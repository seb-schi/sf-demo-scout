"""hooks/run-hook.cmd, which both Claude Code hooks start through: one file that cmd.exe and sh each read their way.

The sh half runs here under every shell present. The cmd.exe half, and the hook commands under PowerShell, run on
Windows only; on other machines the batch half is checked for what cmd.exe reads badly with LF endings.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "hooks" / "run-hook.cmd"
HOOKS = json.loads((ROOT / "hooks" / "claude-hooks.json").read_text(encoding="utf-8"))["hooks"]
EVENTS = {"SessionStart": "session_startup.py", "UserPromptSubmit": "team_updates.py"}
SHELLS = [shell for shell in ("/bin/sh", "/bin/bash", "/bin/dash", "/bin/zsh", "/bin/ksh") if Path(shell).exists()]
NEEDS_SH = unittest.skipUnless(SHELLS, "runs the launcher's sh half")
RECORDER = """import json, os, sys
print(json.dumps({"hook": os.path.basename(sys.argv[0]), "args": sys.argv[1:], "stdin": sys.stdin.read(),
                  "no_bytecode": sys.flags.dont_write_bytecode, "utf8": os.environ.get("PYTHONUTF8", ""),
                  "manager": os.environ.get("PYTHON_MANAGER_AUTOMATIC_INSTALL", "")}))
"""


def command(event: str) -> str:
    return HOOKS[event][0]["hooks"][0]["command"]


class LauncherFixture(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="scout launcher ")  # a space, as in many Windows profile paths
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.root = self.base / "plugin root"
        (self.root / "hooks").mkdir(parents=True)
        shutil.copyfile(LAUNCHER, self.root / "hooks" / "run-hook.cmd")
        for name in EVENTS.values():
            (self.root / "hooks" / name).write_text(RECORDER)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        if SHELLS:  # the sh half's python3; Windows needs extra rights for a symlink, and runs the cmd.exe half
            os.symlink(sys.executable, self.bin / "python3")
        self.empty = self.base / "empty"
        self.empty.mkdir()

    def run_hook(self, shell: str, text: str, *, path: Path | str | None = None, stdin: str = "{}",
                 substitute: bool = True, **extra: str) -> subprocess.CompletedProcess[str]:
        env = {"PATH": str(path or self.bin), "CLAUDE_PLUGIN_ROOT": str(self.root), "HOME": str(self.base), **extra}
        if substitute:  # Claude Code puts the root into the command; the shell may also expand it from the env
            text = text.replace("${CLAUDE_PLUGIN_ROOT}", str(self.root))
        return subprocess.run([shell, "-c", text], input=stdin, env=env, text=True, capture_output=True, timeout=30)


@NEEDS_SH
class ShHalfTests(LauncherFixture):
    def test_each_hook_command_runs_its_hook_in_every_shell(self) -> None:
        for event, name in EVENTS.items():
            for shell in SHELLS:
                for substitute in (True, False):
                    with self.subTest(event=event, shell=shell, substitute=substitute):
                        result = self.run_hook(shell, command(event), stdin='{"prompt": "x"}', substitute=substitute)
                        self.assertEqual((result.returncode, result.stderr), (0, ""))
                        record = json.loads(result.stdout)
                        self.assertEqual((record["hook"], record["args"], record["stdin"], record["no_bytecode"]),
                                         (name, [], '{"prompt": "x"}', 1))

    def test_without_python_it_exits_quietly(self) -> None:
        for event in EVENTS:
            for shell in SHELLS:
                with self.subTest(event=event, shell=shell):
                    result = self.run_hook(shell, command(event), path=self.empty)
                    self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_it_runs_only_its_own_hooks(self) -> None:
        (self.root / "hooks" / "evil.py").write_text(RECORDER)
        (self.root / "hooks" / "team_updates.py").unlink()
        launcher = self.root / "hooks" / "run-hook.cmd"
        for name in ("evil.py", "../hooks/session_startup.py", "", "team_updates.py"):
            with self.subTest(name=name):
                result = subprocess.run([SHELLS[0], str(launcher), name], env={"PATH": str(self.bin)}, text=True,
                                        capture_output=True, timeout=30)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_a_failing_hook_never_fails_the_launcher(self) -> None:
        # Exit 2 would block the prompt (UserPromptSubmit); a hook only ever speeds Scout up.
        (self.root / "hooks" / "team_updates.py").write_text("print('partial')\nraise SystemExit(2)\n")
        result = self.run_hook(SHELLS[0], command("UserPromptSubmit"))
        self.assertEqual((result.returncode, result.stdout), (0, "partial\n"))

    def test_run_directly_it_finds_its_own_folder(self) -> None:
        for shell in SHELLS:
            with self.subTest(shell=shell):
                result = subprocess.run([shell, str(self.root / "hooks" / "run-hook.cmd"), "session_startup.py"],
                                        env={"PATH": str(self.bin)}, input="", text=True, capture_output=True,
                                        timeout=30)
                self.assertEqual(json.loads(result.stdout)["hook"], "session_startup.py")


@NEEDS_SH
class GitBashTests(LauncherFixture):
    """The sh half under Git Bash: OS=Windows_NT, with stand-in interpreters named like Windows' own."""

    def interpreter(self, folder: str, name: str, *, probe_status: int = 0) -> Path:
        path = self.base / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"""#!/bin/sh
printf '%s\\n' "{folder}/{name} $*" >> "$LOG"
[ "$1" != -3 ] || shift
[ "$1" != -c ] || exit {probe_status}
exec "{sys.executable}" "$@"
""")
        path.chmod(0o700)
        return path.parent

    def run_windows(self, *folders: Path) -> tuple[subprocess.CompletedProcess[str], list[str]]:
        log = self.base / "calls.log"
        if log.exists():
            log.unlink()
        path = ":".join(str(folder) for folder in folders) or str(self.empty)
        result = self.run_hook(SHELLS[0], command("SessionStart"), path=path, stdin="payload", OS="Windows_NT",
                               LOG=str(log))
        return result, log.read_text().splitlines() if log.exists() else []

    def test_python_s_launcher_comes_first_with_its_3_flag(self) -> None:
        stubs = self.interpreter("WindowsApps", "python.exe")
        launcher = self.interpreter("Launcher", "py.exe")
        real = self.interpreter("Python313", "python.exe")
        result, calls = self.run_windows(stubs, launcher, real)
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(result.stdout)
        self.assertEqual((record["hook"], record["stdin"], record["utf8"], record["manager"]),
                         ("session_startup.py", "payload", "1", "false"))  # the probe left the payload alone
        self.assertEqual([call.split(" ")[:2] for call in calls], [["Launcher/py.exe", "-3"]] * 2)
        self.assertIn("-B", calls[1].split(" "))

    def test_store_stubs_are_skipped_and_an_old_python_is_passed_over(self) -> None:
        stubs = self.interpreter("WindowsApps", "python.exe")
        old = self.interpreter("Launcher", "py.exe", probe_status=1)
        real = self.interpreter("Python313", "python3.exe")
        result, calls = self.run_windows(stubs, old, real)
        self.assertEqual(json.loads(result.stdout)["hook"], "session_startup.py")
        self.assertEqual([call.split(" ")[0] for call in calls],
                         ["Launcher/py.exe", "Python313/python3.exe", "Python313/python3.exe"])

    def test_only_store_stubs_means_no_python_and_silence(self) -> None:
        stubs = self.interpreter("WindowsApps", "python.exe")
        self.interpreter("WindowsApps", "python3.exe")
        result, calls = self.run_windows(stubs)
        self.assertEqual((result.returncode, result.stdout, result.stderr, calls), (0, "", "", []))


class CmdHalfTests(LauncherFixture):
    def test_the_batch_half_avoids_what_cmd_reads_badly_with_lf_endings(self) -> None:
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertNotIn("\r", text)
        lines = text.split("\n")
        self.assertEqual(lines[0], ": << 'CMDBLOCK'")  # a label to cmd.exe, a no-op here-document to sh
        end = lines.index("CMDBLOCK")
        batch = lines[1:end]
        self.assertEqual(batch[-1], "exit /b 0")  # cmd.exe never reaches the sh half
        for line in batch:
            with self.subTest(line=line):
                self.assertFalse(line.startswith(":"), "a label: cmd.exe finds labels unreliably in LF files")
                if not re.match(r"(?i)rem\b", line):
                    self.assertIsNone(re.search(r"(?i)\b(?:goto|call)\b", line), "a jump: needs a label")
                self.assertFalse(line.rstrip().endswith("^"), "a continuation joins lines")
                self.assertLess(len(line), 512)

    @unittest.skipUnless(os.name == "nt", "cmd.exe")
    def test_cmd_runs_the_hook_with_the_python_it_finds(self) -> None:  # pragma: no cover - Windows only
        path = os.pathsep.join([os.path.dirname(sys.executable), os.environ.get("SystemRoot", "C:\\Windows")])
        result = subprocess.run(["cmd.exe", "/d", "/c", str(self.root / "hooks" / "run-hook.cmd"), "session_startup.py"],
                                input="payload", env={**os.environ, "PATH": path}, text=True, capture_output=True,
                                timeout=60)
        self.assertEqual(json.loads(result.stdout)["stdin"], "payload")
        quiet = subprocess.run(["cmd.exe", "/d", "/c", str(self.root / "hooks" / "run-hook.cmd"), "session_startup.py"],
                               env={**os.environ, "PATH": str(self.empty)}, text=True, capture_output=True, timeout=60)
        self.assertEqual((quiet.returncode, quiet.stdout), (0, ""))

    @unittest.skipUnless(os.name == "nt", "PowerShell runs Claude Code's hooks only on Windows without Git Bash")
    def test_powershell_runs_each_hook_command_and_the_banner_comes_out(self) -> None:  # pragma: no cover - Windows
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if shell is None:
            self.skipTest("no PowerShell on this machine")
        root = ROOT.as_posix()  # Claude Code puts the plugin root into the command with forward slashes
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "workspace"
            workspace.mkdir()
            env = {**os.environ, "CLAUDE_PLUGIN_ROOT": root, "SCOUT_HOST": "codex", "PYTHONDONTWRITEBYTECODE": "1",
                   "SCOUT_WORKSPACE": str(workspace), "SCOUT_CACHE_DIR": str(Path(temp) / "cache"),
                   "SCOUT_RUNTIME_DIR": str(Path(temp) / "runtime"), "SCOUT_CONFIG_FILE": str(Path(temp) / "config.json"),
                   "SCOUT_TEAMS_FILE": str(Path(temp) / "no-teams.json"),
                   # Python, and Windows' own tools, but no Salesforce CLI: the probes report it unavailable.
                   "PATH": os.pathsep.join([os.path.dirname(sys.executable),
                                            os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32")])}
            for event in EVENTS:
                with self.subTest(event=event):
                    text = command(event).replace("${CLAUDE_PLUGIN_ROOT}", root)
                    result = subprocess.run([shell, "-NoProfile", "-Command", text], cwd=str(workspace), input="{}",
                                            env=env, text=True, encoding="utf-8", capture_output=True, timeout=120)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    if event == "SessionStart":
                        self.assertTrue(result.stdout.startswith("Scout is installed."), result.stdout + result.stderr)
                        self.assertIn("**Ready.**", result.stdout)
                    else:
                        self.assertEqual(result.stdout, "", result.stderr)  # no team on this machine

@NEEDS_SH
class RealHookTests(unittest.TestCase):
    def test_the_launcher_gives_the_same_output_as_the_hook_itself(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(ROOT), "SCOUT_HOST": "codex", "PYTHONDONTWRITEBYTECODE": "1",
                   "SCOUT_WORKSPACE": str(Path(temp) / "workspace")}
            direct = subprocess.run([sys.executable, "-B", str(ROOT / "hooks" / "session_startup.py")], cwd=temp,
                                    env=env, text=True, capture_output=True, timeout=60)
            bin_dir = Path(temp) / "bin"
            bin_dir.mkdir()
            os.symlink(sys.executable, bin_dir / "python3")
            launched = subprocess.run([SHELLS[0], "-c", command("SessionStart").replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT))],
                                      cwd=temp, env={**env, "PATH": f"{bin_dir}:/usr/bin:/bin"}, text=True,
                                      capture_output=True, timeout=60)
        self.assertTrue(direct.stdout.startswith("Scout is installed."), direct.stdout + direct.stderr)
        self.assertEqual((launched.returncode, launched.stdout), (0, direct.stdout))


if __name__ == "__main__":
    unittest.main()
