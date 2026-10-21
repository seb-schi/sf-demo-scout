"""Hermetic regressions for first-install tool bootstrapping (scripts/setup_bootstrap.py)."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import stand_ins


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "setup_bootstrap.py"
FRESH_PROMPT = ROOT / "prompts" / "setup" / "fresh-install.md"
PLACEHOLDER = "/absolute/path/of/active/sf-demo-scout/scripts/setup_bootstrap.py"
NEEDS_BASH = unittest.skipUnless(Path("/bin/bash").exists(), "the tool and installer stubs are bash scripts")
# Runs the bootstrap with its Windows branches switched on, on any machine.
AS_WINDOWS = """import runpy, sys
sys.path.insert(0, sys.argv[2])
import scout_portable
scout_portable.PLATFORM = "win32"
scout_portable.process_group_options = lambda: {}  # Windows' process creation flags exist only on Windows
script = sys.argv[1]
sys.argv = [script] + sys.argv[3:]
runpy.run_path(script, run_name="__main__")
"""


class BootstrapScriptTests(unittest.TestCase):
    VERSIONS = {
        "node": "v22.20.0",
        "python": "Python 3.9.19",
        "sf": "@salesforce/cli/2.100.2 darwin-arm64 node-v22.16.0",
    }
    TOOLS = {"node": "node", "python": "python3", "sf": "sf"}
    MANAGERS = {"node": "brew", "python": "brew", "sf": "npm"}
    PREFIXES = {"node": "NODE", "python": "PYTHON", "sf": "SF_CLI"}

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="scout-bootstrap-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    @staticmethod
    def write_executable(path: Path, body: str) -> None:
        path.write_text("#!/bin/bash\n" + body)
        path.chmod(0o700)

    def make_case(
        self,
        name: str,
        selector: str,
        *,
        existing_output: str | None = None,
        existing_stderr: str = "",
        existing_rc: int = 0,
        manager: bool = True,
        install_rc: int = 0,
        post_output: str | None = None,
        post_stderr: str = "",
        post_rc: int = 0,
        log_folder_ok: bool = True,
        executable: bool = True,
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        case = self.base / name
        bin_dir = case / "bin"
        bin_dir.mkdir(parents=True)
        calls = case / "calls.log"
        tool = self.TOOLS[selector]
        if existing_output is not None:
            self.write_executable(
                bin_dir / tool,
                f"printf 'tool {tool} %s\\n' \"$*\" >> \"$CALLS\"\n"
                f"printf '%s\\n' \"$TOOL_OUTPUT\"\nexit {existing_rc}\n",
            )
            if existing_stderr:
                body = (bin_dir / tool).read_text().replace(
                    f"exit {existing_rc}\n",
                    f"printf '%s\\n' \"$TOOL_STDERR\" >&2\nexit {existing_rc}\n",
                )
                (bin_dir / tool).write_text(body)
            if not executable:
                (bin_dir / tool).chmod(0o600)
        post_tool = case / "post-tool"
        if post_output is not None:
            self.write_executable(
                post_tool,
                f"printf 'tool {tool} %s\\n' \"$*\" >> \"$CALLS\"\n"
                f"printf '%s\\n' \"$POST_OUTPUT\"\nexit {post_rc}\n",
            )
            if post_stderr:
                body = post_tool.read_text().replace(
                    f"exit {post_rc}\n",
                    f"printf '%s\\n' \"$POST_STDERR\" >&2\nexit {post_rc}\n",
                )
                post_tool.write_text(body)
        if manager:
            manager_path = bin_dir / self.MANAGERS[selector]
            self.write_executable(
                manager_path,
                "printf 'manager %s\\n' \"$*\" >> \"$CALLS\"\n"
                "if [ -n \"$POST_TOOL\" ]; then /bin/ln -s \"$POST_TOOL\" \"$BIN_DIR/$TOOL_NAME\"; fi\n"
                f"exit {install_rc}\n",
            )
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.update(
            # The case's own folder only: on Linux /bin is /usr/bin, which holds the machine's own python3.
            PATH=str(bin_dir),
            CALLS=str(calls),
            BIN_DIR=str(bin_dir),
            TOOL_NAME=tool,
            TOOL_OUTPUT=existing_output or "",
            TOOL_STDERR=existing_stderr,
            POST_TOOL=str(post_tool) if post_output is not None else "",
            POST_OUTPUT=post_output or "",
            POST_STDERR=post_stderr,
            # An unusable temp folder leaves no private place for the installer's log.
            TMPDIR=str(case) if log_folder_ok else str(case / "missing-folder"),
            PYTHONDONTWRITEBYTECODE="1",
        )
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), selector],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        return result, calls

    def test_invalid_selector_rejects_before_any_probe_or_install(self) -> None:
        for arguments in ([], ["invalid"]):
            with self.subTest(arguments=arguments):
                calls = self.base / ("missing" if not arguments else "invalid")
                result = subprocess.run(
                    [sys.executable, "-B", str(SCRIPT), *arguments],
                    env={**os.environ, "PATH": "/usr/bin:/bin", "CALLS": str(calls)},
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 64)
                self.assertFalse(calls.exists())

    @NEEDS_BASH
    def test_valid_existing_tools_are_present_without_installer_calls(self) -> None:
        for selector, version in self.VERSIONS.items():
            with self.subTest(selector=selector):
                result, calls = self.make_case(
                    f"present-{selector}",
                    selector,
                    existing_output=version,
                    existing_stderr="update available" if selector == "sf" else "",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"{self.PREFIXES[selector]}_PRESENT", result.stdout)
                self.assertNotIn("manager", calls.read_text())

    @NEEDS_BASH
    def test_existing_broken_malformed_or_unsupported_tool_is_never_replaced(self) -> None:
        cases = (
            ("nonzero", "node", "v22.20.1", 9, "NODE_UNVERIFIED"),
            ("malformed", "sf", "error near 2.100.2", 0, "SF_CLI_UNVERIFIED"),
            ("bad-suffix", "python", "Python 3.14.0garbage", 0, "PYTHON_UNVERIFIED"),
            ("old", "python", "Python 3.8.20", 0, "PYTHON_UNSUPPORTED"),
            ("future-major", "python", "Python 4.0.0", 0, "PYTHON_UNSUPPORTED"),
            ("old", "node", "v20.15.1", 0, "NODE_UNSUPPORTED (found 20.15.1; need Node 22.20+)"),
            ("just-below", "node", "v22.19.9", 0, "NODE_UNSUPPORTED (found 22.19.9; need Node 22.20+)"),
        )
        for name, selector, output, rc, expected in cases:
            with self.subTest(name=name, selector=selector):
                result, calls = self.make_case(
                    f"existing-bad-{name}-{selector}",
                    selector,
                    existing_output=output,
                    existing_rc=rc,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stdout)
                self.assertNotIn("manager", calls.read_text())

    @NEEDS_BASH
    def test_an_existing_tool_the_shell_cannot_run_is_reported_not_replaced(self) -> None:
        for selector, version in self.VERSIONS.items():
            with self.subTest(selector=selector):
                result, calls = self.make_case(f"not-executable-{selector}", selector, existing_output=version,
                                               executable=False, post_output=version)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"{self.PREFIXES[selector]}_UNVERIFIED", result.stdout)
                self.assertFalse(calls.exists())  # neither probed successfully nor replaced

    @NEEDS_BASH
    def test_node_at_or_above_the_floor_is_present(self) -> None:
        for output, version in (("v22.20.0", "22.20.0"), ("v24.1.0", "24.1.0"), ("v26.0.0-rc.1", "26.0.0-rc.1")):
            with self.subTest(output=output):
                result, calls = self.make_case(f"floor-{version}", "node", existing_output=output)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, f"NODE_PRESENT ({version})\n")
                self.assertNotIn("manager", calls.read_text())

    @NEEDS_BASH
    def test_missing_tools_install_only_after_successful_post_probe(self) -> None:
        for selector, version in self.VERSIONS.items():
            with self.subTest(selector=selector):
                result, calls = self.make_case(
                    f"installed-{selector}", selector, post_output=version
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"{self.PREFIXES[selector]}_INSTALLED", result.stdout)
                lines = calls.read_text().splitlines()
                expected_install = {
                    "node": "manager install node",
                    "python": "manager install python3",
                    "sf": "manager install @salesforce/cli --global",
                }[selector]
                self.assertEqual(lines[0], expected_install)
                self.assertEqual(lines[-1], f"tool {self.TOOLS[selector]} --version")
                case = self.base / f"installed-{selector}"
                self.assertFalse(any(case.glob("scout-*-install.*")))

    @NEEDS_BASH
    def test_installer_failure_wins_even_when_it_creates_a_valid_tool(self) -> None:
        for selector, version in self.VERSIONS.items():
            with self.subTest(selector=selector):
                result, calls = self.make_case(
                    f"failed-changed-{selector}",
                    selector,
                    install_rc=7,
                    post_output=version,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"{self.PREFIXES[selector]}_INSTALL_FAILED", result.stdout)
                lines = calls.read_text().splitlines()
                self.assertEqual(len(lines), 1)
                self.assertTrue(lines[0].startswith("manager install "))
                case = self.base / f"failed-changed-{selector}"
                self.assertFalse(any(case.glob("scout-*-install.*")))

    @NEEDS_BASH
    def test_exit_zero_without_qualifying_selected_tool_is_unverified(self) -> None:
        cases = (
            ("missing", "node", None, 0),
            ("old", "python", "Python 3.8.20", 0),
            ("malformed", "node", "node version 20.1.2", 0),
            ("below-floor", "node", "v20.1.2", 0),
            ("bad-suffix", "python", "Python 3.14.0garbage", 0),
            ("nonzero", "sf", "@salesforce/cli/2.100.2", 6),
        )
        for name, selector, output, rc in cases:
            with self.subTest(name=name, selector=selector):
                result, _ = self.make_case(
                    f"post-unverified-{name}-{selector}",
                    selector,
                    post_output=output,
                    post_rc=rc,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"{self.PREFIXES[selector]}_UNVERIFIED", result.stdout)

    @NEEDS_BASH
    def test_missing_required_installer_or_npm_is_unavailable(self) -> None:
        for selector in self.VERSIONS:
            with self.subTest(selector=selector):
                result, calls = self.make_case(
                    f"manager-missing-{selector}", selector, manager=False
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"{self.PREFIXES[selector]}_UNAVAILABLE", result.stdout)
                expected_prerequisite = "npm" if selector == "sf" else "brew"
                self.assertIn(f"({expected_prerequisite} prerequisite missing)", result.stdout)
                self.assertFalse(calls.exists())

        result, calls = self.make_case(
            "log-failure-node", "node", log_folder_ok=False
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NODE_UNAVAILABLE (private install log unavailable)", result.stdout)
        self.assertFalse(calls.exists())


@NEEDS_BASH
class WindowsBootstrapTests(unittest.TestCase):
    """The Windows branches, with the platform injected: winget lines where macOS names Homebrew, and no installs."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="scout-bootstrap-windows-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.calls = self.base / "calls.log"
        self.managers = self.base / "managers"
        self.managers.mkdir()
        for manager in ("brew", "npm", "winget"):  # present, so a call to any of them would show
            BootstrapScriptTests.write_executable(self.managers / manager,
                                                  f"printf '{manager} %s\\n' \"$*\" >> \"$CALLS\"\n")

    def tool(self, folder: str, name: str, output: str) -> Path:
        path = self.base / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        BootstrapScriptTests.write_executable(
            path, f"printf '{folder}/{name} %s|%s\\n' \"$*\" \"$PYTHON_MANAGER_AUTOMATIC_INSTALL\" >> \"$CALLS\"\n"
                  f"printf '%s\\n' '{output}'\n")
        return path.parent

    def run_windows(self, selector: str, *folders: Path) -> subprocess.CompletedProcess[str]:
        path = os.pathsep.join([*(str(folder) for folder in folders), str(self.managers), "/bin"])
        return subprocess.run([sys.executable, "-B", "-c", AS_WINDOWS, str(SCRIPT), str(ROOT / "scripts"), selector],
                              env={**os.environ, "PATH": path, "CALLS": str(self.calls), "PYTHONDONTWRITEBYTECODE": "1"},
                              text=True, capture_output=True, check=False)

    def calls_made(self) -> list[str]:
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_a_missing_tool_names_its_install_command_and_nothing_is_installed(self) -> None:
        for selector, expected in (
                ("node", "NODE_MISSING (install it with: winget install --exact --id OpenJS.NodeJS.LTS)\n"),
                ("python", "PYTHON_MISSING (install it with: winget install --exact --id Python.PythonInstallManager, "
                           "then: pymanager install default)\n"),
                ("sf", "SF_CLI_MISSING (install it with: npm.cmd install --global @salesforce/cli)\n")):
            with self.subTest(selector=selector):
                result = self.run_windows(selector)
                self.assertEqual((result.returncode, result.stdout), (1, expected), result.stderr)
                self.assertEqual(self.calls_made(), [])

    def test_python_prefers_the_launcher_and_skips_store_stubs(self) -> None:
        stubs = self.tool("WindowsApps", "python.exe", "Python 3.12.0")
        launcher = self.tool("Launcher", "py.exe", "Python 3.13.1")
        result = self.run_windows("python", stubs, launcher)
        self.assertEqual((result.returncode, result.stdout), (0, "PYTHON_PRESENT (3.13.1)\n"), result.stderr)
        call, = self.calls_made()
        self.assertTrue(call.startswith("Launcher/py.exe -3 -c "), call)
        self.assertTrue(call.endswith("|false"), call)  # the probe never lets Python's manager install a runtime

    def test_python_without_the_launcher_uses_python_outside_windowsapps(self) -> None:
        stubs = self.tool("WindowsApps", "python.exe", "Python 3.12.0")
        real = self.tool("Python313", "python.exe", "Python 3.13.1")
        self.assertEqual(self.run_windows("python", stubs, real).stdout, "PYTHON_PRESENT (3.13.1)\n")
        self.assertEqual([call.split(" ", 1)[0] for call in self.calls_made()], ["Python313/python.exe"])
        self.calls.unlink()
        only_stubs = self.run_windows("python", stubs)
        self.assertEqual(only_stubs.stdout.split(" ", 1)[0], "PYTHON_MISSING")
        self.assertEqual(self.calls_made(), [])

    def test_an_old_python_is_unsupported_and_left_alone(self) -> None:
        old = self.tool("Python38", "python.exe", "Python 3.8.10")
        result = self.run_windows("python", old)
        self.assertEqual((result.returncode, result.stdout),
                         (1, "PYTHON_UNSUPPORTED (found 3.8.10; need Python 3.9+)\n"))


class ProbeOutputTests(unittest.TestCase):
    """What a probe reads, on any platform: one version line, however the platform ends it."""

    def setUp(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("setup_bootstrap_probe", SCRIPT)
        self.bootstrap = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.bootstrap)
        temp = tempfile.TemporaryDirectory(prefix="scout-bootstrap-probe-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)

    def answering(self, name: str, output: bytes) -> str:
        """A tool that prints exactly these bytes, whatever it's asked."""
        return str(stand_ins.tool(self.base, name, "import sys\nsys.stdout.buffer.write(%r)\n" % output))

    def test_a_version_line_ending_in_crlf_is_one_version(self) -> None:
        for selector, output, version in (
                ("python", b"Python 3.12.4\r\n", "3.12.4"), ("node", b"v22.20.0\r\n", "22.20.0"),
                ("sf", b"@salesforce/cli/2.100.2 win32-x64 node-v22.20.0\r\n", "2.100.2")):
            with self.subTest(selector=selector):
                self.assertEqual(self.bootstrap.probe(selector, [self.answering(selector, output)]), ("valid", version))

    def test_the_match_stays_strict_about_everything_else(self) -> None:
        for name, output in (("two", b"Python 3.12.4\r\nPython 3.13.0\r\n"), ("cr", b"Python 3.12.4\r"),
                             ("inner", b"Python 3.12.4\r\r\n"), ("prefix", b"\r\nPython 3.12.4\r\n")):
            with self.subTest(name=name):
                self.assertEqual(self.bootstrap.probe("python", [self.answering(name, output)]), ("invalid", ""))

    def test_this_python_answers_for_itself(self) -> None:
        # On Windows the probe asks the interpreter itself and gets native output, \r\n included.
        import platform
        self.assertEqual(self.bootstrap.probe("python", [sys.executable]), ("valid", platform.python_version()))

    def test_a_probe_that_hangs_is_invalid_and_ended(self) -> None:
        hung = str(stand_ins.tool(self.base, "hung", "import time\ntime.sleep(60)\n"))
        with mock.patch.object(self.bootstrap, "PROBE_SECONDS", 1):
            started = time.monotonic()
            self.assertEqual(self.bootstrap.probe("node", [hung]), ("invalid", ""))
        self.assertLess(time.monotonic() - started, 15)


class FreshInstallPromptTests(unittest.TestCase):
    @staticmethod
    def blocks() -> list[str]:
        prompt = FRESH_PROMPT.read_text()
        return [block.split("```", 1)[0] for block in prompt.split("```bash\n")[1:]
                if "scripts/setup_bootstrap.py" in block.split("```", 1)[0]]

    def test_bootstrap_callers_are_independent_and_nothing_pre_caches_an_mcp_server(self) -> None:
        prompt = FRESH_PROMPT.read_text()
        self.assertEqual(prompt.count('scripts/setup_bootstrap.py" '), 3)
        for selector in ("node", "python", "sf"):
            self.assertIn(f'python3 -B "{PLACEHOLDER}" {selector}', prompt)
        for retired in ("@salesforce/mcp", "MCP_CACHE", "npx", "setup-bootstrap.sh"):  # Scout ships no MCP server to pre-cache
            self.assertNotIn(retired, prompt)
        self.assertEqual(len(self.blocks()), 3)
        for block in self.blocks():
            # One command, with nothing a particular shell would read differently.
            self.assertEqual(len(block.strip().splitlines()), 1, block)
            self.assertIsNone(re.search(r"[$;&|<>`]", block), block)

    @unittest.skipUnless(Path("/bin/sh").exists(), "runs the fences in sh and zsh")
    def test_each_bootstrap_fence_runs_its_own_selector_in_every_shell(self) -> None:
        shells = [shell for shell in ("/bin/sh", "/bin/bash", "/bin/zsh") if Path(shell).exists()]
        with tempfile.TemporaryDirectory(prefix="scout-bootstrap-callers-") as temp:
            base = Path(temp)
            stub = base / "setup_bootstrap.py"
            log = base / "selectors.log"
            stub.write_text("import os, sys\nopen(os.environ['SELECTOR_LOG'], 'a').write(sys.argv[1] + '\\n')\n")
            tools = base / "bin"
            tools.mkdir()
            (tools / "python3").symlink_to(sys.executable)
            for expected, raw in zip(("node", "python", "sf"), self.blocks()):
                shell_text = raw.replace(PLACEHOLDER, str(stub))
                before = log.read_text().splitlines() if log.exists() else []
                for shell in shells:
                    result = subprocess.run(
                        [shell, "-c", shell_text],
                        env={**os.environ, "SELECTOR_LOG": str(log), "PATH": f"{tools}:/usr/bin:/bin"},
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(log.read_text().splitlines(), before + [expected] * len(shells))

if __name__ == "__main__":
    unittest.main()
