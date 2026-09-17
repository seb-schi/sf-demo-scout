#!/usr/bin/env python3
"""Fail-closed reconciliation for Scout phase completion evidence.

This helper reads only local JSON and the approved spec.  It never calls
Salesforce, runs a subprocess, or decides what the spec means.  The orchestrator
owns the expected-work ledger and the provenance of saved tool observations.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 20
MAX_FIELDS = 10_000
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
FLOW_API_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,79}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ITEM_KINDS = {"artifact", "change", "seed", "permission", "assignment", "manual"}
WORKER_STATUSES = {"applied", "already_satisfied", "failed", "blocked", "awaiting_qa"}
SKIP_AUTHORIZATIONS = {"explicit_se_non_execution", "explicit_spec_exclusion"}
VERIFICATIONS = {"targeted_state", "presence", "deployment_receipt", "seed_probe"}
RESULTS = {"match", "mismatch", "unavailable"}
ATTRIBUTIONS = {"applied", "already_satisfied", "unknown"}
FLOW_VALIDATION_MODES = {"flow_test_required", "unsupported"}
FLOW_TEST_OUTCOMES = {
    "PASS",
    "FAIL",
    "ERROR",
    "SKIP",
    "PENDING",
    "UNAVAILABLE",
    "NOT_RUN",
    "NOT_SUPPORTED",
}
PHASE_DETAIL_TYPES = {
    1: {
        "deployed": list,
        "skipped": list,
        "permission_set": dict,
        "data_seeded": list,
        "script_deliverables": list,
        "discovery_notes": list,
        "docs_consulted": list,
        "issues": list,
    },
    2: {
        "deployed": list,
        "skipped": list,
        "rollback_commands": list,
        "discovery_notes": list,
        "docs_consulted": list,
        "issues": list,
    },
    3: {
        "deployed": dict,
        "smoke_test": dict,
        "actions_unverified_in_preview": list,
        "skipped": list,
        "rollback_commands": list,
        "discovery_notes": list,
        "docs_consulted": list,
        "issues": list,
    },
}

AGENTFORCE_GATE_PATH = (
    Path(__file__).resolve().parents[1]
    / "prompts"
    / "building"
    / "agentforce-validation-gate.md"
)
_AGENT_EVIDENCE_PATH = Path(__file__).with_name("agentforce_evidence.py")
_AGENT_EVIDENCE_SPEC = importlib.util.spec_from_file_location(
    "scout_agentforce_evidence", _AGENT_EVIDENCE_PATH
)
if _AGENT_EVIDENCE_SPEC is None or _AGENT_EVIDENCE_SPEC.loader is None:
    raise RuntimeError("cannot load the shipped Agentforce evidence evaluator")
_AGENT_EVIDENCE = importlib.util.module_from_spec(_AGENT_EVIDENCE_SPEC)
_AGENT_EVIDENCE_SPEC.loader.exec_module(_AGENT_EVIDENCE)


class ContractError(ValueError):
    """An input cannot safely participate in reconciliation."""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and len(value.strip()) > 0


def _is_one_of(value: Any, choices: set[str]) -> bool:
    return isinstance(value, str) and value in choices


def _json_shape(value: Any, depth: int = 0) -> tuple[int, int]:
    if depth > MAX_DEPTH:
        raise ContractError(f"JSON nesting exceeds {MAX_DEPTH}")
    if isinstance(value, dict):
        fields = len(value)
        nodes = 1
        for child in value.values():
            child_nodes, child_fields = _json_shape(child, depth + 1)
            nodes += child_nodes
            fields += child_fields
        return nodes, fields
    if isinstance(value, list):
        nodes = 1
        fields = 0
        for child in value:
            child_nodes, child_fields = _json_shape(child, depth + 1)
            nodes += child_nodes
            fields += child_fields
        return nodes, fields
    return 1, 0


def _bounded_json(value: Any, label: str) -> None:
    _nodes, fields = _json_shape(value)
    if fields > MAX_FIELDS:
        raise ContractError(f"{label} contains more than {MAX_FIELDS} fields")


def ledger_sha256(ledger: dict[str, Any]) -> str:
    try:
        canonical = json.dumps(
            ledger, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("ledger is not canonical JSON") from exc
    return hashlib.sha256(canonical).hexdigest()


def _validate_identity(payload: Any, expected: dict[str, Any], label: str) -> list[str]:
    if not isinstance(payload, dict):
        return [f"{label} must be a JSON object"]
    errors = []
    for key in ("schema_version", "build_id", "spec_sha256", "phase"):
        if not _same_json_value(payload.get(key), expected[key]):
            errors.append(f"{label}.{key} does not match the frozen ledger")
    return errors


def _validate_source(source: Any, spec_text: str, label: str) -> None:
    if not isinstance(source, dict):
        raise ContractError(f"{label}.source must be an object")
    if not _nonempty(source.get("location")):
        raise ContractError(f"{label}.source.location must be nonempty")
    quote = source.get("quote")
    if not _nonempty(quote):
        raise ContractError(f"{label}.source.quote must be nonempty")
    if quote not in spec_text:
        raise ContractError(f"{label}.source.quote is not present in the approved spec")


def _validate_calibration(
    acceptance: dict[str, Any], label: str, spec_text: str
) -> None:
    calibration = acceptance.get("calibration")
    if calibration is None:
        return
    if not isinstance(calibration, dict):
        raise ContractError(f"{label}.acceptance.calibration must be an object")
    directive = calibration.get("directive")
    if not _nonempty(directive) or directive not in spec_text:
        raise ContractError(f"{label}.acceptance.calibration.directive is not in the spec")
    if not _nonempty(calibration.get("reference_source")):
        raise ContractError(f"{label}.acceptance.calibration.reference_source is required")
    if not _nonempty(calibration.get("resolved_field")):
        raise ContractError(f"{label}.acceptance.calibration.resolved_field is required")
    resolution = calibration.get("resolution")
    if not _is_one_of(resolution, {"computed", "literal_fallback", "blocked"}):
        raise ContractError(f"{label}.acceptance.calibration.resolution is unsupported")
    if resolution == "blocked":
        if not _nonempty(calibration.get("error")) or "resolved_value" in calibration:
            raise ContractError(f"{label}.acceptance blocked calibration is malformed")
        return
    if "resolved_value" not in calibration:
        raise ContractError(f"{label}.acceptance.calibration.resolved_value is required")
    if resolution == "computed" and calibration.get("reference_result") is None:
        raise ContractError(f"{label}.acceptance computed calibration needs reference_result")
    if resolution == "literal_fallback":
        if not _nonempty(calibration.get("error")) or "spec_literal" not in calibration:
            raise ContractError(f"{label}.acceptance literal fallback is malformed")
        if not _same_json_value(calibration["resolved_value"], calibration["spec_literal"]):
            raise ContractError(f"{label}.acceptance fallback must resolve to spec_literal")
    field = calibration["resolved_field"]
    resolved = calibration["resolved_value"]
    if acceptance["operation"] == "CREATE":
        if field not in acceptance["required_values"] or not _same_json_value(
            acceptance["required_values"][field], resolved
        ):
            raise ContractError(f"{label}.acceptance required_values lack resolved calibration")
    elif not any(
        field in target.get("literal_values", {})
        and _same_json_value(target["literal_values"][field], resolved)
        for target in acceptance["targets"]
    ):
        raise ContractError(f"{label}.acceptance UPDATE targets lack resolved calibration")


def _validate_seed_acceptance(acceptance: Any, label: str, spec_text: str) -> None:
    if not isinstance(acceptance, dict):
        raise ContractError(f"{label}.acceptance must be an object")
    operation = acceptance.get("operation")
    if not _is_one_of(operation, {"CREATE", "UPDATE"}):
        raise ContractError(f"{label}.acceptance.operation must be CREATE or UPDATE")
    if not _nonempty(acceptance.get("object")):
        raise ContractError(f"{label}.acceptance.object must be nonempty")
    if operation == "CREATE":
        count = acceptance.get("count")
        if not _is_int(count) or count <= 0:
            raise ContractError(f"{label}.acceptance.count must be a positive integer")
        if not isinstance(acceptance.get("stable_keys"), dict) or not acceptance["stable_keys"]:
            raise ContractError(f"{label}.acceptance.stable_keys must be nonempty")
        if not isinstance(acceptance.get("required_values"), dict):
            raise ContractError(f"{label}.acceptance.required_values must be an object")
    else:
        if "count" in acceptance:
            raise ContractError(f"{label}.acceptance.count is not valid for UPDATE")
        targets = acceptance.get("targets")
        if not isinstance(targets, list) or not targets:
            raise ContractError(f"{label}.acceptance.targets must be nonempty for UPDATE")
        seen = set()
        for index, target in enumerate(targets):
            target_label = f"{label}.acceptance.targets[{index}]"
            if not isinstance(target, dict):
                raise ContractError(f"{target_label} must be an object")
            stable_key = target.get("stable_key")
            literals = target.get("literal_values", {})
            prose_fields = target.get("prose_fields", [])
            if not isinstance(stable_key, dict) or not stable_key:
                raise ContractError(f"{target_label}.stable_key must be nonempty")
            if not isinstance(literals, dict) or not isinstance(prose_fields, list):
                raise ContractError(f"{target_label} field requirements are malformed")
            if not all(_nonempty(field) for field in prose_fields):
                raise ContractError(f"{target_label}.prose_fields must contain field names")
            if not literals and not prose_fields:
                raise ContractError(f"{target_label} must require literal or prose values")
            if set(literals).intersection(prose_fields):
                raise ContractError(f"{target_label} cannot classify a field twice")
            key = json.dumps(stable_key, sort_keys=True, separators=(",", ":"))
            if key in seen:
                raise ContractError(f"{label}.acceptance.targets contains duplicate stable keys")
            seen.add(key)
    _validate_calibration(acceptance, label, spec_text)


def _validate_ledger(ledger: Any, spec_bytes: bytes) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not isinstance(ledger, dict):
        raise ContractError("ledger must be a JSON object")
    _bounded_json(ledger, "ledger")
    try:
        spec_text = spec_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("approved spec must be UTF-8") from exc
    actual_digest = hashlib.sha256(spec_bytes).hexdigest()
    if not _is_int(ledger.get("schema_version")) or ledger["schema_version"] != 1:
        raise ContractError("ledger.schema_version must be 1")
    if not _nonempty(ledger.get("build_id")) or not ID_PATTERN.fullmatch(ledger["build_id"]):
        raise ContractError("ledger.build_id is malformed")
    if not _nonempty(ledger.get("spec_sha256")) or not SHA256_PATTERN.fullmatch(
        ledger["spec_sha256"]
    ):
        raise ContractError("ledger.spec_sha256 is malformed")
    if ledger["spec_sha256"] != actual_digest:
        raise ContractError("ledger.spec_sha256 does not match the actual approved spec")
    if not _is_int(ledger.get("phase")) or ledger["phase"] not in {1, 2, 3}:
        raise ContractError("ledger.phase must be 1, 2, or 3")

    items = ledger.get("items")
    if not isinstance(items, list) or not items:
        raise ContractError("ledger.items must be a nonempty array")
    indexed: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        label = f"ledger.items[{index}]"
        if not isinstance(item, dict):
            raise ContractError(f"{label} must be an object")
        item_id = item.get("id")
        if not _nonempty(item_id) or not ID_PATTERN.fullmatch(item_id):
            raise ContractError(f"{label}.id is malformed")
        if item_id in indexed:
            raise ContractError(f"ledger contains duplicate item id {item_id}")
        if not _is_one_of(item.get("kind"), ITEM_KINDS):
            raise ContractError(f"{label}.kind is unsupported")
        if not _is_int(item.get("phase")) or item["phase"] != ledger["phase"]:
            raise ContractError(f"{label}.phase does not match ledger.phase")
        _validate_source(item.get("source"), spec_text, label)
        if not isinstance(item.get("acceptance"), dict):
            raise ContractError(f"{label}.acceptance must be an object")
        if item["kind"] == "seed":
            _validate_seed_acceptance(item["acceptance"], label, spec_text)
        else:
            acceptance = item["acceptance"]
            if not _nonempty(acceptance.get("description")):
                raise ContractError(f"{label}.acceptance.description must be nonempty")
            if not isinstance(acceptance.get("expected_state"), dict) or not acceptance[
                "expected_state"
            ]:
                raise ContractError(f"{label}.acceptance.expected_state must be nonempty")
            if "agent_runtime" in acceptance:
                try:
                    _AGENT_EVIDENCE.validate_expected(acceptance["agent_runtime"])
                except _AGENT_EVIDENCE.EvidenceError as exc:
                    raise ContractError(f"{label}.acceptance.agent_runtime: {exc}") from exc
            if "flow_validation" in acceptance:
                flow_validation = acceptance["flow_validation"]
                if ledger["phase"] != 2 or not isinstance(flow_validation, dict):
                    raise ContractError(
                        f"{label}.acceptance.flow_validation must be an object for phase 2"
                    )
                flow_name = flow_validation.get("flow_api_name")
                test_name = flow_validation.get("flow_test_api_name")
                mode = flow_validation.get("mode")
                if not isinstance(flow_name, str) or not FLOW_API_PATTERN.fullmatch(flow_name):
                    raise ContractError(
                        f"{label}.acceptance.flow_validation.flow_api_name is malformed"
                    )
                if not _is_one_of(mode, FLOW_VALIDATION_MODES):
                    raise ContractError(
                        f"{label}.acceptance.flow_validation.mode is unsupported"
                    )
                if mode == "flow_test_required":
                    if not isinstance(test_name, str) or not FLOW_API_PATTERN.fullmatch(test_name):
                        raise ContractError(
                            f"{label}.acceptance.flow_validation.flow_test_api_name is malformed"
                        )
                    if "unsupported_reason" in flow_validation:
                        raise ContractError(
                            f"{label}.acceptance.flow_validation.unsupported_reason conflicts with required testing"
                        )
                elif test_name is not None or not _nonempty(
                    flow_validation.get("unsupported_reason")
                ):
                    raise ContractError(
                        f"{label}.acceptance.flow_validation unsupported mode requires a null test name and reason"
                    )
        indexed[item_id] = item
    return ledger, indexed


def _index_rows(
    rows: Any,
    id_key: str,
    expected_ids: set[str],
    label: str,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        errors.append(f"{label} must be an array")
        return {}
    indexed = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not _nonempty(row.get(id_key)):
            errors.append(f"{label}[{index}].{id_key} is missing or malformed")
            continue
        item_id = row[id_key]
        if item_id in indexed:
            errors.append(f"{label} contains duplicate item id {item_id}")
            continue
        if item_id not in expected_ids:
            errors.append(f"{label} contains unexpected item id {item_id}")
            continue
        indexed[item_id] = row
    return indexed


def _authorized_skips(
    ledger: dict[str, Any],
    expected_ids: set[str],
    spec_text: str,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    skips = ledger.get("authorized_skips", [])
    indexed = _index_rows(skips, "item_id", expected_ids, "ledger.authorized_skips", errors)
    valid = {}
    for item_id, skip in indexed.items():
        if not _is_one_of(skip.get("authorization_type"), SKIP_AUTHORIZATIONS):
            errors.append(
                f"authorized skip {item_id} requires explicit SE non-execution or spec exclusion"
            )
            continue
        if not _nonempty(skip.get("decision_source")) or not _nonempty(skip.get("reason")):
            errors.append(f"authorized skip {item_id} requires decision_source and reason")
            continue
        if skip["authorization_type"] == "explicit_spec_exclusion":
            try:
                _validate_source(skip.get("source"), spec_text, f"authorized skip {item_id}")
            except ContractError as exc:
                errors.append(str(exc))
                continue
        elif skip.get("decision_source_type") != "se_decision":
            errors.append(
                f"authorized skip {item_id} requires decision_source_type se_decision"
            )
            continue
        valid[item_id] = skip
    return valid


def _worker_rows(
    worker: Any,
    identity: dict[str, Any],
    expected_ids: set[str],
    authorized_skips: dict[str, dict[str, Any]],
    agent_actions: dict[str, str],
    errors: list[str],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, list[tuple[str, str]]],
    set[str],
    dict[str, dict[str, Any]],
]:
    if worker is None:
        return {}, {}, {}, set(), {}
    _bounded_json(worker, "worker result")
    errors.extend(_validate_identity(worker, identity, "worker result"))
    if not isinstance(worker, dict):
        return {}, {}, {}, set(), {}
    phase = identity["phase"]
    for key, wanted_type in PHASE_DETAIL_TYPES[phase].items():
        if key not in worker:
            errors.append(f"worker result.{key} is required for phase {phase}")
        elif type(worker[key]) is not wanted_type:
            errors.append(f"worker result.{key} must be {wanted_type.__name__}")
    completion = _index_rows(
        worker.get("completion"), "item_id", expected_ids, "worker completion", errors
    )
    for item_id, row in completion.items():
        if not _is_one_of(row.get("status"), WORKER_STATUSES):
            errors.append(f"worker completion {item_id}.status is unsupported")
        if not _nonempty(row.get("summary")):
            errors.append(f"worker completion {item_id}.summary must be nonempty")
    data_seeded = _index_rows(
        worker.get("data_seeded", []) if isinstance(worker.get("data_seeded", []), list) else [],
        "ledger_item_id",
        expected_ids,
        "worker data_seeded",
        errors,
    )
    detail_outcomes: dict[str, list[tuple[str, str]]] = {}

    def add_outcome(item_id: str, disposition: str, reason: str) -> None:
        detail_outcomes.setdefault(item_id, []).append((disposition, reason))

    deployed_rows: dict[str, dict[str, Any]] = {}
    if phase in {1, 2} and isinstance(worker.get("deployed"), list):
        deployed_rows = _index_rows(
            worker["deployed"], "ledger_item_id", expected_ids, "worker deployed", errors
        )
        for item_id, row in deployed_rows.items():
            status = row.get("status")
            if not _is_one_of(status, {"SUCCESS", "FAILED"}):
                errors.append(f"worker deployed {item_id}.status is unsupported")
            elif status == "FAILED":
                add_outcome(item_id, "FAILED", "detailed deployed row reports FAILED")
            if phase == 2:
                validation = row.get("validation_status")
                if validation is not None and not _is_one_of(
                    validation, {"VERIFIED", "AWAITING_QA", "FAILED"}
                ):
                    errors.append(
                        f"worker deployed {item_id}.validation_status is unsupported"
                    )
                elif validation == "FAILED":
                    add_outcome(item_id, "FAILED", "detailed validation reports FAILED")
                elif validation == "AWAITING_QA" or row.get("flow_status") == "Draft":
                    add_outcome(item_id, "AWAITING_QA", "detailed artifact remains unvalidated")

    skipped_rows: dict[str, dict[str, Any]] = {}
    if isinstance(worker.get("skipped"), list):
        skipped_rows = _index_rows(
            worker["skipped"], "ledger_item_id", expected_ids, "worker skipped", errors
        )
        for item_id, row in skipped_rows.items():
            authorization = authorized_skips.get(item_id)
            if authorization is None:
                errors.append(f"worker skipped {item_id} lacks an authorized omission")
            elif row.get("reason") != authorization["reason"]:
                errors.append(f"worker skipped {item_id}.reason does not mirror the ledger")

    if phase == 1:
        permission = worker.get("permission_set")
        if isinstance(permission, dict):
            status = permission.get("status")
            if not _is_one_of(status, {"SUCCESS", "FAILED", "NOT_APPLICABLE"}):
                errors.append("worker permission_set.status is unsupported")
            elif status != "NOT_APPLICABLE":
                permission_rows = _index_rows(
                    [permission],
                    "ledger_item_id",
                    expected_ids,
                    "worker permission_set",
                    errors,
                )
                for item_id in permission_rows:
                    if status == "FAILED":
                        add_outcome(item_id, "FAILED", "permission-set detail reports FAILED")
        if isinstance(worker.get("script_deliverables"), list):
            scripts = _index_rows(
                worker["script_deliverables"],
                "ledger_item_id",
                expected_ids,
                "worker script_deliverables",
                errors,
            )
            for item_id, row in scripts.items():
                self_test = row.get("self_test_status")
                if not _is_one_of(self_test, {"PASS", "FAIL", "NOT_APPLICABLE"}):
                    errors.append(
                        f"worker script_deliverables {item_id}.self_test_status is unsupported"
                    )
                elif self_test == "FAIL":
                    add_outcome(item_id, "FAILED", "script self-test reports FAIL")

    if phase == 3 and isinstance(worker.get("deployed"), dict):
        deployed = worker["deployed"]
        for nested, wanted in (
            ("agent", dict),
            ("backing_actions", list),
            ("agent_user", dict),
            ("standard_permset_assignment", dict),
        ):
            if type(deployed.get(nested)) is not wanted:
                errors.append(f"worker deployed.{nested} must be {wanted.__name__}")
        agent = deployed.get("agent")
        if isinstance(agent, dict):
            agent_rows = _index_rows(
                [agent], "ledger_item_id", expected_ids, "worker deployed.agent", errors
            )
            for item_id, row in agent_rows.items():
                status = row.get("status")
                if not _is_one_of(status, {"Active", "Inactive", "NeedsUICommit"}):
                    errors.append(f"worker deployed.agent {item_id}.status is unsupported")
                recovery = row.get("recovery")
                if not isinstance(recovery, dict) or not _is_one_of(
                    recovery.get("status") if isinstance(recovery, dict) else None,
                    {"not_needed", "verified", "failed"},
                ):
                    errors.append(f"worker deployed.agent {item_id}.recovery is malformed")
                elif recovery["status"] == "failed":
                    add_outcome(item_id, "BLOCKED", "agent recovery preservation failed")
                # Legacy/new-agent reports may omit this additive detail. The
                # orchestrator determines from approved intent whether it is required.
                if "preedit_snapshot" in row:
                    preedit = row["preedit_snapshot"]
                    if not isinstance(preedit, dict) or not _is_one_of(
                        preedit.get("status") if isinstance(preedit, dict) else None,
                        {"not_needed", "verified", "failed"},
                    ):
                        errors.append(f"worker deployed.agent {item_id}.preedit_snapshot is malformed")
                    elif preedit["status"] == "failed":
                        add_outcome(item_id, "BLOCKED", "agent pre-edit preservation failed")
                    elif preedit["status"] == "not_needed" and not (
                        preedit.get("artifact") is None
                        and preedit.get("source") is None
                        and preedit.get("error") is None
                        and preedit.get("paths") == []
                    ):
                        errors.append(f"worker deployed.agent {item_id}.preedit_snapshot is malformed")
                    elif preedit["status"] == "verified" and not (
                        _nonempty(preedit.get("artifact"))
                        and Path(preedit["artifact"]).is_absolute()
                        and _nonempty(preedit.get("source"))
                        and Path(preedit["source"]).is_absolute()
                        and isinstance(preedit.get("paths"), list)
                        and preedit["paths"]
                        and all(_nonempty(path) for path in preedit["paths"])
                        and preedit.get("error") is None
                    ):
                        errors.append(f"worker deployed.agent {item_id}.preedit_snapshot is malformed")
                if _is_one_of(status, {"Inactive", "NeedsUICommit"}):
                    add_outcome(item_id, "BLOCKED", f"agent status is {status}")
        actions = deployed.get("backing_actions")
        if isinstance(actions, list):
            action_rows = _index_rows(
                actions,
                "ledger_item_id",
                expected_ids,
                "worker deployed.backing_actions",
                errors,
            )
            for item_id, row in action_rows.items():
                status = row.get("status")
                if not _is_one_of(status, {"SUCCESS", "FAILED"}):
                    errors.append(f"worker backing action {item_id}.status is unsupported")
                elif status == "FAILED":
                    add_outcome(item_id, "FAILED", "backing-action detail reports FAILED")
        agent_user = deployed.get("agent_user")
        if isinstance(agent_user, dict) and _nonempty(agent_user.get("username")):
            _index_rows(
                [agent_user], "ledger_item_id", expected_ids, "worker deployed.agent_user", errors
            )
        assignment = deployed.get("standard_permset_assignment")
        if isinstance(assignment, dict):
            assignment_status = assignment.get("status")
            if not _is_one_of(assignment_status, {"SUCCESS", "FAILED", "NOT_FOUND"}):
                errors.append("worker standard_permset_assignment.status is unsupported")
            elif assignment.get("ledger_item_id") is not None:
                assignment_rows = _index_rows(
                    [assignment],
                    "ledger_item_id",
                    expected_ids,
                    "worker standard_permset_assignment",
                    errors,
                )
                for item_id in assignment_rows:
                    if assignment_status == "FAILED":
                        add_outcome(item_id, "FAILED", "standard permission assignment failed")
                    elif assignment_status == "NOT_FOUND":
                        add_outcome(item_id, "BLOCKED", "standard permission set was not found")
        smoke = worker.get("smoke_test")
        if isinstance(smoke, dict):
            smoke_rows = _index_rows(
                [smoke], "ledger_item_id", expected_ids, "worker smoke_test", errors
            )
            for item_id in smoke_rows:
                if smoke.get("ran") is not True or smoke.get("action_invocation_confirmed") is not True:
                    reason = "agent smoke/runtime validation is outstanding"
                    if item_id in agent_actions:
                        reason = f"[agent runtime] {reason}"
                    add_outcome(item_id, "AWAITING_QA", reason)
        if isinstance(worker.get("actions_unverified_in_preview"), list):
            unverified = _index_rows(
                worker["actions_unverified_in_preview"],
                "ledger_item_id",
                expected_ids,
                "worker actions_unverified_in_preview",
                errors,
            )
            for item_id, row in unverified.items():
                action = row.get("action")
                if item_id in agent_actions and action != agent_actions[item_id]:
                    errors.append(
                        f"worker actions_unverified_in_preview {item_id} names a different action; use a distinct ledger item"
                    )
                    add_outcome(item_id, "AWAITING_QA", "different action remains unverified")
                else:
                    reason = "action remains unverified in preview"
                    if item_id in agent_actions:
                        reason = f"[agent runtime] {reason}"
                    add_outcome(item_id, "AWAITING_QA", reason)

    return completion, data_seeded, detail_outcomes, set(skipped_rows), deployed_rows


def _evidence_rows(
    evidence: Any,
    identity: dict[str, Any],
    expected_ids: set[str],
    expected_ledger_digest: str,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    if evidence is None:
        return {}
    _bounded_json(evidence, "evidence")
    errors.extend(_validate_identity(evidence, identity, "evidence"))
    if not isinstance(evidence, dict):
        return {}
    if evidence.get("ledger_sha256") != expected_ledger_digest:
        errors.append("evidence.ledger_sha256 does not match the final ledger")
    if not _nonempty(evidence.get("orchestrator_provenance")):
        errors.append("evidence.orchestrator_provenance must be nonempty")
    observations = _index_rows(
        evidence.get("observations"),
        "item_id",
        expected_ids,
        "evidence observations",
        errors,
    )
    for item_id, row in observations.items():
        if not _is_one_of(row.get("verification"), VERIFICATIONS):
            errors.append(f"evidence observation {item_id}.verification is unsupported")
        if not _is_one_of(row.get("result"), RESULTS):
            errors.append(f"evidence observation {item_id}.result is unsupported")
        if not _is_one_of(row.get("attribution"), ATTRIBUTIONS):
            errors.append(f"evidence observation {item_id}.attribution is unsupported")
        if not _nonempty(row.get("source")) or not _nonempty(row.get("details")):
            errors.append(f"evidence observation {item_id} requires source and details")
    return observations


def _agent_context_rows(
    evidence: Any,
    agent_item_ids: set[str],
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    if not agent_item_ids or not isinstance(evidence, dict):
        return {}
    return _index_rows(
        evidence.get("agent_contexts", []),
        "item_id",
        agent_item_ids,
        "evidence agent_contexts",
        errors,
    )


def _agent_runtime_assessments(
    items: dict[str, dict[str, Any]],
    observations: dict[str, dict[str, Any]],
    contexts: dict[str, dict[str, Any]],
    canonical_gate_bytes: bytes,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    assessments: dict[str, dict[str, Any]] = {}
    for item_id, item in items.items():
        expected = item["acceptance"].get("agent_runtime")
        if expected is None:
            continue
        context = contexts.get(item_id)
        observation = observations.get(item_id)
        runtime = observation.get("agent_runtime") if isinstance(observation, dict) else None
        if context is None or runtime is None:
            assessments[item_id] = {
                "valid": True,
                "observed": False,
                "assessment": "UNAVAILABLE",
                "reason": "independent deployed-version or current-test evidence is missing",
            }
            continue
        assessment = _AGENT_EVIDENCE.assess(
            expected, context, runtime, canonical_gate_bytes
        )
        assessment["observed"] = True
        assessments[item_id] = assessment
        if not assessment["valid"]:
            errors.append(
                f"agent runtime evidence {item_id} is malformed: {assessment['reason']}"
            )
    return assessments


def _positive_int(value: Any) -> bool:
    return _is_int(value) and value > 0


def _flow_validation_assessments(
    items: dict[str, dict[str, Any]],
    deployed_rows: dict[str, dict[str, Any]],
    observations: dict[str, dict[str, Any]],
    worker_present: bool,
    authorized_skips: dict[str, dict[str, Any]],
    reported_skips: set[str],
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    """Check normalized Flow claims against independent version-bound evidence."""
    assessments: dict[str, dict[str, Any]] = {}

    def assessed(
        item_id: str,
        assessment: str,
        reason: str,
        *,
        valid: bool = True,
        observed: bool = True,
    ) -> dict[str, Any]:
        result = {
            "valid": valid,
            "observed": observed,
            "assessment": assessment,
            "reason": reason,
        }
        assessments[item_id] = result
        if not valid:
            errors.append(f"Flow validation {item_id} is malformed: {reason}")
        return result

    for item_id, item in items.items():
        expected = item["acceptance"].get("flow_validation")
        if expected is None:
            continue
        if not worker_present:
            assessed(
                item_id,
                "INCOMPLETE",
                "worker Flow deployment report is missing",
                observed=False,
            )
            continue
        row = deployed_rows.get(item_id)
        observation = observations.get(item_id)
        if (
            item_id in authorized_skips
            and item_id in reported_skips
            and row is None
            and (
                observation is None
                or not _is_one_of(
                    observation.get("attribution"), {"applied", "already_satisfied"}
                )
            )
        ):
            continue
        if row is None:
            assessed(item_id, "INVALID", "worker deployed Flow row is missing", valid=False)
            continue
        if row.get("type") != "Flow" or row.get("api_name") != expected["flow_api_name"]:
            assessed(
                item_id,
                "INVALID",
                "worker deployed Flow type or API name contradicts the ledger",
                valid=False,
            )
            continue
        if row.get("status") == "FAILED":
            assessed(item_id, "FAILED", "worker deployed Flow row reports FAILED")
            continue
        if row.get("status") != "SUCCESS":
            assessed(item_id, "INVALID", "worker deployed Flow status is malformed", valid=False)
            continue
        if (
            not _nonempty(row.get("flow_version_id"))
            or not _positive_int(row.get("flow_version_number"))
            or not _is_one_of(row.get("flow_status"), {"Active", "Draft", "Unknown"})
            or not _is_one_of(
                row.get("validation_status"), {"VERIFIED", "AWAITING_QA", "FAILED"}
            )
            or not _is_one_of(row.get("flow_test_outcome"), FLOW_TEST_OUTCOMES)
        ):
            assessed(item_id, "INVALID", "worker deployed Flow validation fields are malformed", valid=False)
            continue

        flow_evidence = observation.get("flow_validation") if observation else None
        if flow_evidence is None:
            assessed(
                item_id,
                "INCOMPLETE",
                "independent version-bound Flow evidence is missing",
                observed=False,
            )
            continue
        if not isinstance(flow_evidence, dict) or flow_evidence.get("mode") != expected["mode"]:
            assessed(
                item_id,
                "INVALID",
                "independent Flow evidence mode contradicts the frozen ledger",
                valid=False,
            )
            continue
        deployment = flow_evidence.get("deployment")
        test = flow_evidence.get("test")
        activation = flow_evidence.get("activation")
        if not all(isinstance(value, dict) for value in (deployment, test, activation)):
            assessed(
                item_id,
                "INVALID",
                "independent Flow deployment, test, and activation evidence are required",
                valid=False,
            )
            continue
        if (
            deployment.get("flow_api_name") != expected["flow_api_name"]
            or not _nonempty(deployment.get("flow_id"))
            or not _positive_int(deployment.get("version"))
            or not _is_one_of(deployment.get("status"), {"Draft", "Active"})
        ):
            assessed(item_id, "INVALID", "independent deployed Flow identity is malformed", valid=False)
            continue
        attribution = observation.get("attribution") if observation else None
        if attribution == "applied":
            if deployment.get("status") != "Draft" or not all(
                _nonempty(deployment.get(key)) for key in ("receipt_source", "file_source")
            ):
                assessed(
                    item_id,
                    "INVALID",
                    "applied Flow lacks an exact Draft deployment receipt and file identity",
                    valid=False,
                )
                continue
        elif attribution == "already_satisfied":
            if (
                deployment.get("status") != "Active"
                or deployment.get("receipt_source") is not None
                or deployment.get("file_source") is not None
                or not _nonempty(deployment.get("baseline_source"))
                or not _nonempty(deployment.get("current_source"))
            ):
                assessed(
                    item_id,
                    "INVALID",
                    "already-satisfied Flow lacks baseline and current exact active identity",
                    valid=False,
                )
                continue
        else:
            assessed(
                item_id,
                "INCOMPLETE",
                "Flow evidence lacks applied or already-satisfied attribution",
            )
            continue

        active_id = activation.get("active_flow_id")
        active_version = activation.get("active_version")
        if type(activation.get("attempted")) is not bool or not _nonempty(
            activation.get("source")
        ):
            assessed(item_id, "INVALID", "Flow activation evidence is malformed", valid=False)
            continue
        if (active_id is None) != (active_version is None) or (
            active_version is not None and not _positive_int(active_version)
        ):
            assessed(item_id, "INVALID", "Flow active identity is malformed", valid=False)
            continue
        if (
            row.get("flow_version_id") != deployment["flow_id"]
            or row.get("flow_version_number") != deployment["version"]
            or row.get("active_flow_id") != active_id
            or row.get("active_flow_version_number") != active_version
        ):
            assessed(
                item_id,
                "INVALID",
                "worker Flow version or active identity contradicts independent evidence",
                valid=False,
            )
            continue

        if expected["mode"] == "unsupported":
            if (
                test.get("status") != "unsupported"
                or test.get("reason") != expected["unsupported_reason"]
                or activation.get("attempted") is not False
                or not _is_one_of(activation.get("status"), {"not_attempted", "Active"})
                or row.get("validation_status") != "AWAITING_QA"
                or row.get("flow_test_outcome") != "NOT_SUPPORTED"
                or row.get("flow_test_api_name") is not None
                or row.get("flow_test_run_id") is not None
                or row.get("flow_test_queue_item_id") is not None
                or row.get("tested_flow_version_number") is not None
            ):
                assessed(
                    item_id,
                    "INVALID",
                    "unsupported Flow claims contradict the immutable ledger mode",
                    valid=False,
                )
                continue
            expected_flow_status = "Active" if attribution == "already_satisfied" else "Draft"
            if row.get("flow_status") != expected_flow_status:
                assessed(
                    item_id,
                    "INVALID",
                    "unsupported Flow state contradicts deployment attribution",
                    valid=False,
                )
                continue
            assessed(
                item_id,
                "AWAITING_QA",
                expected["unsupported_reason"],
            )
            continue

        if (
            test.get("flow_api_name") != expected["flow_api_name"]
            or test.get("test_api_name") != expected["flow_test_api_name"]
            or not _nonempty(test.get("launch_source"))
            or row.get("flow_test_api_name") != test.get("test_api_name")
            or row.get("flow_test_run_id") != test.get("run_id")
            or row.get("flow_test_queue_item_id") != test.get("queue_item_id")
        ):
            assessed(item_id, "INVALID", "Flow test identity or launch evidence is malformed", valid=False)
            continue
        test_status = test.get("status")
        if test_status == "terminal":
            if (
                not _is_one_of(test.get("outcome"), {"Pass", "Fail", "Error", "Skip"})
                or not _nonempty(test.get("run_id"))
                or not _nonempty(test.get("queue_item_id"))
                or not _positive_int(test.get("tested_version"))
                or not _nonempty(test.get("terminal_source"))
                or not _nonempty(test.get("version_source"))
            ):
                assessed(item_id, "INVALID", "terminal Flow test evidence is malformed", valid=False)
                continue
        elif _is_one_of(test_status, {"pending", "unavailable"}):
            if test.get("outcome") is not None or test.get("tested_version") is not None:
                assessed(
                    item_id,
                    "INVALID",
                    "nonterminal Flow test evidence asserts an outcome or tested version",
                    valid=False,
                )
                continue
            if test_status == "pending" and not _nonempty(test.get("run_id")):
                assessed(item_id, "INVALID", "pending Flow test lacks run identity", valid=False)
                continue
        else:
            assessed(item_id, "INVALID", "Flow test status is malformed", valid=False)
            continue

        normalized_outcome = (
            test.get("outcome", "").upper() if isinstance(test.get("outcome"), str) else None
        )
        if (
            row.get("flow_test_outcome")
            != ({"pending": "PENDING", "unavailable": "UNAVAILABLE"}.get(test_status) or normalized_outcome)
            or row.get("tested_flow_version_number") != test.get("tested_version")
        ):
            assessed(
                item_id,
                "INVALID",
                "worker Flow test outcome or tested version contradicts independent evidence",
                valid=False,
            )
            continue

        activation_status = activation.get("status")
        if activation_status == "unknown":
            if activation.get("attempted") is not True or active_id is not None:
                assessed(item_id, "INVALID", "unknown activation evidence is malformed", valid=False)
            else:
                assessed(
                    item_id,
                    "INCOMPLETE",
                    "activation was attempted but exact active identity read-back is unavailable",
                )
            continue
        if activation_status == "failed":
            if activation.get("attempted") is not True:
                assessed(item_id, "INVALID", "failed activation was not marked attempted", valid=False)
            else:
                assessed(item_id, "BLOCKED", "exact-version Flow activation failed")
            continue
        if activation_status == "not_attempted":
            if activation.get("attempted") is not False:
                assessed(item_id, "INVALID", "non-attempted activation evidence is malformed", valid=False)
                continue
        elif activation_status == "Active":
            if (
                (attribution == "applied" and activation.get("attempted") is not True)
                or (attribution == "already_satisfied" and activation.get("attempted") is not False)
                or active_id != deployment["flow_id"]
                or active_version != deployment["version"]
            ):
                assessed(
                    item_id,
                    "INVALID",
                    "active Flow identity does not match the exact deployed/tested version",
                    valid=False,
                )
                continue
        else:
            assessed(item_id, "INVALID", "Flow activation status is malformed", valid=False)
            continue

        exact_pass = (
            test_status == "terminal"
            and test.get("outcome") == "Pass"
            and test.get("tested_version") == deployment["version"]
            and activation_status == "Active"
            and active_id == deployment["flow_id"]
            and active_version == deployment["version"]
        )
        if exact_pass:
            if row.get("flow_status") != "Active" or not _is_one_of(
                row.get("validation_status"), {"VERIFIED", "AWAITING_QA"}
            ):
                assessed(item_id, "INVALID", "worker Flow active validation claim is malformed", valid=False)
            elif row.get("validation_status") == "AWAITING_QA":
                assessed(item_id, "AWAITING_QA", "worker still reports Flow validation outstanding")
            else:
                assessed(item_id, "VERIFIED", "exact deployed Flow version passed and is active")
            continue
        if row.get("validation_status") == "VERIFIED" or row.get("flow_status") == "Active":
            assessed(
                item_id,
                "INVALID",
                "worker claims verified/active without an exact deployed-version pass and read-back",
                valid=False,
            )
            continue
        assessed(
            item_id,
            "AWAITING_QA",
            "exact deployed Flow version is not yet terminal-passed and active",
        )
    return assessments


def _same_json_value(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(
            _same_json_value(actual[key], wanted) for key, wanted in expected.items()
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _same_json_value(left, right) for left, right in zip(actual, expected)
        )
    return actual == expected


def _seed_report_problem(item: dict[str, Any], row: dict[str, Any] | None) -> str | None:
    if row is None:
        return "worker data_seeded report is missing"
    acceptance = item["acceptance"]
    if row.get("operation") != acceptance["operation"]:
        return "worker data_seeded operation contradicts the ledger"
    if row.get("object") != acceptance["object"]:
        return "worker data_seeded object contradicts the ledger"
    if row.get("status") == "FAILED":
        return "worker data_seeded reports failure"
    if row.get("status") != "SUCCESS":
        return "worker data_seeded status is malformed"
    records = row.get("records")
    if not _is_int(records) or records < 0:
        return "worker data_seeded records must be a nonnegative integer"
    if acceptance["operation"] == "CREATE" and records < acceptance["count"]:
        return "worker data_seeded records are zero or shorter than the approved count"
    return None


def _create_probe_problem(acceptance: dict[str, Any], probe: Any) -> tuple[str, str] | None:
    if not isinstance(probe, dict):
        return "INCOMPLETE", "independent seed_probe is missing"
    if probe.get("operation") != "CREATE" or probe.get("object") != acceptance["object"]:
        return "INCOMPLETE", "independent CREATE probe identity contradicts the ledger"
    if probe.get("stable_keys") != acceptance["stable_keys"]:
        return "INCOMPLETE", "independent CREATE probe widened or changed the stable keys"
    if probe.get("required_values") != acceptance["required_values"]:
        return "INCOMPLETE", "independent CREATE probe changed the requested values"
    matched_count = probe.get("matched_count")
    if not _is_int(matched_count) or matched_count < 0:
        return "INCOMPLETE", "independent CREATE matched_count is malformed"
    if matched_count < acceptance["count"]:
        return "FAILED", "independent CREATE probe found fewer rows than the approved count"
    if probe.get("values_match") is not True:
        return "FAILED", "independent CREATE probe found wrong requested values"
    return None


def _update_probe_problem(acceptance: dict[str, Any], probe: Any) -> tuple[str, str] | None:
    if not isinstance(probe, dict):
        return "INCOMPLETE", "independent seed_probe is missing"
    if probe.get("operation") != "UPDATE" or probe.get("object") != acceptance["object"]:
        return "INCOMPLETE", "independent UPDATE probe identity contradicts the ledger"
    observed = probe.get("targets")
    if not isinstance(observed, list):
        return "INCOMPLETE", "independent UPDATE targets are missing"
    observed_by_key = {}
    for target in observed:
        if not isinstance(target, dict) or not isinstance(target.get("stable_key"), dict):
            return "INCOMPLETE", "independent UPDATE target is malformed"
        key = json.dumps(target["stable_key"], sort_keys=True, separators=(",", ":"))
        if key in observed_by_key:
            return "INCOMPLETE", "independent UPDATE probe contains duplicate targets"
        observed_by_key[key] = target
    if len(observed_by_key) != len(acceptance["targets"]):
        return "INCOMPLETE", "independent UPDATE probe did not check every exact target"
    for expected in acceptance["targets"]:
        key = json.dumps(expected["stable_key"], sort_keys=True, separators=(",", ":"))
        target = observed_by_key.get(key)
        if target is None:
            return "INCOMPLETE", "independent UPDATE probe changed or omitted a stable target"
        actual_values = target.get("actual_values")
        if not isinstance(actual_values, dict):
            return "INCOMPLETE", "independent UPDATE actual_values are missing"
        for field, wanted in expected.get("literal_values", {}).items():
            if field not in actual_values or not _same_json_value(actual_values[field], wanted):
                return "FAILED", f"independent UPDATE literal field {field} does not match"
        for field in expected.get("prose_fields", []):
            if not _nonempty(actual_values.get(field)):
                return "FAILED", f"independent UPDATE prose field {field} is blank"
    return None


def _verification_problem(
    item: dict[str, Any], observation: dict[str, Any] | None
) -> tuple[str, str] | None:
    if observation is None:
        return "INCOMPLETE", "independent orchestrator observation is missing"
    if observation.get("result") == "mismatch":
        return "FAILED", "independent targeted observation found the requested state mismatched"
    if observation.get("result") != "match":
        return "INCOMPLETE", "independent observation is unavailable"
    if item["kind"] == "seed":
        if observation.get("verification") != "seed_probe":
            return "INCOMPLETE", "seed item lacks an independent targeted seed probe"
        if item["acceptance"]["operation"] == "CREATE":
            problem = _create_probe_problem(item["acceptance"], observation.get("seed_probe"))
        else:
            problem = _update_probe_problem(item["acceptance"], observation.get("seed_probe"))
        if problem is not None:
            return problem
        calibration = item["acceptance"].get("calibration")
        if calibration is not None and calibration.get("resolution") != "blocked":
            probe = observation.get("seed_probe")
            if probe.get("calibration_source") != calibration["reference_source"]:
                return "INCOMPLETE", "independent seed probe lacks calibration provenance"
        return None
    if observation.get("verification") != "targeted_state":
        return "INCOMPLETE", "presence or deployment receipt alone does not verify requested state"
    actual_state = observation.get("actual_state")
    if not isinstance(actual_state, dict):
        return "INCOMPLETE", "targeted observation actual_state is missing"
    if not _same_json_value(actual_state, item["acceptance"]["expected_state"]):
        return "FAILED", "targeted observation actual_state does not match expected_state"
    return None


def _item_result(
    item: dict[str, Any],
    completion: dict[str, Any] | None,
    observation: dict[str, Any] | None,
    seed_report: dict[str, Any] | None,
    authorized_skip: dict[str, Any] | None,
    detail_outcomes: list[tuple[str, str]],
    worker_present: bool,
    skipped_detail: bool,
    global_report_invalid: bool,
    runtime_assessment: dict[str, Any] | None,
    flow_assessment: dict[str, Any] | None,
) -> dict[str, Any]:
    item_id = item["id"]
    result = {
        "item_id": item_id,
        "disposition": "INCOMPLETE",
        "execution": None,
        "reason": "worker completion report is missing",
        "automatic_retry": False,
    }
    if runtime_assessment is not None:
        result["runtime_assessment"] = runtime_assessment
    if flow_assessment is not None:
        result["flow_assessment"] = flow_assessment
    skip_is_uncontradicted = (
        completion is None
        and seed_report is None
        and (not worker_present or skipped_detail)
        and not (
            runtime_assessment is not None and runtime_assessment.get("observed") is True
        )
        and (
            observation is None
            or not _is_one_of(
                observation.get("attribution"), {"applied", "already_satisfied"}
            )
        )
    )
    if authorized_skip is not None and skip_is_uncontradicted:
        result.update(
            disposition="SKIPPED",
            reason=authorized_skip["reason"],
            skip_decision_source=authorized_skip["decision_source"],
        )
        return result
    if authorized_skip is not None:
        runtime_outcome = (
            runtime_assessment.get("assessment") if runtime_assessment is not None else None
        )
        if runtime_assessment is not None and runtime_assessment.get("observed") is True:
            if runtime_outcome == "FAIL":
                result.update(disposition="FAILED", reason=runtime_assessment["reason"])
                return result
            if runtime_outcome == "BLOCKED":
                result.update(disposition="BLOCKED", reason=runtime_assessment["reason"])
                return result
        if completion is not None and completion.get("status") == "failed":
            result.update(disposition="FAILED", reason=completion.get("summary", "reported failure"))
            return result
        if completion is not None and completion.get("status") == "blocked":
            result.update(disposition="BLOCKED", reason=completion.get("summary", "reported block"))
            return result
        result["reason"] = (
            "authorized non-execution is contradicted by reported or observed attempted work"
        )
        return result
    calibration = item["acceptance"].get("calibration") if item["kind"] == "seed" else None
    if calibration is not None and calibration.get("resolution") == "blocked":
        result.update(disposition="BLOCKED", reason=calibration["error"])
        return result
    if runtime_assessment is not None:
        runtime_outcome = runtime_assessment["assessment"]
        if runtime_outcome == "FAIL":
            result.update(disposition="FAILED", reason=runtime_assessment["reason"])
            return result
        if runtime_outcome == "BLOCKED":
            result.update(disposition="BLOCKED", reason=runtime_assessment["reason"])
            return result
        if runtime_outcome == "INVALID":
            result["reason"] = runtime_assessment["reason"]
            return result
    if completion is None:
        if item["kind"] == "manual":
            result.update(
                disposition="BLOCKED",
                reason="manual/SE action is still required and has no explicit non-execution authorization",
            )
        return result
    status = completion.get("status")
    if not _is_one_of(status, WORKER_STATUSES) or not _nonempty(completion.get("summary")):
        result["reason"] = "worker completion row is malformed"
        return result
    if status == "failed":
        result.update(disposition="FAILED", reason=completion["summary"])
        return result
    if status == "blocked":
        result.update(disposition="BLOCKED", reason=completion["summary"])
        return result
    for disposition in ("FAILED", "BLOCKED"):
        for detail_disposition, detail_reason in detail_outcomes:
            if detail_disposition == disposition:
                result.update(disposition=disposition, reason=detail_reason)
                return result

    if flow_assessment is not None:
        flow_outcome = flow_assessment["assessment"]
        if flow_outcome == "FAILED":
            result.update(disposition="FAILED", reason=flow_assessment["reason"])
            return result
        if flow_outcome == "BLOCKED":
            result.update(disposition="BLOCKED", reason=flow_assessment["reason"])
            return result
        if flow_outcome in {"INCOMPLETE", "INVALID"}:
            result["reason"] = flow_assessment["reason"]
            return result
        if flow_outcome == "AWAITING_QA":
            if global_report_invalid:
                result["reason"] = "report/evidence structure or identity is invalid"
                return result
            if observation is None or observation.get("verification") != "targeted_state":
                result["reason"] = "Flow awaiting QA lacks targeted current-state evidence"
                return result
            if observation.get("result") == "unavailable" or not isinstance(
                observation.get("actual_state"), dict
            ):
                result["reason"] = "Flow awaiting QA current-state evidence is unavailable"
                return result
            attribution = observation.get("attribution")
            if attribution == "applied" and not _nonempty(observation.get("change_source")):
                result["reason"] = "Flow awaiting QA lacks current change provenance"
                return result
            if attribution == "already_satisfied" and not _nonempty(
                observation.get("baseline_source")
            ):
                result["reason"] = "Flow awaiting QA lacks baseline provenance"
                return result
            if attribution not in {"applied", "already_satisfied"}:
                result["reason"] = "Flow awaiting QA lacks applied or baseline attribution"
                return result
            result.update(disposition="AWAITING_QA", reason=flow_assessment["reason"])
            return result

    evidence_problem = _verification_problem(item, observation)
    if item["kind"] == "seed":
        report_problem = _seed_report_problem(item, seed_report)
        if report_problem is not None:
            result["reason"] = report_problem
            return result
    if evidence_problem is not None:
        result["disposition"], result["reason"] = evidence_problem
        return result
    if global_report_invalid:
        result["reason"] = "report/evidence structure or identity is invalid"
        return result
    runtime_passed = (
        runtime_assessment is not None and runtime_assessment["assessment"] == "PASS"
    )
    runtime_unavailable = (
        runtime_assessment is not None
        and runtime_assessment["assessment"] == "UNAVAILABLE"
    )
    awaiting_reasons = [
        reason for disposition, reason in detail_outcomes if disposition == "AWAITING_QA"
    ]
    if runtime_passed:
        awaiting_reasons = [
            reason for reason in awaiting_reasons if not reason.startswith("[agent runtime]")
        ]
    detail_awaiting = awaiting_reasons[0] if awaiting_reasons else None
    if (status == "awaiting_qa" and not runtime_passed) or detail_awaiting is not None or runtime_unavailable:
        attribution = observation.get("attribution") if observation else None
        if attribution == "applied" and not _nonempty(observation.get("change_source")):
            result["reason"] = "awaiting_qa applied state lacks current change provenance"
            return result
        if attribution == "already_satisfied" and not _nonempty(
            observation.get("baseline_source")
        ):
            result["reason"] = "awaiting_qa pre-existing state lacks baseline provenance"
            return result
        if attribution not in {"applied", "already_satisfied"}:
            result["reason"] = "awaiting_qa lacks applied or pre-existing state provenance"
            return result
        result.update(
            disposition="AWAITING_QA",
            reason=(
                runtime_assessment["reason"]
                if runtime_unavailable
                else detail_awaiting or completion["summary"]
            ),
        )
        return result

    attribution = observation.get("attribution") if observation else None
    effective_status = attribution if runtime_passed and status == "awaiting_qa" else status
    if effective_status != attribution:
        result["reason"] = "worker status and independent evidence attribution contradict"
        return result
    if effective_status == "applied" and not _nonempty(observation.get("change_source")):
        result["reason"] = "applied lacks current deployment or before/after change provenance"
        return result
    if effective_status == "already_satisfied" and not _nonempty(observation.get("baseline_source")):
        result["reason"] = "already_satisfied lacks pre-dispatch baseline provenance"
        return result
    result.update(
        disposition="VERIFIED",
        execution=effective_status,
        reason=completion["summary"],
    )
    return result


def reconcile(
    ledger: Any,
    worker: Any,
    evidence: Any,
    actual_spec_bytes: bytes,
) -> dict[str, Any]:
    """Reconcile one phase. Invalid ledgers/spec anchors reject the assessment."""
    try:
        ledger, items = _validate_ledger(ledger, actual_spec_bytes)
    except ContractError as exc:
        return {
            "schema_version": 1,
            "valid": False,
            "outcome": "INVALID_INPUT",
            "validation_errors": [str(exc)],
            "items": [],
            "counts": {},
        }

    errors: list[str] = []
    expected_ids = set(items)
    identity = {key: ledger[key] for key in ("schema_version", "build_id", "spec_sha256", "phase")}
    spec_text = actual_spec_bytes.decode("utf-8")
    skips = _authorized_skips(ledger, expected_ids, spec_text, errors)
    agent_actions = {
        item_id: item["acceptance"]["agent_runtime"]["hero_action"]
        for item_id, item in items.items()
        if "agent_runtime" in item["acceptance"]
    }
    completion, data_seeded, detail_outcomes, reported_skips, deployed_rows = _worker_rows(
        worker, identity, expected_ids, skips, agent_actions, errors
    )
    observations = _evidence_rows(
        evidence, identity, expected_ids, ledger_sha256(ledger), errors
    )
    agent_item_ids = set(agent_actions)
    contexts = _agent_context_rows(evidence, agent_item_ids, errors)
    canonical_gate_bytes = AGENTFORCE_GATE_PATH.read_bytes() if agent_item_ids else b""
    runtime_assessments = _agent_runtime_assessments(
        items, observations, contexts, canonical_gate_bytes, errors
    )
    flow_assessments = _flow_validation_assessments(
        items,
        deployed_rows,
        observations,
        worker is not None,
        skips,
        reported_skips,
        errors,
    )
    global_report_invalid = bool(errors)

    results = []
    for item_id, item in items.items():
        results.append(
            _item_result(
                item,
                completion.get(item_id),
                observations.get(item_id),
                data_seeded.get(item_id),
                skips.get(item_id),
                detail_outcomes.get(item_id, []),
                worker is not None,
                item_id in reported_skips,
                global_report_invalid,
                runtime_assessments.get(item_id),
                flow_assessments.get(item_id),
            )
        )

    counts = {
        disposition: sum(row["disposition"] == disposition for row in results)
        for disposition in (
            "VERIFIED",
            "SKIPPED",
            "AWAITING_QA",
            "FAILED",
            "BLOCKED",
            "INCOMPLETE",
        )
    }
    if counts["VERIFIED"] == len(results):
        outcome = "FULLY_VERIFIED"
    elif counts["FAILED"] or counts["BLOCKED"] or counts["INCOMPLETE"]:
        outcome = "UNRESOLVED"
    else:
        outcome = "FINISHED_WITH_EXCEPTIONS"
    output = {
        "schema_version": 1,
        "valid": not errors,
        "build_id": ledger["build_id"],
        "spec_sha256": ledger["spec_sha256"],
        "ledger_sha256": ledger_sha256(ledger),
        "phase": ledger["phase"],
        "outcome": outcome,
        "validation_errors": errors,
        "items": results,
        "counts": counts,
    }
    if agent_item_ids:
        output["agentforce_gate_sha256"] = hashlib.sha256(canonical_gate_bytes).hexdigest()
    return output


def _read_bytes(path_text: str, label: str) -> bytes:
    path = Path(path_text).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ContractError(f"{label} must be a regular file")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ContractError(f"{label} exceeds {MAX_FILE_BYTES} bytes")
    return path.read_bytes()


def _read_json(path_text: str, label: str) -> Any:
    raw = _read_bytes(path_text, label)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"{label} is not valid UTF-8 JSON") from exc
    _bounded_json(value, label)
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, help="approved spec Markdown")
    parser.add_argument("--ledger", required=True, help="frozen expected-work ledger JSON")
    parser.add_argument("--worker-result", help="worker output JSON; omit if no worker ran")
    parser.add_argument("--evidence", help="orchestrator observation JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        spec_bytes = _read_bytes(args.spec, "spec")
        ledger = _read_json(args.ledger, "ledger")
        worker = _read_json(args.worker_result, "worker result") if args.worker_result else None
        evidence = _read_json(args.evidence, "evidence") if args.evidence else None
        result = reconcile(ledger, worker, evidence, spec_bytes)
    except (ContractError, OSError) as exc:
        result = {
            "schema_version": 1,
            "valid": False,
            "outcome": "INVALID_INPUT",
            "validation_errors": [str(exc)],
            "items": [],
            "counts": {},
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["outcome"] != "INVALID_INPUT" else 2


if __name__ == "__main__":
    sys.exit(main())
