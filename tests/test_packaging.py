"""Local packaging and source-contract checks for Batch 6."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RETIRED_SHELL_SCRIPTS = ("hooks/session-startup.sh", "hooks/team-updates.sh", "scripts/client-cache.sh",
                         "scripts/setup-bootstrap.sh", "scripts/setup-cli-refresh.sh")
PYTHON_ENTRY_POINTS = ("hooks/session_startup.py", "hooks/team_updates.py", "scripts/setup_bootstrap.py",
                       "scripts/setup_cli_refresh.py", "scripts/scout_portable.py")
REFRESH_PLACEHOLDER = "/absolute/path/of/active/sf-demo-scout/scripts/setup_cli_refresh.py"
SCRIPT_PATH = re.compile(r"(?:scripts|hooks)/[A-Za-z0-9_.-]+\.(?:py|sh|cmd)\b")
# What names an interpreter in front of a script: Python (by name, its launcher, or a resolved variable) or a shell.
INTERPRETER = re.compile(r'(?:^|[\s;|&(`])(?:python3?|py(?:\s+-3)?|\[PYTHON\]|"?\$\{?PYTHON_EXE\}?"?'
                         r'|(?:/bin/)?(?:ba|z|da)?sh)(?:\s+-[A-Za-z0-9]+)*\s+["\']?[^\s"\']*$')
DEFINITION = re.compile(r'(?:^|\s)(?:[A-Z][A-Z0-9_]*=["\']?|\{\{[A-Z_]+\}\}\s*=\s*)[^\s"\']*$')
COMMAND_START = r'(?:^|;|&&|\|\||\||\bthen|\belse|\bdo)\s*'


def tracked_files() -> list[str]:
    listing = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True).stdout
    return [name for name in listing.decode("utf-8").split("\0") if name and (ROOT / name).is_file()]


def script_calls(text: str):
    """(line, text before the script path) for each script named in a fenced block or a multi-word code span."""
    for block in re.findall(r"^[ \t]*```[A-Za-z]*\n(.*?)^[ \t]*```", text, re.S | re.M):
        for line in block.splitlines():
            for match in SCRIPT_PATH.finditer(line):
                yield line, line[:match.start()]
    for span in re.findall(r"`([^`\n]+)`", text):
        if " " in span.strip():
            for match in SCRIPT_PATH.finditer(span):
                yield span, span[:match.start()]


def interpreter_findings(name: str, text: str) -> list[str]:
    """Script calls that rely on an executable bit or a shebang instead of naming their interpreter."""
    found = []
    for line, before in script_calls(text):
        if not (INTERPRETER.search(before) or DEFINITION.search(before)):
            found.append(f"{name}: {line.strip()}")
    for variable in set(re.findall(r'(?m)(?:^|\s)([A-Z][A-Z0-9_]*)=["\']?[^\s"\']*(?:scripts|hooks)/', text)):
        use = re.compile(COMMAND_START + r'"?\$\{?' + variable + r'\b')
        found += [f"{name}: {line.strip()}" for line in text.splitlines() if use.search(line)]
    return found


class PackagingTests(unittest.TestCase):
    def test_all_bundled_mcp_identifiers_are_portable(self) -> None:
        # Scan every manifest/config, including future companion MCP files.
        declarations = []
        for path in ROOT.rglob("*.json"):
            if any(part in {".git", "orgs", ".sfdx"} for part in path.relative_to(ROOT).parts):
                continue
            payload = json.loads(path.read_text())
            if isinstance(payload, dict) and isinstance(payload.get("mcpServers"), dict):
                declarations.extend((path, name) for name in payload["mcpServers"])
        for path, name in declarations:
            with self.subTest(path=path, name=name):
                self.assertRegex(name, r"^[a-zA-Z0-9_-]+$")
        manifest = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        self.assertNotIn("mcpServers", manifest)  # Salesforce ended support for @salesforce/mcp

    def test_shipped_text_no_longer_names_the_retired_dx_server(self) -> None:
        allowed = {  # the one place each name may still appear, and why
            "Salesforce_DX": set(),  # 2.4 leaves old allow rules alone, so nothing names them any more
            "@salesforce/mcp": set(),
            "run_code_analyzer": {"prompts/building/official-skill-overrides.md"},  # official skills still name it
            "salesforce-dx": set(),
            "NPX_ABSENT": set(),
            "MCP_CACHE": set(),
        }
        tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files"], text=True, capture_output=True, check=True)
        shipped = [name for name in tracked.stdout.splitlines()
                   if not name.startswith("tests/") and name != "CHANGELOG.md" and (ROOT / name).is_file()]
        self.assertIn("AGENTS.md", shipped)
        for name in shipped:
            text = (ROOT / name).read_text(errors="replace")
            for needle, places in allowed.items():
                with self.subTest(path=name, needle=needle):
                    if name not in places:
                        self.assertNotIn(needle, text)

    def test_runtime_prompts_do_not_probe_another_hosts_cli(self) -> None:
        for folder in ("commands", "prompts", "skills/scout", "skills/scout-setup"):
            for path in (ROOT / folder).rglob("*.md"):
                with self.subTest(path=path):
                    self.assertNotIn("claude mcp list", path.read_text())
                    self.assertNotIn("~/.claude/plugins/installed_plugins.json", path.read_text())
        for path in ("skills/scout/SKILL.md", "skills/scout-setup/SKILL.md", "commands/scout-building.md",
                     "commands/scout-sparring.md"):
            self.assertIn("prompts/host-runtime.md", (ROOT / path).read_text())

    def test_done_message_has_no_shell_refresh_and_reports_model_routing_read_only(self) -> None:
        content = (ROOT / "prompts/setup/done.md").read_text()
        for retired in ("ZSHRC", ".zshrc", "Open a new shell", "Scout preserved your provider and user model settings"):
            self.assertNotIn(retired, content)  # 2.4 edits no shell files and no model settings
        self.assertIn("read-only model report", content)
        self.assertIn("never needs a restart note", content)

    def test_workspace_template_allows_no_connector_but_the_docs_mcp(self) -> None:
        settings = json.loads((ROOT / "assets/workspace-settings.template.json").read_text())
        connectors = [rule for rule in settings["permissions"]["allow"] if rule.startswith("mcp__")]
        self.assertEqual(connectors, ["mcp__salesforce-docs__*"])  # the SE's own connectors keep their own rules

    def test_the_workspace_denies_user_folder_wipes_in_every_path_form(self) -> None:
        settings = json.loads((ROOT / "assets/workspace-settings.template.json").read_text(encoding="utf-8"))
        deny = settings["permissions"]["deny"]
        for form in ("/Users/*", "/c/Users/*", "C:\\Users\\*"):  # macOS, Git Bash, and Windows' own form
            self.assertIn(f"Bash(rm -rf {form})", deny)
        # A scoped PowerShell rule would switch Claude's PowerShell tool on, where Bash-only safety hooks can't see it.
        rules = settings["permissions"]["allow"] + deny
        self.assertEqual([rule for rule in rules if rule.lower().startswith("powershell")], [])

    def test_the_handover_opens_its_folder_on_every_os(self) -> None:
        brief = (ROOT / "prompts/building/handover-brief.md").read_text(encoding="utf-8")
        files = brief.split("**Your Files**", 1)[1].split("\n- ", 1)[0]
        for command in ("`open`", "`explorer.exe`", "`xdg-open`"):
            self.assertIn(command, files)
        self.assertIn('[OPEN] "[ORG_FOLDER]"', files)  # quoted: Windows profile paths often hold spaces

    def test_host_manifests_share_one_version_and_only_claude_has_hooks(self) -> None:
        manifests = {host: json.loads((ROOT / f".{host}-plugin/plugin.json").read_text())
                     for host in ("claude", "codex", "cursor")}
        versions = {host: manifest["version"] for host, manifest in manifests.items()}
        self.assertEqual(len(set(versions.values())), 1, versions)
        self.assertRegex(versions["claude"], r"^\d+\.\d+\.\d+$")  # plain SemVer from 2.4.0
        self.assertEqual({manifest["name"] for manifest in manifests.values()}, {"sf-demo-scout"})
        # Claude's hooks sit off the default path, so no other host's discovery finds them; Codex declares none.
        self.assertFalse((ROOT / "hooks/hooks.json").exists())
        self.assertEqual(manifests["claude"]["hooks"], "./hooks/claude-hooks.json")
        self.assertEqual((manifests["codex"]["hooks"], manifests["codex"]["commands"]), ({}, []))
        self.assertNotIn("hooks", manifests["cursor"])
        for host in ("claude", "cursor"):
            market = json.loads((ROOT / f".{host}-plugin/marketplace.json").read_text())
            entry, = market["plugins"]
            self.assertEqual((entry["name"], entry["source"]), ("sf-demo-scout", "."))
            self.assertNotIn("version", entry)  # the plugin manifests carry it

    def test_manifest_json_and_required_setup_scripts(self) -> None:
        for relative in (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"):
            with self.subTest(relative=relative):
                payload = json.loads((ROOT / relative).read_text())
                self.assertIsInstance(payload, dict)
        for relative in (*PYTHON_ENTRY_POINTS, "hooks/run-hook.cmd", "scripts/scout_uninstall.py"):
            with self.subTest(relative=relative):
                self.assertTrue((ROOT / relative).is_file())
        for relative in ("scripts/setup-zshrc.sh", "scripts/scout-uninstall.sh", "prompts/setup/zshrc-block.md",
                         *RETIRED_SHELL_SCRIPTS):
            with self.subTest(retired=relative):
                self.assertFalse((ROOT / relative).exists())

    def test_shipped_scripts_have_real_syntax(self) -> None:
        for relative in PYTHON_ENTRY_POINTS:
            with self.subTest(python=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                compile(source, relative, "exec")
        for shell in ("/bin/sh", "/bin/bash", "/bin/dash", "/bin/zsh", "/bin/ksh"):
            if Path(shell).exists():
                with self.subTest(shell=shell):
                    result = subprocess.run([shell, "-n", str(ROOT / "hooks/run-hook.cmd")], text=True,
                                            capture_output=True, check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_callers_require_explicit_active_plugin_absolute_paths(self) -> None:
        refresh = (ROOT / "prompts/setup/refresh.md").read_text()
        self.assertIn("scripts/setup_cli_refresh.py", refresh)
        self.assertNotIn("setup-cli-refresh.sh", refresh)
        self.assertEqual(refresh.count(f'python3 -B "{REFRESH_PLACEHOLDER}" sf'), 1)
        self.assertNotIn('setup_cli_refresh.py" claude', refresh)  # Claude Code updates itself
        self.assertIn("absolute", refresh.lower())
        self.assertIn("unavailable", refresh.lower())
        self.assertNotIn('"${CLAUDE_PLUGIN_ROOT}/scripts/setup-', refresh)
        self.assertNotIn('"${CLAUDE_PLUGIN_ROOT}/scripts/setup_', refresh)

    def test_cli_caller_blocks_execute_independently(self) -> None:
        refresh = (ROOT / "prompts/setup/refresh.md").read_text()
        blocks = re.findall(r"```bash\n(.*?)\n```", refresh, re.S)
        callers = [
            block for block in blocks if "scripts/setup_cli_refresh.py" in block
        ]
        self.assertEqual(len(callers), 1)
        self.assertEqual(len(callers[0].splitlines()), 1)  # one shell-neutral command
        with tempfile.TemporaryDirectory(prefix="scout-caller-test-") as raw:
            base = Path(raw)
            log = base / "selectors.log"
            stub = base / "setup_cli_refresh.py"
            stub.write_text("import os, sys\nopen(os.environ['SCOUT_CALLER_LOG'], 'a').write(sys.argv[1] + '\\n')\n")
            tools = base / "bin"
            tools.mkdir()
            env = {
                **os.environ,
                "PATH": f"{tools}:/usr/bin:/bin",
                "SCOUT_CALLER_LOG": str(log),
            }
            shells = [shell for shell in ("/bin/sh", "/bin/zsh") if Path(shell).exists()]
            if shells:  # runs the fence where a POSIX shell is present; the static checks above run everywhere
                os.symlink(sys.executable, tools / "python3")
            for block in callers:
                for shell in shells:
                    result = subprocess.run(
                        [shell, "-c", block.replace(REFRESH_PLACEHOLDER, str(stub))],
                        env=env,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
            if shells:
                self.assertEqual(log.read_text().splitlines(), ["sf"] * len(shells))

    def test_shipped_files_have_no_carriage_returns(self) -> None:
        # Git checks every file out with LF (.gitattributes), the hook launcher included: cmd.exe and sh both read
        # its halves with LF endings, and a CR would break the sh half and Scout's own markers.
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
        self.assertIn("* text=auto eol=lf", attributes)
        self.assertFalse([line for line in attributes if not line.startswith("#") and "crlf" in line.lower()])
        names = [name for name in tracked_files() if not name.startswith("tests/")]
        self.assertIn("hooks/run-hook.cmd", names)
        self.assertEqual([name for name in names if b"\r" in (ROOT / name).read_bytes()], [])

    def test_the_package_holds_no_symlinks(self) -> None:
        listing = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-s", "-z"], capture_output=True,
                                 check=True).stdout.decode("utf-8")
        entries = [entry.split("\t", 1) for entry in listing.split("\0") if entry]
        self.assertTrue(entries)
        self.assertEqual([name for meta, name in entries if meta.split()[0] == "120000"], [])
        self.assertEqual([name for name in tracked_files() if (ROOT / name).is_symlink()], [])

    def test_json_files_have_no_byte_order_mark(self) -> None:
        names = [name for name in tracked_files() if name.endswith(".json")]
        self.assertIn("hooks/claude-hooks.json", names)
        for name in names:
            with self.subTest(name=name):
                data = (ROOT / name).read_bytes()
                self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
                json.loads(data.decode("utf-8"))  # strict UTF-8, which a BOM would fail

    def test_every_hook_and_prompt_call_names_its_interpreter(self) -> None:
        # Packagers drop executable bits, and Windows ignores shebangs: every call names what runs the script.
        found = []
        for folder in ("commands", "prompts", "skills"):
            for path in sorted((ROOT / folder).rglob("*.md")):
                found += interpreter_findings(path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8"))
        self.assertEqual(found, [])
        hooks = json.loads((ROOT / "hooks/claude-hooks.json").read_text(encoding="utf-8"))["hooks"]
        commands = [hook["command"] for groups in hooks.values() for group in groups for hook in group["hooks"]]
        self.assertEqual(len(commands), 2)
        for command in commands:
            with self.subTest(command=command):
                # The shell runs the launcher itself, with `.`; it never executes the file.
                self.assertRegex(command, r'^set -- ([a-z_]+\.py); \. "\$\{CLAUDE_PLUGIN_ROOT\}/hooks/run-hook\.cmd" \1$')
        launcher = (ROOT / "hooks/run-hook.cmd").read_text(encoding="utf-8")
        self.assertIn('"%SCOUT_PY%" %SCOUT_PY_ARG% -B "%~dp0%SCOUT_HOOK%"', launcher)
        self.assertIn('python3 -B "$scout_dir/$scout_hook"', launcher)
        self.assertIn('"$scout_py" ${scout_arg:+"$scout_arg"} -B "$scout_dir/$scout_hook"', launcher)

    def test_the_interpreter_check_flags_calls_that_name_none(self) -> None:
        bare = "Run `[PLUGIN_ROOT_ABS]/scripts/scout_uninstall.py --dry-run` first.\n"
        variable = '```bash\nHELPER="[PLUGIN_ROOT]/scripts/setup-workspace.py"\n"$HELPER" verify\n```\n'
        named = ('```bash\nHELPER="[PLUGIN_ROOT]/scripts/setup-workspace.py"\n"$PYTHON_EXE" -B "$HELPER" verify\n'
                 'python3 -B "/absolute/path/scripts/x.py" go\n[PYTHON] "[SCOUT_ROOT]/scripts/y.py"\n```\n'
                 "See `scripts/slugify.py` and `py -3 scripts/z.py now`.\n")
        self.assertEqual(len(interpreter_findings("bare", bare)), 1)
        self.assertEqual(len(interpreter_findings("variable", variable)), 1)
        self.assertEqual(interpreter_findings("named", named), [])

    def test_done_summary_keeps_three_truthful_failure_assertions(self) -> None:
        done = (ROOT / "prompts/setup/done.md").read_text()
        failed_lines = [line for line in done.splitlines() if "SF_CLI_UPDATE_FAILED" in line]
        self.assertEqual(len(failed_lines), 1)
        self.assertNotIn("kept the installed one", failed_lines[0])
        self.assertIn("future refresh", failed_lines[0])

    def test_done_contract_keeps_the_outcome_distinctions(self) -> None:
        done = (ROOT / "prompts/setup/done.md").read_text()
        for rule in ("never the `->` target", "a failed install may be partial", "holds it back on purpose",
                     "Not an update", "doesn't establish that the desktop or IDE client updated",
                     "describes transport only"):
            self.assertIn(rule, done)

    def test_mcp_readiness_keeps_its_working_rules(self) -> None:
        readiness = (ROOT / "prompts/mcp-readiness.md").read_text()
        for rule in ("Use the exposed tools", "A worker discovers its own tools", "never dump raw diagnostics",
                     "don't resolve a policy denial", "leave the entry alone", "Unknown isn't absent",
                     "name the unavailable capability and use the caller's fallback",
                     "never write merely to test readiness"):
            self.assertIn(rule, readiness)


if __name__ == "__main__":
    unittest.main()
