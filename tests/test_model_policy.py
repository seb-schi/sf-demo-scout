"""Offline routing-preservation, provider-remedy and running-client regressions."""
from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import stand_ins

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


REPORT = module('model_report', ROOT / 'scripts/setup-model-report.py')
CLIENT = module('client_version', ROOT / 'scripts/client-version.py')
STARTUP = module('startup_fixture_policy', ROOT / 'tests/test_startup.py')
PIN = 'ANTHROPIC_DEFAULT_SONNET_MODEL'
ARN = 'arn:aws:bedrock:us-east-1:123456789012:application-inference-profile/synthetic'
VALUES = {'5.5+': 'claude-sonnet-5-5', 'pre-5.5': 'claude-sonnet-4-6',
          'ARN': ARN, 'alias': 'sonnet', 'unknown': 'claude-fable-5-1', 'absent': None}


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='scout-policy-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / 'home'
        self.home.mkdir()
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        if not stand_ins.WINDOWS:  # for the bash fences; the tests that run them don't run on Windows
            (self.bin / 'python3').symlink_to(sys.executable)
        self.script('launchctl', 'exit 0\n')
        self.environment = stand_ins.keep({**stand_ins.home(self.home),
                                           'PATH': os.pathsep.join((str(self.bin), '/usr/bin', '/bin')),
                                           'SCOUT_HOST': 'claude', 'CLAUDE_CODE_USE_BEDROCK': '1',
                                           'PYTHONDONTWRITEBYTECODE': '1', 'CLAUDE_CONFIG_DIR': str(self.home / '.claude')})
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, self.environment, clear=True).start()

    def script(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/bash\n' + body)
        path.chmod(0o700)
        return path

    def client(self, name, output='', code=0, sleep=0, log=None, note='call'):
        """A stand-in for a Claude Code binary: it adds `note` to `log`, waits `sleep` seconds, prints `output` and
        exits with `code`, on any platform."""
        lines = ['import sys']
        if log is not None:
            lines.append('with open(%r, "a") as calls:\n    calls.write(%r)' % (str(log), note + '\n'))
        if sleep:
            lines += ['import time', 'time.sleep(%r)' % sleep]
        if output:
            lines.append('print(%r)' % output)
        lines.append('sys.exit(%d)' % code)
        return stand_ins.tool(self.bin, name, '\n'.join(lines) + '\n')

    def collect(self, home):
        return REPORT.collect(home, home / 'project', home / 'managed.json', home / 'vscode.json', home / '.zshrc')

    def test_classification_id_grammars_unknown_families_and_arns(self):
        for value, expected in [('claude-3-5-sonnet-20241022', 'pre-5.5'),
                                ('anthropic.claude-haiku-4-5-20251001-v1:0', 'pre-5.5'),
                                ('eu.anthropic.claude-opus-5-5[1m]', '5.5+'),
                                ('claude-opus-6', '5.5+'), ('claude-sonnet-5', 'pre-5.5'),
                                ('claude-sonnet-4-5@20250929', 'pre-5.5'),
                                ('claude-fable-5-1', 'unknown'), ('claude-sonnet-4-6-garbage', 'unknown'),
                                (ARN, 'ARN'), ('opusplan', 'alias'), ('sonnet[1m]', 'alias')]:
            with self.subTest(value=value):
                self.assertEqual(REPORT.classify(value)[0], expected)
        self.assertEqual(REPORT.classify('sonnet', 'foundry', pinned=True)[0], 'unknown')

    def test_surface_value_matrix_is_reported_read_only(self):
        # Setup edits none of these sources since 2.4; the report reads them and leaves every byte as it was.
        surfaces = ('user', 'local', 'vscode', 'launchctl', 'zsh-inside', 'zsh-outside', 'model', 'managed',
                    'session', 'project', 'project-local')
        legacy_block = ('# BEGIN SF-DEMO-SCOUT\n# Managed by Scout plugin — do not edit. Refreshed on first-run setup.\n'
                        '# END SF-DEMO-SCOUT\n')  # what a pre-2.4 Scout left in ~/.zshrc
        count = 0
        for surface in surfaces:
            for classification, value in VALUES.items():
                with self.subTest(surface=surface, classification=classification):
                    case = self.base / f'{surface}-{classification}'
                    case.mkdir()
                    if surface == 'session' and classification == '5.5+':
                        value = 'us.anthropic.claude-sonnet-5-5'  # F7 replay.
                    paths = {'user': case / '.claude/settings.json', 'local': case / '.claude/settings.local.json',
                             'project': case / 'project/.claude/settings.json',
                             'project-local': case / 'project/.claude/settings.local.json',
                             'model': case / '.claude/settings.json', 'managed': case / 'managed.json',
                             'vscode': case / 'vscode.json', 'zsh-inside': case / '.zshrc', 'zsh-outside': case / '.zshrc'}
                    key = 'model' if surface == 'model' else PIN
                    env = {} if value is None else {PIN: value}
                    path = paths.get(surface)
                    os.environ.pop(PIN, None)
                    self.script('launchctl', 'exit 0\n')
                    if surface == 'session':
                        os.environ.update(env)
                    elif surface == 'launchctl':
                        if sys.platform != 'darwin':
                            self.skipTest('the report reads launchctl only on macOS')
                        self.script('launchctl', f'if [ "$1 $2" = "getenv {PIN}" ]; then printf "%s\\n" {shlex_quote(value or "")}; fi\n')
                        path = self.bin / 'launchctl'
                    else:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        if surface.startswith('zsh'):
                            assignment = '' if value is None else f'export {PIN}="{value}"\n'
                            block = legacy_block
                            body = block.replace('# BEGIN SF-DEMO-SCOUT\n', '# BEGIN SF-DEMO-SCOUT\n'+assignment) if surface == 'zsh-inside' else assignment + block
                        elif surface == 'vscode':
                            body = json.dumps({'claudeCode.environmentVariables': [{'name': k, 'value': v} for k, v in env.items()]})
                        else:
                            body = json.dumps(({} if value is None else {'model': value}) if surface == 'model' else {'env': env})
                        path.write_text(body)
                    before = path.read_bytes() if path else None
                    rows, provider, failed = self.collect(case)
                    # A real Claude process also contains settings env.
                    if key != 'model' and value is not None:
                        with patch.dict(os.environ, {key: value}):
                            injected, injected_provider, injected_failed = self.collect(case)
                        self.assertEqual(injected, rows)
                        self.assertEqual((injected_provider, injected_failed), (provider, failed))
                    matching = [r for r in rows if r['key'] == key]
                    if value is not None:
                        self.assertEqual(REPORT.classify(matching[0]['value'], provider)[0], classification)
                    else:
                        self.assertEqual(matching, [])
                    output = '\n'.join(REPORT.report(rows, provider, failed))
                    self.assertEqual(path.read_bytes() if path else None, before)
                    self.assertNotIn(ARN, output)
                    advisory = value is None or surface not in {'user', 'managed', 'launchctl'}
                    self.assertEqual('Model routing advisory:' in output, advisory)
                    if advisory and value is not None and key == PIN:
                        self.assertIn('A Sonnet pin was read at '+matching[0]['surface'], output)
                        self.assertIn('sessions started without it can still resolve sonnet to 4.5', output)
                        self.assertIn('/setup-bedrock', output)
                    if value is not None and classification != 'alias':
                        self.assertNotIn(value, output)
                    if classification in {'pre-5.5', 'alias'}:
                        self.assertIn(key, output)
                        self.assertIn('Ask whoever manages', output) if surface == 'managed' else self.assertIn('/setup-bedrock', output)
                        if surface in {'zsh-inside', 'zsh-outside', 'launchctl', 'vscode', 'session'}:
                            self.assertIn('source first', output)
                    else:
                        self.assertNotIn('Model routing:', output)
                    count += 1
        self.assertEqual(count, 66 if sys.platform == 'darwin' else 60)  # launchctl's six on macOS only

    def test_sonnet_advisory_multiple_sources_and_host_wide_pin(self):
        value = 'us.anthropic.claude-sonnet-5-5'
        rows = [dict(kind=kind, surface=surface, key=PIN, value=value) for kind, surface in
                [('shell', 'session environment'), ('shell', '.zshrc:1'), ('vscode', 'vscode.json'),
                 ('other', 'project/.claude/settings.json')]]
        for provider in ('bedrock', 'vertex'):
            output = '\n'.join(REPORT.report(rows, provider))
            for row in rows:
                self.assertIn(row['surface'], output)
            self.assertIn('sessions started without it can still resolve sonnet to 4.5', output)
            self.assertIn('/setup-'+provider, output)
            self.assertNotIn(value, output)
            for kind, surface in [('user', 'settings.json'), ('managed', 'managed.json'), ('shell', 'launchctl')]:
                shared = dict(kind=kind, surface=surface, key=PIN, value=value)
                self.assertEqual(REPORT.report(rows+[shared], provider),
                                 ['Model routing preserved; no below-5.5 routing found in the inspected sources.'])

    def test_provider_remedies_and_foundry_deployment_names(self):
        for provider in (*REPORT.DEFAULTS, 'unknown'):
            for key, value in [('ANTHROPIC_DEFAULT_OPUS_MODEL', 'claude-opus-4-8'),
                               (PIN, 'claude-sonnet-4-6'), ('model', 'sonnet'),
                               ('ANTHROPIC_DEFAULT_OPUS_MODEL', 'my-deployment')]:
                with self.subTest(provider=provider, key=key, value=value):
                    row = dict(kind='user', surface='settings.json', key=key, value=value)
                    output = '\n'.join(REPORT.report([row], provider))
                    if provider not in {'bedrock', 'vertex', 'foundry', 'aws'}:
                        self.assertNotIn('prompt', output)
                    if provider in {'bedrock', 'vertex'} and value != 'my-deployment':
                        self.assertIn('/setup-bedrock' if provider == 'bedrock' else '/setup-vertex', output)
                        self.assertEqual('pin-update prompt' in output, 'opus' in value)
                    if provider == 'foundry':
                        self.assertEqual('Model routing:' in output, key == 'model')
                        if key == 'model':
                            self.assertIn('no startup prompt', output)
                    if provider == 'api' and value.startswith('claude-'):
                        self.assertIn('Remove the pin at its source', output)
                    self.assertNotRegex(output, r'claude-(?:opus|sonnet|haiku)-[0-9]')
        alias = dict(kind='user', surface='settings.json', key='model', value='opus')
        deployment = dict(kind='user', surface='settings.json', key='ANTHROPIC_DEFAULT_OPUS_MODEL', value='sonnet')
        self.assertNotIn('Model routing:', '\n'.join(REPORT.report([alias, deployment], 'foundry')))
        mismatched = dict(kind='user', surface='settings.json', key=PIN, value='claude-opus-4-8')
        self.assertNotIn('pin-update prompt', '\n'.join(REPORT.report([mismatched], 'bedrock')))

    def test_provider_detection_flags_and_unknown_gateway(self):
        for key, expected in REPORT.PROVIDERS.items():
            self.assertEqual(REPORT.provider_from({key: '1'}), expected)
        self.assertEqual(REPORT.provider_from({'ANTHROPIC_API_KEY': 'synthetic'}), 'api')
        self.assertEqual(REPORT.provider_from({'ANTHROPIC_API_KEY': 'synthetic', 'ANTHROPIC_BASE_URL': 'https://example.invalid'}), 'unknown')
        self.assertEqual(REPORT.provider_from({'CLAUDE_CODE_USE_BEDROCK': '1', 'CLAUDE_CODE_USE_VERTEX': '1'}), 'unknown')

    def test_subagent_override_force_matrix_and_pinned_alias(self):
        for value in ('claude-sonnet-5-5', 'claude-sonnet-4-6', 'sonnet', 'opus', 'inherit', 'unrecognized', None):
            for force in (None, '1'):
                rows = [dict(kind='user', surface='settings.json', key=k, value=v) for k, v in
                        [('CLAUDE_CODE_SUBAGENT_MODEL', value), ('CLAUDE_CODE_SUBAGENT_MODEL_FORCE', force)] if v is not None]
                output = '\n'.join(REPORT.report(rows, 'bedrock'))
                self.assertEqual('Scout workers use' in output, force == '1' and value in {'claude-sonnet-4-6', 'sonnet'})
                self.assertEqual('other agents that set no model' in output, force is None and value in {'claude-sonnet-4-6', 'sonnet'})
                self.assertNotIn('_FORCE', output)
        alias = dict(kind='user', surface='settings.json', key='model', value='sonnet')
        self.assertIn('Sonnet 4.5', REPORT.report([alias], 'bedrock')[0])
        pin = dict(kind='user', surface='settings.json', key=PIN, value='claude-sonnet-5-5')
        self.assertNotIn('Sonnet 4.5', REPORT.report([alias, pin], 'bedrock')[0])

    def test_sonnet_advisory_qualifies_session_pin_and_new_settings_do_not_pin(self):
        session = dict(kind='user', surface='settings.json', key='model', value='claude-sonnet-5-5')
        for provider in ('bedrock', 'vertex'):
            output = '\n'.join(REPORT.report([session], provider))
            self.assertIn('unless the session starts on a specific Sonnet version', output)
            self.assertIn('under an Opus session gets 4.5', output)
        settings = json.loads((ROOT / 'assets/workspace-settings.template.json').read_text())
        self.assertNotIn('model', settings)

    def test_read_safety_jsonc_duplicates_dynamic_shell_and_codex(self):
        (self.home / 'vscode.json').write_text('{/*keep*/ "claudeCode.environmentVariables": ['
            '{"name":"'+PIN+'","value":"claude-sonnet-4-6"},'
            '{"name":"'+PIN+'","value":"claude-sonnet-5-5"},],}')
        marker = self.home / 'executed'
        (self.home / '.zshrc').write_text(f'export {PIN}=$(touch {marker})\n')
        rows, provider, failed = self.collect(self.home)
        self.assertFalse(marker.exists())
        self.assertEqual(len([row for row in rows if row['key'] == PIN]), 3)
        self.assertIn('Sonnet 4.6', '\n'.join(REPORT.report(rows, provider, failed)))
        (self.home / 'managed.json').write_text('{"password":"DO-NOT-ECHO", invalid')
        _, _, failed = self.collect(self.home)
        self.assertTrue(failed)
        os.environ['SCOUT_HOST'] = 'codex'
        completed = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/setup-model-report.py'), '--managed', str(self.home / 'managed.json')], capture_output=True, text=True, check=False)
        self.assertEqual((completed.returncode, completed.stdout, completed.stderr), (0, '', ''))

    def test_running_client_source_floor_and_timeout(self):
        self.client('claude', '2.1.300 (Claude Code)')
        running = self.client('running', '2.1.292 (Claude Code)')
        os.environ.update(CLAUDE_CODE_ENTRYPOINT='claude-desktop', CLAUDE_CODE_EXECPATH=str(running))
        observation = CLIENT.observe()
        self.assertEqual(observation['version'], '2.1.292')
        self.assertIn('desktop app', CLIENT.floor_line(observation))
        for version in ('2.1.279', '2.1.280', '2.1.292', '2.1.293'):
            observation['version'] = version
            self.assertEqual(bool(CLIENT.floor_line(observation)), version != '2.1.293')
        del os.environ['CLAUDE_CODE_EXECPATH']
        self.assertNotIn('version', CLIENT.observe())  # Desktop must not use PATH.
        os.environ['CLAUDE_CODE_ENTRYPOINT'] = 'cli'
        self.assertEqual(CLIENT.observe()['version'], '2.1.300')
        os.environ['CLAUDE_CODE_EXECPATH'] = str(running)
        limit = 5 if stand_ins.WINDOWS else 2  # the probe's own limit: a cold start takes longer on Windows
        for answer in ({'output': 'error near 2.1.279'}, {'output': '2.1.279', 'code': 2},
                       {'output': '2.1.279', 'sleep': limit + 2}):
            running = self.client('running', **answer)
            start = time.monotonic()
            self.assertNotIn('version', CLIENT.observe())
            self.assertLess(time.monotonic()-start, limit + 0.8)

    @unittest.skipIf(stand_ins.WINDOWS, 'runs the refresh fence with /bin/bash')
    def test_refresh_reports_each_floor_version_and_never_updates_the_client(self):
        refresh = (ROOT / 'prompts/setup/refresh.md').read_text()
        block = next(b for b in re.findall(r'```bash\n(.*?)```', refresh, re.S) if 'client-version.py' in b)
        self.script('npm', 'echo called >> "$HOME/npm-called"\nexit 99\n')
        for version in ('2.1.279', '2.1.280', '2.1.292', '2.1.293'):
            with self.subTest(version=version):
                running = self.script('running', f'echo "{version} (Claude Code)"\n')
                env = dict(os.environ, CLAUDE_CODE_EXECPATH=str(running), CLAUDE_CODE_ENTRYPOINT='claude-desktop')
                result = subprocess.run(['/bin/bash', '-c', block.replace('/absolute/path/of/active/sf-demo-scout', str(ROOT))],
                                        env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('Running Claude client binary: ' + version, result.stdout)
                self.assertEqual('Scout needs Claude Code' in result.stdout, version != '2.1.293')
        self.assertFalse((self.home / 'npm-called').exists())  # Claude Code updates itself; setup never does

    @unittest.skipUnless(Path('/bin/bash').exists(), "the startup fixture's sf and claude stubs are bash scripts")
    def test_startup_floor_global_json_roundtrip_and_fail_open(self):
        case = self.base / 'startup'; case.mkdir()
        fixture = STARTUP.StartupFixture(case)
        outside = case / 'outside'; outside.mkdir()
        running = self.script('running', 'echo "2.1.292 (Claude Code)"\n')
        os.environ.update(CLAUDE_CODE_ENTRYPOINT='claude-desktop', CLAUDE_CODE_EXECPATH=str(running))
        # With no plugin root, startup fails open to the plain workspace context.
        first = fixture.run()
        payload = json.loads(first.stdout)
        self.assertIn('Scout needs', payload['systemMessage'])
        self.assertIn('Active Org', payload['hookSpecificOutput']['additionalContext'])
        outside_result = fixture.run(cwd=outside)
        self.assertEqual(json.loads(outside_result.stdout)['hookSpecificOutput']['additionalContext'], '')
        for body in ('echo garbage', 'sleep 4', 'echo "2.1.293 (Claude Code)"'):
            self.script('running', body+'\n')
            result = fixture.run(cwd=outside)
            self.assertEqual((result.returncode, result.stdout), (0, ''))
        self.script('running', 'echo "2.1.292 (Claude Code)"\n')
        self.assertEqual(fixture.run(cwd=outside, host='codex').stdout, '')
        running.unlink()
        self.assertEqual(fixture.run(cwd=outside).stdout, '')
        plain = fixture.run().stdout
        # Both observations use cached org facts, so exact bytes are comparable.
        self.script('running', 'echo "2.1.292 (Claude Code)"\n')
        self.assertEqual(json.loads(fixture.run().stdout)['hookSpecificOutput']['additionalContext'], plain)
        failing_json = case / 'failing-json.py'
        failing_json.write_text('import os, sys\n'
            'if sys.argv[1] == "hook-output": sys.exit(1)\n'
            f'os.execv(sys.executable, [sys.executable, "-B", {str(ROOT / "scripts/startup-evidence.py")!r}, *sys.argv[1:]])\n')
        self.assertEqual(fixture.run(helper=failing_json).stdout, plain)
        self.assertEqual(fixture.run(cwd=outside, helper=failing_json).stdout, '')


class WindowsLocationTests(unittest.TestCase):
    """The report on Windows: its sources read without the POSIX-only open flag, and from Windows' own locations."""

    def test_a_source_is_read_without_o_nonblock_and_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / 'settings.json'
            path.write_bytes(b'{"env": {}}\r\n')
            flag = getattr(os, 'O_NONBLOCK', None)
            if flag is not None:
                del os.O_NONBLOCK  # as on Windows
            try:
                self.assertEqual(REPORT.read_text(path), '{"env": {}}\r\n')
            finally:
                if flag is not None:
                    os.O_NONBLOCK = flag

    def test_a_non_ascii_source_path_prints_as_utf8_whatever_the_code_page(self):
        # Windows can hand a captured stdout the ANSI code page; the report still names the source, as UTF-8 and LF.
        with tempfile.TemporaryDirectory(prefix='scout-report-') as raw:
            base = Path(raw) / 'Łódź 東京'
            settings = base / 'project' / '.claude' / 'settings.json'
            settings.parent.mkdir(parents=True)
            settings.write_text(json.dumps({'env': {PIN: 'us.anthropic.claude-sonnet-5-5'}}), encoding='utf-8')
            env = stand_ins.keep({'PATH': os.environ.get('PATH', ''), **stand_ins.home(base), 'SCOUT_HOST': 'claude',
                                  'CLAUDE_CODE_USE_BEDROCK': '1', 'PYTHONIOENCODING': 'cp1252',
                                  'PYTHONDONTWRITEBYTECODE': '1'})
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/setup-model-report.py'),
                                     '--project', str(base / 'project'), '--managed', str(base / 'managed.json'),
                                     '--vscode', str(base / 'vscode.json'), '--zshrc', str(base / '.zshrc')],
                                    env=env, capture_output=True, check=False, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
            output = result.stdout.decode('utf-8')
            self.assertIn('A Sonnet pin was read at ' + str(settings), output)
            self.assertNotIn('\r', output)

    def test_each_platform_names_its_own_sources_for_a_session_value(self):
        # A value only the session has comes from the shell or a launch agent on macOS and Linux; on Windows from a
        # user or system environment variable, or the app that started the session.
        wording = {'darwin': 'session environment, set outside the files Scout read (shell profile, launch agent or host app)',
                   'linux': 'session environment, set outside the files Scout read (shell profile, launch agent or host app)',
                   'win32': 'session environment, set outside the files Scout read (a user or system environment '
                            'variable, or the app that started the session)'}
        with tempfile.TemporaryDirectory(prefix='scout-report-') as raw:
            home = Path(raw)
            environment = stand_ins.keep({'PATH': str(home / 'no-tools'), PIN: 'claude-sonnet-4-6',
                                          'CLAUDE_CODE_USE_BEDROCK': '1'})  # no launchctl to find, on macOS either
            for platform, surface in wording.items():
                with self.subTest(platform=platform), patch.dict(os.environ, environment, clear=True), \
                        patch.object(REPORT.subprocess, 'run', side_effect=AssertionError('no launchctl call')):
                    rows, provider, failed = REPORT.collect(home, home / 'project', home / 'managed.json',
                                                            home / 'vscode.json', home / '.zshrc', platform=platform)
                    self.assertIn(dict(surface=surface, kind='shell', key=PIN, value='claude-sonnet-4-6'), rows)
                    output = '\n'.join(REPORT.report(rows, provider, failed, platform=platform))
                    self.assertIn(f'Model routing: {PIN} at {surface}:', output)
                    if platform == 'win32':
                        for macos in ('shell profile', 'launch agent', 'launchctl'):
                            self.assertNotIn(macos, output)

    def test_the_sonnet_advisory_names_launchctl_only_where_it_exists(self):
        before = ('Model routing advisory: with no Sonnet pin read in user settings, managed settings or launchctl, '
                  'the sonnet alias resolves to Sonnet 4.5 unless the session starts on a specific Sonnet version, so '
                  'a host’s default worker under an Opus session gets 4.5. Reopen /setup-bedrock to pin Sonnet 5.5.')
        self.assertEqual(REPORT.report([], 'bedrock', platform='darwin'), [before])
        self.assertEqual(REPORT.report([], 'bedrock', platform='linux'), [before])
        self.assertEqual(REPORT.report([], 'bedrock', platform='win32'),
                         [before.replace('user settings, managed settings or launchctl', 'user settings or managed settings')])

    def test_each_platform_reads_its_own_managed_and_vscode_settings(self):
        home = Path(tempfile.gettempdir()) / 'scout-home'
        self.assertEqual(REPORT.default_managed('win32'), Path('C:\\Program Files\\ClaudeCode\\managed-settings.json'))
        self.assertEqual(REPORT.default_managed('darwin'), Path('/Library/Application Support/ClaudeCode/managed-settings.json'))
        self.assertEqual(REPORT.default_managed('linux'), Path('/etc/claude-code/managed-settings.json'))
        with patch.dict(os.environ, {'APPDATA': str(home / 'Roaming')}):
            self.assertEqual(REPORT.default_vscode(home, 'win32'), home / 'Roaming' / 'Code' / 'User' / 'settings.json')
        with patch.dict(os.environ):
            os.environ.pop('APPDATA', None)
            self.assertEqual(REPORT.default_vscode(home, 'win32'),
                             home / 'AppData' / 'Roaming' / 'Code' / 'User' / 'settings.json')
        self.assertEqual(REPORT.default_vscode(home, 'darwin'), home / 'Library/Application Support/Code/User/settings.json')
        self.assertEqual(REPORT.default_vscode(home, 'linux'), home / '.config/Code/User/settings.json')


def shlex_quote(value):
    import shlex
    return shlex.quote(value)


if __name__ == '__main__':
    unittest.main()
