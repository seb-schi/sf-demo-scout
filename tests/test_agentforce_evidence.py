import copy
import hashlib
import importlib.util
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "agentforce_evidence.py"
GATE = b"canonical agentforce gate"
GATE_SHA = hashlib.sha256(GATE).hexdigest()


def load_module():
    spec = importlib.util.spec_from_file_location("agentforce_evidence", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentforceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.expected = {
            "agent_api_name": "Demo_Agent",
            "hero_action": "Flag_Case",
            "behavior": "mutating",
            "source_kind": "agent_script",
            "criteria": {
                "target": {"Case.Id": "500xx"},
                "before": {"Case.Flagged__c": False},
                "after": {"Case.Flagged__c": True},
            },
        }
        self.context = {
            "item_id": "p3.agent.flag-case",
            "agent_api_name": "Demo_Agent",
            "deployed_version_id": "0Xx-version-7",
            "deployment_source": "saved independent deploy/version read-back 3",
            "source_kind": "agent_script",
            "gate_sha256": GATE_SHA,
            "test": {
                "attempt_id": "attempt-1",
                "mode": "session_turn",
                "session_id": "session-current",
                "turn_id": "turn-current",
                "identity_source": "saved current test start/turn result 4",
                "history": [],
            },
        }
        self.runtime = {
            "agent_api_name": "Demo_Agent",
            "deployed_version_id": "0Xx-version-7",
            "gate_sha256": GATE_SHA,
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
                "source": "saved current preview trace / invocation 4",
            },
            "behavior": {
                "target": {"Case.Id": "500xx"},
                "before": {"Case.Flagged__c": False},
                "after": {"Case.Flagged__c": True},
                "source": "saved before and after SOQL 5",
            },
            "structure": {
                "method": "agent_script_validation",
                "result": "pass",
                "source": "saved validate authoring bundle result 2",
            },
        }

    def assess(self, expected=None, context=None, runtime=None):
        return self.module.assess(
            self.expected if expected is None else expected,
            self.context if context is None else context,
            self.runtime if runtime is None else runtime,
            GATE,
        )

    def test_current_live_mutation_with_exact_delta_passes(self):
        result = self.assess()

        self.assertTrue(result["valid"])
        self.assertEqual("PASS", result["assessment"])

    def test_successful_invocation_without_delta_fails(self):
        runtime = copy.deepcopy(self.runtime)
        runtime["behavior"]["after"] = {"Case.Flagged__c": False}

        result = self.assess(runtime=runtime)

        self.assertEqual("FAIL", result["assessment"])

    def test_preexisting_desired_value_without_discriminating_prestate_is_unavailable(self):
        runtime = copy.deepcopy(self.runtime)
        runtime["behavior"]["before"] = None

        result = self.assess(runtime=runtime)

        self.assertEqual("UNAVAILABLE", result["assessment"])

        runtime = copy.deepcopy(self.runtime)
        runtime["behavior"]["before"] = {"Case.Flagged__c": True}
        runtime["behavior"]["after"] = {"Case.Flagged__c": True}
        self.assertEqual("UNAVAILABLE", self.assess(runtime=runtime)["assessment"])

    def test_wrong_mutation_target_fails(self):
        runtime = copy.deepcopy(self.runtime)
        runtime["behavior"]["target"] = {"Case.Id": "500-other"}

        self.assertEqual("FAIL", self.assess(runtime=runtime)["assessment"])

    def test_read_only_current_invocation_and_exact_output_pass(self):
        expected = {
            **self.expected,
            "hero_action": "Answer_Question",
            "behavior": "read_only",
            "criteria": {
                "output": {"answer_contains": "approved dosage"},
                "side_effect": "not_applicable",
            },
        }
        runtime = copy.deepcopy(self.runtime)
        runtime["invocation"]["action"] = "Answer_Question"
        runtime["behavior"] = {
            "output": {"answer_contains": "approved dosage"},
            "side_effect": "not_applicable",
            "source": "saved current answer assertion 8",
        }

        passed = self.assess(expected=expected, runtime=runtime)
        runtime["behavior"]["output"] = {"answer_contains": "wrong answer"}
        failed = self.assess(expected=expected, runtime=runtime)

        self.assertEqual("PASS", passed["assessment"])
        self.assertEqual("FAIL", failed["assessment"])

    def test_stale_version_session_turn_or_job_case_is_ineligible(self):
        mutations = (
            ("deployed_version_id", "old-version"),
            ("session_id", "old-session"),
            ("turn_id", "old-turn"),
        )
        for key, value in mutations:
            with self.subTest(key=key):
                runtime = copy.deepcopy(self.runtime)
                if key == "deployed_version_id":
                    runtime[key] = value
                else:
                    runtime["test_identity"][key] = value
                self.assertEqual("UNAVAILABLE", self.assess(runtime=runtime)["assessment"])

        context = copy.deepcopy(self.context)
        context["test"] = {
            "attempt_id": "job-attempt",
            "mode": "job_case",
            "job_id": "job-current",
            "case_id": "case-current",
            "identity_source": "saved current test job/case selection 9",
            "history": [],
        }
        runtime = copy.deepcopy(self.runtime)
        runtime["test_identity"] = {
            "attempt_id": "job-attempt",
            "mode": "job_case",
            "job_id": "job-old",
            "case_id": "case-current",
        }
        runtime["evidence_channel"] = "test_job"
        self.assertEqual(
            "UNAVAILABLE", self.assess(context=context, runtime=runtime)["assessment"]
        )

    def test_simulated_or_expected_declaration_is_not_live_evidence(self):
        for field, value in (("simulated", True), ("live_actions", False)):
            with self.subTest(field=field):
                runtime = copy.deepcopy(self.runtime)
                runtime["invocation"][field] = value
                self.assertEqual("UNAVAILABLE", self.assess(runtime=runtime)["assessment"])
        for evidence_kind in (
            "expected_action_declaration",
            "transcript_only",
            "authoring_preview",
            "test_metrics",
        ):
            with self.subTest(evidence_kind=evidence_kind):
                runtime = copy.deepcopy(self.runtime)
                runtime["invocation"]["evidence_kind"] = evidence_kind
                self.assertEqual("UNAVAILABLE", self.assess(runtime=runtime)["assessment"])

    def test_current_failure_and_complete_trace_missing_invocation_fail(self):
        for status in ("failed", "not_invoked"):
            with self.subTest(status=status):
                runtime = copy.deepcopy(self.runtime)
                runtime["invocation"]["status"] = status
                runtime["invocation"]["evidence_kind"] = "complete_trace"
                self.assertEqual("FAIL", self.assess(runtime=runtime)["assessment"])

        runtime = copy.deepcopy(self.runtime)
        runtime["invocation"]["status"] = "not_invoked"
        runtime["invocation"]["evidence_kind"] = "live_trace"
        self.assertEqual("UNAVAILABLE", self.assess(runtime=runtime)["assessment"])

    def test_unavailable_or_uncorrelatable_evidence_is_not_observed_failure(self):
        runtime = copy.deepcopy(self.runtime)
        runtime["invocation"]["status"] = "unavailable"
        runtime["invocation"].pop("action")
        del runtime["behavior"]
        self.assertEqual("UNAVAILABLE", self.assess(runtime=runtime)["assessment"])

        runtime = self.event_log_runtime()
        runtime["retrieval"]["correlation"] = "unverified"
        self.assertEqual("UNAVAILABLE", self.assess(runtime=runtime)["assessment"])

    def test_behavior_is_required_only_after_a_successful_invocation(self):
        runtime = copy.deepcopy(self.runtime)
        runtime["invocation"]["status"] = "not_invoked"
        runtime["invocation"]["evidence_kind"] = "complete_trace"
        runtime["invocation"].pop("action")
        del runtime["behavior"]
        self.assertEqual("FAIL", self.assess(runtime=runtime)["assessment"])

        runtime = copy.deepcopy(self.runtime)
        del runtime["behavior"]
        malformed = self.assess(runtime=runtime)
        self.assertFalse(malformed["valid"])
        self.assertEqual("INVALID", malformed["assessment"])

    def event_log_runtime(self):
        runtime = copy.deepcopy(self.runtime)
        runtime["evidence_channel"] = "event_log"
        runtime["retrieval"] = {
            "describe_source": "saved REST describe result 11",
            "field_map": {
                "session": "described-session-field",
                "turn": "described-turn-field",
                "version": "described-version-field",
                "timestamp": "described-time-field",
            },
            "session_mapping_source": "saved verified mapping 12",
            "correlation": "verified",
            "lower_inclusive": "2026-09-17T10:30:05Z",
            "upper_exclusive": "2026-09-17T10:30:06Z",
            "event_timestamp": "2026-09-17T10:30:05Z",
        }
        return runtime

    def test_event_log_same_second_lower_bound_is_eligible(self):
        self.assertEqual("PASS", self.assess(runtime=self.event_log_runtime())["assessment"])

    def test_event_log_requires_describe_mapping_and_half_open_fence(self):
        runtime = self.event_log_runtime()
        runtime["retrieval"]["describe_source"] = ""
        self.assertEqual("UNAVAILABLE", self.assess(runtime=runtime)["assessment"])

        runtime = self.event_log_runtime()
        runtime["retrieval"]["event_timestamp"] = "2026-09-17T10:30:06Z"
        self.assertEqual("UNAVAILABLE", self.assess(runtime=runtime)["assessment"])

    def test_compiled_structure_failure_blocks_but_agent_script_does_not_need_local_actions(self):
        expected = {**self.expected, "source_kind": "compiled_planner"}
        context = {**self.context, "source_kind": "compiled_planner"}
        runtime = copy.deepcopy(self.runtime)
        runtime["structure"] = {
            "method": "compiled_schema_join",
            "result": "fail",
            "source": "saved localActions join 13",
        }
        blocked = self.assess(expected=expected, context=context, runtime=runtime)

        self.assertEqual("BLOCKED", blocked["assessment"])
        self.assertEqual("PASS", self.assess()["assessment"])

    def test_unknown_source_kind_is_unavailable(self):
        expected = {**self.expected, "source_kind": "unknown"}
        context = {**self.context, "source_kind": "unknown"}
        runtime = copy.deepcopy(self.runtime)
        runtime["structure"] = {
            "method": "unknown",
            "result": "unavailable",
            "source": "saved source-kind inspection 3",
        }
        self.assertEqual(
            "UNAVAILABLE", self.assess(expected=expected, context=context, runtime=runtime)["assessment"]
        )

    def test_gate_digest_mismatch_is_stale_evidence(self):
        runtime = copy.deepcopy(self.runtime)
        runtime["gate_sha256"] = "0" * 64
        self.assertEqual("UNAVAILABLE", self.assess(runtime=runtime)["assessment"])

    def test_context_requires_independent_deploy_and_test_identity_sources(self):
        for path in ("deployment_source", "identity_source"):
            with self.subTest(path=path):
                context = copy.deepcopy(self.context)
                if path == "deployment_source":
                    context[path] = ""
                else:
                    context["test"][path] = ""
                result = self.assess(context=context)
                self.assertFalse(result["valid"])
                self.assertEqual("INVALID", result["assessment"])


    def test_later_fixed_retest_can_supersede_failure_but_history_is_required(self):
        context = copy.deepcopy(self.context)
        context["test"].update(
            {
                "attempt_id": "attempt-2",
                "history": [
                    {
                        "attempt_id": "attempt-1",
                        "outcome": "failed",
                        "source": "saved failed current-test result 19",
                    }
                ],
                "supersedes_attempt_id": "attempt-1",
                "fix_source": "saved concrete fix/deploy result 20",
            }
        )
        runtime = copy.deepcopy(self.runtime)
        runtime["test_identity"]["attempt_id"] = "attempt-2"
        self.assertEqual("PASS", self.assess(context=context, runtime=runtime)["assessment"])

        context["test"].pop("fix_source")
        malformed = self.assess(context=context, runtime=runtime)
        self.assertFalse(malformed["valid"])
        self.assertEqual("INVALID", malformed["assessment"])

    def test_malformed_shapes_and_non_string_enums_fail_closed(self):
        for expected, context, runtime in (
            ([], self.context, self.runtime),
            (self.expected, [], self.runtime),
            (self.expected, self.context, []),
            ({**self.expected, "behavior": []}, self.context, self.runtime),
            (self.expected, self.context, {**self.runtime, "evidence_channel": []}),
        ):
            with self.subTest(value=(expected, context, runtime)):
                result = self.module.assess(expected, context, runtime, GATE)
                self.assertFalse(result["valid"])
                self.assertEqual("INVALID", result["assessment"])


class AgentforcePromptWiringTests(unittest.TestCase):
    """Static contract wiring only; these tests do not certify live Salesforce behavior."""

    def test_canonical_gate_uses_describe_and_correlated_current_test_without_invented_query(self):
        text = (ROOT / "prompts" / "building" / "agentforce-validation-gate.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("REST Describe", text)
        self.assertIn("session + turn + deployed version", text)
        self.assertIn("lower-inclusive", text)
        self.assertIn("upper-exclusive", text)
        self.assertNotIn("CreatedDate = TODAY", text)
        self.assertNotIn("SELECT StepType, Action", text)
        self.assertNotIn("IsSuccessful", text)

    def test_source_specific_structural_rules_are_wired(self):
        gate = (ROOT / "prompts" / "building" / "agentforce-validation-gate.md").read_text(
            encoding="utf-8"
        )
        phase = (ROOT / "prompts" / "building" / "phase3.md").read_text(encoding="utf-8")
        for text in (gate, phase):
            self.assertIn("Agent Script", text)
            self.assertIn("compiled", text)
            self.assertIn("localActions", text)
        self.assertIn("does not require `localActions`", gate)
        self.assertNotIn("Action-Invocation Probe", phase)
        self.assertNotIn("event-log probe", phase)
        self.assertNotIn("If no action invocation was confirmed", phase)

    def test_orchestrator_records_gate_digest_and_independent_runtime_context(self):
        command = (ROOT / "commands" / "scout-building.md").read_text(encoding="utf-8")
        validation = (ROOT / "prompts" / "building" / "sub-agent-validation.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("agentforce-validation-gate.md", command)
        self.assertIn("gate_sha256", command)
        self.assertIn("agent_contexts", validation)
        self.assertIn("scripts/agentforce_evidence.py", validation)
        self.assertIn("summary only", validation)

    def test_documented_runtime_example_matches_the_executable_evaluator(self):
        validation = (ROOT / "prompts" / "building" / "sub-agent-validation.md").read_text(
            encoding="utf-8"
        )
        match = re.search(
            r"<!-- agent-runtime-example:start -->\s*```json\s*(.*?)\s*```\s*"
            r"<!-- agent-runtime-example:end -->",
            validation,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match)
        runtime = json.loads(match.group(1))
        gate = (ROOT / "prompts" / "building" / "agentforce-validation-gate.md").read_bytes()
        gate_sha = hashlib.sha256(gate).hexdigest()
        runtime["gate_sha256"] = gate_sha
        expected = {
            "agent_api_name": "Demo_Agent",
            "hero_action": "Flag_Case",
            "behavior": "mutating",
            "source_kind": "agent_script",
            "criteria": {
                "target": {"Case.Id": "500xx"},
                "before": {"Case.Flagged__c": False},
                "after": {"Case.Flagged__c": True},
            },
        }
        context = {
            "item_id": "p3.agent.flag-case",
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

        result = load_module().assess(expected, context, runtime, gate)

        self.assertTrue(result["valid"])
        self.assertEqual("PASS", result["assessment"])

    def test_reporting_preserves_runtime_assessment_and_other_obligations(self):
        change_log = (ROOT / "prompts" / "building" / "change-log-template.md").read_text(
            encoding="utf-8"
        )
        handover = (ROOT / "prompts" / "building" / "handover-brief.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("runtime assessment", change_log)
        self.assertIn("deployed version", change_log)
        self.assertIn("Every remaining Agentforce", handover)
        self.assertIn("only when its reconciled ledger item remains", handover)


if __name__ == "__main__":
    unittest.main()
