"""Hermetic regressions for first-install tool bootstrapping."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "setup-bootstrap.sh"
FRESH_PROMPT = ROOT / "prompts" / "setup" / "fresh-install.md"


class BootstrapScriptTests(unittest.TestCase):
    VERSIONS = {
        "node": "v20.15.1",
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
        mktemp_ok: bool = True,
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        case = self.base / name
        bin_dir = case / "bin"
        bin_dir.mkdir(parents=True)
        if mktemp_ok:
            (bin_dir / "mktemp").symlink_to("/usr/bin/mktemp")
        else:
            self.write_executable(bin_dir / "mktemp", "exit 9\n")
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
                "if [ -n \"$POST_TOOL\" ]; then ln -s \"$POST_TOOL\" \"$BIN_DIR/$TOOL_NAME\"; fi\n"
                f"exit {install_rc}\n",
            )
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.update(
            PATH=f"{bin_dir}:/bin",
            CALLS=str(calls),
            BIN_DIR=str(bin_dir),
            TOOL_NAME=tool,
            TOOL_OUTPUT=existing_output or "",
            TOOL_STDERR=existing_stderr,
            POST_TOOL=str(post_tool) if post_output is not None else "",
            POST_OUTPUT=post_output or "",
            POST_STDERR=post_stderr,
            TMPDIR=str(case),
            PYTHONDONTWRITEBYTECODE="1",
        )
        result = subprocess.run(
            ["/bin/bash", str(SCRIPT), selector],
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
                    ["/bin/bash", str(SCRIPT), *arguments],
                    env={**os.environ, "PATH": "/usr/bin:/bin", "CALLS": str(calls)},
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 64)
                self.assertFalse(calls.exists())

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

    def test_existing_broken_malformed_or_unsupported_tool_is_never_replaced(self) -> None:
        cases = (
            ("nonzero", "node", "v20.1.2", 9, "NODE_UNVERIFIED"),
            ("malformed", "sf", "error near 2.100.2", 0, "SF_CLI_UNVERIFIED"),
            ("bad-suffix", "python", "Python 3.14.0garbage", 0, "PYTHON_UNVERIFIED"),
            ("old", "python", "Python 3.8.20", 0, "PYTHON_UNSUPPORTED"),
            ("future-major", "python", "Python 4.0.0", 0, "PYTHON_UNSUPPORTED"),
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

    def test_exit_zero_without_qualifying_selected_tool_is_unverified(self) -> None:
        cases = (
            ("missing", "node", None, 0),
            ("old", "python", "Python 3.8.20", 0),
            ("malformed", "node", "node version 20.1.2", 0),
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
            "mktemp-failure-node", "node", mktemp_ok=False
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NODE_UNAVAILABLE (private install log unavailable)", result.stdout)
        self.assertFalse(calls.exists())


class FreshInstallPromptTests(unittest.TestCase):
    def test_bootstrap_callers_are_independent_and_npx_outcomes_are_distinct(self) -> None:
        prompt = FRESH_PROMPT.read_text()
        self.assertEqual(prompt.count('SCOUT_BOOTSTRAP_SCRIPT="/absolute/path/'), 3)
        for selector in ("node", "python", "sf"):
            self.assertIn(f'/bin/bash "$SCOUT_BOOTSTRAP_SCRIPT" {selector}', prompt)
        self.assertIn("MCP_CACHE_UNAVAILABLE", prompt)
        self.assertIn("MCP_CACHE_FAILED", prompt)
        blocks = [
            block
            for block in prompt.split("```bash\n")[1:]
            if "scripts/setup-bootstrap.sh" in block.split("```", 1)[0]
        ]
        self.assertEqual(len(blocks), 3)
        with tempfile.TemporaryDirectory(prefix="scout-bootstrap-callers-") as temp:
            base = Path(temp)
            stub = base / "setup-bootstrap.sh"
            log = base / "selectors.log"
            BootstrapScriptTests.write_executable(
                stub, "printf '%s\\n' \"$1\" >> \"$SELECTOR_LOG\"\n"
            )
            placeholder = (
                "/absolute/path/of/active/sf-demo-scout/"
                "scripts/setup-bootstrap.sh"
            )
            for expected, raw in zip(("node", "python", "sf"), blocks, strict=True):
                shell = raw.split("```", 1)[0].replace(placeholder, str(stub))
                before = log.read_text().splitlines() if log.exists() else []
                result = subprocess.run(
                    ["/bin/bash", "-c", shell],
                    env={**os.environ, "SELECTOR_LOG": str(log)},
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(log.read_text().splitlines(), before + [expected])

    def test_npx_missing_and_failed_attempt_are_distinct_runtime_results(self) -> None:
        prompt = FRESH_PROMPT.read_text()
        section = prompt.split("## c: Pre-cache Salesforce MCP server", 1)[1]
        shell = section.split("```bash", 1)[1].split("```", 1)[0].strip()
        with tempfile.TemporaryDirectory(prefix="scout-npx-test-") as temp:
            base = Path(temp)
            bin_dir = base / "bin"
            bin_dir.mkdir()
            missing = subprocess.run(
                ["/bin/bash", "-c", shell],
                env={**os.environ, "PATH": f"{bin_dir}:/bin"},
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(missing.returncode, 0, missing.stderr)
            self.assertIn("MCP_CACHE_UNAVAILABLE", missing.stdout)

            calls = base / "calls.log"
            npx = bin_dir / "npx"
            BootstrapScriptTests.write_executable(
                npx,
                "printf '%s\\n' \"$*\" >> \"$CALLS\"\nexit 7\n",
            )
            failed = subprocess.run(
                ["/bin/bash", "-c", shell],
                env={**os.environ, "PATH": f"{bin_dir}:/bin", "CALLS": str(calls)},
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(failed.returncode, 0, failed.stderr)
            self.assertIn("MCP_CACHE_FAILED", failed.stdout)
            self.assertEqual(calls.read_text().strip(), "-y @salesforce/mcp --help")


if __name__ == "__main__":
    unittest.main()
