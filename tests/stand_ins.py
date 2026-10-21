"""Stand-ins for the command-line tools Scout's helpers call, so the same tests run on macOS, Linux and Windows.

On macOS and Linux a stand-in is what it has always been: a file named like the tool, starting with a shebang.
Windows runs neither shebangs nor files without an extension, so there a stand-in is a `.cmd` file that starts the
same Python code. The Salesforce CLI's stand-in is also laid out the way npm installs the CLI, with the CLI's
`run.js` beside `sf.cmd`, so Scout's portable runner can take Node's route to it, as it does for a real npm
install, and hand every argument over unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest

WINDOWS = os.name == "nt"
# What a cleared environment must keep on Windows for a process, Python included, to start there.
ESSENTIALS = ("SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATHEXT", "TEMP", "TMP")
RUN_JS = """// Stands in for the Salesforce CLI's run.js: every argument goes to the Python stand-in, unchanged.
const { spawnSync } = require("child_process");
const result = spawnSync(%s, [%s, ...process.argv.slice(2)], { stdio: "inherit" });
process.exit(result.status === null ? 1 : result.status);
"""


# Never a real %LOCALAPPDATA%: there, Scout's runner looks for an installed CLI's update, and a test reaches no real sf.
NO_LOCAL_APP_DATA = os.path.join(tempfile.gettempdir(), "scout-tests-no-local-app-data")


def keep(environment: dict) -> dict:
    """`environment`, plus on Windows the variables any process needs to start there."""
    if WINDOWS:
        for name in ESSENTIALS:
            if name in os.environ:
                environment.setdefault(name, os.environ[name])
        environment.setdefault("LOCALAPPDATA", NO_LOCAL_APP_DATA)
    return environment


def cli_environment(folder, *more) -> dict:
    """PATH and LOCALAPPDATA for a test of the Salesforce CLI stand-in in `folder`, with any `more` folders after it
    on the PATH: on Windows, Node's folder follows them for Scout's runner, and no installed CLI can be found in its
    place."""
    if WINDOWS:
        return {"PATH": path(folder, *more, node=True), "LOCALAPPDATA": NO_LOCAL_APP_DATA}
    return {"PATH": path(folder, *more)}


def home(folder) -> dict:
    """The variables that point Path.home() at `folder`: HOME, and on Windows USERPROFILE, which Python reads there."""
    found = {"HOME": str(folder)}
    if WINDOWS:
        found["USERPROFILE"] = str(folder)
    return found


def path(*folders, node: bool = False) -> str:
    """These folders as a PATH, joined the platform's way. With `node`, Node's own folder follows on Windows, where
    Scout runs the Salesforce CLI's run.js with it."""
    entries = [str(folder) for folder in folders]
    if node and WINDOWS:
        found = shutil.which("node")
        if found:
            entries.append(os.path.dirname(found))
    return os.pathsep.join(entries)


def require_node() -> None:
    """On Windows, Scout reaches the Salesforce CLI through Node, so a test of that route needs it."""
    if WINDOWS and shutil.which("node") is None:
        raise unittest.SkipTest("needs Node.js, which Scout's runner uses for the Salesforce CLI on Windows")


def tool(folder, name: str, source: str) -> Path:
    """A stand-in for the command `name` that runs this Python code with the command's arguments."""
    folder = Path(folder)
    if not WINDOWS:
        stand_in = folder / name
        stand_in.write_text("#!" + sys.executable + "\n" + source)
        stand_in.chmod(0o700)
        return stand_in
    (folder / (name + ".py")).write_text(source, encoding="utf-8")
    stand_in = folder / (name + ".cmd")
    # The digest line makes a rewritten stand-in a changed file, as it is on macOS and Linux, for fingerprint checks.
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    stand_in.write_text('@rem %s.py sha256 %s\r\n@"%s" "%%~dp0%s.py" %%*\r\n' % (name, digest, sys.executable, name),
                        encoding="utf-8")
    return stand_in


def salesforce_cli(folder, source: str) -> Path:
    """The `sf` stand-in, running this Python code. On Windows, sf.cmd runs it directly, the way a caller that runs
    the CLI by name gets there, and the run.js beside it serves Scout's portable runner, which takes Node instead."""
    stand_in = tool(folder, "sf", source)
    if WINDOWS:
        run = Path(folder) / "node_modules" / "@salesforce" / "cli" / "bin" / "run.js"
        run.parent.mkdir(parents=True, exist_ok=True)
        run.write_text(RUN_JS % (json.dumps(sys.executable), json.dumps(str(Path(folder) / "sf.py"))), encoding="utf-8")
        # npm's own shim names this script; the portable runner reads that line to find run.js.
        stand_in.write_text("@rem npm layout: node_modules\\@salesforce\\cli\\bin\\run.js\r\n"
                            + stand_in.read_text(encoding="utf-8"), encoding="utf-8")
    return stand_in


def remove(stand_in) -> None:
    """Take a stand-in off the PATH, as if the tool were uninstalled: on Windows its Python file goes too, since a
    PATHEXT that lists .py would still find that one."""
    stand_in = Path(stand_in)
    stand_in.unlink()
    if WINDOWS:
        stand_in.with_suffix(".py").unlink()


_SYMLINKS = []


def symlinks() -> bool:
    """Can this account create symbolic links? Windows allows it only with Developer Mode or as an administrator."""
    if not _SYMLINKS:
        with tempfile.TemporaryDirectory(prefix="scout-symlink-probe-") as probe:
            try:
                os.symlink(probe, os.path.join(probe, "link"), target_is_directory=True)
                _SYMLINKS.append(True)
            except (OSError, NotImplementedError):
                _SYMLINKS.append(False)
    return _SYMLINKS[0]


def needs_symlinks(test):
    """Skip where symbolic links can't be made, with the reason."""
    return unittest.skipUnless(symlinks(), "needs symlinks, which Windows allows only with Developer Mode or as an "
                                           "administrator")(test)


def link_target(link) -> str:
    """What `link` points at, as it was written: Windows' readlink puts \\\\?\\ before an absolute target."""
    target = os.readlink(link)
    if WINDOWS and target.startswith("\\\\?\\"):
        target = target[4:]
    return target


NOT_WINDOWS_MODES = unittest.skipIf(WINDOWS, "checks POSIX permission bits, which Windows doesn't keep")


def ended(pid: int, seconds: float = 5.0) -> bool:
    """Whether process `pid` has ended, waiting up to `seconds` for that: on Windows, taskkill returns before the
    processes it ends have quite gone, and elsewhere an orphan is collected by the process that adopted it a moment
    after it ends."""
    deadline = time.monotonic() + seconds
    while _running(pid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def _running(pid: int) -> bool:
    if not WINDOWS:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return not _zombie(pid)
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
    kernel32.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False  # no such process any more
    try:
        code = ctypes.c_ulong()
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _zombie(pid: int) -> bool:
    """Whether `pid` has ended and only waits for its parent to collect it, which Linux shows in /proc."""
    try:
        with open("/proc/%d/stat" % pid, encoding="ascii", errors="replace") as stat:
            return stat.read().rsplit(")", 1)[1].split()[0] == "Z"  # "pid (name) state …"; a name may hold ")"
    except (OSError, IndexError):
        return False
