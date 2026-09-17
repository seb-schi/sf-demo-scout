#!/usr/bin/env python3
"""Pure assessment of normalized Scout Agentforce current-test evidence.

The orchestrator creates these normalized objects from saved tool results. This
module does not call Salesforce and does not parse raw traces or event-log schemas.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any


SHA256 = re.compile(r"^[0-9a-f]{64}$")
BEHAVIORS = {"mutating", "read_only"}
SOURCE_KINDS = {"agent_script", "compiled_planner", "unknown"}
TEST_MODES = {"session_turn", "job_case"}
CHANNELS = {"live_preview", "event_log", "test_job"}
INVOCATIONS = {"succeeded", "failed", "not_invoked", "unavailable"}
STRUCTURE_RESULTS = {"pass", "fail", "unavailable"}
INVOCATION_EVIDENCE = {
    "live_trace",
    "complete_trace",
    "expected_action_declaration",
    "transcript_only",
    "authoring_preview",
    "test_metrics",
}


class EvidenceError(ValueError):
    """The normalized contract is malformed."""


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _enum(value: Any, choices: set[str], label: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise EvidenceError(f"{label} is unsupported")
    return value


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be an object")
    return value


def _required_text(value: Any, label: str) -> str:
    if not _nonempty(value):
        raise EvidenceError(f"{label} must be nonempty")
    return value


def _strict_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _strict_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _strict_equal(a, b) for a, b in zip(left, right)
        )
    return left == right


def _result(assessment: str, reason: str, *, valid: bool = True) -> dict[str, Any]:
    return {"valid": valid, "assessment": assessment, "reason": reason}


def validate_expected(value: Any) -> dict[str, Any]:
    expected = _object(value, "agent_runtime acceptance")
    _required_text(expected.get("agent_api_name"), "acceptance.agent_api_name")
    _required_text(expected.get("hero_action"), "acceptance.hero_action")
    behavior = _enum(expected.get("behavior"), BEHAVIORS, "acceptance.behavior")
    _enum(expected.get("source_kind"), SOURCE_KINDS, "acceptance.source_kind")
    criteria = _object(expected.get("criteria"), "acceptance.criteria")
    if behavior == "mutating":
        for key in ("target", "before", "after"):
            if not isinstance(criteria.get(key), dict) or not criteria[key]:
                raise EvidenceError(f"acceptance.criteria.{key} must be a nonempty object")
        if _strict_equal(criteria["before"], criteria["after"]):
            raise EvidenceError("mutating acceptance needs a discriminating before/after state")
    else:
        if not isinstance(criteria.get("output"), dict) or not criteria["output"]:
            raise EvidenceError("read-only acceptance.criteria.output must be nonempty")
        if criteria.get("side_effect") != "not_applicable":
            raise EvidenceError("read-only acceptance must mark side_effect not_applicable")
    return expected


def _test_identity(test: dict[str, Any], label: str) -> dict[str, str]:
    attempt_id = _required_text(test.get("attempt_id"), f"{label}.attempt_id")
    mode = _enum(test.get("mode"), TEST_MODES, f"{label}.mode")
    identity = {"attempt_id": attempt_id, "mode": mode}
    keys = ("session_id", "turn_id") if mode == "session_turn" else ("job_id", "case_id")
    for key in keys:
        identity[key] = _required_text(test.get(key), f"{label}.{key}")
    return identity


def _validate_context(value: Any) -> tuple[dict[str, Any], dict[str, str]]:
    context = _object(value, "agent context")
    for key in ("item_id", "agent_api_name", "deployed_version_id", "deployment_source"):
        _required_text(context.get(key), f"agent_context.{key}")
    _enum(context.get("source_kind"), SOURCE_KINDS, "agent_context.source_kind")
    digest = context.get("gate_sha256")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise EvidenceError("agent_context.gate_sha256 is malformed")
    test = _object(context.get("test"), "agent_context.test")
    identity = _test_identity(test, "agent_context.test")
    _required_text(test.get("identity_source"), "agent_context.test.identity_source")
    history = test.get("history")
    if not isinstance(history, list):
        raise EvidenceError("agent_context.test.history must be an array")
    seen: set[str] = set()
    for index, row_value in enumerate(history):
        row = _object(row_value, f"agent_context.test.history[{index}]")
        attempt = _required_text(row.get("attempt_id"), "history.attempt_id")
        if attempt == identity["attempt_id"] or attempt in seen:
            raise EvidenceError("agent_context.test.history has duplicate/current attempt")
        seen.add(attempt)
        _enum(row.get("outcome"), {"passed", "failed", "unavailable"}, "history.outcome")
        _required_text(row.get("source"), "history.source")
    supersedes = test.get("supersedes_attempt_id")
    if supersedes is not None:
        _required_text(supersedes, "agent_context.test.supersedes_attempt_id")
        if supersedes not in seen:
            raise EvidenceError("superseded attempt is not preserved in history")
        _required_text(test.get("fix_source"), "agent_context.test.fix_source")
    return context, identity


def _parse_utc(value: Any, label: str) -> datetime:
    text = _required_text(value, label)
    if not text.endswith("Z"):
        raise EvidenceError(f"{label} must be an ISO-8601 UTC value")
    try:
        return datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise EvidenceError(f"{label} must be an ISO-8601 UTC value") from exc


def _event_log_eligible(runtime: dict[str, Any]) -> bool:
    retrieval = runtime.get("retrieval")
    if not isinstance(retrieval, dict):
        return False
    if not _nonempty(retrieval.get("describe_source")):
        return False
    if not _nonempty(retrieval.get("session_mapping_source")):
        return False
    if retrieval.get("correlation") != "verified":
        return False
    field_map = retrieval.get("field_map")
    if not isinstance(field_map, dict) or set(field_map) != {
        "session",
        "turn",
        "version",
        "timestamp",
    }:
        return False
    if not all(_nonempty(value) for value in field_map.values()):
        return False
    try:
        lower = _parse_utc(retrieval.get("lower_inclusive"), "retrieval.lower_inclusive")
        upper = _parse_utc(retrieval.get("upper_exclusive"), "retrieval.upper_exclusive")
        event = _parse_utc(retrieval.get("event_timestamp"), "retrieval.event_timestamp")
    except EvidenceError:
        return False
    return lower < upper and lower <= event < upper


def _structure_assessment(
    expected: dict[str, Any], context: dict[str, Any], runtime: dict[str, Any]
) -> dict[str, Any] | None:
    intended = expected["source_kind"]
    actual = context["source_kind"]
    if intended != actual:
        return _result("UNAVAILABLE", "deployed source kind does not match ledger acceptance")
    structure = _object(runtime.get("structure"), "agent_runtime.structure")
    method = structure.get("method")
    outcome = _enum(structure.get("result"), STRUCTURE_RESULTS, "structure.result")
    _required_text(structure.get("source"), "structure.source")
    if actual == "unknown":
        return _result("UNAVAILABLE", "deployed source kind is unknown")
    wanted_method = (
        "agent_script_validation" if actual == "agent_script" else "compiled_schema_join"
    )
    if method != wanted_method:
        return _result("UNAVAILABLE", "structural evidence method does not match source kind")
    if outcome == "unavailable":
        return _result("UNAVAILABLE", "structural validation evidence is unavailable")
    if outcome == "fail":
        return _result(
            "BLOCKED",
            "compiled action schemas are missing" if actual == "compiled_planner" else "authoring validation failed",
        )
    return None


def assess(
    expected_value: Any,
    context_value: Any,
    runtime_value: Any,
    canonical_gate_bytes: bytes,
) -> dict[str, Any]:
    """Assess one ledger-scoped Agentforce runtime obligation."""
    try:
        if not isinstance(canonical_gate_bytes, bytes):
            raise EvidenceError("canonical gate content must be bytes")
        expected = validate_expected(expected_value)
        context, selected_identity = _validate_context(context_value)
        runtime = _object(runtime_value, "agent runtime observation")
        for key in ("agent_api_name", "deployed_version_id"):
            _required_text(runtime.get(key), f"agent_runtime.{key}")
        digest = runtime.get("gate_sha256")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise EvidenceError("agent_runtime.gate_sha256 is malformed")
        runtime_identity = _test_identity(
            _object(runtime.get("test_identity"), "agent_runtime.test_identity"),
            "agent_runtime.test_identity",
        )
        channel = _enum(runtime.get("evidence_channel"), CHANNELS, "evidence_channel")
        invocation = _object(runtime.get("invocation"), "agent_runtime.invocation")
        invocation_status = _enum(
            invocation.get("status"), INVOCATIONS, "agent_runtime.invocation.status"
        )
        evidence_kind = _enum(
            invocation.get("evidence_kind"),
            INVOCATION_EVIDENCE,
            "agent_runtime.invocation.evidence_kind",
        )
        if type(invocation.get("live_actions")) is not bool:
            raise EvidenceError("agent_runtime.invocation.live_actions must be boolean")
        if type(invocation.get("simulated")) is not bool:
            raise EvidenceError("agent_runtime.invocation.simulated must be boolean")
        _required_text(invocation.get("source"), "agent_runtime.invocation.source")
        canonical_digest = hashlib.sha256(canonical_gate_bytes).hexdigest()
        if context["gate_sha256"] != canonical_digest or digest != canonical_digest:
            return _result("UNAVAILABLE", "evidence uses a stale validation-gate digest")
        if context["agent_api_name"] != expected["agent_api_name"]:
            return _result("UNAVAILABLE", "deployed agent identity differs from ledger acceptance")
        if runtime["agent_api_name"] != context["agent_api_name"]:
            return _result("UNAVAILABLE", "runtime agent identity is not the deployed agent")
        if runtime["deployed_version_id"] != context["deployed_version_id"]:
            return _result("UNAVAILABLE", "runtime evidence is for a different deployed version")
        if not _strict_equal(runtime_identity, selected_identity):
            return _result("UNAVAILABLE", "runtime evidence is not the selected current test")

        structure_problem = _structure_assessment(expected, context, runtime)
        if structure_problem is not None:
            return structure_problem
        if channel == "event_log" and not _event_log_eligible(runtime):
            return _result("UNAVAILABLE", "event-log evidence is uncorrelatable or outside its fence")
        if channel == "test_job" and selected_identity["mode"] != "job_case":
            return _result("UNAVAILABLE", "test-job evidence lacks the selected job/case identity")
        if invocation.get("simulated") or not invocation.get("live_actions"):
            return _result("UNAVAILABLE", "simulated or non-live invocation cannot validate deployment")
        if evidence_kind not in {"live_trace", "complete_trace"}:
            return _result(
                "UNAVAILABLE",
                "expected declarations, transcripts, metrics, and prepublish previews are not live invocation evidence",
            )
        if invocation_status == "unavailable":
            return _result("UNAVAILABLE", "current invocation evidence is unavailable")
        if invocation_status == "not_invoked" and evidence_kind != "complete_trace":
            return _result(
                "UNAVAILABLE", "missing invocation is not proven by a complete current trace"
            )
        if invocation_status == "not_invoked":
            return _result("FAIL", "current test proves the hero action failed or was not invoked")
        _required_text(invocation.get("action"), "agent_runtime.invocation.action")
        if invocation_status == "failed":
            return _result("FAIL", "current test proves the hero action failed or was not invoked")
        if invocation["action"] != expected["hero_action"]:
            return _result("FAIL", "current invocation is not the required hero action")

        behavior = _object(runtime.get("behavior"), "agent_runtime.behavior")
        _required_text(behavior.get("source"), "agent_runtime.behavior.source")

        history = context["test"]["history"]
        failures = [row for row in history if row["outcome"] == "failed"]
        if failures:
            latest_failure = failures[-1]["attempt_id"]
            if (
                context["test"].get("supersedes_attempt_id") != latest_failure
                or not _nonempty(context["test"].get("fix_source"))
            ):
                return _result(
                    "UNAVAILABLE",
                    "passing retest does not explicitly supersede the preserved failed attempt",
                )

        criteria = expected["criteria"]
        if expected["behavior"] == "mutating":
            before = behavior.get("before")
            if before is None:
                return _result("UNAVAILABLE", "mutating evidence lacks a discriminating pre-state")
            if _strict_equal(before, criteria["after"]):
                return _result(
                    "UNAVAILABLE", "desired state preexisted the turn without a discriminating sentinel"
                )
            if not _strict_equal(behavior.get("target"), criteria["target"]):
                return _result("FAIL", "current invocation changed or inspected the wrong target")
            if not _strict_equal(before, criteria["before"]):
                return _result("FAIL", "current test pre-state does not match the approved sentinel")
            if _strict_equal(before, behavior.get("after")):
                return _result("FAIL", "successful invocation produced no target-state delta")
            if not _strict_equal(behavior.get("after"), criteria["after"]):
                return _result("FAIL", "current test did not produce the requested target state")
        else:
            if behavior.get("side_effect") != "not_applicable":
                return _result("FAIL", "read-only evidence must mark side effects not applicable")
            if not _strict_equal(behavior.get("output"), criteria["output"]):
                return _result("FAIL", "current read-only output does not satisfy the spec assertion")
        return _result("PASS", "current deployed-version test satisfies this ledger obligation")
    except EvidenceError as exc:
        return _result("INVALID", str(exc), valid=False)
