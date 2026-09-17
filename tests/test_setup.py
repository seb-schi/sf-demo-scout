"""Hermetic regressions for the shipped setup shell scripts."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ZSHRC_SCRIPT = ROOT / "scripts" / "setup-zshrc.sh"
CLI_SCRIPT = ROOT / "scripts" / "setup-cli-refresh.sh"
BEGIN = "# BEGIN SF-DEMO-SCOUT"
END = "# END SF-DEMO-SCOUT"
VALID_BLOCK = f"{BEGIN}\n# old\n{END}\n"
MULTILINE_EXPORT = (
    'export ANTHROPIC_DEFAULT_OPUS_MODEL=$(\n  printf "example-model"\n)\n'
    + VALID_BLOCK
    + "export UNRELATED_USER_SETTING=important\n"
)


class ZshrcScriptTests(unittest.TestCase):
    """The 65 historical B2 assertions, adapted to temporary fixtures."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="scout-zshrc-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def run_script(
        self, fixture: Path, extra_env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.pop("SCOUT_ZSH_BIN", None)
        env.update(
            SCOUT_ZSHRC_OVERRIDE=str(fixture),
            PYTHONDONTWRITEBYTECODE="1",
        )
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            ["/bin/bash", str(ZSHRC_SCRIPT)],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def assert_case(
        self,
        name: str,
        content: str,
        token: str,
        *,
        diagnostic: str | None = None,
        unchanged: bool = True,
        symlink: bool = False,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        case_dir = self.base / name
        case_dir.mkdir()
        fixture = case_dir / ".zshrc"
        target = case_dir / "real_zshrc"
        if symlink:
            target.write_text(content)
            fixture.symlink_to(target)
            readback = target
        else:
            fixture.write_text(content)
            readback = fixture
        result = self.run_script(fixture, extra_env)
        lines = result.stdout.splitlines()
        self.assertTrue(lines, result.stderr)
        self.assertEqual(lines[0], token)
        if diagnostic is not None:
            self.assertIn(diagnostic, result.stdout)
        if unchanged:
            self.assertEqual(readback.read_text(), content)
        if symlink:
            self.assertTrue(fixture.is_symlink())

    def test_missing_file_creation(self) -> None:
        fixture = self.base / "missing" / ".zshrc"
        fixture.parent.mkdir()
        result = self.run_script(fixture)
        self.assertEqual(result.stdout.splitlines()[0], "ZSHRC_MODIFIED")
        self.assertTrue(fixture.is_file() and BEGIN in fixture.read_text())

    def test_existing_pair_backup_and_idempotency(self) -> None:
        fixture = self.base / "existing.zshrc"
        fixture.write_text("export KEEP_ME=1\n" + VALID_BLOCK + "alias ll='ls -la'\n")
        first = self.run_script(fixture)
        self.assertEqual(first.stdout.splitlines()[0], "ZSHRC_MODIFIED")
        body = fixture.read_text()
        self.assertTrue("KEEP_ME=1" in body and "alias ll" in body)
        self.assertTrue(Path(str(fixture) + ".scout-bak-zshrc").is_file())
        second = self.run_script(fixture)
        self.assertEqual(second.stdout.splitlines()[0], "ZSHRC_UNCHANGED")

    def test_malformed_markers_and_safe_rejections(self) -> None:
        cases = (
            ("lone_begin", BEGIN + "\n# body\nexport UNRELATED_USER_SETTING=important\n", "malformed", False),
            ("space_end", BEGIN + "\n# body\n" + END + " \nexport UNRELATED_USER_SETTING=important\n", "malformed", False),
            ("tab_begin", BEGIN + "\t\n# body\n" + END + "\nexport UNRELATED_USER_SETTING=important\n", "malformed", False),
            ("reversed", END + "\n# x\n" + BEGIN + "\n", "malformed", False),
            ("duplicate", VALID_BLOCK + VALID_BLOCK, "malformed", False),
            ("marker_words", "# talking about SF-DEMO-SCOUT here\nexport KEEP=1\n", None, True),
            ("multiline", MULTILINE_EXPORT, "rejected", False),
            ("original_invalid", 'export BROKEN="unterminated\n', "pre-existing", False),
        )
        for name, content, diagnostic, modifies in cases:
            with self.subTest(name=name):
                self.assert_case(
                    name,
                    content,
                    "ZSHRC_MODIFIED" if modifies else "ZSHRC_UNCHANGED",
                    diagnostic=diagnostic,
                    unchanged=not modifies,
                )

    def test_validator_unavailable(self) -> None:
        self.assert_case(
            "validator_unavailable",
            VALID_BLOCK + "export KEEP=1\n",
            "ZSHRC_UNCHANGED",
            diagnostic="validator",
            extra_env={"SCOUT_ZSH_BIN": "/nonexistent/zsh"},
        )

    def test_symlink_success_and_rejected_edit(self) -> None:
        case_dir = self.base / "symlink_success"
        case_dir.mkdir()
        target = case_dir / "real_zshrc"
        fixture = case_dir / ".zshrc"
        target.write_text("export KEEP=1\n" + VALID_BLOCK)
        fixture.symlink_to(target)
        result = self.run_script(fixture)
        self.assertEqual(result.stdout.splitlines()[0], "ZSHRC_MODIFIED")
        self.assertTrue(fixture.is_symlink())
        self.assertIn("KEEP=1", target.read_text())
        self.assertTrue(Path(str(target) + ".scout-bak-zshrc").is_file())

        self.assert_case(
            "symlink_rejected",
            MULTILINE_EXPORT,
            "ZSHRC_UNCHANGED",
            diagnostic="rejected",
            symlink=True,
        )

    def test_dangling_symlinks_do_not_create_targets(self) -> None:
        existing = self.base / "dangling_existing"
        existing.mkdir()
        fixture = existing / ".zshrc"
        target = existing / "gone"
        fixture.symlink_to(target)
        result = self.run_script(fixture)
        self.assertTrue(
            result.stdout.splitlines()[0] == "ZSHRC_UNCHANGED"
            and "symlink" in result.stdout
        )
        self.assertFalse(target.exists())
        self.assertTrue(fixture.is_symlink())

        missing = self.base / "dangling_missing_parent"
        missing.mkdir()
        fixture = missing / ".zshrc"
        target = missing / "nodir" / "gone"
        fixture.symlink_to(target)
        result = self.run_script(fixture)
        self.assertTrue(
            result.stdout.splitlines()[0] == "ZSHRC_UNCHANGED"
            and "symlink" in result.stdout
        )
        self.assertFalse(target.parent.exists())

    def write_sitecustomize(self, case_dir: Path, body: str) -> dict[str, str]:
        injection = case_dir / "injection"
        injection.mkdir()
        (injection / "sitecustomize.py").write_text(body)
        return {"PYTHONPATH": str(injection)}

    def test_staging_write_failure_preserves_original(self) -> None:
        case_dir = self.base / "staging_failure"
        case_dir.mkdir()
        fixture = case_dir / ".zshrc"
        before = "export KEEP=1\n" + VALID_BLOCK + "alias x='y'\n"
        fixture.write_text(before)
        env = self.write_sitecustomize(
            case_dir,
            """import os
import tempfile
_original_mkstemp = tempfile.mkstemp
def fail_fixture_stage(*args, **kwargs):
    if os.fspath(kwargs.get("dir", "")) == os.environ.get("SCOUT_TEST_STAGE_DIR"):
        raise OSError("injected staging write failure")
    return _original_mkstemp(*args, **kwargs)
tempfile.mkstemp = fail_fixture_stage
""",
        )
        env["SCOUT_TEST_STAGE_DIR"] = str(case_dir)
        result = self.run_script(fixture, env)
        self.assertEqual(result.stdout.splitlines()[0], "ZSHRC_UNCHANGED")
        self.assertTrue(
            "WRITE_FAILED" in result.stdout or "preserved" in result.stdout
        )
        self.assertEqual(fixture.read_text(), before)

    def test_additional_marker_shapes_mode_and_exact_backup(self) -> None:
        for index, suffix in enumerate((" ", "\t")):
            with self.subTest(suffix=repr(suffix)):
                self.assert_case(
                    f"both_padded_{index}",
                    BEGIN + suffix + "\n# old\n" + END + suffix + "\nexport KEEP=1\n",
                    "ZSHRC_UNCHANGED",
                    diagnostic="malformed",
                )
        self.assert_case(
            "lone_end",
            END + "\nexport KEEP=1\n",
            "ZSHRC_UNCHANGED",
            diagnostic="malformed",
        )
        self.assert_case(
            "nested",
            BEGIN + "\n" + VALID_BLOCK + END + "\n",
            "ZSHRC_UNCHANGED",
            diagnostic="malformed",
        )

        fixture = self.base / "mode.zshrc"
        before = "export KEEP=1\n" + VALID_BLOCK
        fixture.write_text(before)
        fixture.chmod(0o600)
        result = self.run_script(fixture)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(stat.S_IMODE(fixture.stat().st_mode), 0o600)
        self.assertEqual(Path(str(fixture) + ".scout-bak-zshrc").read_text(), before)

    def test_final_replace_failure_preserves_original_backup_and_cleans_stage(self) -> None:
        case_dir = self.base / "replace_failure"
        case_dir.mkdir()
        fixture = case_dir / ".zshrc"
        before = "export KEEP=1\n" + VALID_BLOCK
        fixture.write_text(before)
        env = self.write_sitecustomize(
            case_dir,
            """import os
_original_replace = os.replace
def fail_fixture_replace(src, dst):
    if os.fspath(dst) == os.environ.get("SCOUT_TEST_REPLACE_TARGET"):
        raise OSError("injected final replace failure")
    return _original_replace(src, dst)
os.replace = fail_fixture_replace
""",
        )
        env["SCOUT_TEST_REPLACE_TARGET"] = str(fixture)
        result = self.run_script(fixture, env)
        self.assertTrue(
            "ZSHRC_UNCHANGED" in result.stdout
            and "injected final replace failure" in result.stdout
        )
        self.assertEqual(fixture.read_text(), before)
        self.assertEqual(Path(str(fixture) + ".scout-bak-zshrc").read_text(), before)
        self.assertFalse(any(path.name.startswith(".scout-zshrc.") for path in case_dir.iterdir()))


class CliRefreshScriptTests(unittest.TestCase):
    """The 24 behavioral B3 assertions; done-summary assertions are packaging tests."""

    CONFIG = {
        "sf": {
            "package": "@salesforce/cli",
            "pre": "@salesforce/cli/1.0.0 darwin node-v18.0.0",
            "current": "@salesforce/cli/2.0.0 x",
            "post": "@salesforce/cli/{version} foo",
            "prefix": "SF_CLI",
        },
        "claude": {
            "package": "@anthropic-ai/claude-code",
            "pre": "1.0.0 (Claude Code)",
            "current": "2.0.0 (Claude Code)",
            "post": "{version} (Claude Code)",
            "prefix": "CLAUDE_CLI",
        },
    }

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="scout-cli-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def make_stubs(self, case_dir: Path, cli: str) -> tuple[Path, Path]:
        bin_dir = case_dir / "bin"
        bin_dir.mkdir(parents=True)
        calls = case_dir / "calls.log"
        npm = bin_dir / "npm"
        npm.write_text(
            """#!/bin/bash
printf 'npm %s\n' "$*" >> "$CALLS"
case "$*" in
  *--dry-run*) printf '%s\n' "$NPM_RESOLVE_LINE"; exit 0 ;;
  *view*) printf '%s\n' "$NPM_VIEW"; exit 0 ;;
  *) echo "npm install log"; exit "${NPM_INSTALL_RC:-0}" ;;
esac
"""
        )
        npm.chmod(0o700)
        tool = bin_dir / cli
        tool.write_text(
            """#!/bin/bash
printf '%s %s\n' "$0" "$*" >> "$CALLS"
if [ "$1" = "--version" ]; then
  n=$(cat "$COUNTER" 2>/dev/null || echo 0)
  n=$((n+1)); echo "$n" > "$COUNTER"
  if [ "$n" -eq 1 ]; then printf '%s\n' "$PRE_OUT"; exit 0; fi
  printf '%s\n' "$POST_OUT"; exit "${POST_RC:-0}"
fi
exit 0
"""
        )
        tool.chmod(0o700)
        return bin_dir, calls

    def run_case(
        self, cli: str, name: str, overrides: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        case_dir = self.base / f"{cli}_{name}"
        bin_dir, calls = self.make_stubs(case_dir, cli)
        config = self.CONFIG[cli]
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.update(
            PATH=f"{bin_dir}:/usr/bin:/bin",
            CALLS=str(calls),
            COUNTER=str(case_dir / "counter"),
            PRE_OUT=config["pre"],
            POST_OUT="",
            POST_RC="0",
            NPM_VIEW="2.0.0",
            NPM_INSTALL_RC="0",
            NPM_RESOLVE_LINE=f"add {config['package']} 1.0.0 => 2.0.0",
            TMPDIR=str(case_dir),
            PYTHONDONTWRITEBYTECODE="1",
        )
        env.update(overrides)
        return subprocess.run(
            ["/bin/bash", str(CLI_SCRIPT), cli],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    @staticmethod
    def outcome(result: subprocess.CompletedProcess[str]) -> str:
        lines = [line for line in result.stdout.splitlines() if "_CLI_" in line]
        return lines[-1].split(" ", 1)[0] if lines else result.stdout.strip()

    def test_all_historical_cli_outcomes(self) -> None:
        for cli, config in self.CONFIG.items():
            prefix = config["prefix"]
            good = lambda version: config["post"].format(version=version)
            current_resolve = f"add {config['package']} 2.0.0 => 2.0.0"
            update_resolve = f"add {config['package']} 1.0.0 => 2.0.0"
            cases = (
                ("current", {"PRE_OUT": config["current"], "NPM_RESOLVE_LINE": current_resolve}, prefix + "_CURRENT"),
                ("held", {"PRE_OUT": config["current"], "NPM_RESOLVE_LINE": current_resolve, "NPM_VIEW": "2.5.0"}, prefix + "_HELD"),
                ("check_failed", {"NPM_RESOLVE_LINE": ""}, prefix + "_CHECK_FAILED"),
                ("failed_unchanged", {"NPM_RESOLVE_LINE": update_resolve, "NPM_INSTALL_RC": "1", "POST_OUT": good("1.0.0")}, prefix + "_UPDATE_FAILED"),
                ("failed_changed", {"NPM_RESOLVE_LINE": update_resolve, "NPM_INSTALL_RC": "1", "POST_OUT": good("1.5.0")}, prefix + "_UPDATE_FAILED"),
                ("updated", {"NPM_RESOLVE_LINE": update_resolve, "POST_OUT": good("2.0.0")}, prefix + "_UPDATED"),
                ("noop", {"NPM_RESOLVE_LINE": update_resolve, "POST_OUT": good("1.0.0")}, prefix + "_UPDATE_NOOP"),
                ("unverified_empty", {"NPM_RESOLVE_LINE": update_resolve, "POST_OUT": ""}, prefix + "_UPDATE_UNVERIFIED"),
                ("mismatch", {"NPM_RESOLVE_LINE": update_resolve, "POST_OUT": good("1.9.0")}, prefix + "_UPDATE_MISMATCH"),
                ("unverified_rc", {"NPM_RESOLVE_LINE": update_resolve, "POST_OUT": good("2.0.0"), "POST_RC": "7"}, prefix + "_UPDATE_UNVERIFIED"),
                ("unverified_malformed", {"NPM_RESOLVE_LINE": update_resolve, "POST_OUT": "Error: could not launch (build 2.0.0)" if cli == "claude" else "Error: cli crashed near 2.0.0"}, prefix + "_UPDATE_UNVERIFIED"),
                ("unverified_embedded", {"NPM_RESOLVE_LINE": update_resolve, "POST_OUT": "2.0.0garbage" if cli == "claude" else "Error: failed to run @salesforce/cli/2.0.0"}, prefix + "_UPDATE_UNVERIFIED"),
            )
            for name, overrides, expected in cases:
                with self.subTest(cli=cli, case=name):
                    result = self.run_case(cli, name, overrides)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self.outcome(result), expected)

    def test_invalid_selector_fails_before_any_cli_or_npm_call(self) -> None:
        for selector in (None, "invalid"):
            with self.subTest(selector=selector):
                case_dir = self.base / (selector or "missing")
                bin_dir, calls = self.make_stubs(case_dir, "sf")
                arguments = ["/bin/bash", str(CLI_SCRIPT)]
                if selector is not None:
                    arguments.append(selector)
                result = subprocess.run(
                    arguments,
                    env={
                        **os.environ,
                        "PATH": f"{bin_dir}:/usr/bin:/bin",
                        "CALLS": str(calls),
                    },
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(calls.exists())


if __name__ == "__main__":
    unittest.main()
