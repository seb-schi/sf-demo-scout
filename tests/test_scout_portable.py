"""scripts/scout_portable.py, with its Windows branches run on any machine by injecting the platform."""
from __future__ import annotations

import errno
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.dont_write_bytecode = True
import scout_portable as portable  # noqa: E402
import scout_prep as prep  # noqa: E402
import scout_report_repair as repair  # noqa: E402


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WORKSPACE = load("scout_setup_workspace", ROOT / "scripts" / "setup-workspace.py")

SOQL = "SELECT COUNT() FROM Account WHERE Name LIKE '100%' AND (Industry != null)"
# npm's cmd-shim, as `npm install --global` writes it next to node.exe
NPM_SHIM = r"""@ECHO off
GOTO start
:find_dp0
SET dp0=%~dp0
EXIT /b
:start
SETLOCAL
CALL :find_dp0

IF EXIST "%dp0%\node.exe" (
  SET "_prog=%dp0%\node.exe"
) ELSE (
  SET "_prog=node"
  SET PATHEXT=%PATHEXT:;.JS;=;%
)

endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & "%_prog%"  "%dp0%\node_modules\@salesforce\cli\bin\run.js" %*
"""
# The installer's bin\sf.cmd, which hands over to an update under %LOCALAPPDATA%\sf when there is one
INSTALLER_LAUNCHER = r"""@echo off
setlocal enableextensions
set SF_BINPATH=%~dp0\sf.cmd
if exist "%LOCALAPPDATA%\sf\client\bin\sf.cmd" (
  "%LOCALAPPDATA%\sf\client\bin\sf.cmd" %*
) else (
  "%~dp0\..\client\bin\node.exe" "%~dp0\..\client\bin\run" %*
)
"""
CLIENT_LAUNCHER = r"""@echo off
setlocal enableextensions
if not "%SF_REDIRECTED%"=="1" if exist "%LOCALAPPDATA%\sf\client\bin\sf.cmd" (
  set SF_REDIRECTED=1
  "%LOCALAPPDATA%\sf\client\bin\sf.cmd" %*
  goto:EOF
)
if exist "%~dp0..\bin\node.exe" (
  "%~dp0..\bin\node.exe" "%~dp0..\bin\run" %*
) else (
  node "%~dp0..\bin\run" %*
)
"""


def as_windows():
    return mock.patch.object(portable, "PLATFORM", "win32")


class Folder(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="scout-portable-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()

    def file(self, relative: str, text: str = "") -> Path:
        path = self.base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path


class PlatformTests(unittest.TestCase):
    def test_the_platform_is_read_when_each_branch_runs(self) -> None:
        self.assertEqual(portable.windows(), sys.platform == "win32")
        with as_windows():
            self.assertTrue(portable.windows())
        with mock.patch.object(portable, "PLATFORM", "darwin"):
            self.assertFalse(portable.windows())


class LockTests(Folder):
    @unittest.skipIf(os.name == "nt", "fcntl locks")
    def test_a_second_holder_is_refused_at_once_and_the_lock_ends_with_the_block(self) -> None:
        target = self.base / "repair.lock"
        with portable.lock(target):
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            started = time.monotonic()
            with self.assertRaises(BlockingIOError):
                with portable.lock(target):
                    pass
            self.assertLess(time.monotonic() - started, 1)
        with portable.lock(target):  # free again
            pass

    @unittest.skipIf(os.name == "nt", "fcntl locks")
    def test_another_process_holding_it_counts(self) -> None:
        target = self.base / "repair.lock"
        holder = subprocess.Popen(
            [sys.executable, "-B", "-c", "import sys, time; sys.path.insert(0, sys.argv[1]); import scout_portable as p\n"
             "with p.lock(sys.argv[2]):\n    print('held', flush=True); time.sleep(30)\n",
             str(ROOT / "scripts"), str(target)], stdout=subprocess.PIPE, text=True)
        self.addCleanup(holder.stdout.close)
        self.addCleanup(holder.wait)
        self.addCleanup(holder.kill)
        self.assertEqual(holder.stdout.readline().strip(), "held")
        with self.assertRaises(BlockingIOError):
            with portable.lock(target):
                pass

    def test_windows_locks_the_first_byte_without_waiting_and_unlocks_it(self) -> None:
        calls = []
        held = {"value": False}

        def locking(descriptor, mode, size):
            calls.append((mode, size, os.lseek(descriptor, 0, os.SEEK_CUR)))
            if mode == fake.LK_NBLCK and held["value"]:
                raise OSError(errno.EACCES, "locked")
        fake = types.SimpleNamespace(LK_NBLCK=2, LK_UNLCK=0, locking=locking)
        target = self.base / "repair.lock"
        with as_windows(), mock.patch.dict(sys.modules, {"msvcrt": fake}):
            with portable.lock(target):
                pass
            self.assertEqual(calls, [(fake.LK_NBLCK, 1, 0), (fake.LK_UNLCK, 1, 0)])
            held["value"] = True
            with self.assertRaises(BlockingIOError):
                with portable.lock(target):
                    self.fail("the block never runs when the lock is held")


class ReplaceTests(Folder):
    def test_replace_moves_the_file_over_an_existing_one(self) -> None:
        source, target = self.file("a.tmp", "new"), self.file("a.json", "old")
        portable.replace(source, target)
        self.assertEqual((target.read_text(), source.exists()), ("new", False))

    def test_elsewhere_an_error_is_final(self) -> None:
        with mock.patch.object(portable, "PLATFORM", "linux"), \
                mock.patch.object(portable.os, "replace", side_effect=PermissionError(errno.EACCES, "denied")) as move:
            with self.assertRaises(PermissionError):
                portable.replace("a", "b")
        self.assertEqual(move.call_count, 1)

    def test_windows_retries_a_held_file_then_succeeds(self) -> None:
        errors = [PermissionError(errno.EACCES, "sharing violation"), OSError(errno.EBUSY, "busy"), None]
        with as_windows(), mock.patch.object(portable.time, "sleep") as sleep, \
                mock.patch.object(portable.os, "replace", side_effect=errors) as move:
            portable.replace("a", "b")
        self.assertEqual(move.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_windows_gives_up_after_its_attempts_and_never_retries_a_real_error(self) -> None:
        with as_windows(), mock.patch.object(portable.time, "sleep"), \
                mock.patch.object(portable.os, "replace", side_effect=PermissionError(errno.EACCES, "held")) as move:
            with self.assertRaises(PermissionError):
                portable.replace("a", "b", attempts=3)
        self.assertEqual(move.call_count, 3)
        with as_windows(), mock.patch.object(portable.time, "sleep"), \
                mock.patch.object(portable.os, "replace", side_effect=FileNotFoundError(errno.ENOENT, "gone")) as move:
            with self.assertRaises(FileNotFoundError):
                portable.replace("a", "b")
        self.assertEqual(move.call_count, 1)


class TempdirTests(Folder):
    def test_a_new_private_folder_under_the_base(self) -> None:
        first = Path(portable.private_tempdir("scout-x.", self.base))
        second = Path(portable.private_tempdir("scout-x.", self.base))
        self.assertNotEqual(first, second)
        self.assertEqual((first.parent, second.parent), (self.base, self.base))
        self.assertTrue(first.name.startswith("scout-x."))
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(first.stat().st_mode), 0o700)
        default = Path(portable.private_tempdir())
        self.addCleanup(default.rmdir)
        self.assertEqual(default.parent, Path(os.path.realpath(tempfile.gettempdir())))


class ProcessTests(unittest.TestCase):
    def test_group_options_per_platform(self) -> None:
        with mock.patch.object(portable, "PLATFORM", "darwin"):
            self.assertEqual(portable.process_group_options(), {"start_new_session": True})
        with as_windows():
            self.assertEqual(portable.process_group_options(),
                             {"creationflags": portable.CREATE_NEW_PROCESS_GROUP | portable.CREATE_NO_WINDOW})
        self.assertEqual((portable.CREATE_NEW_PROCESS_GROUP, portable.CREATE_NO_WINDOW), (0x200, 0x08000000))

    @unittest.skipUnless(Path("/bin/sh").exists() and os.name != "nt", "a POSIX process group")
    def test_kill_tree_ends_the_child_and_what_it_started(self) -> None:
        proc = subprocess.Popen(["/bin/sh", "-c", "trap '' TERM; sleep 30 & echo $!; wait"], stdout=subprocess.PIPE,
                                text=True, **portable.process_group_options())
        grandchild = int(proc.stdout.readline())
        started = time.monotonic()
        portable.kill_tree(proc, grace=0.3)  # the shell ignores SIGTERM, so SIGKILL has to end it
        self.assertIsNotNone(proc.returncode)
        self.assertLess(time.monotonic() - started, 5)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.killpg(proc.pid, 0)
            except ProcessLookupError:
                break
            except PermissionError:
                pass  # macOS answers EPERM for a group of killed processes not yet reaped; keep waiting for it to go
            time.sleep(0.05)
        else:
            self.fail("the background child outlived kill_tree")
        with self.assertRaises(ProcessLookupError):
            os.kill(grandchild, 0)
        proc.stdout.close()

    @unittest.skipIf(os.name == "nt", "POSIX signals")
    def test_kill_tree_still_ends_a_child_without_a_group_of_its_own(self) -> None:
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        portable.kill_tree(proc, grace=0.3)
        self.assertIsNotNone(proc.returncode)

    def test_windows_ends_the_tree_with_taskkill(self) -> None:
        proc = mock.Mock(pid=4242)
        with as_windows(), mock.patch.dict(os.environ, {"SystemRoot": "C:\\Windows"}), \
                mock.patch.object(portable.subprocess, "run") as run:
            portable.kill_tree(proc)
        command = run.call_args.args[0]
        self.assertTrue(command[0].endswith("taskkill.exe"))
        self.assertTrue(command[0].startswith("C:\\Windows"))
        self.assertEqual(command[1:], ["/T", "/F", "/PID", "4242"])
        self.assertEqual(run.call_args.kwargs["creationflags"], portable.CREATE_NO_WINDOW)
        proc.kill.assert_called_once_with()
        proc.wait.assert_called()


class ShellWhichTests(Folder):
    @unittest.skipIf(os.name == "nt", "executable bits")
    def test_the_first_executable_wins_else_a_file_the_shell_cannot_run(self) -> None:
        blocked = self.file("one/tool", "#!/bin/sh\n")
        blocked.chmod(0o600)
        runnable = self.file("two/tool", "#!/bin/sh\n")
        runnable.chmod(0o700)
        path = os.pathsep.join([str(blocked.parent), str(runnable.parent)])
        with mock.patch.dict(os.environ, {"PATH": path}):
            self.assertEqual(portable.shell_which("tool"), str(runnable))
            runnable.chmod(0o600)
            self.assertEqual(portable.shell_which("tool"), str(blocked))
            self.assertIsNone(portable.shell_which("absent"))
        self.assertEqual(portable.exec_status(FileNotFoundError()), 127)
        self.assertEqual(portable.exec_status(PermissionError()), 126)

    def test_windows_uses_its_own_lookup(self) -> None:
        with as_windows(), mock.patch.object(portable.shutil, "which", return_value="C:\\x\\npm.cmd") as which:
            self.assertEqual(portable.shell_which("npm"), "C:\\x\\npm.cmd")
        which.assert_called_once_with("npm")


class LinkTests(Folder):
    def test_only_links_count_a_cloud_file_doesnt(self) -> None:
        plain = os.lstat(self.base)
        self.assertFalse(portable.is_link(plain))
        def reparse(tag):
            return types.SimpleNamespace(st_mode=plain.st_mode, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
                                         st_reparse_tag=tag)
        for tag in (portable.IO_REPARSE_TAG_SYMLINK, portable.IO_REPARSE_TAG_MOUNT_POINT, 0xA0000027):
            self.assertTrue(portable.is_link(reparse(tag)), hex(tag))  # a symlink, a junction, another name surrogate
        for tag in (0x9000601A, 0x9000001A, 0x80000021):
            self.assertFalse(portable.is_link(reparse(tag)), hex(tag))  # cloud files and OneDrive's own tag
        if hasattr(os, "symlink"):
            link = self.base / "link"
            try:
                link.symlink_to(self.base, target_is_directory=True)
            except OSError:
                return  # Windows allows links only with Developer Mode or as an administrator
            self.assertTrue(portable.is_link(os.lstat(link)))


class CmdSafeTests(unittest.TestCase):
    def test_plain_arguments_pass_as_strings(self) -> None:
        self.assertEqual(portable.cmd_safe(["org", "display", "--target-org", "QA A", 42]),
                         ["org", "display", "--target-org", "QA A", "42"])

    def test_every_character_cmd_would_reread_is_refused_with_the_reason(self) -> None:
        for character in '%!^&|"()<>\r\n':
            with self.subTest(character=repr(character)):
                with self.assertRaises(ValueError) as caught:
                    portable.cmd_safe(["data", "query", "--query", f"SELECT Id {character} x"])
                message = str(caught.exception)
                self.assertIn("cmd.exe would re-read", message)
                self.assertIn("a line break" if character in "\r\n" else character, message)
                self.assertIn("couldn't find the Node script", message)


class Layouts(Folder):
    """The Salesforce CLI's two Windows layouts, laid out in a temporary folder."""

    def npm_layout(self, *, node_beside: bool = True) -> Path:
        shim = self.file("npm/sf.cmd", NPM_SHIM)
        if node_beside:
            self.file("npm/node.exe")
        self.file("npm/node_modules/@salesforce/cli/bin/run.js", "// the CLI")
        self.file("npm/node_modules/@salesforce/cli/package.json", json.dumps({"name": "@salesforce/cli"}))
        return shim

    def client(self, root: str, *, name: str = "@salesforce/cli", run: str = "run") -> Path:
        self.file(f"{root}/bin/node.exe")
        self.file(f"{root}/bin/{run}", "// the CLI")
        self.file(f"{root}/package.json", json.dumps({"name": name}))
        return self.base / root

    def installer_layout(self, **client) -> Path:
        launcher = self.file("Program Files/sf/bin/sf.cmd", INSTALLER_LAUNCHER)
        self.client("Program Files/sf/client", **client)
        return launcher

    def windows(self, **environment):
        environment.setdefault("LOCALAPPDATA", str(self.base / "LocalAppData"))
        return mock.patch.dict(os.environ, environment)

    def node_entry(self, launcher: Path) -> list[str]:
        with as_windows(), self.windows():
            return portable.sf_argv(str(launcher))


class SalesforceCliTests(Layouts):
    def test_elsewhere_the_cli_runs_as_found_with_any_argument(self) -> None:
        with mock.patch.object(portable, "PLATFORM", "darwin"):
            self.assertEqual(portable.sf_argv("/usr/local/bin/sf"), ["/usr/local/bin/sf"])
            self.assertEqual(portable.sf_command("sf", ["data", "query", "--query", SOQL]),
                             ["sf", "data", "query", "--query", SOQL])

    def test_the_npm_shim_runs_its_node_script_and_soql_passes_unchanged(self) -> None:
        shim = self.npm_layout()
        with as_windows(), self.windows():
            argv = portable.sf_command(str(shim), ["data", "query", "--query", SOQL, "--json"])
        self.assertEqual(argv, [os.path.join(str(shim.parent), "node.exe"),
                                os.path.join(str(shim.parent), "node_modules", "@salesforce", "cli", "bin", "run.js"),
                                "data", "query", "--query", SOQL, "--json"])

    def test_the_npm_shim_without_its_own_node_uses_the_node_on_path(self) -> None:
        shim = self.npm_layout(node_beside=False)
        with as_windows(), self.windows(), mock.patch.object(portable.shutil, "which", return_value="C:\\node\\node.exe"):
            self.assertEqual(portable.sf_argv(str(shim))[0], "C:\\node\\node.exe")
        with as_windows(), self.windows(), mock.patch.object(portable.shutil, "which", return_value=None):
            self.assertEqual(portable.sf_argv(str(shim)), [str(shim)])  # no Node: the batch file, checked

    def test_the_installer_runs_its_bundled_node_and_soql_passes_unchanged(self) -> None:
        launcher = self.installer_layout()
        client = self.base / "Program Files" / "sf" / "client"
        with as_windows(), self.windows():
            argv = portable.sf_command(str(launcher), ["data", "query", "--query", SOQL])
        self.assertEqual(argv, [os.path.normpath(str(client / "bin" / "node.exe")),
                                os.path.normpath(str(client / "bin" / "run")), "data", "query", "--query", SOQL])

    def test_an_update_under_local_app_data_wins_as_the_launcher_has_it(self) -> None:
        launcher = self.installer_layout()
        update = self.client("LocalAppData/sf/client", run="run.js")
        self.file("LocalAppData/sf/client/bin/sf.cmd", CLIENT_LAUNCHER)
        with as_windows(), self.windows():
            self.assertEqual(portable.sf_argv(str(launcher)),
                             [os.path.normpath(str(update / "bin" / "node.exe")),
                              os.path.normpath(str(update / "bin" / "run.js"))])
            # The update's own launcher, found first on PATH, resolves to the same pair.
            self.assertEqual(portable.sf_argv(str(update / "bin" / "sf.cmd")), portable.sf_argv(str(launcher)))

    def test_an_update_that_cant_be_resolved_never_falls_back_to_the_older_client(self) -> None:
        launcher = self.installer_layout()
        self.file("LocalAppData/sf/client/bin/sf.cmd", CLIENT_LAUNCHER)  # no run script beside it
        with as_windows(), self.windows():
            self.assertEqual(portable.sf_argv(str(launcher)), [str(launcher)])
            with self.assertRaises(ValueError) as caught:
                portable.sf_command(str(launcher), ["data", "query", "--query", SOQL])
            self.assertIn("would re-read ! % ( ) in this argument", str(caught.exception))
            self.assertEqual(portable.sf_command(str(launcher), ["org", "display", "--json"]),
                             [str(launcher), "org", "display", "--json"])

    def test_another_tools_client_or_an_unknown_wrapper_is_not_resolved(self) -> None:
        launcher = self.installer_layout(name="some-other-cli")
        wrapper = self.file("wrapper/sf.bat", "@echo off\r\ncall C:\\tools\\sf.exe %*\r\n")
        with as_windows(), self.windows():
            self.assertEqual(portable.sf_argv(str(launcher)), [str(launcher)])
            self.assertEqual(portable.sf_argv(str(wrapper)), [str(wrapper)])
            for script in (launcher, wrapper):
                with self.assertRaises(ValueError):
                    portable.sf_command(str(script), ["data", "query", "--query", SOQL])

    def test_a_bare_name_is_looked_up_and_an_absent_cli_comes_back_unchanged(self) -> None:
        shim = self.npm_layout()
        with as_windows(), self.windows(), mock.patch.object(portable.shutil, "which", return_value=str(shim)) as which:
            self.assertEqual(len(portable.sf_argv("sf")), 2)
        which.assert_called_once_with("sf")
        with as_windows(), self.windows(), mock.patch.object(portable.shutil, "which", return_value=None):
            self.assertEqual(portable.sf_argv("sf"), ["sf"])
            self.assertEqual(portable.sf_argv(str(self.base / "missing" / "sf.cmd")),
                             [str(self.base / "missing" / "sf.cmd")])

    def test_an_executable_cli_needs_no_check(self) -> None:
        exe = self.file("bin/sf.exe")
        with as_windows(), self.windows():
            self.assertEqual(portable.sf_command(str(exe), ["data", "query", "--query", SOQL]),
                             [str(exe), "data", "query", "--query", SOQL])



class WiringTests(Layouts):
    """Prep, report repair and workspace setup run the CLI through sf_command(), so Windows gets its Node entry."""

    def capture(self, payload: bytes = b'{"status": 0, "result": {}}', error: Exception | None = None):
        calls = []

        def run(argv, **kwargs):
            calls.append(list(argv))
            if error is not None:
                raise error
            return subprocess.CompletedProcess(argv, 0, payload, b"")
        return calls, mock.patch.object(subprocess, "run", side_effect=run)

    def test_prep_runs_a_query_through_the_node_entry_on_both_layouts(self) -> None:
        for launcher in (self.npm_layout(), self.installer_layout()):
            with self.subTest(launcher=launcher.parent.name):
                calls, run = self.capture(b'{"status": 0, "result": {"records": [], "totalSize": 0}}')
                with as_windows(), self.windows(), run, mock.patch.object(prep.shutil, "which", return_value=str(launcher)):
                    try:
                        prep.run_cli(["data", "query", "--query", SOQL], scratch=self.base)
                    except prep.Refused:
                        pass  # only the command it ran matters here
                self.assertEqual(calls, [[*self.node_entry(launcher), "data", "query", "--query", SOQL, "--json"]])

    def test_prep_refuses_a_query_cmd_would_change_when_no_node_entry_is_found(self) -> None:
        wrapper = self.file("tools/sf.cmd", "@echo off\r\nC:\\tools\\sf.exe %*\r\n")
        calls, run = self.capture()
        with as_windows(), self.windows(), run, mock.patch.object(prep.shutil, "which", return_value=str(wrapper)):
            with self.assertRaises(prep.Refused) as caught:
                prep.run_cli(["data", "query", "--query", SOQL], scratch=self.base)
        self.assertIn("cmd.exe would re-read", str(caught.exception))
        self.assertEqual(calls, [])

    def test_report_repair_runs_through_the_node_entry_and_refuses_otherwise(self) -> None:
        launcher = self.installer_layout()
        calls, run = self.capture()
        with as_windows(), self.windows(), run, mock.patch.object(repair.shutil, "which", return_value=str(launcher)):
            repair.Salesforce("sf").run(["data", "query", "--query", SOQL], self.base)
        self.assertEqual(calls, [[*self.node_entry(launcher), "data", "query", "--query", SOQL, "--json"]])
        wrapper = self.file("tools/sf.bat", "@echo off\r\n")
        with as_windows(), self.windows(), mock.patch.object(repair.shutil, "which", return_value=str(wrapper)):
            with self.assertRaises(repair.RepairError) as caught:
                repair.Salesforce("sf").run(["data", "query", "--query", SOQL], self.base)
        self.assertIn("cmd.exe would re-read", str(caught.exception))

    def test_workspace_setup_scaffolds_through_the_node_entry(self) -> None:
        launcher = self.npm_layout()
        workspace = self.base / "Demo (1)" / "sf-demo-scout"  # a folder name cmd.exe would re-read
        workspace.parent.mkdir()
        calls, run = self.capture(error=OSError("stop after the call"))
        with as_windows(), self.windows(), run, mock.patch.object(WORKSPACE.shutil, "which", return_value=str(launcher)):
            with self.assertRaises(WORKSPACE.SetupFailure):
                WORKSPACE.run_sf_scaffold(workspace)
        command, = calls
        self.assertEqual(command[:2], self.node_entry(launcher))
        self.assertEqual(command[2:7], ["project", "generate", "--name", "sf-demo-scout", "--template"])
        self.assertIn("Demo (1)", command[command.index("--output-dir") + 1])
        wrapper = self.file("tools/sf.cmd", "@echo off\r\n")
        with as_windows(), self.windows(), mock.patch.object(WORKSPACE.shutil, "which", return_value=str(wrapper)):
            with self.assertRaises(WORKSPACE.SetupFailure) as caught:
                WORKSPACE.run_sf_scaffold(workspace)
        self.assertIn("cmd.exe would re-read ( )", str(caught.exception.args))
        self.assertEqual(list(workspace.parent.glob(".scout-sfdx-*")), [])  # the staging folder went with it

    def test_elsewhere_the_commands_are_unchanged(self) -> None:
        calls, run = self.capture()
        with mock.patch.object(portable, "PLATFORM", "darwin"), run, \
                mock.patch.object(repair.shutil, "which", return_value="/usr/local/bin/sf"):
            repair.Salesforce("sf").run(["data", "query", "--query", SOQL], self.base)
        self.assertEqual(calls, [["/usr/local/bin/sf", "data", "query", "--query", SOQL, "--json"]])


if __name__ == "__main__":
    unittest.main()
