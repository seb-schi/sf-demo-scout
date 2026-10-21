"""Hermetic regressions for setup MCP readiness reporting."""

from __future__ import annotations

import os
import json
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import stand_ins


ROOT = Path(__file__).resolve().parents[1]
STATUS_SCRIPT = ROOT / "scripts" / "setup-mcp-status.py"
# Stands in for the host's CLI: `mcp list` answers with MCP_LIST_OUTPUT, or with bytes that aren't UTF-8.
HOST_CLI = r"""import os, sys
if sys.argv[1:] != %r:
    sys.stderr.write("unexpected arguments\n")
    sys.exit(97)
if os.environ.get("MCP_LIST_DELAY"):
    import time
    time.sleep(float(os.environ["MCP_LIST_DELAY"]))
sys.stdout.buffer.write(b"\xff\n" if os.environ.get("MCP_LIST_INVALID_UTF8") == "1"
                        else os.environ["MCP_LIST_OUTPUT"].encode("utf-8"))
sys.stdout.flush()
sys.exit(int(os.environ["MCP_LIST_RC"]))
"""


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
        expected_args = ["mcp", "list", "--json"] if host == "codex" else ["mcp", "list"]
        stand_ins.tool(bin_dir, host, HOST_CLI % (expected_args,))
        if not stand_ins.WINDOWS:  # the helper's shebang finds python3 on the PATH; Windows runs no shebang
            (bin_dir / "python3").symlink_to(sys.executable)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.update(
            PATH=os.pathsep.join((str(bin_dir), "/usr/bin", "/bin")),
            MCP_LIST_OUTPUT=output,
            MCP_LIST_RC=str(returncode),
            MCP_LIST_DELAY=delay,
            MCP_LIST_INVALID_UTF8="1" if invalid_utf8 else "0",
            PYTHONDONTWRITEBYTECODE="1",
        )
        return subprocess.run(
            [*([sys.executable] if stand_ins.WINDOWS else []), str(STATUS_SCRIPT), "--host", host, provider],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_list_failure_and_no_match_never_report_absent(self) -> None:
        cases = (
            ("https://private.example/token=secret", 9, "registration=unknown"),
            ("unrelated: command --password hunter2 - Connected\n", 0, "registration=not_observed"),
            ("Checking MCP server health...\n", 0, "registration=unknown"),
        )
        for output, rc, expected in cases:
            with self.subTest(expected=expected, rc=rc):
                result = self.run_status("salesforce-docs", output, returncode=rc)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)
                self.assertNotIn("absent", result.stdout.lower())
                for secret in ("private.example", "token", "password", "hunter2"):
                    self.assertNotIn(secret, result.stdout)

    def test_aliases_and_known_signatures_are_registered(self) -> None:
        cases = (
            ("plugin:company:salesforce-docs: https://salesforce-docs-76258744c9d7.herokuapp.com/api/mcp (HTTP) - ✔ Connected\n", "transport=connected"),
            ("custom: https://salesforce-docs-76258744c9d7.herokuapp.com/api/mcp - ! Needs authentication\n", "transport=authentication_required"),
            ("plugin_sf-demo-scout_salesforce_docs: /opt/custom-launcher - ✘ Failed to connect\n", "transport=failed"),
        )
        for output, transport in cases:
            with self.subTest(transport=transport):
                result = self.run_status("salesforce-docs", output)
                self.assertIn("registration=registered", result.stdout)
                self.assertIn(transport, result.stdout)
                self.assertNotIn("http", result.stdout.lower())
                self.assertNotIn("/opt/", result.stdout)

    def test_disabled_pending_and_unknown_transport_stay_distinct(self) -> None:
        cases = (
            ("salesforce-docs: https://example.invalid - ⊘ Disabled for this project (re-enable via /mcp)\n", "disabled"),
            ("salesforce_docs: command - ⏸ Pending approval (run claude to approve)\n", "pending"),
            ("salesforce_docs: surprising future state\n", "unknown"),
        )
        for output, state in cases:
            with self.subTest(state=state):
                result = self.run_status("salesforce-docs", output)
                self.assertIn("registration=registered", result.stdout)
                self.assertIn(f"transport={state}", result.stdout)

    def test_multiple_matches_report_ambiguity_without_echoing_entries(self) -> None:
        output = (
            "salesforce-docs: https://salesforce-docs-76258744c9d7.herokuapp.com/api/mcp - ✓ Connected\n"
            "plugin:team:salesforce-docs: command --secret value - Disabled\n"
        )
        result = self.run_status("salesforce-docs", output)
        self.assertIn("registration=ambiguous", result.stdout)
        self.assertIn("transport=unknown", result.stdout)
        self.assertNotIn("secret", result.stdout)

    def test_signature_spoofs_and_argument_words_do_not_match(self) -> None:
        cases = (
            "salesforce-docs-unrelated: https://salesforce-docs-76258744c9d7.herokuapp.com.evil/api/mcp - Connected\n",
            "other: /opt/launcher serve --server salesforce-docs --connected - Connected\n",
            "other: http://salesforce-docs-76258744c9d7.herokuapp.com/api/mcp - Connected\n",
            "other: https://salesforce-docs-76258744c9d7.herokuapp.com/api/mcp?token=x - Connected\n",
            "Warning: could not read https://salesforce-docs-76258744c9d7.herokuapp.com/api/mcp - Connected\n",
            "other: https://salesforce-docs-76258744c9d7.herokuapp.com/API/MCP - Connected\n",
        )
        for output in cases:
            with self.subTest(output=output):
                result = self.run_status("salesforce-docs", output)
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
            result = module.report("salesforce-docs", "claude")
            self.assertEqual(result["registration"], "unknown")
            self.assertEqual(result["transport"], "unknown")

        result = self.run_status("salesforce-docs", "", invalid_utf8=True)
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
            ({"CURSOR_AGENT": "1"}, "cursor"),
            ({"CURSOR_AGENT": "1", "CLAUDECODE": "1"}, "unknown"),
            ({"SCOUT_HOST": "cursor"}, "cursor"),
        ):
            with self.subTest(env=env), mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch.object(module.shutil, "which") as which:
                self.assertEqual(module.active_host(), expected)
                if expected == "unknown":
                    self.assertEqual(module.report("salesforce-docs")["reason"], "unknown_host")
                which.assert_not_called()
                self.assertEqual(module.active_host("codex"), "codex")

    def test_missing_codex_never_falls_back_to_connected_claude(self) -> None:
        module = self.load_module()
        with mock.patch.object(module.shutil, "which", side_effect=lambda name: "/claude" if name == "claude" else None) as which, \
             mock.patch.object(module.subprocess, "run") as run:
            self.assertEqual(module.report("salesforce-docs", "codex")["reason"], "missing_cli")
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
        for name, reason in (("salesforce-docs", "enabled"), ("Salesforce Docs", "invalid_server_name")):
            with self.subTest(name=name):
                payload = [{"name": name, "enabled": True, "disabled_reason": None,
                            "transport": {"url": "https://salesforce-docs-76258744c9d7.herokuapp.com/api/mcp"},
                            "auth_status": "bearer_token", "tools": ["salesforce_docs_search"]}]
                result = self.run_status("salesforce-docs", json.dumps(payload), host="codex")
                self.assertIn("registration=registered transport=unknown", result.stdout)
                self.assertIn(f"policy=permitted reason={reason} tools=unknown", result.stdout)
                self.assertNotIn("connected", result.stdout)
                self.assertNotIn("bearer_token", result.stdout)

    def test_codex_disabled_malformed_and_ambiguous_states(self) -> None:
        for payload, expected in (
            ([], "registration=not_observed"),
            ({"servers": []}, "reason=malformed_listing"),
            ([42], "reason=malformed_listing"),
            ([{"name": "salesforce-docs", "enabled": "false"}], "reason=malformed_listing"),
            ([{"name": "salesforce-docs", "enabled": False}], "reason=disabled_unknown"),
            ([{"name": "salesforce-docs", "enabled": False, "disabled_reason": "config"}], "reason=user_disabled"),
            ([{"name": "salesforce-docs", "enabled": False, "disabled_reason": "UNKNOWN_SECRET"}], "reason=disabled_unknown"),
            ([{"name": "salesforce-docs"}, {"name": "plugin:team:salesforce_docs"}], "registration=ambiguous"),
        ):
            with self.subTest(expected=expected, payload=payload):
                result = self.run_status("salesforce-docs", json.dumps(payload), host="codex")
                self.assertIn(expected, result.stdout)
                self.assertNotIn("UNKNOWN_SECRET", result.stdout)
        result = self.run_status("salesforce-docs", "{not json", host="codex")
        self.assertIn("reason=malformed_listing", result.stdout)

    def test_codex_signatures_and_spoofs(self) -> None:
        cases = (
            ({"url": "https://salesforce-docs-76258744c9d7.herokuapp.com/api/mcp"}, "registered"),
            ({"url": "https://salesforce-docs-76258744c9d7.herokuapp.com.evil/api/mcp"}, "not_observed"),
            ({"url": "https://salesforce-docs-76258744c9d7.herokuapp.com:8443/api/mcp"}, "not_observed"),
            ({"command": "/opt/launcher", "args": ["serve", "--server", "salesforce-docs"]}, "not_observed"),
        )
        for transport, expected in cases:
            with self.subTest(transport=transport):
                payload = [{"name": "custom", "enabled": True, "transport": transport}]
                result = self.run_status("salesforce-docs", json.dumps(payload), host="codex")
                self.assertIn(f"registration={expected}", result.stdout)

    def test_only_selected_host_runs_in_current_working_directory(self) -> None:
        module = self.load_module()
        def run(command, **kwargs):
            if command[0] == "/stub/claude":
                return subprocess.CompletedProcess(command, 0, "salesforce-docs: command - Connected", "")
            self.assertEqual(command, ["/stub/codex", "mcp", "list", "--json"])
            self.assertNotIn("cwd", kwargs)  # inherit the caller's project policy
            return subprocess.CompletedProcess(command, 0, json.dumps([
                {"name": "salesforce-docs", "enabled": False, "disabled_reason": "requirements (Baseline)"}
            ]), "STDERR_SECRET")
        with mock.patch.object(module.shutil, "which", side_effect=lambda name: f"/stub/{name}"), \
             mock.patch.object(module.subprocess, "run", side_effect=run):
            self.assertEqual(module.report("salesforce-docs", "claude")["transport"], "connected")
            self.assertEqual(module.report("salesforce-docs", "codex")["policy"], "blocked")

    def test_cursor_registration_comes_from_its_mcp_files_without_a_cli(self) -> None:
        module = self.load_module()
        home, project = self.base / "home", self.base / "project"
        (home / ".cursor").mkdir(parents=True)
        (project / ".cursor").mkdir(parents=True)
        docs = "https://salesforce-docs-76258744c9d7.herokuapp.com/api/mcp"
        cases = (
            ({}, {}, "registration=not_observed"),
            ({"mcpServers": {"salesforce-docs": {"url": docs}}}, {}, "registration=registered"),
            ({"mcpServers": {"docs": {"url": docs}}}, {}, "registration=registered"),
            ({"mcpServers": {"salesforce-docs": {"url": docs}}}, {"mcpServers": {"salesforce_docs": {"url": docs}}},
             "registration=ambiguous"),
            ({"mcpServers": []}, {}, "reason=malformed_listing"),
        )
        for user, local, expected in cases:
            with self.subTest(expected=expected, user=user, local=local):
                (home / ".cursor" / "mcp.json").write_text(json.dumps(user))
                (project / ".cursor" / "mcp.json").write_text(json.dumps(local))
                with mock.patch.object(module.Path, "home", return_value=home), \
                     mock.patch.object(module.shutil, "which") as which, mock.patch.object(module.subprocess, "run") as run:
                    status = module.cursor_status(module.unknown_status("salesforce-docs", "cursor", "unknown_host"), project)
                    line = " ".join(f"{k}={v}" for k, v in status.items())
                    self.assertIn(expected, line)
                    self.assertIn("transport=unknown", line)  # Cursor reports the connection itself
                    which.assert_not_called(); run.assert_not_called()
        (home / ".cursor" / "mcp.json").write_text(json.dumps({"mcpServers": {"salesforce-docs": {"url": docs}}}))
        with mock.patch.object(module.Path, "home", return_value=home):  # started in the home folder: one file, read once
            status = module.cursor_status(module.unknown_status("salesforce-docs", "cursor", "unknown_host"), home)
        self.assertEqual(status["registration"], "registered")

    def test_retired_providers_are_no_longer_probed(self) -> None:
        # 2.4 ships no Slack or Google setup, and the DX server left in 2.1.5.
        aliases = self.load_module().ALIASES
        self.assertEqual(set(aliases), {"salesforce-docs"})
        for provider in ("salesforce-dx", "slack", "google"):
            with self.subTest(provider=provider):
                result = self.run_status(provider, "[]")
                self.assertEqual(result.returncode, 2)
                self.assertIn("invalid choice", result.stderr)


if __name__ == "__main__":
    unittest.main()
