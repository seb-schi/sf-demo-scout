#!/usr/bin/env python3
"""Read-only model routing inventory. Never execute shell configuration."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import shutil
import stat
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PROVIDERS = {'CLAUDE_CODE_USE_BEDROCK': 'bedrock', 'CLAUDE_CODE_USE_VERTEX': 'vertex',
             'CLAUDE_CODE_USE_FOUNDRY': 'foundry', 'CLAUDE_CODE_USE_ANTHROPIC_AWS': 'aws'}
KEYS = ('ANTHROPIC_MODEL', 'ANTHROPIC_DEFAULT_MODEL', 'ANTHROPIC_SMALL_FAST_MODEL',
        'CLAUDE_CODE_SUBAGENT_MODEL', 'CLAUDE_CODE_SUBAGENT_MODEL_FORCE',
        *(f'ANTHROPIC_DEFAULT_{family}_MODEL' for family in ('OPUS', 'SONNET', 'HAIKU')))
DEFAULTS = {'api': ('5.5', '5.5', '5.5'), 'bedrock': ('5.5', '4.5', '4.5'),
            'vertex': ('5.5', '4.5', '4.5'), 'foundry': ('4.6', '4.5', '4.5'),
            'aws': ('5.5', '4.6', '4.5')}
ALIASES = {'opus': 'opus', 'sonnet': 'sonnet', 'haiku': 'haiku', 'opusplan': 'sonnet'}
MODEL = re.compile(r'(?:(?:[a-z]+\.)?anthropic\.)?claude-(?:(opus|sonnet|haiku)-(\d+)(?:[-.](\d{1,2})(?!\d))?|(\d+)(?:[-.](\d{1,2})(?!\d))?-(opus|sonnet|haiku))(?:-\d{8})?(?:-v\d+:\d+|@\d{8})?(?:\[1m\])?')


def classify(value: object, provider: str = 'unknown', pinned: bool = False) -> tuple[str, str, str]:
    if not isinstance(value, str) or not value:
        return 'unknown', '', ''
    if value.startswith('arn:'):
        return 'ARN', '', ''
    if provider == 'foundry' and pinned:
        return 'unknown', '', ''
    alias = value.removesuffix('[1m]')
    if alias in ALIASES:
        return 'alias', ALIASES[alias], ''
    if provider == 'foundry':
        return 'unknown', '', ''  # Deployment names are not model IDs.
    match = MODEL.fullmatch(value)
    if not match:
        return 'unknown', '', ''
    family, major, minor, old_major, old_minor, old_family = match.groups()
    family, major, minor = (family, major, minor) if family else (old_family, old_major, old_minor)
    version = (int(major), int(minor or 0))
    return ('5.5+' if version >= (5, 5) else 'pre-5.5'), family, f'{version[0]}.{version[1]}'


def provider_from(environment: dict) -> str:
    if environment.get('CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST'):
        return 'unknown'
    enabled = [name for key, name in PROVIDERS.items() if str(environment.get(key, '')).lower() in {'1', 'true'}]
    if len(enabled) == 1:
        return enabled[0]
    if enabled or environment.get('CLAUDE_CODE_USE_MANTLE') or environment.get('CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST'):
        return 'unknown'
    endpoint = environment.get('ANTHROPIC_BASE_URL', '')
    if endpoint and endpoint.rstrip('/') != 'https://api.anthropic.com':
        return 'unknown'
    return 'api' if environment.get('ANTHROPIC_API_KEY') or endpoint else 'unknown'


def read_text(path: Path) -> str:
    # Nonblocking open avoids hanging on a FIFO (Windows has neither, so the flag is 0 there); binary mode keeps the
    # bytes as they are on Windows too; bounded reads avoid huge inputs.
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0))
    with os.fdopen(descriptor, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('not a regular file')
        content = stream.read(1024 * 1024 + 1)
    if len(content) > 1024 * 1024:
        raise ValueError('input too large')
    return content.decode('utf-8')


def collect(home: Path, project: Path, managed: Path, vscode: Path, zshrc: Path) -> tuple[list[dict], str, bool]:
    rows, failed, environments = [], False, []
    def add(surface: str, kind: str, key: str, value: object) -> None:
        if key in KEYS or key == 'model' or re.fullmatch(r'ANTHROPIC_DEFAULT_[A-Z]+_MODEL', key):
            rows.append(dict(surface=surface, kind=kind, key=key, value=value))
    paths = [(home / '.claude/settings.json', 'user'), (home / '.claude/settings.local.json', 'other'),
             (project / '.claude/settings.json', 'other'), (project / '.claude/settings.local.json', 'other'),
             (managed, 'managed'), (vscode, 'vscode')]
    seen = set()
    for path, kind in paths:
        if str(path) in seen:
            continue
        seen.add(str(path))
        try:
            content = read_text(path)
            if kind == 'vscode':
                data = runpy.run_path(str(HERE / 'setup-settings.py'))['parse_jsonc'](content.encode())[1].value
                env = {}
                for entry in data.get('claudeCode.environmentVariables', []):
                    if isinstance(entry, dict) and isinstance(entry.get('name'), str) and 'value' in entry:
                        add(str(path), kind, entry['name'], entry['value'])
                        env[entry['name']] = entry['value']
            else:
                data = runpy.run_path(str(HERE / 'setup-settings.py'))['load_strict_json'](content.encode())
                env = data.get('env', {})
                if 'model' in data:
                    add(str(path), kind, 'model', data['model'])
            if not isinstance(env, dict):
                raise ValueError('invalid env')
            if kind != 'vscode':
                for key, value in env.items():
                    add(str(path), kind, key, value)
            if kind not in {'vscode', 'other'} or path == project / '.claude/settings.local.json' or path == project / '.claude/settings.json':
                environments.append(env)
        except FileNotFoundError:
            pass
        except Exception:
            failed = True  # Never print parser errors which might quote credentials.
    try:
        for number, line in enumerate(read_text(zshrc).splitlines(), 1):
            match = re.match(r'^\s*(?:export\s+)?([A-Z_][A-Z_0-9]*)=(.*)$', line)
            if not match:
                continue
            key, value = match.groups()
            try:
                tokens = shlex.split(value, comments=True)
                value = tokens[0] if len(tokens) == 1 and not any(c in value for c in '$`;|&') else None
            except ValueError:
                value = None
            add(f'{zshrc}:{number}', 'shell', key, value)
    except FileNotFoundError:
        pass
    except (OSError, UnicodeError, ValueError):
        failed = True
    launchctl = shutil.which('launchctl') if sys.platform == 'darwin' else None
    if launchctl:
        for key in KEYS:
            try:
                result = subprocess.run([launchctl, 'getenv', key], capture_output=True, text=True, timeout=1, check=False)
                if result.returncode == 0 and result.stdout.strip():
                    add('launchctl', 'shell', key, result.stdout.strip())
            except (OSError, UnicodeError, subprocess.SubprocessError):
                failed = True
    # Claude injects settings env into its process. A matching value is not a
    # second source; wait until shell/launchctl sources have also been read.
    for key, value in os.environ.items():
        if not any(row['key'] == key and row['value'] == value for row in rows):
            add('session environment, set outside the files Scout read (shell profile, launch agent or host app)',
                'shell', key, value)
    effective = {}
    for env in environments:
        effective.update(env)
    # The launch environment is authoritative for host-managed sessions. If it
    # supplies provider flags, use it; don't infer routing from dormant shell text.
    effective.update(os.environ)
    return rows, provider_from(effective), failed


def fix(row: dict, provider: str, family: str) -> str:
    kind, key = row['kind'], row['key']
    if kind == 'managed':
        return 'Ask whoever manages this setting.'
    where = ('Remove it at this source first; a user-settings fix is not a reliable override. '
             if kind in {'shell', 'vscode'} else 'Change this file/key; user-settings wizards do not override project/local settings or a specific model key. '
             if kind != 'user' or key == 'model' else '')
    if key == 'CLAUDE_CODE_SUBAGENT_MODEL':
        advice = 'Remove this override at its source to let agents use the session model.'
        if provider in {'bedrock', 'vertex'} and classify(row['value'])[0] == 'alias':
            advice += ' Alternatively reopen ' + ('/setup-bedrock' if provider == 'bedrock' else '/setup-vertex') + ' to configure that alias.'
        return where + advice
    if provider in {'bedrock', 'vertex'}:
        wizard = '/setup-bedrock' if provider == 'bedrock' else '/setup-vertex'
        advice = f'Reopen {wizard} to configure the alias in user settings.'
        if family == 'opus' and kind == 'user' and key in {'ANTHROPIC_DEFAULT_OPUS_MODEL', 'ANTHROPIC_MODEL'}:
            advice += ' Or accept the startup pin-update prompt if your account can use the newer default.'
    elif provider == 'api':
        advice = 'Remove the pin at its source; with no pin the API alias uses the 5.5 model on a current client.'
    elif provider in {'foundry', 'aws'}:
        advice = 'Ask whoever provisions the deployment (or update your own configuration) to change the model mapping at its source and redeploy; no startup prompt offers this change.'
    else:
        advice = 'Provider undetermined; check this setting with its owner before changing routing.'
    return where + advice


def report(rows: list[dict], provider: str, failed: bool = False) -> list[str]:
    lines, uncertain = [], failed
    forced = any(row['key'] == 'CLAUDE_CODE_SUBAGENT_MODEL_FORCE' and row['value'] == '1' for row in rows)
    pins = {row['key'] for row in rows if row['key'].startswith('ANTHROPIC_DEFAULT_') and row['value']
            and classify(row['value'], provider, pinned=True)[0] != 'alias'}
    for row in rows:
        key = row['key']
        if key.endswith('_FORCE') or row['value'] == 'inherit':
            continue
        classification, family, version = classify(row['value'], provider, key.startswith('ANTHROPIC_DEFAULT_'))
        uncertain |= classification in {'unknown', 'ARN'}
        if classification == 'alias':
            if f'ANTHROPIC_DEFAULT_{family.upper()}_MODEL' in pins or provider not in DEFAULTS:
                continue
            version = DEFAULTS[provider][('opus', 'sonnet', 'haiku').index(family)]
            if tuple(map(int, version.split('.'))) >= (5, 5):
                continue
        elif classification != 'pre-5.5':
            continue
        impact = (f'Scout workers use {family.title()} {version} instead of the session model when the forced override is effective'
                  if key == 'CLAUDE_CODE_SUBAGENT_MODEL' and forced else
                  f'other agents that set no model use {family.title()} {version}; Scout workers follow the session'
                  if key == 'CLAUDE_CODE_SUBAGENT_MODEL' else f'this setting selects {family.title()} {version} when effective')
        # Values are never echoed: this also prevents full ARN / arbitrary text leakage.
        lines.append(f"Model routing: {key} at {row['surface']}: {impact}. {fix(row, provider, family)}")
    sonnet_pins = [row for row in rows if row['key'] == 'ANTHROPIC_DEFAULT_SONNET_MODEL' and row['value']]
    if provider in {'bedrock', 'vertex'} and not any(
            row['kind'] in {'user', 'managed'} or row['surface'] == 'launchctl' for row in sonnet_pins):
        wizard = '/setup-bedrock' if provider == 'bedrock' else '/setup-vertex'
        sources = '; '.join(dict.fromkeys(row['surface'] for row in sonnet_pins))
        limited = (f'A Sonnet pin was read at {sources}; sessions started without it can still resolve sonnet to 4.5. '
                   if sources else '')
        lines.append('Model routing advisory: with no Sonnet pin read in user settings, managed settings or launchctl, '
                     'the sonnet alias resolves to Sonnet 4.5 '
                     'unless the session starts on a specific Sonnet version, so a host’s default worker '
                     'under an Opus session gets 4.5. '
                     f'{limited}Reopen {wizard} to pin Sonnet 5.5.')
    return lines or [('Model routing preserved; some values or sources could not be assessed; no recognized below-5.5 routing found.'
                      if uncertain or provider == 'unknown' else 'Model routing preserved; no below-5.5 routing found in the inspected sources.')]


def default_managed(platform: str = sys.platform) -> Path:
    """Claude Code's managed settings file where its docs place it: https://code.claude.com/docs/en/managed-settings
    (Windows no longer reads the older C:\\ProgramData\\ClaudeCode path)."""
    if platform == 'darwin':
        return Path('/Library/Application Support/ClaudeCode/managed-settings.json')
    if platform == 'win32':
        return Path('C:\\Program Files\\ClaudeCode\\managed-settings.json')
    return Path('/etc/claude-code/managed-settings.json')


def default_vscode(home: Path, platform: str = sys.platform) -> Path:
    """VS Code's user settings file where its docs place it: https://code.visualstudio.com/docs/configure/settings"""
    if platform == 'darwin':
        return home / 'Library/Application Support/Code/User/settings.json'
    if platform == 'win32':
        roaming = os.environ.get('APPDATA')
        return (Path(roaming) if roaming else home / 'AppData' / 'Roaming') / 'Code' / 'User' / 'settings.json'
    return home / '.config/Code/User/settings.json'


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # the report's lines and paths, the same everywhere
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument('--managed', type=Path, default=default_managed())
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--vscode', type=Path)
    parser.add_argument('--zshrc', type=Path)
    args = parser.parse_args()
    if runpy.run_path(str(HERE / 'setup-mcp-status.py'))['active_host']() != 'claude':
        return
    home = Path.home()
    rows, provider, failed = collect(home, args.project, args.managed, args.vscode or default_vscode(home),
                                     args.zshrc or home / '.zshrc')
    print('\n'.join(report(rows, provider, failed)))


if __name__ == '__main__':
    main()
