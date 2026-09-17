"""Offline integration tests for the shipped Scout startup hook."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "session-startup.sh"
HELPER = ROOT / "scripts" / "startup-evidence.py"
SLUGIFY = ROOT / "scripts" / "slugify.py"


class StartupFixture:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.workspace = base / "workspace"
        self.workspace.mkdir()
        self.cache = base / "cache"
        self.runtime = base / "runtime"
        self.settings = base / "settings.json"
        self.scout_config = base / "config.json"
        self.fixtures = base / "fixtures"
        self.fixtures.mkdir()
        self.bin = base / "bin"
        self.bin.mkdir()
        (self.bin / "python3").symlink_to(sys.executable)
        self.settings.write_text('{"env":{"ANTHROPIC_AUTH_TOKEN":"synthetic"}}')
        self.scout_config.write_text("{}")
        self.log = base / "calls.log"
        self._write_cli_stubs()
        self.write_config("QA A")
        self.write_list([{"alias": "QA A", "username": "qa-a@example.invalid"}])
        self.write_display("QA A", username="qa-a@example.invalid")
        self.write_mcp("slack: https://mcp.slack.com - ✓ Connected\n")

    def _write_cli_stubs(self) -> None:
        sf = self.bin / "sf"
        sf.write_text(
            """#!/bin/bash
set -u
kind=unknown
case "$1 $2" in
  "config get") kind=config ;;
  "org list") kind=list ;;
  "org display") kind=display ;;
esac
printf '%s\n' "$kind" >> "$SCOUT_FIXTURE_LOG"
mode_file="$SCOUT_FIXTURE_DIR/$kind.mode"
mode=ok
[ ! -f "$mode_file" ] || mode=$(cat "$mode_file")
case "$mode" in
  signal) kill -TERM $$ ;;
  timeout) sleep 5 ;;
  exit:*) exit "${mode#exit:}" ;;
esac
cat "$SCOUT_FIXTURE_DIR/$kind.json"
"""
        )
        sf.chmod(0o700)
        claude = self.bin / "claude"
        claude.write_text(
            """#!/bin/bash
set -u
printf '%s\n' mcp >> "$SCOUT_FIXTURE_LOG"
mode=ok
[ ! -f "$SCOUT_FIXTURE_DIR/mcp.mode" ] || mode=$(cat "$SCOUT_FIXTURE_DIR/mcp.mode")
case "$mode" in
  timeout) sleep 5 ;;
  exit:*) exit "${mode#exit:}" ;;
esac
cat "$SCOUT_FIXTURE_DIR/mcp.txt"
"""
        )
        claude.chmod(0o700)

    def write_config(self, target: str | None, *, malformed: bool = False) -> None:
        if malformed:
            body = "{not-json"
        else:
            result = [{"name": "target-org", "value": target}]
            body = json.dumps({"status": 0, "result": result})
        (self.fixtures / "config.json").write_text(body)

    def write_list(self, orgs: list[dict[str, str]], *, extra: dict | None = None) -> None:
        result = {"nonScratchOrgs": orgs, "scratchOrgs": []}
        if extra:
            result.update(extra)
        (self.fixtures / "list.json").write_text(
            json.dumps({"status": 0, "result": result})
        )

    def write_display(
        self,
        target: str,
        *,
        username: str,
        connected_status: str = "Connected",
        extra: dict | None = None,
    ) -> None:
        result = {
            "username": username,
            "id": "00D-SYNTHETIC",
            "instanceUrl": "https://example.invalid",
            "connectedStatus": connected_status,
        }
        if extra:
            result.update(extra)
        (self.fixtures / "display.json").write_text(
            json.dumps({"status": 0, "result": result, "fixtureTarget": target})
        )

    def write_mcp(self, text: str) -> None:
        (self.fixtures / "mcp.txt").write_text(text)

    def set_mode(self, kind: str, mode: str | None) -> None:
        path = self.fixtures / f"{kind}.mode"
        if mode is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(mode)

    def run(
        self,
        *,
        cwd: Path | None = None,
        nocache: bool = False,
        helper: Path = HELPER,
        default_runtime: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        workdir = cwd or self.workspace
        env = dict(os.environ)
        env.update(
            PATH=f"{self.bin}:/usr/bin:/bin:/usr/sbin:/sbin",
            PYTHONDONTWRITEBYTECODE="1",
            SCOUT_WORKSPACE=str(self.workspace),
            SCOUT_CACHE_DIR=str(self.cache),
            SCOUT_RUNTIME_DIR=str(self.runtime),
            SCOUT_SETTINGS_FILE=str(self.settings),
            SCOUT_CONFIG_FILE=str(self.scout_config),
            SCOUT_STARTUP_EVIDENCE=str(helper),
            SCOUT_SLUGIFY=str(SLUGIFY),
            SCOUT_FIXTURE_DIR=str(self.fixtures),
            SCOUT_FIXTURE_LOG=str(self.log),
            SCOUT_NETWORK_TIMEOUT="1",
            PWD=str(workdir),
        )
        if nocache:
            env["SCOUT_HOOK_NOCACHE"] = "1"
        else:
            env.pop("SCOUT_HOOK_NOCACHE", None)
        if default_runtime:
            env.pop("SCOUT_RUNTIME_DIR", None)
            env.pop("TMPDIR", None)
        return subprocess.run(
            ["/bin/bash", str(HOOK)],
            cwd=workdir,
            env=env,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )


class StartupEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="scout-startup-test-")
        self.addCleanup(self.temp.cleanup)
        self.fx = StartupFixture(Path(self.temp.name))

    def test_helper_uses_collision_resistant_exact_target_keys(self) -> None:
        keys = []
        for target in ("QA A", "QA_A", "QA.*[x]"):
            result = subprocess.run(
                ["python3", "-B", str(HELPER), "key", target],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            keys.append(result.stdout.strip())
        self.assertEqual(len(set(keys)), 3)
        self.assertTrue(all(len(key) == 64 for key in keys))

    def helper(
        self, *arguments: str, stdin: dict | str
    ) -> subprocess.CompletedProcess[str]:
        raw = stdin if isinstance(stdin, str) else json.dumps(stdin)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(
            [sys.executable, "-B", str(HELPER), *arguments],
            input=raw,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def test_helper_rejects_ambiguous_config_and_non_minimal_cache(self) -> None:
        today = time.strftime("%Y-%m-%d")
        ambiguous = self.helper(
            "normalize",
            "config",
            "--collected-date",
            today,
            "--provenance",
            "sf config get target-org --json",
            stdin={"status": 0, "result": [{"value": "QA"}]},
        )
        self.assertEqual(ambiguous.returncode, 65)

        normalized = self.helper(
            "normalize",
            "list",
            "--collected-date",
            today,
            "--provenance",
            "sf org list --json",
            stdin={
                "status": 0,
                "result": {"nonScratchOrgs": [], "scratchOrgs": []},
            },
        )
        payload = json.loads(normalized.stdout)
        payload["accessToken"] = "SYNTHETIC_SECRET"
        rejected = self.helper(
            "validate", "list", "--collected-date", today, stdin=payload
        )
        self.assertEqual(rejected.returncode, 65)

    def test_helper_rejects_contradictory_or_calendar_invalid_cache(self) -> None:
        today = time.strftime("%Y-%m-%d")
        normalized = self.helper(
            "normalize",
            "display",
            "--collected-date",
            today,
            "--provenance",
            "sf org display --json",
            "--target",
            "QA A",
            stdin={
                "status": 0,
                "result": {
                    "username": "qa@example.invalid",
                    "id": "00D",
                    "instanceUrl": "https://example.invalid",
                    "connectedStatus": "Connected",
                },
            },
        )
        payload = json.loads(normalized.stdout)
        payload["state"] = "not_connected"
        contradictory = self.helper(
            "validate",
            "display",
            "--collected-date",
            today,
            "--target",
            "QA A",
            stdin=payload,
        )
        self.assertEqual(contradictory.returncode, 65)

        payload = json.loads(normalized.stdout)
        payload["collected_date"] = "2000-01-01"
        calendar_invalid = self.helper(
            "validate",
            "display",
            "--collected-date",
            "2000-01-01",
            "--target",
            "QA A",
            stdin=payload,
        )
        self.assertEqual(calendar_invalid.returncode, 65)

    def test_workspace_gate_is_silent_and_does_not_create_cache(self) -> None:
        outside = self.fx.base / "outside"
        outside.mkdir()
        result = self.fx.run(cwd=outside)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.fx.cache.exists())

    def test_default_runtime_works_when_tmpdir_is_unset(self) -> None:
        result = self.fx.run(nocache=True, default_runtime=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## ✅ Active Org (fresh evidence", result.stdout)

    def test_config_failure_absence_and_malformed_evidence_are_distinct(self) -> None:
        self.fx.set_mode("config", "exit:42")
        failed = self.fx.run(nocache=True).stdout
        self.assertIn("Default Salesforce org check unavailable (exit 42)", failed)
        self.assertNotIn("No default Salesforce org set", failed)

        self.fx.set_mode("config", None)
        self.fx.write_config(None)
        absent = self.fx.run(nocache=True).stdout
        self.assertIn("No default Salesforce org set", absent)

        self.fx.write_config(None, malformed=True)
        malformed = self.fx.run(nocache=True).stdout
        self.assertIn("Default Salesforce org check unavailable (malformed evidence)", malformed)
        self.assertNotIn("No default Salesforce org set", malformed)

    def test_exact_list_membership_and_collision_resistant_display_cache(self) -> None:
        self.fx.write_list(
            [
                {"alias": "QA A", "username": "space@example.invalid"},
                {"alias": "QA_A", "username": "under@example.invalid"},
            ]
        )
        self.fx.write_display("QA A", username="space@example.invalid")
        first = self.fx.run().stdout
        self.assertIn("**Username:** space@example.invalid", first)

        self.fx.write_config("QA_A")
        self.fx.write_display("QA_A", username="under@example.invalid")
        second = self.fx.run().stdout
        self.assertIn("**Username:** under@example.invalid", second)
        self.assertNotIn("**Username:** space@example.invalid", second)

        self.fx.write_config("QA.*[x]")
        self.fx.write_list([{"alias": "QAzzzx", "username": "near@example.invalid"}])
        literal = self.fx.run(nocache=True).stdout
        self.assertIn("Configured target-org 'QA.*[x]' is not in the connected org list", literal)

    def test_list_failure_differs_from_valid_missing_member(self) -> None:
        self.fx.set_mode("list", "exit:43")
        unavailable = self.fx.run(nocache=True).stdout
        self.assertIn("Connected org list unavailable (exit 43)", unavailable)
        self.assertIn("**Username:** qa-a@example.invalid", unavailable)
        self.assertNotIn("not in the connected org list", unavailable)

        self.fx.set_mode("list", None)
        self.fx.write_list([{"alias": "OTHER", "username": "other@example.invalid"}])
        self.fx.run(nocache=True)
        missing = self.fx.run().stdout
        self.assertIn("Configured target-org 'QA A' is not in the connected org list", missing)
        self.assertNotIn("Connected org list unavailable", missing)
        calls = self.fx.log.read_text().splitlines()
        self.assertGreaterEqual(calls.count("list"), 3)

    def test_display_failure_non_connected_signal_and_timeout_are_distinct(self) -> None:
        cases = (
            ("exit:44", "Org 'QA A' evidence unavailable (exit 44)"),
            ("signal", "Org 'QA A' evidence unavailable (terminated by signal 15)"),
            ("timeout", "Org 'QA A' evidence unavailable (timed out)"),
        )
        for mode, expected in cases:
            with self.subTest(mode=mode):
                self.fx.set_mode("display", mode)
                output = self.fx.run(nocache=True).stdout
                self.assertIn(expected, output)
                self.assertNotIn("auth expired", output)

        self.fx.set_mode("display", None)
        self.fx.write_display(
            "QA A",
            username="qa-a@example.invalid",
            connected_status="RefreshTokenAuthError",
        )
        explicit = self.fx.run(nocache=True).stdout
        self.assertIn("Org 'QA A' is not connected (RefreshTokenAuthError;", explicit)
        self.assertNotIn("## ✅ Active Org", explicit)

    def test_warm_cache_is_labeled_and_failed_forced_refresh_discards_success(self) -> None:
        fresh = self.fx.run().stdout
        self.assertIn("## ✅ Active Org (fresh evidence", fresh)

        self.fx.set_mode("list", "exit:51")
        self.fx.set_mode("display", "exit:52")
        warm = self.fx.run().stdout
        self.assertIn("## ℹ️ Active Org (cached evidence", warm)
        self.assertNotIn("## ✅ Active Org (cached evidence", warm)

        forced = self.fx.run(nocache=True).stdout
        self.assertNotIn("## ✅ Active Org", forced)
        self.assertIn("Connected org list unavailable (exit 51)", forced)
        self.assertIn("Org 'QA A' evidence unavailable (exit 52)", forced)

        later = self.fx.run().stdout
        self.assertNotIn("## ✅ Active Org", later)
        self.assertIn("Connected org list unavailable (exit 51)", later)

    def test_malformed_mismatched_future_and_stale_display_cache_are_refreshed(self) -> None:
        self.fx.run()
        display_file = next(self.fx.cache.glob("org-display-*.json"))
        original = json.loads(display_file.read_text())
        mutations = (
            "{broken",
            json.dumps({**original, "target": "DIFFERENT"}),
            json.dumps({**original, "collected_at": 4_102_444_800}),
            json.dumps({**original, "collected_date": "2000-01-01"}),
        )
        for index, bad in enumerate(mutations):
            with self.subTest(index=index):
                display_file.write_text(bad)
                display_file.chmod(0o600)
                username = f"refreshed-{index}@example.invalid"
                self.fx.write_display("QA A", username=username)
                output = self.fx.run().stdout
                self.assertIn(f"**Username:** {username}", output)
                self.assertIn("fresh evidence", output)

    def test_cache_is_minimal_private_and_drops_synthetic_secrets(self) -> None:
        secrets = ("DISPLAY_SECRET", "LIST_SECRET", "MCP_SECRET")
        self.fx.write_display(
            "QA A",
            username="qa-a@example.invalid",
            extra={"accessToken": secrets[0], "extra": {"password": "nested"}},
        )
        self.fx.write_list(
            [{"alias": "QA A", "username": "qa-a@example.invalid", "token": secrets[1]}],
            extra={"credential": secrets[1]},
        )
        self.fx.write_mcp(f"slack: {secrets[2]} - authentication required\n")
        output = self.fx.run().stdout
        cache_text = "\n".join(path.read_text() for path in self.fx.cache.glob("*.json"))
        for secret in secrets:
            self.assertNotIn(secret, output)
            self.assertNotIn(secret, cache_text)
        self.assertEqual(stat.S_IMODE(self.fx.cache.stat().st_mode), 0o700)
        cache_files = list(self.fx.cache.glob("*.json"))
        self.assertTrue(cache_files)
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in cache_files)
        )
        self.assertFalse(list(self.fx.cache.glob("*.partial*")))
        self.assertEqual(list(self.fx.runtime.rglob("*")), [])

    def test_late_cache_publication_failure_discards_all_probe_evidence(self) -> None:
        fresh = self.fx.run()
        self.assertIn("## ✅ Active Org (fresh evidence", fresh.stdout)

        mv = self.fx.bin / "mv"
        mv.write_text("#!/bin/bash\nexit 73\n")
        mv.chmod(0o700)
        failed = self.fx.run(nocache=True)

        self.assertIn("cache update failed", failed.stdout)
        self.assertNotIn("## ✅ Active Org", failed.stdout)
        self.assertEqual(list(self.fx.cache.glob("*.json")), [])
        self.assertEqual(list(self.fx.cache.glob(".normalized.*")), [])
        self.assertEqual(list(self.fx.runtime.rglob("*")), [])

    def test_cache_path_failure_and_missing_helper_degrade_without_crashing(self) -> None:
        self.fx.cache.write_text("not-a-directory")
        failed_cache = self.fx.run().stdout
        self.assertIn("Startup evidence cache unavailable", failed_cache)
        self.assertIn("**Ready.**", failed_cache)

        self.fx.cache.unlink()
        missing = self.fx.run(helper=self.fx.base / "missing-helper.py").stdout
        self.assertIn("Startup evidence helper unavailable", missing)
        self.assertIn("**Ready.**", missing)

    def test_missing_salesforce_cli_does_not_fall_through_to_user_path(self) -> None:
        (self.fx.bin / "sf").unlink()
        output = self.fx.run(nocache=True).stdout
        self.assertIn("Default Salesforce org check unavailable (command unavailable)", output)
        self.assertIn("Connected org list unavailable (command unavailable)", output)

    def test_missing_claude_cli_does_not_probe_another_path(self) -> None:
        (self.fx.bin / "claude").unlink()
        output = self.fx.run(nocache=True).stdout
        self.assertNotIn("Slack MCP registered", output)
        calls = self.fx.log.read_text().splitlines()
        self.assertNotIn("mcp", calls)

    def test_canonical_slug_folder_lookup_uses_shipped_slugifier(self) -> None:
        self.fx.write_config("CareConnect4Me_DPA")
        self.fx.write_list([{"alias": "CareConnect4Me_DPA"}])
        self.fx.write_display(
            "CareConnect4Me_DPA", username="care@example.invalid"
        )
        folder = self.fx.workspace / "orgs" / "careconnect4me-dpa-acme"
        folder.mkdir(parents=True)
        output = self.fx.run(nocache=True).stdout
        self.assertIn("1 customer folder(s) for CareConnect4Me_DPA", output)
        self.assertIn("acme: no audit found", output)

    def test_slack_status_distinguishes_fresh_and_cached_evidence(self) -> None:
        self.fx.write_mcp("slack: registered - authentication required\n")
        fresh = self.fx.run().stdout
        self.assertIn("Slack MCP registered but not connected (fresh evidence", fresh)
        self.fx.set_mode("mcp", "exit:61")
        cached = self.fx.run().stdout
        self.assertIn("Slack MCP registered but not connected (cached evidence", cached)


if __name__ == "__main__":
    unittest.main()
