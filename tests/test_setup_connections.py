"""Hermetic regressions for setup MCP readiness reporting."""

from __future__ import annotations

import os
import json
import io
import importlib.util
from contextlib import redirect_stdout
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
        host: str = "claude",
    ) -> subprocess.CompletedProcess[str]:
        bin_dir = self.base / f"bin-{provider}-{len(list(self.base.iterdir()))}"
        bin_dir.mkdir()
        claude = bin_dir / host
        expected_args = "mcp list --json" if host == "codex" else "mcp list"
        claude.write_text(
            "#!/bin/bash\n"
            f"if [ \"$*\" != \"{expected_args}\" ]; then echo 'unexpected arguments' >&2; exit 97; fi\n"
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
            [str(STATUS_SCRIPT), "--host", host, provider],
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
            result = module.report("slack", "claude")
            self.assertEqual(result["registration"], "unknown")
            self.assertEqual(result["transport"], "unknown")

        result = self.run_status("slack", "", invalid_utf8=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("registration=unknown transport=unknown", result.stdout)

    def load_module(self):
        spec = importlib.util.spec_from_file_location("setup_mcp_status", STATUS_SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_host_selection_never_uses_installed_clis(self) -> None:
        module = self.load_module()
        for env, expected in (
            ({}, "unknown"),
            ({"CODEX_THREAD_ID": "task"}, "codex"),
            ({"CLAUDECODE": "1"}, "claude"),
            ({"CODEX_THREAD_ID": "task", "CLAUDECODE": "1"}, "unknown"),
            ({"SCOUT_HOST": "other", "CLAUDECODE": "1"}, "unknown"),
        ):
            with self.subTest(env=env), mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch.object(module.shutil, "which") as which:
                self.assertEqual(module.active_host(), expected)
                if expected == "unknown":
                    self.assertEqual(module.report("slack")["reason"], "unknown_host")
                which.assert_not_called()
                self.assertEqual(module.active_host("codex"), "codex")

    def test_missing_codex_never_falls_back_to_connected_claude(self) -> None:
        module = self.load_module()
        with mock.patch.object(module.shutil, "which", side_effect=lambda name: "/claude" if name == "claude" else None) as which, \
             mock.patch.object(module.subprocess, "run") as run:
            self.assertEqual(module.report("slack", "codex")["reason"], "missing_cli")
            which.assert_called_once_with("codex")
            run.assert_not_called()

    def test_codex_policy_block_is_distinct_and_secret_free(self) -> None:
        policy_id = "bfe97950-5fbb-4d44-9c58-fe5f878da066"
        payload = [{"name": "salesforce-docs", "enabled": False,
                    "disabled_reason": f"requirements (enterprise-managed requirements Baseline ({policy_id}))",
                    "transport": {"url": "https://private.example/URL_SECRET",
                                  "http_headers": {"Authorization": "HEADER_SECRET"},
                                  "env": {"TOKEN": "ENV_SECRET"},
                                  "args": ["ARG_SECRET"]}}]
        result = self.run_status("salesforce-docs", json.dumps(payload), host="codex")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("registration=registered transport=disabled", result.stdout)
        self.assertIn("host=codex policy=blocked reason=managed_requirements", result.stdout)
        self.assertIn(f"policy_id={policy_id}", result.stdout)
        for secret in ("URL_SECRET", "HEADER_SECRET", "ENV_SECRET", "ARG_SECRET", "private.example"):
            self.assertNotIn(secret, result.stdout + result.stderr)

    def test_codex_enabled_does_not_prove_startup_auth_or_tools(self) -> None:
        for name, reason in (("Salesforce_DX", "enabled"), ("Salesforce DX", "invalid_server_name")):
            with self.subTest(name=name):
                payload = [{"name": name, "enabled": True, "disabled_reason": None,
                            "auth_status": "bearer_token", "tools": ["run_soql_query"]}]
                result = self.run_status("salesforce-dx", json.dumps(payload), host="codex")
                self.assertIn("registration=registered transport=unknown", result.stdout)
                self.assertIn(f"policy=permitted reason={reason} tools=unknown", result.stdout)
                self.assertNotIn("connected", result.stdout)
                self.assertNotIn("bearer_token", result.stdout)

    def test_codex_disabled_malformed_and_ambiguous_states(self) -> None:
        for payload, expected in (
            ([], "registration=not_observed"),
            ({"servers": []}, "reason=malformed_listing"),
            ([42], "reason=malformed_listing"),
            ([{"name": "slack", "enabled": "false"}], "reason=malformed_listing"),
            ([{"name": "slack", "enabled": False}], "reason=disabled_unknown"),
            ([{"name": "slack", "enabled": False, "disabled_reason": "config"}], "reason=user_disabled"),
            ([{"name": "slack", "enabled": False, "disabled_reason": "UNKNOWN_SECRET"}], "reason=disabled_unknown"),
            ([{"name": "slack"}, {"name": "plugin:team:slack"}], "registration=ambiguous"),
        ):
            with self.subTest(expected=expected):
                result = self.run_status("slack", json.dumps(payload), host="codex")
                self.assertIn(expected, result.stdout)
                self.assertNotIn("UNKNOWN_SECRET", result.stdout)
        result = self.run_status("slack", "{not json", host="codex")
        self.assertIn("reason=malformed_listing", result.stdout)

    def test_codex_signatures_and_spoofs(self) -> None:
        cases = (
            ("slack", {"url": "https://mcp.slack.com/mcp"}, "registered"),
            ("slack", {"url": "https://mcp.slack.com.evil/mcp"}, "not_observed"),
            ("google", {"command": "/opt/mcp-adaptor", "args": ["serve", "--server", "google_workspace"]}, "registered"),
            ("google", {"command": "/opt/mcp-adaptor", "args": ["serve", "--server", "other"]}, "not_observed"),
        )
        for provider, transport, expected in cases:
            with self.subTest(provider=provider, transport=transport):
                payload = [{"name": "custom", "enabled": True, "transport": transport}]
                result = self.run_status(provider, json.dumps(payload), host="codex")
                self.assertIn(f"registration={expected}", result.stdout)

    def test_only_selected_host_runs_in_current_working_directory(self) -> None:
        module = self.load_module()
        def run(command, **kwargs):
            if command[0] == "/stub/claude":
                return subprocess.CompletedProcess(command, 0, "slack: command - Connected", "")
            self.assertEqual(command, ["/stub/codex", "mcp", "list", "--json"])
            self.assertNotIn("cwd", kwargs)  # inherit the caller's project policy
            return subprocess.CompletedProcess(command, 0, json.dumps([
                {"name": "slack", "enabled": False, "disabled_reason": "requirements (Baseline)"}
            ]), "STDERR_SECRET")
        with mock.patch.object(module.shutil, "which", side_effect=lambda name: f"/stub/{name}"), \
             mock.patch.object(module.subprocess, "run", side_effect=run):
            self.assertEqual(module.report("slack", "claude")["transport"], "connected")
            self.assertEqual(module.report("slack", "codex")["policy"], "blocked")

    def test_prefix_repair_requires_explicit_claude_selection(self) -> None:
        script = ROOT / "scripts/repair-mcp-prefixes.py"
        for args in ([], ["--host", "codex"], ["--host", "unknown"]):
            with self.subTest(args=args):
                spec = importlib.util.spec_from_file_location("repair_prefixes", script)
                module = importlib.util.module_from_spec(spec)
                output = io.StringIO()
                # Even a broken/missing guard must never reach real home files.
                with mock.patch.object(sys, "argv", [str(script), *args]), \
                     mock.patch.object(os.path, "expanduser", side_effect=AssertionError("unexpected home access")), \
                     redirect_stdout(output), self.assertRaises(SystemExit) as stopped:
                    spec.loader.exec_module(module)
                self.assertEqual(stopped.exception.code, 0)
                self.assertEqual(
                    output.getvalue(),
                    "MCP_PREFIX_SKIPPED (Claude-only repair; explicit --host claude required)\n",
                )

    def test_maintainer_uninstall_cannot_target_claude_implicitly(self) -> None:
        for args in ([], ["--host", "codex"], ["--host", "unknown"]):
            with self.subTest(args=args):
                result = subprocess.run(
                    ["/bin/bash", str(ROOT / "scripts/scout-uninstall.sh"), *args],
                    # A guard regression cannot invoke rm/python against HOME.
                    env={**os.environ, "PATH": str(self.base / "no-tools")},
                    text=True, capture_output=True, check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(result.stdout.startswith("UNINSTALL_SKIPPED:"))
                self.assertNotIn("Removing", result.stdout)


if __name__ == "__main__":
    unittest.main()
