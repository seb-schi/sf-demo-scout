#!/usr/bin/env python3
"""The few things Scout's Python helpers do differently on Windows, in one place.

- lock(path): an exclusive lock on a lock file that never waits (fcntl, or msvcrt on Windows)
- replace(src, dst): os.replace, retried briefly on Windows, where antivirus or a reader can hold a file
- private_tempdir(): a new folder that only this user can read, under the user's temp folder
- shell_which(name) and exec_status(error): find a command and report a failed start the way a shell does
- process_group_options() and kill_tree(proc): start a child in its own process group, and end it together
  with everything it started (taskkill /T /F on Windows)
- sf_argv(executable), cmd_safe(args) and sf_command(executable, args): run the Salesforce CLI without
  cmd.exe re-parsing its arguments
- is_link(info): whether an os.lstat() result is a link, on Windows a junction too, but never a cloud file

Standard library only, Python 3.9 or newer. Every Windows branch reads PLATFORM when it runs, so tests can set
it to "win32" and exercise those branches on any machine.
"""
from __future__ import annotations

import contextlib
import errno
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Iterator, List, Optional, Sequence

PLATFORM = sys.platform

# Windows process creation flags. The subprocess module defines them only on Windows.
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000

# What cmd.exe expands or reinterprets in a batch file's arguments.
CMD_METACHARACTERS = frozenset('%!^&|"()<>\r\n')
BATCH_SUFFIXES = (".cmd", ".bat")
NPM_ENTRY = re.compile(r"node_modules\\@salesforce\\cli\\bin\\(run(?:\.js)?)\b")
SALESFORCE_CLI = "@salesforce/cli"
# Windows reparse tags (winnt.h) that make a path a link: a symbolic link, a junction, and any other tag with the
# name-surrogate bit. Every other reparse point, such as the cloud files and folders OneDrive keeps, is the plain
# file or folder it shows.
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
IO_REPARSE_TAG_SYMLINK = 0xA000000C
NAME_SURROGATE = 0x20000000


def windows() -> bool:
    return PLATFORM == "win32"


@contextlib.contextmanager
def lock(path) -> Iterator[None]:
    """Hold an exclusive lock on the lock file at `path` (created with mode 0600 when missing) for the block.

    It never waits: when another process holds the lock, it raises BlockingIOError at once. The lock ends with
    the block, or with the process.
    """
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(os.fspath(path), flags, 0o600)
    try:
        if windows():
            import msvcrt  # Windows only; it locks a byte range, here the file's first byte

            os.lseek(descriptor, 0, os.SEEK_SET)
            try:
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise BlockingIOError(errno.EAGAIN, "another process holds the lock") from error
            try:
                yield
            finally:
                os.lseek(descriptor, 0, os.SEEK_SET)
                try:
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass  # closing the file releases it as well
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
    finally:
        os.close(descriptor)


def replace(src, dst, *, attempts: int = 8, delay: float = 0.05) -> None:
    """os.replace(src, dst).

    On Windows a virus scanner or a reader can hold either file for a moment, so a sharing or access error is
    retried for about a second and a half. Elsewhere such an error is final and is raised at once.
    """
    if not windows():
        os.replace(src, dst)
        return
    for attempt in range(1, attempts + 1):
        try:
            os.replace(src, dst)
            return
        except OSError as error:
            if attempt == attempts or not _transient(error):
                raise
        time.sleep(delay * attempt)


def _transient(error: OSError) -> bool:
    return (isinstance(error, PermissionError) or error.errno == errno.EBUSY
            or getattr(error, "winerror", None) in (5, 32, 33))


def private_tempdir(prefix: str = "scout-", base=None) -> str:
    """Make a new folder that only this user can read and return its resolved path; the caller removes it.

    It goes under `base`, else the user's temp folder: mode 0700 on macOS and Linux, and on Windows the
    per-user temp folder's own permissions.
    """
    parent = os.path.realpath(os.fspath(base) if base is not None else tempfile.gettempdir())
    return os.path.realpath(tempfile.mkdtemp(prefix=prefix, dir=parent))


def shell_which(name: str) -> Optional[str]:
    """The command a POSIX shell would select for `name`: the first executable file of that name on PATH, else
    the first one that isn't executable, which the shell would then fail to run. On Windows, shutil.which."""
    if windows():
        return shutil.which(name)
    fallback = None
    for folder in os.environ.get("PATH", os.defpath).split(os.pathsep):
        candidate = os.path.join(folder or ".", name)
        if os.path.isfile(candidate):
            if os.access(candidate, os.X_OK):
                return candidate
            fallback = fallback or candidate
    return fallback


def exec_status(error: OSError) -> int:
    """The status a shell reports when it can't start a command: 126 when it can't run it, 127 when it's missing."""
    return 127 if isinstance(error, (FileNotFoundError, NotADirectoryError)) else 126


def process_group_options() -> dict:
    """Popen keyword arguments that start a child in its own process group, so kill_tree() can end it with
    everything it starts. On Windows the child also gets no console window, so none flashes up."""
    if windows():
        return {"creationflags": CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW}
    return {"start_new_session": True}


def kill_tree(proc, grace: float = 1.0) -> None:
    """End `proc` and every process it started, then reap it.

    On Windows, taskkill ends the whole tree (/T) at once (/F). Elsewhere the child's process group gets
    SIGTERM, then SIGKILL after `grace` seconds; that needs a child started with process_group_options().
    """
    if windows():
        system = os.environ.get("SystemRoot") or "C:\\Windows"
        try:
            subprocess.run([os.path.join(system, "System32", "taskkill.exe"), "/T", "/F", "/PID", str(proc.pid)],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=CREATE_NO_WINDOW, timeout=10, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            proc.kill()  # the child itself, if taskkill couldn't run
        except OSError:
            pass
    else:
        _signal_group(proc, signal.SIGTERM)
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            pass
        _signal_group(proc, signal.SIGKILL)  # whatever outlived SIGTERM, the child's own children included
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def _signal_group(proc, sig) -> None:
    try:
        os.killpg(proc.pid, sig)
        return
    except OSError:
        pass  # no such group: it's gone, or the child never had one of its own
    if proc.poll() is None:
        try:
            proc.send_signal(sig)
        except OSError:
            pass


def is_link(info) -> bool:
    """Whether an os.lstat() result is a link: a symbolic link, or on Windows also a junction or another name
    surrogate. There lstat opens only those itself and reads any other reparse point as os.stat would, so a OneDrive
    file or folder is no link, however it's synced."""
    if stat.S_ISLNK(info.st_mode):
        return True
    tag = getattr(info, "st_reparse_tag", 0) or 0
    return tag in (IO_REPARSE_TAG_SYMLINK, IO_REPARSE_TAG_MOUNT_POINT) or bool(tag & NAME_SURROGATE)


def cmd_safe(args: Sequence[str]) -> List[str]:
    """Return `args` as strings, or raise ValueError for one that cmd.exe would re-read.

    Only for a Salesforce CLI that can run nowhere but through its batch launcher: cmd.exe expands or
    reinterprets % ! ^ & | " ( ) < > and line breaks in a batch file's arguments, so they would no longer reach
    the CLI as written.
    """
    checked = []
    for argument in args:
        text = str(argument)
        found = sorted(set(text) & CMD_METACHARACTERS)
        if found:
            shown = " ".join("a line break" if character in "\r\n" else character for character in found)
            raise ValueError("the Salesforce CLI could only run through its batch launcher, because Scout "
                             "couldn't find the Node script that launcher starts, and cmd.exe would re-read "
                             + shown + " in this argument; Scout won't pass it that way")
        checked.append(text)
    return checked


def sf_argv(executable: str) -> List[str]:
    """The argv prefix that runs the Salesforce CLI without cmd.exe re-parsing the arguments.

    On Windows the CLI's `sf` is a batch file: npm's `sf.cmd` shim, or `bin\\sf.cmd` from Salesforce's
    installer, which hands over to an update under %LOCALAPPDATA%\\sf when there is one. Each of them only
    starts `node <the CLI's run script>`, so this returns that pair, and every argument then reaches the CLI as
    written. On macOS and Linux it returns `[executable]`, and on Windows anything it can't resolve comes back
    as the full path of what was found; a batch file left that way needs cmd_safe() for its arguments, which
    sf_command() applies.
    """
    if not windows():
        return [executable]
    found = _locate(executable)
    if found is None:
        return [executable]
    if found.lower().endswith(BATCH_SUFFIXES):
        resolved = _npm_entry(found) or _installer_entry(found)
        if resolved:
            return resolved
    return [found]


def sf_command(executable: str, args: Sequence[str]) -> List[str]:
    """The whole argv for one Salesforce CLI call: sf_argv(executable) and then `args`.

    When the CLI could only run through its batch launcher, the arguments go through cmd_safe() first, so this
    raises ValueError for one that cmd.exe would re-read.
    """
    prefix = sf_argv(executable)
    arguments = [str(argument) for argument in args]
    if windows() and prefix[0].lower().endswith(BATCH_SUFFIXES):
        cmd_safe(arguments)
    return prefix + arguments


def _locate(executable: str) -> Optional[str]:
    separators = {os.sep, "/"} | ({os.altsep} if os.altsep else set())
    if any(separator in executable for separator in separators):
        return executable if os.path.isfile(executable) else None
    return shutil.which(executable)


def _batch_text(script: str) -> str:
    """The launcher's text, lower case and with backslashes only, for matching; empty when unreadable."""
    try:
        with open(script, "rb") as stream:
            raw = stream.read(65536)
    except OSError:
        return ""
    return raw.decode("utf-8", "replace").replace("/", "\\").lower()


def _node(folder: str) -> Optional[str]:
    """The node.exe a launcher in `folder` would use: its own copy, else the first `node` on PATH."""
    bundled = os.path.join(folder, "node.exe")
    return bundled if os.path.isfile(bundled) else shutil.which("node")


def _npm_entry(script: str) -> Optional[List[str]]:
    """npm's shim runs `<shim folder>\\node_modules\\@salesforce\\cli\\bin\\run.js` with the node beside it, or the
    node on PATH."""
    match = NPM_ENTRY.search(_batch_text(script))
    if not match:
        return None
    folder = os.path.dirname(os.path.abspath(script))
    entry = os.path.join(folder, "node_modules", "@salesforce", "cli", "bin", match.group(1))
    node = _node(folder)
    if not os.path.isfile(entry) or not node:
        return None
    return [node, entry]


def _installer_entry(script: str) -> Optional[List[str]]:
    """The installer's `bin\\sf.cmd` runs `client\\bin\\run` with the node.exe shipped in `client\\bin`, unless an
    update the CLI installed for this user exists under %LOCALAPPDATA%\\sf\\client, which then runs instead. A
    client's own `bin\\sf.cmd` runs the `bin\\run` beside it the same way."""
    if "\\bin\\run" not in _batch_text(script):
        return None
    folder = os.path.dirname(os.path.abspath(script))
    local = os.environ.get("LOCALAPPDATA")
    update = os.path.join(local, "sf", "client") if local else None
    if update and os.path.isfile(os.path.join(update, "bin", "sf.cmd")):
        clients = [update]
    else:
        clients = [os.path.join(folder, os.pardir, "client"), os.path.join(folder, os.pardir)]
    for client in clients:
        entry = _run_script(client)
        if entry is None or not _names_salesforce_cli(client):
            continue
        node = _node(os.path.join(client, "bin"))
        return [os.path.normpath(node), os.path.normpath(entry)] if node else None
    return None


def _run_script(client: str) -> Optional[str]:
    for name in ("run", "run.js"):
        entry = os.path.join(client, "bin", name)
        if os.path.isfile(entry):
            return entry
    return None


def _names_salesforce_cli(client: str) -> bool:
    try:
        with open(os.path.join(client, "package.json"), encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, ValueError):
        return False
    return isinstance(manifest, dict) and manifest.get("name") == SALESFORCE_CLI
