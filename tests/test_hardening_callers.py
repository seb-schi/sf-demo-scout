"""Instruction delivery and executable isolated-project caller boundary (not model enforcement)."""

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class HardeningCallerTests(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_shipped_workspace_command_preserves_interrupted_source(self):
        contract = self.read("prompts/operation-safety.md")
        command = re.search(r"```bash\n(.*?)\n```", contract, re.S).group(1)
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve() / "sf-demo-scout"
            customer = workspace / "orgs" / "customer"
            customer.mkdir(parents=True)
            (workspace / "sfdx-project.json").write_text(json.dumps({
                "packageDirectories": [{"path": "force-app", "default": True}],
                "sourceApiVersion": "66.0", "namespace": "",
            }))
            old = workspace / "force-app/main/default/layouts/Retained.layout-meta.xml"
            old.parent.mkdir(parents=True)
            old.write_text("interrupted original")
            projects = []
            for writer in ("build-phase1", "audit-prelude", "direct-repair"):
                result = subprocess.run(["/bin/bash", "-eu", "-c", command],
                    env={**os.environ, "ASSET_HELPER": str(ROOT / "scripts/build-assets.py"),
                         "WORKSPACE_ROOT": str(workspace), "CUSTOMER_DIR": str(customer),
                         "WRITER": writer, "PYTHONDONTWRITEBYTECODE": "1"},
                    text=True, capture_output=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                receipt = json.loads(result.stdout)
                projects.append(receipt["project_root"])
                self.assertEqual(receipt["rollback_dir"], str(customer / "rollback"))
                marker = Path(receipt["source_root"]) / "retained.txt"
                marker.write_text(writer)
            self.assertEqual(len(set(projects)), 3)
            self.assertEqual(old.read_text(), "interrupted original")
            for project, writer in zip(projects, ("build-phase1", "audit-prelude", "direct-repair")):
                self.assertEqual((Path(project) / "force-app/main/default/retained.txt").read_text(), writer)

    def test_each_phase_receives_owned_project_and_refusal_contract(self):
        safety = self.read("prompts/operation-safety.md")
        for phase in (1, 2, 3):
            prompt = self.read(f"prompts/building/phase{phase}.md")
            self.assertIn("{{OPERATION_SAFETY}}", prompt)
            materialized = prompt.replace("{{OPERATION_SAFETY}}", safety).replace(
                "{{PROJECT_ROOT}}", "/workspace/orgs/customer/.scout-work/phase-unique")
            self.assertIn("explicit permission or policy rejection", materialized)
            self.assertIn("directory", materialized)
            self.assertNotIn('directory` = `$HOME/claude-projects/sf-demo-scout`', materialized)
        for caller in ("commands/scout-building.md", "prompts/sparring/audit-orchestration.md",
                       "prompts/building/direct-repair.md", "prompts/cross-org-extract.md"):
            self.assertIn("prompts/operation-safety.md", self.read(caller))

    def test_existing_agent_handoff_between_distinct_owned_projects(self):
        preflight = self.read("prompts/building/agentforce-editability.md")
        caller = self.read("commands/scout-building.md")
        preserve = next(block for block in re.findall(r"```bash\n(.*?)\n\s*```", preflight, re.S)
                        if "AGENT_PREFLIGHT_PATH" in block)
        stage = next(block for block in re.findall(r"```bash\n(.*?)\n\s*```", caller, re.S)
                     if "AGENT_PREFLIGHT_ARTIFACT" in block)
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve() / "sf-demo-scout"
            customer = workspace / "orgs/customer"
            customer.mkdir(parents=True)
            (workspace / "sfdx-project.json").write_text(json.dumps({
                "packageDirectories": [{"path": "force-app", "default": True}],
                "sourceApiVersion": "66.0"}))
            helper = str(ROOT / "scripts/build-assets.py")
            def prepare(writer):
                return json.loads(subprocess.check_output([
                    "python3", "-B", helper, "prepare-workspace", "--workspace-root",
                    str(workspace), "--customer-dir", str(customer), "--writer", writer], text=True))
            parent, worker = prepare("preflight"), prepare("phase3")
            member = "aiAuthoringBundles/Existing_v1"
            source = Path(parent["source_root"]) / member / "Existing.agent"
            source.parent.mkdir(parents=True)
            source.write_text("original agent source")
            env = {**os.environ, "ASSET_HELPER": helper, "SOURCE_ROOT": parent["source_root"],
                   "ROLLBACK_DIR": parent["rollback_dir"], "PROJECT_ROOT": worker["project_root"],
                   "AGENT_PREFLIGHT_PATH": member, "PYTHONDONTWRITEBYTECODE": "1"}
            artifact = json.loads(subprocess.check_output(["/bin/bash", "-eu", "-c", preserve],
                                                         env=env, text=True))
            env["AGENT_PREFLIGHT_ARTIFACT"] = artifact["artifact"]
            subprocess.run(["/bin/bash", "-eu", "-c", stage], env=env, text=True,
                           capture_output=True, check=True)
            staged = Path(worker["source_root"]) / member / "Existing.agent"
            self.assertEqual(staged.read_bytes(), source.read_bytes())
            staged.write_text("worker edit")
            self.assertEqual(source.read_text(), "original agent source")
            self.assertEqual((Path(artifact["source"]) / member / "Existing.agent").read_bytes(),
                             source.read_bytes())

    def test_materialized_unsupported_flow_report_stays_awaiting_qa(self):
        import test_build_completion as fixtures
        fixture = fixtures.CompletionReconciliationTests()
        fixture.setUp()
        item, ledger, worker, evidence = fixture.flow_phase_context("unsupported")
        prompt = self.read("prompts/building/phase2.md")
        section = prompt[prompt.index("### Unsupported Flow report fields"):]
        fields = json.loads(re.search(r"```json\n(.*?)\n```", section, re.S).group(1))
        row = worker["deployed"][0]
        for key in list(row):
            if key.startswith("flow_test_") or key == "tested_flow_version_number":
                del row[key]
        row.update(fields)
        result = fixture.module.reconcile(ledger, worker, evidence, fixture.spec_bytes)
        self.assertTrue(result["valid"], result)
        self.assertEqual("AWAITING_QA", fixture.result_for(result, item["id"])["disposition"])

    def test_cleanup_routes_retain_source_without_suppressed_sweeps(self):
        showtime = self.read("prompts/sparring/showtime.md")
        self.assertNotIn("[ORG_FOLDER]/.audit-progress.log", showtime)
        self.assertIn("[AUDIT_RUN_DIR]/.audit-progress.log", showtime)
        for caller in ("commands/scout-building.md", "prompts/sparring/audit-orchestration.md"):
            text = self.read(caller)
            self.assertNotRegex(text, r"find[^\n]*-delete|rm -rf|deny-rule-safe")
            self.assertNotIn("2>/dev/null || true", text)

    def test_named_incumbents_receive_materialized_immutable_contract(self):
        phase = self.read("prompts/building/phase1.md")
        contract = self.read("prompts/building/component-rollback.md")
        for tag in ("LAYOUTS", "SHARING_RULES", "LRP"):
            selected = re.sub(r"<!-- IF:(\w+) -->(.*?)<!-- /IF:\1 -->",
                lambda match: match[2] if match[1] in {tag, "COMPONENT_ROLLBACK"} else "",
                phase, flags=re.S)
            selected = selected.replace("{{COMPONENT_ROLLBACK}}", contract)
            self.assertLess(selected.index("first verified before-state"),
                            selected.index("## Deployment Rules"))
            self.assertIn("component-preedit", selected)
            self.assertNotIn(".xml.preedit", selected)
        caller = self.read("commands/scout-building.md")
        self.assertIn("all selected Phase 1 metadata", caller)

    def test_handover_opens_with_actual_disposition(self):
        handover = self.read("prompts/building/handover-brief.md")
        self.assertLess(handover.index("Achieved State"), handover.index("Demo Story"))
        self.assertIn("supersedes", handover)
        self.assertNotIn("from the spec scenario, not component names", handover)


if __name__ == "__main__":
    unittest.main()
