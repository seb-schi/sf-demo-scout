"""Hermetic regressions for setup MCP readiness reporting."""

from __future__ import annotations

import os
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
STATUS_SCRIPT = ROOT / "scripts" / "setup-mcp-status.py"


class McpStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="scout-mcp-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def run_status(
        self,
        provider: str,
        output: str,
        *,
        returncode: int = 0,
        delay: str = "",
        invalid_utf8: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        bin_dir = self.base / f"bin-{provider}-{len(list(self.base.iterdir()))}"
        bin_dir.mkdir()
        claude = bin_dir / "claude"
        claude.write_text(
            "#!/bin/bash\n"
            "if [ \"$*\" != \"mcp list\" ]; then echo 'unexpected claude arguments' >&2; exit 97; fi\n"
            "[ -n \"$MCP_LIST_DELAY\" ] && sleep \"$MCP_LIST_DELAY\"\n"
            "if [ \"$MCP_LIST_INVALID_UTF8\" = 1 ]; then printf '\\377\\n'; "
            "else printf '%s' \"$MCP_LIST_OUTPUT\"; fi\n"
            "exit \"$MCP_LIST_RC\"\n"
        )
        claude.chmod(0o700)
        (bin_dir / "python3").symlink_to(sys.executable)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.update(
            PATH=f"{bin_dir}:/usr/bin:/bin",
            MCP_LIST_OUTPUT=output,
            MCP_LIST_RC=str(returncode),
            MCP_LIST_DELAY=delay,
            MCP_LIST_INVALID_UTF8="1" if invalid_utf8 else "0",
            PYTHONDONTWRITEBYTECODE="1",
        )
        return subprocess.run(
            [str(STATUS_SCRIPT), provider],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_list_failure_and_no_match_never_report_absent(self) -> None:
        cases = (
            ("slack", "https://private.example/token=secret", 9, "registration=unknown"),
            ("google", "unrelated: command --password hunter2 - Connected\n", 0, "registration=not_observed"),
            ("salesforce-docs", "Checking MCP server health...\n", 0, "registration=unknown"),
        )
        for provider, output, rc, expected in cases:
            with self.subTest(provider=provider):
                result = self.run_status(provider, output, returncode=rc)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)
                self.assertNotIn("absent", result.stdout.lower())
                for secret in ("private.example", "token", "password", "hunter2"):
                    self.assertNotIn(secret, result.stdout)

    def test_aliases_and_known_signatures_are_registered(self) -> None:
        cases = (
            ("slack", "plugin:company:slack: https://mcp.slack.com/mcp (HTTP) - ✔ Connected\n", "transport=connected"),
            ("google", "google_workspace: /opt/mcp-adaptor serve --server google_workspace - ! Needs authentication\n", "transport=authentication_required"),
            ("salesforce-docs", "plugin_sf-demo-scout_salesforce_docs: custom-launcher - ✘ Failed to connect\n", "transport=failed"),
        )
        for provider, output, transport in cases:
            with self.subTest(provider=provider):
                result = self.run_status(provider, output)
                self.assertIn("registration=registered", result.stdout)
                self.assertIn(transport, result.stdout)
                self.assertNotIn("http", result.stdout.lower())
                self.assertNotIn("/opt/", result.stdout)

    def test_disabled_pending_and_unknown_transport_stay_distinct(self) -> None:
        cases = (
            ("slack", "slack: https://example.invalid - ⊘ Disabled for this project (re-enable via /mcp)\n", "disabled"),
            ("google", "google-workspace: command - ⏸ Pending approval (run claude to approve)\n", "pending"),
            ("salesforce-docs", "salesforce_docs: surprising future state\n", "unknown"),
        )
        for provider, output, state in cases:
            with self.subTest(provider=provider):
                result = self.run_status(provider, output)
                self.assertIn("registration=registered", result.stdout)
                self.assertIn(f"transport={state}", result.stdout)

    def test_multiple_matches_report_ambiguity_without_echoing_entries(self) -> None:
        output = (
            "slack: https://mcp.slack.com/mcp - ✓ Connected\n"
            "plugin:team:slack: command --secret value - Disabled\n"
        )
        result = self.run_status("slack", output)
        self.assertIn("registration=ambiguous", result.stdout)
        self.assertIn("transport=unknown", result.stdout)
        self.assertNotIn("secret", result.stdout)

    def test_signature_spoofs_and_argument_words_do_not_match(self) -> None:
        cases = (
            ("slack", "slack-unrelated: https://mcp.slack.com.evil/mcp - Connected\n"),
            ("google", "other: /opt/mcp-adaptor serve --server another --connected - Disconnected\n"),
            ("google", "other: /opt/mcp-adaptor serve --server Google_Workspace - Connected\n"),
            ("salesforce-docs", "Warning: could not read https://salesforce-docs-76258744c9d7.herokuapp.com/api/mcp - Connected\n"),
            ("salesforce-docs", "other: https://salesforce-docs-76258744c9d7.herokuapp.com/API/MCP - Connected\n"),
        )
        for provider, output in cases:
            with self.subTest(provider=provider):
                result = self.run_status(provider, output)
                self.assertIn("registration=not_observed", result.stdout)
                self.assertIn("transport=unknown", result.stdout)

    def test_timeout_and_invalid_utf8_degrade_to_unknown(self) -> None:
        spec = importlib.util.spec_from_file_location("setup_mcp_status", STATUS_SCRIPT)
        self.assertIsNotNone(spec and spec.loader)
        module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(module)
        with mock.patch.object(module.shutil, "which", return_value="/stub/claude"), \
             mock.patch.object(
                 module.subprocess,
                 "run",
                 side_effect=subprocess.TimeoutExpired(["claude", "mcp", "list"], 10),
             ):
            self.assertEqual(module.report("slack"), ("unknown", "unknown"))

        result = self.run_status("slack", "", invalid_utf8=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("registration=unknown transport=unknown", result.stdout)


if __name__ == "__main__":
    unittest.main()
