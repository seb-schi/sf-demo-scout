"""Hermetic regressions for the shipped Salesforce CLI refresh (scripts/setup_cli_refresh.py)."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import json


ROOT = Path(__file__).resolve().parents[1]
CLI_SCRIPT = ROOT / "scripts" / "setup_cli_refresh.py"


@unittest.skipUnless(Path("/bin/bash").exists(), "the npm and sf stubs are bash scripts")
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
  "root -g")
    [ -n "$NPM_ROOT_DELAY" ] && sleep "$NPM_ROOT_DELAY"
    if [ "$NPM_ROOT_INVALID_UTF8" = 1 ]; then printf '\377\n'; else printf '%s\n' "$NPM_ROOT"; fi
    exit "${NPM_ROOT_RC:-0}" ;;
  *--dry-run*) printf '%s\n' "$NPM_RESOLVE_LINE"; exit "${NPM_DRY_RUN_RC:-0}" ;;
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
  if [ "$n" -eq 1 ]; then printf '%s\n' "$PRE_OUT"; exit "${PRE_RC:-0}"; fi
  printf '%s\n' "$POST_OUT"; exit "${POST_RC:-0}"
fi
exit 0
"""
        )
        tool.chmod(0o700)
        package = self.CONFIG[cli]["package"]
        package_dir = case_dir / "npm-root" / package
        package_dir.mkdir(parents=True)
        package_bin = package_dir / "bin" / cli
        package_bin.parent.mkdir()
        package_bin.write_text(tool.read_text())
        package_bin.chmod(0o700)
        tool.unlink()
        tool.symlink_to(package_bin)
        (package_dir / "package.json").write_text(
            json.dumps({"name": package, "bin": {cli: f"bin/{cli}"}})
        )
        return bin_dir, calls

    def run_case(
        self, cli: str, name: str, overrides: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        case_dir = self.base / f"{cli}_{name}"
        bin_dir, calls = self.make_stubs(case_dir, cli)
        config = self.CONFIG[cli]
        package_name = overrides.pop("PACKAGE_NAME", None)
        if package_name is not None:
            metadata_path = case_dir / "npm-root" / config["package"] / "package.json"
            metadata = json.loads(metadata_path.read_text())
            metadata["name"] = package_name
            metadata_path.write_text(json.dumps(metadata))
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.update(
            PATH=f"{bin_dir}:/usr/bin:/bin",
            CALLS=str(calls),
            COUNTER=str(case_dir / "counter"),
            PRE_OUT=config["pre"],
            PRE_RC="0",
            POST_OUT="",
            POST_RC="0",
            NPM_VIEW="2.0.0",
            NPM_INSTALL_RC="0",
            NPM_DRY_RUN_RC="0",
            NPM_ROOT=str(case_dir / "npm-root"),
            NPM_ROOT_RC="0",
            NPM_ROOT_DELAY="",
            NPM_ROOT_INVALID_UTF8="0",
            NPM_RESOLVE_LINE=f"add {config['package']} 1.0.0 => 2.0.0",
            TMPDIR=str(case_dir),
            PYTHONDONTWRITEBYTECODE="1",
        )
        env.update(overrides)
        return subprocess.run(
            [sys.executable, "-B", str(CLI_SCRIPT), cli],
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
                ("unverified_malformed", {"NPM_RESOLVE_LINE": update_resolve, "POST_OUT": "Error: cli crashed near 2.0.0"}, prefix + "_UPDATE_UNVERIFIED"),
                ("unverified_embedded", {"NPM_RESOLVE_LINE": update_resolve, "POST_OUT": "Error: failed to run @salesforce/cli/2.0.0"}, prefix + "_UPDATE_UNVERIFIED"),
            )
            for name, overrides, expected in cases:
                with self.subTest(cli=cli, case=name):
                    result = self.run_case(cli, name, overrides)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self.outcome(result), expected)

    def test_preupdate_probes_fail_closed_without_installing(self) -> None:
        """A failed, malformed, or ambiguous probe must never authorize update."""
        for cli, config in self.CONFIG.items():
            prefix = config["prefix"]
            update = f"add {config['package']} 1.0.0 => 2.0.0"
            cases = (
                (
                    "pre_nonzero_plausible",
                    {"PRE_OUT": config["pre"], "PRE_RC": "17"},
                ),
                (
                    "pre_zero_malformed",
                    {"PRE_OUT": "ERROR probe 1.0.0"},
                ),
                (
                    "pre_zero_ambiguous",
                    {"PRE_OUT": config["pre"] + "\n" + config["current"]},
                ),
                (
                    "dry_nonzero_plausible",
                    {"NPM_RESOLVE_LINE": update, "NPM_DRY_RUN_RC": "23"},
                ),
                (
                    "dry_zero_malformed",
                    {"NPM_RESOLVE_LINE": f"ERROR {config['package']} 1.0.0 => 2.0.0"},
                ),
                (
                    "dry_zero_ambiguous",
                    {"NPM_RESOLVE_LINE": update + "\n" + update.replace("2.0.0", "2.1.0")},
                ),
                (
                    "dry_wrong_installed_version",
                    {"NPM_RESOLVE_LINE": f"add {config['package']} 9.9.9 => 2.0.0"},
                ),
            )
            for name, overrides in cases:
                with self.subTest(cli=cli, case=name):
                    result = self.run_case(
                        cli,
                        name,
                        {
                            "POST_OUT": config["post"].format(version="2.0.0"),
                            **overrides,
                        },
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self.outcome(result), prefix + "_CHECK_FAILED")
                    call_lines = (
                        self.base / f"{cli}_{name}" / "calls.log"
                    ).read_text().splitlines()
                    self.assertNotIn(
                        f"npm install {config['package']} --global", call_lines
                    )

    def test_real_npm_change_transition_can_authorize_update(self) -> None:
        """npm reports an existing global package update with the `change` verb."""
        for cli, config in self.CONFIG.items():
            with self.subTest(cli=cli):
                result = self.run_case(
                    cli,
                    "real_change_transition",
                    {
                        "NPM_RESOLVE_LINE": (
                            f"change {config['package']} 1.0.0 => 2.0.0"
                        ),
                        "POST_OUT": config["post"].format(version="2.0.0"),
                    },
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.outcome(result), config["prefix"] + "_UPDATED")

    def test_invalid_selector_fails_before_any_cli_or_npm_call(self) -> None:
        for selector in (None, "invalid", "claude"):  # Claude Code updates itself; setup leaves it alone
            with self.subTest(selector=selector):
                case_dir = self.base / (selector or "missing")
                bin_dir, calls = self.make_stubs(case_dir, "sf")
                arguments = [sys.executable, "-B", str(CLI_SCRIPT)]
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

    def test_non_npm_and_unavailable_ownership_skip_before_registry_calls(self) -> None:
        for case, overrides in (
            ("not_salesforce", {"PACKAGE_NAME": "not-salesforce"}),
            ("root_failed", {"NPM_ROOT_RC": "7"}),
        ):
            cli = "sf"
            with self.subTest(case=case):
                name = f"ownership_skip_{case}"
                result = self.run_case(cli, name, dict(overrides))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    self.outcome(result),
                    self.CONFIG[cli]["prefix"] + "_OWNERSHIP_UNVERIFIED",
                )
                calls = self.base / f"{cli}_{name}" / "calls.log"
                npm_calls = [
                    line for line in (calls.read_text() if calls.exists() else "").splitlines()
                    if line.startswith("npm ")
                ]
                self.assertEqual(npm_calls, ["npm root -g"])

    def test_shadowed_executable_skips_before_registry_calls(self) -> None:
        for cli in self.CONFIG:
            with self.subTest(cli=cli):
                case_dir = self.base / f"shadowed_{cli}"
                bin_dir, calls = self.make_stubs(case_dir, cli)
                shadow = case_dir / "shadow"
                shadow.mkdir()
                (shadow / cli).write_text("#!/bin/bash\necho native\n")
                (shadow / cli).chmod(0o700)
                config = self.CONFIG[cli]
                result = subprocess.run(
                    [sys.executable, "-B", str(CLI_SCRIPT), cli],
                    env={
                        **os.environ,
                        "PATH": f"{shadow}:{bin_dir}:/usr/bin:/bin",
                        "CALLS": str(calls),
                        "COUNTER": str(case_dir / "counter"),
                        "PRE_OUT": config["pre"],
                        "POST_OUT": "",
                        "NPM_VIEW": "2.0.0",
                        "NPM_INSTALL_RC": "0",
                        "NPM_RESOLVE_LINE": f"add {config['package']} 1.0.0 => 2.0.0",
                        "NPM_ROOT": str(case_dir / "npm-root"),
                        "TMPDIR": str(case_dir),
                        "PYTHONDONTWRITEBYTECODE": "1",
                    },
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(
                    self.outcome(result), config["prefix"] + "_NOT_NPM_OWNED"
                )
                self.assertEqual(calls.read_text().splitlines(), ["npm root -g"])

    def test_malformed_ambiguous_and_bounded_ownership_probes_skip(self) -> None:
        cases = (
            ("relative_root", {"NPM_ROOT": "relative/root"}),
            ("ambiguous_root", {"NPM_ROOT": "/one\n/two"}),
            ("invalid_utf8", {"NPM_ROOT_INVALID_UTF8": "1"}),
            ("timeout", {"NPM_ROOT_DELAY": "3"}),
        )
        for name, overrides in cases:
            with self.subTest(name=name):
                result = self.run_case("sf", name, dict(overrides))
                self.assertEqual(self.outcome(result), "SF_CLI_OWNERSHIP_UNVERIFIED")
                calls = self.base / f"sf_{name}" / "calls.log"
                self.assertEqual(calls.read_text().splitlines(), ["npm root -g"])

    def test_malformed_package_and_bin_metadata_skip(self) -> None:
        for name, metadata, executable in (
            ("bad_json", "{", True),
            ("wrong_name", json.dumps({"name": "other", "bin": {"sf": "bin/sf"}}), True),
            ("bad_bin", json.dumps({"name": "@salesforce/cli", "bin": []}), True),
            ("traversal", json.dumps({"name": "@salesforce/cli", "bin": {"sf": "../sf"}}), True),
            ("string_shorthand", json.dumps({"name": "@salesforce/cli", "bin": "bin/sf"}), True),
            ("non_executable", json.dumps({"name": "@salesforce/cli", "bin": {"sf": "bin/sf"}}), False),
        ):
            with self.subTest(name=name):
                case_dir = self.base / f"malformed_{name}"
                bin_dir, calls = self.make_stubs(case_dir, "sf")
                package = case_dir / "npm-root" / "@salesforce" / "cli"
                (package / "package.json").write_text(metadata)
                if not executable:
                    (package / "bin" / "sf").chmod(0o600)
                result = subprocess.run(
                    [sys.executable, "-B", str(CLI_SCRIPT), "sf"],
                    env={
                        **os.environ,
                        "PATH": f"{bin_dir}:/usr/bin:/bin",
                        "CALLS": str(calls),
                        "NPM_ROOT": str(case_dir / "npm-root"),
                        "NPM_ROOT_RC": "0",
                        "NPM_ROOT_DELAY": "",
                        "NPM_ROOT_INVALID_UTF8": "0",
                        "PYTHONDONTWRITEBYTECODE": "1",
                    },
                    text=True, capture_output=True, check=False,
                )
                self.assertEqual(self.outcome(result), "SF_CLI_OWNERSHIP_UNVERIFIED")
                self.assertEqual(calls.read_text().splitlines(), ["npm root -g"])

    def test_shell_functions_cannot_replace_verified_executables(self) -> None:
        result = self.run_case(
            "sf",
            "shell_functions",
            {
                "BASH_FUNC_npm%%": "() { echo poisoned; }",
                "BASH_FUNC_sf%%": "() { echo poisoned; }",
                "PRE_OUT": self.CONFIG["sf"]["current"],
                "NPM_RESOLVE_LINE": "add @salesforce/cli 2.0.0 => 2.0.0",
            },
        )
        self.assertEqual(self.outcome(result), "SF_CLI_CURRENT")

    def test_missing_npm_cli_or_owner_helper_skips_without_running_npm(self) -> None:
        # Each prerequisite the refresh still has; Python itself is the one running it.
        for missing in ("npm", "sf", "owner helper"):
            with self.subTest(missing=missing):
                case_dir = self.base / f"missing_{missing.replace(' ', '_')}"
                bin_dir = case_dir / "bin"
                bin_dir.mkdir(parents=True)
                calls = case_dir / "calls.log"
                if missing != "npm":
                    npm = bin_dir / "npm"
                    npm.write_text("#!/bin/bash\necho called >> \"$CALLS\"\n")
                    npm.chmod(0o700)
                if missing != "sf":
                    sf = bin_dir / "sf"
                    sf.write_text("#!/bin/bash\necho native\n")
                    sf.chmod(0o700)
                script = CLI_SCRIPT
                if missing == "owner helper":
                    scripts = case_dir / "scripts"
                    scripts.mkdir()
                    for name in ("setup_cli_refresh.py", "scout_portable.py"):
                        shutil.copyfile(ROOT / "scripts" / name, scripts / name)
                    script = scripts / "setup_cli_refresh.py"
                result = subprocess.run(
                    [sys.executable, "-B", str(script), "sf"],
                    env={
                        **os.environ,
                        "PATH": f"{bin_dir}:/bin",
                        "CALLS": str(calls),
                        "PYTHONDONTWRITEBYTECODE": "1",
                    },
                    text=True, capture_output=True, check=False,
                )
                self.assertEqual(self.outcome(result), "SF_CLI_OWNERSHIP_UNVERIFIED")
                self.assertFalse(calls.exists())

if __name__ == "__main__":
    unittest.main()
