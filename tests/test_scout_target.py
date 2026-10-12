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
    assert args[args.index('--query')+1] == 'SELECT Id FROM Organization'
    data = state.get('query', {'records':[{'Id':state.get('query_id', state['org'])}]})
data['accessToken'] = 'SYNTHETIC-SECRET-DO-NOT-PRINT'
data['instanceUrl'] = 'https://example.test'
print(json.dumps({'status':state.get('status',0), 'result':data}))
'''


class ScoutTargetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='scout-target-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        binary = self.root / 'sf'
        binary.write_text('#!' + sys.executable + '\n' + FAKE)
        binary.chmod(0o700)
        self.state = self.root / 'state.json'
        self.calls = self.root / 'calls.jsonl'
        self.env = dict(HOME=str(self.root), PATH=str(self.root),
                        SCOUT_TARGET_FIXTURE=str(self.state), SCOUT_TARGET_CALLS=str(self.calls),
                        PYTHONDONTWRITEBYTECODE='1')
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
            self.assertEqual(data, dict(selector='maple', username=USER, org_id=ORG, reason='identity verified'))
        self.assertEqual(self.call_log(), [
            ['org', 'display', '--target-org', 'maple', '--json'],
            ['data', 'query', '--target-org', USER, '--query', 'SELECT Id FROM Organization', '--json']
        ] * 2)

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
                  dict(query={}), dict(query={'records':[]}), dict(query={'records':[{}, {}]}),
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

    def test_usage_errors_do_not_call_cli(self):
        self.assertEqual(self.run_target('check', '--selector', 'maple')[0], 2)
        self.assertEqual(self.run_target('check', '--selector', 'maple', '--username', USER, '--org-id', 'bad')[0], 2)
        self.assertEqual(self.call_log(), [])

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
