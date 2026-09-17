"""Local packaging and source-contract checks for Batch 6."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_manifest_json_and_required_setup_scripts(self) -> None:
        for relative in (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"):
            with self.subTest(relative=relative):
                payload = json.loads((ROOT / relative).read_text())
                self.assertIsInstance(payload, dict)
        for relative in ("scripts/setup-zshrc.sh", "scripts/setup-cli-refresh.sh"):
            with self.subTest(relative=relative):
                self.assertTrue((ROOT / relative).is_file())

    def test_shipped_scripts_have_real_shell_syntax(self) -> None:
        commands = (
            (["/bin/bash", "-n", str(ROOT / "scripts/setup-zshrc.sh")], "bash zshrc"),
            (["/bin/bash", "-n", str(ROOT / "scripts/setup-cli-refresh.sh")], "bash cli"),
            (["/bin/zsh", "-f", "-n", str(ROOT / "scripts/setup-zshrc.sh")], "zsh zshrc"),
        )
        if not Path("/bin/zsh").is_file():
            self.fail("/bin/zsh is required for the shell-repair syntax prerequisite")
        for command, label in commands:
            with self.subTest(label=label):
                result = subprocess.run(command, text=True, capture_output=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_callers_require_explicit_active_plugin_absolute_paths(self) -> None:
        zshrc = (ROOT / "prompts/setup/zshrc-block.md").read_text()
        refresh = (ROOT / "prompts/setup/refresh.md").read_text()
        self.assertIn("scripts/setup-zshrc.sh", zshrc)
        self.assertIn("scripts/setup-cli-refresh.sh", refresh)
        self.assertEqual(refresh.count('SCOUT_CLI_REFRESH_SCRIPT="/absolute/'), 2)
        self.assertEqual(
            refresh.count('/bin/bash "$SCOUT_CLI_REFRESH_SCRIPT" sf'), 1
        )
        self.assertEqual(
            refresh.count('/bin/bash "$SCOUT_CLI_REFRESH_SCRIPT" claude'), 1
        )
        for text in (zshrc, refresh):
            self.assertIn("absolute", text.lower())
            self.assertIn("unavailable", text.lower())
            self.assertNotIn('"${CLAUDE_PLUGIN_ROOT}/scripts/setup-', text)

    def test_cli_caller_blocks_execute_independently(self) -> None:
        refresh = (ROOT / "prompts/setup/refresh.md").read_text()
        blocks = re.findall(r"```bash\n(.*?)\n```", refresh, re.S)
        callers = [
            block for block in blocks if "scripts/setup-cli-refresh.sh" in block
        ]
        self.assertEqual(len(callers), 2)
        with tempfile.TemporaryDirectory(prefix="scout-caller-test-") as raw:
            base = Path(raw)
            log = base / "selectors.log"
            stub = base / "setup-cli-refresh.sh"
            stub.write_text(
                "#!/bin/bash\nprintf '%s\\n' \"$1\" >> \"$SCOUT_CALLER_LOG\"\n"
            )
            stub.chmod(0o700)
            placeholder = (
                "/absolute/path/of/active/sf-demo-scout/"
                "scripts/setup-cli-refresh.sh"
            )
            env = {
                **os.environ,
                "PATH": "/usr/bin:/bin",
                "SCOUT_CALLER_LOG": str(log),
            }
            for block in callers:
                result = subprocess.run(
                    ["/bin/bash", "-c", block.replace(placeholder, str(stub))],
                    env=env,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(log.read_text().splitlines(), ["sf", "claude"])

    def test_done_summary_keeps_three_truthful_failure_assertions(self) -> None:
        done = (ROOT / "prompts/setup/done.md").read_text()
        failed_lines = [line for line in done.splitlines() if "*_UPDATE_FAILED" in line]
        self.assertEqual(len(failed_lines), 1)
        self.assertNotIn("kept the installed one", failed_lines[0])
        self.assertIn("future refresh", failed_lines[0])

    def test_source_login_instructions_preserve_default_org_contract(self) -> None:
        """Static instruction checks; these do not prove model compliance."""
        for name, expected in (("cross-org-extract.md", 0), ("switch-org.md", 2)):
            with self.subTest(name=name):
                text = (ROOT / "prompts" / name).read_text()
                commands = [
                    line
                    for line in text.splitlines()
                    if re.match(r"^\s*sf org login web(?:\s|$)", line)
                ]
                self.assertEqual(len(commands), 2)
                self.assertEqual(
                    sum("--set-default" in line for line in commands), expected
                )

        extraction = (ROOT / "prompts" / "cross-org-extract.md").read_text()
        switching = (ROOT / "prompts" / "switch-org.md").read_text()
        self.assertEqual(extraction.count("authenticate the source org INLINE"), 1)
        self.assertNotIn("follow it ONLY through authenticating", extraction)
        self.assertIn("test.salesforce.com", extraction)
        self.assertEqual(extraction.count("login fails or the SE cancels"), 1)
        self.assertIn("cross-org extract", switching)


if __name__ == "__main__":
    unittest.main()
