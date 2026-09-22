"""Behavioral regressions for complete, current, transport-specific Flow gates."""

import copy
import unittest

import test_build_completion as fixtures


class FlowRequiredTestTests(unittest.TestCase):
    setUp = fixtures.CompletionReconciliationTests.setUp
    flow_phase_context = fixtures.CompletionReconciliationTests.flow_phase_context

    def context(self, mode="synchronous", names=None):
        names = names or ["Demo_Flow_Test", "Demo_Flow_Excluded_Test"]
        item, ledger, worker, evidence = self.flow_phase_context()
        expected = item["acceptance"]["flow_validation"]
        expected["required_tests_all_must_pass"] = names
        expected["target_org_id"] = "00D000000000001AAA"
        flow = evidence["observations"][0]["flow_validation"]
        flow["target_org_id"] = expected["target_org_id"]
        for section in ("deployment", "activation"):
            flow[section].update(build_id=ledger["build_id"], target_org_id=flow["target_org_id"])
        prototype = flow.pop("test")
        flow["tests"] = []
        worker_row = worker["deployed"][0]
        for field in list(worker_row):
            if field.startswith("flow_test_") or field == "tested_flow_version_number":
                del worker_row[field]
        worker_row["flow_tests"] = []
        for index, name in enumerate(names):
            test = {
                **prototype,
                "test_api_name": name,
                "execution_mode": mode,
                "build_id": ledger["build_id"],
                "target_org_id": flow["target_org_id"],
                "flow_id": flow["deployment"]["flow_id"],
                "run_id": None,
                "queue_item_id": f"709-queue-{index}" if mode == "asynchronous" else None,
                "apex_test_result_id": f"07M-method-{index}",
                "launch_source": f"saved current request {index}",
                "terminal_source": f"saved current response {index}",
                "version_source": f"saved FlowTestResult query {index}",
            }
            test["version_result"] = {
                key: test[key]
                for key in ("build_id", "target_org_id", "flow_api_name", "test_api_name",
                            "flow_id", "tested_version", "outcome", "queue_item_id",
                            "apex_test_result_id")
            }
            test["version_result"]["id"] = f"2hU-result-{index}"
            flow["tests"].append(test)
            worker_row["flow_tests"].append(self.claim(test))
        evidence["ledger_sha256"] = self.module.ledger_sha256(ledger)
        return item, ledger, worker, evidence

    @staticmethod
    def claim(test):
        return {key: copy.deepcopy(value) for key, value in test.items()
                if key not in {"launch_source", "terminal_source", "version_source", "version_result"}}

    def assess(self, context):
        _, ledger, worker, evidence = context
        return self.module.reconcile(ledger, worker, evidence, self.spec_bytes)

    def assert_unverified(self, context):
        result = self.assess(context)
        self.assertNotEqual("FULLY_VERIFIED", result["outcome"], result)
        self.assertFalse(any(row["disposition"] == "VERIFIED" for row in result["items"]), result)
        return result

    def test_complete_sync_and_async_collections_verify_exact_version(self):
        for mode in ("synchronous", "asynchronous"):
            with self.subTest(mode=mode):
                result = self.assess(self.context(mode))
                self.assertEqual("FULLY_VERIFIED", result["outcome"], result)

    def test_explicit_legacy_singleton_remains_compatible(self):
        self.assertEqual("FULLY_VERIFIED", self.assess(self.flow_phase_context())["outcome"])
        context = self.context(names=["Demo_Flow_Test"])
        context[0]["acceptance"]["flow_validation"].pop("flow_test_api_name")
        context[3]["ledger_sha256"] = self.module.ledger_sha256(context[1])
        self.assertEqual("FULLY_VERIFIED", self.assess(context)["outcome"])
        context = self.context(names=["Demo_Flow_Test"])
        context[0]["acceptance"]["flow_validation"].pop("required_tests_all_must_pass")
        context[3]["ledger_sha256"] = self.module.ledger_sha256(context[1])
        self.assertEqual("FULLY_VERIFIED", self.assess(context)["outcome"])

    def test_all_required_declaration_cannot_fall_back_to_one_legacy_result(self):
        context = self.flow_phase_context()
        context[0]["acceptance"]["flow_validation"]["required_tests_all_must_pass"] = [
            "Demo_Flow_Test", "Demo_Flow_Excluded_Test"]
        context[3]["ledger_sha256"] = self.module.ledger_sha256(context[1])
        self.assert_unverified(context)

    def test_malformed_and_conflicting_required_declarations_reject_ledger(self):
        for names in (None, [], "Demo_Flow_Test", ["Demo_Flow_Test", "Demo_Flow_Test"],
                      ["bad test"], [True], [{"name": "Demo_Flow_Test"}], ["Other_Test"]):
            with self.subTest(names=names):
                context = self.flow_phase_context()
                context[0]["acceptance"]["flow_validation"]["required_tests_all_must_pass"] = names
                context[3]["ledger_sha256"] = self.module.ledger_sha256(context[1])
                result = self.assess(context)
                self.assertEqual("INVALID_INPUT", result["outcome"], result)

    def test_unsupported_mode_cannot_hide_required_declaration(self):
        context = self.flow_phase_context("unsupported")
        context[0]["acceptance"]["flow_validation"]["required_tests_all_must_pass"] = ["Demo_Flow_Test"]
        context[3]["ledger_sha256"] = self.module.ledger_sha256(context[1])
        self.assertEqual("INVALID_INPUT", self.assess(context)["outcome"])

    def test_wrong_missing_duplicate_and_diagnostic_names_cannot_pass(self):
        for change in ("empty", "missing", "duplicate", "wrong", "diagnostic"):
            with self.subTest(change=change):
                context = self.context()
                flow = context[3]["observations"][0]["flow_validation"]
                tests = flow["tests"]
                if change == "empty": tests.clear()
                elif change == "missing": tests.pop()
                elif change == "duplicate": tests.append(copy.deepcopy(tests[0]))
                elif change == "wrong": tests[1]["test_api_name"] = "Other_Test"
                else:
                    tests.append({**copy.deepcopy(tests[0]), "test_api_name": "Diagnostic_Test"})
                context[2]["deployed"][0]["flow_tests"] = [self.claim(test) for test in tests]
                self.assert_unverified(context)

    def test_nonpassing_companions_remain_unfulfilled(self):
        for status, outcome in (("terminal", "Fail"), ("terminal", "Error"),
                                ("terminal", "Skip"), ("pending", None), ("unavailable", None)):
            with self.subTest(status=status, outcome=outcome):
                context = self.context("asynchronous")
                flow = context[3]["observations"][0]["flow_validation"]
                test = flow["tests"][1]
                test.update(status=status, outcome=outcome)
                if status == "terminal":
                    test["version_result"]["outcome"] = outcome
                else:
                    test.update(tested_version=None, version_result=None,
                                terminal_source=None, version_source=None, apex_test_result_id=None)
                row = context[2]["deployed"][0]
                row["flow_tests"][1] = self.claim(test)
                row.update(flow_status="Draft", validation_status="AWAITING_QA",
                           active_flow_id=None, active_flow_version_number=None)
                flow["activation"].update(attempted=False, status="not_attempted",
                                          active_flow_id=None, active_version=None)
                context[2]["completion"][0]["status"] = "awaiting_qa"
                result = self.assert_unverified(context)
                self.assertTrue(result["valid"], result)
                self.assertEqual("AWAITING_QA", result["items"][0]["disposition"])

    def test_current_attempt_org_flow_and_version_attribution_cannot_mix(self):
        for section, field, value in (
            ("test", "build_id", "old-build"), ("test", "target_org_id", "other-org"),
            ("test", "flow_id", "other-flow"), ("test", "tested_version", 12),
            ("version_result", "build_id", "old-build"),
            ("version_result", "target_org_id", "other-org"),
            ("version_result", "test_api_name", "Diagnostic_Test"),
            ("version_result", "flow_api_name", "Other_Flow"),
            ("deployment", "target_org_id", "other-org"),
            ("activation", "build_id", "old-build"),
        ):
            with self.subTest(section=section, field=field):
                context = self.context()
                flow = context[3]["observations"][0]["flow_validation"]
                target = flow["tests"][1] if section == "test" else (
                    flow["tests"][1]["version_result"] if section == "version_result" else flow[section])
                target[field] = value
                context[2]["deployed"][0]["flow_tests"][1] = self.claim(flow["tests"][1])
                self.assert_unverified(context)

    def test_sync_requires_method_result_link_and_null_queue_and_run(self):
        for field, value in (("apex_test_result_id", None), ("queue_item_id", "invented-queue"),
                             ("run_id", "07M-method-1"), ("execution_mode", "automatic")):
            with self.subTest(field=field):
                context = self.context()
                test = context[3]["observations"][0]["flow_validation"]["tests"][1]
                test[field] = value
                context[2]["deployed"][0]["flow_tests"][1] = self.claim(test)
                self.assert_unverified(context)
        context = self.context()
        context[3]["observations"][0]["flow_validation"]["tests"][1]["version_result"]["apex_test_result_id"] = "07M-stale"
        self.assert_unverified(context)
        context = self.context()
        context[3]["observations"][0]["flow_validation"]["tests"][1]["version_result"]["run_id"] = "invented-run"
        self.assert_unverified(context)

    def test_async_requires_exact_terminal_queue_relationship(self):
        for value in (None, "other-queue"):
            with self.subTest(value=value):
                context = self.context("asynchronous")
                context[3]["observations"][0]["flow_validation"]["tests"][1]["version_result"]["queue_item_id"] = value
                self.assert_unverified(context)

    def test_async_run_id_is_optional_but_must_be_observed_and_correlated(self):
        context = self.context("asynchronous")
        test = context[3]["observations"][0]["flow_validation"]["tests"][1]
        test["run_id"] = "707-observed-run"
        context[2]["deployed"][0]["flow_tests"][1] = self.claim(test)
        self.assert_unverified(context)
        test["run_source"] = "saved queue parent run query"
        self.assert_unverified(context)
        test["version_result"]["run_id"] = test["run_id"]
        self.assertEqual("FULLY_VERIFIED", self.assess(context)["outcome"])

    def test_captured_sync_null_queue_identity_preserves_actual_failure(self):
        # Whitelisted fields from the retained native tool result at
        # 2026-09-22T18:02:08.726Z. Other context below is a synthetic local fixture.
        captured = {
            "Id": "2hUKa000000007NMAQ", "ApexTestResultId": "07MKa000007WMhTMAW",
            "ApexTestQueueItemId": None, "Result": "Fail",
        }
        context = self.context()
        flow = context[3]["observations"][0]["flow_validation"]
        test = flow["tests"][1]
        test.update(apex_test_result_id=captured["ApexTestResultId"],
                    queue_item_id=captured["ApexTestQueueItemId"], outcome=captured["Result"])
        test["version_result"].update(
            id=captured["Id"], apex_test_result_id=captured["ApexTestResultId"],
            queue_item_id=captured["ApexTestQueueItemId"], outcome=captured["Result"])
        row = context[2]["deployed"][0]
        row["flow_tests"][1] = self.claim(test)
        row.update(flow_status="Draft", validation_status="AWAITING_QA",
                   active_flow_id=None, active_flow_version_number=None)
        flow["activation"].update(attempted=False, status="not_attempted",
                                  active_flow_id=None, active_version=None)
        context[2]["completion"][0]["status"] = "awaiting_qa"
        result = self.assert_unverified(context)
        self.assertTrue(result["valid"], result)
        self.assertEqual("AWAITING_QA", result["items"][0]["disposition"])

    def test_reused_result_records_and_missing_context_fail_closed(self):
        for field in ("id", "apex_test_result_id"):
            with self.subTest(field=field):
                context = self.context()
                tests = context[3]["observations"][0]["flow_validation"]["tests"]
                tests[1]["version_result"][field] = tests[0]["version_result"][field]
                if field == "apex_test_result_id":
                    tests[1][field] = tests[0][field]
                    context[2]["deployed"][0]["flow_tests"][1] = self.claim(tests[1])
                self.assert_unverified(context)
        for section, field in (("context", "target_org_id"), ("deployment", "build_id"),
                               ("activation", "target_org_id")):
            with self.subTest(section=section, field=field):
                context = self.context()
                flow = context[3]["observations"][0]["flow_validation"]
                (flow if section == "context" else flow[section]).pop(field)
                self.assert_unverified(context)

    def test_malformed_collection_values_fail_closed_without_exceptions(self):
        for field, value in (("tests", None), ("tests", {}), ("tests", [None]),
                             ("tests", [{"test_api_name": []}])):
            with self.subTest(value=value):
                context = self.context()
                context[3]["observations"][0]["flow_validation"][field] = value
                self.assert_unverified(context)

    def test_zero_or_ambiguous_independent_results_cannot_pass(self):
        for value in (None, {}, [], {"id": "2hU-only"}):
            with self.subTest(value=value):
                context = self.context()
                context[3]["observations"][0]["flow_validation"]["tests"][1]["version_result"] = value
                self.assert_unverified(context)
        for count in (0, -1, True, "1", None):
            with self.subTest(num_tests_run=count):
                context = self.context()
                context[3]["observations"][0]["flow_validation"]["tests"][1]["num_tests_run"] = count
                self.assert_unverified(context)

    def test_missing_or_conflated_raw_sources_cannot_pass(self):
        for field in ("launch_source", "terminal_source", "version_source"):
            with self.subTest(field=field):
                context = self.context()
                context[3]["observations"][0]["flow_validation"]["tests"][1][field] = None
                self.assert_unverified(context)
        context = self.context()
        test = context[3]["observations"][0]["flow_validation"]["tests"][1]
        test["version_source"] = test["terminal_source"]
        self.assert_unverified(context)

    def test_worker_companion_claims_and_collection_forms_cannot_conflict(self):
        context = self.context()
        context[2]["deployed"][0]["flow_tests"][1]["outcome"] = "Fail"
        self.assert_unverified(context)
        context = self.context()
        context[3]["observations"][0]["flow_validation"]["test"] = copy.deepcopy(
            context[3]["observations"][0]["flow_validation"]["tests"][0])
        self.assert_unverified(context)
        context = self.flow_phase_context()
        context[3]["observations"][0]["flow_validation"]["test"]["execution_mode"] = "synchronous"
        self.assert_unverified(context)
        context = self.flow_phase_context()
        context[0]["acceptance"]["flow_validation"]["target_org_id"] = "selected-org"
        context[3]["ledger_sha256"] = self.module.ledger_sha256(context[1])
        self.assert_unverified(context)


if __name__ == "__main__":
    unittest.main()
