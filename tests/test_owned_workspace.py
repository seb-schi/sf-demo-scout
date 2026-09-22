"""Executable fixtures for retained, per-writer Scout metadata projects."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


HELPER = Path(__file__).resolve().parents[1] / "scripts/build-assets.py"


class OwnedWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.workspace = self.base / "sf-demo-scout"
        self.customer = self.workspace / "orgs/customer-a"
        self.customer.mkdir(parents=True)
        self.config = {
            "packageDirectories": [{"path": "force-app", "default": True}],
            "namespace": "DemoNS",
            "sourceApiVersion": "66.0",
            "sfdcLoginUrl": "https://example.invalid",
            "plugins": {"fixture": "not copied"},
        }
        self.config_path = self.workspace / "sfdx-project.json"
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        self.shared_source = self.workspace / "force-app/main/default"
        self.shared_source.mkdir(parents=True)
        (self.shared_source / "shared.xml").write_bytes(b"shared incumbent")
        (self.workspace / ".sf").mkdir()
        (self.workspace / ".sf/config.json").write_bytes(b"synthetic default fixture")

    def tearDown(self):
        self.temporary.cleanup()

    def cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-B", str(HELPER), *map(str, arguments)],
            capture_output=True, text=True, check=False,
        )

    def prepare(self, writer="build", customer=None):
        result = self.cli(
            "prepare-workspace", "--workspace-root", self.workspace,
            "--customer-dir", customer or self.customer, "--writer", writer,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def reject_prepare(self, workspace=None, customer=None, writer="build"):
        result = self.cli(
            "prepare-workspace", "--workspace-root", workspace or self.workspace,
            "--customer-dir", customer or self.customer, "--writer", writer,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr)
        return result

    def files(self, root):
        return {
            str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file() and not path.is_symlink()
        }

    def test_preparation_returns_exact_paths_and_minimal_supported_project(self):
        original = self.files(self.workspace)
        payload = self.prepare()
        project = Path(payload["project_root"])
        self.assertEqual(project.parent, self.customer / ".scout-work")
        self.assertEqual(payload["workspace_root"], str(self.workspace))
        self.assertEqual(payload["customer_dir"], str(self.customer))
        self.assertEqual(payload["source_root"], str(project / "force-app/main/default"))
        self.assertEqual(payload["rollback_dir"], str(self.customer / "rollback"))
        self.assertEqual(payload["ownership_receipt"], str(project / "ownership.json"))
        actual = json.loads((project / "sfdx-project.json").read_text())
        self.assertEqual(actual, {key: self.config[key] for key in (
            "packageDirectories", "namespace", "sourceApiVersion",
        )})
        self.assertEqual(list(Path(payload["source_root"]).iterdir()), [])
        self.assertFalse((project / ".sf").exists())
        for relative, contents in original.items():
            self.assertEqual((self.workspace / relative).read_bytes(), contents)
        verified = self.cli("verify-workspace", "--project-root", project)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertEqual(json.loads(verified.stdout), payload)

    def test_namespace_can_be_absent_or_empty(self):
        for namespace in (None, ""):
            with self.subTest(namespace=namespace):
                config = dict(self.config)
                if namespace is None:
                    del config["namespace"]
                else:
                    config["namespace"] = namespace
                self.config_path.write_text(json.dumps(config))
                prepared = self.prepare()
                actual = json.loads((Path(prepared["project_root"]) / "sfdx-project.json").read_text())
                self.assertEqual(actual.get("namespace"), namespace)

    def test_overlapping_audit_build_repair_writers_and_same_label_are_isolated(self):
        writers = ["audit", "build", "repair", "build"]
        with ThreadPoolExecutor(max_workers=4) as executor:
            payloads = list(executor.map(self.prepare, writers))
        self.assertEqual(len({item["project_root"] for item in payloads}), 4)
        for index, payload in enumerate(payloads):
            (Path(payload["source_root"]) / "same.xml").write_text(str(index))
        for index, payload in enumerate(payloads):
            self.assertEqual((Path(payload["source_root"]) / "same.xml").read_text(), str(index))
        self.assertEqual((self.shared_source / "shared.xml").read_bytes(), b"shared incumbent")

    def test_interrupted_customer_and_unknown_owner_survive_next_customer(self):
        first = self.prepare()
        first_source = Path(first["source_root"]) / "retained.xml"
        first_source.write_bytes(b"interrupted customer A")
        unknown = self.customer / ".scout-work/unknown-owner"
        unknown.mkdir()
        (unknown / "source.xml").write_bytes(b"unknown retained source")
        original = self.files(self.customer)
        customer_b = self.workspace / "orgs/customer-b"
        customer_b.mkdir()
        self.prepare(customer=customer_b)
        self.prepare()
        for relative, contents in original.items():
            self.assertEqual((self.customer / relative).read_bytes(), contents)
        rejected = self.cli("verify-workspace", "--project-root", unknown)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual((unknown / "source.xml").read_bytes(), b"unknown retained source")

    def test_relative_escaping_nested_and_wrong_root_paths_fail_before_writes(self):
        wrong_root = self.base / "wrong-workspace"
        wrong_root.mkdir()
        nested = self.customer / "nested"
        nested.mkdir()
        for workspace, customer in (
            ("sf-demo-scout", self.customer),
            (self.workspace, "orgs/customer-a"),
            (wrong_root, self.customer),
            (self.workspace, self.base),
            (self.workspace, nested),
            (self.workspace, str(self.customer) + "/../customer-a"),
        ):
            with self.subTest(workspace=workspace, customer=customer):
                self.reject_prepare(workspace=workspace, customer=customer)
        self.assertFalse((self.customer / ".scout-work").exists())

    def test_symlinked_workspace_customer_and_source_config_are_rejected(self):
        alias = self.base / "alias"
        alias.symlink_to(self.workspace, target_is_directory=True)
        self.reject_prepare(workspace=alias)
        alias_customer = self.workspace / "orgs/alias-customer"
        alias_customer.symlink_to(self.customer, target_is_directory=True)
        self.reject_prepare(customer=alias_customer)
        external = self.base / "config.json"
        self.config_path.rename(external)
        self.config_path.symlink_to(external)
        self.reject_prepare()
        self.assertFalse((self.customer / ".scout-work").exists())

    def test_symlinked_staging_or_rollback_and_plain_file_blockers_are_untouched(self):
        external = self.base / "external"
        external.mkdir()
        sentinel = external / "sentinel"
        sentinel.write_bytes(b"keep")
        for name in (".scout-work", "rollback"):
            for kind in ("symlink", "file"):
                with self.subTest(name=name, kind=kind):
                    blocker = self.customer / name
                    if kind == "symlink":
                        blocker.symlink_to(external, target_is_directory=True)
                    else:
                        blocker.write_bytes(b"keep blocker")
                    self.reject_prepare()
                    self.assertEqual(sentinel.read_bytes(), b"keep")
                    blocker.unlink()

    def test_malformed_or_inapplicable_workspace_config_cannot_prepare(self):
        invalid = [[], {}, dict(self.config, sourceApiVersion=66),
                   dict(self.config, sourceApiVersion="66.0\n"),
                   dict(self.config, namespace="../namespace"),
                   dict(self.config, packageDirectories=[{"path": "../force-app"}])]
        for config in invalid:
            with self.subTest(config=config):
                self.config_path.write_text(json.dumps(config))
                self.reject_prepare()
        self.config_path.write_text("{broken")
        self.reject_prepare()
        self.assertFalse((self.customer / ".scout-work").exists())

    def test_invalid_writer_is_not_interpreted_as_a_path(self):
        for writer in ("../other", "/absolute", "", "has space", "a" * 65):
            with self.subTest(writer=writer):
                self.reject_prepare(writer=writer)
        self.assertFalse((self.customer / ".scout-work").exists())

    def test_failed_config_or_receipt_write_retains_partial_without_success(self):
        spec = importlib.util.spec_from_file_location("owned_workspace_helper", HELPER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for fail_at in (1, 2):
            with self.subTest(fail_at=fail_at):
                real_write = module.write_receipt
                calls = []

                def failing_write(path, value):
                    calls.append(path)
                    if len(calls) == fail_at:
                        raise OSError("injected receipt/config write failure")
                    return real_write(path, value)

                output, errors = io.StringIO(), io.StringIO()
                with mock.patch.object(module, "write_receipt", side_effect=failing_write):
                    with redirect_stdout(output), redirect_stderr(errors):
                        result = module.main([
                            "prepare-workspace", "--workspace-root", str(self.workspace),
                            "--customer-dir", str(self.customer), "--writer", "build",
                        ])
                self.assertEqual(result, 1)
                self.assertEqual(output.getvalue(), "")
                self.assertIn("injected", errors.getvalue())
        retained = list((self.customer / ".scout-work").iterdir())
        self.assertEqual(len(retained), 2)
        for path in retained:
            self.assertFalse((path / "ownership.json").exists())
            self.assertNotEqual(self.cli("verify-workspace", "--project-root", path).returncode, 0)
        self.prepare()
        self.assertTrue(all(path.exists() for path in retained))

    def test_verify_is_read_only_and_rejects_tampering_and_source_symlink(self):
        payload = self.prepare()
        project = Path(payload["project_root"])
        original = self.files(project)
        result = self.cli("verify-workspace", "--project-root", project)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.files(project), original)
        config_path = project / "sfdx-project.json"
        config_path.write_text(json.dumps(dict(self.config, sourceApiVersion="65.0")))
        self.assertNotEqual(self.cli("verify-workspace", "--project-root", project).returncode, 0)
        config_path.write_bytes(original["sfdx-project.json"])
        receipt_path = Path(payload["ownership_receipt"])
        receipt = json.loads(receipt_path.read_text())
        receipt["rollback_dir"] = str(self.base / "wrong-rollback")
        receipt_path.write_text(json.dumps(receipt))
        self.assertNotEqual(self.cli("verify-workspace", "--project-root", project).returncode, 0)
        receipt_path.write_bytes(original["ownership.json"])
        source = Path(payload["source_root"])
        source.rmdir()
        source.symlink_to(self.shared_source, target_is_directory=True)
        self.assertNotEqual(self.cli("verify-workspace", "--project-root", project).returncode, 0)

    def test_phase1_incumbents_keep_separate_first_originals_across_edits_and_retry(self):
        """The caller reuses its first receipt; later captures never replace it."""
        prepared = self.prepare()
        source = Path(prepared["source_root"])
        originals = {
            "layouts/Case-Case Layout.layout-meta.xml": b"<Layout>original</Layout>",
            "sharingRules/Case.sharingRules-meta.xml": b"<SharingRules>original</SharingRules>",
            "flexipages/Case_Record.flexipage-meta.xml": b"<FlexiPage>original</FlexiPage>",
        }
        first_receipts = {}
        for relative, original in originals.items():
            with self.subTest(relative=relative):
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(original)
                arguments = (
                    "preserve", "--source-root", source,
                    "--rollback-dir", prepared["rollback_dir"],
                    "--kind", "component-preedit", "--path", relative,
                )
                first = self.cli(*arguments)
                self.assertEqual(first.returncode, 0, first.stderr)
                first_receipts[relative] = json.loads(first.stdout)
                target.write_bytes(b"edited incumbent")
                second = self.cli(*arguments)
                self.assertEqual(second.returncode, 0, second.stderr)
                later = json.loads(second.stdout)
                self.assertNotEqual(later["artifact"], first_receipts[relative]["artifact"])
                self.assertEqual((Path(later["source"]) / relative).read_bytes(), b"edited incumbent")
                target.write_bytes(b"second edit")
                for _ in range(2):
                    verified = self.cli("verify", "--artifact", first_receipts[relative]["artifact"])
                    self.assertEqual(verified.returncode, 0, verified.stderr)
                    self.assertEqual((Path(first_receipts[relative]["source"]) / relative).read_bytes(), original)
        restore = self.prepare(writer="repair")
        for relative, receipt in first_receipts.items():
            restored = self.cli(
                "stage", "--artifact", receipt["artifact"],
                "--project-root", restore["project_root"], "--path", relative,
            )
            self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertEqual(self.files(Path(restore["source_root"])), originals)
        self.assertEqual(self.files(source), {relative: b"second edit" for relative in originals})

    def test_preparation_is_not_preservation_and_failed_copy_has_no_verified_snapshot(self):
        prepared = self.prepare()
        source = Path(prepared["source_root"])
        target = source / "layouts/Case-Case Layout.layout-meta.xml"
        target.parent.mkdir()
        target.write_bytes(b"incumbent")
        spec = importlib.util.spec_from_file_location("preservation_failure_helper", HELPER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(module, "copy_file", side_effect=OSError("injected copy failure")):
            with redirect_stdout(output), redirect_stderr(errors):
                result = module.main([
                    "preserve", "--source-root", str(source),
                    "--rollback-dir", prepared["rollback_dir"],
                    "--kind", "component-preedit", "--path", str(target.relative_to(source)),
                ])
        self.assertEqual(result, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("injected copy failure", errors.getvalue())
        self.assertEqual(target.read_bytes(), b"incumbent")
        artifacts = list(Path(prepared["rollback_dir"]).glob("component-preedit/snapshot-*"))
        self.assertEqual(len(artifacts), 1)
        self.assertNotEqual(self.cli("verify", "--artifact", artifacts[0]).returncode, 0)
        self.assertFalse((artifacts[0] / "receipt.json").exists())

    def test_snapshot_commands_reject_relative_roots_before_any_mutation(self):
        fixture = self.base / "relative-fixture"
        fixture.mkdir()
        (fixture / "source/flows").mkdir(parents=True)
        (fixture / "source/flows/Example.flow-meta.xml").write_bytes(b"original")
        spec = importlib.util.spec_from_file_location("relative_path_helper", HELPER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original = Path.cwd()
        try:
            os.chdir(fixture)
            with self.assertRaises(module.AssetError):
                module.preserve("source", str(fixture / "rollback"), "imports", ["flows"])
            with self.assertRaises(module.AssetError):
                module.preserve(str(fixture / "source"), "rollback", "imports", ["flows"])
        finally:
            os.chdir(original)
        self.assertFalse((fixture / "rollback").exists())


if __name__ == "__main__":
    unittest.main()
