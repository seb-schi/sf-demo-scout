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

import stand_ins


ROOT = Path(__file__).resolve().parents[1]
CLI_SCRIPT = ROOT / "scripts" / "setup_cli_refresh.py"
# How long setup-cli-owner.py waits for `npm root -g`: npm.cmd starts slowly on Windows.
NPM_ROOT_LIMIT = 10 if stand_ins.WINDOWS else 2
# Stands in for npm: it logs each call to $CALLS and answers the way the NPM_* variables say.
NPM_STAND_IN = r'''import os, sys, time
command = " ".join(sys.argv[1:])
with open(os.environ["CALLS"], "ab") as calls:
    calls.write(("npm " + command + "\n").encode())
def say(text):
    sys.stdout.buffer.write(text.encode() + b"\n")
if command == "root -g":
    if os.environ.get("NPM_ROOT_DELAY"):
        time.sleep(float(os.environ["NPM_ROOT_DELAY"]))
    if os.environ.get("NPM_ROOT_INVALID_UTF8") == "1":
        sys.stdout.buffer.write(b"\xff\n")
    else:
        say(os.environ.get("NPM_ROOT", ""))
    sys.exit(int(os.environ.get("NPM_ROOT_RC") or 0))
if "--dry-run" in command:
    say(os.environ.get("NPM_RESOLVE_LINE", ""))
    sys.exit(int(os.environ.get("NPM_DRY_RUN_RC") or 0))
if "view" in command:
    say(os.environ.get("NPM_VIEW", ""))
    sys.exit(0)
say("npm install log")
sys.exit(int(os.environ.get("NPM_INSTALL_RC") or 0))
'''
# Stands in for the Salesforce CLI: it logs each call to $CALLS; its first --version prints PRE_OUT and exits PRE_RC,
# each later one POST_OUT and POST_RC, counted in $COUNTER.
SF_STAND_IN = r'''import os, sys
arguments = sys.argv[1:]
with open(os.environ["CALLS"], "ab") as calls:
    calls.write((sys.argv[0] + " " + " ".join(arguments) + "\n").encode())
if arguments[:1] == ["--version"]:
    counter = os.environ.get("COUNTER", "")
    try:
        with open(counter) as stream:
            count = int(stream.read()) + 1
    except (OSError, ValueError):
        count = 1
    try:
        with open(counter, "w") as stream:
            stream.write(str(count))
    except OSError:
        pass
    first = count == 1
    sys.stdout.buffer.write(os.environ.get("PRE_OUT" if first else "POST_OUT", "").encode() + b"\n")
    sys.exit(int(os.environ.get("PRE_RC" if first else "POST_RC") or 0))
'''


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

    @staticmethod
    def npm_root(case_dir: Path) -> Path:
        """What the stand-in's `npm root -g` answers: on Windows, npm keeps node_modules beside its shims."""
        return case_dir / "bin" / "node_modules" if stand_ins.WINDOWS else case_dir / "npm-root"

    def make_stubs(self, case_dir: Path, cli: str) -> tuple[Path, Path]:
        """npm, and the CLI as `npm install --global` lays it out on this platform."""
        stand_ins.require_node()  # on Windows the refresh runs the CLI's run.js with Node, as for a real npm install
        bin_dir = case_dir / "bin"
        bin_dir.mkdir(parents=True)
        calls = case_dir / "calls.log"
        stand_ins.tool(bin_dir, "npm", NPM_STAND_IN)
        package = self.CONFIG[cli]["package"]
        package_dir = self.npm_root(case_dir) / package
        if stand_ins.WINDOWS:
            # npm's sf.cmd shim, which starts node_modules\@salesforce\cli\bin\run.js, the package's declared bin
            stand_ins.salesforce_cli(bin_dir, SF_STAND_IN)
            entry = "bin/run.js"
        else:
            # npm's symlink on the PATH, to the package's declared bin
            (package_dir / "bin").mkdir(parents=True)
            (bin_dir / cli).symlink_to(stand_ins.tool(package_dir / "bin", cli, SF_STAND_IN))
            entry = f"bin/{cli}"
        (package_dir / "package.json").write_text(
            json.dumps({"name": package, "bin": {cli: entry}})
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
            metadata_path = self.npm_root(case_dir) / config["package"] / "package.json"
            metadata = json.loads(metadata_path.read_text())
            metadata["name"] = package_name
            metadata_path.write_text(json.dumps(metadata))
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.update(stand_ins.cli_environment(bin_dir, "/usr/bin", "/bin"))
        env.update(
            CALLS=str(calls),
            COUNTER=str(case_dir / "counter"),
            PRE_OUT=config["pre"],
            PRE_RC="0",
            POST_OUT="",
            POST_RC="0",
            NPM_VIEW="2.0.0",
            NPM_INSTALL_RC="0",
            NPM_DRY_RUN_RC="0",
            NPM_ROOT=str(self.npm_root(case_dir)),
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
                        "PATH": stand_ins.path(bin_dir, "/usr/bin", "/bin"),
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
                stand_ins.salesforce_cli(shadow, 'print("native")\n')  # another installation, first on the PATH
                config = self.CONFIG[cli]
                result = subprocess.run(
                    [sys.executable, "-B", str(CLI_SCRIPT), cli],
                    env={
                        **os.environ,
                        **stand_ins.cli_environment(shadow, bin_dir, "/usr/bin", "/bin"),
                        "CALLS": str(calls),
                        "COUNTER": str(case_dir / "counter"),
                        "PRE_OUT": config["pre"],
                        "POST_OUT": "",
                        "NPM_VIEW": "2.0.0",
                        "NPM_INSTALL_RC": "0",
                        "NPM_RESOLVE_LINE": f"add {config['package']} 1.0.0 => 2.0.0",
                        "NPM_ROOT": str(self.npm_root(case_dir)),
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
            # On Windows the owner check's timeout ends npm.cmd's cmd.exe, not the npm under it, and still waits for
            # npm's output, so this case lasts the whole delay there.
            ("timeout", {"NPM_ROOT_DELAY": str(NPM_ROOT_LIMIT + 1)}),
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
                if not executable and stand_ins.WINDOWS:
                    self.skipTest("Windows has no execute permission to take away: any existing file passes X_OK")
                case_dir = self.base / f"malformed_{name}"
                bin_dir, calls = self.make_stubs(case_dir, "sf")
                package = self.npm_root(case_dir) / "@salesforce" / "cli"
                (package / "package.json").write_text(metadata)
                if not executable:
                    (package / "bin" / "sf").chmod(0o600)
                result = subprocess.run(
                    [sys.executable, "-B", str(CLI_SCRIPT), "sf"],
                    env={
                        **os.environ,
                        **stand_ins.cli_environment(bin_dir, "/usr/bin", "/bin"),
                        "CALLS": str(calls),
                        "NPM_ROOT": str(self.npm_root(case_dir)),
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
                    stand_ins.tool(bin_dir, "npm", 'import os\nwith open(os.environ["CALLS"], "a") as calls:\n'
                                                   '    calls.write("called\\n")\n')
                if missing != "sf":
                    stand_ins.tool(bin_dir, "sf", 'print("native")\n')
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
                        "PATH": stand_ins.path(bin_dir, "/bin"),  # no Node folder: on Windows it holds a real npm
                        "CALLS": str(calls),
                        "PYTHONDONTWRITEBYTECODE": "1",
                    },
                    text=True, capture_output=True, check=False,
                )
                self.assertEqual(self.outcome(result), "SF_CLI_OWNERSHIP_UNVERIFIED")
                self.assertFalse(calls.exists())

if __name__ == "__main__":
    unittest.main()
