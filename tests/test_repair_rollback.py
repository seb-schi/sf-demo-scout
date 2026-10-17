"""Focused static contracts for direct repair and incumbent rollback routing."""

from pathlib import Path
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]


class RepairRollbackContractTests(unittest.TestCase):
    """Check only the prompt boundaries that select and order the shared contract."""

    def read(self, relative):
        return (REPOSITORY / relative).read_text(encoding="utf-8")

    def test_direct_repair_entrypoints_share_one_compact_route(self):
        direct = self.read("prompts/building/direct-repair.md")
        self.assertIn("component-rollback.md", direct)
        self.assertIn("failed", direct)
        self.assertIn("already_satisfied", direct)
        self.assertIn("unverified", direct)
        self.assertIn("does not create a full ledger", direct)
        self.assertIn("pending repair checkpoint", direct)

        self.assertIn("prompts/building/direct-repair.md", self.read("AGENTS.md"))

    def test_phase_mutation_rules_load_shared_rollback_before_deploying(self):
        for relative in ("prompts/building/phase1.md", "prompts/building/phase2.md"):
            with self.subTest(relative=relative):
                prompt = self.read(relative)
                contract = prompt.index("{{COMPONENT_ROLLBACK}}")
                deploy = prompt.index("Deploy in small increments")
                self.assertLess(contract, deploy)

    def test_phase_workers_receive_materialized_shared_contract_without_nested_tokens(self):
        contract = self.read("prompts/building/component-rollback.md")
        self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", contract)
        self.assertNotIn("{{", contract)

        for relative in ("prompts/building/phase1.md", "prompts/building/phase2.md"):
            with self.subTest(relative=relative):
                prompt = self.read(relative)
                self.assertIn("{{COMPONENT_ROLLBACK}}", prompt)
                materialized = (
                    prompt.replace("{{COMPONENT_ROLLBACK}}", contract)
                    .replace("{{ASSET_HELPER}}", "/installed/scripts/build-assets.py")
                    .replace("{{ROLLBACK_DIR}}", "/org/rollback")
                )
                section = materialized[
                    materialized.index("# Existing and New Component Rollback") :
                    materialized.index("## Deployment Rules")
                ]
                self.assertNotIn("{{", section)
                self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", section)

    def test_folder_absence_and_inactive_flow_rollback_fail_closed(self):
        phase1 = self.read("prompts/building/phase1.md")
        report_rules = phase1[phase1.index("### Report Rules") : phase1.index("<!-- /IF:REPORTS -->")]
        self.assertNotIn("returns nothing", report_rules)
        self.assertIn("positive absence evidence", report_rules)
        self.assertIn("BLOCKED", report_rules)

        rollback = self.read("prompts/building/component-rollback.md")
        self.assertIn("current read-back proves inactive", rollback)
        self.assertIn("BLOCKED — manual Flow deactivation", rollback)
        self.assertIn("stage the preserved original definition", rollback)

    def test_no_mutation_already_satisfied_is_receipt_exempt(self):
        validation = self.read("prompts/building/sub-agent-validation.md")
        contract = self.read("prompts/building/component-rollback.md")
        for text in (validation, contract):
            with self.subTest(surface=text[:40]):
                self.assertIn("already_satisfied", text)
                self.assertIn("baseline", text)
                self.assertIn("current", text)
                self.assertIn("no mutation", text)

    def test_inactive_flow_rollback_separates_current_state_branches(self):
        rollback = self.read("prompts/building/component-rollback.md")
        flow = rollback[rollback.index("- Existing Flow:") : rollback.index("- Proven-new component:")]
        flow = " ".join(flow.split())
        inactive = flow.index("current read-back proves inactive")
        unknown = flow.index("If current state is unknown")
        active = flow.index("If current state is active")
        self.assertLess(inactive, unknown)
        self.assertLess(unknown, active)
        self.assertNotIn("deactivation operation", flow[inactive:unknown])
        self.assertIn("supported deactivation operation", flow[active:])
        self.assertIn("BLOCKED — manual Flow deactivation", flow[active:])

    def test_change_log_and_handover_carry_preservation_evidence(self):
        change_log = self.read("prompts/building/change-log-template.md")
        handover = self.read("prompts/building/handover-brief.md")
        self.assertIn("Existing Component Before-State", change_log)
        self.assertIn("Existing Component Before-State", handover)


if __name__ == "__main__":
    unittest.main()
