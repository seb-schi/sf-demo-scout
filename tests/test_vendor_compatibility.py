import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


def section(text, heading):
    match = re.search(
        rf"^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing section: {heading}")
    return match.group(1)


def materialize(reference, headings, plugin_root="/installed/scout"):
    first_heading = re.search(r"^## ", reference, flags=re.MULTILINE)
    if first_heading is None:
        raise AssertionError("reference has no named sections")
    blocks = [reference[: first_heading.start()].rstrip()]
    blocks.extend(f"## {heading}\n\n{section(reference, heading).strip()}" for heading in headings)
    return "\n\n".join(blocks).replace("${CLAUDE_PLUGIN_ROOT}", plugin_root)


class VendorCompatibilityContractTests(unittest.TestCase):
    """Static caller contracts only; these tests do not execute a model or Salesforce."""

    def test_reference_limits_precedence_and_missing_dependency_authority(self):
        reference = read("prompts/building/vendor-compatibility.md")
        headings = re.findall(r"^## (.+)$", reference, flags=re.MULTILINE)
        self.assertEqual(
            [
                "Flow handoffs",
                "Analyzer prerequisites",
                "Report tools",
                "Validation formulas",
                "FlexiPage scope",
                "Agentforce prerequisites and precedence",
            ],
            headings,
        )
        preamble = reference[: reference.index("## Flow handoffs")]
        self.assertIn("only the named vendor conflicts", preamble)
        self.assertIn("scope, category permissions, retries, preservation, and acceptance", preamble)
        self.assertIn("Missing dependency is evidence to report", preamble)
        self.assertIn("never authorization to install", preamble)
        self.assertIn("mark a check passed", preamble)

    def test_flow_handoffs_map_bundled_routes_without_widening_phase_scope(self):
        flow = section(read("prompts/building/vendor-compatibility.md"), "Flow handoffs")
        self.assertIn("`sf-metadata`", flow)
        self.assertIn("`platform-custom-object-generate`", flow)
        self.assertIn("`platform-custom-field-generate`", flow)
        self.assertIn("`sf-ai-agentscript`", flow)
        self.assertIn("`agentforce-generate`", flow)
        self.assertIn("exact approved schema dependency", flow)
        self.assertIn("Flow-only", flow)
        self.assertIn("unrelated schema or agent work", flow)
        self.assertIn("BLOCKED", flow)
        self.assertIn("test, version, activation, and rollback", flow)

    def test_analyzer_prefers_mcp_and_preserves_unavailable_scan_gap(self):
        analyzer = section(
            read("prompts/building/vendor-compatibility.md"), "Analyzer prerequisites"
        )
        self.assertLess(analyzer.index("`run_code_analyzer`"), analyzer.index("`dx-code-analyzer-run`"))
        self.assertIn("its own prerequisite checks succeed", analyzer)
        self.assertIn("Do not delegate to absent `configuring-code-analyzer`", analyzer)
        self.assertIn("do not install", analyzer)
        self.assertIn("preserve the exact failure and scan gap", analyzer)
        self.assertIn("scan not run/unverified", analyzer)
        self.assertIn("acceptance unresolved", analyzer)

        phase2 = read("prompts/building/phase2.md")
        self.assertNotIn("record the gap in `discovery_notes` and rely on the MCP scan", phase2)

    def test_report_fallback_never_fabricates_tools_or_unknown_columns(self):
        reports = section(read("prompts/building/vendor-compatibility.md"), "Report tools")
        self.assertIn("platform-report-generate/references/column-names.md", reports)
        self.assertIn("Phase 1", reports)
        self.assertIn("never fabricate", reports.lower())
        self.assertIn("static mapping", reports)
        self.assertIn("live validation", reports)
        self.assertRegex(reports, r"Unknown columns.*BLOCKED.*before writing")
        for requirement in ("filter values", "filter logic", "ReportType", "folder", "read-back"):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, reports)

        phase1 = read("prompts/building/phase1.md")
        report_rules = phase1[
            phase1.index("### Report Rules") : phase1.index("<!-- /IF:REPORTS -->")
        ]
        self.assertIn("BLOCKED before writing", report_rules)
        prereq_rule = report_rules[report_rules.index("2. **MCP note") : report_rules.index("3. **Folder")]
        self.assertNotIn("`FAILED`", prereq_rule)

    def test_formula_and_flexipage_overrides_keep_semantics_and_supported_scope(self):
        reference = read("prompts/building/vendor-compatibility.md")
        formulas = section(reference, "Validation formulas")
        self.assertIn("`ISCHANGE()`", formulas)
        self.assertIn("`ISCHANGED(field)`", formulas)
        self.assertIn("before deployment", formulas)
        self.assertIn("CDATA", formulas)
        self.assertIn("existing validation rules", formulas)
        self.assertIn("literal strings", formulas)

        flexipage = section(reference, "FlexiPage scope")
        self.assertIn("whole RecordPages", flexipage)
        self.assertIn("manual/App Builder", flexipage)
        self.assertIn("compatible field-section append", flexipage)
        self.assertIn("confirmed page", flexipage)
        self.assertIn("confirmed section", flexipage)
        self.assertIn("read-back", flexipage)
        self.assertIn("BLOCKED", flexipage)

        phase1 = read("prompts/building/phase1.md")
        self.assertIn("`ISCHANGE()`", phase1)
        self.assertIn("`ISCHANGED(field)`", phase1)
        self.assertNotIn(
            "`platform-flexipage-generate` — Lightning Page (FlexiPage) authoring rules",
            phase1,
        )

    def test_agentforce_readiness_is_mode_specific_and_keeps_canonical_evidence(self):
        agentforce = section(
            read("prompts/building/vendor-compatibility.md"),
            "Agentforce prerequisites and precedence",
        )
        self.assertIn("Scout's orchestration", agentforce)
        self.assertIn("global no-dependencies", agentforce)
        self.assertIn("Scout caller override", agentforce)
        self.assertIn("Phase 3", agentforce)
        self.assertIn("metadata MCP", agentforce)
        self.assertIn("`sf agent`", agentforce)
        self.assertIn("`agentforce-test`", agentforce)
        self.assertIn("`sf --version`", agentforce)
        self.assertIn("`sf agent preview start --help`", agentforce)
        self.assertIn("exit 0", agentforce)
        for flag in ("`--authoring-bundle`", "`--simulate-actions`", "`--use-live-actions`"):
            with self.subTest(flag=flag):
                self.assertIn(flag, agentforce)
        self.assertIn("selected send/end command help", agentforce)
        self.assertIn("send: `--utterance`, `--session-id`, and `--authoring-bundle`", agentforce)
        self.assertIn("end: `--session-id` and `--authoring-bundle`", agentforce)
        self.assertIn("start with `--authoring-bundle` and `--simulate-actions`", agentforce.lower())
        self.assertIn("published `--api-name` preview", agentforce)
        self.assertIn("executes real actions", agentforce)
        self.assertIn("2.130.9", agentforce)
        self.assertIn("numeric version alone", agentforce)
        self.assertIn("PREVIEW_SIMULATION_UNAVAILABLE", agentforce)
        self.assertIn("silently use `--use-live-actions`", agentforce)
        self.assertIn("live-action fallback", agentforce)
        self.assertIn("Mode B", agentforce)
        self.assertIn("separately", agentforce)
        self.assertIn("canonical evidence", agentforce)
        self.assertIn("help proves", agentforce)
        self.assertIn("not auth, license, runtime, or action readiness", agentforce)

    def test_report_only_materialization_excludes_unselected_sections_and_resolves_paths(self):
        command = read("commands/scout-building.md")
        reference = read("prompts/building/vendor-compatibility.md")
        phase1_row = next(
            line for line in command.splitlines() if line.startswith("     | Phase 1 |")
        )
        routes = re.findall(r"`([^`]+)` for ([^,|]+)", phase1_row)
        selected = [heading for heading, condition in routes if condition.strip() == "Reports"]
        self.assertEqual(["Report tools"], selected)

        materialized = materialize(reference, selected)
        self.assertIn("## Report tools", materialized)
        self.assertIn("/installed/scout/skills/platform-report-generate/references/column-names.md", materialized)
        self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", materialized)
        all_headings = re.findall(r"^## (.+)$", reference, flags=re.MULTILINE)
        for excluded in (heading for heading in all_headings if heading not in selected):
            with self.subTest(excluded=excluded):
                self.assertNotIn(f"## {excluded}", materialized)

    def test_orchestrator_materializes_selected_sections_into_every_phase(self):
        command = read("commands/scout-building.md")
        self.assertIn("prompts/building/vendor-compatibility.md", command)
        self.assertIn("common preamble plus only", command)
        for selection in (
            "Phase 1",
            "Report tools",
            "Validation formulas",
            "FlexiPage scope",
            "Phase 2",
            "Flow handoffs",
            "Analyzer prerequisites",
            "Phase 3",
            "Agentforce prerequisites and precedence",
        ):
            with self.subTest(selection=selection):
                self.assertIn(selection, command)
        self.assertIn("absolute installed paths", command)
        self.assertIn("no unresolved plugin-root", command)

        for phase in ("phase1.md", "phase2.md", "phase3.md"):
            with self.subTest(phase=phase):
                template = read(f"prompts/building/{phase}")
                self.assertEqual(1, template.count("{{VENDOR_COMPATIBILITY}}"))
                self.assertLess(
                    template.index("{{VENDOR_COMPATIBILITY}}"),
                    template.index("## Skills Available"),
                )
                row = next(
                    line
                    for line in command.splitlines()
                    if line.startswith(
                        f"| {phase[5]} | `${{CLAUDE_PLUGIN_ROOT}}/prompts/building/{phase}`"
                    )
                )
                self.assertIn("{{VENDOR_COMPATIBILITY}}", row)

    def test_direct_repair_reads_shared_contract_before_vendor_resolution(self):
        repair = read("prompts/building/direct-repair.md")
        reference_read = repair.index("vendor-compatibility.md")
        vendor_resolution = repair.index("Resolve the installed supported skill/tool")
        self.assertLess(reference_read, vendor_resolution)
        self.assertIn("common preamble", repair)
        self.assertRegex(repair, r"only the\s+applicable named sections")
        self.assertIn("absolute installed paths", repair)
        self.assertIn("approved Agentforce repair", repair)
        self.assertIn("phase3.md", repair)
        self.assertIn("agentforce-validation-gate.md", repair)
        self.assertIn("otherwise do not load", repair)


if __name__ == "__main__":
    unittest.main()
