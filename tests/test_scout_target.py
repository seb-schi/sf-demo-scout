"""Target helper tested through an argv-recording fake CLI, never an org."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import scout_target as target
import stand_ins

ORG = '00D000000000001EAA'
OTHER = '00D000000000002EAA'
USER = 'maple@example.test'
SECRET = 'SYNTHETIC-SECRET-DO-NOT-PRINT'

FAKE = r'''
import json, os, sys, time
from pathlib import Path
state = json.loads(Path(os.environ['SCOUT_TARGET_FIXTURE']).read_text())
args = sys.argv[1:]
with open(os.environ['SCOUT_TARGET_CALLS'], 'a') as f:
    f.write(json.dumps(args) + '\n')
assert args[:2] in (['org','display'], ['data','query']), args
print('SYNTHETIC-SECRET-DO-NOT-PRINT', file=sys.stderr)
mode = state.get('mode')
if mode == 'timeout': time.sleep(2)
if mode == 'exit': print('SYNTHETIC-SECRET-DO-NOT-PRINT'); sys.exit(1)
if mode == 'invalid': print('{SYNTHETIC-SECRET-DO-NOT-PRINT'); sys.exit(0)
if mode == 'duplicate': print('{"status":0,"status":0,"result":{}}'); sys.exit(0)
if mode == 'utf8': sys.stdout.buffer.write(b'\xff'); sys.exit(0)
if mode == 'deep': print('[' * 5000 + '0' + ']' * 5000); sys.exit(0)
if mode == 'oversize': print('x' * (3 * 1024 * 1024)); sys.exit(0)
if args[:2] == ['org','display']:
    data = state.get('display', {'id':state['org'], 'username':state['username']})
else:
    assert args[args.index('--target-org')+1] == state['username']
    query = args[args.index('--query')+1]
    assert query in ('SELECT Id, IsSandbox, OrganizationType, TrialExpirationDate FROM Organization',
                     'SELECT Id FROM Organization'), query
    if state.get('type_query_fails') and 'IsSandbox' in query: sys.exit(1)
    row = {'Id': state.get('query_id', state['org'])}
    row.update(state.get('organization', {'IsSandbox': False, 'OrganizationType': 'Developer Edition',
                                          'TrialExpirationDate': None}))
    data = state.get('query', {'records': [row]})
data['accessToken'] = 'SYNTHETIC-SECRET-DO-NOT-PRINT'
data['instanceUrl'] = state.get('instance', 'https://example.test')
print(json.dumps({'status':state.get('status',0), 'result':data}))
'''


class ScoutTargetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='scout-target-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        stand_ins.salesforce_cli(self.root, FAKE)
        self.state = self.root / 'state.json'
        self.calls = self.root / 'calls.jsonl'
        self.env = stand_ins.keep(dict(stand_ins.home(self.root), PATH=stand_ins.path(self.root, node=True),
                                       SCOUT_TARGET_FIXTURE=str(self.state), SCOUT_TARGET_CALLS=str(self.calls),
                                       PYTHONDONTWRITEBYTECODE='1'))
        patcher = patch.dict(os.environ, self.env, clear=True)
        patcher.start(); self.addCleanup(patcher.stop)
        self.configure()

    def configure(self, **kwargs):
        self.state.write_text(json.dumps(dict(org=ORG, username=USER, **kwargs)))

    def run_target(self, *args):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            try:
                code = target.main(list(args))
            except SystemExit as exc:
                code = exc.code
        for stream in (output.getvalue(), error.getvalue()):
            self.assertNotIn(SECRET, stream)
            self.assertNotIn('instanceUrl', stream)
            self.assertNotIn('accessToken', stream)
            self.assertNotIn('Traceback', stream)
        return code, json.loads(output.getvalue()) if output.getvalue() else {}, error.getvalue()

    def check(self):
        return self.run_target('check', '--selector', 'maple', '--username', USER, '--org-id', ORG)

    def call_log(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def test_bind_and_check_allowlist_exact_two_read_commands(self):
        for command in ('bind', 'check'):
            code, data, error = (self.run_target('bind', '--selector', 'maple') if command == 'bind' else self.check())
            self.assertEqual(code, 0, error)
            self.assertEqual(data, dict(selector='maple', username=USER, org_id=ORG, reason='identity verified',
                                        **{'class': 'trial', 'writes': 'allowed'}))
        self.assertEqual(self.call_log(), [
            ['org', 'display', '--target-org', 'maple', '--json'],
            ['data', 'query', '--target-org', USER, '--query', target.ORGANIZATION, '--json']
        ] * 2)

    def test_the_org_class_follows_the_official_gates_buckets_in_order(self):
        today = target.datetime.date(2026, 10, 20)
        def org(sandbox=False, edition='Enterprise Edition', expiry=None):
            return {'IsSandbox': sandbox, 'OrganizationType': edition, 'TrialExpirationDate': expiry}
        cases = [
            ('https://acme--uat.sandbox.my.salesforce.com', org(), 'sandbox'),
            ('https://acme.my.salesforce.com', org(sandbox=True), 'sandbox'),
            ('https://test.salesforce.com', org(), 'sandbox'),
            ('https://acme-dev-ed.scratch.my.salesforce.com', org(sandbox=True), 'scratch'),
            ('https://acme.my.salesforce.com', org(expiry='2026-11-30T00:00:00.000+0000'), 'trial'),
            ('https://acme.my.salesforce.com', org(expiry='2026-10-20T00:00:00.000+0000'), 'trial'),
            ('https://acme-dev-ed.develop.my.salesforce.com', org(edition='Developer Edition'), 'trial'),
            ('https://orgfarm-abc123.my.salesforce.com', org(), 'trial'),
            # A trial converted to production keeps its old expiry date: only a future date counts.
            ('https://acme.my.salesforce.com', org(expiry='2025-01-31T00:00:00.000+0000'), 'production'),
            ('https://acme.my.salesforce.com', org(expiry='not a date'), 'production'),
            ('https://acme.my.salesforce.com', org(), 'production'),
            ('https://acme.my.salesforce.com', {'OrganizationType': 'Enterprise Edition'}, 'unknown'),
            ('https://acme.my.salesforce.com', org(edition=None), 'unknown'),
            (None, org(), 'unknown'),
        ]
        for instance, organization, expected in cases:
            with self.subTest(instance=instance, organization=organization):
                self.assertEqual(target.classify(instance, organization, today), expected)

    def test_a_failed_type_query_binds_read_only_when_the_identity_holds(self):
        self.configure(type_query_fails=True)
        code, data, _ = self.run_target('bind', '--selector', 'maple')
        self.assertEqual((code, data['class'], data['writes']), (0, 'unknown', 'read-only'))
        self.assertEqual(self.run_target('check', '--selector', 'maple', '--username', USER, '--org-id', ORG,
                                         '--write')[0], 5)
        self.configure(type_query_fails=True, query_id=OTHER)  # the identity still decides first
        self.assertEqual(self.run_target('bind', '--selector', 'maple')[0], 3)

    def test_the_clis_scratch_flag_counts(self):
        org = {'IsSandbox': False, 'OrganizationType': 'Developer Edition', 'TrialExpirationDate': None}
        self.assertEqual(target.classify('https://acme.my.salesforce.com', org, scratch=True), 'scratch')

    def test_check_write_refuses_production_and_unknown_orgs_and_reads_still_pass(self):
        for organization, cls in (({'IsSandbox': False, 'OrganizationType': 'Enterprise Edition',
                                    'TrialExpirationDate': None}, 'production'),
                                   ({'OrganizationType': 'Enterprise Edition'}, 'unknown')):
            with self.subTest(cls=cls):
                self.configure(organization=organization, instance='https://acme.my.salesforce.com')
                code, data, _ = self.run_target('check', '--selector', 'maple', '--username', USER,
                                                '--org-id', ORG, '--write')
                self.assertEqual((code, data['class'], data['writes']), (5, cls, 'read-only'))
                self.assertIn("Scout doesn't write here", data['reason'])
                code, data, _ = self.check()
                self.assertEqual((code, data['writes']), (0, 'read-only'))
                code, data, _ = self.run_target('bind', '--selector', 'maple')
                self.assertEqual((code, data['class']), (0, cls))
        self.configure(organization={'IsSandbox': True, 'OrganizationType': 'Enterprise Edition',
                                     'TrialExpirationDate': None})
        code, data, _ = self.run_target('check', '--selector', 'maple', '--username', USER, '--org-id', ORG, '--write')
        self.assertEqual((code, data['writes']), (0, 'allowed'))

    def test_selector_repoint_username_and_displayed_org_are_mismatches(self):
        for display, reason in ((dict(id=ORG, username='second@example.test'), 'another username'),
                                (dict(id=OTHER, username=USER), 'another org')):
            self.configure(display=display)
            code, data, _ = self.check()
            self.assertEqual(code, 3)
            self.assertIn(reason, data['reason'])
        self.assertTrue(all(row[:2] == ['org', 'display'] for row in self.call_log()))

    def test_authenticated_query_org_mismatch(self):
        self.configure(query_id=OTHER)
        for args in (('bind', '--selector', 'maple'),
                     ('check', '--selector', 'maple', '--username', USER, '--org-id', ORG)):
            code, data, _ = self.run_target(*args)
            self.assertEqual((code, data['reason']), (3, 'authenticated org differs'))

    def test_fifteen_and_eighteen_character_ids_normalize_and_checksum_is_checked(self):
        for displayed, queried in ((ORG[:15], ORG), (ORG, ORG[:15]), (ORG[:15], ORG[:15])):
            self.configure(display=dict(id=displayed, username=USER), query_id=queried)
            self.assertEqual(self.check()[0], 0)
            code, data, _ = self.run_target('bind', '--selector', 'maple')
            self.assertEqual((code, data['org_id']), (0, ORG))
        self.configure(display=dict(id=ORG[:15] + 'AAA', username=USER))
        self.assertEqual(self.check()[0], 4)

    def test_error_json_missing_fields_and_rows_are_unverified_without_secrets(self):
        cases = [dict(mode=m) for m in ('exit', 'invalid', 'duplicate', 'utf8', 'deep', 'oversize')]
        cases += [dict(status=1), dict(status=False), dict(display={}), dict(display={'id':ORG}),
                  dict(query={}), dict(query={'records':[]}), dict(query={'records':[{'Id':ORG}, {'Id':ORG}]}),
                  dict(query={'records':[{'Id':'bad'}]})]
        for case in cases:
            with self.subTest(case=case):
                self.configure(**case)
                code, data, _ = self.check()
                self.assertEqual(code, 4)
                self.assertEqual(set(data), {'reason'})

    def test_timeout_and_missing_cli_are_unverified(self):
        self.configure(mode='timeout')
        with patch.object(target, 'TIMEOUT', 1):
            self.assertEqual(self.check()[0], 4)
        with patch.dict(os.environ, PATH=str(self.root / 'absent')):
            self.assertEqual(self.check()[0], 4)
        self.assertEqual(len(self.call_log()), 1)

    def test_failed_import_and_surrogate_username_exit_four_without_traceback(self):
        isolated = self.root / 'isolated-target.py'
        isolated.write_text(Path(target.__file__).read_text())
        result = subprocess.run([sys.executable, '-S', '-B', str(isolated), 'bind', '--selector', 'maple'],
                                capture_output=True, text=True, env=os.environ.copy())
        self.assertEqual(result.returncode, 4)
        self.assertEqual(json.loads(result.stdout), {'reason': 'target helper dependencies unavailable'})
        self.assertEqual(result.stderr, '')
        self.assertEqual(self.call_log(), [])
        self.configure(display={'id': ORG, 'username': '\ud800@example.test'})
        self.assertEqual(self.run_target('bind', '--selector', 'maple')[0], 4)
        self.assertEqual(len(self.call_log()), 1)

    def test_a_username_no_platform_can_pass_on_ends_the_binding_after_one_call(self):
        # Windows would hand the lone surrogate to the next CLI call; the identity check refuses it first, everywhere.
        with self.assertRaises(target.RepairError):
            target.text('\ud800@example.test', 'username')
        self.configure(display={'id': ORG, 'username': 'maple\udfff@example.test'})
        self.assertEqual(self.run_target('bind', '--selector', 'maple')[0], 4)
        self.assertEqual(self.call_log(), [['org', 'display', '--target-org', 'maple', '--json']])

    def test_usage_errors_do_not_call_cli(self):
        self.assertEqual(self.run_target('check', '--selector', 'maple')[0], 2)
        self.assertEqual(self.run_target('check', '--selector', 'maple', '--username', USER, '--org-id', 'bad')[0], 2)
        self.assertEqual(self.call_log(), [])

    def test_a_selector_cmd_would_split_reaches_the_cli_unchanged(self):
        # R&D has no space, so nothing quotes it: run through a batch launcher, cmd.exe would end the command at &.
        # On Windows Scout runs the CLI's Node entry instead; elsewhere the CLI itself.
        code, data, error = self.run_target('bind', '--selector', 'R&D')
        self.assertEqual((code, data['selector']), (0, 'R&D'), error)
        self.assertEqual(self.call_log()[0], ['org', 'display', '--target-org', 'R&D', '--json'])

    def test_a_batch_launcher_alone_never_gets_an_argument_cmd_would_reread(self):
        launcher = self.root / 'launcher' / 'sf.cmd'
        launcher.parent.mkdir()
        launcher.write_text('@echo off\r\nrem a launcher whose Node entry Scout cannot find\r\n')
        with patch.object(target.scout_portable, 'PLATFORM', 'win32'), \
                patch.object(target.subprocess, 'run', side_effect=AssertionError('the CLI ran')):
            with self.assertRaisesRegex(target.Unverified, 'batch launcher'):
                target.query_cli(str(launcher), ['org', 'display', '--target-org', 'R&D'])

    def test_selector_is_one_literal_argument_and_cli_entrypoint_works(self):
        selector = 'maple; $(echo unexpected)'
        result = subprocess.run([sys.executable, '-S', '-B', target.__file__, 'bind', '--selector', selector],
                                capture_output=True, text=True, env=os.environ.copy())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['selector'], selector)
        self.assertEqual(self.call_log()[0][3], selector)
        self.assertNotIn(SECRET, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
