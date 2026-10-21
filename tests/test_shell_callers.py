from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SHELLS = (("bash", "/bin/bash"), ("zsh", "/bin/zsh"))


def fenced_block(relative_path: str, marker: str) -> str:
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    blocks = re.findall(r"```bash\n(.*?)```", text, flags=re.DOTALL)
    matches = [block for block in blocks if marker in block]
    if len(matches) != 1:
        raise AssertionError(
            f"expected one {marker!r} Bash block in {relative_path}, found {len(matches)}"
        )
    return matches[0]


@unittest.skipUnless(all(Path(shell).exists() for _, shell in SHELLS), "runs the prompts' fences in /bin/bash and /bin/zsh")
class ShellCallerTests(unittest.TestCase):
    """Execute shipped prompt fences; no model, installer, settings, or org is used."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="scout-shell-callers-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()  # macOS temp folders sit behind the /var link
        self.workspace = self.base / "workspace"
        self.config = self.base / "config" / "config.json"
        self.plugin = self.base / "plugin"
        self.bin_dir = self.base / "bin"
        self.bin_dir.mkdir()
        self.no_python_bin = self.base / "no-python-bin"
        self.no_python_bin.mkdir()
        self.settings = self.base / "settings.json"
        self.local_settings = self.base / "settings.local.json"
        self.vscode_settings = self.base / "Code" / "User" / "settings.json"
        self.log = self.base / "calls.jsonl"
        os.symlink(sys.executable, self.bin_dir / "python3")
        os.symlink("/bin/mkdir", self.bin_dir / "mkdir")
        os.symlink("/bin/mkdir", self.no_python_bin / "mkdir")

    def environment(self, *, include_python: bool = True) -> dict[str, str]:
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment["PATH"] = str(self.bin_dir if include_python else self.no_python_bin)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["TEST_LOG"] = str(self.log)
        # The one-line gates read these seams; the real workspace and configuration are never touched.
        environment["SCOUT_WORKSPACE"] = str(self.workspace)
        environment["SCOUT_CONFIG_FILE"] = str(self.config)
        self.assertEqual(os.environ.get("HOME"), environment.get("HOME"))
        return environment

    def render(self, block: str, *, plugin: Path | None = None) -> str:
        replacements = {
            "$HOME/claude-projects/sf-demo-scout": str(self.workspace),
            "$HOME/.config/sf-demo-scout/config.json": str(self.config),
            "$HOME/.claude/settings.json": str(self.settings),
            "$HOME/.claude/settings.local.json": str(self.local_settings),
            "$HOME/Library/Application Support/Code/User/settings.json": str(
                self.vscode_settings
            ),
            "[PLUGIN_ROOT]": str(plugin or self.plugin),
            "[PLUGIN_VERSION]": "2026.09.21-test",
            "[SCOUT_HOST]": "claude",
        }
        rendered = block
        for original, replacement in replacements.items():
            rendered = rendered.replace(original, replacement)
        return rendered

    def run_block(
        self,
        block: str,
        shell: str,
        *,
        plugin: Path | None = None,
        include_python: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        arguments = [shell]
        if shell.endswith("zsh"):
            arguments.append("-f")
        return subprocess.run(
            arguments,
            input=self.render(block, plugin=plugin),
            cwd=self.base,
            env=self.environment(include_python=include_python),
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

    def make_valid_workspace(self) -> None:
        (self.workspace / "force-app").mkdir(parents=True, exist_ok=True)
        lessons = self.workspace / "orgs" / "lessons"
        lessons.mkdir(parents=True, exist_ok=True)
        (lessons / "INDEX.md").write_text("# Test lessons\n", encoding="utf-8")
        settings = self.workspace / ".claude" / "settings.json"
        settings.parent.mkdir(exist_ok=True)
        settings.write_text("{}\n", encoding="utf-8")
        (self.workspace / "sfdx-project.json").write_text(
            json.dumps(
                {
                    "packageDirectories": [{"path": "force-app", "default": True}],
                    "sourceApiVersion": "65.0",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text(
            json.dumps(
                {
                    "workspace_path": str(self.workspace.resolve()),
                    "install_method": "plugin",
                    "plugin_version": "2026.09.17-existing",
                    "setup_completed_at": "2026-09-17T12:00:00Z",
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def test_workspace_bootstrap_accepts_real_valid_workspace_in_bash_and_zsh(self) -> None:
        block = fenced_block("prompts/workspace-bootstrap.md", "gate --host")
        self.assertEqual(len(block.strip().splitlines()), 1)  # one command: the same in sh, PowerShell and cmd.exe
        self.make_valid_workspace()

        for name, shell in SHELLS:
            with self.subTest(shell=name):
                result = self.run_block(block, shell, plugin=ROOT)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertIn("WORKSPACE_READY", result.stdout)
                self.assertIn("STATE=OK WORKSPACE=%s" % self.workspace.resolve(), result.stdout)
                self.assertNotIn("STATE=CHECK_FAILED", result.stdout)

    def test_workspace_bootstrap_reports_failures_and_never_creates_workspace(self) -> None:
        block = fenced_block("prompts/workspace-bootstrap.md", "gate --host")

        for name, shell in SHELLS:
            with self.subTest(shell=name, case="missing-python"):
                result = self.run_block(block, shell, plugin=ROOT, include_python=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("STATE=OK", result.stdout)
                self.assertFalse(self.workspace.exists())

            with self.subTest(shell=name, case="missing-helper"):
                result = self.run_block(block, shell)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("STATE=OK", result.stdout)
                self.assertIn("setup-workspace.py", result.stderr)
                self.assertFalse(self.workspace.exists())

            with self.subTest(shell=name, case="missing-workspace"):
                result = self.run_block(block, shell, plugin=ROOT)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("WORKSPACE_INVALID", result.stdout)
                self.assertIn("STATE=CHECK_FAILED", result.stdout)
                self.assertFalse(self.workspace.exists())

        self.workspace.write_text("not a directory\n", encoding="utf-8")
        for name, shell in SHELLS:
            with self.subTest(shell=name, case="workspace-is-file"):
                result = self.run_block(block, shell, plugin=ROOT)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("WORKSPACE_INVALID", result.stdout)
                self.assertIn("STATE=CHECK_FAILED", result.stdout)
        self.workspace.unlink()

        self.make_valid_workspace()
        self.config.unlink()
        for name, shell in SHELLS:
            with self.subTest(shell=name, case="missing-config"):
                result = self.run_block(block, shell, plugin=ROOT)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("CONFIG_INVALID", result.stdout)
                self.assertIn("STATE=CHECK_FAILED", result.stdout)

        self.config.mkdir()
        for name, shell in SHELLS:
            with self.subTest(shell=name, case="config-is-directory"):
                result = self.run_block(block, shell, plugin=ROOT)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("CONFIG_INVALID", result.stdout)
                self.assertIn("STATE=CHECK_FAILED", result.stdout)
        self.config.rmdir()

        self.config.write_text("{malformed\n", encoding="utf-8")
        for name, shell in SHELLS:
            with self.subTest(shell=name, case="malformed-config"):
                result = self.run_block(block, shell, plugin=ROOT)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("CONFIG_INVALID", result.stdout)
                self.assertIn("STATE=CHECK_FAILED", result.stdout)

        self.make_valid_workspace()
        (self.workspace / "orgs" / "lessons" / "INDEX.md").unlink()
        for name, shell in SHELLS:
            with self.subTest(shell=name, case="missing-artifact"):
                result = self.run_block(block, shell, plugin=ROOT)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("LESSONS_INVALID", result.stdout)
                self.assertIn("STATE=CHECK_FAILED", result.stdout)

    def test_workspace_bootstrap_preserves_nonzero_verifier_output_and_status(self) -> None:
        block = fenced_block("prompts/workspace-bootstrap.md", "gate --host")
        self.make_valid_workspace()
        helper = self.plugin / "scripts" / "setup-workspace.py"
        helper.parent.mkdir(parents=True)
        helper.write_text(
            """import sys
print("VERIFIER_STDOUT_DETAIL")
print("VERIFIER_STDERR_DETAIL", file=sys.stderr)
raise SystemExit(37)
""",
            encoding="utf-8",
        )

        for name, shell in SHELLS:
            with self.subTest(shell=name):
                result = self.run_block(block, shell)
                self.assertEqual(result.returncode, 37)
                self.assertIn("VERIFIER_STDOUT_DETAIL", result.stdout)
                self.assertIn("VERIFIER_STDERR_DETAIL", result.stderr)
                self.assertNotIn("STATE=OK", result.stdout)

    def test_setup_state_detection_is_truthful_in_bash_and_zsh(self) -> None:
        block = fenced_block("skills/scout-setup/SKILL.md", "state --host")
        self.make_valid_workspace()

        for name, shell in SHELLS:
            with self.subTest(shell=name, case="valid"):
                result = self.run_block(block, shell, plugin=ROOT)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertIn("WORKSPACE_READY", result.stdout)
                self.assertIn("STATE=REFRESH", result.stdout)

        self.config.write_text("{malformed\n", encoding="utf-8")
        for name, shell in SHELLS:
            with self.subTest(shell=name, case="invalid"):
                result = self.run_block(block, shell, plugin=ROOT)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertIn("CONFIG_INVALID", result.stdout)
                self.assertIn("STATE=FRESH", result.stdout)

        for name, shell in SHELLS:
            with self.subTest(shell=name, case="missing-python"):  # the skill reads a Python that can't start as FRESH
                result = self.run_block(block, shell, plugin=ROOT, include_python=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("STATE=REFRESH", result.stdout)

    def test_fresh_install_workspace_setup_keeps_exact_arguments(self) -> None:
        setup_block = fenced_block("prompts/setup/fresh-install.md", 'setup-workspace.py" setup')
        self.assertEqual(len(setup_block.strip().splitlines()), 1)  # one command, the same in every shell
        helper = self.plugin / "scripts" / "setup-workspace.py"
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text(
            """import json, os, sys
with open(os.environ["TEST_LOG"], "w", encoding="utf-8") as stream:
    json.dump(sys.argv[1:], stream)
print("WORKSPACE_READY")
""",
            encoding="utf-8",
        )
        template = self.plugin / "assets" / "workspace-settings.template.json"
        template.parent.mkdir()
        template.write_text("{}\n", encoding="utf-8")

        expected = [  # the workspace and configuration come from the helper's own defaults
            "setup",
            "--template",
            str(template),
            "--plugin-version",
            "2026.09.21-test",
            "--host",
            "claude",
        ]
        for name, shell in SHELLS:
            with self.subTest(shell=name, block="workspace"):
                result = self.run_block(setup_block, shell)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertEqual(json.loads(self.log.read_text(encoding="utf-8")), expected)

    def test_marketplace_auto_update_fills_only_a_missing_choice(self) -> None:
        block = fenced_block("prompts/setup/fresh-install.md", "marketplace-autoupdate --name scout")
        self.assertEqual(len(block.strip().splitlines()), 1)
        cases = (
            ({"source": {"source": "github"}}, "AUTOUPDATE_SET[settings.json]", True),
            ({"source": {"source": "github"}, "autoUpdate": False}, "AUTOUPDATE_LEFT_AS_CHOSEN[settings.json]", False),
            ({"source": {"source": "github"}, "autoUpdate": True}, "AUTOUPDATE_ALREADY[settings.json]", True),
        )
        for entry, outcome, expected in cases:
            for name, shell in SHELLS:
                with self.subTest(outcome=outcome, shell=name):
                    before = json.dumps({"extraKnownMarketplaces": {"scout": entry}}, indent=2) + "\n"
                    self.settings.write_text(before, encoding="utf-8")
                    result = self.run_block(block, shell, plugin=ROOT)
                    self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                    self.assertEqual(result.stdout.strip(), outcome)
                    after = json.loads(self.settings.read_text(encoding="utf-8"))
                    self.assertIs(after["extraKnownMarketplaces"]["scout"]["autoUpdate"], expected)
                    if not outcome.startswith("AUTOUPDATE_SET"):
                        self.assertEqual(self.settings.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
