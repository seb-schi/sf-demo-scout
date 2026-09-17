"""Black-box regression tests for the build-assets safety boundary."""

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[1]
HELPER = REPOSITORY / "scripts" / "build-assets.py"


class BuildAssetsContractTests(unittest.TestCase):
    """Each test exercises the shipped CLI against a disposable workspace."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tempdir.name)
        self.source_root = self.base / "workspace" / "force-app" / "main" / "default"
        self.rollback = self.base / "durable-rollback"
        self.project_root = self.base / "restore-project"
        self.source_root.mkdir(parents=True)
        self.rollback.mkdir()
        self.project_root.mkdir()
        self._create_fixture()

    def tearDown(self):
        self.tempdir.cleanup()

    def _create_fixture(self):
        self.write("flows/OrderFlow.flow-meta.xml", "<Flow>order</Flow>\n")
        self.write("flows/OldFlow.flow-meta.xml", "<Flow>old</Flow>\n")
        self.write("classes/OrderService.cls", "public class OrderService {}\n")
        self.write("classes/OrderService.cls-meta.xml", "<?xml version='1.0'?>\n")
        self.write("classes/Archived.cls", "public class Archived {}\n")
        self.write("classes/Archived.cls-meta.xml", "<?xml version='1.0'?>\n")
        self.write("lwc/orderPanel/orderPanel.html", "<template>Order</template>\n")
        self.write("lwc/orderPanel/orderPanel.js", "export default class OrderPanel {}\n")
        self.write("lwc/orderPanel/orderPanel.js-meta.xml", "<LightningComponentBundle/>\n")
        (self.source_root / "lwc/orderPanel/assets/empty").mkdir(parents=True)
        self.write("lwc/archivePanel/archivePanel.html", "<template>Archive</template>\n")
        self.write("lwc/archivePanel/archivePanel.js", "export default class ArchivePanel {}\n")
        self.write("lwc/archivePanel/archivePanel.js-meta.xml", "<LightningComponentBundle/>\n")
        self.write("aiAuthoringBundles/OrderAgent/OrderAgent.agent", "name: OrderAgent\n")
        self.write("aiAuthoringBundles/OrderAgent/bundle.json", '{"version": 1}\n')
        self.write("aiAuthoringBundles/OrderAgent/schemas/input/order.json", '{"type": "object"}\n')
        (self.source_root / "aiAuthoringBundles/OrderAgent/schemas/empty").mkdir(parents=True)
        self.write("data-samples/order-query/run-001/records.json", '[{"Id": "001"}]\n')

    def write(self, relative, contents):
        target = self.source_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(HELPER), *map(str, arguments)],
            text=True,
            capture_output=True,
            check=False,
        )

    def success(self, *arguments):
        result = self.run_cli(*arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            self.fail("success output was not JSON: %s (%s)" % (result.stdout, error))

    def rejected(self, *arguments):
        result = self.run_cli(*arguments)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertTrue(result.stderr.strip(), "rejection should explain the failure")
        return result

    def preserve(self, *paths, kind="imports", source_root=None, rollback=None):
        return self.success(
            "preserve",
            "--source-root", source_root or self.source_root,
            "--rollback-dir", rollback or self.rollback,
            "--kind", kind,
            *sum((["--path", path] for path in paths), []),
        )

    def artifact_files(self, root):
        return {
            item.relative_to(root).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
            for item in root.rglob("*")
            if item.is_file()
        }

    def selected_source_files(self, *paths):
        expected = {}
        for selected in paths:
            selected_root = self.source_root / selected
            for item in selected_root.rglob("*"):
                if item.is_file():
                    expected[item.relative_to(self.source_root).as_posix()] = hashlib.sha256(
                        item.read_bytes()
                    ).hexdigest()
        return expected

    def loaded_helper(self):
        """Load the shipped executable only for injected local-I/O failure paths."""
        spec = importlib.util.spec_from_file_location("build_assets_under_test", HELPER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def injected_preserve_exit(self, seam):
        module = self.loaded_helper()
        arguments = [
            "preserve", "--source-root", str(self.source_root), "--rollback-dir", str(self.rollback),
            "--kind", "imports", "--path", "flows",
        ]
        with mock.patch.object(module, seam, side_effect=OSError("injected I/O failure")):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                return module.main(arguments)

    def test_helper_is_shipped(self):
        """Catches a release that omits the executable safety boundary entirely."""
        self.assertTrue(HELPER.is_file(), "scripts/build-assets.py must be shipped")

    def test_agent_preedit_preserves_exact_complete_bundles_and_retry_is_immutable(self):
        """Existing-agent backups must not silently nest/replace a prior snapshot."""
        self.write("genAiPlannerBundles/OrderAgent_v7/planner.xml", "<planner>old</planner>")
        self.write("genAiPlannerBundles/OrderAgent_v7/localActions/topic/action/input/schema.json", "{}")
        paths = ("genAiPlannerBundles/OrderAgent_v7", "aiAuthoringBundles/OrderAgent")
        first = self.preserve(*paths, kind="agent-preedit")
        old = self.artifact_files(Path(first["artifact"]))
        self.write("genAiPlannerBundles/OrderAgent_v7/planner.xml", "<planner>new</planner>")
        second = self.preserve(*paths, kind="agent-preedit")
        self.assertNotEqual(first["artifact"], second["artifact"])
        self.assertEqual(self.artifact_files(Path(first["artifact"])), old)
        shutil.rmtree(self.source_root)
        self.assertEqual(self.success("verify", "--artifact", first["artifact"])["paths"], list(paths))
        self.rejected("stage", "--artifact", first["artifact"], "--project-root", self.project_root,
                      "--path", paths[0])

    def test_agent_preedit_requires_only_the_selected_available_family(self):
        """A planner is not required when an exact editable authoring bundle is selected."""
        result = self.preserve("aiAuthoringBundles/OrderAgent", kind="agent-preedit")
        self.assertEqual(result["paths"], ["aiAuthoringBundles/OrderAgent"])
        self.assertEqual(result["kind"], "agent-preedit")

    def test_agent_preedit_rejects_missing_family_wide_and_partial_selections(self):
        """A missing required source must never become a verified backup."""
        for selected in ("genAiPlannerBundles/Missing", "aiAuthoringBundles",
                         "aiAuthoringBundles/OrderAgent/schemas", "flows/OrderFlow.flow-meta.xml"):
            with self.subTest(selected=selected):
                self.rejected("preserve", "--source-root", self.source_root,
                              "--rollback-dir", self.rollback, "--kind", "agent-preedit",
                              "--path", selected)
        self.assertEqual(list(self.rollback.rglob("receipt.json")), [])

    def test_agent_preedit_copy_failure_preserves_original_and_has_no_valid_receipt(self):
        module = self.loaded_helper()
        original = self.artifact_files(self.source_root)
        with mock.patch.object(module, "copy_file", side_effect=OSError("copy unavailable")):
            with self.assertRaises(module.AssetError):
                module.preserve(str(self.source_root), str(self.rollback), "agent-preedit",
                                ["aiAuthoringBundles/OrderAgent"])
        self.assertEqual(self.artifact_files(self.source_root), original)
        self.assertEqual(list(self.rollback.rglob("receipt.json")), [])

    def test_static_existing_agent_snapshot_precedes_edit_and_blocks_cleanup(self):
        """Prompt wiring only: behavioral file protection is exercised above."""
        phase = (REPOSITORY / "prompts/building/phase3.md").read_text()
        modify = phase[phase.index("### Modify Existing Agent"):phase.index("### Smoke Test")]
        self.assertNotIn("2>/dev/null || true", modify)
        invoke = modify.index("Invoke `agentforce-generate`")
        self.assertLess(modify.index("--kind agent-preedit"), invoke)
        self.assertLess(modify.index("Record the current active version number"), invoke)
        self.assertIn("preedit_snapshot", modify)
        caller = (REPOSITORY / "commands/scout-building.md").read_text()
        cleanup = caller[caller.index("Workspace cleanup (after the change log is written).") :]
        self.assertIn("preedit_snapshot", cleanup)
        self.assertIn("agent-preedit", cleanup)

    def test_preserve_retains_all_flat_and_nested_content(self):
        """Catches a shallow copy that drops companion files or nested schema data."""
        imports = self.preserve("classes")
        self.assertEqual(imports["paths"], ["classes"])
        self.assertEqual(
            self.artifact_files(Path(imports["source"])), self.selected_source_files("classes")
        )
        recovery = self.preserve("aiAuthoringBundles/OrderAgent", kind="agent-recovery")
        self.assertEqual(recovery["paths"], ["aiAuthoringBundles/OrderAgent"])
        self.assertEqual(
            self.artifact_files(Path(recovery["source"])),
            self.selected_source_files("aiAuthoringBundles/OrderAgent"),
        )
        self.assertTrue((Path(recovery["source"]) / "aiAuthoringBundles/OrderAgent/schemas/empty").is_dir())

    def test_preserve_retains_deeply_nested_data_samples(self):
        """Catches a snapshot that treats nested data samples as metadata leaf files."""
        payload = self.preserve("data-samples")
        self.assertEqual(
            self.artifact_files(Path(payload["source"])), self.selected_source_files("data-samples")
        )

    def test_preserve_creates_unique_snapshots_in_the_same_minute(self):
        """Catches timestamp-only artifact names that overwrite a prior attempt."""
        first = self.preserve("flows")
        second = self.preserve("flows")
        self.assertNotEqual(first["artifact"], second["artifact"])
        self.assertTrue(Path(first["artifact"]).is_dir())
        self.assertTrue(Path(second["artifact"]).is_dir())

    def test_verify_survives_scratch_cleanup_in_a_fresh_process(self):
        """Catches a receipt that implicitly relies on temporary source files."""
        payload = self.preserve("aiAuthoringBundles/OrderAgent", kind="agent-recovery")
        shutil.rmtree(self.source_root / "aiAuthoringBundles" / "OrderAgent")
        verified = self.success("verify", "--artifact", payload["artifact"])
        self.assertEqual(verified["artifact"], payload["artifact"])
        self.assertEqual(verified["kind"], "agent-recovery")

    def test_stage_only_restores_the_explicit_component(self):
        """Catches staging that scans an artifact and restores archived siblings."""
        payload = self.preserve("flows")
        staged = self.success(
            "stage", "--artifact", payload["artifact"], "--project-root", self.project_root,
            "--path", "flows/OrderFlow.flow-meta.xml",
        )
        destination = self.project_root / "force-app" / "main" / "default" / "flows"
        self.assertEqual(staged["staged"], ["flows/OrderFlow.flow-meta.xml"])
        self.assertTrue((destination / "OrderFlow.flow-meta.xml").is_file())
        self.assertFalse((destination / "OldFlow.flow-meta.xml").exists())

    def test_fresh_consumer_stages_only_the_component_persisted_in_a_spec(self):
        """Exercises controlled spec fields; Scout's prose interpretation remains static review."""
        payload = self.preserve("flows")
        spec = self.base / "demo-spec.md"
        spec.write_text(
            "### Imported Assets (optional — selected metadata only)\n"
            "- Artifact: %s\n"
            "- Component paths: flows/OrderFlow.flow-meta.xml\n"
            "- Supplies spec item: Flows / OrderFlow\n"
            "- Phase: 2\n" % payload["artifact"],
            encoding="utf-8",
        )
        shutil.rmtree(self.source_root)
        consumer = """
import re, subprocess, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding='utf-8')
artifact = re.search(r'^- Artifact: (.+)$', text, re.M).group(1)
component = re.search(r'^- Component paths: (.+)$', text, re.M).group(1)
for _ in range(2):
    result = subprocess.run([
        sys.executable, sys.argv[2], 'stage', '--artifact', artifact,
        '--project-root', sys.argv[3], '--path', component,
    ], text=True, capture_output=True)
    if result.returncode:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
"""
        result = subprocess.run(
            [sys.executable, "-c", consumer, str(spec), str(HELPER), str(self.project_root)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        destination = self.project_root / "force-app/main/default/flows"
        self.assertTrue((destination / "OrderFlow.flow-meta.xml").is_file())
        self.assertFalse((destination / "OldFlow.flow-meta.xml").exists())

    def test_stage_class_includes_its_metadata_companion(self):
        """Catches a class restore that stages code without its metadata companion."""
        payload = self.preserve("classes")
        staged = self.success(
            "stage", "--artifact", payload["artifact"], "--project-root", self.project_root,
            "--path", "classes/OrderService.cls",
        )
        self.assertEqual(
            staged["staged"],
            ["classes/OrderService.cls", "classes/OrderService.cls-meta.xml"],
        )
        destination = self.project_root / "force-app/main/default/classes"
        self.assertTrue((destination / "OrderService.cls").is_file())
        self.assertTrue((destination / "OrderService.cls-meta.xml").is_file())

    def test_stage_whole_bundle_retains_empty_directories(self):
        """Catches bundle staging that drops an empty directory retained by the receipt."""
        payload = self.preserve("lwc")
        self.success(
            "stage", "--artifact", payload["artifact"], "--project-root", self.project_root,
            "--path", "lwc/orderPanel",
        )
        self.assertTrue(
            (self.project_root / "force-app/main/default/lwc/orderPanel/assets/empty").is_dir()
        )

    def test_stage_rejects_class_missing_its_metadata_companion(self):
        """Catches partial class components that deployment would interpret incompletely."""
        (self.source_root / "classes" / "OrderService.cls-meta.xml").unlink()
        payload = self.preserve("classes")
        self.rejected(
            "stage", "--artifact", payload["artifact"], "--project-root", self.project_root,
            "--path", "classes/OrderService.cls",
        )
        self.assertFalse((self.project_root / "force-app").exists())

    def test_repeated_stage_leaves_snapshot_byte_identical(self):
        """Catches staging that consumes, changes, or invalidates a preserved artifact."""
        payload = self.preserve("flows")
        artifact = Path(payload["artifact"])
        before = self.artifact_files(artifact)
        command = (
            "stage", "--artifact", artifact, "--project-root", self.project_root,
            "--path", "flows/OrderFlow.flow-meta.xml",
        )
        self.success(*command)
        self.success(*command)
        self.assertEqual(self.artifact_files(artifact), before)
        self.success("verify", "--artifact", artifact)

    def test_verify_rejects_equal_size_corruption(self):
        """Catches verification that checks count or size but not cryptographic bytes."""
        payload = self.preserve("flows")
        copied = Path(payload["source"]) / "flows" / "OrderFlow.flow-meta.xml"
        original = copied.read_bytes()
        copied.write_bytes(b"X" + original[1:])
        self.rejected("verify", "--artifact", payload["artifact"])

    def test_verify_rejects_missing_extra_and_empty_directories(self):
        """Catches receipt checks that ignore full file and directory topology."""
        for mutation in ("missing", "extra", "directory"):
            with self.subTest(mutation=mutation):
                payload = self.preserve("aiAuthoringBundles")
                source = Path(payload["source"])
                if mutation == "missing":
                    (source / "aiAuthoringBundles/OrderAgent/bundle.json").unlink()
                elif mutation == "extra":
                    (source / "aiAuthoringBundles/OrderAgent/unexpected.json").write_text("{}")
                else:
                    (source / "aiAuthoringBundles/OrderAgent/empty").mkdir()
                self.rejected("verify", "--artifact", payload["artifact"])

    def test_verify_rejects_missing_receipt_and_unsafe_receipt_reference(self):
        """Catches artifacts trusted without a usable, self-contained receipt."""
        payload = self.preserve("flows")
        artifact = Path(payload["artifact"])
        (artifact / "receipt.json").unlink()
        self.rejected("verify", "--artifact", artifact)
        payload = self.preserve("flows")
        receipt = Path(payload["artifact"]) / "receipt.json"
        contents = json.loads(receipt.read_text())
        contents["paths"] = ["../outside"]
        receipt.write_text(json.dumps(contents))
        self.rejected("verify", "--artifact", payload["artifact"])

    def test_rejects_traversal_and_symlinked_source_or_destination(self):
        """Catches selectors or filesystem links that escape the intended boundary."""
        self.rejected(
            "preserve", "--source-root", self.source_root, "--rollback-dir", self.rollback,
            "--kind", "imports", "--path", "../flows",
        )
        external = self.base / "external"
        external.mkdir()
        os.symlink(external, self.source_root / "flows" / "linked")
        self.rejected(
            "preserve", "--source-root", self.source_root, "--rollback-dir", self.rollback,
            "--kind", "imports", "--path", "flows",
        )
        (self.source_root / "flows" / "linked").unlink()
        payload = self.preserve("flows")
        destination_root = self.project_root / "force-app" / "main" / "default"
        destination_root.mkdir(parents=True)
        os.symlink(external, destination_root / "flows")
        self.rejected(
            "stage", "--artifact", payload["artifact"], "--project-root", self.project_root,
            "--path", "flows/OrderFlow.flow-meta.xml",
        )

    def test_rejects_source_root_with_a_symlinked_parent(self):
        """Catches source-root resolution that silently traverses a symlinked ancestor."""
        alias = self.base / "aliased-workspace"
        os.symlink(self.base / "workspace", alias)
        self.rejected(
            "preserve", "--source-root", alias / "force-app/main/default",
            "--rollback-dir", self.rollback, "--kind", "imports", "--path", "flows",
        )

    def test_recovery_bundle_survives_cleanup_and_cannot_be_staged_as_import(self):
        """Catches recovery copies that lose nested content or cross into import staging."""
        payload = self.preserve("aiAuthoringBundles/OrderAgent", kind="agent-recovery")
        shutil.rmtree(self.source_root / "aiAuthoringBundles")
        verified = self.success("verify", "--artifact", payload["artifact"])
        self.assertEqual(verified["paths"], ["aiAuthoringBundles/OrderAgent"])
        self.rejected(
            "stage", "--artifact", payload["artifact"], "--project-root", self.project_root,
            "--path", "aiAuthoringBundles/OrderAgent",
        )

    def test_stage_rejects_top_level_and_partial_bundle_selectors(self):
        """Catches broad or partial bundle staging that can deploy an unintended scope."""
        payload = self.preserve("flows", "lwc", "aiAuthoringBundles")
        for selector in ("flows", "lwc/orderPanel/orderPanel.js", "aiAuthoringBundles/OrderAgent/OrderAgent.agent"):
            with self.subTest(selector=selector):
                self.rejected(
                    "stage", "--artifact", payload["artifact"], "--project-root", self.project_root,
                    "--path", selector,
                )

    def test_stage_validates_every_selection_before_writing_anything(self):
        """Catches a sequential stage that writes a good member before rejecting a bad one."""
        payload = self.preserve("flows")
        self.rejected(
            "stage", "--artifact", payload["artifact"], "--project-root", self.project_root,
            "--path", "flows/OrderFlow.flow-meta.xml", "--path", "../bad",
        )
        self.assertFalse(
            (self.project_root / "force-app/main/default/flows/OrderFlow.flow-meta.xml").exists()
        )

    def test_stage_rejects_destination_inside_the_artifact(self):
        """Catches a stage target that can mutate the immutable snapshot itself."""
        payload = self.preserve("flows")
        artifact = Path(payload["artifact"])
        before = self.artifact_files(artifact)
        destination = artifact / "project-output"
        destination.mkdir()
        self.rejected(
            "stage", "--artifact", artifact, "--project-root", destination,
            "--path", "flows/OrderFlow.flow-meta.xml",
        )
        self.assertEqual(self.artifact_files(artifact), before)

    def test_preserve_rejects_missing_empty_and_ephemeral_destinations(self):
        """Catches claims of durable preservation for invalid inputs or scratch storage."""
        self.rejected(
            "preserve", "--source-root", self.source_root, "--rollback-dir", self.rollback,
            "--kind", "imports", "--path", "missing",
        )
        (self.source_root / "empty").mkdir()
        self.rejected(
            "preserve", "--source-root", self.source_root, "--rollback-dir", self.rollback,
            "--kind", "imports", "--path", "empty",
        )
        self.rejected(
            "preserve", "--source-root", self.source_root, "--rollback-dir", self.source_root / "scratch",
            "--kind", "imports", "--path", "flows",
        )

    def test_copy_or_hash_failure_keeps_original_and_never_marks_snapshot_valid(self):
        """Catches an I/O error path that writes a receipt despite an invalid copy."""
        before = self.artifact_files(self.source_root / "flows")
        for seam in ("copy_file", "hash_file"):
            with self.subTest(seam=seam):
                self.assertNotEqual(self.injected_preserve_exit(seam), 0)
                self.assertEqual(self.artifact_files(self.source_root / "flows"), before)
                self.assertEqual(list(self.rollback.rglob("receipt.json")), [])

    def test_static_prior_recovery_guard_precedes_sweeps_and_final_cleanup_rechecks(self):
        """Static prompt wiring only; no live model or Salesforce behavior is claimed."""
        prompt = (REPOSITORY / "commands" / "scout-building.md").read_text(encoding="utf-8")
        startup_guard = prompt.index("A previous build's retained recovery source is not disposable.")
        startup_sweep = prompt.index(
            'find "$HOME/claude-projects/sf-demo-scout/force-app/main/default" -mindepth 1 -delete'
        )
        self.assertLess(startup_guard, startup_sweep)
        guard = prompt[startup_guard:startup_sweep]
        for behavior in (
            "unresolved recovery-preservation / cleanup-withheld",
            "preserve --kind agent-recovery",
            "missing/malformed prior",
            "unknown owner",
            "withhold cleanup",
        ):
            self.assertIn(behavior, guard)

        final_cleanup = prompt.index("Workspace cleanup (after the change log is written).")
        final_sweep = prompt.index(
            'find "$HOME/claude-projects/sf-demo-scout/force-app/main/default" -mindepth 1 -delete',
            final_cleanup,
        )
        final_guard = prompt[final_cleanup:final_sweep]
        for behavior in ("NeedsUICommit", "failed/unverified", "BLOCKS this sweep"):
            self.assertIn(behavior, final_guard)
