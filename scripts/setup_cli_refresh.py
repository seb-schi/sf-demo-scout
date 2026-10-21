#!/usr/bin/env python3
"""Update the global Salesforce CLI only when this npm provably owns it and it's behind: setup_cli_refresh.py sf

It prints the outcome lines setup's done message reads (SF_CLI_CURRENT, SF_CLI_UPDATED, ...) and exits 0 for
every outcome; a bad selector exits 64 before any CLI or npm call.
"""
from __future__ import annotations

import os
import re
import runpy
import subprocess
import sys
from typing import List, Optional, Tuple

sys.dont_write_bytecode = True
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import scout_portable  # noqa: E402

OWNER_HELPER = os.path.join(SCRIPT_DIR, "setup-cli-owner.py")
VERSION_LINE = re.compile(r"@salesforce/cli/([0-9]+\.[0-9]+\.[0-9]+)([ \t\r\f\v].*)?")
RESOLVE_LINE = re.compile(r"(?:add|change)[ \t\r\f\v]+@salesforce/cli[ \t\r\f\v]+([0-9]+\.[0-9]+\.[0-9]+)"
                          r"[ \t\r\f\v]*=>[ \t\r\f\v]*([0-9]+\.[0-9]+\.[0-9]+)[ \t\r\f\v]*")


def status(code: int) -> int:
    return 128 - code if code < 0 else code  # a signal's number, the way the shell reported it


def run(command: List[str]) -> Tuple[int, str]:
    """A command's exit status and stdout, as the shell's $(...) captured it; stderr is discarded."""
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    except OSError as error:
        return scout_portable.exec_status(error), ""
    except (ValueError, subprocess.SubprocessError):
        return 127, ""
    return status(result.returncode), result.stdout.decode("utf-8", "replace").rstrip("\n")


def matches(pattern, output: str) -> List[Tuple[str, ...]]:
    """Every line of `output` the pattern matches in full, like `sed -n 's/.../p'`."""
    return [match.groups() for match in map(pattern.fullmatch, output.split("\n")) if match]


def installed_version(cli: List[str]) -> Tuple[int, str]:
    """The CLI's own `--version` report, trusted only from a zero exit with exactly one supported line."""
    code, output = run(cli + ["--version"])
    versions = [groups[0] for groups in matches(VERSION_LINE, output)]
    return code, versions[0] if code == 0 and len(versions) == 1 else ""


def windows_installer(cli: Optional[str]) -> bool:
    """Whether the active `sf` is the launcher Salesforce's Windows installer writes, in a folder with a space, such
    as C:\\Program Files\\sf\\bin\\sf.cmd.

    cmd.exe drops the first and the last quote of a command line with more than two, so whenever another argument is
    quoted it cuts that path at the space, and a coding tool's own `sf` call fails with 'C:\\Program' is not
    recognized. Scout's own calls start the CLI's Node script instead (scout_portable.sf_argv), so they still work.
    npm's own shim never counts, wherever it lives."""
    if not (scout_portable.windows() and cli and " " in cli and cli.lower().endswith(scout_portable.BATCH_SUFFIXES)):
        return False
    if scout_portable.NPM_ENTRY.search(scout_portable._batch_text(cli)):
        return False
    return scout_portable._installer_entry(cli) is not None


def ownership(npm: Optional[str], cli: Optional[str]) -> str:
    if npm is None or cli is None or not os.path.isfile(OWNER_HELPER):
        return "unavailable"
    try:
        return str(runpy.run_path(OWNER_HELPER, run_name="scout_cli_owner")["npm_ownership"]("sf", npm, cli))
    except (Exception, SystemExit):
        return "unavailable"


def last_line(output: bytes) -> bytes:
    """What `tail -1` prints: the last line, with its newline when it has one."""
    if not output:
        return b""
    body, newline = (output[:-1], b"\n") if output.endswith(b"\n") else (output, b"")
    return body.rsplit(b"\n", 1)[-1] + newline


def main(argv: List[str]) -> int:
    if (argv[1] if len(argv) > 1 else "") != "sf":
        print("usage: setup_cli_refresh.py sf", file=sys.stderr)
        return 64
    npm, cli_path = scout_portable.shell_which("npm"), scout_portable.shell_which("sf")
    owner = ownership(npm, cli_path)
    if owner != "owned":
        if windows_installer(cli_path):
            print(f"SF_CLI_WINDOWS_INSTALLER ({cli_path}; the Windows installer's copy, whose launcher breaks when an "
                  "argument is quoted; skipped update)")
        elif owner == "different":
            print("SF_CLI_NOT_NPM_OWNED (active executable belongs to another installation; skipped update)")
        else:
            print("SF_CLI_OWNERSHIP_UNVERIFIED (npm ownership could not be proved; skipped update)")
        return 0
    print("CHECKING_SF_CLI", flush=True)
    cli, npm_command = scout_portable.sf_argv(cli_path), [npm]
    # Gate on what npm would actually install here, not on `npm view` latest: `npm view` ignores the builder's
    # ~/.npmrc min-release-age policy, so comparing against it would report "behind" whenever the newest
    # release is younger than the policy window. The dry-run resolve ("X => Y") honors that policy. Skipping
    # the reinstall when already on the newest installable version keeps the CLI's keychain-backed org logins
    # away from a needless Node rebuild, which would leave the builder with an empty org list.
    _, installed = installed_version(cli)
    resolved_from = resolved = ""
    if installed:
        code, output = run(npm_command + ["install", "@salesforce/cli", "--global", "--dry-run"])
        transitions = matches(RESOLVE_LINE, output)
        if code == 0 and len(transitions) == 1:
            resolved_from, resolved = transitions[0]
    if resolved_from != installed:
        resolved = ""
    registry = ""
    if installed and resolved:
        registry = run(npm_command + ["view", "@salesforce/cli", "version"])[1]
    if not installed or not resolved:
        print(f"SF_CLI_CHECK_FAILED (offline or npm probe failed) — kept installed: {installed or 'unknown'}")
        return 0
    if installed == resolved:
        if registry and resolved != registry:
            print(f"SF_CLI_HELD (installed {installed}; registry {registry} held by your npm min-release-age policy)")
        else:
            print(f"SF_CLI_CURRENT ({installed})")
        return 0
    print(f"UPDATING_SF_CLI ({installed} -> {resolved})", flush=True)
    # Capture the installer's own exit status, never a pipe's, and show only the last line of its log.
    try:
        result = subprocess.run(npm_command + ["install", "@salesforce/cli", "--global"], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        code, log = status(result.returncode), result.stdout
    except OSError as error:
        code, log = scout_portable.exec_status(error), b""
    except (ValueError, subprocess.SubprocessError):
        code, log = 127, b""
    sys.stdout.buffer.write(last_line(log))
    sys.stdout.buffer.flush()
    # The version probe's output and exit status count separately: a probe that exits nonzero isn't trusted
    # even when it prints a version, and only a supported `@salesforce/cli/<semver>` line is read.
    after_code, after_output = run(cli + ["--version"])
    after = "\n".join(groups[0] for groups in matches(VERSION_LINE, after_output)) if after_code == 0 else ""
    if code != 0:
        # A failed install is a failure whatever the probe says, and never a promise the old one survived.
        if after:
            print(f"SF_CLI_UPDATE_FAILED (npm exit {code}; version now reports {after} — install may be partially "
                  "applied)")
        else:
            print(f"SF_CLI_UPDATE_FAILED (npm exit {code}; post-install version could not be verified)")
    elif after_code != 0 or not after:
        print("SF_CLI_UPDATE_UNVERIFIED (install exit 0 but the version probe failed or returned no supported version)")
    elif after == resolved:
        print(f"SF_CLI_UPDATED ({installed} -> {after})")
    elif after == installed:
        print(f"SF_CLI_UPDATE_NOOP (install exit 0 but version unchanged — still {after})")
    else:
        print(f"SF_CLI_UPDATE_MISMATCH (install exit 0; observed {after}, expected {resolved})")
    return 0


if __name__ == "__main__":
    scout_portable.utf8_output()
    raise SystemExit(main(sys.argv))
