"""W9 prep-mode contracts: constructed read-only checks, the total verdict, and safe publication."""
import contextlib
import datetime
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import scout_prep as prep

ORG, USER = '00D000000000001EAA', 'maple@example.test'
FAKE = r'''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['PREP_CALLS'], 'a') as f:
    f.write(json.dumps({'args': args, 'cwd': os.getcwd()}) + '\n')
state = json.loads(Path(os.environ['PREP_STATE']).read_text())
if args[:2] == ['org', 'display']:
    print(json.dumps({'status': 0, 'result': {'id': state['org'], 'username': state['username']}}))
elif args[:2] == ['data', 'query'] and 'FROM Organization' in args[args.index('--query') + 1]:
    print(json.dumps({'status': 0, 'result': {'records': [{'Id': state['org']}]}}))
elif args[:2] == ['data', 'query']:
    print(json.dumps({'status': 0, 'result': {'totalSize': 2, 'records': [{'Id': 'a1'}, {'Id': 'a2'}]}}))
elif args[:2] == ['sobject', 'describe']:
    print(json.dumps({'status': 0, 'result': {'fields': [{'name': 'Status__c'}, {'name': 'Id'}]}}))
elif args[:3] == ['project', 'retrieve', 'start']:
    target = Path(args[args.index('--target-metadata-dir') + 1])
    (target / 'objects').mkdir(parents=True, exist_ok=True)
    (target / 'objects' / 'X.object').write_text('<CustomObject/>')
    print(json.dumps({'status': 0, 'result': {'files': []}}))
else:
    sys.exit(9)
'''


def obligation(key='task-2026-10-13-1200-x.md#B1/claim1', status='passed', kind='claim', beat='B1', proof=True,
               required=True, at='2026-10-13T15:00:00+02:00', **extra):
    value = dict(key=key, kind=kind, beat=beat, proof_moment=proof, required=required, text='Two overdue rows',
                 result=dict(status=status, observed='2', at=at) if status else None)
    value.update(extra)
    return value


def results(*obligations, sources=()):
    return dict(schema=1, folder='orgs/example', org_id=ORG, username=USER, observed_at='2026-10-13T15:00:00+02:00',
                sources=list(sources), obligations=list(obligations))


class Fixture(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='scout-prep-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.folder = self.root / 'orgs' / 'example'
        self.folder.mkdir(parents=True)
        self.results = self.root / 'results.json'

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = prep.main(list(args))
        return code, output.getvalue()

    def save(self, data):
        self.results.write_text(json.dumps(data))


class QueryGrammarTests(unittest.TestCase):
    def test_constrained_select_only(self):
        for query in ("SELECT Id, Name FROM Account WHERE Name LIKE 'A%' ORDER BY Name LIMIT 5",
                      'SELECT COUNT(Id) n, Status__c FROM Kit_Request__c GROUP BY Status__c',
                      'SELECT Id FROM Kit_Request__c WHERE Due_Date__c < TODAY'):
            with self.subTest(query=query):
                prep.validate_query(query)
        for query in ('SELECT Id FROM Account FOR VIEW', 'SELECT Id FROM Account FOR REFERENCE', 'SELECT Id FROM Account FOR UPDATE',
                      'SELECT Id FROM Account USING SCOPE mine', 'SELECT Id FROM Account ALL ROWS', 'SELECT Id FROM Account; DELETE',
                      'DELETE FROM Account', 'UPDATE Account SET Name = 1', 'SELECT Id FROM `Account`', 'SELECT $(whoami) FROM Account',
                      'SELECT Id FROM Account && sf data delete record', ''):
            with self.subTest(query=query):
                with self.assertRaises(prep.Refused):
                    prep.validate_query(query)


class RunTests(Fixture):
    def setUp(self):
        super().setUp()
        binary = self.root / 'bin' / 'sf'
        binary.parent.mkdir()
        binary.write_text('#!' + sys.executable + '\n' + FAKE)
        binary.chmod(0o700)
        self.calls = self.root / 'calls.jsonl'
        self.state = self.root / 'state.json'
        self.state.write_text(json.dumps(dict(org=ORG, username=USER)))
        patcher = patch.dict(os.environ, dict(PATH=str(binary.parent), HOME=str(self.root), PREP_CALLS=str(self.calls),
                                              PREP_STATE=str(self.state), PYTHONDONTWRITEBYTECODE='1'), clear=True)
        patcher.start(); self.addCleanup(patcher.stop)

    def log(self):
        return [json.loads(l) for l in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def run_prep(self, *extra):
        return self.cli('run', '--selector', 'maple', '--username', USER, '--org-id', ORG, *extra)

    def test_query_binds_first_then_runs_one_constructed_read(self):
        code, output = self.run_prep('--kind', 'query', '--query', 'SELECT Id FROM Kit_Request__c WHERE Due_Date__c < TODAY')
        self.assertEqual(code, 0, output)
        calls = [c['args'][:2] for c in self.log()]
        self.assertEqual(calls, [['org', 'display'], ['data', 'query'], ['data', 'query']])
        last = self.log()[-1]['args']
        self.assertEqual(last[last.index('--target-org') + 1], USER)
        self.assertEqual(json.loads(output)['observed']['totalSize'], 2)

    def test_mutations_never_reach_the_cli(self):
        before = self.folder.stat().st_mtime_ns
        for extra in (('--kind', 'query', '--query', 'DELETE FROM Account'), ('--kind', 'describe', '--sobject', 'Account; rm -rf /'),
                      ('--kind', 'retrieve', '--metadata', 'CustomObject:X && sf data delete')):
            with self.subTest(extra=extra):
                code, output = self.run_prep(*extra)
                self.assertEqual(code, 3, output)
        mutating = [c for c in self.log() if c['args'][:2] not in (['org', 'display'], ['data', 'query'])]
        self.assertEqual(mutating, [])
        self.assertTrue(all('FROM Organization' in c['args'][c['args'].index('--query') + 1] for c in self.log() if c['args'][:2] == ['data', 'query']))
        self.assertEqual(self.folder.stat().st_mtime_ns, before)

    def test_binding_mismatch_runs_nothing_else(self):
        self.state.write_text(json.dumps(dict(org='00D000000000002EAA', username=USER)))
        code, output = self.run_prep('--kind', 'describe', '--sobject', 'Kit_Request__c')
        self.assertEqual(code, 3)
        self.assertIn('binding check failed', output)
        self.assertEqual([c['args'][:2] for c in self.log()], [['org', 'display']])

    def test_retrieve_goes_to_scratch_never_the_folder(self):
        code, output = self.run_prep('--kind', 'retrieve', '--metadata', 'CustomObject:Kit_Request__c')
        self.assertEqual(code, 0, output)
        directory = Path(json.loads(output)['observed']['directory'])
        self.assertFalse(str(directory).startswith(str(self.root / 'orgs')))
        self.assertEqual(list(self.folder.iterdir()), [])
        retrieve = [c for c in self.log() if c['args'][:3] == ['project', 'retrieve', 'start']][0]
        self.assertFalse(retrieve['cwd'].startswith(str(self.root / 'orgs')))


class VerdictTests(Fixture):
    def verdict(self, data, demo_time=None):
        self.save(data)
        args = ['verdict', '--results', str(self.results)] + (['--demo-time', demo_time] if demo_time else [])
        code, output = self.cli(*args)
        self.assertEqual(code, 0, output)
        return json.loads(output)

    def test_table_is_total_and_ordered(self):
        cases = [
            (results(obligation()), 'ready'),
            (results(obligation(), obligation('t.md#B1/eye', 'eye', proof=False)), 'ready with exceptions'),
            (results(obligation(), obligation('t.md#B1/qa', 'visual_qa', kind='visual_qa', proof=False)), 'ready with exceptions'),
            (results(obligation(), obligation('t.md#B1/persona', 'persona', kind='persona', proof=False)), 'ready with exceptions'),
            (results(obligation(), obligation('t.md#B2/c', 'failed', proof=False)), 'not ready'),
            (results(obligation(), obligation('t.md#I2', 'unavailable', kind='item', proof=False)), 'not ready'),
            (results(obligation(), obligation('t.md#manual1', 'open', kind='manual', proof=False)), 'not ready'),
            (results(obligation(), obligation('t.md#job', 'open', kind='job', proof=False)), 'not ready'),
            (results(obligation(), obligation('t.md#I3', 'unknown', kind='item', proof=False)), 'not ready'),
            (results(obligation(), obligation('t.md#I4', None, kind='item', proof=False)), 'not ready'),
            (results(obligation(), obligation('t.md#weird', 'maybe', proof=False)), 'not ready'),
            (results(obligation(), obligation('t.md#weird', 'passed', kind='mystery', proof=False)), 'not ready'),
            (results(obligation(), obligation('t.md#opt', 'failed', proof=False, required=False)), 'ready with exceptions'),
            (results(obligation(), obligation('t.md#old', 'failed', proof=False, superseded_by='t2.md#B1/claim1')), 'ready'),
            (results(obligation(), obligation('t.md#B1/c2', 'passed', at=None, proof=False)), 'not ready'),
            (results(), 'not ready'),
            (results(obligation(proof=False)), 'not ready'),
            (results(obligation(), sources=[dict(path='task-old.md', state='unreadable')]), 'not ready'),
            (results(obligation(), sources=[dict(path='other.md', state='quarantined')]), 'not ready'),
            (results(obligation(), sources=[dict(path='other.md', state='unrelated')]), 'ready'),
        ]
        for data, expected in cases:
            with self.subTest(expected=expected, obligations=[(o['key'], (o.get('result') or {}).get('status')) for o in data['obligations']]):
                self.assertEqual(self.verdict(data)['verdict'], expected)

    def test_validity_window_is_checked_through_the_demo_time(self):
        data = results(obligation(valid_until='2026-10-14'))
        self.assertEqual(self.verdict(data, '2026-10-14T10:00:00+02:00')['verdict'], 'ready')
        self.assertEqual(self.verdict(data, '2026-10-15T10:00:00+02:00')['verdict'], 'not ready')

    def test_keys_are_task_qualified_and_unique(self):
        for data in (results(obligation('B1/claim1')), results(obligation(), obligation())):
            with self.subTest(keys=[o['key'] for o in data['obligations']]):
                self.save(data)
                self.assertEqual(self.cli('verdict', '--results', str(self.results))[0], 3)


class PublishTests(Fixture):
    def render(self, data):
        self.save(data)
        candidate = self.root / 'candidate.md'
        code, output = self.cli('render', '--results', str(self.results), '--folder', str(self.folder), '--out', str(candidate))
        return code, output, candidate

    def publish(self, candidate):
        return self.cli('publish', '--folder', str(self.folder), '--candidate', str(candidate))

    def gate(self, candidate, data, org=ORG, user=USER):
        self.save(data)
        return self.cli('check', '--results', str(self.results), '--candidate', str(candidate), '--org-id', org, '--username', user)

    def test_render_gate_publish_and_regenerate(self):
        data = results(obligation())
        code, output, candidate = self.render(data)
        self.assertEqual(code, 0, output)
        self.assertEqual(self.gate(candidate, data)[0], 0)
        self.assertEqual(self.publish(candidate)[0], 0)
        published = open(self.folder / 'demo-path.md', newline='').read()
        self.assertIn('ready — 1 of 1 checks passed', published)
        note = '\n## My own notes\nKeep the Willowgate tab open.\r\n'
        with open(self.folder / 'demo-path.md', 'w', newline='') as stream:
            stream.write(published + note)
        data['obligations'].append(obligation('t.md#B2/c', 'failed', beat='B2', proof=False))
        code, output, candidate = self.render(data)
        self.assertEqual(code, 0, output)
        self.assertEqual(self.publish(candidate)[0], 0)
        regenerated = open(self.folder / 'demo-path.md', newline='').read()
        self.assertTrue(regenerated.endswith(note))
        self.assertIn('not ready', regenerated)
        self.assertEqual(len(list((self.folder / '.scout-work' / 'prep').iterdir())), 2 - 1)
        self.assertEqual([p.name for p in self.folder.iterdir() if p.name.startswith('demo-path.md.tmp')], [])

    def test_an_se_edit_inside_a_region_refuses_regeneration(self):
        data = results(obligation())
        _, _, candidate = self.render(data)
        self.publish(candidate)
        path = self.folder / 'demo-path.md'
        path.write_text(path.read_text().replace('## Known seams\n', '## Known seams\n- My own seam note\n'))
        code, output, _ = self.render(data)
        self.assertEqual(code, 3)
        self.assertIn('edited Scout region', output)

    def test_hand_made_and_malformed_files_stay_untouched(self):
        for text in ('# My demo path\nStep 1\n', '<!-- scout:begin path sha256=zz -->\n', '<!-- scout:begin path sha256=' + 'a' * 64 + ' -->\nx\n',
                     '<!-- scout:begin path sha256=' + 'a' * 64 + ' -->\n<!-- scout:begin seams sha256=' + 'a' * 64 + ' -->\n'):
            with self.subTest(text=text[:40]):
                path = self.folder / 'demo-path.md'
                path.write_text(text)
                code, output, _ = self.render(results(obligation()))
                self.assertEqual(code, 3, output)
                self.assertEqual(path.read_text(), text)

    def test_a_concurrent_save_refuses_and_keeps_a_backup(self):
        data = results(obligation())
        _, _, candidate = self.render(data)
        self.publish(candidate)
        _, _, candidate = self.render(data)
        path = self.folder / 'demo-path.md'
        original = prep.publish
        def racing(folder, candidate_path):
            real_mkstemp = prep.tempfile.mkstemp
            def mkstemp(*a, **k):
                path.write_text(path.read_text() + '\nA save during prep.\n')
                return real_mkstemp(*a, **k)
            with patch.object(prep.tempfile, 'mkstemp', mkstemp):
                return original(folder, candidate_path)
        with patch.object(prep, 'publish', racing):
            code, output = self.publish(candidate)
        self.assertEqual(code, 3)
        self.assertIn('changed during prep', output)
        self.assertTrue(path.read_text().endswith('A save during prep.\n'))
        self.assertTrue(list((self.folder / '.scout-work' / 'prep').iterdir()))

    def test_gate_rejects_mismatched_stamp_identity_tampering_and_missing_results(self):
        data = results(obligation())
        _, _, candidate = self.render(data)
        self.assertEqual(self.gate(candidate, data, org='00D000000000002EAA')[0], 3)
        tampered = candidate.read_text().replace('— ready —', '— ready with exceptions —')
        candidate.write_text(tampered)
        self.assertEqual(self.gate(candidate, data)[0], 3)
        _, _, candidate = self.render(data)
        candidate.write_text(candidate.read_text().replace('Two overdue rows', 'Three overdue rows'))
        self.assertIn('changed after rendering', self.gate(candidate, data)[1])
        data['obligations'].append(obligation('t.md#I9', None, kind='item', proof=False))
        _, _, candidate = self.render(data)
        self.assertIn('has no result', self.gate(candidate, data)[1])


if __name__ == '__main__':
    unittest.main()
