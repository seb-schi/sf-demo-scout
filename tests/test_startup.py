"""Offline integration tests for the shipped Scout startup hook (hooks/session_startup.py)."""

from __future__ import annotations

import importlib.util
import json
import ntpath
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import stand_ins


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "session_startup.py"
HOOKS_FILE = ROOT / "hooks" / "claude-hooks.json"
HELPER = ROOT / "scripts" / "startup-evidence.py"
SLUGIFY = ROOT / "scripts" / "slugify.py"
SELF_REPAIR = ("Before the first Scout task or Salesforce change in this session, tell the builder in one line that Scout is "
               "repairing its setup, then run `/scout-setup self-repair` yourself (the `sf-demo-scout:scout-setup` skill "
               "with argument `self-repair`), once.")
# What the builder sees of each official-plugins notice on Claude Code, where the model gets the full text above.
MISSING_LINE = ("Scout builds with Salesforce's official plugins, which aren't set up yet; it sets them up before its "
                "first task in this session.")
CONFLICT_LINE = ("Two copies of Salesforce's official plugin are switched on; Scout offers to switch the extra one off "
                 "before its first task in this session.")
UPDATE = "Scout 2.4.0 is installed; 2.5.0 is out. Restart."  # what the version stub reports, after SCOUT_UPDATE
# The line for a session at low or medium effort, which adds nothing to the model's text.
EFFORT_LINE = ("Scout works best on Opus 5.5 at High effort or higher. Switch with `/effort high`, or under Effort in "
               "the model picker.")


def hook_output(stdout: str) -> tuple[str, str]:
    """What the model and the builder each get from one run: hook JSON's additionalContext and systemMessage, or a
    plain output, which on Claude Code only the model reads."""
    try:
        payload = json.loads(stdout)
    except ValueError:
        return stdout, ""
    return payload["hookSpecificOutput"]["additionalContext"], payload["systemMessage"]


# Runs the hook with its cache publication refused, the way a failing rename would refuse it.
REFUSE_REPLACE = """import runpy, sys
sys.path.insert(0, sys.argv[2])
import scout_portable
def refuse(src, dst, **kwargs):
    raise PermissionError(13, "synthetic: the destination is held")
scout_portable.replace = refuse
hook = sys.argv[1]
sys.argv = [hook]
runpy.run_path(hook, run_name="__main__")
"""
# Each org probe's bound in the fixture, and how long the timeout stand-in hangs past it: on Windows a probe starts
# Node and then Python, which takes longer there, the first time most of all.
PROBE_BOUND, PROBE_HANG = (6, 10) if stand_ins.WINDOWS else (3, 5)
# The fixture's Salesforce CLI and claude stand-ins. Each logs the kind of call to SCOUT_FIXTURE_LOG, does what the
# kind's mode file in SCOUT_FIXTURE_DIR says (ok, exit:N, timeout, or signal: it ends itself with SIGTERM), and then
# prints its answer file from that folder.
FIXTURE_PROBE = """
with open(os.environ["SCOUT_FIXTURE_LOG"], "ab") as log:
    log.write(kind.encode() + b"\\n")
mode_file = folder / (kind + ".mode")
mode = mode_file.read_text().strip() if mode_file.is_file() else "ok"
if mode == "signal":
    os.kill(os.getpid(), signal.SIGTERM)
    time.sleep(5)
elif mode == "timeout":
    time.sleep(float(os.environ["SCOUT_FIXTURE_HANG"]))
elif mode.startswith("exit:"):
    sys.exit(int(mode[len("exit:"):]))
sys.stdout.buffer.write((folder / answer).read_bytes())
"""
FIXTURE_SF = """import os, signal, sys, time
from pathlib import Path
folder = Path(os.environ["SCOUT_FIXTURE_DIR"])
kind = {"config get": "config", "org list": "list", "org display": "display"}.get(" ".join(sys.argv[1:3]), "unknown")
answer = kind + ".json"
""" + FIXTURE_PROBE
FIXTURE_CLAUDE = """import os, signal, sys, time
from pathlib import Path
folder = Path(os.environ["SCOUT_FIXTURE_DIR"])
kind, answer = "mcp", "mcp.txt"
""" + FIXTURE_PROBE


def load_hook():
    spec = importlib.util.spec_from_file_location("scout_session_startup_test", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def official_config(config: Path, *, ready: bool) -> Path:
    """A Claude config folder with Salesforce's official plugin set up from GitHub, or with nothing."""
    (config / "plugins").mkdir(parents=True, exist_ok=True)
    if ready:
        root = config / "cache/salesforce/salesforce-development/2.4.0"
        root.mkdir(parents=True, exist_ok=True)
        (config / "plugins/known_marketplaces.json").write_text(json.dumps(
            {"salesforce": {"source": {"source": "git", "url": "https://github.com/forcedotcom/sf-skills.git"}}}))
        (config / "plugins/installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
            "salesforce-development@salesforce": [{"scope": "user", "installPath": str(root)}]}}))
        (config / "settings.json").write_text(json.dumps({"enabledPlugins": {"salesforce-development@salesforce": True}}))
    return config


class StartupFixture:
    def __init__(self, base: Path) -> None:
        self.extra_env: dict[str, str] = {}
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
        self.settings.write_text('{"env":{"ANTHROPIC_AUTH_TOKEN":"synthetic"}}')
        self.scout_config.write_text("{}")
        self.log = base / "calls.log"
        # The machine's own Claude config never leaks in: by default the official plugin is set up, so no notice.
        self.claude_config = official_config(base / "claude-config", ready=True)
        self.sf = stand_ins.salesforce_cli(self.bin, FIXTURE_SF)
        self.claude = stand_ins.tool(self.bin, "claude", FIXTURE_CLAUDE)
        self.write_config("QA A")
        self.write_list([{"alias": "QA A", "username": "qa-a@example.invalid"}])
        self.write_display("QA A", username="qa-a@example.invalid")
        self.write_mcp("slack: https://mcp.slack.com - ✓ Connected\n")

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
        (self.fixtures / "mcp.txt").write_text(text, encoding="utf-8")

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
        host: str = "claude",
        plugin_root: str = "",
        refuse_replace: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        workdir = cwd or self.workspace
        env = dict(os.environ)
        # The stand-ins' folder first; on Windows Node's folder too, for the CLI's route, and no installed CLI's update.
        env.update(stand_ins.cli_environment(self.bin, "/usr/bin", "/bin", "/usr/sbin", "/sbin"))
        env.update(
            PYTHONDONTWRITEBYTECODE="1",
            CLAUDE_PLUGIN_ROOT=plugin_root,
            SCOUT_HOST=host,
            SCOUT_WORKSPACE=str(self.workspace),
            SCOUT_CACHE_DIR=str(self.cache),
            SCOUT_RUNTIME_DIR=str(self.runtime),
            SCOUT_SETTINGS_FILE=str(self.settings),
            SCOUT_CONFIG_FILE=str(self.scout_config),
            SCOUT_STARTUP_EVIDENCE=str(helper),
            SCOUT_SLUGIFY=str(SLUGIFY),
            SCOUT_FIXTURE_DIR=str(self.fixtures),
            SCOUT_FIXTURE_LOG=str(self.log),
            # Keep ordinary stub startup tolerant of a busy developer machine.
            # The timeout fixture hangs past the bound, so it still exercises
            # the real process-group timeout/cleanup path.
            SCOUT_NETWORK_TIMEOUT=str(PROBE_BOUND),
            SCOUT_FIXTURE_HANG=str(PROBE_HANG),
            CLAUDE_CONFIG_DIR=str(self.claude_config),
            PWD=str(workdir),
            SCOUT_NO_UPDATE_CHECK="1",  # never GitHub, nor the developer's own update cache, from a test
        )
        env.pop("CLAUDE_EFFORT", None)  # nor the effort of a Claude Code session running the tests
        env.update(self.extra_env)
        if nocache:
            env["SCOUT_HOOK_NOCACHE"] = "1"
        else:
            env.pop("SCOUT_HOOK_NOCACHE", None)
        if default_runtime:
            env.pop("SCOUT_RUNTIME_DIR", None)
            env.pop("TMPDIR", None)
        command = [sys.executable, "-B", str(HOOK)]
        if refuse_replace:
            command = [sys.executable, "-B", "-c", REFUSE_REPLACE, str(HOOK), str(ROOT / "scripts")]
        return subprocess.run(
            command,
            cwd=workdir,
            env=env,
            encoding="utf-8",  # what the hook prints on every platform, whatever the console's code page
            errors="replace",  # for stderr, which a Python on Windows may write in the ANSI code page
            capture_output=True,
            timeout=30,  # a loaded machine (a review or second suite running) can pass 15 s on the 100-folder fixture
            check=False,
        )


class StartupUpdateNoticeTests(unittest.TestCase):
    """On Claude Code the builder sees only the hook's systemMessage, so the client floor and each notice go there as
    one plain line each, while the model still gets the plugin and release notices' full text. Codex and Cursor keep
    plain output."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="scout-update-notice-")
        self.addCleanup(temp.cleanup)
        self.fx = StartupFixture(Path(temp.name).resolve())
        self.stub = self.fx.base / "version-stub.py"
        self.stub.write_text("print(%r)\n" % ("SCOUT_UPDATE " + UPDATE))
        # No client of this machine's own: only the test that names one gets a floor line.
        self.fx.extra_env = {"SCOUT_VERSION_SCRIPT": str(self.stub), "SCOUT_NO_UPDATE_CHECK": "",
                             "CLAUDE_CODE_EXECPATH": "", "CLAUDE_CODE_ENTRYPOINT": "", "CLAUDE_PLUGIN_DATA": ""}
        self.outside = self.fx.base / "outside"
        self.outside.mkdir()

    def test_a_newer_release_is_one_line_and_nothing_otherwise(self) -> None:
        for printed, expected in (("SCOUT_UPDATE " + UPDATE, True), ("", False),
                                  ("Traceback (most recent call last):", False)):
            with self.subTest(printed=printed):
                self.stub.write_text("print(%r)\n" % printed)
                result = self.fx.run()
                self.assertEqual(result.returncode, 0, result.stderr)
                context, shown = hook_output(result.stdout)
                self.assertEqual("2.5.0 is out" in context, expected, result.stdout)
                self.assertEqual(shown, UPDATE if expected else "")
                self.assertNotIn("Traceback", result.stdout)

    def test_a_session_start_says_nothing_about_the_retirement(self) -> None:
        # 2.6.2: the farewell comes up only when someone starts Scout (/scout), never in every session.
        self.stub.write_text("print('')\n")  # no newer release, so nothing else shows either
        context, shown = hook_output(self.fx.run(cwd=self.outside).stdout)
        self.assertNotIn("retir", context + shown)
        for host in ("codex", "cursor"):
            with self.subTest(host=host):
                self.assertNotIn("retir", self.fx.run(cwd=self.outside, host=host).stdout)
        entry = (ROOT / "skills" / "scout" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Scout is retiring", entry)
        self.assertIn("move me off Scout", entry)

    def test_claude_code_shows_the_builder_the_line_and_codex_and_cursor_keep_plain_text(self) -> None:
        self.assertEqual(hook_output(self.fx.run(cwd=self.outside).stdout), (f"## ℹ️ {UPDATE}\n\n", UPDATE))
        for host in ("codex", "cursor"):
            with self.subTest(host=host):
                self.assertEqual(self.fx.run(cwd=self.outside, host=host).stdout, f"## ℹ️ {UPDATE}\n\n")

    def test_a_low_or_medium_effort_gets_one_line_on_claude_code_only(self) -> None:
        self.stub.write_text("print('')\n")  # no newer release, so the effort line is all there is to show
        for effort, shown in (("low", EFFORT_LINE), ("medium", EFFORT_LINE), ("high", ""), (None, ""), ("", ""),
                              ("xhigh", ""), ("max", ""), ("auto", "")):
            with self.subTest(effort=effort):
                self.fx.extra_env.pop("CLAUDE_EFFORT", None)  # None: unset, which Claude Code may leave it here
                if effort is not None:
                    self.fx.extra_env["CLAUDE_EFFORT"] = effort
                result = self.fx.run(cwd=self.outside)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(hook_output(result.stdout), ("", shown))  # the model's context stays as it was
        self.fx.extra_env["CLAUDE_EFFORT"] = "low"
        for host in ("codex", "cursor"):
            with self.subTest(host=host):
                self.assertEqual(self.fx.run(cwd=self.outside, host=host).stdout, "")

    def test_the_floor_line_and_every_notice_make_one_valid_message(self) -> None:
        self.fx.claude_config = official_config(self.fx.base / "claude-config-missing", ready=False)
        client = stand_ins.tool(self.fx.base, "old-claude", 'print("2.1.280 (Claude Code)")\n')
        self.fx.extra_env.update(CLAUDE_CODE_EXECPATH=str(client), CLAUDE_CODE_ENTRYPOINT="claude-desktop",
                                 CLAUDE_EFFORT="medium")
        payload = json.loads(self.fx.run(nocache=True).stdout)
        self.assertEqual(sorted(payload), ["hookSpecificOutput", "systemMessage"])
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "SessionStart")
        floor, effort, missing, update = payload["systemMessage"].split("\n")
        self.assertTrue(floor.startswith("Scout needs Claude Code 2.1.293+ for the 5.5 models;"), floor)
        self.assertEqual((effort, missing, update), (EFFORT_LINE, MISSING_LINE, UPDATE))
        self.assertNotIn(SELF_REPAIR, payload["systemMessage"])
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn(f"## ℹ️ Scout builds with Salesforce's official plugins, which aren't set up yet. "
                      f"{SELF_REPAIR}\n\n## ℹ️ {UPDATE}\n\n", context)  # the model's full text, with the repair it runs
        self.assertIn("## ✅ Active Org", context)

    def test_scout_leaves_the_update_notice_to_the_claude_code_banner(self) -> None:
        skill = (ROOT / "skills" / "scout" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("put a `SCOUT_UPDATE` line into your first message, once, unless on Claude Code your "
                      "session-start context already holds the same notice, which the builder saw at session start;",
                      skill)


class StartupEvidenceTests(unittest.TestCase):
    def test_helper_uses_collision_resistant_exact_target_keys(self) -> None:
        keys = []
        for target in ("QA A", "QA_A", "QA.*[x]"):
            result = subprocess.run(
                [sys.executable, "-B", str(HELPER), "key", target],
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
            "config",
            "--collected-date",
            today,
            "--provenance",
            "sf config get target-org --json",
            stdin={"status": 0, "result": [{"name": "target-org", "value": "QA"}]},
        )
        payload = json.loads(normalized.stdout)
        payload["accessToken"] = "SYNTHETIC_SECRET"
        rejected = self.helper(
            "validate", "config", "--collected-date", today, stdin=payload
        )
        self.assertEqual(rejected.returncode, 65)
        self.assertNotEqual(self.helper("normalize", "list", "--collected-date", today, "--provenance",
                                        "sf org list --json", stdin={"status": 0, "result": {}}).returncode, 0)

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


class StartupHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="scout-startup-test-")
        self.addCleanup(self.temp.cleanup)
        self.fx = StartupFixture(Path(self.temp.name))

    def test_workspace_gate_is_silent_and_does_not_create_cache(self) -> None:
        outside = self.fx.base / "outside"
        outside.mkdir()
        result = self.fx.run(cwd=outside)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.fx.cache.exists())

    def test_the_setup_notice_also_reaches_a_builder_outside_the_workspace(self) -> None:
        # After Scout updates, a builder who starts Claude in another folder still learns that setup is needed;
        # the org probes stay workspace-only.
        outside = self.fx.base / "outside"
        outside.mkdir()
        notice = "Scout builds with Salesforce's official plugins, which aren't set up yet. " + SELF_REPAIR
        self.fx.claude_config = official_config(self.fx.base / "claude-config-empty", ready=False)
        result = self.fx.run(cwd=outside)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(hook_output(result.stdout), ("## ℹ️ " + notice + "\n\n", MISSING_LINE))
        self.assertEqual(self.fx.run(cwd=outside, host="codex").stdout, "")
        self.assertFalse(self.fx.log.exists())  # no org or MCP probes outside the workspace
        self.assertFalse(self.fx.cache.exists())
        self.assertEqual(hook_output(self.fx.run(nocache=True).stdout)[0].count(notice), 1)

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

    def test_collision_resistant_display_cache(self) -> None:
        self.fx.write_display("QA A", username="space@example.invalid")
        first = self.fx.run().stdout
        self.assertIn("**Username:** space@example.invalid", first)

        self.fx.write_config("QA_A")
        self.fx.write_display("QA_A", username="under@example.invalid")
        second = self.fx.run().stdout
        self.assertIn("**Username:** under@example.invalid", second)
        self.assertNotIn("**Username:** space@example.invalid", second)

    def test_display_failure_non_connected_signal_and_timeout_are_distinct(self) -> None:
        cases = [
            ("exit:44", "Org 'QA A' evidence unavailable (exit 44)"),
            ("signal", "Org 'QA A' evidence unavailable (terminated by signal 15)"),
            ("timeout", "Org 'QA A' evidence unavailable (timed out)"),
        ]
        if stand_ins.WINDOWS:  # no signals there: a status past 128 is an exit status like any other
            cases.append(("exit:143", "Org 'QA A' evidence unavailable (exit 143)"))
        for mode, expected in cases:
            with self.subTest(mode=mode):
                if mode == "signal" and stand_ins.WINDOWS:
                    self.skipTest("Windows has no signals to end a process with; the hook reports its exit status")
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

        self.fx.set_mode("display", "exit:52")
        warm = self.fx.run().stdout
        self.assertIn("## ℹ️ Active Org (cached evidence", warm)
        self.assertNotIn("## ✅ Active Org (cached evidence", warm)

        forced = self.fx.run(nocache=True).stdout
        self.assertNotIn("## ✅ Active Org", forced)
        self.assertIn("Org 'QA A' evidence unavailable (exit 52)", forced)

        later = self.fx.run().stdout
        self.assertNotIn("## ✅ Active Org", later)

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
        cache_files = list(self.fx.cache.glob("*.json"))
        self.assertTrue(cache_files)
        self.assertFalse(list(self.fx.cache.glob("*.partial*")))
        self.assertEqual(list(self.fx.runtime.rglob("*")), [])
        if stand_ins.WINDOWS:
            return  # the rest checks POSIX permission bits, which Windows doesn't keep
        self.assertEqual(stat.S_IMODE(self.fx.cache.stat().st_mode), 0o700)
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in cache_files)
        )

    def test_late_cache_publication_failure_discards_all_probe_evidence(self) -> None:
        fresh = self.fx.run()
        self.assertIn("## ✅ Active Org (fresh evidence", fresh.stdout)

        failed = self.fx.run(nocache=True, refuse_replace=True)

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
        stand_ins.remove(self.fx.sf)
        output = self.fx.run(nocache=True).stdout
        self.assertIn("Default Salesforce org check unavailable (command unavailable)", output)

    def test_missing_claude_cli_does_not_probe_another_path(self) -> None:
        stand_ins.remove(self.fx.claude)
        output = self.fx.run(nocache=True).stdout
        self.assertNotIn("Slack MCP registered", output)
        calls = self.fx.log.read_text().splitlines()
        self.assertNotIn("mcp", calls)

    def test_codex_ignores_claude_credentials_and_removes_legacy_probe_caches(self) -> None:
        self.fx.cache.mkdir(mode=0o700, exist_ok=True)
        legacy = [self.fx.cache / name for name in ("mcp-list.json", "org-list.json")]
        for path in legacy:  # what an earlier release's org-list and MCP probes left behind
            path.write_text('{"slack": "Needs authentication", "header": "RAW_SECRET"}\n')
        self.fx.log.write_text("")
        self.fx.settings.unlink()
        stand_ins.tool(self.fx.bin, "codex", (
            'import os\n'
            'with open(os.environ["SCOUT_FIXTURE_LOG"], "ab") as log:\n'
            '    log.write(b"codex-mcp\\n")\n'
            'print(\'[{"name":"slack","enabled":false,'
            '"disabled_reason":"requirements (Baseline)",'
            '"transport":{"http_headers":{"Authorization":"RAW_SECRET"}}}]\')\n'))
        result = self.fx.run(host="codex")
        self.assertEqual(result.returncode, 0, result.stderr)
        for wrong in ("LLM" + "GW", "Claude Code installer", "Opus", "Slack", "needs authentication", "RAW_SECRET"):
            self.assertNotIn(wrong, result.stdout)
        calls = self.fx.log.read_text().splitlines()
        self.assertNotIn("codex-mcp", calls)  # startup no longer probes MCP state on any host
        self.assertNotIn("mcp", calls)
        self.assertEqual([path for path in legacy if path.exists()], [])
        for path in self.fx.cache.iterdir():
            if path.is_file():
                self.assertNotIn("RAW_SECRET", path.read_text())

    def test_official_plugin_notice_on_claude_only(self) -> None:
        config = official_config(self.fx.base / "claude-config-notice", ready=False)
        self.fx.claude_config = config
        notice = "Scout builds with Salesforce's official plugins, which aren't set up yet"
        context, shown = hook_output(self.fx.run(nocache=True).stdout)
        self.assertIn(notice + ". " + SELF_REPAIR, context)
        self.assertEqual(shown, MISSING_LINE)
        self.assertNotIn(notice, self.fx.run(nocache=True, host="codex").stdout)
        root = config / "cache/salesforce/salesforce-development/2.4.0"
        root.mkdir(parents=True)
        (config / "plugins/known_marketplaces.json").write_text(json.dumps(
            {"salesforce": {"source": {"source": "git", "url": "https://github.com/forcedotcom/sf-skills.git"}}}))
        (config / "plugins/installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
            "salesforce-development@salesforce": [{"scope": "user", "installPath": str(root)}],
            "salesforce-development@claude-plugins-official": [{"scope": "user", "installPath": str(root)}]}}))
        enabled = {"salesforce-development@salesforce": True}
        (config / "settings.json").write_text(json.dumps({"enabledPlugins": enabled}))
        output = self.fx.run(nocache=True).stdout
        self.assertNotIn(notice, output)
        self.assertNotIn("Two copies", output)
        self.assertEqual(hook_output(output)[1], "")  # nothing to tell the builder: the plain context, as before
        enabled["salesforce-development@claude-plugins-official"] = True
        (config / "settings.json").write_text(json.dumps({"enabledPlugins": enabled}))
        context, shown = hook_output(self.fx.run(nocache=True).stdout)
        self.assertIn("Two copies of Salesforce's official plugin are switched on", context)
        self.assertEqual(shown, CONFLICT_LINE)

    def test_a_broken_setup_is_repaired_by_the_session_not_left_to_the_builder(self) -> None:
        healthy = self.fx.run(nocache=True).stdout
        self.assertNotIn(SELF_REPAIR, healthy)
        self.fx.scout_config.unlink()  # setup never finished
        self.assertIn("## ⚠️ Scout setup not yet complete. " + SELF_REPAIR, self.fx.run(nocache=True).stdout)
        self.fx.scout_config.write_text("{}")
        config = official_config(self.fx.base / "claude-config-repair", ready=False)
        self.fx.claude_config = config
        missing = hook_output(self.fx.run(nocache=True).stdout)
        self.assertIn("which aren't set up yet. " + SELF_REPAIR, missing[0])
        root = config / "cache/salesforce/salesforce-development/2.4.0"
        root.mkdir(parents=True)
        (config / "plugins/known_marketplaces.json").write_text(json.dumps(
            {"salesforce": {"source": {"source": "git", "url": "https://github.com/forcedotcom/sf-skills.git"}}}))
        (config / "plugins/installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
            "salesforce-development@salesforce": [{"scope": "user", "installPath": str(root)}],
            "salesforce-development@claude-plugins-official": [{"scope": "user", "installPath": str(root)}]}}))
        (config / "settings.json").write_text(json.dumps({"enabledPlugins": {
            "salesforce-development@salesforce": True, "salesforce-development@claude-plugins-official": True}}))
        conflict = hook_output(self.fx.run(nocache=True).stdout)  # setup repairs this one only on the builder's yes
        self.assertIn("are switched on. " + SELF_REPAIR + " It asks the builder before switching the extra one off.",
                      conflict[0])
        for output in (healthy, *missing, *conflict):
            self.assertNotIn("Run `/scout-setup`", output)
            self.assertNotIn("Run /scout-setup", output)
        for shown in (missing[1], conflict[1]):  # the builder learns of the repair; running it is the session's job
            self.assertTrue(shown)
            self.assertNotIn("/scout-setup", shown)

    def test_the_notice_judges_the_folder_the_session_started_in(self) -> None:
        # Both copies are switched on for the user, but this project switches Anthropic's off: no "two copies" here.
        config = official_config(self.fx.base / "claude-config-two", ready=True)
        enabled = {"salesforce-development@salesforce": True, "salesforce-development@claude-plugins-official": True}
        (config / "settings.json").write_text(json.dumps({"enabledPlugins": enabled}))
        anthropic = config / "cache/claude-plugins-official/salesforce-development/2.3.0"
        anthropic.mkdir(parents=True)
        records = json.loads((config / "plugins/installed_plugins.json").read_text())
        records["plugins"]["salesforce-development@claude-plugins-official"] = [
            {"scope": "user", "installPath": str(anthropic)}]
        (config / "plugins/installed_plugins.json").write_text(json.dumps(records))
        self.fx.claude_config = config
        project, other = self.fx.base / "project", self.fx.base / "other"
        (project / ".claude").mkdir(parents=True)
        other.mkdir()
        (project / ".claude/settings.json").write_text(json.dumps(
            {"enabledPlugins": {"salesforce-development@claude-plugins-official": False}}))
        self.assertEqual(self.fx.run(cwd=project).stdout, "")
        self.assertEqual(hook_output(self.fx.run(cwd=other).stdout)[1], CONFLICT_LINE)

    def test_a_stalled_resolver_never_stalls_startup_or_shows_a_false_notice(self) -> None:
        slow = self.fx.base / "slow_official.py"
        slow.write_text("import time\ntime.sleep(30)\n")
        started = time.monotonic()
        with mock.patch.dict(os.environ, {"SCOUT_OFFICIAL_SCRIPT": str(slow)}):
            result = self.fx.run(nocache=True)
        self.assertLess(time.monotonic() - started, 15)  # the 3-second bound plus its termination grace, not 30
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Salesforce's official plugin", result.stdout)

    def test_unknown_host_does_not_infer_claude_or_authentication(self) -> None:
        self.fx.settings.unlink()
        result = self.fx.run(host="unknown")
        self.assertNotIn("LLM" + "GW", result.stdout)
        self.assertNotIn("mcp", self.fx.log.read_text().splitlines())

    def test_startup_runs_no_org_list_mcp_or_folder_probe(self) -> None:
        self.fx.write_mcp("slack: command - Needs authentication\n")
        output = self.fx.run(nocache=True).stdout
        for removed in ("Slack", "Authenticate", "org(s) available", "customer folder", "connected org list"):
            self.assertNotIn(removed, output)
        self.assertIn("**Username:** qa-a@example.invalid", output)
        calls = self.fx.log.read_text().splitlines()
        self.assertNotIn("list", calls)
        self.assertNotIn("mcp", calls)


class StartupPortTests(unittest.TestCase):
    """What the Python hook adds for Windows, checked on any machine."""

    def setUp(self) -> None:
        self.hook = load_hook()
        temp = tempfile.TemporaryDirectory(prefix="scout-startup-port-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)

    def test_a_windows_plugin_root_still_gets_the_standing_rules(self) -> None:
        for root, shown in (("C:/Plugins/Scout Plugin/", '"C:/Plugins/Scout Plugin/AGENTS.md"'),
                            ("D:\\Plugins\\scout", '"D:\\\\Plugins\\\\scout/AGENTS.md"')):
            with self.subTest(root=root):
                block = self.hook.rules_block(root)
                self.assertTrue(block.startswith("Scout is installed."), block)
                self.assertIn(shown, block)
        for root in ("relative", "C:relative", "\\\\server\\share", "C:/a\nb"):
            with self.subTest(root=root):
                self.assertEqual(self.hook.rules_block(root), "")

    def test_the_probes_fit_inside_the_declared_hook_timeout(self) -> None:
        hooks = json.loads(HOOKS_FILE.read_text(encoding="utf-8"))["hooks"]
        timeout = hooks["SessionStart"][0]["hooks"][0]["timeout"]
        # Every probe draws on one budget, and each timed-out probe gets a second to stop: the banner always prints.
        self.assertLessEqual(self.hook.BUDGET_SECONDS + 4, timeout)
        for platform in ("darwin", "win32"):
            with self.subTest(platform=platform), mock.patch.object(self.hook.scout_portable, "PLATFORM", platform):
                bounds = self.hook.bounds()
                self.assertLess(sum(bounds.values()) - bounds["network"], self.hook.BUDGET_SECONDS)
        with mock.patch.object(self.hook.scout_portable, "PLATFORM", "win32"):
            self.assertGreater(self.hook.bounds()["network"], 6)  # a cold Salesforce CLI start on Windows

    def test_a_spent_budget_starts_no_probe(self) -> None:
        marker = self.base / "started"
        status = self.hook.run_bounded(0.1, str(self.base / "out"), [sys.executable, "-c",
                                                                     f"open({str(marker)!r}, 'w')"])
        self.assertEqual((status, marker.exists()), (124, False))
        clock = self.hook.Clock(budget=0)
        self.assertEqual(clock.bound(6), 0)

    def test_windows_has_no_permission_bits_or_owners_to_check(self) -> None:
        loose = self.base / "evidence.json"
        loose.write_text("{}")
        loose.chmod(0o644)
        with mock.patch.object(self.hook.scout_portable, "PLATFORM", "win32"):
            self.assertTrue(self.hook.private(str(loose), 0o600, stat.S_ISREG))
            self.assertFalse(self.hook.private(str(self.base), 0o700, stat.S_ISREG))  # the kind still counts
        if os.name != "nt":
            with mock.patch.object(self.hook.scout_portable, "PLATFORM", "darwin"):
                self.assertFalse(self.hook.private(str(loose), 0o600, stat.S_ISREG))
                loose.chmod(0o600)
                self.assertTrue(self.hook.private(str(loose), 0o600, stat.S_ISREG))

    def test_only_the_shipped_evidence_helper_runs_in_process(self) -> None:
        self.assertIs(type(self.hook.evidence_for(str(HELPER))), self.hook.Evidence)  # one Python start for the pass
        stand_in = self.base / "evidence.py"
        stand_in.write_text("import sys\nprint(sys.argv[1:])\n")
        program = self.hook.evidence_for(str(stand_in))  # a test seam's file is a program, run as the shell hook ran it
        self.assertIsInstance(program, self.hook.ProgramEvidence)
        self.assertEqual(program.key("QA A"), "['key', 'QA A']")
        self.assertEqual(program.field("display", b"{}", "2026-01-02", "state", "QA A"),
                         "['field', 'display', '--collected-date', '2026-01-02', '--target', 'QA A', '--field', 'state']")
        crlf = self.base / "crlf-evidence.py"  # what a Python program prints on Windows
        crlf.write_text("import sys\nsys.stdout.buffer.write(repr(sys.argv[1:]).encode() + b'\\r\\n')\n")
        self.assertEqual(self.hook.evidence_for(str(crlf)).key("QA A"), "['key', 'QA A']")
        missing = self.hook.evidence_for(str(self.base / "missing.py"))
        self.assertFalse(missing.ready)
        with self.assertRaises(self.hook.EvidenceFailed):
            missing.normalize("config", b"{}", "2026-01-02", "sf config get target-org --json")

    def test_a_windows_folder_spelled_two_ways_is_one_folder(self) -> None:
        # PowerShell can hand the hook a long name where the workspace setting has the 8.3 short one, or the other way
        # round; macOS's /var link and the real folder behind it stand in for that here.
        spelled, resolved = str(self.base), str(self.base.resolve())
        other = self.base / "other"
        other.mkdir()
        with mock.patch.object(self.hook.scout_portable, "PLATFORM", "win32"):
            self.assertTrue(self.hook.same_folder(spelled, resolved))
            self.assertTrue(self.hook.same_folder(resolved, spelled))
            self.assertFalse(self.hook.same_folder(str(other), resolved))
            self.assertFalse(self.hook.same_folder(str(self.base / "absent"), resolved))  # names only, when one is missing

    def test_workspace_folders_compare_the_way_each_platform_names_them(self) -> None:
        with mock.patch.object(self.hook.scout_portable, "PLATFORM", "win32"), \
                mock.patch.object(self.hook.os, "path", ntpath):
            self.assertTrue(self.hook.same_folder("C:\\Users\\Tester\\claude-projects\\sf-demo-scout",
                                                  "c:/users/tester/claude-projects/sf-demo-scout/"))
        with mock.patch.object(self.hook.scout_portable, "PLATFORM", "darwin"):
            self.assertFalse(self.hook.same_folder("/x/Workspace", "/x/workspace"))  # exactly as the shell compared


if __name__ == "__main__":
    unittest.main()
