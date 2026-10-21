"""Hermetic regressions for Scout workspace setup and validation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import stand_ins


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "setup-workspace.py"
# Stands in for `sf project generate`: it scaffolds the way each test asks, then prints SF_OUTPUT.
SF_STUB = r"""import os
from pathlib import Path
import sys

arguments = sys.argv[1:]
output = Path(arguments[arguments.index("--output-dir") + 1] if "--output-dir" in arguments else "")
project = output / "sf-demo-scout"
if os.environ["MAKE_PROJECT"] == "1":
    project.mkdir(parents=True, exist_ok=True)
    (project / "sfdx-project.json").write_bytes(
        b'{"packageDirectories":[{"path":"force-app","default":true}],"sourceApiVersion":"65.0"}\n')
if os.environ["MAKE_FORCE_APP"] == "1":
    if os.environ["SYMLINK_FORCE_APP"] == "1":
        (output / "generated-force-app" / "main" / "default").mkdir(parents=True, exist_ok=True)
        os.symlink(output / "generated-force-app", project / "force-app", target_is_directory=True)
    else:
        default = project / "force-app" / "main" / "default"
        default.mkdir(parents=True, exist_ok=True)
        if os.environ["BROKEN_FORCE_APP"] == "1":
            os.symlink("missing-target", default / "broken")
        else:
            (default / "generated.txt").write_bytes(b"generated\n")
print(os.environ["SF_OUTPUT"])
sys.exit(int(os.environ["SF_EXIT_CODE"]))
"""


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
        stand_ins.require_node()  # setup reaches the CLI through Node on Windows
        stand_ins.salesforce_cli(self.bin_dir, SF_STUB)
        self.sf_env = {
            **stand_ins.cli_environment(self.bin_dir),
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
        host: str = "claude",
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
                "--host",
                host,
            ],
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

    def run_verify(self, host: str = "claude") -> subprocess.CompletedProcess[str]:
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
                "--host",
                host,
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

    def run_default(self, command: str, *args: str) -> subprocess.CompletedProcess[str]:
        """A command that takes its paths from the SCOUT_WORKSPACE and SCOUT_CONFIG_FILE seams."""
        environment = dict(os.environ, SCOUT_WORKSPACE=str(self.workspace), SCOUT_CONFIG_FILE=str(self.config),
                           PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, "-B", str(SCRIPT), command, *args], text=True, capture_output=True,
                              check=False, timeout=10, env=environment)

    def test_lessons_writes_the_index_once_and_never_replaces_it(self) -> None:
        first = self.run_default("lessons")
        self.assertEqual((first.returncode, first.stdout.strip()), (0, "LESSONS_WRITTEN"), first.stderr)
        index = self.workspace / "orgs" / "lessons" / "INDEX.md"
        self.assertTrue(index.read_text().startswith("# Lessons Index"))
        index.write_text("# Lessons Index\n\n- my own line\n")
        second = self.run_default("lessons")
        self.assertEqual(second.stdout.strip(), "LESSONS_PRESENT")
        self.assertIn("my own line", index.read_text())

    def test_a_non_ascii_workspace_path_prints_as_utf8_whatever_the_code_page(self) -> None:
        # Windows can hand a captured stdout the ANSI code page; the gate still prints its path, as UTF-8 and LF.
        self.workspace = self.base / "Łódź 東京" / "sf-demo-scout"
        self.install_sf_stub()
        self.assertEqual(self.run_setup().returncode, 0)
        env = {key: value for key, value in os.environ.items() if key not in ("PYTHONUTF8", "PYTHONPATH")}
        env.update(PYTHONIOENCODING="cp1252", SCOUT_WORKSPACE=str(self.workspace), SCOUT_CONFIG_FILE=str(self.config),
                   PYTHONDONTWRITEBYTECODE="1")
        gate = subprocess.run([sys.executable, "-B", str(SCRIPT), "gate", "--host", "claude"], env=env,
                              capture_output=True, check=False, timeout=30)
        self.assertEqual(gate.returncode, 0, gate.stderr.decode("utf-8", "replace"))
        output = gate.stdout.decode("utf-8")
        self.assertIn("WORKSPACE_READY\nSTATE=OK WORKSPACE=", output)
        self.assertIn("Łódź 東京", output)
        self.assertNotIn("\r", output)

    def test_state_creates_only_the_folder_and_reports_fresh(self) -> None:
        result = self.run_default("state", "--host", "codex")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip().endswith("STATE=FRESH"))
        self.assertEqual(list(self.workspace.iterdir()), [])  # the fresh path does the rest
        self.assertFalse(self.config.exists())

    def test_codex_setup_and_verify_do_not_require_claude_settings(self) -> None:
        self.install_sf_stub()
        result = self.run_setup(host="codex")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.workspace / ".claude").exists())
        self.assertFalse((self.workspace / ".codex").exists())
        self.assertEqual(self.run_verify(host="codex").returncode, 0)
        self.assertNotEqual(self.run_verify(host="claude").returncode, 0)
        # Switching back to Claude adds only its missing settings.
        self.assertEqual(self.run_setup(host="claude").returncode, 0)
        self.assertEqual(self.run_verify(host="claude").returncode, 0)

    def test_codex_preserves_even_malformed_incumbent_claude_settings(self) -> None:
        self.install_sf_stub()
        settings = self.workspace / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text("USER_OWNED_MALFORMED_SETTINGS")
        result = self.run_setup(host="codex")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(settings.read_text(), "USER_OWNED_MALFORMED_SETTINGS")
        self.assertEqual(self.run_verify(host="codex").returncode, 0)

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
        original_config = json.dumps({  # json.dumps: a Windows path's backslashes need escaping in JSON
            "workspace_path": str(self.workspace.resolve()), "install_method": "plugin", "plugin_version": "older",
            "setup_completed_at": "2026-01-01T00:00:00Z", "custom": True}, separators=(",", ":")) + "\n"
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

    @stand_ins.needs_symlinks
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
            stand_ins.link_target(force_app), str(self.workspace / "missing-user-target")
        )
        self.assertFalse((self.workspace / "sfdx-project.json").exists())
        self.assertFalse(self.config.exists())

    @stand_ins.needs_symlinks
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

    @stand_ins.needs_symlinks
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

    @stand_ins.needs_symlinks
    def test_nested_scaffold_symlink_is_unverified_and_staging_is_cleaned(self) -> None:
        self.install_sf_stub(broken_force_app=True)

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SFDX_GENERATE_UNVERIFIED", result.stdout)
        self.assertFalse((self.workspace / "force-app").exists())
        self.assertFalse((self.workspace / "sfdx-project.json").exists())
        self.assertFalse(self.config.exists())
        self.assertEqual(list(self.base.glob(".scout-sfdx-*")), [])

    @stand_ins.needs_symlinks
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

    @stand_ins.needs_symlinks
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
        self.assertEqual(stand_ins.link_target(config_link), str(external_config))
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
