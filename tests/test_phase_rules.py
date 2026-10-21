"""Live technical rules in the phase prompts that /scout reads by section.

Static source checks only; they don't prove model compliance or org behaviour.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


class PhaseRuleTests(unittest.TestCase):
    def test_email_to_case_base_scope_production_confirmation_and_agent_probe(self):
        phase1 = read("prompts/building/phase1.md")
        phase3 = read("prompts/building/phase3.md")
        overrides = read("prompts/building/official-skill-overrides.md")
        email_rules = phase1[phase1.index("### Email-to-Case Rules"):phase1.index("<!-- /IF:EMAIL_TO_CASE -->")]
        self.assertIn("base Email-to-Case", email_rules)
        self.assertIn("--confirm-production", email_rules)
        self.assertIn("production-org confirmation required", email_rules)
        for agent_work in ("check-agent-email-capability.sh", "agentforce-generate", "service-agentforce-channel-configure"):
            self.assertNotIn(agent_work, email_rules)
        for rule in ("check-agent-email-capability.sh", "Exit 3", "other nonzero", "BLOCKED", "routingName",
                     "VERIFIED base Email-to-Case prerequisite", "manual channel assignment"):
            self.assertIn(rule, phase3)
        self.assertIn("never creates or modifies Agentforce agents and never assigns channels", overrides)

    def test_explicit_no_apex_and_the_bounded_backing_action_fallback(self):
        phase3 = " ".join(read("prompts/building/phase3.md").split())
        # 2.4.1: Scout 1.x's Showtime modes are gone; explicit no-Apex is the one rule that forbids the fallback.
        self.assertNotIn("Showtime", phase3)
        for rule in ("Explicit no-Apex is binding in every mode and never permits a backing Apex fallback",
                     "Explicit no-Apex forbids backing Apex even after failure",
                     "fallback is allowed only when BUILD_SCOPE names it, the approved spec names the exact Apex class/action",
                     "the frozen expected-work ledger already contains matching artifact/action obligations",
                     "Generic permission is insufficient",
                     "Record exact failure evidence from `sf agent validate` or `sf agent preview`",
                     "do not change the hero-action identity or expected state",
                     "FAILED with exact failure evidence"):
            self.assertIn(rule, phase3)
        self.assertNotIn('If the spec says "no Apex" and you deploy Apex', phase3)
        self.assertIn("no-Apex choice", read("prompts/building/direct-repair.md"))

    def test_scout_ships_only_its_own_skills(self):
        shipped = {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md") if path.is_file()}
        self.assertEqual(shipped, {"demo-deployment-rules", "demo-docs-consultation", "demo-org-audit", "sf-flow",
                                   "scout", "scout-setup"})  # 2.4: the two entry points are skills on every host


if __name__ == "__main__":
    unittest.main()
