import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


class RoutingAndScopeContractTests(unittest.TestCase):
    """Static source-contract checks; these do not prove live model or org behavior."""

    def test_phase_selection_uses_the_complete_phase_input_table(self):
        command = read("commands/scout-building.md")
        phase1 = read("prompts/building/phase1.md")
        analysis = command[
            command.index("### Phase Analysis") : command.index(
                "### Settle Calibration and Freeze"
            )
        ]
        phase1_row = next(
            line
            for line in command.splitlines()
            if line.startswith("| 1 | `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md`")
        )
        expected_tags = {
            "QUEUES",
            "LAYOUTS",
            "LRP",
            "PERMSET",
            "STRUCTURAL",
            "PICKLISTS",
            "DATA_SEEDING",
            "BUSINESS_PROCESS",
            "PATHS",
            "VALIDATION_RULES",
            "LIST_VIEWS",
            "SHARING_RULES",
            "CUSTOM_REPORT_TYPE",
            "REPORTS",
            "CUSTOM_SETTING",
            "CUSTOM_METADATA_TYPE",
            "EMAIL_TO_CASE",
        }
        self.assertEqual(
            expected_tags,
            set(re.findall(r"<!-- IF:([A-Z_]+) -->", phase1)),
        )
        for tag in expected_tags:
            with self.subTest(tag=tag):
                self.assertIn(tag, phase1_row)
        self.assertIn("authoritative phase-input table", analysis)
        self.assertIn("concrete approved work", analysis)
        self.assertNotIn("Only safe operations", analysis)
        phase2_row = next(
            line
            for line in command.splitlines()
            if line.startswith("| 2 | `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase2.md`")
        )
        spec = read("prompts/spec-template.md")
        for heading, tag in (
            ("Flows", "FLOWS"),
            ("Screen Flows", "FLOWS"),
            ("Apex", "APEX"),
            ("LWC Components", "LWC"),
        ):
            with self.subTest(heading=heading):
                self.assertIn(f"### {heading}", spec)
                self.assertIn(f"`{tag}`", phase2_row)
                self.assertIn(heading, phase2_row)

    def test_email_agent_work_is_phase3_only_and_channel_wiring_fails_closed(self):
        command = read("commands/scout-building.md")
        phase1 = read("prompts/building/phase1.md")
        phase3 = read("prompts/building/phase3.md")
        skill = read("skills/service-email-to-case-configure/SKILL.md")
        spec = read("prompts/spec-template.md")

        email_rules = phase1[
            phase1.index("### Email-to-Case Rules") : phase1.index("<!-- /IF:EMAIL_TO_CASE -->")
        ]
        self.assertNotIn("check-agent-email-capability.sh", email_rules)
        self.assertNotIn("agentforce-generate", email_rules)
        self.assertNotIn("service-agentforce-channel-configure", email_rules)
        self.assertIn("base Email-to-Case", email_rules)

        for text in (command, phase3):
            self.assertIn("check-agent-email-capability.sh", text)
            self.assertIn("Exit 3", text)
            self.assertIn("other nonzero", text)
            self.assertIn("BLOCKED", text)
            self.assertIn("routingName", text)
        self.assertIn("absolute", command)
        self.assertIn("exact skill is installed", command)
        self.assertIn("explicitly\napproved", command)
        self.assertIn("probe command and exit/result", command)
        self.assertIn("base Email-to-Case prerequisite status", command)
        self.assertIn("VERIFIED base Email-to-Case prerequisite", phase3)
        self.assertEqual(1, phase3.count("{{PRIOR_PHASES_SUMMARY}}"))
        self.assertIn("manual channel assignment", phase3)
        self.assertIn("never creates or modifies Agentforce agents", skill)
        self.assertIn("--confirm-production", email_rules)
        self.assertIn("production-org confirmation required", email_rules)
        self.assertIn("Base Email-to-Case", spec)
        self.assertIn("exact Agent API name", spec)

    def test_sparring_uses_exact_scout_skill_membership_and_provenance(self):
        sparring = read("commands/scout-sparring.md")
        shipped = {
            path.parent.name
            for path in (ROOT / "skills").glob("*/SKILL.md")
            if path.is_file()
        }
        self.assertIn("service-email-to-case-configure", shipped)
        self.assertNotIn("service-agentforce-channel-configure", shipped)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/skills/*/SKILL.md", sparring)
        self.assertIn("provider/path provenance", sparring)
        self.assertIn("same basename", sparring)
        self.assertIn("another plugin", sparring)
        self.assertIn("unknown", sparring)
        self.assertNotIn("six name families", sparring)
        self.assertNotIn("Judge by family", sparring)

    def test_build_scope_is_injected_verbatim_and_controls_every_execution_stage(self):
        command = read("commands/scout-building.md")
        for name in ("phase1.md", "phase2.md", "phase3.md"):
            with self.subTest(name=name):
                self.assertIn("{{BUILD_SCOPE}}", read(f"prompts/building/{name}"))
        self.assertIn("`{{BUILD_SCOPE}}` (all three phases)", command)
        for field in (
            "Mode:",
            "Showtime envelope(s):",
            "Applicable envelope limits/prerequisites:",
            "Approved executable slice:",
            "Hard exclusions:",
            "Ordinary-build Apex fallback authorization:",
        ):
            with self.subTest(field=field):
                self.assertIn(field, command)
        for stage in ("selection", "ledger", "staging", "dispatch", "retry", "return review"):
            with self.subTest(stage=stage):
                self.assertIn(stage, command)
        self.assertIn("verbatim", command)

    def test_showtime_scope_never_defaults_to_ordinary(self):
        command = read("commands/scout-building.md")
        showtime = read("prompts/sparring/showtime.md")
        spec = read("prompts/spec-template.md")
        self.assertIn("any Showtime marker or Showtime PoC evidence", command)
        self.assertIn("missing or ambiguous", command)
        self.assertIn("contradictory", command)
        self.assertIn("blocks affected execution", command)
        self.assertIn("Showtime envelope", showtime)
        self.assertIn("Hard exclusions", showtime)
        self.assertIn("Ordinary-build Apex fallback authorization", spec)

    def test_no_apex_and_fallback_authority_are_explicit_and_ledger_bound(self):
        command = read("commands/scout-building.md")
        phase3 = read("prompts/building/phase3.md")
        for text in (command, phase3):
            self.assertIn("Explicit no-Apex", text)
            self.assertIn("Showtime E4", text)
            self.assertIn("Showtime E3", text)
            self.assertIn("E3 never selects Phase 3", text)
            self.assertIn("exact failure evidence", text)
            self.assertIn("frozen expected-work ledger", text)
            self.assertIn("hero-action identity", text)
            self.assertIn("FAILED with exact failure evidence", text)
        self.assertNotIn("If the spec says \"no Apex\" and you deploy Apex", phase3)
        self.assertNotIn("Spec forbids Apex backing actions. If the sub-agent hits", command)


if __name__ == "__main__":
    unittest.main()
