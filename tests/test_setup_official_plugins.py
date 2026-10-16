"""Official-plugin setup tested through a fake claude CLI, never a real marketplace, network or user config."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/setup-official-plugins.py'
SETTINGS = ROOT / 'scripts/setup-settings.py'
PLUGINS = ('salesforce-development', 'salesforce-code-quality', 'agentforce-adlc', 'experience-lwc', 'service-engagement')  # all five at setup

FAKE_CLAUDE = r'''
import json, os, sys
from pathlib import Path
path = Path(os.environ['OP_STATE'])
state = json.loads(path.read_text())
args = sys.argv[1:]
config = Path(os.environ['CLAUDE_CONFIG_DIR'])
with open(os.environ['OP_CALLS'], 'a') as f:
    f.write(json.dumps(args) + '\n')
def records():
    # What the real CLI keeps: known marketplaces, install records and enabledPlugins in user settings.
    (config / 'plugins').mkdir(parents=True, exist_ok=True)
    known = {}
    for m in state.get('marketplaces', []):
        location = config / 'plugins/marketplaces' / m['name']
        for skill in state.get('catalog', []):  # the clone's standalone skills, as Claude keeps it
            (location / 'skills' / skill).mkdir(parents=True, exist_ok=True)
            (location / 'skills' / skill / 'SKILL.md').write_text('---\nname: %s\n---\n' % skill)
        location.mkdir(parents=True, exist_ok=True)
        known[m['name']] = {'source': {k: v for k, v in m.items() if k != 'name'}, 'installLocation': str(location)}
    (config / 'plugins/known_marketplaces.json').write_text(json.dumps(known))
    plugins = {}
    for row in state.get('plugins', []):
        root = config / 'cache' / row['id'].replace('@', '/') / row.get('version', '1')
        root.mkdir(parents=True, exist_ok=True)
        plugins.setdefault(row['id'], []).append({'scope': row.get('scope', 'user'), 'installPath': str(root),
                                                  'version': row.get('version')})
    (config / 'plugins/installed_plugins.json').write_text(json.dumps({'version': 2, 'plugins': plugins}))
    settings = config / 'settings.json'
    data = json.loads(settings.read_text()) if settings.exists() else {}
    if isinstance(data, dict):
        data['enabledPlugins'] = {r['id']: r.get('enabled', True) for r in state.get('plugins', []) if r.get('scope', 'user') == 'user'}
        settings.write_text(json.dumps(data, indent=2))
def save(): path.write_text(json.dumps(state)); records()
def result(**fields): print('progress line'); print(json.dumps(fields)); sys.exit(0 if fields.get('outcome') == 'ok' else 1)
if args[:3] == ['plugin', 'marketplace', 'list']:
    print(json.dumps(state.get('marketplaces', []), indent=2)); sys.exit(0)
if args[:3] == ['plugin', 'marketplace', 'add']:
    if state.get('add_fail'):
        result(command='marketplace-add', outcome='failed', message='git clone failed: network unreachable')
    where, _, ref = args[3].partition('#')
    source = {'source': 'git', 'url': where} if '://' in where or where.endswith('.git') else {'source': 'github', 'repo': where}
    if ref:
        source['ref'] = ref
    name = state.get('add_name', 'salesforce')
    settings = config / 'settings.json'
    data = json.loads(settings.read_text()) if settings.exists() else {}
    declared = data.get('extraKnownMarketplaces', {}).get(name, {}).get('source')
    if declared is not None and declared != source:  # the real CLI's rule: re-add only from the declared form
        result(command='marketplace-add', outcome='failed', message="its source doesn't match its extraKnownMarketplaces entry")
    if declared is not None and state.get('readd_save_ref'):  # the SE saves another ref while the re-add runs
        data['extraKnownMarketplaces'][name]['source']['ref'] = state['readd_save_ref']
        settings.write_text(json.dumps(data, indent=2))
        result(command='marketplace-add', outcome='failed', message='git clone failed: network unreachable')
    if declared is not None and state.get('readd_mutate_fail'):  # the registry changed before the failure
        state['marketplaces'] = [dict(source, name=name) if m['name'] == name else m for m in state.get('marketplaces', [])]
        save()
        result(command='marketplace-add', outcome='failed', message='git clone timed out')
    if declared is not None and state.get('readd_fail'):
        result(command='marketplace-add', outcome='failed', message='git clone failed: network unreachable')
    state['marketplaces'] = [m for m in state.get('marketplaces', []) if m['name'] != name] + [dict(source, name=name)]
    data.setdefault('extraKnownMarketplaces', {})[name] = dict(data.get('extraKnownMarketplaces', {}).get(name, {}), source=source)
    settings.write_text(json.dumps(data, indent=2)); save()
    result(command='marketplace-add', outcome='ok', marketplace=name)
if args[:2] == ['plugin', 'update']:
    if args[2] in state.get('update_fail', []):
        result(command='update', outcome='failed', message='Plugin update failed: network unreachable')
    for row in state.get('plugins', []):
        if row['id'] == args[2] and row.get('scope', 'user') == 'user':
            old, row['version'] = row.get('version'), state.get('update_to', '2.4.0')
            save(); result(command='update', outcome='ok', oldVersion=old, newVersion=row['version'])
    result(command='update', outcome='failed', message='Plugin not found')
if args[:2] == ['plugin', 'list']:
    state['lists'] = state.get('lists', 0) + 1; path.write_text(json.dumps(state))
    if state.get('list_fail') or state['lists'] == state.get('list_fail_on', -1):
        print('[]'); sys.exit(1)
    print(json.dumps(state.get('plugins', []))); sys.exit(0)
if args[:2] == ['plugin', 'install']:
    if args[2] in state.get('install_fail', []):
        result(command='install', outcome='failed', message='Plugin not found in marketplace')
    state.setdefault('plugins', []).append({'id': args[2], 'version': '9.9.9', 'scope': 'user', 'enabled': True}); save()
    if args[2] in state.get('install_exit_nonzero', []):
        print(json.dumps({'command': 'install', 'outcome': 'ok'})); sys.exit(3)
    result(command='install', outcome='ok', pluginId=args[2])
if args[:2] == ['plugin', 'disable']:
    if args[2] in state.get('disable_fail', []):
        result(command='disable', outcome='failed', message='Plugin is managed by policy')
    for row in state.get('plugins', []):
        if row['id'] == args[2] and row.get('scope', 'user') == 'user':
            row['enabled'] = False
    save(); result(command='disable', outcome='ok')
if args[:2] == ['plugin', 'enable']:
    for row in state.get('plugins', []):
        if row['id'] == args[2] and row.get('scope', 'user') == 'user':
            row['enabled'] = True
    save(); result(command='enable', outcome='ok')
sys.exit(9)
'''


class SetupFixture(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='scout-op-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        binary = self.bin / 'claude'
        binary.write_text('#!' + sys.executable + '\n' + FAKE_CLAUDE)
        binary.chmod(0o700)
        self.config = self.root / 'claude-config'
        self.config.mkdir()
        self.state, self.calls = self.root / 'state.json', self.root / 'calls.jsonl'
        self.workspace_settings = self.root / 'ws-settings.json'
        self.configure()

    def configure(self, **state):
        self.state.write_text(json.dumps(state))
        env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.config), OP_STATE=str(self.state), OP_CALLS=str(self.root / 'ignored.jsonl'))
        subprocess.run([str(self.bin / 'claude'), 'plugin', 'enable', '--none--'], env=env, capture_output=True)  # writes the records

    def run_setup(self, *extra, host='claude', path=None, env=None):
        env = dict(HOME=str(self.root), PATH=path if path is not None else str(self.bin) + ':/usr/bin:/bin',
                   CLAUDE_CONFIG_DIR=str(self.config), OP_STATE=str(self.state), OP_CALLS=str(self.calls),
                   PYTHONDONTWRITEBYTECODE='1', **(env or {}))
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), '--host', host, *extra], env=env,
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return result.stdout.splitlines()

    def calls_made(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []


class OfficialPluginSetupTests(SetupFixture):
    def test_a_fresh_install_registers_auto_updates_and_installs_all_five(self):
        out = self.run_setup()
        self.assertEqual(out[0], 'OFFICIAL_MARKETPLACE_ADDED salesforce')
        self.assertEqual(out[1], 'OFFICIAL_AUTOUPDATE_SET[settings.json]')
        self.assertEqual(out[2:7], ['OFFICIAL_PLUGIN_INSTALLED %s' % p for p in PLUGINS])
        self.assertEqual(out[-2:], ['OFFICIAL_PLUGINS_DONE restart=needed', 'OFFICIAL_READINESS ready'])
        settings = json.loads((self.config / 'settings.json').read_text())
        self.assertIs(settings['extraKnownMarketplaces']['salesforce']['autoUpdate'], True)
        add = [c for c in self.calls_made() if c[:3] == ['plugin', 'marketplace', 'add']][0]
        self.assertEqual(add[3:], ['https://github.com/forcedotcom/sf-skills.git', '--scope', 'user', '--json'])
        installs = [c[2] for c in self.calls_made() if c[:2] == ['plugin', 'install']]
        self.assertEqual(installs, ['%s@salesforce' % p for p in PLUGINS])

    def test_a_rerun_changes_nothing(self):
        self.run_setup()
        calls = len(self.calls_made())
        out = self.run_setup()
        self.assertEqual(out[0], 'OFFICIAL_MARKETPLACE_PRESENT salesforce')
        self.assertEqual(out[1], 'OFFICIAL_AUTOUPDATE_ALREADY[settings.json]')
        self.assertTrue(all(line.startswith('OFFICIAL_PLUGIN_PRESENT') for line in out[2:7]))
        self.assertEqual(out[-2:], ['OFFICIAL_PLUGINS_DONE restart=no', 'OFFICIAL_READINESS ready'])
        self.assertFalse(any(c[:2] in (['plugin', 'install'], ['plugin', 'enable']) or c[:3] == ['plugin', 'marketplace', 'add']
                             for c in self.calls_made()[calls:]))

    def test_an_existing_registration_under_another_name_is_reused(self):
        (self.config / 'settings.json').write_text(json.dumps({'extraKnownMarketplaces': {
            'sf-skills': {'source': {'source': 'github', 'repo': 'forcedotcom/sf-skills'}}}}))
        self.configure(marketplaces=[{'name': 'sf-skills', 'source': 'github', 'repo': 'forcedotcom/sf-skills'}])
        out = self.run_setup()
        self.assertEqual(out[:2], ['OFFICIAL_MARKETPLACE_PRESENT sf-skills', 'OFFICIAL_AUTOUPDATE_SET[settings.json]'])
        self.assertTrue(all(c[2].endswith('@sf-skills') for c in self.calls_made() if c[:2] == ['plugin', 'install']))

    def test_failures_are_reported_per_plugin_and_never_abort(self):
        self.configure(install_fail=['agentforce-adlc@salesforce'],
                       plugins=[{'id': 'experience-lwc@salesforce', 'version': '1.0.0', 'enabled': False}])
        out = self.run_setup('--plugins', 'agentforce-adlc', 'experience-lwc', 'service-engagement')  # a task's first need
        self.assertIn('OFFICIAL_PLUGIN_FAILED agentforce-adlc Plugin not found in marketplace', out)
        self.assertIn('OFFICIAL_PLUGIN_ENABLED experience-lwc', out)
        self.assertEqual([l for l in out if l.startswith('OFFICIAL_PLUGIN_INSTALLED')], ['OFFICIAL_PLUGIN_INSTALLED service-engagement'])
        self.configure(add_fail=True)
        (self.config / 'settings.json').unlink()
        self.assertEqual(self.run_setup(), ['OFFICIAL_MARKETPLACE_FAILED git clone failed: network unreachable',
                                            'OFFICIAL_READINESS blocked ' + ' '.join('%s:setup-needed' % p for p in PLUGINS)])

    def test_anthropics_copies_are_reported_and_switched_off_only_when_asked(self):
        anthropic = [{'id': 'salesforce-development@claude-plugins-official', 'version': '2.3.0', 'scope': 'user', 'enabled': True},
                     {'id': 'experience-lwc@claude-plugins-official', 'version': '1.0.0', 'scope': 'user', 'enabled': True},
                     {'id': 'salesforce-code-quality@claude-plugins-official', 'version': '1.0.0', 'scope': 'user', 'enabled': False}]
        self.configure(plugins=anthropic, disable_fail=[])
        out = self.run_setup()
        self.assertEqual([l for l in out if l.startswith('OFFICIAL_DUPLICATE')],
                         ['OFFICIAL_DUPLICATE salesforce-development@claude-plugins-official',
                          'OFFICIAL_DUPLICATE experience-lwc@claude-plugins-official'])  # the switched-off copy isn't one
        self.assertFalse(any(c[:2] == ['plugin', 'disable'] for c in self.calls_made()))
        out = self.run_setup('--disable-duplicates', 'salesforce-development@claude-plugins-official', 'experience-lwc@claude-plugins-official')
        self.assertIn('OFFICIAL_DUPLICATE_DISABLED salesforce-development@claude-plugins-official', out)
        self.assertIn('OFFICIAL_DUPLICATE_DISABLED experience-lwc@claude-plugins-official', out)
        self.assertEqual(out[-2:], ['OFFICIAL_PLUGINS_DONE restart=needed', 'OFFICIAL_READINESS ready'])
        disables = [c[2] for c in self.calls_made() if c[:2] == ['plugin', 'disable']]
        self.assertEqual(disables, ['salesforce-development@claude-plugins-official', 'experience-lwc@claude-plugins-official'])
        self.configure(plugins=anthropic, disable_fail=['experience-lwc@claude-plugins-official'])
        out = self.run_setup('--plugins', 'experience-lwc', '--disable-duplicates', 'experience-lwc@claude-plugins-official')
        self.assertIn('OFFICIAL_DUPLICATE_FAILED experience-lwc@claude-plugins-official Plugin is managed by policy', out)

    def test_an_add_on_duplicate_is_found_and_its_repair_keeps_the_plugin_selection(self):
        lwc = [{'id': 'experience-lwc@claude-plugins-official', 'version': '1.0.0', 'scope': 'user', 'enabled': True}]
        self.configure(plugins=list(lwc))
        out = self.run_setup('--plugins', 'experience-lwc')  # a first need
        self.assertIn('OFFICIAL_PLUGIN_INSTALLED experience-lwc', out)
        self.assertIn('OFFICIAL_DUPLICATE experience-lwc@claude-plugins-official', out)
        self.assertEqual(out[-1], 'OFFICIAL_READINESS blocked experience-lwc:conflict')
        out = self.run_setup()  # an ordinary setup still notices the add-on's two copies
        self.assertIn('OFFICIAL_DUPLICATE experience-lwc@claude-plugins-official', out)
        out = self.run_setup('--plugins', 'experience-lwc', '--disable-duplicates', 'experience-lwc@claude-plugins-official')  # the same command, plus the yes
        self.assertIn('OFFICIAL_DUPLICATE_DISABLED experience-lwc@claude-plugins-official', out)
        self.assertEqual(out[-1], 'OFFICIAL_READINESS ready')

    def test_another_projects_installation_never_counts(self):
        self.configure(plugins=[{'id': '%s@salesforce' % p, 'version': '2.4.0', 'scope': 'project', 'enabled': True}
                                for p in PLUGINS])
        out = self.run_setup()
        self.assertEqual([l for l in out if l.startswith('OFFICIAL_PLUGIN_INSTALLED')],
                         ['OFFICIAL_PLUGIN_INSTALLED %s' % p for p in PLUGINS])
        installs = [c for c in self.calls_made() if c[:2] == ['plugin', 'install']]
        self.assertTrue(all(c[-3:] == ['--scope', 'user', '--json'] for c in installs))
        self.assertEqual(out[-1], 'OFFICIAL_READINESS ready')

    def test_a_nonzero_exit_is_a_failure_whatever_the_json_says(self):
        self.configure(install_exit_nonzero=['salesforce-code-quality@salesforce'])
        out = self.run_setup()
        self.assertIn('OFFICIAL_PLUGIN_FAILED salesforce-code-quality no result', out)
        self.configure(list_fail=True)
        self.assertIn('OFFICIAL_PLUGINS_UNKNOWN could not list plugins after installing: no result', self.run_setup())  # exit 1, even with JSON

    def test_setup_and_readiness_match_sources_the_same_way(self):
        self.configure(marketplaces=[{'name': 'sf', 'source': 'git', 'url': 'ssh://git@github.com/forcedotcom/sf-skills.git'}])
        (self.config / 'settings.json').write_text(json.dumps({'extraKnownMarketplaces': {'sf': {'source': {}}}}))
        out = self.run_setup()
        self.assertEqual(out[0], 'OFFICIAL_MARKETPLACE_PRESENT sf')
        self.assertEqual(out[-1], 'OFFICIAL_READINESS ready')
        clone = self.root / 'clone'
        clone.mkdir()
        self.configure()
        out = self.run_setup(env={'SCOUT_OFFICIAL_SOURCE': str(clone)})  # the trial mode reaches setup too
        add = [c for c in self.calls_made() if c[:3] == ['plugin', 'marketplace', 'add']][-1]
        self.assertEqual(add[3], str(clone))

    def test_an_unresolved_add_on_conflict_is_never_ready(self):
        lwc = [{'id': 'experience-lwc@claude-plugins-official', 'version': '1.0.0', 'scope': 'user', 'enabled': True},
               {'id': 'experience-lwc@salesforce', 'version': '0.2.0', 'scope': 'user', 'enabled': True}]
        self.configure(marketplaces=[{'name': 'salesforce', 'source': 'git', 'url': 'https://github.com/forcedotcom/sf-skills.git'}],
                       plugins=list(lwc))
        (self.config / 'settings.json').write_text(json.dumps({'extraKnownMarketplaces': {'salesforce': {'source': {}}},
                                                                'enabledPlugins': {r['id']: True for r in lwc}}))
        out = self.run_setup()  # an ordinary setup; the SE then declines the switch-off
        self.assertIn('OFFICIAL_DUPLICATE experience-lwc@claude-plugins-official', out)
        self.assertEqual(out[-1], 'OFFICIAL_READINESS blocked experience-lwc:conflict')
        out = self.run_setup('--disable-duplicates', 'experience-lwc@claude-plugins-official')
        self.assertEqual(out[-1], 'OFFICIAL_READINESS ready')

    def test_a_healthy_second_registration_is_left_alone(self):
        markets = [{'name': 'old', 'source': 'git', 'url': 'https://github.com/forcedotcom/sf-skills.git'},
                   {'name': 'new', 'source': 'github', 'repo': 'forcedotcom/sf-skills'}]
        plugins = [{'id': '%s@%s' % (p, m), 'version': '2.4.0', 'scope': 'user', 'enabled': m == 'new'}
                   for p in PLUGINS for m in ('old', 'new')]
        self.configure(marketplaces=markets, plugins=plugins)
        (self.config / 'settings.json').write_text(json.dumps({'extraKnownMarketplaces': {'old': {'source': {}}, 'new': {'source': {}}},
                                                                'enabledPlugins': {r['id']: r['enabled'] for r in plugins}}))
        calls = len(self.calls_made())
        out = self.run_setup()
        self.assertFalse(any(c[:2] in (['plugin', 'install'], ['plugin', 'enable'], ['plugin', 'disable'])
                             for c in self.calls_made()[calls:]))
        self.assertEqual(out[-2:], ['OFFICIAL_PLUGINS_DONE restart=no', 'OFFICIAL_READINESS ready'])
        markets = json.loads((self.config / 'settings.json').read_text())['extraKnownMarketplaces']
        self.assertIs(markets['new'].get('autoUpdate'), True)  # the registration in use auto-updates too

    def test_a_failed_reread_is_reported_and_duplicates_still_found(self):
        lwc = [{'id': 'experience-lwc@claude-plugins-official', 'version': '1.0.0', 'scope': 'user', 'enabled': True}]
        self.configure(plugins=list(lwc), list_fail_on=1)  # the one list call, after installing, fails
        out = self.run_setup('--plugins', 'experience-lwc')
        self.assertIn('OFFICIAL_PLUGIN_INSTALLED experience-lwc', out)
        self.assertIn('OFFICIAL_PLUGINS_UNKNOWN could not list plugins after installing: no result', out)
        self.assertFalse(any(l.startswith('OFFICIAL_PLUGIN_VERSION') for l in out))
        self.assertIn('OFFICIAL_DUPLICATE experience-lwc@claude-plugins-official', out)
        self.assertEqual(out[-1], 'OFFICIAL_READINESS blocked experience-lwc:conflict')

    def test_an_unaccepted_explicit_source_is_refused(self):
        out = self.run_setup('--source', str(self.root / 'some-checkout'))
        self.assertTrue(out[0].startswith('OFFICIAL_SOURCE_UNSUPPORTED'), out[0])
        self.assertEqual(self.calls_made(), [])

    def test_records_that_landed_before_an_error_still_need_a_reload(self):
        others = [{'id': '%s@salesforce' % p, 'version': '2.4.0', 'scope': 'user', 'enabled': True}
                  for p in PLUGINS if p != 'salesforce-code-quality']  # nothing else succeeds, so only the snapshot can tell
        self.configure(marketplaces=[{'name': 'salesforce', 'source': 'git', 'url': 'https://github.com/forcedotcom/sf-skills.git'}],
                       plugins=others, install_exit_nonzero=['salesforce-code-quality@salesforce'])
        (self.config / 'settings.json').write_text(json.dumps({'extraKnownMarketplaces': {'salesforce': {'source': {}}},
                                                                'enabledPlugins': {r['id']: True for r in others}}))
        out = self.run_setup()
        self.assertIn('OFFICIAL_PLUGIN_FAILED salesforce-code-quality no result', out)
        self.assertFalse(any(l.startswith('OFFICIAL_PLUGIN_INSTALLED') for l in out))
        self.assertEqual(out[-2:], ['OFFICIAL_PLUGINS_DONE restart=needed', 'OFFICIAL_READINESS ready'])

    def test_other_hosts_and_a_missing_cli(self):
        self.assertEqual(self.run_setup(host='codex'), ['OFFICIAL_PLUGINS_SKIPPED host=codex (sf-skills ships no plugin for this host)',
                                                        'OFFICIAL_READINESS not-applicable host=codex'])
        self.assertEqual(self.calls_made(), [])
        self.assertEqual(self.run_setup(path='/usr/bin:/bin')[0], "OFFICIAL_PLUGINS_UNAVAILABLE Claude Code's binary not found")
        self.assertTrue(self.run_setup(path='/usr/bin:/bin')[-1].startswith('OFFICIAL_READINESS blocked '))

    def running_client(self, version_output):
        """A second fake that answers `--version` and logs its calls apart, so a test can tell which binary ran."""
        app = self.root / 'Claude.app'
        app.mkdir(exist_ok=True)
        binary = app / 'claude'
        binary.write_text('#!' + sys.executable + '\nimport os, sys\nif sys.argv[1:] == ["--version"]:\n'
                          '    sys.stdout.buffer.write(%r); sys.exit(0)\n'
                          'os.environ["OP_CALLS"] += ".running"\n' % version_output + FAKE_CLAUDE)
        binary.chmod(0o700)
        return str(binary)

    def calls_by_running_client(self):
        log = Path(str(self.calls) + '.running')
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    INSTALL = ['plugin', 'install', 'salesforce-development@salesforce', '--scope', 'user', '--json']

    def test_a_desktop_only_se_installs_through_the_apps_own_binary(self):
        # The desktop app puts no `claude` on the PATH; the running client's binary manages the same plugins.
        desktop = self.running_client(b'2.1.295 (Claude Code)\n')
        out = self.run_setup(path='/usr/bin:/bin', env={'CLAUDE_CODE_EXECPATH': desktop})
        self.assertEqual(out[0], 'OFFICIAL_MARKETPLACE_ADDED salesforce')
        self.assertEqual(out[-1], 'OFFICIAL_READINESS ready')
        self.assertIn(self.INSTALL, self.calls_by_running_client())

    def test_the_running_client_wins_over_another_cli_on_the_path(self):
        # An SE may keep an older terminal install; the client that's running Scout manages the plugins.
        desktop = self.running_client(b'2.1.295 (Claude Code)\n')
        self.assertEqual(self.run_setup(env={'CLAUDE_CODE_EXECPATH': desktop})[-1], 'OFFICIAL_READINESS ready')
        self.assertIn(self.INSTALL, self.calls_by_running_client())
        self.assertEqual(self.calls_made(), [])

    def test_a_running_client_that_is_not_claude_falls_back_to_the_path(self):
        for output in (b'v22.11.0\n', b'\xff\xfe\n'):  # an npm install's node; output that isn't text
            with self.subTest(output=output):
                other = self.running_client(output)
                self.assertEqual(self.run_setup(env={'CLAUDE_CODE_EXECPATH': other})[-1], 'OFFICIAL_READINESS ready')
                self.assertIn(['plugin', 'marketplace', 'list', '--json'], self.calls_made())  # the PATH's claude
                self.assertEqual(self.calls_by_running_client(), [])
                self.assertEqual(self.run_setup(path='/usr/bin:/bin', env={'CLAUDE_CODE_EXECPATH': other})[0],
                                 "OFFICIAL_PLUGINS_UNAVAILABLE Claude Code's binary not found")

    def test_auto_update_needs_the_declared_entry(self):
        self.configure(marketplaces=[{'name': 'salesforce', 'source': 'git', 'url': 'https://github.com/forcedotcom/sf-skills'}])
        (self.config / 'settings.json').write_text('{"other": true}\n')
        out = self.run_setup()
        self.assertEqual(out[1], 'OFFICIAL_AUTOUPDATE_NO_ENTRY[settings.json]')
        data = json.loads((self.config / 'settings.json').read_text())
        self.assertEqual((data['other'], 'extraKnownMarketplaces' in data), (True, False))  # nothing invented

    def test_the_workspace_recommender_switch(self):
        self.workspace_settings.write_text(json.dumps({'permissions': {'allow': ['Bash']}}))
        out = self.run_setup('--workspace-settings', str(self.workspace_settings))
        self.assertIn('OFFICIAL_RECOMMENDER_ENV_SET[ws-settings.json]', out)
        data = json.loads(self.workspace_settings.read_text())
        self.assertEqual((data['env'], data['permissions']), ({'SF_DISABLE_PLUGIN_MATCH': '1'}, {'allow': ['Bash']}))
        self.assertIn('OFFICIAL_RECOMMENDER_ENV_ALREADY[ws-settings.json]', self.run_setup('--workspace-settings', str(self.workspace_settings)))
        self.workspace_settings.write_text('{"env": {"A": "1"},}')
        self.assertIn('OFFICIAL_RECOMMENDER_ENV_PARSE_ERROR[ws-settings.json]', ' '.join(self.run_setup('--workspace-settings', str(self.workspace_settings))))
        self.assertEqual(self.workspace_settings.read_text(), '{"env": {"A": "1"},}')


class PinnedFixture(SetupFixture):
    """Scout takes over existing installs (W20-T): a pinned registration it uses, after one approval; duplicates as
    before; personal and project copies are only reported."""
    PINNED = {'source': 'github', 'repo': 'forcedotcom/sf-skills', 'ref': '1.59.0'}

    def pinned_setup(self, plugins=('salesforce-development', 'salesforce-code-quality'), declared=None, **state):
        rows = [{'id': '%s@salesforce' % p, 'version': '2.3.0', 'scope': 'user', 'enabled': True} for p in plugins]
        self.configure(marketplaces=[dict(self.PINNED, name='salesforce')], plugins=rows, **state)
        settings = json.loads((self.config / 'settings.json').read_text())
        settings['extraKnownMarketplaces'] = {'salesforce': {'source': dict(declared or self.PINNED)}}
        (self.config / 'settings.json').write_text(json.dumps(settings))
        return rows

    def settings(self):
        return json.loads((self.config / 'settings.json').read_text())


class TakeoverTests(PinnedFixture):
    """Scout takes over a pinned registration it uses, after one approval; copies are only reported."""

    def test_a_pinned_registration_is_proposed_not_changed(self):
        self.pinned_setup()
        out = self.run_setup()
        self.assertIn('OFFICIAL_PINNED salesforce 1.59.0 %s' % ','.join(sorted(PLUGINS)), out)  # the final list, after installs (D1)
        self.assertFalse(any(c[:2] == ['plugin', 'update'] or c[:3] == ['plugin', 'marketplace', 'add'] for c in self.calls_made()))
        self.assertEqual(self.settings()['extraKnownMarketplaces']['salesforce']['source']['ref'], '1.59.0')

    def test_an_approved_unpin_follows_the_latest_and_updates_each_plugin(self):
        self.pinned_setup(plugins=PLUGINS + ('mobile-development',))  # one plugin Scout doesn't use, switched off
        state = json.loads(self.state.read_text())
        for row in state['plugins']:
            row['enabled'] = row['id'] != 'mobile-development@salesforce'
        self.configure(**state)
        settings = self.settings()
        settings['extraKnownMarketplaces'] = {'salesforce': {'source': dict(self.PINNED)}}
        (self.config / 'settings.json').write_text(json.dumps(settings))
        self.assertIn('OFFICIAL_PINNED salesforce 1.59.0 %s' % ','.join(sorted(PLUGINS + ('mobile-development',))),
                      self.run_setup())  # the approval names every plugin the unpin would update
        out = self.run_setup('--unpin', 'salesforce:1.59.0')
        for plugin in PLUGINS + ('mobile-development',):
            self.assertIn('OFFICIAL_PLUGIN_UPDATED %s 2.3.0 2.4.0' % plugin, out)
        self.assertIn('OFFICIAL_UNPINNED salesforce', out)
        self.assertNotIn('ref', self.settings()['extraKnownMarketplaces']['salesforce']['source'])
        known = json.loads((self.config / 'plugins/known_marketplaces.json').read_text())
        self.assertNotIn('ref', known['salesforce']['source'])
        self.assertIs(self.settings()['enabledPlugins']['mobile-development@salesforce'], False)  # still switched off
        self.assertIn('OFFICIAL_PLUGINS_DONE restart=needed', out)

    def test_a_failed_re_add_restores_the_pin(self):
        self.pinned_setup(readd_fail=True)
        out = self.run_setup('--unpin', 'salesforce:1.59.0')
        self.assertIn('OFFICIAL_UNPIN_FAILED salesforce git clone failed: network unreachable; the setting is fixed to 1.59.0 again', out)
        self.assertEqual(self.settings()['extraKnownMarketplaces']['salesforce']['source']['ref'], '1.59.0')
        self.assertFalse(any(c[:2] == ['plugin', 'update'] for c in self.calls_made()))

    def test_a_plugin_already_at_the_latest_version_is_reported_current(self):
        self.pinned_setup(update_to='2.3.0')  # the latest happens to carry the same version
        out = self.run_setup('--unpin', 'salesforce:1.59.0')
        self.assertIn('OFFICIAL_PLUGIN_CURRENT salesforce-development 2.3.0', out)
        self.assertFalse(any(l.startswith('OFFICIAL_PLUGIN_UPDATED') for l in out))
        self.assertIn('OFFICIAL_UNPINNED salesforce', out)

    def test_a_partial_update_is_reported_as_partial(self):
        self.pinned_setup(update_fail=['salesforce-development@salesforce'])
        out = self.run_setup('--unpin', 'salesforce:1.59.0')
        self.assertIn('OFFICIAL_PLUGIN_UPDATE_FAILED salesforce-development Plugin update failed: network unreachable', out)
        self.assertIn('OFFICIAL_UNPIN_PARTIAL salesforce 1/2 salesforce-development', out)
        self.assertNotIn('OFFICIAL_UNPINNED salesforce', out)

    def test_a_rerun_after_the_settings_were_unpinned_finishes_the_job(self):
        self.pinned_setup(declared={'source': 'github', 'repo': 'forcedotcom/sf-skills'})  # an earlier run's half
        out = self.run_setup('--unpin', 'salesforce:1.59.0')
        self.assertIn('OFFICIAL_UNPINNED salesforce', out)
        adds = [c for c in self.calls_made() if c[:3] == ['plugin', 'marketplace', 'add']]
        self.assertEqual([c[3] for c in adds], ['forcedotcom/sf-skills'])  # the declared form, as Claude requires

    def test_the_current_copy_wins_over_a_pinned_one_in_either_order(self):
        for order in ((('old', True), ('new', False)), (('new', False), ('old', True))):
            with self.subTest(order=[o for o, _ in order]):
                markets = [dict(self.PINNED, name=n) if pinned else {'name': n, 'source': 'git', 'url': 'https://github.com/forcedotcom/sf-skills.git'}
                           for n, pinned in order]
                rows = [{'id': '%s@%s' % (p, n), 'version': '2.3.0' if n == 'old' else '2.4.0', 'scope': 'user', 'enabled': True}
                        for p in PLUGINS for n, _ in order]
                self.configure(marketplaces=markets, plugins=rows)
                (self.config / 'settings.json').write_text(json.dumps({
                    'extraKnownMarketplaces': {n: {'source': {}} for n, _ in order},
                    'enabledPlugins': {r['id']: True for r in rows}}))
                out = self.run_setup()
                self.assertFalse(any(l.startswith('OFFICIAL_PINNED') for l in out))  # an unused pin is left alone
                self.assertEqual(sorted(l for l in out if l.startswith('OFFICIAL_DUPLICATE')),
                                 sorted('OFFICIAL_DUPLICATE %s@old' % p for p in PLUGINS))
                out = self.run_setup('--disable-duplicates', *('%s@old' % p for p in PLUGINS))
                self.assertEqual(out[-1], 'OFFICIAL_READINESS ready')
                self.assertTrue(all(self.settings()['enabledPlugins']['%s@new' % p] for p in PLUGINS))

    def test_a_project_copy_is_reported_and_counts_as_a_conflict_there(self):
        self.run_setup()  # the five, from GitHub
        state = json.loads(self.state.read_text())
        state['plugins'].append({'id': 'salesforce-development@claude-plugins-official', 'version': '2.3.0', 'scope': 'user',
                                 'enabled': False})
        self.state.write_text(json.dumps(state))
        self.configure(**state)
        workspace = self.root / 'ws'
        (workspace / '.claude').mkdir(parents=True)
        (workspace / '.claude/settings.json').write_text(json.dumps(
            {'enabledPlugins': {'salesforce-development@claude-plugins-official': True}}))
        out = self.run_setup('--workspace-settings', str(workspace / '.claude/settings.json'), '--launch-dir', str(workspace))
        self.assertIn('OFFICIAL_PROJECT_COPY salesforce-development@claude-plugins-official %s' % (workspace / '.claude/settings.json'), out)
        self.assertEqual(json.loads((workspace / '.claude/settings.json').read_text())['enabledPlugins'],
                         {'salesforce-development@claude-plugins-official': True})  # Scout never edits it

    def test_personal_copies_are_reported_never_moved(self):
        self.configure(catalog=['platform-apex-generate', 'consumer-goods-dashboard'])
        skills = self.root / '.claude/skills'
        (skills / 'platform-apex-generate').mkdir(parents=True)
        (skills / 'platform-apex-generate/SKILL.md').write_text('---\nname: platform-apex-generate\n---\n')
        shared = self.root / '.agents/skills/consumer-goods-dashboard'
        shared.mkdir(parents=True)
        (shared / 'SKILL.md').write_text('x')
        (skills / 'consumer-goods-dashboard').symlink_to(shared)
        (skills / 'my-own-skill').mkdir()
        (skills / 'my-own-skill/SKILL.md').write_text('x')
        out = self.run_setup()
        self.assertIn('OFFICIAL_PERSONAL_COPIES 2 %s' % skills, out)
        self.assertTrue((skills / 'platform-apex-generate/SKILL.md').is_file())  # nothing moved
        self.assertTrue((skills / 'consumer-goods-dashboard').is_symlink())
        import shutil
        shutil.rmtree(self.config / 'plugins/marketplaces')  # no clone to read the catalog from
        self.assertTrue(any(l.startswith('OFFICIAL_PERSONAL_COPIES_UNKNOWN') for l in self.run_setup()))


class TakeoverBindingTests(PinnedFixture):
    """The takeover: execution bound to the approved list (D1), compare-and-set recovery (D2), retries (D3),
    the launch folder (D5), unused pins (D6) and read-backs (D7)."""

    def test_every_update_belongs_to_the_approved_list(self):
        self.pinned_setup(plugins=('salesforce-development',))
        proposal = next(l for l in self.run_setup() if l.startswith('OFFICIAL_PINNED'))
        listed = set(proposal.split()[3].split(','))
        self.assertEqual(listed, set(PLUGINS))  # the run's own installs are in the list
        calls = len(self.calls_made())
        self.run_setup('--unpin', 'salesforce:1.59.0')
        updated = {c[2].rpartition('@')[0] for c in self.calls_made()[calls:] if c[:2] == ['plugin', 'update']}
        self.assertEqual(updated, listed)

    def test_an_approval_for_a_different_ref_changes_nothing(self):
        self.pinned_setup()
        out = self.run_setup('--unpin', 'salesforce:1.58.0')
        self.assertIn('OFFICIAL_UNPIN_SKIPPED salesforce now fixed to 1.59.0, not the approved 1.58.0: nothing changed', out)
        self.assertEqual(self.settings()['extraKnownMarketplaces']['salesforce']['source']['ref'], '1.59.0')

    def test_an_approved_duplicate_that_became_the_selected_copy_is_never_swapped(self):
        markets = [dict(self.PINNED, name='a'), {'name': 'b', 'source': 'git', 'url': 'https://github.com/forcedotcom/sf-skills.git'}]
        rows = ([{'id': '%s@a' % p, 'version': '2.3.0', 'scope': 'user', 'enabled': True} for p in PLUGINS]
                + [{'id': 'experience-lwc@b', 'version': '0.2.0', 'scope': 'user', 'enabled': True}])
        self.configure(marketplaces=markets, plugins=rows)
        (self.config / 'settings.json').write_text(json.dumps({
            'extraKnownMarketplaces': {'a': {'source': dict(self.PINNED)}, 'b': {'source': {'source': 'git', 'url': 'https://github.com/forcedotcom/sf-skills.git'}}},
            'enabledPlugins': {r['id']: True for r in rows}}))
        out = self.run_setup()
        self.assertIn('OFFICIAL_DUPLICATE experience-lwc@a', out)  # b follows the latest, so b's copy is kept
        self.assertTrue(any(l.startswith('OFFICIAL_PINNED a 1.59.0') for l in out))
        out = self.run_setup('--unpin', 'a:1.59.0', '--disable-duplicates', 'experience-lwc@a')
        disables = [c[2] for c in self.calls_made() if c[:2] == ['plugin', 'disable']]
        self.assertNotIn('experience-lwc@b', disables)  # never a copy that wasn't approved
        self.assertTrue('OFFICIAL_DUPLICATE_DISABLED experience-lwc@a' in out or
                        'OFFICIAL_DUPLICATE_SKIPPED experience-lwc@a no longer an extra copy: nothing changed' in out)

    def test_a_newer_se_choice_survives_a_failed_takeover(self):
        self.pinned_setup(readd_save_ref='1.60.0')
        out = self.run_setup('--unpin', 'salesforce:1.59.0')
        self.assertTrue(any('the settings changed meanwhile, so they were kept as saved; the takeover is incomplete' in l for l in out))
        self.assertEqual(self.settings()['extraKnownMarketplaces']['salesforce']['source']['ref'], '1.60.0')

    def test_a_registry_changed_before_the_failure_is_reported_incomplete(self):
        self.pinned_setup(readd_mutate_fail=True)
        out = self.run_setup('--unpin', 'salesforce:1.59.0')
        line = next(l for l in out if l.startswith('OFFICIAL_UNPIN_FAILED'))
        self.assertIn("the setting is fixed to 1.59.0 again, but the marketplace isn't listed as before: rerun /scout-setup", line)

    def test_a_partial_takeover_is_finished_by_its_retry(self):
        self.pinned_setup(update_fail=['salesforce-development@salesforce'])
        self.run_setup()  # the proposal run installs the rest first
        self.assertIn('OFFICIAL_UNPIN_PARTIAL salesforce 4/5 salesforce-development', self.run_setup('--unpin', 'salesforce:1.59.0'))
        state = json.loads(self.state.read_text())
        state['update_fail'] = []
        self.state.write_text(json.dumps(state))
        out = self.run_setup('--unpin', 'salesforce')  # the retry the partial line gives: both refs are gone now
        self.assertIn('OFFICIAL_PLUGIN_UPDATED salesforce-development 2.3.0 2.4.0', out)
        self.assertIn('OFFICIAL_UNPINNED salesforce', out)

    def test_an_unused_pinned_registration_is_never_proposed(self):
        markets = [dict(self.PINNED, name='first'), dict(self.PINNED, name='second', ref='1.60.0')]
        rows = [{'id': '%s@second' % p, 'version': '2.3.0', 'scope': 'user', 'enabled': True} for p in PLUGINS]
        self.configure(marketplaces=markets, plugins=rows)
        (self.config / 'settings.json').write_text(json.dumps({
            'extraKnownMarketplaces': {'first': {'source': dict(self.PINNED)}, 'second': {'source': dict(self.PINNED, ref='1.60.0')}},
            'enabledPlugins': {r['id']: True for r in rows}}))
        out = self.run_setup()
        self.assertEqual([l.split()[1] for l in out if l.startswith('OFFICIAL_PINNED')], ['second'])

    def test_the_launch_folder_not_the_workspace_decides_project_copies(self):
        self.run_setup()
        state = json.loads(self.state.read_text())
        state['plugins'].append({'id': 'salesforce-development@claude-plugins-official', 'version': '2.3.0', 'scope': 'user', 'enabled': False})
        self.configure(**state)
        launch, workspace = self.root / 'customer-project', self.root / 'scout-ws'
        for folder in (launch, workspace):
            (folder / '.claude').mkdir(parents=True)
        (launch / '.claude/settings.json').write_text(json.dumps(
            {'enabledPlugins': {'salesforce-development@claude-plugins-official': True, 'ghost@nowhere': True}}))
        (workspace / '.claude/settings.json').write_text('{}')
        out = self.run_setup('--workspace-settings', str(workspace / '.claude/settings.json'), '--launch-dir', str(launch))
        self.assertIn('OFFICIAL_PROJECT_COPY salesforce-development@claude-plugins-official %s' % (launch / '.claude/settings.json'), out)
        self.assertFalse(any('ghost' in l for l in out))  # switched on, but installed nowhere: not a copy
        self.assertEqual(out[-1], 'OFFICIAL_READINESS blocked salesforce-development:conflict')  # judged for that folder
        out = self.run_setup('--workspace-settings', str(workspace / '.claude/settings.json'), '--launch-dir', str(workspace))
        self.assertEqual(out[-1], 'OFFICIAL_READINESS ready')


class LoadedSetup(unittest.TestCase):
    """The setup script loaded in-process, for its helpers."""
    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('setup_official_under_test', SCRIPT)
        self.setup = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.setup
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(self.setup)


class BudgetTests(LoadedSetup):
    """Every `claude` call shares one budget inside the callers' 10-minute timeout; running out says so."""
    def test_each_call_gets_what_is_left_of_the_budget(self):
        self.assertTrue(540 <= self.setup.BUDGET < 600)  # room for a slow download, inside the callers' 10 minutes
        seen = []
        def run(*args, **kwargs):
            seen.append(kwargs['timeout'])
            return subprocess.CompletedProcess(args[0], 0, '{"outcome": "ok"}', '')
        with unittest.mock.patch.object(self.setup.subprocess, 'run', run):
            self.assertEqual(self.setup.claude_json('claude', ['plugin', 'list']), (0, {'outcome': 'ok'}))
            self.setup.STARTED -= self.setup.BUDGET - 100
            self.setup.claude_json('claude', ['plugin', 'list'])
        self.assertGreater(seen[0], self.setup.BUDGET - 60)
        self.assertLessEqual(seen[1], 100)

    def test_a_timeout_and_an_exhausted_budget_are_reported_as_such(self):
        def slow(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], kwargs['timeout'])
        with unittest.mock.patch.object(self.setup.subprocess, 'run', slow):
            code, data = self.setup.claude_json('claude', ['plugin', 'marketplace', 'add', 'x'])
        self.assertEqual((code, self.setup.message(data)), (None, 'timed out, possibly on a slow network'))
        self.setup.STARTED -= self.setup.BUDGET
        code, data = self.setup.claude_json('claude', ['plugin', 'list'])
        self.assertEqual((code, self.setup.message(data)), (None, 'setup ran out of time'))


class RunningClientProbeTests(LoadedSetup):
    """A running client that can't be identified (timeout, launch error, failure) is skipped for the PATH's claude."""
    def test_a_probe_that_fails_falls_back_to_the_path(self):
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], kwargs['timeout'])
        def unlaunchable(*args, **kwargs):
            raise OSError('exec format error')
        def failing(*args, **kwargs):
            return subprocess.CompletedProcess(args[0], 1, '2.1.295 (Claude Code)\n', '')
        for probe in (timeout, unlaunchable, failing):
            with self.subTest(probe=probe.__name__), \
                    unittest.mock.patch.dict(os.environ, {'CLAUDE_CODE_EXECPATH': sys.executable}), \
                    unittest.mock.patch.object(self.setup.subprocess, 'run', probe), \
                    unittest.mock.patch.object(self.setup.shutil, 'which', lambda name: '/path/to/claude'):
                self.assertEqual(self.setup.find_claude(), '/path/to/claude')

    def test_the_marketplace_list_failure_keeps_its_reason(self):
        def slow(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], kwargs['timeout'])
        with unittest.mock.patch.object(self.setup.subprocess, 'run', slow):
            self.assertEqual(self.setup.find_marketplace('claude', 'https://github.com/forcedotcom/sf-skills.git'),
                             (None, 'timed out, possibly on a slow network'))
            self.assertEqual(self.setup.installed('claude'), 'timed out, possibly on a slow network')


class SettingsHelperTests(unittest.TestCase):
    def helper_module(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('setup_settings_under_test', SETTINGS)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module  # Python 3.9's dataclasses look the module up there
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(module)
        return module

    def test_unpin_and_repin_touch_only_the_ref(self):
        module = self.helper_module()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp).resolve() / 'settings.json'
            entry = {'source': {'source': 'github', 'repo': 'forcedotcom/sf-skills', 'ref': '1.59.0'}, 'autoUpdate': True}
            path.write_text(json.dumps({'extraKnownMarketplaces': {'salesforce': entry}, 'theme': 'dark'}))
            self.assertEqual(module.run_marketplace_ref(path, 'salesforce', None), 'UNPIN_SET[settings.json]')
            data = json.loads(path.read_text())
            self.assertEqual(data['extraKnownMarketplaces']['salesforce'],
                             {'source': {'source': 'github', 'repo': 'forcedotcom/sf-skills'}, 'autoUpdate': True})
            self.assertEqual(data['theme'], 'dark')
            self.assertEqual(module.run_marketplace_ref(path, 'salesforce', None), 'UNPIN_ALREADY[settings.json]')
            self.assertEqual(module.run_marketplace_ref(path, 'salesforce', '1.59.0'), 'REPIN_SET[settings.json]')
            self.assertEqual(json.loads(path.read_text())['extraKnownMarketplaces']['salesforce']['source']['ref'], '1.59.0')
            self.assertEqual(module.run_marketplace_ref(path, 'other', None), 'UNPIN_NO_ENTRY[settings.json]')

    def test_backups_from_the_same_second_and_process_never_collide(self):
        module = self.helper_module()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp).resolve() / 'settings.json'
            path.write_text(json.dumps({'extraKnownMarketplaces': {'salesforce': {'source': {'source': 'github', 'repo': 'x/y', 'ref': '1'}}}}))
            with unittest.mock.patch.object(module.time, 'strftime', return_value='same'), \
                    unittest.mock.patch.object(module.os, 'getpid', return_value=4242):
                self.assertEqual(module.run_marketplace_ref(path, 'salesforce', None), 'UNPIN_SET[settings.json]')
                self.assertEqual(module.run_marketplace_ref(path, 'salesforce', '1'), 'REPIN_SET[settings.json]')
            self.assertEqual(sorted(p.name for p in Path(temp).resolve().glob('settings.json.scout-bak-unpin-*')),
                             ['settings.json.scout-bak-unpin-same-4242', 'settings.json.scout-bak-unpin-same-4242-1'])

    def test_unpin_and_repin_are_compare_and_set(self):
        module = self.helper_module()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp).resolve() / 'settings.json'
            path.write_text(json.dumps({'extraKnownMarketplaces': {'salesforce': {'source': {'source': 'github', 'repo': 'x/y', 'ref': '2'}}}}))
            self.assertEqual(module.run_marketplace_ref(path, 'salesforce', None, expect_ref='1'), 'UNPIN_CHANGED[settings.json]')
            self.assertEqual(module.run_marketplace_ref(path, 'salesforce', None, expect_ref='2'), 'UNPIN_SET[settings.json]')
            other = {'source': 'github', 'repo': 'x/other'}
            self.assertEqual(module.run_marketplace_ref(path, 'salesforce', '2', expect_source=other), 'REPIN_CHANGED[settings.json]')
            self.assertEqual(module.run_marketplace_ref(path, 'salesforce', '2', expect_source={'source': 'github', 'repo': 'x/y'}),
                             'REPIN_SET[settings.json]')

    def test_a_concurrent_save_is_never_overwritten(self):
        module = self.helper_module()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp).resolve() / 'settings.json'
            path.write_text(json.dumps({'extraKnownMarketplaces': {'salesforce': {'source': {}}}}))
            real = Path.read_bytes
            def racing(self_path):
                content = real(self_path)
                if self_path == path and getattr(racing, 'calls', 0) == 1:
                    path.write_text('{"saved": "by the SE meanwhile"}')  # an editor saves between Scout's read and write
                    content = real(self_path)
                racing.calls = getattr(racing, 'calls', 0) + 1
                return content
            with unittest.mock.patch.object(Path, 'read_bytes', racing):
                outcome = module.run_marketplace_autoupdate(path, 'salesforce')
            self.assertEqual(outcome, 'AUTOUPDATE_CHANGED_MEANWHILE[settings.json]: rerun setup')
            self.assertEqual(json.loads(path.read_text()), {'saved': 'by the SE meanwhile'})

    def test_a_post_write_failure_restores_only_scouts_own_bytes(self):
        module = self.helper_module()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp).resolve() / 'settings.json'
            path.write_text('{"env": {}}')
            strict = module.load_strict_json
            calls = []
            def failing_after_write(raw):
                calls.append(raw)
                if len(calls) == 2:  # the validation of Scout's own write
                    raise module.SettingsError('validation failed')
                return strict(raw)
            with unittest.mock.patch.object(module, 'load_strict_json', failing_after_write):
                outcome = module.run_workspace_env(path, 'SF_DISABLE_PLUGIN_MATCH')
            self.assertTrue(outcome.startswith('ENV_POST_WRITE_FAILED[settings.json]: original restored'), outcome)
            self.assertEqual(path.read_text(), '{"env": {}}')

    def test_a_newer_save_after_the_write_survives_a_failed_validation(self):
        module = self.helper_module()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp).resolve() / 'settings.json'
            path.write_text('{"env": {}}')
            strict = module.load_strict_json
            calls = []
            def save_then_fail(raw):
                calls.append(raw)
                if len(calls) == 2:  # Scout's write landed; the SE's editor saves before validation fails
                    path.write_text('{"saved": "by the SE after Scout"}')
                    raise module.SettingsError('validation failed')
                return strict(raw)
            with unittest.mock.patch.object(module, 'load_strict_json', save_then_fail):
                outcome = module.run_workspace_env(path, 'SF_DISABLE_PLUGIN_MATCH')
            self.assertTrue(outcome.startswith('ENV_POST_WRITE_FAILED[settings.json]: left as found'), outcome)
            self.assertEqual(json.loads(path.read_text()), {'saved': 'by the SE after Scout'})
            backups = list(Path(temp).resolve().glob('settings.json.scout-bak-env-*'))
            self.assertEqual([b.read_text() for b in backups], ['{"env": {}}'])

    def test_a_full_disk_leaves_the_file_and_no_temporary(self):
        module = self.helper_module()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp).resolve()
            path = folder / 'settings.json'
            path.write_text('{"env": {}}')
            def no_space(*args):
                raise OSError(28, 'No space left on device')
            with unittest.mock.patch.object(module.os, 'fsync', no_space):
                outcome = module.run_workspace_env(path, 'SF_DISABLE_PLUGIN_MATCH')
            self.assertTrue(outcome.startswith('ENV_WRITE_FAILED[settings.json]'), outcome)
            self.assertEqual(path.read_text(), '{"env": {}}')
            self.assertEqual([p.name for p in folder.iterdir() if p.name.startswith('.settings.json.')], [])

    def test_repeated_repairs_keep_every_backup(self):
        module = self.helper_module()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp).resolve() / 'settings.json'
            path.write_text('{}')
            self.assertEqual(module.run_workspace_env(path, 'SF_DISABLE_PLUGIN_MATCH'), 'ENV_SET[settings.json]')
            path.write_text('{"env": {"SF_DISABLE_PLUGIN_MATCH": "0"}}')
            with unittest.mock.patch.object(module.time, 'strftime', return_value='later'):
                self.assertEqual(module.run_workspace_env(path, 'SF_DISABLE_PLUGIN_MATCH'), 'ENV_SET[settings.json]')
            self.assertEqual(len(list(Path(temp).resolve().glob('settings.json.scout-bak-env-*'))), 2)
            self.assertEqual(json.loads(path.read_text())['env']['SF_DISABLE_PLUGIN_MATCH'], '1')

    def run_helper(self, *args):
        result = subprocess.run([sys.executable, '-B', str(SETTINGS), *args], capture_output=True, text=True, timeout=60)
        return result.stdout.strip()

    def test_only_allowlisted_workspace_env_keys(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp).resolve()  # the helper refuses symlinked ancestors, such as macOS's /var
            path = temp / 'settings.json'
            path.write_text('{}')
            self.assertEqual(self.run_helper('workspace-env', '--settings', str(path), '--key', 'ANTHROPIC_MODEL'),
                             'ENV_KEY_NOT_ALLOWED[ANTHROPIC_MODEL]')
            self.assertEqual(path.read_text(), '{}')
            self.assertEqual(self.run_helper('marketplace-autoupdate', '--settings', str(temp / 'absent.json')),
                             'AUTOUPDATE_ABSENT[absent.json]')


if __name__ == '__main__':
    unittest.main()
