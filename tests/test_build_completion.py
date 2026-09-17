import hashlib
import importlib.util
import json
import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build-completion.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_completion", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CompletionReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.spec_bytes = (
            b"# Approved demo spec\n"
            b"Add Risk__c with default Low\n"
            b"CREATE 2 EmailMessage rows for Case 500xx\n"
            b"UPDATE Case 500xx with EU regulatory values\n"
            b"UI-only obligation excluded from this build\n"
            b"Approved exclusion: omit Risk__c from this run\n"
            b"Calibration: quota = 70-80% of pipeline - reference query: SELECT SUM(Amount) FROM Opportunity\n"
            b"Agent Demo_Agent hero action Flag_Case\n"
        )
        self.digest = hashlib.sha256(self.spec_bytes).hexdigest()
        self.identity = {
            "schema_version": 1,
            "build_id": "build-20260917-001",
            "spec_sha256": self.digest,
            "phase": 1,
        }
        self.item = {
            "id": "p1.field.case-risk",
            "kind": "change",
            "phase": 1,
            "source": {
                "location": "Objects & Fields / Case",
                "quote": "Add Risk__c with default Low",
            },
            "acceptance": {
                "description": "Risk__c default is Low",
                "expected_state": {"defaultValue": "Low"},
            },
        }

    def ledger(self, item=None, authorized_skips=None):
        return {
            **self.identity,
            "items": [item or self.item],
            "authorized_skips": authorized_skips or [],
        }

    def worker(self, completion=None, **extra):
        payload = {
            **self.identity,
            "completion": completion
            if completion is not None
            else [
                {
                    "item_id": self.item["id"],
                    "status": "applied",
                    "summary": "Field deployed with the requested default.",
                }
            ],
            "deployed": [],
            "skipped": [],
            "data_seeded": [],
            "permission_set": {
                "ledger_item_id": None,
                "api_name": "",
                "assigned_to": "",
                "status": "NOT_APPLICABLE",
            },
            "script_deliverables": [],
            "discovery_notes": [],
            "docs_consulted": [],
            "issues": [],
        }
        payload.update(extra)
        return payload

    def evidence(self, observations=None, **identity_changes):
        identity = {**self.identity, **identity_changes}
        return {
            **identity,
            "ledger_sha256": self.module.ledger_sha256(self.ledger()),
            "orchestrator_provenance": "orchestrator run log / saved probe index",
            "observations": observations
            if observations is not None
            else [
                {
                    "item_id": self.item["id"],
                    "verification": "targeted_state",
                    "result": "match",
                    "attribution": "applied",
                    "change_source": "current deployment receipt 16",
                    "source": "saved retrieve_metadata result 17",
                    "details": "Risk__c defaultValue is Low",
                    "actual_state": {"defaultValue": "Low"},
                }
            ],
        }

    def reconcile(self, ledger=None, worker=None, evidence=None):
        return self.module.reconcile(
            ledger or self.ledger(),
            self.worker() if worker is None else worker,
            self.evidence() if evidence is None else evidence,
            self.spec_bytes,
        )

    def result_for(self, result, item_id=None):
        wanted = item_id or self.item["id"]
        return next(row for row in result["items"] if row["item_id"] == wanted)

    def test_targeted_current_evidence_verifies_applied_item(self):
        result = self.reconcile()

        self.assertEqual("FULLY_VERIFIED", result["outcome"])
        self.assertEqual("VERIFIED", self.result_for(result)["disposition"])
        self.assertEqual("applied", self.result_for(result)["execution"])
        self.assertFalse(self.result_for(result)["automatic_retry"])

    def test_missing_or_empty_report_stays_incomplete(self):
        for worker in (None, {}):
            with self.subTest(worker=worker):
                result = self.module.reconcile(
                    self.ledger(), worker, self.evidence(), self.spec_bytes
                )
                self.assertEqual("UNRESOLVED", result["outcome"])
                self.assertEqual("INCOMPLETE", self.result_for(result)["disposition"])

    def test_non_object_worker_or_evidence_fails_closed_without_exception(self):
        for worker, evidence in (([], self.evidence()), (self.worker(), [])):
            with self.subTest(worker=worker, evidence=evidence):
                result = self.module.reconcile(
                    self.ledger(), worker, evidence, self.spec_bytes
                )
                self.assertEqual("UNRESOLVED", result["outcome"])
                self.assertEqual("INCOMPLETE", self.result_for(result)["disposition"])
                self.assertFalse(result["valid"])

    def test_missing_completion_stays_incomplete_even_when_evidence_matches(self):
        worker = self.worker()
        del worker["completion"]

        result = self.reconcile(worker=worker)

        self.assertEqual("INCOMPLETE", self.result_for(result)["disposition"])
        self.assertTrue(any("completion" in error for error in result["validation_errors"]))

    def test_phase_required_detail_keys_and_types_are_enforced(self):
        for key in (
            "deployed",
            "skipped",
            "permission_set",
            "data_seeded",
            "script_deliverables",
            "discovery_notes",
            "docs_consulted",
            "issues",
        ):
            with self.subTest(missing=key):
                worker = self.worker()
                del worker[key]
                result = self.reconcile(worker=worker)
                self.assertEqual("INCOMPLETE", self.result_for(result)["disposition"])
                self.assertFalse(result["valid"])
        worker = self.worker(issues={})
        result = self.reconcile(worker=worker)
        self.assertEqual("INCOMPLETE", self.result_for(result)["disposition"])
        self.assertTrue(any("worker result.issues" in error for error in result["validation_errors"]))

    def test_common_only_report_cannot_verify_non_seed_item(self):
        worker = {**self.identity, "completion": self.worker()["completion"]}

        result = self.reconcile(worker=worker)

        self.assertEqual("INCOMPLETE", self.result_for(result)["disposition"])
        self.assertFalse(result["valid"])

    def test_identity_values_use_strict_json_types(self):
        ledger = copy.deepcopy(self.ledger())
        ledger["schema_version"] = True
        invalid = self.module.reconcile(ledger, self.worker(), self.evidence(), self.spec_bytes)
        self.assertEqual("INVALID_INPUT", invalid["outcome"])

        for key in ("schema_version", "phase"):
            with self.subTest(key=key):
                worker = self.worker()
                worker[key] = True
                result = self.reconcile(worker=worker)
                self.assertEqual("INCOMPLETE", self.result_for(result)["disposition"])
                self.assertFalse(result["valid"])

    def test_non_string_nested_enum_values_fail_closed_without_type_error(self):
        ledger = copy.deepcopy(self.ledger())
        ledger["items"][0]["kind"] = []
        invalid_kind = self.module.reconcile(
            ledger, self.worker(), self.evidence(), self.spec_bytes
        )
        self.assertEqual("INVALID_INPUT", invalid_kind["outcome"])

        seed = self.seed_item(operation=[])
        invalid_operation = self.module.reconcile(
            self.ledger(seed), None, None, self.spec_bytes
        )
        self.assertEqual("INVALID_INPUT", invalid_operation["outcome"])

        worker = self.worker()
        worker["completion"][0]["status"] = {}
        invalid_status = self.reconcile(worker=worker)
        self.assertEqual("INCOMPLETE", self.result_for(invalid_status)["disposition"])

        evidence = self.evidence()
        evidence["observations"][0]["verification"] = []
        invalid_verification = self.reconcile(evidence=evidence)
        self.assertEqual("INCOMPLETE", self.result_for(invalid_verification)["disposition"])

    def test_duplicate_and_unexpected_worker_ids_fail_closed(self):
        duplicate = {
            "item_id": self.item["id"],
            "status": "applied",
            "summary": "duplicate",
        }
        unexpected = {
            "item_id": "p1.unexpected",
            "status": "applied",
            "summary": "not in the ledger",
        }
        worker = self.worker(completion=self.worker()["completion"] + [duplicate, unexpected])

        result = self.reconcile(worker=worker)

        self.assertEqual("INCOMPLETE", self.result_for(result)["disposition"])
        self.assertTrue(any("duplicate" in error for error in result["validation_errors"]))
        self.assertTrue(any("unexpected" in error for error in result["validation_errors"]))

    def test_duplicate_and_unexpected_evidence_ids_fail_closed(self):
        base = self.evidence()["observations"][0]
        observations = [base, dict(base), {**base, "item_id": "p1.unexpected"}]

        result = self.reconcile(evidence=self.evidence(observations))

        self.assertEqual("INCOMPLETE", self.result_for(result)["disposition"])
        self.assertTrue(any("evidence" in error for error in result["validation_errors"]))

    def test_stale_build_or_spec_identity_never_verifies(self):
        stale_worker = self.worker()
        stale_worker["build_id"] = "older-build"
        stale_evidence = self.evidence(spec_sha256="0" * 64)

        result = self.reconcile(worker=stale_worker, evidence=stale_evidence)

        self.assertEqual("INCOMPLETE", self.result_for(result)["disposition"])
        self.assertTrue(any("build_id" in error for error in result["validation_errors"]))
        self.assertTrue(any("spec_sha256" in error for error in result["validation_errors"]))

    def test_actual_spec_digest_must_match_frozen_ledger(self):
        result = self.module.reconcile(
            self.ledger(), self.worker(), self.evidence(), b"different spec"
        )

        self.assertEqual("INVALID_INPUT", result["outcome"])
        self.assertEqual([], result["items"])

    def test_presence_or_receipt_is_diagnostic_only(self):
        for verification in ("presence", "deployment_receipt"):
            with self.subTest(verification=verification):
                observation = self.evidence()["observations"][0]
                observation["verification"] = verification
                result = self.reconcile(evidence=self.evidence([observation]))
                self.assertEqual("INCOMPLETE", self.result_for(result)["disposition"])

    def test_targeted_mismatch_is_failed_but_unavailable_is_incomplete(self):
        for observed_result, disposition in (
            ("mismatch", "FAILED"),
            ("unavailable", "INCOMPLETE"),
        ):
            with self.subTest(observed_result=observed_result):
                observation = self.evidence()["observations"][0]
                observation["result"] = observed_result
                result = self.reconcile(evidence=self.evidence([observation]))
                self.assertEqual(disposition, self.result_for(result)["disposition"])

    def test_non_seed_expected_state_is_required_and_compared_by_typed_value(self):
        empty = {**self.item, "acceptance": {}}
        invalid = self.module.reconcile(
            self.ledger(empty), self.worker(), self.evidence(), self.spec_bytes
        )
        self.assertEqual("INVALID_INPUT", invalid["outcome"])

        for actual in ({"defaultValue": "High"}, {"defaultValue": 1}, {}):
            with self.subTest(actual=actual):
                observation = self.evidence()["observations"][0]
                observation["actual_state"] = actual
                result = self.reconcile(evidence=self.evidence([observation]))
                self.assertEqual("FAILED", self.result_for(result)["disposition"])

    def test_preexisting_exact_state_can_verify_without_claiming_applied(self):
        completion = [
            {
                "item_id": self.item["id"],
                "status": "already_satisfied",
                "summary": "Exact state existed before this build.",
            }
        ]
        observation = self.evidence()["observations"][0]
        observation["attribution"] = "already_satisfied"
        observation["baseline_source"] = "saved pre-dispatch retrieve result 2"

        result = self.reconcile(
            worker=self.worker(completion=completion),
            evidence=self.evidence([observation]),
        )

        self.assertEqual("VERIFIED", self.result_for(result)["disposition"])
        self.assertEqual("already_satisfied", self.result_for(result)["execution"])

    def test_applied_requires_current_change_provenance_in_addition_to_readback(self):
        observation = self.evidence()["observations"][0]
        del observation["change_source"]

        result = self.reconcile(evidence=self.evidence([observation]))

        self.assertEqual("INCOMPLETE", self.result_for(result)["disposition"])
        self.assertIn("change provenance", self.result_for(result)["reason"])

    def test_already_satisfied_requires_pre_dispatch_baseline_provenance(self):
        completion = [
            {
                "item_id": self.item["id"],
                "status": "already_satisfied",
                "summary": "Exact state existed before this build.",
            }
        ]
        observation = self.evidence()["observations"][0]
        observation["attribution"] = "already_satisfied"

        result = self.reconcile(
            worker=self.worker(completion=completion),
            evidence=self.evidence([observation]),
        )

        self.assertEqual("INCOMPLETE", self.result_for(result)["disposition"])
        self.assertIn("baseline", self.result_for(result)["reason"])

    def test_attribution_contradiction_is_incomplete(self):
        observation = self.evidence()["observations"][0]
        observation["attribution"] = "already_satisfied"

        result = self.reconcile(evidence=self.evidence([observation]))

        self.assertEqual("INCOMPLETE", self.result_for(result)["disposition"])
        self.assertIn("attribution", self.result_for(result)["reason"])

    def test_failed_blocked_and_awaiting_qa_are_not_success(self):
        expected = {
            "failed": "FAILED",
            "blocked": "BLOCKED",
            "awaiting_qa": "AWAITING_QA",
        }
        for status, disposition in expected.items():
            with self.subTest(status=status):
                completion = [
                    {
                        "item_id": self.item["id"],
                        "status": status,
                        "summary": "Concrete current state.",
                    }
                ]
                result = self.reconcile(worker=self.worker(completion=completion))
                row = self.result_for(result)
                self.assertEqual(disposition, row["disposition"])
                self.assertNotEqual("FULLY_VERIFIED", result["outcome"])
                self.assertFalse(row["automatic_retry"])

    def test_only_independently_authorized_skip_is_accepted(self):
        authorized = [
            {
                "item_id": self.item["id"],
                "authorization_type": "explicit_spec_exclusion",
                "decision_source": "Approved spec / SE Manual Checklist line 8",
                "reason": "Approved spec explicitly excludes this item.",
                "source": {
                    "location": "Approved exclusions / Risk__c",
                    "quote": "Approved exclusion: omit Risk__c from this run",
                },
            }
        ]
        result = self.module.reconcile(
            self.ledger(authorized_skips=authorized), None, None, self.spec_bytes
        )

        row = self.result_for(result)
        self.assertEqual("SKIPPED", row["disposition"])
        self.assertEqual("FINISHED_WITH_EXCEPTIONS", result["outcome"])
        self.assertFalse(row["automatic_retry"])

        mirrored_worker = self.worker(
            completion=[],
            skipped=[
                {
                    "ledger_item_id": self.item["id"],
                    "type": "CustomField",
                    "api_name": "Case.Risk__c",
                    "reason": authorized[0]["reason"],
                }
            ],
        )
        mirrored = self.module.reconcile(
            self.ledger(authorized_skips=authorized), mirrored_worker, None, self.spec_bytes
        )
        self.assertEqual("SKIPPED", self.result_for(mirrored)["disposition"])

    def test_authorized_skip_cannot_mask_reported_failed_attempt(self):
        authorized = [
            {
                "item_id": self.item["id"],
                "authorization_type": "explicit_se_non_execution",
                "decision_source_type": "se_decision",
                "decision_source": "SE decision recorded before dispatch",
                "reason": "Do not make another attempt.",
            }
        ]
        completion = [
            {
                "item_id": self.item["id"],
                "status": "failed",
                "summary": "Attempt failed before the stop decision.",
            }
        ]

        result = self.module.reconcile(
            self.ledger(authorized_skips=authorized),
            self.worker(completion=completion),
            self.evidence(),
            self.spec_bytes,
        )

        self.assertEqual("FAILED", self.result_for(result)["disposition"])
        self.assertEqual("UNRESOLVED", result["outcome"])

        applied = [
            {
                "item_id": self.item["id"],
                "status": "applied",
                "summary": "Work ran despite the non-execution authorization.",
            }
        ]
        contradiction = self.module.reconcile(
            self.ledger(authorized_skips=authorized),
            self.worker(completion=applied),
            self.evidence(),
            self.spec_bytes,
        )
        self.assertEqual("INCOMPLETE", self.result_for(contradiction)["disposition"])
        self.assertIn("non-execution", self.result_for(contradiction)["reason"])

    def test_detail_failure_and_unauthorized_skipped_row_override_applied_completion(self):
        failed = self.worker(
            deployed=[
                {
                    "ledger_item_id": self.item["id"],
                    "type": "CustomField",
                    "api_name": "Case.Risk__c",
                    "status": "FAILED",
                    "error": "deploy failed",
                }
            ]
        )
        failed_result = self.reconcile(worker=failed)
        self.assertEqual("FAILED", self.result_for(failed_result)["disposition"])

        skipped = self.worker(
            skipped=[
                {
                    "ledger_item_id": self.item["id"],
                    "type": "CustomField",
                    "api_name": "Case.Risk__c",
                    "reason": "worker omitted it",
                }
            ]
        )
        skipped_result = self.reconcile(worker=skipped)
        self.assertEqual("INCOMPLETE", self.result_for(skipped_result)["disposition"])
        self.assertFalse(skipped_result["valid"])

    def test_failed_permission_detail_cannot_verify_item(self):
        worker = self.worker(
            permission_set={
                "ledger_item_id": self.item["id"],
                "api_name": "Demo_Access",
                "assigned_to": "user@example.com",
                "status": "FAILED",
            }
        )

        result = self.reconcile(worker=worker)

        self.assertEqual("FAILED", self.result_for(result)["disposition"])

    def test_same_item_may_have_distinct_successful_detail_paths(self):
        worker = self.worker(
            deployed=[
                {
                    "ledger_item_id": self.item["id"],
                    "type": "CustomField",
                    "api_name": "Case.Risk__c",
                    "status": "SUCCESS",
                }
            ],
            permission_set={
                "ledger_item_id": self.item["id"],
                "api_name": "Demo_Access",
                "assigned_to": "user@example.com",
                "status": "SUCCESS",
            },
        )

        result = self.reconcile(worker=worker)

        self.assertEqual("VERIFIED", self.result_for(result)["disposition"])

    def test_duplicate_or_unknown_detail_ids_fail_closed(self):
        row = {
            "ledger_item_id": self.item["id"],
            "type": "CustomField",
            "api_name": "Case.Risk__c",
            "status": "SUCCESS",
        }
        duplicate = self.reconcile(worker=self.worker(deployed=[row, dict(row)]))
        self.assertEqual("INCOMPLETE", self.result_for(duplicate)["disposition"])
        self.assertFalse(duplicate["valid"])

        unknown_row = {**row, "ledger_item_id": "p1.unknown"}
        unknown = self.reconcile(worker=self.worker(deployed=[unknown_row]))
        self.assertEqual("INCOMPLETE", self.result_for(unknown)["disposition"])
        self.assertFalse(unknown["valid"])

    def phase_context(self, phase):
        item = {
            **self.item,
            "id": f"p{phase}.artifact.demo",
            "phase": phase,
        }
        identity = {**self.identity, "phase": phase}
        ledger = {**identity, "items": [item], "authorized_skips": []}
        completion = [
            {
                "item_id": item["id"],
                "status": "applied",
                "summary": "Detailed artifact operation completed.",
            }
        ]
        evidence = {
            **identity,
            "ledger_sha256": self.module.ledger_sha256(ledger),
            "orchestrator_provenance": "saved phase probe index",
            "observations": [
                {
                    "item_id": item["id"],
                    "verification": "targeted_state",
                    "result": "match",
                    "attribution": "applied",
                    "change_source": "current phase deploy receipt",
                    "source": "saved targeted phase read-back",
                    "details": "Requested literal state matches.",
                    "actual_state": {"defaultValue": "Low"},
                }
            ],
        }
        return item, identity, ledger, completion, evidence

    def agent_phase_context(self, suffix="flag-case"):
        gate_sha = hashlib.sha256(
            (ROOT / "prompts" / "building" / "agentforce-validation-gate.md").read_bytes()
        ).hexdigest()
        item = {
            "id": f"p3.agent.{suffix}",
            "kind": "artifact",
            "phase": 3,
            "source": {
                "location": "Agentforce / hero action",
                "quote": "Agent Demo_Agent hero action Flag_Case",
            },
            "acceptance": {
                "description": "Published agent is active and the hero action changes the sentinel",
                "expected_state": {"active": True},
                "agent_runtime": {
                    "agent_api_name": "Demo_Agent",
                    "hero_action": "Flag_Case",
                    "behavior": "mutating",
                    "source_kind": "agent_script",
                    "criteria": {
                        "target": {"Case.Id": "500xx"},
                        "before": {"Case.Flagged__c": False},
                        "after": {"Case.Flagged__c": True},
                    },
                },
            },
        }
        identity = {**self.identity, "phase": 3}
        ledger = {**identity, "items": [item], "authorized_skips": []}
        context = {
            "item_id": item["id"],
            "agent_api_name": "Demo_Agent",
            "deployed_version_id": "0Xx-version-7",
            "deployment_source": "saved independent deploy/version read-back 3",
            "source_kind": "agent_script",
            "gate_sha256": gate_sha,
            "test": {
                "attempt_id": "attempt-1",
                "mode": "session_turn",
                "session_id": "session-current",
                "turn_id": "turn-current",
                "identity_source": "saved current test start/turn result 4",
                "history": [],
            },
        }
        runtime = {
            "agent_api_name": "Demo_Agent",
            "deployed_version_id": "0Xx-version-7",
            "gate_sha256": gate_sha,
            "test_identity": {
                "attempt_id": "attempt-1",
                "mode": "session_turn",
                "session_id": "session-current",
                "turn_id": "turn-current",
            },
            "evidence_channel": "live_preview",
            "invocation": {
                "status": "succeeded",
                "action": "Flag_Case",
                "live_actions": True,
                "simulated": False,
                "evidence_kind": "live_trace",
                "source": "saved current preview trace 5",
            },
            "behavior": {
                "target": {"Case.Id": "500xx"},
                "before": {"Case.Flagged__c": False},
                "after": {"Case.Flagged__c": True},
                "source": "saved before/after SOQL 6",
            },
            "structure": {
                "method": "agent_script_validation",
                "result": "pass",
                "source": "saved authoring validation 2",
            },
        }
        observation = {
            "item_id": item["id"],
            "verification": "targeted_state",
            "result": "match",
            "attribution": "applied",
            "change_source": "current publish receipt 2",
            "source": "saved agent state read-back 3",
            "details": "Agent is active at the independently recorded version.",
            "actual_state": {"active": True},
            "agent_runtime": runtime,
        }
        evidence = {
            **identity,
            "ledger_sha256": self.module.ledger_sha256(ledger),
            "orchestrator_provenance": "saved phase-3 probe index",
            "agent_contexts": [context],
            "observations": [observation],
        }
        worker = {
            **identity,
            "completion": [
                {
                    "item_id": item["id"],
                    "status": "applied",
                    "summary": "Agent published and activated.",
                }
            ],
            "deployed": {
                "agent": {
                    "ledger_item_id": item["id"],
                    "api_name": "Demo_Agent",
                    "version": 7,
                    "status": "Active",
                    "recovery": {
                        "status": "not_needed",
                        "artifact": None,
                        "bundle_path": None,
                        "original_path": None,
                        "error": None,
                    },
                },
                "backing_actions": [],
                "agent_user": {"ledger_item_id": None, "username": "", "created_by_cli": False},
                "standard_permset_assignment": {
                    "ledger_item_id": None,
                    "name": None,
                    "assigned_to": None,
                    "status": "NOT_FOUND",
                },
            },
            "smoke_test": {
                "ledger_item_id": item["id"],
                "ran": True,
                "action_invocation_confirmed": False,
                "utterances": [],
            },
            "actions_unverified_in_preview": [
                {
                    "ledger_item_id": item["id"],
                    "action": "Flag_Case",
                    "reason": "worker could not confirm it",
                }
            ],
            "skipped": [],
            "rollback_commands": [],
            "discovery_notes": [],
            "docs_consulted": [],
            "issues": [],
        }
        return item, ledger, worker, evidence

    def test_phase2_draft_or_unvalidated_detail_is_awaiting_qa(self):
        item, identity, ledger, completion, evidence = self.phase_context(2)
        worker = {
            **identity,
            "completion": completion,
            "deployed": [
                {
                    "ledger_item_id": item["id"],
                    "type": "Flow",
                    "api_name": "Demo_Flow",
                    "status": "SUCCESS",
                    "flow_status": "Draft",
                    "validation_status": "AWAITING_QA",
                }
            ],
            "skipped": [],
            "rollback_commands": [],
            "discovery_notes": [],
            "docs_consulted": [],
            "issues": [],
        }

        result = self.module.reconcile(ledger, worker, evidence, self.spec_bytes)

        self.assertEqual("AWAITING_QA", self.result_for(result, item["id"])["disposition"])
        self.assertEqual("FINISHED_WITH_EXCEPTIONS", result["outcome"])

    def test_phase3_failed_recovery_is_blocked(self):
        item, identity, ledger, completion, evidence = self.phase_context(3)
        worker = {
            **identity,
            "completion": completion,
            "deployed": {
                "agent": {
                    "ledger_item_id": item["id"],
                    "api_name": "Demo_Agent",
                    "version": 0,
                    "status": "NeedsUICommit",
                    "recovery": {
                        "status": "failed",
                        "artifact": None,
                        "bundle_path": None,
                        "original_path": "/tmp/original",
                        "error": "preservation failed",
                    },
                },
                "backing_actions": [],
                "agent_user": {"ledger_item_id": None, "username": "", "created_by_cli": False},
                "standard_permset_assignment": {
                    "ledger_item_id": None,
                    "name": None,
                    "assigned_to": None,
                    "status": "NOT_FOUND",
                },
            },
            "smoke_test": {
                "ledger_item_id": item["id"],
                "ran": False,
                "action_invocation_confirmed": False,
                "utterances": [],
            },
            "actions_unverified_in_preview": [],
            "skipped": [],
            "rollback_commands": [],
            "discovery_notes": [],
            "docs_consulted": [],
            "issues": [],
        }

        result = self.module.reconcile(ledger, worker, evidence, self.spec_bytes)

        self.assertEqual("BLOCKED", self.result_for(result, item["id"])["disposition"])
        self.assertNotEqual("FULLY_VERIFIED", result["outcome"])

        worker["smoke_test"].pop("ledger_item_id")
        malformed = self.module.reconcile(ledger, worker, evidence, self.spec_bytes)
        self.assertEqual("BLOCKED", self.result_for(malformed, item["id"])["disposition"])
        self.assertFalse(malformed["valid"])
        self.assertNotEqual("FULLY_VERIFIED", malformed["outcome"])

    def test_failed_preedit_snapshot_cannot_be_cleared_by_current_runtime_pass(self):
        item, ledger, worker, evidence = self.agent_phase_context()
        worker["deployed"]["agent"]["preedit_snapshot"] = {
            "status": "failed", "artifact": None, "source": None,
            "paths": ["aiAuthoringBundles/Demo_Agent"], "error": "copy failed",
        }
        result = self.module.reconcile(ledger, worker, evidence, self.spec_bytes)
        row = self.result_for(result, item["id"])
        self.assertEqual("PASS", row["runtime_assessment"]["assessment"])
        self.assertEqual("BLOCKED", row["disposition"])
        self.assertEqual("UNRESOLVED", result["outcome"])

    def test_malformed_preedit_snapshot_is_not_verified(self):
        item, ledger, worker, evidence = self.agent_phase_context()
        for value in (None, {}, {"status": "verified"},
                      {"status": "not_needed", "artifact": "/tmp/stale", "source": None,
                       "paths": ["../stale"], "error": "old failure"}):
            with self.subTest(value=value):
                worker["deployed"]["agent"]["preedit_snapshot"] = value
                result = self.module.reconcile(ledger, worker, evidence, self.spec_bytes)
                self.assertFalse(result["valid"])
                self.assertNotEqual("VERIFIED", self.result_for(result, item["id"])["disposition"])

    def test_missing_preedit_parent_unavailable_observation_keeps_runtime_truth(self):
        """Models the parent gate; it does not prove a model performs the check."""
        item, ledger, worker, evidence = self.agent_phase_context()
        evidence["observations"][0]["result"] = "unavailable"
        evidence["observations"][0]["details"] = "Required pre-edit receipt absent from worker result."
        result = self.module.reconcile(ledger, worker, evidence, self.spec_bytes)
        row = self.result_for(result, item["id"])
        self.assertEqual("PASS", row["runtime_assessment"]["assessment"])
        self.assertEqual("INCOMPLETE", row["disposition"])
        self.assertEqual("UNRESOLVED", result["outcome"])

    def test_independent_runtime_pass_overrides_only_same_item_worker_smoke_summary(self):
        item, ledger, worker, evidence = self.agent_phase_context()

        result = self.module.reconcile(ledger, worker, evidence, self.spec_bytes)
        row = self.result_for(result, item["id"])

        self.assertEqual("VERIFIED", row["disposition"])
        self.assertEqual("PASS", row["runtime_assessment"]["assessment"])

    def test_independent_runtime_pass_resolves_same_item_worker_awaiting_qa(self):
        item, ledger, worker, evidence = self.agent_phase_context()
        worker["completion"][0].update(
            {
                "status": "awaiting_qa",
                "summary": "Worker preview could not confirm the hero action.",
            }
        )

        result = self.module.reconcile(ledger, worker, evidence, self.spec_bytes)
        row = self.result_for(result, item["id"])

        self.assertEqual("VERIFIED", row["disposition"])
        self.assertEqual("PASS", row["runtime_assessment"]["assessment"])

    def test_expected_runtime_failure_is_exposed_even_without_worker_report(self):
        item, ledger, _worker, evidence = self.agent_phase_context()
        evidence["observations"][0]["agent_runtime"]["invocation"].update(
            {"status": "not_invoked", "evidence_kind": "complete_trace"}
        )
        evidence["observations"][0]["agent_runtime"].pop("behavior")

        result = self.module.reconcile(ledger, None, evidence, self.spec_bytes)
        row = self.result_for(result, item["id"])

        self.assertEqual("FAILED", row["disposition"])
        self.assertEqual("FAIL", row["runtime_assessment"]["assessment"])

    def test_runtime_pass_is_exposed_but_missing_worker_stays_incomplete(self):
        item, ledger, _worker, evidence = self.agent_phase_context()

        result = self.module.reconcile(ledger, None, evidence, self.spec_bytes)
        row = self.result_for(result, item["id"])

        self.assertEqual("INCOMPLETE", row["disposition"])
        self.assertEqual("PASS", row["runtime_assessment"]["assessment"])
        self.assertEqual(evidence["agent_contexts"][0]["gate_sha256"], result["agentforce_gate_sha256"])

    def test_runtime_unavailable_keeps_deployed_item_awaiting_qa(self):
        item, ledger, worker, evidence = self.agent_phase_context()
        evidence["observations"][0]["agent_runtime"]["invocation"]["status"] = "unavailable"
        evidence["observations"][0]["agent_runtime"].pop("behavior")

        result = self.module.reconcile(ledger, worker, evidence, self.spec_bytes)
        row = self.result_for(result, item["id"])

        self.assertEqual("AWAITING_QA", row["disposition"])
        self.assertEqual("UNAVAILABLE", row["runtime_assessment"]["assessment"])

    def test_runtime_pass_does_not_clear_another_required_obligation(self):
        item, ledger, worker, evidence = self.agent_phase_context()
        other = copy.deepcopy(item)
        other["id"] = "p3.agent.guardrail"
        other["acceptance"]["agent_runtime"]["hero_action"] = "Guardrail refusal"
        ledger["items"].append(other)
        worker["completion"].append(
            {
                "item_id": other["id"],
                "status": "awaiting_qa",
                "summary": "Guardrail behavior still needs a current test.",
            }
        )
        worker["actions_unverified_in_preview"].append(
            {
                "ledger_item_id": other["id"],
                "action": "Guardrail refusal",
                "reason": "current independent test is still required",
            }
        )
        evidence["ledger_sha256"] = self.module.ledger_sha256(ledger)
        other_observation = copy.deepcopy(evidence["observations"][0])
        other_observation["item_id"] = other["id"]
        other_observation.pop("agent_runtime")
        evidence["observations"].append(other_observation)

        result = self.module.reconcile(ledger, worker, evidence, self.spec_bytes)

        self.assertEqual("VERIFIED", self.result_for(result, item["id"])["disposition"])
        self.assertEqual("AWAITING_QA", self.result_for(result, other["id"])["disposition"])

    def test_authorized_skip_cannot_hide_observed_runtime_failure(self):
        item, ledger, _worker, evidence = self.agent_phase_context()
        ledger["authorized_skips"] = [
            {
                "item_id": item["id"],
                "authorization_type": "explicit_se_non_execution",
                "decision_source": "saved SE decision 1",
                "decision_source_type": "se_decision",
                "reason": "SE declined this runtime test",
            }
        ]
        evidence["ledger_sha256"] = self.module.ledger_sha256(ledger)
        evidence["observations"][0]["attribution"] = "unknown"
        evidence["observations"][0]["agent_runtime"]["invocation"].update(
            {"status": "not_invoked", "evidence_kind": "complete_trace"}
        )
        evidence["observations"][0]["agent_runtime"].pop("behavior")

        result = self.module.reconcile(ledger, None, evidence, self.spec_bytes)

        self.assertEqual("FAILED", self.result_for(result, item["id"])["disposition"])

    def test_runtime_pass_cannot_clear_different_action_qa_on_same_item(self):
        item, ledger, worker, evidence = self.agent_phase_context()
        worker["actions_unverified_in_preview"][0]["action"] = "Different_Action"

        result = self.module.reconcile(ledger, worker, evidence, self.spec_bytes)

        self.assertFalse(result["valid"])
        self.assertNotEqual("FULLY_VERIFIED", result["outcome"])
        self.assertTrue(any("distinct ledger item" in error for error in result["validation_errors"]))

    def test_manual_handoff_remains_blocked_without_explicit_non_execution(self):
        manual = {
            "id": "p1.manual.ui",
            "kind": "manual",
            "phase": 1,
            "source": {
                "location": "SE Manual Checklist / item 1",
                "quote": "UI-only obligation excluded from this build",
            },
            "acceptance": {
                "description": "SE confirms the UI result",
                "expected_state": {"se_confirmed": True},
            },
        }
        bare_handoff = [
            {
                "item_id": manual["id"],
                "decision_source": "SE Manual Checklist / item 1",
                "reason": "Automation unavailable; SE must do it.",
            }
        ]

        result = self.module.reconcile(
            self.ledger(manual, bare_handoff), None, None, self.spec_bytes
        )

        self.assertEqual("BLOCKED", self.result_for(result, manual["id"])["disposition"])
        self.assertIn("manual", self.result_for(result, manual["id"])["reason"])

    def test_spec_exclusion_skip_requires_quote_anchored_in_actual_spec(self):
        skip = [
            {
                "item_id": self.item["id"],
                "authorization_type": "explicit_spec_exclusion",
                "decision_source": "claimed spec exclusion",
                "reason": "Do not execute.",
                "source": {
                    "location": "invented exclusion",
                    "quote": "this exclusion is not in the approved spec",
                },
            }
        ]

        result = self.module.reconcile(
            self.ledger(authorized_skips=skip), None, None, self.spec_bytes
        )

        self.assertEqual("INCOMPLETE", self.result_for(result)["disposition"])
        self.assertFalse(result["valid"])

    def test_awaiting_qa_requires_applied_or_baseline_provenance(self):
        completion = [
            {
                "item_id": self.item["id"],
                "status": "awaiting_qa",
                "summary": "Metadata matches; visual QA remains.",
            }
        ]
        observation = self.evidence()["observations"][0]
        observation["attribution"] = "unknown"
        observation.pop("change_source")

        incomplete = self.reconcile(
            worker=self.worker(completion=completion),
            evidence=self.evidence([observation]),
        )
        self.assertEqual("INCOMPLETE", self.result_for(incomplete)["disposition"])

        observation["attribution"] = "applied"
        observation["change_source"] = "current deployment receipt 18"
        awaiting = self.reconcile(
            worker=self.worker(completion=completion),
            evidence=self.evidence([observation]),
        )
        self.assertEqual("AWAITING_QA", self.result_for(awaiting)["disposition"])

    def test_worker_cannot_authorize_its_own_skip(self):
        completion = [
            {
                "item_id": self.item["id"],
                "status": "skipped",
                "summary": "Worker chose not to do it.",
            }
        ]

        result = self.reconcile(worker=self.worker(completion=completion))

        self.assertEqual("INCOMPLETE", self.result_for(result)["disposition"])
        self.assertTrue(any("status" in error for error in result["validation_errors"]))

    def seed_item(self, operation="CREATE", **acceptance_changes):
        acceptance = {
            "operation": operation,
            "object": "EmailMessage",
            "count": 2,
            "stable_keys": {"ParentId": "500xx", "Incoming": True},
            "required_values": {"Status": "3"},
        }
        acceptance.update(acceptance_changes)
        return {
            "id": "p1.seed.email",
            "kind": "seed",
            "phase": 1,
            "source": {
                "location": "Data Seeding / EmailMessage",
                "quote": "CREATE 2 EmailMessage rows for Case 500xx",
            },
            "acceptance": acceptance,
        }

    def seed_worker(self, item, records=2, status="SUCCESS", operation="CREATE"):
        return self.worker(
            completion=[
                {
                    "item_id": item["id"],
                    "status": "applied",
                    "summary": "Seed operation completed.",
                }
            ],
            data_seeded=[
                {
                    "ledger_item_id": item["id"],
                    "object": item["acceptance"]["object"],
                    "operation": operation,
                    "records": records,
                    "status": status,
                }
            ],
        )

    def seed_evidence(self, item, matched_count=2, **probe_changes):
        acceptance = item["acceptance"]
        probe = {
            "operation": acceptance["operation"],
            "object": acceptance["object"],
            "stable_keys": acceptance.get("stable_keys"),
            "required_values": acceptance.get("required_values", {}),
            "matched_count": matched_count,
            "values_match": True,
        }
        calibration = acceptance.get("calibration")
        if calibration is not None and calibration.get("resolution") != "blocked":
            probe["calibration_source"] = calibration["reference_source"]
        probe.update(probe_changes)
        evidence = self.evidence(
            [
                {
                    "item_id": item["id"],
                    "verification": "seed_probe",
                    "result": "match",
                    "attribution": "applied",
                    "change_source": "current seed execution result 21",
                    "source": "saved SOQL result 22",
                    "details": "Stable-key query and requested values checked.",
                    "seed_probe": probe,
                }
            ]
        )
        evidence["ledger_sha256"] = self.module.ledger_sha256(self.ledger(item))
        return evidence

    def test_create_seed_requires_positive_integer_count_and_known_operation(self):
        for item in (
            self.seed_item(count=0),
            self.seed_item(count="2"),
            self.seed_item(operation="UPSERT"),
        ):
            with self.subTest(acceptance=item["acceptance"]):
                result = self.module.reconcile(
                    self.ledger(item), self.seed_worker(item), self.seed_evidence(item), self.spec_bytes
                )
                self.assertEqual("INVALID_INPUT", result["outcome"])

    def test_create_seed_short_or_zero_fails_but_extra_paired_rows_pass(self):
        item = self.seed_item()
        for matched, expected in ((0, "FAILED"), (1, "FAILED"), (3, "VERIFIED")):
            with self.subTest(matched=matched):
                result = self.module.reconcile(
                    self.ledger(item),
                    self.seed_worker(item, records=max(2, matched)),
                    self.seed_evidence(item, matched_count=matched),
                    self.spec_bytes,
                )
                self.assertEqual(expected, self.result_for(result, item["id"])["disposition"])

    def test_missing_data_seeded_row_stays_incomplete_even_when_probe_passes(self):
        item = self.seed_item()
        worker = self.seed_worker(item)
        worker["data_seeded"] = []

        result = self.module.reconcile(
            self.ledger(item), worker, self.seed_evidence(item), self.spec_bytes
        )

        self.assertEqual("INCOMPLETE", self.result_for(result, item["id"])["disposition"])

    def test_create_seed_report_short_or_zero_contradicts_success(self):
        item = self.seed_item()
        for records in (0, 1):
            with self.subTest(records=records):
                result = self.module.reconcile(
                    self.ledger(item),
                    self.seed_worker(item, records=records),
                    self.seed_evidence(item, matched_count=2),
                    self.spec_bytes,
                )
                self.assertEqual(
                    "INCOMPLETE", self.result_for(result, item["id"])["disposition"]
                )

    def test_calibration_uses_one_resolved_value_and_rejects_stale_literal(self):
        directive = (
            "Calibration: quota = 70-80% of pipeline - reference query: "
            "SELECT SUM(Amount) FROM Opportunity"
        )
        item = self.seed_item(
            required_values={"Status": "3", "Quota__c": 75},
            calibration={
                "directive": directive,
                "resolution": "computed",
                "reference_result": 100,
                "reference_source": "saved calibration query 4",
                "resolved_field": "Quota__c",
                "resolved_value": 75,
                "spec_literal": 50,
                "error": None,
            },
        )
        worker = self.seed_worker(item, records=2)

        passed = self.module.reconcile(
            self.ledger(item), worker, self.seed_evidence(item), self.spec_bytes
        )
        self.assertEqual("VERIFIED", self.result_for(passed, item["id"])["disposition"])

        stale = self.module.reconcile(
            self.ledger(item),
            worker,
            self.seed_evidence(
                item,
                values_match=False,
                actual_values={"Status": "3", "Quota__c": 50},
            ),
            self.spec_bytes,
        )
        self.assertEqual("FAILED", self.result_for(stale, item["id"])["disposition"])

    def test_unresolvable_calibration_without_literal_fallback_is_blocked(self):
        directive = (
            "Calibration: quota = 70-80% of pipeline - reference query: "
            "SELECT SUM(Amount) FROM Opportunity"
        )
        item = self.seed_item(
            calibration={
                "directive": directive,
                "resolution": "blocked",
                "reference_result": None,
                "reference_source": "saved calibration query failure 4",
                "resolved_field": "Quota__c",
                "error": "reference query returned no data and spec has no literal fallback",
            }
        )

        result = self.module.reconcile(self.ledger(item), None, None, self.spec_bytes)

        self.assertEqual("BLOCKED", self.result_for(result, item["id"])["disposition"])

    def test_calibration_query_failure_uses_approved_literal_fallback_once(self):
        directive = (
            "Calibration: quota = 70-80% of pipeline - reference query: "
            "SELECT SUM(Amount) FROM Opportunity"
        )
        item = self.seed_item(
            required_values={"Status": "3", "Quota__c": 50},
            calibration={
                "directive": directive,
                "resolution": "literal_fallback",
                "reference_result": None,
                "reference_source": "saved calibration query failure 4",
                "resolved_field": "Quota__c",
                "resolved_value": 50,
                "spec_literal": 50,
                "error": "reference query returned no data",
            },
        )

        result = self.module.reconcile(
            self.ledger(item),
            self.seed_worker(item),
            self.seed_evidence(item),
            self.spec_bytes,
        )

        self.assertEqual("VERIFIED", self.result_for(result, item["id"])["disposition"])

    def test_update_seed_checks_every_literal_and_prose_target(self):
        item = self.seed_item(
            operation="UPDATE",
            object="Case",
            count=None,
            stable_keys=None,
            required_values=None,
            targets=[
                {
                    "stable_key": {"Id": "500xx"},
                    "literal_values": {"Regulatory_Market__c": "EU"},
                    "prose_fields": ["Scientific_Question__c"],
                }
            ],
        )
        for key in ("count", "stable_keys", "required_values"):
            item["acceptance"].pop(key)
        worker = self.seed_worker(item, records=1, operation="UPDATE")

        def evidence(actual_values):
            payload = self.evidence(
                [
                    {
                        "item_id": item["id"],
                        "verification": "seed_probe",
                        "result": "match",
                        "attribution": "applied",
                        "change_source": "current update execution result 21",
                        "source": "saved SOQL result 23",
                        "details": "Named Case target queried.",
                        "seed_probe": {
                            "operation": "UPDATE",
                            "object": "Case",
                            "targets": [
                                {
                                    "stable_key": {"Id": "500xx"},
                                    "actual_values": actual_values,
                                }
                            ],
                        },
                    }
                ]
            )
            payload["ledger_sha256"] = self.module.ledger_sha256(self.ledger(item))
            return payload

        cases = (
            ({"Regulatory_Market__c": "US", "Scientific_Question__c": "text"}, "FAILED"),
            ({"Regulatory_Market__c": "EU", "Scientific_Question__c": "   "}, "FAILED"),
            ({"Regulatory_Market__c": "EU", "Scientific_Question__c": "approved prose"}, "VERIFIED"),
        )
        for actual, disposition in cases:
            with self.subTest(actual=actual):
                result = self.module.reconcile(
                    self.ledger(item), worker, evidence(actual), self.spec_bytes
                )
                self.assertEqual(disposition, self.result_for(result, item["id"])["disposition"])

    def test_malformed_update_targets_fail_closed(self):
        item = self.seed_item(operation="UPDATE", object="Case", targets=[])
        for key in ("count", "stable_keys", "required_values"):
            item["acceptance"].pop(key, None)

        result = self.module.reconcile(
            self.ledger(item), self.seed_worker(item, operation="UPDATE"), self.seed_evidence(item), self.spec_bytes
        )

        self.assertEqual("INVALID_INPUT", result["outcome"])

    def test_evidence_must_bind_final_ledger_and_orchestrator_provenance(self):
        evidence = self.evidence()
        evidence["ledger_sha256"] = "0" * 64
        evidence["orchestrator_provenance"] = ""

        result = self.reconcile(evidence=evidence)

        self.assertEqual("INCOMPLETE", self.result_for(result)["disposition"])
        self.assertTrue(any("ledger_sha256" in error for error in result["validation_errors"]))
        self.assertTrue(any("orchestrator_provenance" in error for error in result["validation_errors"]))

    def test_source_quote_must_be_nonempty_and_present_in_hashed_spec(self):
        for quote in ("", "text that is not in the approved spec"):
            item = {**self.item, "source": {**self.item["source"], "quote": quote}}
            with self.subTest(quote=quote):
                result = self.module.reconcile(
                    self.ledger(item), self.worker(), self.evidence(), self.spec_bytes
                )
                self.assertEqual("INVALID_INPUT", result["outcome"])


class CompletionCliTests(unittest.TestCase):
    def test_malformed_json_returns_structured_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec_path = root / "spec.md"
            ledger_path = root / "ledger.json"
            worker_path = root / "worker.json"
            evidence_path = root / "evidence.json"
            spec_path.write_text("approved", encoding="utf-8")
            ledger_path.write_text("{not json", encoding="utf-8")
            worker_path.write_text("{}", encoding="utf-8")
            evidence_path.write_text("{}", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--spec",
                    str(spec_path),
                    "--ledger",
                    str(ledger_path),
                    "--worker-result",
                    str(worker_path),
                    "--evidence",
                    str(evidence_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(2, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assertEqual("INVALID_INPUT", payload["outcome"])
        self.assertFalse(payload["valid"])


class StaticPromptWiringTests(unittest.TestCase):
    """Minimal source wiring checks; these do not prove model or org behavior."""

    def test_all_phase_templates_receive_common_contract_and_expected_ledger(self):
        for name in ("phase1.md", "phase2.md", "phase3.md"):
            with self.subTest(name=name):
                text = (ROOT / "prompts" / "building" / name).read_text(encoding="utf-8")
                self.assertIn("{{COMPLETION_CONTRACT}}", text)
                self.assertIn("{{EXPECTED_COMPLETION_LEDGER}}", text)

    def test_orchestrator_wires_helper_and_common_fragment(self):
        text = (ROOT / "commands" / "scout-building.md").read_text(encoding="utf-8")
        self.assertIn("scripts/build-completion.py", text)
        self.assertIn("prompts/building/completion-contract.md", text)

    def test_ledger_freeze_follows_workspace_prep_and_settles_calibration_once(self):
        text = (ROOT / "commands" / "scout-building.md").read_text(encoding="utf-8")
        self.assertLess(text.index("### Workspace Prep"), text.index("### Settle Calibration and Freeze"))
        self.assertLess(text.index("### Settle Calibration and Freeze"), text.index("### Phase Prep Procedure"))
        self.assertIn("Complete that allowed\nannotation before hashing", text)
        phase1 = (ROOT / "prompts" / "building" / "phase1.md").read_text(encoding="utf-8")
        self.assertIn("Do not rerun the reference query or recompute", phase1)

    def test_phase_skipped_arrays_are_authorized_omissions_only(self):
        for name in ("phase1.md", "phase2.md", "phase3.md"):
            with self.subTest(name=name):
                text = (ROOT / "prompts" / "building" / name).read_text(encoding="utf-8")
                self.assertNotIn("record SKIPPED", text)
                self.assertIn("authorized omission only", text)

    def test_validation_distinguishes_observed_seed_failure_from_missing_evidence(self):
        text = (ROOT / "prompts" / "building" / "sub-agent-validation.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Observed zero or short results are FAILED", text)
        self.assertIn("unavailable probe is INCOMPLETE", text)

    def test_later_phases_use_reconciled_prerequisite_dispositions(self):
        text = (ROOT / "commands" / "scout-building.md").read_text(encoding="utf-8")
        self.assertIn("Use reconciled item dispositions", text)
        self.assertIn("needed prerequisite", text)
        self.assertIn("Unrelated AWAITING_QA", text)


if __name__ == "__main__":
    unittest.main()
