"""Hermetic regressions for Scout workspace setup and validation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "setup-workspace.py"


class SetupWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="scout-workspace-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / "workspace"
        self.config = self.base / "config" / "config.json"
        self.template = self.base / "workspace-settings.template.json"
        self.template.write_text(
            json.dumps({"model": "opus", "permissions": {"allow": ["Read"]}})
            + "\n"
        )
        self.bin_dir = self.base / "bin"
        self.bin_dir.mkdir()

    def install_sf_stub(
        self,
        *,
        exit_code: int = 0,
        output: str = '{"status": 0, "result": {}}',
        make_project: bool = True,
        make_force_app: bool = True,
        broken_force_app: bool = False,
        symlink_force_app: bool = False,
    ) -> None:
        sf = self.bin_dir / "sf"
        sf.write_text(
            """#!/bin/bash
set -u
output_dir=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--output-dir" ]; then
    shift
    output_dir="$1"
  fi
  shift
done
if [ "${MAKE_PROJECT}" = 1 ]; then
  mkdir -p "$output_dir/sf-demo-scout"
  printf '{"packageDirectories":[{"path":"force-app","default":true}],"sourceApiVersion":"65.0"}\n' > "$output_dir/sf-demo-scout/sfdx-project.json"
fi
if [ "${MAKE_FORCE_APP}" = 1 ]; then
  if [ "${SYMLINK_FORCE_APP}" = 1 ]; then
    mkdir -p "$output_dir/generated-force-app/main/default"
    ln -s "$output_dir/generated-force-app" "$output_dir/sf-demo-scout/force-app"
  else
    mkdir -p "$output_dir/sf-demo-scout/force-app/main/default"
    if [ "${BROKEN_FORCE_APP}" = 1 ]; then
      ln -s missing-target "$output_dir/sf-demo-scout/force-app/main/default/broken"
    else
      printf 'generated\n' > "$output_dir/sf-demo-scout/force-app/main/default/generated.txt"
    fi
  fi
fi
printf '%s\n' "${SF_OUTPUT}"
exit "${SF_EXIT_CODE}"
"""
        )
        sf.chmod(0o700)
        self.sf_env = {
            "PATH": f"{self.bin_dir}:/usr/bin:/bin",
            "SF_EXIT_CODE": str(exit_code),
            "SF_OUTPUT": output,
            "MAKE_PROJECT": "1" if make_project else "0",
            "MAKE_FORCE_APP": "1" if make_force_app else "0",
            "BROKEN_FORCE_APP": "1" if broken_force_app else "0",
            "SYMLINK_FORCE_APP": "1" if symlink_force_app else "0",
        }

    def run_setup(
        self,
        *,
        config: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.update(getattr(self, "sf_env", {}))
        if extra_env:
            env.update(extra_env)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPT),
                "setup",
                "--workspace",
                str(self.workspace),
                "--config",
                str(config or self.config),
                "--template",
                str(self.template),
                "--plugin-version",
                "2026.09.17-test",
            ],
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

    def run_verify(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPT),
                "verify",
                "--workspace",
                str(self.workspace),
                "--config",
                str(self.config),
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

    def test_sf_failure_aborts_before_settings_and_config(self) -> None:
        self.install_sf_stub(exit_code=73, output='{"status": 1}')

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SFDX_GENERATE_FAILED", result.stdout)
        self.assertFalse((self.workspace / "sfdx-project.json").exists())
        self.assertFalse((self.workspace / ".claude/settings.json").exists())
        self.assertFalse(self.config.exists())

    def test_malformed_or_unsuccessful_sf_json_aborts(self) -> None:
        for name, output in (
            ("malformed", "not json"),
            ("unsuccessful", '{"status": 1, "result": {}}'),
            ("ambiguous", '{"status": "0", "result": {}}'),
        ):
            with self.subTest(name=name):
                case = self.base / name
                case.mkdir()
                self.workspace = case / "workspace"
                self.config = case / "config.json"
                self.install_sf_stub(output=output)
                result = self.run_setup()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("SFDX_GENERATE_UNVERIFIED", result.stdout)
                self.assertFalse(self.config.exists())

    def test_success_json_without_generated_artifacts_is_unverified_and_cleaned(self) -> None:
        self.install_sf_stub(make_project=False, make_force_app=False)

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SFDX_GENERATE_UNVERIFIED", result.stdout)
        self.assertFalse(self.config.exists())
        self.assertEqual(list(self.base.glob(".scout-sfdx-*")), [])

    def test_success_creates_verified_mandatory_artifacts_and_config(self) -> None:
        self.install_sf_stub()

        result = self.run_setup()

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("WORKSPACE_READY", result.stdout)
        project = json.loads((self.workspace / "sfdx-project.json").read_text())
        settings = json.loads(
            (self.workspace / ".claude/settings.json").read_text()
        )
        config = json.loads(self.config.read_text())
        self.assertEqual(project["packageDirectories"][0]["path"], "force-app")
        self.assertEqual(settings["model"], "opus")
        self.assertEqual(config["workspace_path"], str(self.workspace.resolve()))
        self.assertEqual(config["plugin_version"], "2026.09.17-test")
        self.assertTrue((self.workspace / "force-app").is_dir())
        self.assertTrue((self.workspace / "orgs/lessons/INDEX.md").is_file())
        verified = self.run_verify()
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        self.assertEqual(verified.stdout.strip(), "WORKSPACE_READY")

    def test_partial_rerun_preserves_existing_user_files_and_config(self) -> None:
        self.workspace.mkdir()
        (self.workspace / "force-app").mkdir()
        user_source = self.workspace / "force-app/user-owned.txt"
        user_source.write_text("keep source\n")
        lessons = self.workspace / "orgs/lessons"
        lessons.mkdir(parents=True)
        index = lessons / "INDEX.md"
        index.write_text("# My lessons\n")
        settings = self.workspace / ".claude/settings.json"
        settings.parent.mkdir()
        settings.write_text('{"model":"user-choice","custom":true}\n')
        self.config.parent.mkdir()
        original_config = (
            '{"workspace_path":"'
            + str(self.workspace.resolve())
            + '","install_method":"plugin","plugin_version":"older",'
            + '"setup_completed_at":"2026-01-01T00:00:00Z","custom":true}\n'
        )
        self.config.write_text(original_config)
        self.install_sf_stub()

        result = self.run_setup()

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(user_source.read_text(), "keep source\n")
        self.assertFalse(
            (self.workspace / "force-app/main/default/generated.txt").exists()
        )
        self.assertEqual(index.read_text(), "# My lessons\n")
        self.assertEqual(settings.read_text(), '{"model":"user-choice","custom":true}\n')
        self.assertEqual(self.config.read_text(), original_config)

    def test_partial_rerun_repairs_missing_force_app_and_preserves_project(self) -> None:
        self.workspace.mkdir()
        project = self.workspace / "sfdx-project.json"
        original_project = (
            '{"packageDirectories":[{"path":"force-app","default":true}],'
            '"sourceApiVersion":"64.0","custom":"keep"}\n'
        )
        project.write_text(original_project)
        self.install_sf_stub()

        result = self.run_setup()

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(project.read_text(), original_project)
        self.assertTrue((self.workspace / "force-app").is_dir())
        self.assertTrue(
            (self.workspace / "force-app/main/default/generated.txt").is_file()
        )
        self.assertTrue(self.config.is_file())

    def test_missing_template_aborts_without_claiming_settings_or_config(self) -> None:
        self.install_sf_stub()
        self.template.unlink()

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SETTINGS_TEMPLATE_INVALID", result.stdout)
        self.assertFalse((self.workspace / ".claude/settings.json").exists())
        self.assertFalse(self.config.exists())

    def test_force_app_file_blocks_scaffold_without_clobber(self) -> None:
        self.workspace.mkdir()
        force_app = self.workspace / "force-app"
        force_app.write_text("user-owned blocker\n")
        self.install_sf_stub()

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FORCE_APP_INVALID", result.stdout)
        self.assertEqual(force_app.read_text(), "user-owned blocker\n")
        self.assertFalse((self.workspace / "sfdx-project.json").exists())
        self.assertFalse(self.config.exists())

    def test_dangling_force_app_symlink_is_preserved(self) -> None:
        self.workspace.mkdir()
        force_app = self.workspace / "force-app"
        force_app.symlink_to(self.workspace / "missing-user-target")
        self.install_sf_stub()

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FORCE_APP_INVALID", result.stdout)
        self.assertTrue(force_app.is_symlink())
        self.assertEqual(
            os.readlink(force_app), str(self.workspace / "missing-user-target")
        )
        self.assertFalse((self.workspace / "sfdx-project.json").exists())
        self.assertFalse(self.config.exists())

    def test_live_force_app_symlink_blocks_setup_without_clobber(self) -> None:
        self.workspace.mkdir()
        outside = self.base / "outside-force-app"
        outside.mkdir()
        force_app = self.workspace / "force-app"
        force_app.symlink_to(outside, target_is_directory=True)
        self.install_sf_stub()

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FORCE_APP_INVALID", result.stdout)
        self.assertTrue(force_app.is_symlink())
        self.assertTrue(outside.is_dir())
        self.assertFalse((self.workspace / "sfdx-project.json").exists())
        self.assertFalse(self.config.exists())

    def test_verify_rejects_live_force_app_symlink(self) -> None:
        self.install_sf_stub()
        setup_result = self.run_setup()
        self.assertEqual(
            setup_result.returncode, 0, setup_result.stderr + setup_result.stdout
        )
        force_app = self.workspace / "force-app"
        outside = self.base / "outside-force-app"
        force_app.rename(outside)
        force_app.symlink_to(outside, target_is_directory=True)

        result = self.run_verify()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FORCE_APP_INVALID", result.stdout)
        self.assertTrue(force_app.is_symlink())
        self.assertTrue((outside / "main/default/generated.txt").is_file())

    def test_nested_scaffold_symlink_is_unverified_and_staging_is_cleaned(self) -> None:
        self.install_sf_stub(broken_force_app=True)

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SFDX_GENERATE_UNVERIFIED", result.stdout)
        self.assertFalse((self.workspace / "force-app").exists())
        self.assertFalse((self.workspace / "sfdx-project.json").exists())
        self.assertFalse(self.config.exists())
        self.assertEqual(list(self.base.glob(".scout-sfdx-*")), [])

    def test_scaffold_force_app_symlink_is_unverified(self) -> None:
        self.install_sf_stub(symlink_force_app=True)

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SFDX_GENERATE_UNVERIFIED", result.stdout)
        self.assertFalse((self.workspace / "force-app").exists())
        self.assertFalse((self.workspace / "sfdx-project.json").exists())
        self.assertFalse(self.config.exists())
        self.assertEqual(list(self.base.glob(".scout-sfdx-*")), [])

    def test_copy_staging_failure_aborts_before_project_and_config(self) -> None:
        injection = self.base / "copy-failure-injection"
        injection.mkdir()
        (injection / "sitecustomize.py").write_text(
            """import os
import shutil

_original_copytree = shutil.copytree

def fail_owned_force_app_copy(src, dst, *args, **kwargs):
    if (
        os.environ.get("SCOUT_TEST_COPY_FAILURE") == "1"
        and ".scout-sfdx-" in os.fspath(src)
        and ".force-app-stage-" in os.fspath(dst)
    ):
        raise OSError("injected force-app staging copy failure")
    return _original_copytree(src, dst, *args, **kwargs)

shutil.copytree = fail_owned_force_app_copy
"""
        )
        self.install_sf_stub()

        result = self.run_setup(
            extra_env={
                "PYTHONPATH": str(injection),
                "SCOUT_TEST_COPY_FAILURE": "1",
            }
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FORCE_APP_COPY_FAILED", result.stdout)
        self.assertFalse((self.workspace / "force-app").exists())
        self.assertFalse((self.workspace / "sfdx-project.json").exists())
        self.assertFalse(self.config.exists())
        self.assertEqual(list(self.base.glob(".scout-sfdx-*")), [])

    def test_settings_write_failure_aborts_before_config(self) -> None:
        self.workspace.mkdir()
        (self.workspace / ".claude").write_text("user-owned blocker\n")
        self.install_sf_stub()

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SETTINGS_WRITE_FAILED", result.stdout)
        self.assertEqual(
            (self.workspace / ".claude").read_text(), "user-owned blocker\n"
        )
        self.assertFalse(self.config.exists())

    def test_lessons_blocker_aborts_before_settings_and_config(self) -> None:
        self.workspace.mkdir()
        index = self.workspace / "orgs/lessons/INDEX.md"
        index.mkdir(parents=True)
        self.install_sf_stub()

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("LESSONS_INVALID", result.stdout)
        self.assertTrue(index.is_dir())
        self.assertFalse((self.workspace / ".claude/settings.json").exists())
        self.assertFalse(self.config.exists())

    def test_config_replace_failure_does_not_claim_ready(self) -> None:
        self.install_sf_stub()
        self.config.mkdir(parents=True)

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CONFIG_WRITE_FAILED", result.stdout)
        self.assertNotIn("WORKSPACE_READY", result.stdout)
        self.assertTrue(self.config.is_dir())

    def test_dangling_config_symlink_is_preserved_without_writing_target(self) -> None:
        self.workspace.mkdir()
        (self.workspace / "force-app").mkdir()
        (self.workspace / "sfdx-project.json").write_text(
            '{"packageDirectories":[{"path":"force-app"}]}\n'
        )
        lessons = self.workspace / "orgs/lessons"
        lessons.mkdir(parents=True)
        (lessons / "INDEX.md").write_text("# Existing lessons\n")
        settings = self.workspace / ".claude/settings.json"
        settings.parent.mkdir()
        settings.write_text("{}\n")
        config_link = self.base / "config-link.json"
        external_config = self.base / "outside/config.json"
        config_link.symlink_to(external_config)

        result = self.run_setup(config=config_link)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("INVALID_ARGUMENT", result.stdout)
        self.assertTrue(config_link.is_symlink())
        self.assertEqual(os.readlink(config_link), str(external_config))
        self.assertFalse(external_config.exists())

    def test_verify_fails_closed_for_bad_workspace_and_missing_artifacts(self) -> None:
        self.workspace.write_text("not a directory\n")
        self.config.parent.mkdir()
        self.config.write_text("{}\n")
        blocked = self.run_verify()
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("WORKSPACE_INVALID", blocked.stdout)

        self.workspace.unlink()
        self.workspace.mkdir()
        incomplete = self.run_verify()
        self.assertNotEqual(incomplete.returncode, 0)
        self.assertIn("SFDX_PROJECT_INVALID", incomplete.stdout)

    def test_existing_malformed_json_is_preserved_and_rejected(self) -> None:
        self.workspace.mkdir()
        (self.workspace / "sfdx-project.json").write_text("{broken\n")
        (self.workspace / "force-app").mkdir()
        self.install_sf_stub()

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SFDX_PROJECT_INVALID", result.stdout)
        self.assertEqual(
            (self.workspace / "sfdx-project.json").read_text(), "{broken\n"
        )
        self.assertFalse(self.config.exists())


if __name__ == "__main__":
    unittest.main()
