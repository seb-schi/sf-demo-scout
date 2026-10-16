"""Static caller contracts for driving Salesforce's official skills; no model, org or network runs here."""
import json
import os
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERRIDES = "prompts/building/official-skill-overrides.md"
CHECKOUT = Path(os.environ.get("SCOUT_SF_SKILLS_CHECKOUT") or "/nonexistent-sf-skills-checkout") / "plugins/builder"


def read(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


def section(text, heading):
    match = re.search(rf"^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)", text, flags=re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError(f"missing section: {heading}")
    return match.group(1)


def materialize(reference, headings, plugin_root="/installed/scout"):
    first_heading = re.search(r"^## ", reference, flags=re.MULTILINE)
    blocks = [reference[: first_heading.start()].rstrip()]
    blocks.extend(f"## {heading}\n\n{section(reference, heading).strip()}" for heading in headings)
    return "\n\n".join(blocks).replace("${CLAUDE_PLUGIN_ROOT}", plugin_root)


class OverridesContractTests(unittest.TestCase):
    def setUp(self):
        self.reference = read(OVERRIDES)

    def test_sections_preamble_and_missing_dependency_authority(self):
        self.assertEqual(re.findall(r"^## (.+)$", self.reference, flags=re.MULTILINE), [
            "Readiness", "Missing-plugin repair", "Other official plugins", "The official hooks", "Binding and confirmation", "Flow scope",
            "Analyzer prerequisites", "Report tools", "Validation formulas", "FlexiPage scope", "Email-to-Case scope",
            "Agentforce prerequisites and precedence", "The action log", "Cross-plugin handoffs", "Hosts"])
        preamble = self.reference[: self.reference.index("## Readiness")]
        for phrase in ("always by their qualified names", "never Anthropic's copy", "overrides only what it names",
                       "scope, category permissions, retries, preservation and acceptance",
                       "A missing dependency is evidence to report", "never authorization to install",
                       "mark a check passed", "the missing-plugin repair below, after the SE's yes"):
            self.assertIn(phrase, preamble)

    def test_readiness_needs_session_evidence_and_blocks_by_name(self):
        readiness = section(self.reference, "Readiness")
        self.assertIn('scripts/scout_official.py" inspect --host [SCOUT_HOST] --launch-dir "[the folder this session started in, else the verified workspace]"` once per task', readiness)
        self.assertIn("join the bundled confirmation", readiness)
        self.assertIn("its qualified name is in your skill list", readiness)
        self.assertIn("`/reload-plugins`", readiness)
        self.assertIn('verify --host [SCOUT_HOST] --plugin <plugin> --skill-dir "<base directory>" --launch-dir "<the same folder as the inspection>"', readiness)
        self.assertIn("Anything but `verified` stops that item", readiness)
        for state in ("`setup-needed`", "`unknown`", "`conflict`", "`missing`", "`unsupported-host`"):
            self.assertIn(state, readiness)
        self.assertIn("Independent items proceed", readiness)
        self.assertIn('Before any inspection, worker dispatch, proposal or write in a build or repair', readiness)
        self.assertIn('copy it into every worker brief with the qualified names and resolved roots', readiness)

    def test_takeover_notes_never_block_and_project_files_stay_the_ses(self):
        readiness = section(self.reference, "Readiness")
        self.assertIn("`notes` never block", readiness)
        self.assertIn("`/scout-setup` can switch them to the latest", readiness)
        self.assertIn("Scout never changes project plugin selections", readiness)
        setup = read("prompts/setup/official-plugins.md")
        for phrase in ("with **one** question naming exactly what would change",
                       "which updates every plugin installed from it: <plugins>",
                       "with `--unpin <name>:<ref>` for each pinned line and `--disable-duplicates <id> …` naming each listed duplicate. Setup acts only on those.",
                       "Never offer to move or delete them", "Scout doesn't change project plugin selections",
                       "possible personal copies", "outside Scout's automatic updates", "--launch-dir \"[LAUNCH_DIR]\"",
                       "retry once, within the same approval, by rerunning the same command with `--unpin <name>`"):
            self.assertIn(phrase, setup)

    def test_first_need_install_is_named_approved_reloaded_and_resumed(self):
        install = section(self.reference, "Missing-plugin repair")
        self.assertIn("Otherwise this repairs one plugin that failed to install, was removed or was switched off", install)
        self.assertIn("the bundled confirmation names it in one line", install)
        self.assertIn("in any project, not only Scout's", install)
        self.assertIn("setup-official-plugins.py\" --host [SCOUT_HOST] --plugins <plugin>", install)
        self.assertIn("Record the task as waiting for the reload in the change log", install)
        self.assertIn("resume that same task only after readiness and coexistence pass again", install)
        self.assertIn("A decline or a failure leaves those items blocked", install)

    def test_an_se_without_the_plugins_gets_them_installed_on_one_yes(self):
        # Right after an update from 2.0, nothing is set up: /scout offers the install itself instead of sending
        # the SE to /scout-setup, then asks for the reload and resumes.
        install = section(self.reference, "Missing-plugin repair")
        self.assertIn("When the plugins aren't set up at all (`setup-needed`", install)
        self.assertIn("Shall I install them now? It takes about a minute, and they keep themselves up to date.", install)
        self.assertIn("run the two bash blocks of `prompts/setup/official-plugins.md`, as setup does", install)
        self.assertIn("a 10-minute timeout", install)
        self.assertIn("ask the SE to run `/reload-plugins`, and resume the same task once readiness passes", install)
        self.assertIn("A no leaves the build items blocked; read-only work goes on.", install)

    def test_other_plugins_are_offered_one_build_need_at_a_time(self):
        offer = section(self.reference, "Other official plugins")
        for phrase in ("`inspect` lists them under `optional`", "falls squarely in one of those areas",
                       "Salesforce has an official plugin for [area]: [plugin]. Want me to install it for this build?",
                       "as its own line with its own yes, and never one it doesn't need, just in case",
                       "declining blocks nothing", "Never offer `dx-org-lifecycle` or `salesforce-test-drive`"):
            self.assertIn(phrase, offer)
        table = section(self.reference, "Cross-plugin handoffs")
        for row in ("the same skill under `integration:` when that plugin is installed and verified",
                    "the same skill under `experience-react:` when that plugin is installed and verified"):
            self.assertIn(row, table)  # an accepted optional plugin is used, not reported as manual

    def test_the_official_hooks_are_followed_not_worked_around(self):
        hooks = section(self.reference, "The official hooks")
        for skill in ("salesforce-development:platform-soql-query", "salesforce-development:platform-data-manage",
                      "salesforce-development:platform-metadata-retrieve", "salesforce-development:platform-apex-test-run",
                      "salesforce-development:platform-manifest-generate"):
            self.assertIn(skill, hooks)
        self.assertIn("before the first such command in each turn and in each worker", hooks)
        self.assertIn("write the change log with the edit tools", hooks)
        self.assertIn("Before every deploy, Salesforce's plugin double-checks your default org", hooks)
        self.assertIn("Can I make [bound org] your default [for your project folder [folder] / on this computer]?", hooks)
        self.assertIn('the one exception to `commands/scout.md`\'s "Keep defaults … unchanged", and it needs an explicit yes', hooks)
        self.assertIn("run `sf config set target-org [bound username]` in the issue's `folder`", hooks)
        self.assertIn("with `--global` instead when the scope is `global`", hooks)
        self.assertIn("`SF_TARGET_ORG`, `SFDX_TARGET_ORG` or `SFDX_DEFAULTUSERNAME`", hooks)
        self.assertIn("On a no, change nothing", hooks)
        self.assertIn("With scope `environment`", hooks)
        self.assertNotIn("Scout never changes your default org", hooks)
        self.assertIn("ask once per task", hooks)
        self.assertIn("Only an explicit yes counts", hooks)
        self.assertIn("`CONFIRM_PROD=1` prefixed to that command only, never exported", hooks)
        self.assertIn("A deploy outside that scope asks again", hooks)
        self.assertIn("Destructive deploys stay blocked", hooks)
        self.assertNotRegex(hooks, r"(?i)I-CONFIRM-PROD|export CONFIRM_PROD|misclassif")
        self.assertIn("switch off `SFDX_AUTO_DEPLOY`", hooks)
        self.assertIn("never install from it without their yes", hooks)
        self.assertIn("Comply rather than work around them", hooks)

    def test_binding_and_confirmation_scope(self):
        binding = section(self.reference, "Binding and confirmation")
        self.assertIn("`--target-org [bound username]`, whatever a skill shows", binding)
        self.assertIn("satisfies only the approved target, action and delta", binding)
        self.assertIn("Preserve an incumbent description unless its replacement was approved", binding)
        self.assertIn("Delete, org-wide and billable approvals stay separate", binding)

    def test_flow_scope_uses_scouts_route_never_the_official_pipeline(self):
        flow = section(self.reference, "Flow scope")
        self.assertIn("never an official skill's own hosted pipeline", flow)
        self.assertIn("`sf-demo-scout:sf-flow`", flow)
        self.assertIn("maintained `sf-flow`", flow)
        self.assertIn("exact approved schema dependency", flow)
        self.assertIn("Flow-only", flow)
        self.assertIn("unrelated schema or agent", flow)
        self.assertIn("BLOCKED", flow)
        self.assertIn("required-test set, version, activation and rollback", flow)

    def test_analyzer_prefers_mcp_and_preserves_unavailable_scan_gap(self):
        analyzer = section(self.reference, "Analyzer prerequisites")
        self.assertLess(analyzer.index("`run_code_analyzer`"), analyzer.index("`salesforce-code-quality:dx-code-analyzer-run`"))
        for phrase in ("its own prerequisite checks succeed", "Do not delegate to an analyzer-configuration skill",
                       "do not install", "do not disable required engines", "preserve the exact failure and scan gap",
                       "scan not run/unverified", "acceptance unresolved"):
            self.assertIn(phrase, analyzer)
        self.assertNotIn("record the gap in `discovery_notes` and rely on the MCP scan", read("prompts/building/phase2.md"))

    def test_report_fallback_resolves_the_official_root_and_never_fabricates(self):
        reports = section(self.reference, "Report tools")
        self.assertIn("resolved `salesforce-development` root", reports)
        self.assertIn("skills/platform-report-generate/references/column-names.md", reports)
        self.assertNotIn("${CLAUDE_PLUGIN_ROOT}/skills/", reports)
        self.assertIn("Never fabricate tool calls", reports)
        self.assertIn("static mapping", reports)
        self.assertIn("live validation", reports)
        self.assertRegex(reports, r"Unknown columns.*BLOCKED before writing")
        for requirement in ("filter values", "filter logic", "ReportType", "folder", "read-back"):
            self.assertIn(requirement, reports)
        phase1 = read("prompts/building/phase1.md")
        report_rules = phase1[phase1.index("### Report Rules"): phase1.index("<!-- /IF:REPORTS -->")]
        self.assertIn("BLOCKED before writing", report_rules)

    def test_formula_flexipage_email_and_agentforce_scope(self):
        formulas = section(self.reference, "Validation formulas")
        for phrase in ("`ISCHANGE()`", "`ISCHANGED(field)`", "before deployment", "CDATA", "existing validation rules",
                       "literal strings"):
            self.assertIn(phrase, formulas)
        flexipage = section(self.reference, "FlexiPage scope")
        for phrase in ("whole RecordPages", "manual/App Builder", "never run the official FlexiPage generator",
                       "compatible field-section append", "confirmed page", "confirmed section", "read-back", "BLOCKED"):
            self.assertIn(phrase, flexipage)
        email = section(self.reference, "Email-to-Case scope")
        self.assertIn("resolved `service-engagement` root", email)
        self.assertIn("channel assignment stays manual", email)
        agentforce = section(self.reference, "Agentforce prerequisites and precedence")
        for phrase in ("Scout's orchestration", "global no-dependencies", "Scout caller override", "`sf agent`",
                       "`agentforce-adlc:agentforce-test`", "only if one is already available", "never install its SDK",
                       '"compiler not used"', "`sf agent preview start --help`",
                       "send: `--utterance`, `--session-id`, and `--authoring-bundle`",
                       "end: `--session-id` and `--authoring-bundle`", "published `--api-name` preview",
                       "PREVIEW_SIMULATION_UNAVAILABLE", "silently use `--use-live-actions`", "live-action fallback",
                       "not auth, license, runtime, or action readiness"):
            self.assertIn(phrase, agentforce)

    def test_every_attempt_logs_why_and_via(self):
        log = section(self.reference, "The action log")
        self.assertIn("`- why: <the item's criterion, or the beat it serves>`", log)
        self.assertIn("`- via: <the qualified skill, Scout helper or command that made the change>`", log)
        self.assertIn("with the edit tools", log)

    def test_codex_reads_only_an_explicit_checkout(self):
        hosts = section(self.reference, "Hosts")
        self.assertIn("BLOCKED by name", hosts)
        self.assertIn("`SCOUT_OFFICIAL_SKILLS_ROOT`", hosts)
        self.assertIn("never copying them", hosts)


class HandoffClosureTests(unittest.TestCase):
    """X4: every cross-plugin handoff in a skill Scout routes to has a destination in the handoff table."""

    def test_handoffs_in_the_pinned_checkout_are_all_mapped(self):
        if not CHECKOUT.is_dir():
            self.skipTest("no local sf-skills checkout")
        table = section(read(OVERRIDES), "Cross-plugin handoffs")
        mapped = set(re.findall(r"`([\w*-]+)`", table.split("---|---", 1)[1]))
        owners = {}
        for plugin in CHECKOUT.iterdir():
            for skill in (plugin / "skills").glob("*/SKILL.md") if (plugin / "skills").is_dir() else ():
                owners.setdefault(skill.parent.name, set()).add(plugin.name)
        names = re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, sorted(owners, key=len, reverse=True))) + r")(?![\w-])")
        routed = json.loads(read("assets/official-capabilities.json"))["capabilities"]
        unmapped = set()
        for spec in routed.values():
            for entry in spec.get("skills", []):
                plugin, _, skill = entry.partition(":")
                if plugin == "sf-demo-scout":
                    continue
                for path in (CHECKOUT / plugin / "skills" / skill).rglob("*.md"):
                    for name in set(names.findall(path.read_text(errors="ignore"))):
                        if plugin in owners[name]:
                            continue  # its own plugin's skill: the qualified name follows directly
                        if name not in mapped and not any(m.endswith("*") and name.startswith(m[:-1]) for m in mapped):
                            unmapped.add((skill, name))
        self.assertEqual(unmapped, set())


class RouteNameTests(unittest.TestCase):
    """Scout's files name official skills only by qualified names that exist, and never point into removed copies."""
    PLUGINS = ("salesforce-development", "salesforce-code-quality", "agentforce-adlc", "experience-lwc", "service-engagement")

    def files(self):
        for pattern in ("commands/*.md", "prompts/**/*.md", "AGENTS.md", "README.md", "docs/*.md", "skills/**/*.md",
                        "skills/sf-flow/hooks/scripts/*.py", "hooks/*", "scripts/*", "assets/**/*.json"):
            for path in ROOT.glob(pattern):
                if path.is_file():
                    yield path

    def test_qualified_names_exist_and_no_copy_is_referenced(self):
        qualified = re.compile(r"(?<![\w-])(%s|sf-demo-scout):([a-z][\w-]*)" % "|".join(self.PLUGINS))
        removed = re.compile(r"(?:\$\{CLAUDE_PLUGIN_ROOT\}|\[PLUGIN_ROOT_ABS\]|\.\.)/(?:skills/)?((?:platform|agentforce|experience|service|dx)-[\w-]+)")
        seen = set()
        for path in self.files():
            text = path.read_text(errors="ignore")
            for plugin, skill in qualified.findall(text):
                seen.add((plugin, skill))
            for name in removed.findall(text):
                self.assertTrue((ROOT / "skills" / name).is_dir(), f"{path.relative_to(ROOT)} points into a removed copy: {name}")
        self.assertGreater(len(seen), 20)
        for plugin, skill in sorted(seen):
            if plugin == "sf-demo-scout":
                self.assertTrue((ROOT / "skills" / skill / "SKILL.md").is_file(), skill)
        self.__class__.seen = seen

    def test_official_qualified_names_exist_in_the_checkout(self):
        if not CHECKOUT.is_dir():
            self.skipTest("SCOUT_SF_SKILLS_CHECKOUT not set: official names unchecked")
        qualified = re.compile(r"(?<![\w-])(%s):([a-z][\w-]*)" % "|".join(self.PLUGINS))
        names = {(plugin, skill) for path in self.files() for plugin, skill in qualified.findall(path.read_text(errors="ignore"))
                 if skill not in ("skills", "scripts")}  # asset paths in the capability map, checked by their own test
        self.assertGreater(len(names), 20)
        for plugin, skill in sorted(names):
            self.assertTrue((CHECKOUT / plugin / "skills" / skill / "SKILL.md").is_file(), f"{plugin}:{skill}")

    def test_no_bare_copied_names_remain_outside_the_handoff_table(self):
        bare = re.compile(r"(?<![\w:/.-])(platform-(?:apex|custom|data|flexipage|list|metadata|permission|report|sharing|soql|validation|value)[\w-]*"
                          r"|agentforce-(?:generate|test|observe)|experience-lwc-generate|dx-code-analyzer-run"
                          r"|service-email-to-case-configure)(?![\w-])")
        for path in self.files():
            if path.name in ("official-skill-overrides.md", "official-capabilities.json"):
                continue
            for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
                self.assertIsNone(bare.search(line), f"{path.relative_to(ROOT)}:{number}: {line.strip()[:120]}")


class ProductionGateTests(unittest.TestCase):
    """X15: the official prod-check gate, run from the pinned checkout with a stubbed `sf` that classifies the org as
    production. It shows that Scout's marker is command-local and that destructive deploys stay blocked."""

    def setUp(self):
        self.gate = CHECKOUT / "salesforce-development/scripts/sf-deploy-gate"
        if not self.gate.is_file():
            self.skipTest("no local sf-skills checkout")
        import tempfile
        temp = tempfile.TemporaryDirectory(prefix="scout-prod-gate-")
        self.addCleanup(temp.cleanup)
        self.bin = Path(temp.name)
        record = {"alias": "demo", "username": "admin@demo.example", "orgId": "00D000000000001",
                  "instanceUrl": "https://acme.my.salesforce.com", "isSandbox": False, "isScratch": False}
        (self.bin / "sf").write_text("#!/bin/sh\necho '%s'\n" % json.dumps({"status": 0, "result": {"nonScratchOrgs": [record]}}))
        (self.bin / "sf").chmod(0o700)

    def decide(self, command):
        import subprocess
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        env = {"PATH": "%s:/usr/bin:/bin" % self.bin, "HOME": str(self.bin)}
        result = subprocess.run(["/bin/bash", str(self.gate), "prod-check"], input=payload, capture_output=True,
                                text=True, env=env, timeout=60)
        output = json.loads(result.stdout.strip().splitlines()[-1])
        return output.get("hookSpecificOutput", {}).get("permissionDecision", "allow")

    def test_the_marker_is_command_local_and_destructive_deploys_stay_blocked(self):
        deploy = "sf project deploy start --source-dir force-app --target-org admin@demo.example --json"
        self.assertEqual(self.decide(deploy), "deny")
        self.assertEqual(self.decide("CONFIRM_PROD=1 " + deploy), "allow")
        self.assertEqual(self.decide("sf project deploy validate --source-dir force-app --target-org admin@demo.example"),
                         "allow")  # check-only is never gated
        destructive = "CONFIRM_PROD=1 sf project deploy start --manifest package.xml --post-destructive-changes destructiveChanges.xml --target-org admin@demo.example"
        self.assertEqual(self.decide(destructive), "deny")


class LwcHookScopeTests(unittest.TestCase):
    """X9: the install line's disclosure is true: the LWC plugin's Write/Edit hook validates an HTML file in a folder
    that's no Salesforce project, and probes its linter through npx (stubbed here)."""

    def test_the_validator_runs_outside_any_project(self):
        plugin = CHECKOUT / "experience-lwc"
        script = plugin / "skills/experience-lwc-generate/scripts/post-tool-validate.py"
        if not script.is_file():
            self.skipTest("no local sf-skills checkout")
        import subprocess
        import sys
        import tempfile
        with tempfile.TemporaryDirectory(prefix="scout-lwc-hook-") as temp:
            root = Path(temp)
            (root / "bin").mkdir()
            (root / "bin/npx").write_text("#!/bin/sh\necho \"$*\" >> \"%s/calls.log\"\nexit 1\n" % root)
            (root / "bin/npx").chmod(0o700)
            (root / "elsewhere").mkdir()
            (root / "elsewhere/index.html").write_text("<html><body><div>hi</div></body></html>\n")
            payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(root / "elsewhere/index.html")}})
            result = subprocess.run([sys.executable, "-I", str(script)], input=payload, capture_output=True, text=True,
                                    env={"PATH": "%s/bin:/usr/bin:/bin" % root, "HOME": str(root),
                                         "CLAUDE_PLUGIN_ROOT": str(plugin)}, timeout=120)
            self.assertIn("SLDS 2 Validation: index.html", json.loads(result.stdout)["output"])
            self.assertIn("slds-linter", (root / "calls.log").read_text())
        self.assertIn('"matcher": "Write|Edit"', (plugin / ".claude-plugin/plugin.json").read_text())


class MarketplaceMapTests(unittest.TestCase):
    """The map names every plugin in Salesforce's marketplace: installed at setup, offered for an area, or excluded."""

    def test_every_marketplace_plugin_has_a_decision(self):
        data = json.loads(read("assets/official-capabilities.json"))
        for name, spec in data["plugins"].items():
            self.assertTrue(spec.get("setup") or spec.get("offer") or spec.get("excluded"), name)
        self.assertEqual({n for n, s in data["plugins"].items() if s.get("setup")},
                         {"salesforce-development", "salesforce-code-quality", "agentforce-adlc", "experience-lwc",
                          "service-engagement"})
        manifest = CHECKOUT.parent.parent / ".claude-plugin/marketplace.json"
        if not manifest.is_file():
            self.skipTest("SCOUT_SF_SKILLS_CHECKOUT not set: marketplace coverage unchecked")
        upstream = {p["name"] for p in json.loads(manifest.read_text())["plugins"]}
        self.assertEqual(set(data["plugins"]), upstream)  # a new upstream plugin needs a decision here


class CallerTests(unittest.TestCase):
    def test_scout_and_direct_repair_run_readiness_before_writing(self):
        command = read("commands/scout.md")
        pointer = command.index('First follow `${CLAUDE_PLUGIN_ROOT}/prompts/building/official-skill-overrides.md` §"Readiness", '
                                'before inspection, delegation, proposals or writes.')
        for later in ('skills/demo-org-audit/SKILL.md` for scoped inspection', 'Delegate read-only research/inspection'):
            self.assertLess(pointer, command.index(later), later)  # F8: readiness and the hooks precede inspection and workers
        repair = read("prompts/building/direct-repair.md")
        self.assertLess(repair.index("official-skill-overrides.md"), repair.index("Resolve the installed supported skill/tool"))
        self.assertIn('Run its §"Readiness" inspection before any', repair)
        self.assertRegex(repair, r"only the\s+applicable named overrides")
        self.assertIn("absolute installed paths", repair)
        self.assertIn("otherwise do not load", repair)
        hosted = read("prompts/scout/hosted-flow.md")
        self.assertIn('§"Readiness"', hosted)
        self.assertNotIn("coexistence --host", hosted)

    def test_classic_materialization_keeps_the_hooks_and_selected_sections(self):
        command = read("prompts/classic/scout-building.md")
        reference = read(OVERRIDES)
        self.assertIn("prompts/building/official-skill-overrides.md", command)
        phase1_row = next(line for line in command.splitlines() if line.startswith("     | Phase 1 |"))
        selected = [h for h, condition in re.findall(r"`([^`]+)` for ([^,|]+)", phase1_row) if condition.strip() == "Reports"]
        self.assertEqual(["Report tools"], selected)
        materialized = materialize(reference, ["The official hooks", "Binding and confirmation", *selected])
        self.assertIn("## Report tools", materialized)
        self.assertNotIn("## FlexiPage scope", materialized)
        for heading in ("Report tools", "Validation formulas", "FlexiPage scope", "Email-to-Case scope", "Flow scope",
                        "Analyzer prerequisites", "Agentforce prerequisites and precedence", "The official hooks"):
            self.assertIn(heading, command)
        for phase in ("phase1.md", "phase2.md", "phase3.md"):
            template = read(f"prompts/building/{phase}")
            self.assertEqual(1, template.count("{{VENDOR_COMPATIBILITY}}"))


if __name__ == "__main__":
    unittest.main()
