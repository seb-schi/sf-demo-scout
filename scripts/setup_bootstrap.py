#!/usr/bin/env python3
"""Check one of setup's prerequisites, and install it when it's missing: setup_bootstrap.py node|python|sf

It probes the executable the shell would select and installs only when there is none: Node and Python with
Homebrew, the Salesforce CLI with npm. An existing broken, malformed or unsupported tool is left unchanged;
Scout never installs a competing runtime over it. On Windows it installs nothing: a missing tool comes back as
<TOOL>_MISSING with the exact command to run, or as <TOOL>_NOT_IN_THIS_WINDOW when it's in its usual install
location but not on this window's PATH yet. It prints one outcome line (an install adds INSTALLING_<TOOL>
first) and exits 0 only for a tool that is present or was installed.
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import sys
import tempfile
from typing import List, Optional, Tuple

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scout_portable  # noqa: E402

SELECTORS = {"node": ("node", "NODE"), "python": ("python3", "PYTHON"), "sf": ("sf", "SF_CLI")}
NODE_FLOOR = (22, 20)
PYTHON_FLOOR = (3, 9)
SPACE = "[ \t\n\r\f\v]"  # the shell's [[:space:]]
VERSIONS = {
    "node": re.compile(r"v([0-9]{1,6})\.([0-9]{1,6})\.([0-9]{1,6})([-+][0-9A-Za-z.-]{1,64})?"),
    "python": re.compile(r"Python" + SPACE + r"([0-9]{1,6})\.([0-9]{1,6})\.([0-9]{1,6})((?:a|b|rc)[0-9]{1,6})?"),
    "sf": re.compile(r"@salesforce/cli/([0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6})(" + SPACE + r"[\x20-\x7e]+)?"),
}
# What a Windows user runs instead; Scout runs none of these itself.
WINDOWS_INSTALL = {
    "node": "winget install --exact --id OpenJS.NodeJS.LTS",
    # `pymanager` is the install manager's own name for `py`: an older Python launcher can take `py`, never it.
    "python": "winget install --exact --id Python.PythonInstallManager, then: pymanager install default",
    # `npm.cmd`: PowerShell would otherwise pick npm.ps1, which the default execution policy blocks on Windows.
    "sf": "npm.cmd install --global @salesforce/cli",
}
# On Windows, Python's launcher first, as the hook launcher has it; Python's own -c reports the version, because
# `--version` can reach a launcher rather than the interpreter.
WINDOWS_PYTHONS = (("py", ["-3"]), ("python", []), ("python3", []))
PYTHON_VERSION = "import platform; print('Python ' + platform.python_version())"
PROBE_SECONDS = 30  # each probe's limit: a cold start on Windows is slow, and a probe that hangs never stalls setup
NOT_IN_THIS_WINDOW = "open a new PowerShell window and quit and reopen the app, so it's found"


def classify(selector: str, output: str) -> Tuple[str, str]:
    """("valid" | "unsupported" | "invalid", the version) for a probe's output."""
    match = VERSIONS[selector].fullmatch(output)
    if not match:
        return "invalid", ""
    if selector == "sf":
        return "valid", match.group(1)
    version = ".".join(match.group(index) for index in (1, 2, 3)) + (match.group(4) or "")
    major, minor = int(match.group(1)), int(match.group(2))
    if selector == "node":
        return ("valid" if (major, minor) >= NODE_FLOOR else "unsupported"), version
    return ("valid" if major == PYTHON_FLOOR[0] and minor >= PYTHON_FLOOR[1] else "unsupported"), version


def probe(selector: str, command: List[str]) -> Tuple[str, str]:
    """Run the version probe; any failure to run, a nonzero exit or no answer in PROBE_SECONDS means "invalid"."""
    env = None
    if scout_portable.windows() and selector == "python":
        command = command + ["-c", PYTHON_VERSION]
        env = dict(os.environ, PYTHON_MANAGER_AUTOMATIC_INSTALL="false")  # a probe never installs a runtime
    else:
        command = command + ["--version"]
    try:
        with subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              env=env, **scout_portable.process_group_options()) as process:
            try:
                output, _ = process.communicate(timeout=PROBE_SECONDS)
            except subprocess.TimeoutExpired:
                scout_portable.kill_tree(process)  # with anything it started, so no one keeps the pipe open
                return "invalid", ""
    except (OSError, ValueError, subprocess.SubprocessError):
        return "invalid", ""
    if process.returncode != 0:
        return "invalid", ""
    # Native Windows programs end their line with \r\n. That's normalised here, for every tool; the version
    # patterns stay strict about everything else.
    return classify(selector, output.decode("utf-8", "replace").replace("\r\n", "\n").rstrip("\n"))


def windows_pythons() -> List[List[str]]:
    """The Python commands found on PATH, in the hook launcher's order: `py -3` (Python's launcher has no Store
    stub, so its WindowsApps alias counts), then `python` and `python3` outside a WindowsApps folder, where the
    Store's install stubs live."""
    found = []
    for name, arguments in WINDOWS_PYTHONS:
        for folder in os.environ.get("PATH", "").split(os.pathsep):
            if not folder:
                continue
            if name != "py" and os.path.basename(os.path.normpath(folder)).lower() == "windowsapps":
                continue
            candidate = os.path.join(folder, name + ".exe")
            if os.path.lexists(candidate):
                found.append([candidate, *arguments])
                break
    return found


def windows_locations(selector: str) -> List[str]:
    """Where the usual Windows installers put the tool, built from environment variables only: Node's installer,
    Python's install manager or its classic installer, and npm or Salesforce's installer for the CLI.

    Windows gives each window the PATH it had when it started, so a tool installed after the app started sits here
    but isn't on this window's PATH yet."""
    # A 32-bit Python sees Program Files (x86) as %ProgramFiles%; %ProgramW6432% still names the 64-bit folder.
    program_files = [folder for folder in dict.fromkeys((os.environ.get("ProgramFiles"),
                                                          os.environ.get("ProgramW6432"))) if folder]
    local, roaming = os.environ.get("LOCALAPPDATA"), os.environ.get("APPDATA")
    if selector == "node":
        return [os.path.join(folder, "nodejs", "node.exe") for folder in program_files]
    if selector == "python":
        if not local:
            return []
        aliases = os.path.join(local, "Microsoft", "WindowsApps")  # the install manager's app execution aliases
        classic = glob.glob(os.path.join(glob.escape(local), "Programs", "Python", "Python3*", "python.exe"))
        return [os.path.join(aliases, "pymanager.exe"), os.path.join(aliases, "py.exe"),
                os.path.join(local, "Python", "bin", "python.exe"), *sorted(classic, key=python_minor, reverse=True)]
    return ([os.path.join(roaming, "npm", "sf.cmd")] if roaming else []) + [
        os.path.join(folder, "sf", "bin", "sf.cmd") for folder in program_files]


def python_minor(path: str) -> int:
    """3.13 for ...\\Python313\\python.exe, so the newest classic install comes first."""
    match = re.match(r"python3([0-9]+)", os.path.basename(os.path.dirname(path)), re.IGNORECASE)
    return int(match.group(1)) if match else -1


def installed_elsewhere(selector: str) -> Optional[str]:
    """The first usual install location that holds the tool. Existence only: nothing there runs."""
    return next((path for path in windows_locations(selector) if os.path.lexists(path)), None)


def selected(selector: str, tool: str) -> List[List[str]]:
    """The commands to probe, in order; empty when the tool is missing."""
    if scout_portable.windows() and selector == "python":
        return windows_pythons()
    path = scout_portable.shell_which(tool)
    if path is None:
        return []
    return [scout_portable.sf_argv(path) if selector == "sf" else [path]]


def report_existing(selector: str, prefix: str, commands: List[List[str]]) -> int:
    first = None
    for command in commands:
        state, version = probe(selector, command)
        if state == "valid":
            print(f"{prefix}_PRESENT ({version})")
            return 0
        first = first or (state, version)
    state, version = first
    if state == "unsupported" and selector == "python":
        print(f"PYTHON_UNSUPPORTED (found {version or 'unknown'}; need Python 3.9+)")
    elif state == "unsupported" and selector == "node":
        print(f"NODE_UNSUPPORTED (found {version}; need Node 22.20+)")
    else:
        print(f"{prefix}_UNVERIFIED (existing executable version could not be verified)")
    return 1


def install_log(tool: str) -> Optional[str]:
    """A private file that takes the installer's output, so none of it reaches the transcript."""
    try:
        descriptor, name = tempfile.mkstemp(prefix=f"scout-{tool}-install.",
                                            dir=os.environ.get("TMPDIR") or tempfile.gettempdir())
    except OSError:
        return None
    os.close(descriptor)
    return name


def install(selector: str, tool: str, prefix: str) -> int:
    if selector == "sf":
        installer, arguments, prerequisite = (scout_portable.shell_which("npm"),
                                              ["install", "@salesforce/cli", "--global"], "npm")
    else:
        installer, arguments, prerequisite = scout_portable.shell_which("brew"), ["install", tool], "brew"
    if installer is None:
        print(f"{prefix}_UNAVAILABLE ({prerequisite} prerequisite missing)")
        return 1
    log = install_log(tool)
    if log is None:
        print(f"{prefix}_UNAVAILABLE (private install log unavailable)")
        return 1
    print(f"INSTALLING_{prefix}", flush=True)
    try:
        with open(log, "wb") as stream:
            code = subprocess.run([installer, *arguments], stdout=stream, stderr=subprocess.STDOUT,
                                  check=False).returncode
    except OSError as error:
        code = scout_portable.exec_status(error)
    finally:
        try:
            os.unlink(log)
        except OSError:
            pass
    if code != 0:
        print(f"{prefix}_INSTALL_FAILED (installer exit {128 - code if code < 0 else code})")
        return 1
    path = scout_portable.shell_which(tool)
    if path is None:
        print(f"{prefix}_UNVERIFIED (installer exited 0; selected executable missing)")
        return 1
    state, version = probe(selector, [path])
    if state != "valid":
        print(f"{prefix}_UNVERIFIED (installer exited 0; selected executable version could not be verified)")
        return 1
    print(f"{prefix}_INSTALLED ({version})")
    return 0


def main(argv: List[str]) -> int:
    selector = argv[1] if len(argv) > 1 else ""
    if selector not in SELECTORS:
        print("usage: setup_bootstrap.py node|python|sf", file=sys.stderr)
        return 64
    tool, prefix = SELECTORS[selector]
    commands = selected(selector, tool)
    if commands:
        return report_existing(selector, prefix, commands)
    if scout_portable.windows():
        found = installed_elsewhere(selector)
        if found:
            print(f"{prefix}_NOT_IN_THIS_WINDOW (found at {found}; {NOT_IN_THIS_WINDOW})")
        else:
            print(f"{prefix}_MISSING (install it with: {WINDOWS_INSTALL[selector]})")
        return 1
    return install(selector, tool, prefix)


if __name__ == "__main__":
    scout_portable.utf8_output()
    raise SystemExit(main(sys.argv))
