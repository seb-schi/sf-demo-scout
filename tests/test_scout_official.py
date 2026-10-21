"""The official-plugin resolver, readiness check, skill verification and coexistence check, tested against
synthetic Claude config folders and a fake `sf`."""
import contextlib
import json
import os
import shutil
import subprocess
import types
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import scout_official as official
import stand_ins

GITHUB = {'source': 'git', 'url': 'https://github.com/forcedotcom/sf-skills.git'}
ANTHROPIC = {'source': 'github', 'repo': 'anthropics/claude-plugins-official'}
FAKE_SF = r'''
import json, os, sys
args = sys.argv[1:]
if args[:3] == ['config', 'get', 'target-org']:
    value = os.environ.get('FAKE_DEFAULT', '')
    row = {'name': 'target-org', 'value': value, 'location': os.environ.get('FAKE_LOCATION', 'Local')}
    print(json.dumps({'status': 0, 'result': [row] if value else []}))
    sys.exit(int(os.environ.get('FAKE_CONFIG_EXIT', '0')))
elif args[:2] == ['org', 'display']:
    ok = args[args.index('--target-org') + 1] in os.environ.get('FAKE_REACHABLE', '').split(',')
    empty = os.environ.get('FAKE_EMPTY_DISPLAY') == '1'
    print(json.dumps({'status': 0 if ok else 1, 'result': {} if empty else {'id': '00D000000000001'}}))
    sys.exit(0 if ok else 1)
'''


class Fixture(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='scout-official-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.config = self.root / 'claude'
        (self.config / 'plugins').mkdir(parents=True)
        patcher = patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(self.config), **stand_ins.home(self.root)}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        for key in ('SCOUT_OFFICIAL_SOURCE', 'SCOUT_OFFICIAL_SKILLS_ROOT', 'SF_DISABLE_PLUGIN_MATCH',
                    'SF_PLUGIN_MATCH_SENSITIVITY', 'SF_TARGET_ORG', 'SFDX_TARGET_ORG', 'SFDX_AUTO_DEPLOY'):
            os.environ.pop(key, None)
        self.known, self.installed, self.enabled = {}, {}, {}
        self.write()

    def plugin_dir(self, provider, plugin, skills=(), files=()):
        root = self.root / 'cache' / provider / plugin
        root.mkdir(parents=True, exist_ok=True)
        for skill in skills:
            (root / 'skills' / skill).mkdir(parents=True, exist_ok=True)
            (root / 'skills' / skill / 'SKILL.md').write_text('---\nname: %s\n---\n' % skill)
        for name in files:
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text('x')
        return root

    def register(self, marketplace, source, plugin, root, scope='user', enabled=True):
        self.known[marketplace] = {'source': source, 'installLocation': str(self.root / marketplace)}
        self.installed.setdefault('%s@%s' % (plugin, marketplace), []).append(
            {'scope': scope, 'installPath': str(root), 'version': '2.4.0'})
        if enabled is not None:
            self.enabled['%s@%s' % (plugin, marketplace)] = enabled
        self.write()

    def write(self):
        (self.config / 'plugins/known_marketplaces.json').write_text(json.dumps(self.known))
        (self.config / 'plugins/installed_plugins.json').write_text(json.dumps({'version': 2, 'plugins': self.installed}))
        (self.config / 'settings.json').write_text(json.dumps({'enabledPlugins': self.enabled}))


class ResolverTests(Fixture):
    def test_only_salesforces_github_installation_counts_under_any_name(self):
        anthropic = self.plugin_dir('anthropic', 'salesforce-development')
        self.register('claude-plugins-official', ANTHROPIC, 'salesforce-development', anthropic)
        found = official.resolve('salesforce-development')
        self.assertEqual(found['state'], 'setup-needed')  # Anthropic's copy is never a fallback
        self.assertIsNone(official.installation('salesforce-development'))
        github = self.plugin_dir('github', 'salesforce-development')
        self.register('sf-skills', GITHUB, 'salesforce-development', github)
        found = official.resolve('salesforce-development')
        self.assertEqual((found['state'], found['ident']), ('conflict', 'salesforce-development@sf-skills'))
        self.assertIn('salesforce-development@claude-plugins-official', found['reason'])
        self.enabled['salesforce-development@claude-plugins-official'] = False
        self.write()
        found = official.resolve('salesforce-development')
        self.assertEqual((found['state'], found['provider'], found['root']), ('installed', 'salesforce-github', str(github)))

    def test_every_supported_github_form_is_the_same_source(self):
        forms = ['https://github.com/forcedotcom/sf-skills.git', 'https://github.com/forcedotcom/sf-skills',
                 'https://github.com/ForceDotCom/sf-skills/', 'git@github.com:forcedotcom/sf-skills.git',
                 'ssh://git@github.com/forcedotcom/sf-skills.git', 'forcedotcom/sf-skills']
        self.assertEqual({official.normalize(form) for form in forms}, {'github.com/forcedotcom/sf-skills'})
        self.assertNotEqual(official.normalize('https://github.com/someone/sf-skills'), official.normalize(forms[0]))
        root = self.plugin_dir('github', 'salesforce-development')
        self.register('salesforce', {'source': 'github', 'repo': 'forcedotcom/sf-skills'}, 'salesforce-development', root)
        self.assertEqual(official.resolve('salesforce-development')['state'], 'installed')

    def test_switched_off_project_scoped_and_missing_installations(self):
        root = self.plugin_dir('github', 'salesforce-development')
        self.register('salesforce', GITHUB, 'salesforce-development', root, scope='project')
        self.assertEqual(official.resolve('salesforce-development')['state'], 'installable')  # repairable, core or not
        self.installed.clear()
        self.enabled.clear()
        self.register('salesforce', GITHUB, 'salesforce-development', root, enabled=None)
        self.assertEqual(official.resolve('salesforce-development')['state'], 'disabled')  # no `true`: not loaded
        self.assertEqual(official.resolve('experience-lwc'),
                         {'state': 'installable', 'ident': 'experience-lwc@salesforce'})  # an optional plugin

    def test_unreadable_records_are_unknown_never_absent(self):
        (self.config / 'plugins/installed_plugins.json').write_text('{not json')
        self.assertEqual(official.resolve('salesforce-development'), {'state': 'unknown'})
        self.assertEqual(official.check(['soql'])['soql']['state'], 'unknown')

    def codex(self, enabled=True, versions=('0.4.0',), source='https://github.com/forcedotcom/sf-skills.git'):
        codex = self.root / '.codex'
        codex.mkdir(exist_ok=True)
        (codex / 'config.toml').write_text(
            '[marketplaces.salesforce]\nsource_type = "git"\nsource = "%s"\n\n'
            '[plugins."salesforce-development@salesforce"]\nenabled = %s  # a comment\n\n'
            '[projects."/somewhere"]\ntrust_level = "trusted"\n' % (source, 'true' if enabled else 'false'))
        for version in versions:
            skill = codex / 'plugins/cache/salesforce/salesforce-development' / version / 'skills/platform-soql-query'
            skill.mkdir(parents=True, exist_ok=True)
            (skill / 'SKILL.md').write_text('x')

    def test_codex_reads_its_own_installation_from_salesforces_marketplace(self):
        root = self.plugin_dir('github', 'salesforce-development', skills=['platform-soql-query'])
        self.register('salesforce', GITHUB, 'salesforce-development', root)  # Claude's records are never read on Codex
        self.assertEqual(official.check(['soql'], host='codex')['soql']['state'], 'setup-needed')
        for tomllib in (True, False):  # Python 3.11+ reads TOML itself; 3.9 and 3.10 use Scout's narrow reader
            with self.subTest(tomllib=tomllib), patch.dict(sys.modules, {} if tomllib else {'tomllib': None}):
                self.codex()
                report = official.check(['soql'], host='codex')['soql']
                found = report['plugins']['salesforce-development']
                self.assertEqual((report['state'], found['provider'], found['version']),
                                 ('installed', 'salesforce-github', '0.4.0'))
                self.assertEqual(Path(found['root']).parts[-6:],
                                 ('.codex', 'plugins', 'cache', 'salesforce', 'salesforce-development', '0.4.0'))
                self.codex(enabled=False)
                self.assertEqual(official.resolve('salesforce-development', host='codex')['state'], 'disabled')
                self.codex(source='https://github.com/someone/fork.git')
                self.assertEqual(official.resolve('salesforce-development', host='codex')['state'], 'setup-needed')
                self.assertEqual(official.resolve('experience-lwc', host='codex')['state'], 'setup-needed')
        self.codex(versions=('0.4.0', '0.5.0'))  # mid-upgrade: never guess
        self.assertEqual(official.resolve('salesforce-development', host='codex')['state'], 'unknown')
        self.codex()
        (self.root / '.codex' / 'config.toml').write_text('[marketplaces.salesforce\nbroken')
        self.assertEqual(official.resolve('salesforce-development', host='codex')['state'], 'unknown')
        # Ordinary TOML the narrow reader must still read on Python 3.9 and 3.10: comments after headers, literal strings.
        shutil.rmtree(self.root / '.codex/plugins/cache/salesforce/salesforce-development/0.5.0')  # the upgrade finished
        (self.root / '.codex' / 'config.toml').write_text(
            "[marketplaces.salesforce]  # Salesforce's skills\nsource = 'https://github.com/forcedotcom/sf-skills.git'\n"
            '[plugins."salesforce-development@salesforce"]\nenabled = true\n')
        with patch.dict(sys.modules, {'tomllib': None}):
            self.assertEqual(official.resolve('salesforce-development', host='codex')['state'], 'installed')
            (self.root / '.codex' / 'config.toml').write_text(  # whitespace inside the brackets is valid TOML
                "[ marketplaces.salesforce ]\nsource = 'https://github.com/forcedotcom/sf-skills.git'\n"
                '[ plugins."salesforce-development@salesforce" ]\nenabled = true\n')
            self.assertEqual(official.resolve('salesforce-development', host='codex')['state'], 'installed')
            for broken in ('[plugins."salesforce-development@salesforce"]\nenabled = [true]\n',
                           '[marketplaces.salesforce\nbroken', '[[plugins]]\nname = "x"\n',
                           'plugins."salesforce-development@salesforce".enabled = true\n',
                           'marketplaces = { salesforce = { source = "x" } }\n'):
                with self.subTest(broken=broken):
                    (self.root / '.codex' / 'config.toml').write_text(broken)
                    self.assertEqual(official.resolve('salesforce-development', host='codex')['state'], 'unknown')
        self.codex()
        project = self.root / 'work' / 'repo'
        (project / 'sub').mkdir(parents=True)
        (project / '.git').mkdir()  # the project root, as Codex finds it
        self.assertEqual(official.resolve('salesforce-development', host='codex', launch_dir=project / 'sub')['state'],
                         'installed')  # the user configuration in the home folder is never taken for a project's
        (project / '.codex').mkdir()
        (project / '.codex' / 'config.toml').write_text('[plugins."salesforce-development@salesforce"]\nenabled = false\n')
        found = official.resolve('salesforce-development', host='codex', launch_dir=project / 'sub')
        self.assertEqual((found['state'], found['reason']), ('unknown', "a project's Codex configuration also selects plugins"))
        for selection in ('plugins."salesforce-development@salesforce".enabled = false\n',
                          'marketplaces.salesforce = { source_type = "git", source = "https://github.com/forcedotcom/sf-skills.git" }\n',
                          '[marketplaces.salesforce]\nsource = "https://github.com/forcedotcom/sf-skills.git"\n'):
            with self.subTest(selection=selection):
                (project / '.codex' / 'config.toml').write_text(selection)
                self.assertEqual(official.resolve('salesforce-development', host='codex', launch_dir=project)['state'],
                                 'unknown')

    def test_a_named_or_recorded_checkout_serves_codex_and_cursor(self):
        checkout = self.root / 'sf-skills'
        (checkout / 'plugins/builder/salesforce-development/skills/platform-soql-query').mkdir(parents=True)
        (checkout / 'plugins/builder/salesforce-development/skills/platform-soql-query/SKILL.md').write_text('x')
        self.assertEqual(official.check(['soql'], host='cursor')['soql']['state'], 'setup-needed')
        with patch.dict(os.environ, {'SCOUT_OFFICIAL_SKILLS_ROOT': str(checkout)}):
            for host in ('codex', 'cursor'):
                report = official.check(['soql'], host=host)['soql']
                self.assertEqual((report['state'], report['plugins']['salesforce-development']['provider']),
                                 ('installed', 'local-checkout'))
            self.assertEqual(official.check(['email-to-case'], host='codex')['email-to-case']['state'], 'missing')
        record = self.root / '.config' / 'sf-demo-scout' / 'official-skills.json'
        record.parent.mkdir(parents=True)
        record.write_text(json.dumps({'root': str(checkout)}))  # what Scout's installer writes
        self.assertEqual(official.check(['soql'], host='cursor')['soql']['state'], 'installed')
        self.assertEqual(official.resolve('salesforce-development', host='codex')['provider'], 'local-checkout')
        self.codex()  # once Codex has its own installation, it comes first; a clone recorded for Cursor doesn't override it
        self.assertEqual(official.resolve('salesforce-development', host='codex')['provider'], 'salesforce-github')
        self.assertEqual(official.resolve('salesforce-development', host='cursor')['provider'], 'local-checkout')

    def test_the_trial_mode_accepts_a_named_local_source(self):
        clone = self.root / 'clone'
        clone.mkdir()
        root = self.plugin_dir('local', 'salesforce-code-quality', skills=['dx-code-analyzer-run'])
        self.register('local-test', {'source': 'directory', 'path': str(clone)}, 'salesforce-code-quality', root)
        self.assertEqual(official.check(['code-analyzer'])['code-analyzer']['state'], 'setup-needed')
        with patch.dict(os.environ, {'SCOUT_OFFICIAL_SOURCE': str(clone)}):
            self.assertEqual(official.check(['code-analyzer'])['code-analyzer']['state'], 'installed')


class RecordShapeTests(Fixture):
    def test_malformed_relevant_records_are_unknown_never_absent(self):
        root = self.plugin_dir('github', 'salesforce-development')
        self.register('salesforce', GITHUB, 'salesforce-development', root)
        self.installed['experience-lwc@salesforce'] = 'bad-record'
        self.write()
        self.assertEqual(official.resolve('experience-lwc'), {'state': 'unknown'})
        self.installed['experience-lwc@salesforce'] = [{'scope': 'user'}]  # no installPath
        self.write()
        self.assertEqual(official.resolve('experience-lwc'), {'state': 'unknown'})
        del self.installed['experience-lwc@salesforce']
        self.enabled['salesforce-development@salesforce'] = 'yes'
        self.write()
        self.assertEqual(official.resolve('salesforce-development'), {'state': 'unknown'})
        (self.config / 'settings.json').write_text(json.dumps({'enabledPlugins': ['salesforce-development@salesforce']}))
        self.assertEqual(official.resolve('salesforce-development'), {'state': 'unknown'})
        self.enabled = {'salesforce-development@salesforce': None}  # an explicit null is malformed, not "off"
        self.write()
        self.assertEqual(official.resolve('salesforce-development'), {'state': 'unknown'})
        self.enabled = {'salesforce-development@salesforce': True}
        self.installed['experience-lwc@salesforce'] = None  # nor is a null installation "absent"
        self.write()
        self.assertEqual(official.resolve('experience-lwc'), {'state': 'unknown'})

    def test_one_enabled_registration_among_several_is_chosen(self):
        old = self.plugin_dir('old', 'salesforce-development')
        new = self.plugin_dir('new', 'salesforce-development')
        self.register('old', GITHUB, 'salesforce-development', old, enabled=False)
        self.register('new', {'source': 'github', 'repo': 'forcedotcom/sf-skills'}, 'salesforce-development', new)
        found = official.resolve('salesforce-development')
        self.assertEqual((found['state'], found['ident']), ('installed', 'salesforce-development@new'))
        self.enabled['salesforce-development@old'] = True
        self.write()
        self.assertEqual(official.resolve('salesforce-development')['state'], 'conflict')

    def test_email_to_case_needs_each_of_its_files(self):
        files = ['skills/service-email-to-case-configure/scripts/validate-casesettings.py',
                 'skills/service-email-to-case-configure/scripts/apply-casesettings.py',
                 'skills/service-email-to-case-configure/assets/CaseSettings.settings-meta.xml']
        root = self.plugin_dir('github', 'service-engagement', skills=['service-email-to-case-configure'])
        (root / 'skills/service-email-to-case-configure/scripts').mkdir(parents=True)
        self.register('salesforce', GITHUB, 'service-engagement', root)
        self.assertEqual(official.check(['email-to-case'])['email-to-case']['state'], 'missing')  # an empty scripts folder
        for name in files:
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text('x')
        self.assertEqual(official.check(['email-to-case'])['email-to-case']['state'], 'installed')
        for name in files:
            with self.subTest(removed=name):
                (root / name).rename(root / (name + '.gone'))
                self.assertEqual(official.check(['email-to-case'])['email-to-case']['missing'], ['service-engagement:' + name])
                (root / (name + '.gone')).rename(root / name)

    def test_inspect_keeps_each_plugins_identity_and_the_checks(self):
        root = self.plugin_dir('github', 'salesforce-development', skills=['platform-soql-query'])
        self.register('salesforce', GITHUB, 'salesforce-development', root)
        with patch.object(official, 'coexistence', return_value=([], {'deploy-gate': 'ok'})):
            result = official.inspect(official.check(['soql', 'lwc']), 'claude', self.root)
        self.assertEqual(result['plugins']['salesforce-development'],
                         {'state': 'installed', 'provider': 'salesforce-github', 'root': str(root), 'version': '2.4.0',
                          'ident': 'salesforce-development@salesforce'})
        self.assertEqual(result['plugins']['experience-lwc'], {'state': 'installable', 'ident': 'experience-lwc@salesforce'})
        self.assertEqual((result['ready'], result['checks']), (['soql'], {'deploy-gate': 'ok'}))
        self.assertEqual(result['optional']['service-omni']['state'], 'installable')  # offered for its area, not installed
        self.assertIn('Omni-Channel', result['optional']['service-omni']['area'])
        self.assertNotIn('dx-org-lifecycle', result['optional'])  # never offered


class TakeoverDetectionTests(Fixture):
    """W20-T detection: pinned registrations, the copy that follows the latest, the launch folder's own settings and
    installs, and possible personal copies (report-only)."""
    PINNED = {'source': 'github', 'repo': 'forcedotcom/sf-skills', 'ref': '1.59.0'}

    def test_a_pin_is_carried_and_the_unpinned_copy_wins(self):
        for order in (('old', 'new'), ('new', 'old')):
            with self.subTest(order=order):
                self.known, self.installed, self.enabled = {}, {}, {}
                for name in order:
                    root = self.plugin_dir(name, 'salesforce-development')
                    self.register(name, self.PINNED if name == 'old' else GITHUB, 'salesforce-development', root)
                found = official.resolve('salesforce-development')
                self.assertEqual((found['state'], found['ident']), ('conflict', 'salesforce-development@new'))
                self.assertEqual(found['others'], ['salesforce-development@old'])
        self.enabled['salesforce-development@new'] = False
        self.write()
        self.assertEqual(official.resolve('salesforce-development')['pinned'], '1.59.0')  # only the pinned copy is on
        self.known['old']['source']['ref'] = 'main'
        self.write()
        self.assertNotIn('pinned', official.resolve('salesforce-development'))  # following main is following the latest

    def test_the_launch_folders_own_settings_and_installs_count(self):
        github = self.plugin_dir('github', 'salesforce-development', skills=['platform-soql-query'])
        anthropic = self.plugin_dir('anthropic', 'salesforce-development', skills=['platform-soql-query'])
        self.register('salesforce', GITHUB, 'salesforce-development', github)
        self.register('claude-plugins-official', ANTHROPIC, 'salesforce-development', anthropic, enabled=False)
        folder = self.root / 'project'
        (folder / '.claude').mkdir(parents=True)
        (folder / '.claude/settings.json').write_text(json.dumps({'enabledPlugins': {'salesforce-development@claude-plugins-official': True}}))
        self.assertEqual(official.check(['soql'])['soql']['state'], 'installed')  # user settings alone
        report = official.check(['soql'], launch_dir=folder)['soql']
        self.assertEqual(report['state'], 'conflict')  # that folder switches the other copy on
        self.assertEqual(report['plugins']['salesforce-development']['switched_on_in'],
                         {'salesforce-development@claude-plugins-official': str(folder / '.claude/settings.json')})
        (folder / '.claude/settings.local.json').write_text(json.dumps({'enabledPlugins': {'salesforce-development@claude-plugins-official': False}}))
        self.assertEqual(official.check(['soql'], launch_dir=folder)['soql']['state'], 'installed')  # the local file wins
        self.installed['salesforce-development@claude-plugins-official'].append(
            {'scope': 'project', 'projectPath': str(folder), 'installPath': str(anthropic), 'version': '2.3.0'})
        self.installed['salesforce-development@claude-plugins-official'] = [r for r in self.installed['salesforce-development@claude-plugins-official'] if r['scope'] == 'project']
        self.enabled['salesforce-development@claude-plugins-official'] = True
        self.write()
        (folder / '.claude/settings.local.json').unlink()
        self.assertEqual(official.check(['soql'], launch_dir=folder)['soql']['state'], 'conflict')  # a project install for it
        self.assertEqual(official.check(['soql'], launch_dir=self.root / 'elsewhere')['soql']['state'], 'installed')

    def test_personal_copies_are_bounded_reported_and_unknown_without_a_catalog(self):
        root = self.plugin_dir('github', 'salesforce-development', skills=['platform-soql-query'])
        self.register('salesforce', GITHUB, 'salesforce-development', root)
        records = official.Records(official.capability_map())
        self.assertIsNone(official.personal_copies(self.root, records))  # no clone, no catalog: unknown, not zero
        clone = Path(self.known['salesforce']['installLocation'])
        for skill in ('platform-soql-query', 'consumer-goods-dashboard'):
            (clone / 'skills' / skill).mkdir(parents=True, exist_ok=True)
            (clone / 'skills' / skill / 'SKILL.md').write_text('x')
        personal = self.root / '.claude/skills'
        (personal / 'consumer-goods-dashboard').mkdir(parents=True)
        (personal / 'consumer-goods-dashboard/SKILL.md').write_text('x')
        (personal / 'my-own').mkdir()
        (personal / 'my-own/SKILL.md').write_text('x')
        other = self.root / 'other-project/.claude/skills/platform-soql-query'
        other.mkdir(parents=True)
        (other / 'SKILL.md').write_text('x')
        found = official.personal_copies(self.root / 'launch', official.Records(official.capability_map()))
        self.assertEqual([c['name'] for c in found], ['consumer-goods-dashboard'])  # never another project's folder
        with patch.object(official, 'coexistence', return_value=([], {})):
            result = official.inspect(official.check(['soql']), 'claude', self.root / 'launch')
        self.assertEqual(result['notes']['personal_copies'], {'count': 1, 'folders': [str(personal)]})


class CheckTests(Fixture):
    def test_capability_states_name_what_is_missing_and_the_action(self):
        root = self.plugin_dir('github', 'salesforce-development', skills=['platform-report-generate'])
        self.register('salesforce', GITHUB, 'salesforce-development', root)
        report = official.check(['report', 'flow', 'agentforce', 'nonsense'])
        self.assertEqual(report['report']['state'], 'missing')
        self.assertEqual(sorted(report['report']['missing']), [
            'salesforce-development:platform-custom-report-type-generate',
            'salesforce-development:skills/platform-report-generate/references/column-names.md'])
        self.assertEqual(report['flow']['state'], 'installed')  # Scout's own sf-flow ships with Scout
        self.assertEqual((report['agentforce']['state'], report['agentforce']['action']),
                         ('installable', official.ACTIONS['installable']))
        self.assertEqual(report['nonsense'], {'state': 'unknown-capability'})
        self.plugin_dir('github', 'salesforce-development', skills=['platform-custom-report-type-generate'],
                        files=['skills/platform-report-generate/references/column-names.md'])
        self.assertEqual(official.check(['report'])['report']['state'], 'installed')

    def test_the_worst_plugin_state_wins(self):
        root = self.plugin_dir('github', 'salesforce-development', skills=['platform-apex-generate'])
        self.register('salesforce', GITHUB, 'salesforce-development', root)
        lwc = self.plugin_dir('github', 'experience-lwc', skills=['experience-lwc-generate'])
        self.register('salesforce', GITHUB, 'experience-lwc', lwc, enabled=False)
        data = official.capability_map()
        data['capabilities']['both'] = {'skills': ['salesforce-development:platform-apex-generate',
                                                   'experience-lwc:experience-lwc-generate',
                                                   'agentforce-adlc:agentforce-generate']}
        with patch.object(official, 'capability_map', return_value=data):
            report = official.check(['both'])['both']
        self.assertEqual({p: i['state'] for p, i in report['plugins'].items()},
                         {'salesforce-development': 'installed', 'experience-lwc': 'disabled', 'agentforce-adlc': 'installable'})
        self.assertEqual(report['state'], 'disabled')  # disabled is worse than installable, which is worse than installed


class VerifyTests(Fixture):
    def test_a_loaded_skill_must_come_from_the_resolved_installation(self):
        github = self.plugin_dir('github', 'salesforce-development', skills=['platform-soql-query'])
        anthropic = self.plugin_dir('anthropic', 'salesforce-development', skills=['platform-soql-query'])
        self.register('salesforce', GITHUB, 'salesforce-development', github)
        self.register('claude-plugins-official', ANTHROPIC, 'salesforce-development', anthropic, enabled=False)
        loaded = github / 'skills/platform-soql-query'
        self.assertEqual(official.verify('salesforce-development', str(loaded))['state'], 'verified')
        other = official.verify('salesforce-development', str(anthropic / 'skills/platform-soql-query'))
        self.assertEqual((other['state'], other['expected']), ('conflict', str(github)))

    def test_a_folder_sourced_marketplace_loads_skills_in_place_from_that_plugins_own_folder(self):
        clone = self.root / 'clone'
        for plugin in ('salesforce-development', 'experience-lwc'):
            (clone / 'plugins/builder' / plugin / 'skills/some-skill').mkdir(parents=True)
        (clone / '.claude-plugin').mkdir()
        (clone / '.claude-plugin/marketplace.json').write_text(json.dumps({'name': 'salesforce', 'plugins': [
            {'name': 'salesforce-development', 'source': './plugins/builder/salesforce-development'},
            {'name': 'experience-lwc', 'source': './plugins/builder/experience-lwc'}]}))
        root = self.plugin_dir('local', 'salesforce-development')
        self.register('local-test', {'source': 'directory', 'path': str(clone)}, 'salesforce-development', root)
        with patch.dict(os.environ, {'SCOUT_OFFICIAL_SOURCE': str(clone)}):
            result = official.verify('salesforce-development', str(clone / 'plugins/builder/salesforce-development/skills/some-skill'))
            self.assertEqual((result['state'], result['provider']), ('verified', 'trial-source'))
            other = official.verify('salesforce-development', str(clone / 'plugins/builder/experience-lwc/skills/some-skill'))
            self.assertEqual(other['state'], 'conflict')  # another plugin's folder in the same checkout


class CoexistenceTests(Fixture):
    def setUp(self):
        super().setUp()
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        self.sf = str(stand_ins.salesforce_cli(bin_dir, FAKE_SF))

    def issues(self, **env):
        with patch.dict(os.environ, env):
            return official.coexistence(self.sf, 'claude', self.root)[0]

    def checks(self, **env):
        with patch.dict(os.environ, env):
            return official.coexistence(self.sf, 'claude', self.root)[1]

    def test_nothing_to_predict_without_any_copy_of_the_plugin(self):
        self.assertEqual(self.issues(SFDX_AUTO_DEPLOY='1'), [
            {'issue': 'auto-deploy', 'detail': 'the official hook deploys saved files to its own default org'}])

    def test_the_deploy_gate_and_the_recommender_from_anthropics_copy_too(self):
        root = self.plugin_dir('anthropic', 'salesforce-development')
        self.register('claude-plugins-official', ANTHROPIC, 'salesforce-development', root)  # its hooks still run
        self.assertEqual([i['detail'] for i in self.issues() if i['issue'] == 'deploy-gate'], ['no-default'])
        self.assertEqual([i['scope'] for i in self.issues() if i['issue'] == 'deploy-gate'], ['global'])  # no project here
        gate = [i for i in self.issues(FAKE_DEFAULT='old') if i['issue'] == 'deploy-gate'][0]
        self.assertEqual((gate['detail'], gate['default']), ('default-unreachable', 'old'))  # named in the SE's question
        self.assertEqual([i['detail'] for i in self.issues(FAKE_DEFAULT='old') if i['issue'] == 'deploy-gate'],
                         ['default-unreachable'])
        self.assertEqual(self.issues(FAKE_DEFAULT='demo', FAKE_REACHABLE='demo'), [])  # no Salesforce project here
        self.assertEqual(self.checks(FAKE_DEFAULT='demo', FAKE_REACHABLE='demo')['deploy-gate'], 'ok')
        (self.root / 'sfdx-project.json').write_text('{}')
        self.assertEqual([i['issue'] for i in self.issues(FAKE_DEFAULT='demo', FAKE_REACHABLE='demo')], ['recommender'])
        self.assertEqual([i['scope'] for i in self.issues() if i['issue'] == 'deploy-gate'], ['project'])  # a local fix
        self.assertEqual([i['scope'] for i in self.issues(SF_TARGET_ORG='gone') if i['issue'] == 'deploy-gate'], ['environment'])
        legacy = [i for i in self.issues(FAKE_DEFAULT='gone', FAKE_LOCATION='Environment', SFDX_DEFAULTUSERNAME='gone')
                  if i['issue'] == 'deploy-gate'][0]
        self.assertEqual((legacy['scope'], legacy.get('folder')), ('environment', None))  # no config change can clear it
        nested = self.root / 'force-app/main'
        nested.mkdir(parents=True)
        with patch.dict(os.environ, {}):
            gate = [i for i in official.coexistence(self.sf, 'claude', nested)[0] if i['issue'] == 'deploy-gate'][0]
        self.assertEqual((gate['scope'], gate['folder']), ('project', str(self.root)))  # the project root's config changes
        self.assertEqual(self.issues(SF_TARGET_ORG='demo', FAKE_REACHABLE='demo', SF_DISABLE_PLUGIN_MATCH='1'), [])
        self.assertEqual(self.checks(SF_DISABLE_PLUGIN_MATCH='1', SF_TARGET_ORG='demo', FAKE_REACHABLE='demo')['recommender'],
                         {'on': False, 'setting': 'off', 'source': 'SF_DISABLE_PLUGIN_MATCH', 'fires_here': False})
        self.assertEqual([i['detail'] for i in self.issues(FAKE_DEFAULT='demo', FAKE_CONFIG_EXIT='1') if i['issue'] == 'deploy-gate'],
                         ['query-failed'])
        self.assertEqual([i['detail'] for i in self.issues(FAKE_DEFAULT='demo', FAKE_REACHABLE='demo', FAKE_EMPTY_DISPLAY='1')
                          if i['issue'] == 'deploy-gate'], ['default-unreachable'])
        with patch.dict(os.environ, {'SFDX_AUTO_DEPLOY': '1'}):
            self.assertEqual(official.coexistence(self.sf, 'codex', self.root), ([], {}))  # no official hooks off Claude

    def test_the_recommender_reports_which_setting_won_as_the_official_hook_resolves_it(self):
        self.assertEqual(official.recommender()['source'], "default (the plugin's own option isn't visible)")
        saved = self.root / '.sf/plugin-recommendations/config.json'
        saved.parent.mkdir(parents=True)
        saved.write_text('{"sensitivity": "off"}')
        self.assertEqual(official.recommender(), {'on': False, 'setting': 'off', 'source': 'saved preference'})
        with patch.dict(os.environ, {'SF_PLUGIN_MATCH_SENSITIVITY': 'eager'}):  # invalid: falls through, as upstream does
            self.assertEqual(official.recommender()['source'], 'saved preference')
        with patch.dict(os.environ, {'SF_PLUGIN_MATCH_SENSITIVITY': 'High'}):
            self.assertEqual(official.recommender(), {'on': True, 'setting': 'high', 'source': 'SF_PLUGIN_MATCH_SENSITIVITY'})
        saved.write_text('{"sensitivity": 4.5}')
        self.assertEqual(official.recommender(), {'on': True, 'setting': 4.5, 'source': 'saved preference'})
        saved.write_text('{"sensitivity": 40}')  # out of range: falls through to the default
        self.assertEqual(official.recommender()['source'], "default (the plugin's own option isn't visible)")
        with patch.dict(os.environ, {'SF_DISABLE_PLUGIN_MATCH': '1', 'SF_PLUGIN_MATCH_SENSITIVITY': 'high'}):
            self.assertEqual(official.recommender()['source'], 'SF_DISABLE_PLUGIN_MATCH')
        if not stand_ins.symlinks():  # Windows allows links only with Developer Mode or as an administrator
            return
        dotfile = self.root / 'dotfiles-config.json'  # a dotfile-managed link: the official hook ignores it, so Scout does too
        dotfile.write_text('{"sensitivity": "off"}')
        saved.unlink()
        saved.symlink_to(dotfile)
        self.assertEqual(official.recommender()['source'], "default (the plugin's own option isn't visible)")


class CliRouteTests(Fixture):
    """The two CLI calls go through scout_portable.sf_command: on Windows the CLI's Node entry, and a batch launcher
    alone never gets an argument cmd.exe would re-read."""

    def test_both_calls_take_the_portable_route(self):
        sf = str(stand_ins.salesforce_cli(self.root, FAKE_SF))
        with patch.object(official.scout_portable, 'sf_command', wraps=official.scout_portable.sf_command) as route, \
                patch.dict(os.environ, {'FAKE_DEFAULT': 'R&D', 'FAKE_REACHABLE': 'R&D'}):
            self.assertEqual(official.default_org(sf, self.root)[:2], ('R&D', None))
            self.assertTrue(official.reachable(sf, 'R&D'))
        self.assertEqual([call.args[1] for call in route.call_args_list],
                         [['config', 'get', 'target-org', '--json'], ['org', 'display', '--target-org', 'R&D', '--json']])

    def test_a_batch_launcher_alone_never_gets_an_argument_cmd_would_reread(self):
        launcher = self.root / 'launcher' / 'sf.cmd'
        launcher.parent.mkdir()
        launcher.write_text('@echo off\r\nrem a launcher whose Node entry Scout cannot find\r\n')
        with patch.object(official.scout_portable, 'PLATFORM', 'win32'):
            with patch.object(official.subprocess, 'run', side_effect=AssertionError('the CLI ran')):
                with self.assertRaisesRegex(official.Refused, 'batch launcher'):
                    official.reachable(str(launcher), 'R&D')
            # The refusal stays apart from an unreachable org: no question about the default org or its login.
            self.register('salesforce', GITHUB, 'salesforce-development', self.plugin_dir('github', 'salesforce-development'))
            answers = [subprocess.CompletedProcess([], 0, json.dumps({'status': 0, 'result': [
                {'name': 'target-org', 'value': 'R&D', 'location': 'Global'}]}).encode(), b'')]
            with patch.object(official.subprocess, 'run', side_effect=answers):
                issues, checks = official.coexistence(str(launcher), 'claude', self.root)
        gate, = [issue for issue in issues if issue['issue'] == 'deploy-gate']
        self.assertEqual(set(gate), {'issue', 'detail', 'reason'})
        self.assertEqual(gate['detail'], 'cli-refused')
        self.assertIn('batch launcher', gate['reason'])
        self.assertEqual(checks['deploy-gate'], 'cli-refused')


class WindowsPreferenceTests(Fixture):
    """The saved recommender preference on Windows, with the platform injected: no user IDs to compare, and a link
    found by its reparse tag, because there is no O_NOFOLLOW."""

    @contextlib.contextmanager
    def as_windows(self):
        getuid = getattr(os, 'getuid', None)
        if getuid is not None:
            del os.getuid
        try:
            with patch.object(official.scout_portable, 'PLATFORM', 'win32'):
                yield
        finally:
            if getuid is not None:
                os.getuid = getuid

    def test_the_saved_preference_is_read_without_user_ids_and_a_link_is_refused(self):
        saved = self.root / '.sf/plugin-recommendations/config.json'
        saved.parent.mkdir(parents=True)
        saved.write_bytes(b'{"sensitivity": "off"}\r\n')
        with self.as_windows():
            self.assertEqual(official.recommender(), {'on': False, 'setting': 'off', 'source': 'saved preference'})
            real = os.lstat
            def linked(path, *args, **kwargs):
                info = real(path, *args, **kwargs)
                if Path(path) == saved:
                    return types.SimpleNamespace(st_mode=info.st_mode, st_reparse_tag=official.scout_portable.IO_REPARSE_TAG_SYMLINK)
                return info
            with patch.object(os, 'lstat', side_effect=linked):
                self.assertEqual(official.recommender()['source'], "default (the plugin's own option isn't visible)")


class FolderContextTests(Fixture):
    """D4: inspection, verification and the hook prediction judge the same launch folder."""

    def setUp(self):
        super().setUp()
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        self.sf = str(stand_ins.salesforce_cli(bin_dir, FAKE_SF))

    def test_verify_agrees_with_inspection_for_the_folder(self):
        github = self.plugin_dir('github', 'salesforce-development', skills=['platform-soql-query'])
        anthropic = self.plugin_dir('anthropic', 'salesforce-development', skills=['platform-soql-query'])
        self.register('salesforce', GITHUB, 'salesforce-development', github)
        self.register('claude-plugins-official', ANTHROPIC, 'salesforce-development', anthropic)  # both on globally
        folder = self.root / 'project'
        (folder / '.claude').mkdir(parents=True)
        (folder / '.claude/settings.json').write_text(json.dumps({'enabledPlugins': {'salesforce-development@claude-plugins-official': False}}))
        loaded = str(github / 'skills/platform-soql-query')
        self.assertEqual(official.verify('salesforce-development', loaded)['state'], 'conflict')  # globally, two copies
        self.assertEqual(official.verify('salesforce-development', loaded, launch_dir=folder)['state'], 'verified')
        self.assertEqual(official.check(['soql'], launch_dir=folder)['soql']['state'], 'installed')

    def test_a_folder_that_switches_the_plugin_on_gets_the_deploy_gate_prediction(self):
        github = self.plugin_dir('github', 'salesforce-development')
        self.register('salesforce', GITHUB, 'salesforce-development', github, enabled=False)  # off for the user
        folder = self.root / 'project'
        (folder / '.claude').mkdir(parents=True)
        (folder / '.claude/settings.json').write_text(json.dumps({'enabledPlugins': {'salesforce-development@salesforce': True}}))
        with patch.dict(os.environ, {}):
            self.assertEqual(official.coexistence(self.sf, 'claude', self.root)[1], {'official-hooks': 'absent'})
            issues, checks = official.coexistence(self.sf, 'claude', folder)
        self.assertEqual(checks['deploy-gate'], 'no-default')  # the folder runs the official hooks, so they're predicted


class CapabilityMapTests(unittest.TestCase):
    def test_every_entry_names_a_known_plugin_or_scout(self):
        data = official.capability_map()
        plugins = set(data['plugins']) | {'sf-demo-scout'}
        for name, spec in data['capabilities'].items():
            for entry in spec.get('skills', []) + spec.get('assets', []):
                self.assertIn(entry.partition(':')[0], plugins, name)
        self.assertEqual({p for p, v in data['plugins'].items() if v['core']}, {'salesforce-development', 'salesforce-code-quality'})
        self.assertEqual(sum(1 for v in data['plugins'].values() if v['setup']), 5)  # the user, 2026-10-16: all five, once

    def test_entries_exist_in_the_pinned_upstream_checkout_when_present(self):
        checkout = Path(os.environ.get('SCOUT_SF_SKILLS_CHECKOUT') or '/nonexistent-sf-skills-checkout') / 'plugins/builder'
        if not checkout.is_dir():
            self.skipTest('no local sf-skills checkout')
        for name, spec in official.capability_map()['capabilities'].items():
            for entry in spec.get('skills', []):
                plugin, _, skill = entry.partition(':')
                if plugin != 'sf-demo-scout':
                    self.assertTrue((checkout / plugin / 'skills' / skill / 'SKILL.md').is_file(), entry)
            for entry in spec.get('assets', []):
                plugin, _, rest = entry.partition(':')
                self.assertTrue((checkout / plugin / rest).exists(), entry)


if __name__ == '__main__':
    unittest.main()
