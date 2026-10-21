"""Two Windows setup outcomes, with the platform injected so they run on any machine.

- A tool installed after the app started isn't on this window's PATH: Windows gives each window the PATH it had when it
  started. setup_bootstrap.py finds it in its usual install location and says to reopen the app, rather than to install
  it again.
- The Salesforce CLI from Salesforce's Windows installer runs through a launcher in a folder with a space, which a quoted
  argument breaks in a coding tool's own calls. setup_cli_refresh.py says so and how to switch to npm's copy.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

import stand_ins

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True
import scout_portable  # noqa: E402

# Salesforce's installer writes this launcher to <install folder>\bin\sf.cmd; npm's cmd-shim writes the other one.
INSTALLER_LAUNCHER = ('@echo off\r\nsetlocal enableextensions\r\n'
                      'if exist "%LOCALAPPDATA%\\sf\\client\\bin\\sf.cmd" (\r\n'
                      '  "%LOCALAPPDATA%\\sf\\client\\bin\\sf.cmd" %*\r\n) else (\r\n'
                      '  "%~dp0\\..\\client\\bin\\node.exe" "%~dp0\\..\\client\\bin\\run" %*\r\n)\r\n')
NPM_SHIM = ('@ECHO off\r\nGOTO start\r\n:find_dp0\r\nSET dp0=%~dp0\r\nEXIT /b\r\n:start\r\nSETLOCAL\r\nCALL :find_dp0\r\n'
            'IF EXIST "%dp0%\\node.exe" (\r\n  SET "_prog=%dp0%\\node.exe"\r\n) ELSE (\r\n  SET "_prog=node"\r\n)\r\n'
            'endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & "%_prog%"  '
            '"%dp0%\\node_modules\\@salesforce\\cli\\bin\\run.js" %*\r\n')
REOPEN = "open a new PowerShell window and quit and reopen the app, so it's found"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BOOTSTRAP = load("setup_bootstrap_windows_setup", SCRIPTS / "setup_bootstrap.py")
REFRESH = load("setup_cli_refresh_windows_setup", SCRIPTS / "setup_cli_refresh.py")


def as_platform(platform: str = "win32"):
    return mock.patch.object(scout_portable, "PLATFORM", platform)


def write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class NotInThisWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="scout-not-in-window-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.program_files = self.base / "Program Files"
        self.local = self.base / "AppData" / "Local"
        self.roaming = self.base / "AppData" / "Roaming"
        (self.base / "PATH").mkdir()
        # This window's PATH holds none of the tools; the install locations come only from these variables.
        self.environment = {"PATH": str(self.base / "PATH"), "ProgramFiles": str(self.program_files),
                            "ProgramW6432": str(self.program_files), "LOCALAPPDATA": str(self.local),
                            "APPDATA": str(self.roaming)}

    def bootstrap(self, selector: str, platform: str = "win32", **environment: str) -> tuple[int, str]:
        """The bootstrap's outcome and output; it may run no command, so a look at the install locations is
        existence checks only."""
        output = io.StringIO()
        refuse = AssertionError("this step runs no command")
        with as_platform(platform), mock.patch.dict(os.environ, {**self.environment, **environment}), \
                mock.patch("subprocess.Popen", side_effect=refuse), mock.patch("subprocess.run", side_effect=refuse), \
                contextlib.redirect_stdout(output):
            code = BOOTSTRAP.main(["setup_bootstrap.py", selector])
        return code, output.getvalue()

    def test_a_tool_that_is_nowhere_is_still_missing(self) -> None:
        for selector, expected in (("node", "NODE_MISSING (install it with: winget install --exact --id OpenJS.NodeJS.LTS)\n"),
                                   ("python", "PYTHON_MISSING (install it with: winget install --exact --id "
                                              "Python.PythonInstallManager, then: pymanager install default)\n"),
                                   ("sf", "SF_CLI_MISSING (install it with: npm.cmd install --global @salesforce/cli)\n")):
            with self.subTest(selector=selector):
                self.assertEqual(self.bootstrap(selector), (1, expected))

    def test_node_from_its_installer_is_installed_but_not_in_this_window(self) -> None:
        node = write(self.program_files / "nodejs" / "node.exe")
        self.assertEqual(self.bootstrap("node"), (1, f"NODE_NOT_IN_THIS_WINDOW (found at {node}; {REOPEN})\n"))

    def test_a_32_bit_python_still_looks_in_the_64_bit_program_files(self) -> None:
        # A 32-bit process sees Program Files (x86) as %ProgramFiles%; %ProgramW6432% still names the 64-bit folder.
        node = write(self.program_files / "nodejs" / "node.exe")
        x86 = str(self.base / "Program Files (x86)")
        self.assertEqual(self.bootstrap("node", ProgramFiles=x86),
                         (1, f"NODE_NOT_IN_THIS_WINDOW (found at {node}; {REOPEN})\n"))

    def test_each_python_install_location_counts(self) -> None:
        aliases = self.local / "Microsoft" / "WindowsApps"
        for name, path in (("install manager", aliases / "pymanager.exe"), ("its py alias", aliases / "py.exe"),
                           ("its global shortcuts", self.local / "Python" / "bin" / "python.exe"),
                           ("the classic installer", self.local / "Programs" / "Python" / "Python313" / "python.exe")):
            with self.subTest(location=name):
                write(path)
                try:
                    self.assertEqual(self.bootstrap("python"),
                                     (1, f"PYTHON_NOT_IN_THIS_WINDOW (found at {path}; {REOPEN})\n"))
                finally:
                    path.unlink()

    def test_the_newest_classic_python_is_named_and_store_stubs_never_count(self) -> None:
        write(self.local / "Microsoft" / "WindowsApps" / "python.exe")  # the Store's install stubs
        write(self.local / "Microsoft" / "WindowsApps" / "python3.exe")
        self.assertEqual(self.bootstrap("python")[1].split(" ", 1)[0], "PYTHON_MISSING")
        programs = self.local / "Programs" / "Python"
        for folder in ("Python39", "Python313", "Python312"):
            write(programs / folder / "python.exe")
        newest = programs / "Python313" / "python.exe"
        self.assertEqual(self.bootstrap("python"), (1, f"PYTHON_NOT_IN_THIS_WINDOW (found at {newest}; {REOPEN})\n"))

    def test_the_salesforce_cli_from_npm_or_its_installer_is_not_in_this_window(self) -> None:
        for name, path in (("npm", self.roaming / "npm" / "sf.cmd"),
                           ("Salesforce's installer", self.program_files / "sf" / "bin" / "sf.cmd")):
            with self.subTest(source=name):
                write(path)
                try:
                    self.assertEqual(self.bootstrap("sf"), (1, f"SF_CLI_NOT_IN_THIS_WINDOW (found at {path}; {REOPEN})\n"))
                finally:
                    path.unlink()

    def test_without_those_variables_nothing_is_guessed(self) -> None:
        write(self.program_files / "nodejs" / "node.exe")
        with mock.patch.dict(os.environ):
            for name in ("ProgramFiles", "ProgramW6432", "LOCALAPPDATA", "APPDATA"):
                self.environment.pop(name)
                os.environ.pop(name, None)
            self.assertEqual(self.bootstrap("node")[1].split(" ", 1)[0], "NODE_MISSING")

    def test_only_windows_looks_beyond_the_path(self) -> None:
        # On macOS and Linux a missing tool is installed as before; here Homebrew is missing too, so nothing runs.
        write(self.program_files / "nodejs" / "node.exe")
        self.assertEqual(self.bootstrap("node", platform="darwin"), (1, "NODE_UNAVAILABLE (brew prerequisite missing)\n"))

    def test_setup_maps_the_outcome_to_a_reopen_not_an_install(self) -> None:
        prompt = (ROOT / "prompts" / "setup" / "fresh-install.md").read_text(encoding="utf-8")
        bullets = [bullet for bullet in re.split(r"\n(?=- )", prompt) if bullet.startswith("- `*_NOT_IN_THIS_WINDOW`")]
        self.assertEqual(len(bullets), 1, "fresh-install.md maps *_NOT_IN_THIS_WINDOW once")
        bullet = " ".join(bullets[0].split())
        for words in ("ABORT", "installed", "new PowerShell window", "reopen", "/scout-setup", "Don't install it again"):
            self.assertIn(words, bullet)


class WindowsInstallerCliTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="scout-installer-cli-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.local = self.base / "AppData" / "Local"  # holds no update of the installer's CLI
        self.calls = self.base / "npm-calls.log"
        self.npm_root = self.base / "npm-root"  # npm's global packages: no Salesforce CLI among them
        self.npm_root.mkdir()
        (self.base / "npm-bin").mkdir()
        self.npm = stand_ins.tool(self.base / "npm-bin", "npm",
                                  "import sys\nwith open(%r, 'a') as log:\n    log.write(' '.join(sys.argv[1:]) + '\\n')\n"
                                  "print(%r)\n" % (str(self.calls), str(self.npm_root)))

    def installer(self, folder: Path) -> Path:
        """Salesforce's installer layout: bin\\sf.cmd, and the client it starts with its own node.exe."""
        write(folder / "client" / "bin" / "run", "// the CLI")
        write(folder / "client" / "bin" / "node.exe")
        write(folder / "client" / "package.json", json.dumps({"name": "@salesforce/cli"}))
        return write(folder / "bin" / "sf.cmd", INSTALLER_LAUNCHER)

    def refresh(self, sf: Path, platform: str = "win32", owner: str | None = None) -> tuple[int, str]:
        """The refresh with this `sf` and the npm stand-in active; `owner` stands in for the ownership proof."""
        found = {"npm": str(self.npm), "sf": str(sf)}
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(as_platform(platform))
            stack.enter_context(mock.patch.object(scout_portable, "shell_which", side_effect=found.get))
            stack.enter_context(mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.local)}))
            if owner is not None:
                stack.enter_context(mock.patch.object(REFRESH, "ownership", return_value=owner))
            stack.enter_context(contextlib.redirect_stdout(output))
            code = REFRESH.main(["setup_cli_refresh.py", "sf"])
        return code, output.getvalue()

    def npm_calls(self) -> list[str]:
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_the_installers_cli_gets_its_own_note_and_no_update(self) -> None:
        # What a tester's machine printed for this CLI: SF_CLI_OWNERSHIP_UNVERIFIED, since npm's packages hold no CLI.
        launcher = self.installer(self.base / "Program Files" / "sf")
        code, output = self.refresh(launcher)
        self.assertEqual(code, 0)
        self.assertEqual(output, f"SF_CLI_WINDOWS_INSTALLER ({launcher}; the Windows installer's copy, whose launcher "
                                 "breaks when an argument is quoted; skipped update)\n")
        self.assertEqual(self.npm_calls(), ["root -g"])  # the ownership probe only: no dry run, view or install

    def test_it_replaces_the_not_npm_owned_outcome_too(self) -> None:
        launcher = self.installer(self.base / "Program Files" / "sf")
        for owner in ("different", "unavailable"):
            with self.subTest(owner=owner):
                code, output = self.refresh(launcher, owner=owner)
                self.assertEqual((code, output.split(" ", 1)[0]), (0, "SF_CLI_WINDOWS_INSTALLER"))

    def test_other_launchers_keep_their_outcomes(self) -> None:
        no_space = self.installer(self.base / "Tools" / "sf")  # cmd.exe keeps a path without a space whole
        shim = write(self.base / "Program Files" / "npm" / "sf.cmd", NPM_SHIM)  # npm's own shim, not the installer's
        write(self.base / "Program Files" / "npm" / "node_modules" / "@salesforce" / "cli" / "bin" / "run.js")
        write(self.base / "Program Files" / "npm" / "node.exe")
        unresolved = write(self.base / "Program Files" / "other" / "bin" / "sf.cmd", INSTALLER_LAUNCHER)  # no client
        installer = self.installer(self.base / "Program Files" / "sf")
        cases = [("npm shim", shim, "win32"), ("no installer client", unresolved, "win32"), ("macOS", installer, "darwin")]
        if " " not in str(self.base):  # a temp folder with a space would put one in every path here
            cases.append(("no space", no_space, "win32"))
        for name, sf, platform in cases:
            for owner, expected in (("different", "SF_CLI_NOT_NPM_OWNED"), ("unavailable", "SF_CLI_OWNERSHIP_UNVERIFIED")):
                with self.subTest(launcher=name, owner=owner):
                    code, output = self.refresh(sf, platform=platform, owner=owner)
                    self.assertEqual((code, output.split(" ", 1)[0]), (0, expected))

    def test_the_done_message_maps_every_cli_outcome_and_the_installer_note(self) -> None:
        done = (ROOT / "prompts" / "setup" / "done.md").read_text(encoding="utf-8")
        printed = set(re.findall(r"\bSF_CLI_[A-Z_]+", (SCRIPTS / "setup_cli_refresh.py").read_text(encoding="utf-8")))
        self.assertIn("SF_CLI_WINDOWS_INSTALLER", printed)
        self.assertEqual(sorted(token for token in printed if f"`{token}" not in done), [])
        note, = [line for line in done.splitlines() if line.startswith("- `SF_CLI_WINDOWS_INSTALLER`")]
        for words in ("Windows installer's copy", "Scout's own steps still work", "quoted", "Settings → Apps",
                      "saved logins stay", "npm.cmd install --global @salesforce/cli", "new PowerShell window",
                      "reopen the app", "Not an error"):
            self.assertIn(words, note)


if __name__ == "__main__":
    unittest.main()
