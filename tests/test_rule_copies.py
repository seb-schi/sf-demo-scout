"""Where Scout states one rule in several files, the copies agree, and the stale copies a newer file overruled are gone.

Static text checks only; they don't prove model compliance or org behaviour.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


class FlowCopiesTests(unittest.TestCase):
    """2.4.1, the limits review: screen-flow caps, a component whitelist, "fail twice" and orchestration flows sent
    to the checklist survived in older copies after phase2.md's rules had decided otherwise."""
    COPIES = ("AGENTS.md", "skills/demo-deployment-rules/SKILL.md", "prompts/building/phase2.md",
              "skills/demo-docs-consultation/SKILL.md", "prompts/building/handover-brief.md", "README.md")

    def test_no_copy_keeps_a_screen_cap_a_whitelist_or_fail_twice(self):
        stale = re.compile(r"(?i)three linear screens|five with builder justification|whitelist|fails? twice"
                           r"|terminal DML|out of autonomous scope|not demo-day-viable|scope down to")
        for path in self.COPIES:
            with self.subTest(path=path):
                self.assertIsNone(stale.search(read(path)))

    def test_screen_flows_deploy_draft_for_visual_qa_in_every_copy(self):
        rules = read("AGENTS.md")
        for phrase in ("Screen flows, any screens and components", "Draft first, activated after visual QA on the builder's yes",
                       "classic layout arrangements, record page edits, screen flows, dashboards and orchestration runtime"):
            self.assertTrue(phrase in rules, phrase)
        deploy = read("skills/demo-deployment-rules/SKILL.md")
        self.assertIn("with any number of screens and any screen component", deploy)
        self.assertIn('prompts/building/phase2.md` §"Flow Rules" decides each Flow\'s validation', deploy)
        self.assertIn("unless the story needs a save between screens", deploy)
        phase2 = read("prompts/building/phase2.md")
        self.assertIn("Screen-flow logic complexity remains in scope", phase2)
        self.assertIn("a visual-QA requirement is not an authoring prohibition", phase2)

    def test_one_orchestration_rule_and_one_flowtest_repair_rule(self):
        deploy = read("skills/demo-deployment-rules/SKILL.md")
        self.assertIn("docs-confirmed orchestration metadata", deploy)
        self.assertIn("A live orchestration run creates work items, so it runs only on the builder's yes", deploy)
        self.assertIn("docs-confirmed orchestration metadata", read("prompts/building/phase2.md"))
        self.assertIn("orchestration runtime", read("AGENTS.md"))  # deployed, then visual QA
        self.assertIn("Orchestration flows (deployed; you validate the lifecycle)", read("README.md"))
        self.assertIn("Repair a failure as `building/phase2.md` Flow Rules step 4 says", deploy)
        self.assertIn("Never activate a Flow that failed its own test", deploy)


class StaleWordingTests(unittest.TestCase):
    """2.4.1: dated instructions in passing: MCP-era tool lines, numeric Docs budgets, an old API version, and Scout
    1.x stages and modes."""
    PHASES = tuple("prompts/building/phase%d.md" % n for n in (1, 2, 3))

    def test_phase_prompts_use_the_cli_and_the_docs_floor(self):
        for path in self.PHASES:
            with self.subTest(path=path):
                text = read(path)
                self.assertIn("Use the `sf` CLI for every org operation, always with `--target-org {{ORG_ALIAS}}`", text)
                self.assertIn("never rely on a default org or call an MCP org tool", text)
                for stale in ("Use MCP tools", "Keep using MCP", "faster and richer", "get_username",
                              "not for pre-flight checks"):
                    self.assertNotIn(stale, text)
        for path in self.PHASES[:2]:
            self.assertIn("consult it before the first write of a new metadata type, for an ungrounded assumption "
                          "and on an unfamiliar error", read(path))

    def test_docs_consultation_has_no_dated_budget(self):
        docs = read("skills/demo-docs-consultation/SKILL.md")
        self.assertIn("## How Much to Consult", docs)
        self.assertIn("No count applies", docs)
        self.assertIn("a search snippet isn't evidence", docs)
        self.assertIn('§"Ground design and claims" sets that floor', docs)
        for stale in ("Budget Guidance", "consultations for new scenarios", "0 consultations is the happy path",
                      "Stage 4", "Stage 6", "in the spec"):
            self.assertNotIn(stale, docs)
        self.assertNotIn("overrides budgets", read("prompts/scout/router-build.md"))

    def test_templates_take_the_projects_api_version(self):
        phase2 = read("prompts/building/phase2.md")
        self.assertNotIn("<apiVersion>62.0</apiVersion>", phase2)
        self.assertEqual(phase2.count("<apiVersion>[SOURCE_API_VERSION]</apiVersion>"), 2)
        self.assertEqual(phase2.count("is the `sourceApiVersion` in the writer project's `sfdx-project.json`"), 2)

    def test_no_scout_1_stage_or_mode_words_in_the_rules(self):
        rules = read("AGENTS.md")
        for stale in ("sparring Stage", "Stage 4/6", "Stage 5", "external-skills gate", "in the spec"):
            self.assertFalse(stale in rules, stale)
        self.assertNotIn("Showtime", read("prompts/building/phase3.md"))
        self.assertNotIn("Two-attempt failures", read("prompts/lessons-maintenance.md"))




class SmallEasesTests(unittest.TestCase):
    """2.4.1, the limits review: limits written for weaker models ease where Scout can do the step itself, with no new
    capability; the safety and consent limits stay."""

    def test_scheduled_and_platform_event_flows_need_no_builder_homework(self):
        rules = read("AGENTS.md")
        self.assertIn("propose the schedule (`<startDate>`, `<startTime>`, `<frequency>`) in the bundled confirmation", rules)
        self.assertIn("check that `<eventType>` exists in the org or ships in this build; ask only when neither holds", rules)
        deploy = read("skills/demo-deployment-rules/SKILL.md")
        self.assertIn("the bundled confirmation proposes `<startDate>`", deploy)
        self.assertIn("Ask the builder only when it's absent and not planned", deploy)
        self.assertIn("read back the deployed `<schedule>` block", deploy)
        phase2 = read("prompts/building/phase2.md")
        self.assertIn("that the bundled confirmation proposed and the builder accepted", phase2)
        self.assertIn("so the orchestrator can propose it or ask the builder", phase2)
        for text in (rules, deploy, phase2):
            for stale in ("the builder must add to spec", "have the builder confirm", "Spec must provide",
                          "the builder must create or import first"):
                self.assertFalse(stale in text, stale)

    def test_the_check_in_at_ten_never_raises_an_official_cap(self):
        cap = "but never an official skill's cap on an org-wide or permanent step"
        self.assertIn(cap, read("AGENTS.md"))
        for n in (1, 2, 3):
            self.assertIn(cap, read("prompts/building/phase%d.md" % n))
        deploy = " ".join(read("skills/demo-deployment-rules/SKILL.md").split())
        self.assertIn("never raises an official skill's own cap on an org-wide or permanent step", deploy)
        self.assertIn("A worker that can't ask returns both to its orchestrator, which asks", deploy)
        phase2 = read("prompts/building/phase2.md")
        self.assertIn("a check-in with the builder every ten, while each fixes something new", phase2)
        self.assertIn("a check-in with the builder every ten test runs for the item", phase2)

    def test_scheduled_and_platform_event_flows_follow_what_the_platform_offers(self):
        # A schedule-triggered flow offers Once, Daily or Weekly; a platform-event-triggered flow has no FlowTest.
        for path in ("skills/demo-deployment-rules/SKILL.md", "prompts/building/phase2.md"):
            text = read(path)
            self.assertIn("Once, Daily or Weekly, what a schedule-triggered flow offers", text, path)
            for stale in ("Monthly / Yearly", "Hourly / Weekdays"):
                self.assertNotIn(stale, text, path)
        deploy = read("skills/demo-deployment-rules/SKILL.md")
        self.assertNotIn("mock event payload", deploy)
        self.assertIn("No FlowTest: platform-event-triggered flows deploy as Draft for visual QA", deploy)

    def test_one_lwc_rule_with_its_signals(self):
        self.assertIn("- LWC, one component or several, via `experience-lwc:experience-lwc-generate`: Code Analyzer, a dry "
                      "run, read-back and any Jest tests the project runs, then visual QA.", read("AGENTS.md"))
        for path in ("skills/demo-deployment-rules/SKILL.md", "prompts/building/phase2.md"):
            text = " ".join(read(path).split())
            self.assertIn("one component or several, under one rule; no size or complexity label decides anything", text)
            self.assertIn("Jest tests where the project already runs Jest", text)
        stale = re.compile(r"(?i)simple demo-specific LWC|complex/multi-component LWC|complex LWC|Complex / multi-component")
        for path in ("AGENTS.md", "README.md", "skills/demo-deployment-rules/SKILL.md", "prompts/building/phase2.md"):
            self.assertIsNone(stale.search(read(path)), path)

    def test_agent_identity_fields_and_the_model_are_scouts_to_set(self):
        gate = " ".join(read("prompts/building/agentforce-validation-gate.md").split())
        self.assertIn("set it in the `.agent` config", gate)
        self.assertIn("republish through the same publish path, activate the new version and read both fields back", gate)
        self.assertNotIn("the builder must hand-fill them", gate)
        phase3 = " ".join(read("prompts/building/phase3.md").split())
        self.assertNotIn("hand-fill", phase3)
        self.assertIn("If a read-back after publish still finds either blank, set it and republish", phase3)
        self.assertIn("Agent Script's `model_config` block, which Scout authors", phase3)
        deploy = read("skills/demo-deployment-rules/SKILL.md")
        self.assertIn("it's Agent Script's `model_config` block", deploy)
        for text in (phase3, deploy):
            self.assertNotRegex(text, r"(?i)- Custom model ?/ ?LLM config")

    def test_no_fresh_session_by_default_and_one_item_per_deploy(self):
        rules = read("AGENTS.md")
        self.assertIn("Keep the task record and change log current, so a compaction or a new session can resume.", rules)
        self.assertNotIn("start a fresh session", rules)
        phase2 = read("prompts/building/phase2.md")
        self.assertIn("one item per deploy, with the components it can't land without", phase2)
        self.assertNotIn("One component per deploy call", phase2)


class RecordPageCopiesTests(unittest.TestCase):
    """2.4.1, the limits review: additive edits to an existing record page go through Salesforce's page skill, with
    one convergence rule, and every copy of the rule says so. The old append-only-fields limit came from weaker
    executors without org grounding."""
    SKILL = "`salesforce-development:platform-flexipage-generate`"
    UNGROUNDED = re.compile(r"(?i)nothing ungrounded is written|write nothing ungrounded")
    SECOND = re.compile(r"(?i)a second (?:such )?rejection(?: on the same page)? stops the edit")
    THREE = "at most three dry runs"
    NEW_PAGE = re.compile(r"(?i)new (?:record )?page(?: from scratch)?[^.]*(?:manual|App Builder|checklist)"
                          r"|(?:manual checklist|App Builder)[^.]*a new page from scratch")
    OWN_YES = re.compile(r"(?i)(?:moving|reordering)[^.]*(?:needs|need) its own (?:explicit )?yes")
    MODEL_COPIES = {
        "AGENTS.md": (SKILL, UNGROUNDED, SECOND, NEW_PAGE, OWN_YES),
        "skills/demo-deployment-rules/SKILL.md": (SKILL, UNGROUNDED, SECOND, THREE, NEW_PAGE, "Needs its own yes"),
        "skills/demo-deployment-rules/references/deploy-error-patterns.md": (SECOND, THREE, "Never re-guess"),
        "prompts/building/phase1.md": (SKILL, UNGROUNDED, SECOND, THREE, NEW_PAGE, OWN_YES),
        "prompts/building/direct-repair.md": (SKILL, UNGROUNDED, re.compile(r"(?i)a second rejection stops the edit"),
                                              NEW_PAGE, OWN_YES),
        "prompts/building/official-skill-overrides.md": (SKILL, UNGROUNDED, SECOND, THREE, NEW_PAGE, OWN_YES),
        "prompts/scout/router-build.md": (UNGROUNDED, SECOND, NEW_PAGE),
        "prompts/building/handover-brief.md": (NEW_PAGE, "each component the convergence rule dropped with its App Builder step"),
    }
    STALE = re.compile(r"(?i)only to existing `flexipage:fieldSection`|Route `mixed`|non-convergent|whole-new-FlexiPage"
                       r"|whole-page|App Builder provides a live preview|compatible field-section append"
                       r"|Out of autonomous scope|Treat as field_section for safety|at most a few hours old"
                       r"|full-new-RecordPage|Field Section Add Rules|must re-add via Lightning App Builder"
                       r"|retry once before recording FAILED")

    def check(self, text, expectation):
        if isinstance(expectation, str):
            return expectation in text
        return expectation.search(text) is not None

    def test_every_copy_states_the_rule_and_the_convergence_rule(self):
        for path, expected in self.MODEL_COPIES.items():
            text = " ".join(read(path).split())
            for expectation in expected:
                with self.subTest(path=path, expects=getattr(expectation, "pattern", expectation)):
                    self.assertTrue(self.check(text, expectation))

    def test_the_readme_tells_the_builder_the_same_rule(self):
        readme = " ".join(read("README.md").split())
        for phrase in ("Additions to existing Lightning record pages", "with Salesforce's official page skill",
                       "everything already on the page is still where it was", "writes nothing it can't ground",
                       "a second rejection ends the edit", "at most three dry runs", "needs your yes",
                       "A new `RecordPage` from scratch is still yours to compose in App Builder"):
            self.assertIn(phrase, readme)

    def test_no_copy_keeps_the_old_append_only_limit(self):
        for path in [*self.MODEL_COPIES, "README.md", "prompts/scout/build.md", "prompts/building/change-log-template.md",
                     "prompts/sparring/audit/standard-objects.md"]:
            with self.subTest(path=path):
                self.assertIsNone(self.STALE.search(" ".join(read(path).split())))

    def test_the_procedure_snapshots_grounds_and_compares_incumbents(self):
        phase1 = read("prompts/building/phase1.md")
        rules = phase1[phase1.index("<!-- IF:LRP -->"):phase1.index("<!-- /IF:LRP -->")]
        order = [rules.index(marker) for marker in (
            "1. **Retrieve and snapshot.**", "preserve --kind component-preedit",
            "2. **Ground every component and property before the first dry run.**",
            "3. **Edit additively.**", "4. **Dry run, then deploy.**", "5. **Read back and compare.**",
            "6. **Rollback:**", "#### Field-section append (fallback)")]
        self.assertEqual(order, sorted(order))
        for phrase in ("under the same parent and in the same order", "every facet is referenced exactly once",
                       "A missing, moved or changed incumbent (`changed`), or changed page settings, makes the item FAILED",
                       "scripts/scout_page_check.py\" --before [snapshot file] --after [edited file]",
                       "`--allow-property [identifier]=[property]`, `--allow-move [identifier]`, `--allow-remove [identifier]`",
                       "with its properties and visibility rule unchanged", "a page retrieved from this org that already uses it",
                       "no name is guessed from memory", "when the `flexipage` capability is ready",
                       "`salesforce-development:platform-metadata-api-context-get`", "the click path for visual QA",
                       "never bootstrap one with `sf template generate flexipage`", "redeploy under the attempt rule"):
            self.assertIn(phrase, " ".join(phase1.split()))
        self.assertIn("Record page edit | `salesforce-development:platform-flexipage-generate`", read("prompts/scout/build.md"))
        self.assertIn('§"Lightning Record Page — Edit Rules"', read("prompts/scout/build.md"))

    def test_record_pages_are_a_gated_category_with_a_capability(self):
        rules = read("AGENTS.md")
        gated = rules[rules.index("### Gated:"):rules.index("### Docs-Gated:")]
        self.assertIn("- Lightning record pages: additive edits to existing pages", gated)
        autonomous = rules[rules.index("### Autonomous:"):rules.index("### Gated:")]
        self.assertNotIn("Lightning Record Page", autonomous)
        self.assertIn("keep record page edits append-only", rules)
        capabilities = json.loads(read("assets/official-capabilities.json"))["capabilities"]
        self.assertEqual(capabilities["flexipage"]["skills"], ["salesforce-development:platform-flexipage-generate",
                                                               "salesforce-development:platform-metadata-api-context-get"])


if __name__ == "__main__":
    unittest.main()
