"""Offline routing-preservation, provider-remedy and running-client regressions."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

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
REFRESH = module('refresh_fixture_policy', ROOT / 'tests/test_setup.py')
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
        (self.bin / 'python3').symlink_to(sys.executable)
        self.script('launchctl', 'exit 0\n')
        self.environment = {'HOME': str(self.home), 'PATH': f'{self.bin}:/usr/bin:/bin',
                            'SCOUT_HOST': 'claude', 'CLAUDE_CODE_USE_BEDROCK': '1',
                            'PYTHONDONTWRITEBYTECODE': '1', 'CLAUDE_CONFIG_DIR': str(self.home / '.claude')}
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, self.environment, clear=True).start()

    def script(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/bash\n' + body)
        path.chmod(0o700)
        return path

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

    def test_surface_value_matrix_fresh_and_refresh_preserve_bytes(self):
        surfaces = ('user', 'local', 'vscode', 'launchctl', 'zsh-inside', 'zsh-outside', 'model', 'managed')
        count = 0
        cleanup = runpy.run_path(str(ROOT / 'scripts/setup-settings.py'))['run_json_pins']
        for surface in surfaces:
            for classification, value in VALUES.items():
                for mode in ('fresh', 'refresh'):
                    with self.subTest(surface=surface, classification=classification, mode=mode):
                        case = self.base / f'{surface}-{classification}-{mode}'
                        case.mkdir()
                        paths = {'user': case / '.claude/settings.json', 'local': case / '.claude/settings.local.json',
                                 'model': case / '.claude/settings.json', 'managed': case / 'managed.json',
                                 'vscode': case / 'vscode.json', 'zsh-inside': case / '.zshrc', 'zsh-outside': case / '.zshrc'}
                        key = 'model' if surface == 'model' else PIN
                        env = {} if value is None else {PIN: value}
                        path = paths.get(surface)
                        self.script('launchctl', 'exit 0\n')
                        if surface == 'launchctl':
                            self.script('launchctl', f'if [ "$1 $2" = "getenv {PIN}" ]; then printf "%s\\n" {shlex_quote(value or "")}; fi\n')
                            path = self.bin / 'launchctl'
                        else:
                            path.parent.mkdir(parents=True, exist_ok=True)
                            if surface.startswith('zsh'):
                                assignment = '' if value is None else f'export {PIN}="{value}"\n'
                                env_for_shell = dict(os.environ, SCOUT_ZSHRC_OVERRIDE=str(path))
                                subprocess.run(['/bin/bash', str(ROOT / 'scripts/setup-zshrc.sh')], env=env_for_shell, capture_output=True, check=True)
                                block = path.read_text()
                                body = block.replace('# BEGIN SF-DEMO-SCOUT\n', '# BEGIN SF-DEMO-SCOUT\n'+assignment) if surface == 'zsh-inside' else assignment + block
                            elif surface == 'vscode':
                                body = json.dumps({'claudeCode.environmentVariables': [{'name': k, 'value': v} for k, v in env.items()]})
                            else:
                                body = json.dumps(({} if value is None else {'model': value}) if surface == 'model' else {'env': env})
                            path.write_text(body)
                        before = path.read_bytes()
                        if surface in {'user', 'local', 'model'}:
                            cleanup(path)  # Both setup routes invoke the same cleanup operation.
                        if surface == 'vscode':
                            runpy.run_path(str(ROOT / 'scripts/setup-settings.py'))['run_vscode'](path)
                        if surface.startswith('zsh'):
                            subprocess.run(['/bin/bash', str(ROOT / 'scripts/setup-zshrc.sh')], env=env_for_shell, capture_output=True, check=True)
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
                        self.assertEqual(path.read_bytes(), before)
                        self.assertNotIn(ARN, output)
                        if classification in {'pre-5.5', 'alias'}:
                            self.assertIn(key, output)
                            self.assertIn('Ask whoever manages', output) if surface == 'managed' else self.assertIn('/setup-bedrock', output)
                            if surface in {'zsh-inside', 'zsh-outside', 'launchctl', 'vscode'}:
                                self.assertIn('source first', output)
                        else:
                            self.assertNotIn('Model routing:', output)
                        count += 1
        self.assertEqual(count, 96)

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
        self.script('claude', 'echo "2.1.300 (Claude Code)"\n')
        running = self.script('running', 'echo "2.1.292 (Claude Code)"\n')
        os.environ.update(CLAUDE_CODE_ENTRYPOINT='claude-desktop', CLAUDE_CODE_EXECPATH=str(running))
        observation = CLIENT.observe()
        self.assertEqual(observation['version'], '2.1.292')
        self.assertIn('desktop app', CLIENT.floor_line(observation))
        self.assertIn('different CLI binary', CLIENT.floor_line(observation, updated=str(self.bin / 'claude')))
        for version in ('2.1.279', '2.1.280', '2.1.292', '2.1.293'):
            observation['version'] = version
            self.assertEqual(bool(CLIENT.floor_line(observation)), version != '2.1.293')
        del os.environ['CLAUDE_CODE_EXECPATH']
        self.assertNotIn('version', CLIENT.observe())  # Desktop must not use PATH.
        os.environ['CLAUDE_CODE_ENTRYPOINT'] = 'cli'
        self.assertEqual(CLIENT.observe()['version'], '2.1.300')
        os.environ['CLAUDE_CODE_EXECPATH'] = str(running)
        for body in ('echo "error near 2.1.279"', 'echo "2.1.279"; exit 2', 'sleep 4; echo 2.1.279'):
            self.script('running', body+'\n')
            start = time.monotonic()
            self.assertNotIn('version', CLIENT.observe())
            self.assertLess(time.monotonic()-start, 2.8)

    def test_refresh_outcomes_report_each_floor_version_without_extra_updates(self):
        for version in ('2.1.279', '2.1.280', '2.1.292', '2.1.293'):
            for outcome in ('current', 'updated', 'held', 'not-owned', 'unverified', 'failure'):
                with self.subTest(version=version, outcome=outcome):
                    case = self.base / f'{version}-{outcome}'
                    fixture = REFRESH.CliRefreshScriptTests()
                    bin_dir, calls = fixture.make_stubs(case, 'claude')
                    (bin_dir / 'python3').symlink_to(sys.executable)
                    running = self.script('running', f'echo "{version} (Claude Code)"\n')
                    env = dict(os.environ, PATH=f'{bin_dir}:/usr/bin:/bin', CALLS=str(calls), COUNTER=str(case / 'counter'),
                        PRE_OUT=f'{version} (Claude Code)', POST_OUT='2.1.300 (Claude Code)',
                        NPM_ROOT=str(case / 'npm-root'), NPM_ROOT_RC='0', NPM_VIEW=version,
                        NPM_RESOLVE_LINE=f'add @anthropic-ai/claude-code {version} => {version}',
                        CLAUDE_CODE_EXECPATH=str(running), CLAUDE_CODE_ENTRYPOINT='claude-desktop',
                        TMPDIR=str(case))
                    if outcome in {'updated', 'failure'}:
                        env['NPM_RESOLVE_LINE'] = f'add @anthropic-ai/claude-code {version} => 2.1.300'
                    if outcome == 'failure': env['NPM_INSTALL_RC'] = '1'
                    if outcome == 'held': env['NPM_VIEW'] = '2.1.300'
                    if outcome == 'unverified': env['NPM_ROOT_RC'] = '1'
                    if outcome == 'not-owned':
                        tool = bin_dir / 'claude'; tool.unlink(); tool.write_text('#!/bin/bash\necho 2.1.293\n'); tool.chmod(0o700)
                    result = subprocess.run(['/bin/bash', str(ROOT / 'scripts/setup-cli-refresh.sh'), 'claude'], env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('Running Claude client binary: '+version, result.stdout)
                    self.assertEqual('Scout needs Claude Code' in result.stdout, version != '2.1.293')
                    self.assertEqual('npm install @anthropic-ai/claude-code --global\n' in calls.read_text(), outcome in {'updated', 'failure'})
                    if outcome == 'updated' and version != '2.1.293':
                        self.assertIn('different CLI binary', result.stdout)

    def test_startup_floor_global_json_roundtrip_and_fail_open(self):
        case = self.base / 'startup'; case.mkdir()
        fixture = STARTUP.StartupFixture(case)
        outside = case / 'outside'; outside.mkdir()
        running = self.script('running', 'echo "2.1.292 (Claude Code)"\n')
        os.environ.update(CLAUDE_CODE_ENTRYPOINT='claude-desktop', CLAUDE_CODE_EXECPATH=str(running))
        # With no plugin root, W6 fails open to W2's exact legacy context.
        orgs = fixture.workspace / 'orgs'; orgs.mkdir()
        for index in range(100):
            (orgs / ('qa-a-' + str(index).zfill(3) + '-' + 'x'*200)).mkdir()
        first = fixture.run()
        payload = json.loads(first.stdout)
        self.assertIn('Scout needs', payload['systemMessage'])
        self.assertGreater(len(payload['hookSpecificOutput']['additionalContext']), 10000)
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


def shlex_quote(value):
    import shlex
    return shlex.quote(value)


if __name__ == '__main__':
    unittest.main()
