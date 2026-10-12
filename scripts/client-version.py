#!/usr/bin/env python3
"""Read the active Claude client's version without updating it."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import runpy
import shutil
import signal
import subprocess

FLOOR = (2, 1, 293)
VERSION = re.compile(r"([0-9]+)\.([0-9]+)\.([0-9]+)(?: \(Claude Code\))?")


def active_host() -> str:
    return runpy.run_path(str(Path(__file__).with_name('setup-mcp-status.py')))["active_host"]()


def observe() -> dict[str, str]:
    if active_host() != 'claude':
        return {'reason': 'not a Claude session'}
    entry = os.environ.get('CLAUDE_CODE_ENTRYPOINT', '')
    kind = ('desktop' if 'desktop' in entry else 'IDE' if entry in
            {'vscode', 'jetbrains', 'ide'} else 'terminal' if entry in
            {'cli', 'terminal'} else 'unidentified host')
    executable = os.environ.get('CLAUDE_CODE_EXECPATH', '')
    source = 'CLAUDE_CODE_EXECPATH'
    if not executable and kind == 'terminal':
        executable = shutil.which('claude') or ''
        source = 'terminal PATH'
    if not executable or not Path(executable).is_absolute():
        return {'reason': 'running client not identified; PATH is used only for an identified terminal session'}
    try:
        with subprocess.Popen([executable, '--version'], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              start_new_session=True) as process:
            try:
                output, _ = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                return {'reason': 'running client version probe exceeded 2 seconds'}
        match = VERSION.fullmatch(output.decode('utf-8').strip())
        if process.returncode or not match:
            return {'reason': 'running client returned no supported version'}
        return {'version': '.'.join(match.groups()), 'executable': executable,
                'source': source, 'kind': kind}
    except (OSError, UnicodeError, subprocess.SubprocessError):
        return {'reason': 'running client binary unavailable'}


def floor_line(observation: dict[str, str], npm_owned: str = '', updated: str = '') -> str:
    version = observation.get('version')
    if not version or tuple(map(int, version.split('.'))) >= FLOOR:
        return ''
    kind = observation['kind']
    if kind == 'desktop':
        remedy = 'Update the Claude desktop app and restart the session.'
    elif kind == 'IDE':
        remedy = 'Update the Claude Code extension in your IDE and restart the session.'
    elif npm_owned and Path(npm_owned).resolve() == Path(observation['executable']).resolve():
        remedy = 'Use the npm installation’s update path, then restart the session.'
    else:
        remedy = 'Use this client’s installer/updater (claude update for a native install), then restart the session.'
    different = (' Setup updated a different CLI binary; this client was not updated.'
                 if updated and Path(updated).resolve() != Path(observation['executable']).resolve() else '')
    return f"Scout needs Claude Code 2.1.293+ for the 5.5 models; this {kind} client binary reports {version}. {remedy}{different}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('setup', 'floor'))
    parser.add_argument('--npm-owned', default='')
    parser.add_argument('--updated', default='')
    args = parser.parse_args()
    if active_host() != 'claude':
        return
    observation = observe()
    if args.mode == 'setup':
        print('Running Claude client binary: ' + (observation['version'] + ' (' + observation['source'] + ')'
              if 'version' in observation else 'unverified — ' + observation['reason']))
    line = floor_line(observation, args.npm_owned, args.updated)
    if line:
        print(line)


if __name__ == '__main__':
    main()
