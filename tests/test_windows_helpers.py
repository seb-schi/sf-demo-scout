"""The Windows branches of the report repair, the client-version helper and the CLI-owner check, with the platform
injected so they run on any machine. Windows lacks O_NOFOLLOW, O_NONBLOCK, fchmod and user IDs, and its link
reparse points (junctions as well as symlinks) are what the link checks look for there, never a cloud file's."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True
import scout_portable  # noqa: E402
import scout_report_repair as repair  # noqa: E402

# npm's cmd-shim, as `npm install --global` writes it next to node.exe
NPM_SHIM = ('@ECHO off\r\nGOTO start\r\n:find_dp0\r\nSET dp0=%~dp0\r\nEXIT /b\r\n:start\r\nSETLOCAL\r\nCALL :find_dp0\r\n'
            'IF EXIST "%dp0%\\node.exe" (\r\n  SET "_prog=%dp0%\\node.exe"\r\n) ELSE (\r\n  SET "_prog=node"\r\n)\r\n'
            'endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & "%_prog%"  '
            '"%dp0%\\node_modules\\@salesforce\\cli\\bin\\run.js" %*\r\n')
INSTALLER_LAUNCHER = ('@echo off\r\nsetlocal enableextensions\r\n'
                      'if exist "%LOCALAPPDATA%\\sf\\client\\bin\\sf.cmd" (\r\n'
                      '  "%LOCALAPPDATA%\\sf\\client\\bin\\sf.cmd" %*\r\n) else (\r\n'
                      '  "%~dp0\\..\\client\\bin\\node.exe" "%~dp0\\..\\client\\bin\\run" %*\r\n)\r\n')


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CLIENT = load("scout_client_version_windows", SCRIPTS / "client-version.py")
OWNER = load("scout_cli_owner_windows", SCRIPTS / "setup-cli-owner.py")


def as_windows():
    return mock.patch.object(scout_portable, "PLATFORM", "win32")


@contextlib.contextmanager
def without(module, *names):
    """The module as Windows has it, without these attributes."""
    saved = {name: getattr(module, name) for name in names if hasattr(module, name)}
    for name in saved:
        delattr(module, name)
    try:
        yield
    finally:
        for name, value in saved.items():
            setattr(module, name, value)


JUNCTION = scout_portable.IO_REPARSE_TAG_MOUNT_POINT
CLOUD = 0x9000601A  # IO_REPARSE_TAG_CLOUD_6, one of the cloud-file tags of OneDrive's files on demand


def reparse_point_at(target: Path, tag: int = JUNCTION):
    """os.lstat, reporting `target` the way Windows reports a reparse point with this tag: a junction by default."""
    real = os.lstat

    def lstat(path, *args, **kwargs):
        info = real(path, *args, **kwargs)
        if Path(path) == target:
            return types.SimpleNamespace(st_mode=info.st_mode, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
                                         st_reparse_tag=tag, st_size=info.st_size, st_uid=getattr(info, "st_uid", 0))
        return info
    return mock.patch.object(os, "lstat", side_effect=lstat)


class Folder(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="scout-windows-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()


class ReportRepairTests(Folder):
    def test_it_reads_and_writes_without_the_posix_only_calls(self) -> None:
        with without(os, "O_NOFOLLOW", "O_NONBLOCK"):
            windows = load("scout_report_repair_windows", SCRIPTS / "scout_report_repair.py")
        self.assertEqual((windows.NOFOLLOW, windows.NONBLOCK), (0, 0))
        target = self.base / "task.json"
        target.write_bytes(b'{"old": true}\r\n')
        target.chmod(0o640)
        opened = []
        real_open = os.open

        def recording(name, flags, *args, **kwargs):
            opened.append(Path(name))
            return real_open(name, flags, *args, **kwargs)
        with as_windows(), without(os, "fchmod"), mock.patch.object(os, "open", side_effect=recording):
            windows.write(target, b'{"new": true}\r\n')
            self.assertEqual(windows.read(target), b'{"new": true}\r\n')  # bytes exact, CRLF kept
        self.assertNotIn(self.base, opened)  # Windows can't open a folder to fsync it
        if os.name == "nt":
            return  # the rest is about POSIX: permission bits, which Windows doesn't keep, and a folder's fsync
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)  # kept through os.chmod, without fchmod
        opened.clear()
        with mock.patch.object(os, "open", side_effect=recording):
            repair.write(target, b"{}")
        self.assertIn(self.base, opened)  # elsewhere the folder is still fsynced

    def test_a_junction_in_the_path_is_refused_as_a_link(self) -> None:
        folder = self.base / "linked"
        folder.mkdir()
        target = folder / "task.json"
        target.write_bytes(b"{}")
        with as_windows(), reparse_point_at(folder):
            with self.assertRaisesRegex(repair.RepairError, "symlink paths are not supported"):
                repair.read(target)
            with self.assertRaisesRegex(repair.RepairError, "symlink paths are not supported"):
                repair.write(target, b"[]")
        self.assertEqual(repair.read(target), b"{}")  # a plain folder, and on macOS and Linux no lstat of the parts

    def test_a_onedrive_folder_in_the_path_is_a_plain_folder(self) -> None:
        folder = self.base / "OneDrive - Example"
        folder.mkdir()
        target = folder / "task.json"
        target.write_bytes(b"{}")
        with as_windows(), reparse_point_at(folder, CLOUD), reparse_point_at(target, CLOUD):
            repair.write(target, b"[]")
            self.assertEqual(repair.read(target), b"[]")


class SetupPublicationTests(Folder):
    """Setup publishes through the portable replace, closed file first: on Windows a brief hold on the file, such as
    a virus scanner's, is waited out instead of failing setup halfway."""

    def held_once(self):
        real, moves = os.replace, []

        def replace(source, destination):
            moves.append(Path(destination))
            if len(moves) == 1:
                raise PermissionError(13, "synthetic: the file is held for a moment")
            return real(source, destination)
        return mock.patch.object(os, "replace", side_effect=replace), moves

    def test_each_publication_waits_out_a_brief_hold(self) -> None:
        workspace = load("scout_setup_workspace_windows", SCRIPTS / "setup-workspace.py")
        settings = load("scout_setup_settings_windows", SCRIPTS / "setup-settings.py")
        install = load("scout_install_windows", SCRIPTS / "scout_install.py")
        declared = self.base / "settings.json"
        declared.write_bytes(b'{"extraKnownMarketplaces": {"salesforce": {"source": {}}}}\n')
        cases = (("workspace config", self.base / "config.json",
                  lambda: workspace.atomic_write(self.base / "config.json", b"{}\n", "CONFIG_WRITE_FAILED")),
                 ("Claude settings", declared, lambda: settings.run_marketplace_autoupdate(declared, "salesforce")),
                 ("install pointer", self.base / "AGENTS.md", lambda: install.atomic_write(self.base / "AGENTS.md", "x\n")))
        for name, destination, publish in cases:
            with self.subTest(name=name):
                held, moves = self.held_once()
                with as_windows(), held:
                    publish()
                self.assertEqual(moves, [destination, destination])  # held once, then moved
                self.assertTrue(destination.is_file())
        self.assertTrue(json.loads(declared.read_bytes())["extraKnownMarketplaces"]["salesforce"]["autoUpdate"])
        self.assertEqual([p.name for p in self.base.iterdir() if p.name.startswith(".")], [])  # no staged copy left


class ClientVersionTests(Folder):
    def test_the_version_cache_works_without_posix_flags_or_user_ids(self) -> None:
        executable = self.base / "claude.exe"
        executable.write_bytes(b"client")
        key = CLIENT.fingerprint(str(executable))
        cache = self.base / "data" / "scout-client-versions.txt"
        with as_windows(), without(os, "O_NOFOLLOW", "O_NONBLOCK", "getuid"):
            CLIENT.write_cache(str(cache), [], key, "2.1.300")
            self.assertEqual(CLIENT.read_cache(str(cache)), [{"key": key, "version": "2.1.300"}])
            with reparse_point_at(cache):
                self.assertEqual(CLIENT.read_cache(str(cache)), [])
            with reparse_point_at(cache.parent):
                CLIENT.write_cache(str(cache), [], [key[0], 1, 2], "2.1.301")
        self.assertEqual(CLIENT.read_cache(str(cache)), [{"key": key, "version": "2.1.300"}])  # never written through a link
        with as_windows(), without(os, "O_NOFOLLOW", "O_NONBLOCK", "getuid"):
            with reparse_point_at(cache, CLOUD):  # a OneDrive file is the plain file it shows
                self.assertEqual(CLIENT.read_cache(str(cache)), [{"key": key, "version": "2.1.300"}])
            with reparse_point_at(cache.parent, CLOUD):
                CLIENT.write_cache(str(cache), [], key, "2.1.302")
        self.assertEqual(CLIENT.read_cache(str(cache)), [{"key": key, "version": "2.1.302"}])

    def test_a_slow_client_is_ended_with_its_whole_tree(self) -> None:
        executable = self.base / "claude.exe"
        executable.write_bytes(b"client")
        started, ended = {}, []

        class SlowClient:
            pid = 4242

            def __init__(self, argv, **kwargs):
                started.update(kwargs, argv=argv)
                self.calls = 0

            def __enter__(self):
                return self

            def __exit__(self, *exception):
                return False

            def communicate(self, timeout=None):
                self.calls += 1
                if self.calls == 1:
                    raise subprocess.TimeoutExpired("claude", timeout)
                return b"", None
        environment = {"SCOUT_HOST": "claude", "CLAUDE_CODE_EXECPATH": str(executable),
                       "CLAUDE_CODE_ENTRYPOINT": "claude-desktop"}
        with as_windows(), mock.patch.dict(os.environ, environment), mock.patch.object(subprocess, "Popen", SlowClient), \
                mock.patch.object(scout_portable, "kill_tree", side_effect=ended.append) as kill:
            observation = CLIENT.observe()
        self.assertEqual(observation, {"reason": "running client version probe exceeded 5 seconds"})
        kill.assert_called_once()
        self.assertEqual(started["creationflags"], scout_portable.CREATE_NEW_PROCESS_GROUP | scout_portable.CREATE_NO_WINDOW)
        self.assertNotIn("start_new_session", started)
        floor = CLIENT.floor_line({"version": "2.1.280", "kind": "desktop"})
        self.assertIn("Update the Claude desktop app", floor)  # the notice itself is the same on every platform


@unittest.skipIf(os.name == "nt", "the npm stand-in is a script with a shebang")
class CliOwnerTests(Folder):
    def setUp(self) -> None:
        super().setUp()
        self.prefix = self.base / "npm"
        self.root = self.prefix / "node_modules"
        package = self.root / "@salesforce" / "cli"
        (package / "bin").mkdir(parents=True)
        (package / "package.json").write_text(json.dumps({"name": "@salesforce/cli", "bin": {"sf": "bin/run.js"}}))
        script = package / "bin" / "run.js"
        script.write_text("// the CLI")
        script.chmod(0o755)
        self.shim = self.prefix / "sf.cmd"
        self.shim.write_text(NPM_SHIM)
        (self.prefix / "node.exe").write_bytes(b"node")
        self.npm = self.base / "npm-stand-in"
        self.npm.write_text(f"#!{sys.executable}\nprint({str(self.root)!r})\n")
        self.npm.chmod(0o755)
        local = mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.base / "LocalAppData")})
        local.start()
        self.addCleanup(local.stop)

    def owner(self, active: Path) -> str:
        return OWNER.npm_ownership("sf", str(self.npm), str(active))

    def test_a_plain_npm_install_is_npm_owned(self) -> None:
        with as_windows():
            self.assertEqual(self.owner(self.shim), "owned")
        # Elsewhere the active CLI must be npm's own symlink; a shim file isn't one.
        self.assertEqual(self.owner(self.shim), "different")

    def test_the_installers_cli_belongs_to_another_installation(self) -> None:
        launcher = self.base / "Program Files" / "sf" / "bin" / "sf.cmd"
        launcher.parent.mkdir(parents=True)
        launcher.write_text(INSTALLER_LAUNCHER)
        client = self.base / "Program Files" / "sf" / "client"
        (client / "bin").mkdir(parents=True)
        (client / "bin" / "run").write_text("// the CLI")
        (client / "bin" / "node.exe").write_bytes(b"node")
        (client / "package.json").write_text(json.dumps({"name": "@salesforce/cli"}))
        with as_windows():
            self.assertEqual(self.owner(launcher), "different")

    def test_a_launcher_it_cannot_resolve_proves_nothing(self) -> None:
        wrapper = self.base / "tools" / "sf.cmd"
        wrapper.parent.mkdir()
        wrapper.write_text("@echo off\r\nC:\\tools\\sf.exe %*\r\n")
        with as_windows():
            self.assertEqual(self.owner(wrapper), "unavailable")



class TeamModeOnWindowsTests(unittest.TestCase):
    """Team mode runs on macOS for now. On Windows its helper refuses before any step, so no liveness check runs
    there (os.kill(pid, 0) would end the process), and the prompt hook returns at once."""

    def test_the_team_helper_refuses_on_windows_before_any_step(self):
        team = load("scout_team_windows", SCRIPTS / "scout_team.py")
        handler = mock.Mock(side_effect=AssertionError("no team step runs on Windows"))
        out = io.StringIO()
        with mock.patch.object(team.os, "name", "nt"), mock.patch.dict(team.__dict__, {"cmd_context": handler}), \
                contextlib.redirect_stdout(out):
            code = team.main(["context"])
        self.assertEqual(code, 2)
        self.assertIn("runs on macOS for now", json.loads(out.getvalue())["reason"])
        handler.assert_not_called()
        quiet = io.StringIO()
        with mock.patch.object(team.os, "name", "nt"), contextlib.redirect_stdout(quiet):
            self.assertEqual(team.main(["updates", "--hook"]), 0)  # the prompt hook stays silent
        self.assertEqual(quiet.getvalue(), "")

    def test_the_prompt_hook_runs_no_team_helper_on_windows(self):
        hook = load("scout_team_updates_windows", ROOT / "hooks" / "team_updates.py")
        with tempfile.TemporaryDirectory() as raw:
            teams = Path(raw) / "teams.json"
            teams.write_text("{}")
            with mock.patch.object(hook.os, "name", "nt"), mock.patch.dict(os.environ, {"SCOUT_TEAMS_FILE": str(teams)}), \
                    mock.patch.object(hook.subprocess, "run", side_effect=AssertionError("no helper on Windows")):
                self.assertEqual(hook.main(), 0)


if __name__ == "__main__":
    unittest.main()
