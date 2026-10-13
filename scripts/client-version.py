#!/usr/bin/env python3
"""Read the active Claude client's version without updating it."""
from __future__ import annotations

import os
import stat
import sys
import re

FLOOR = (2, 1, 293)
VERSION = re.compile(r"([0-9]+)\.([0-9]+)\.([0-9]+)(?: \(Claude Code\))?")


def active_host() -> str:
    # Keep this lightweight startup path equivalent to setup-mcp-status.py;
    # a parity test guards it without importing that helper's CLI dependencies.
    selected = os.environ.get('SCOUT_HOST')
    if selected is not None:
        return selected if selected in {'claude', 'codex'} else 'unknown'
    codex, claude = bool(os.environ.get('CODEX_THREAD_ID')), os.environ.get('CLAUDECODE') == '1'
    return 'unknown' if codex == claude else 'codex' if codex else 'claude'


def fingerprint(executable: str) -> list:
    path = os.path.realpath(executable)
    info = os.stat(path)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('not a regular client binary')
    return [path, info.st_mtime_ns, info.st_size]


def cache_path() -> str:
    data = os.environ.get('CLAUDE_PLUGIN_DATA', '')
    return os.path.join(data, 'scout-client-versions.txt') if os.path.isabs(data) else ''


def read_cache(path: str) -> list:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 16384:
                return []
            lines = stream.read(16385).decode('utf-8').splitlines()
        if not lines or lines[0] != 'scout-client-versions-v1' or (len(lines)-1) % 4 or len(lines) > 65:
            return []
        records = []
        for offset in range(1, len(lines), 4):
            binary, mtime, size, version = lines[offset:offset+4]
            if (not os.path.isabs(binary) or not re.fullmatch(r'[0-9]{1,24}', mtime)
                    or not re.fullmatch(r'[0-9]{1,24}', size)
                    or not re.fullmatch(r'[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}', version)):
                return []
            records.append({'key': [binary, int(mtime), int(size)], 'version': version})
        return records
    except (OSError, ValueError, TypeError, KeyError):
        return []


def write_cache(path: str, records: list, key: list, version: str) -> None:
    if not path:
        return
    temporary = None
    try:
        import tempfile
        parent = os.path.dirname(path)
        os.makedirs(parent, mode=0o700, exist_ok=True)
        info = os.lstat(parent)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or os.path.islink(path):
            return
        records = [r for r in records if r['key'][0] != key[0]][-15:]
        records.append({'key': key, 'version': version})
        if any('\n' in r['key'][0] or '\r' in r['key'][0] for r in records):
            return
        content = ('scout-client-versions-v1\n' + ''.join(
            '\n'.join(map(str, [*r['key'], r['version']])) + '\n' for r in records)).encode()
        if len(content) > 16384:
            return
        descriptor, temporary = tempfile.mkstemp(prefix='.scout-client-', dir=parent)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
        os.replace(temporary, path)
    except (OSError, ValueError, TypeError, KeyError):
        pass  # A cache is optional; never discard a successful probe for it.
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def observe() -> dict[str, str]:
    if active_host() != 'claude':
        return {'reason': 'not a Claude session'}
    entry = os.environ.get('CLAUDE_CODE_ENTRYPOINT', '')
    kind = ('desktop' if 'desktop' in entry else 'IDE' if 'vscode' in entry or 'jetbrains' in entry
            else 'terminal' if entry == 'cli' else 'Claude Code')
    executable = os.environ.get('CLAUDE_CODE_EXECPATH', '')
    source = 'CLAUDE_CODE_EXECPATH'
    if not executable and kind == 'terminal':
        import shutil
        executable = shutil.which('claude') or ''
        source = 'terminal PATH'
    if not executable or not os.path.isabs(executable):
        return {'reason': 'running client not identified; PATH is used only for an identified terminal session'}
    observation = dict(executable=executable, source=source, kind=kind)
    path, key, records = cache_path(), None, []
    try:
        key = fingerprint(executable)
        records = read_cache(path) if path else []
        for item in records:
            if item['key'] == key:
                return dict(observation, version=item['version'])
    except (OSError, ValueError):
        pass
    import signal
    import subprocess
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
        version = '.'.join(match.groups())
        if key is not None:
            try:
                if key == fingerprint(executable):
                    write_cache(path, records, key, version)
            except (OSError, ValueError):
                pass
        return dict(observation, version=version)
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
    elif npm_owned and os.path.realpath(npm_owned) == os.path.realpath(observation['executable']):
        remedy = 'Use the npm installation’s update path, then restart the session.'
    else:
        remedy = 'Use this client’s installer/updater (claude update for a native install), then restart the session.'
    different = (' Setup updated a different CLI binary; this client was not updated.'
                 if updated and os.path.realpath(updated) != os.path.realpath(observation['executable']) else '')
    return f"Scout needs Claude Code 2.1.293+ for the 5.5 models; this {kind} client binary reports {version}. {remedy}{different}"


def main() -> None:
    if sys.argv[1:] == ['floor']:
        line = floor_line(observe())
        if line:
            print(line)
        return
    import argparse
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
