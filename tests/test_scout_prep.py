"""W9 prep-mode contracts: constructed read-only checks, the total verdict, and safe publication."""
import contextlib
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import scout_prep as prep

ORG, USER = '00D000000000001EAA', 'maple@example.test'
NOW, STARTED, STAMP = '2026-10-13T16:00:00+02:00', '2026-10-13T14:50:00+02:00', '2026-10-13T15:00:00+02:00'
KEY = 'task-2026-10-13-1200-x.md#B1/claim1'
FAKE = r'''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['PREP_CALLS'], 'a') as f:
    f.write(json.dumps({'args': args, 'cwd': os.getcwd()}) + '\n')
state = json.loads(Path(os.environ['PREP_STATE']).read_text())
def reply(value, code=0, stream=sys.stdout):
    print(json.dumps(value), file=stream)
    sys.exit(code)
if args[:2] == ['org', 'display']:
    reply({'status': 0, 'result': {'id': state['org'], 'username': state['username']}})
if args[:2] == ['data', 'query']:
    query = args[args.index('--query') + 1]
    if 'FROM Organization' in query:
        reply({'status': 0, 'result': {'records': [{'Id': state['org']}]}})
    if 'error' in state:
        reply({'status': 1, 'name': state['error'][0], 'message': state['error'][1]}, 1,
              sys.stderr if state.get('error_stream') == 'stderr' else sys.stdout)
    if 'result' in state:
        reply({'status': 0, 'result': state['result']})
    for needle, answer in state.get('answers', {}).items():
        if needle in query:
            reply({'status': 0, 'result': {'totalSize': answer.get('total', len(answer.get('records', []))),
                                           'done': True, 'records': answer.get('records', [])}})
    rows = [{'Id': 'a%d' % i} for i in range(state.get('rows', 2))]
    reply({'status': 0, 'result': {'totalSize': state.get('total', len(rows)), 'done': state.get('done', True), 'records': rows}})
if args[:2] == ['sobject', 'describe']:
    reply({'status': 0, 'result': {'fields': [{'name': 'Status__c'}, {'name': 'Id'}]}})
if args[:3] == ['project', 'retrieve', 'start']:
    target = Path(args[args.index('--target-metadata-dir') + 1])
    (target / 'objects').mkdir(parents=True, exist_ok=True)
    (target / 'objects' / 'X.object').write_text('<CustomObject/>')
    reply({'status': 0, 'result': {'files': []}})
sys.exit(9)
'''
READS = (['org', 'display'], ['data', 'query'], ['sobject', 'describe'], ['project', 'retrieve'])


def obligation(key=KEY, status='passed', kind='claim', beat='B1', proof=True, required=True, at=STAMP, **extra):
    value = dict(key=key, kind=kind, beat=beat, proof_moment=proof, required=required, text='Two overdue rows',
                 result=dict(status=status, observed='2', at=at) if status else None)
    value.update(extra)
    return value


def results(*obligations, sources=(), **extra):
    value = dict(schema=1, folder='orgs/example', org_id=ORG, username=USER, started_at=STARTED, observed_at=STAMP,
                 sources=list(sources), obligations=list(obligations))
    value.update(extra)
    return value


def beat(key='task-2026-10-13-1200-x.md#B1', **extra):
    value = dict(key=key, name='Overdue kit requests', persona='Field rep', login='rep@example.test',
                 start='Kit Requests app > Requests tab > R-0001',
                 steps=[dict(do='Open the Overdue list view', expect='Two overdue rows', ref=KEY),
                        dict(do='Open R-0001', expect='Status shows Overdue', ref=None)],
                 climax=1, transitions=['Switch to the manager dashboard'], fallback='Show the saved screenshot')
    value.update(extra)
    return value


def inventory(root):
    """F23: every entry under root, with its sha256, so overwritten bytes show up, not only new names."""
    found = {}
    for directory, folders, files in os.walk(root):
        for name in folders + files:
            path = Path(directory) / name
            relative = str(path.relative_to(root))
            if path.is_symlink():
                found[relative] = 'link:' + os.readlink(path)
            elif path.is_dir():
                found[relative] = 'dir'
            else:
                found[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


class Fixture(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='scout-prep-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.orgs = self.root / 'orgs'
        self.folder = self.orgs / 'example'
        self.folder.mkdir(parents=True)
        (self.orgs / 'other').mkdir()
        (self.orgs / 'other' / 'task-2026-10-01-0900-other.md').write_text('Another customer.\n')
        self.scratch = self.root / 'scratch'
        self.scratch.mkdir()
        self.results = self.scratch / 'results.json'
        self.destination = self.folder / 'demo-path.md'
        self.clock = prep.now(NOW)
        clock = patch.object(prep, 'current_time', lambda: self.clock, create=True)
        clock.start()
        self.addCleanup(clock.stop)
        self.renders = 0
        real_scratch = prep.scratch_dir  # R01: render makes its own scratch under the vetted base; clean it up

        def tracked():
            path = real_scratch()
            self.addCleanup(shutil.rmtree, str(path), True)
            return path
        scratch = patch.object(prep, 'scratch_dir', tracked)
        scratch.start()
        self.addCleanup(scratch.stop)

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = prep.main([str(a) for a in args])
        return code, output.getvalue()

    def save(self, data):
        self.results.write_text(json.dumps(data))

    def render(self, data, demo_time=None):
        # R01 changed this helper: render chooses its own scratch file and names it.
        self.save(data)
        self.renders += 1
        extra = ['--demo-time', demo_time] if demo_time else []
        code, output = self.cli('render', '--results', self.results, '--folder', self.folder, *extra)
        candidate = Path(json.loads(output)['candidate']) if code == 0 else self.scratch / ('not-rendered-%d.md' % self.renders)
        return code, output, candidate

    def gate(self, candidate, data, org=ORG, user=USER):
        self.save(data)
        return self.cli('check', '--results', self.results, '--candidate', candidate, '--org-id', org, '--username', user)

    def publish(self, candidate, data, org=ORG, user=USER):
        self.save(data)
        return self.cli('publish', '--results', self.results, '--folder', self.folder, '--candidate', candidate,
                        '--org-id', org, '--username', user)

    def published(self, data):
        code, output, candidate = self.render(data)
        self.assertEqual(code, 0, output)
        code, output = self.publish(candidate, data)
        self.assertEqual(code, 0, output)
        return self.destination.read_bytes()

    def regions(self, text):
        return {name: found['body'] for name, found in prep.parse_regions(text).items()}

    def backups(self):
        directory = self.folder / '.scout-work' / 'prep'
        return sorted(directory.iterdir()) if directory.is_dir() else []

    def staged(self):
        return [p.name for p in self.folder.iterdir() if p.name.startswith('demo-path.md.')]


class QueryGrammarTests(unittest.TestCase):
    def test_the_constrained_grammar_accepts_read_only_selects(self):
        for query in ("SELECT Id, Name FROM Account WHERE Name LIKE 'A%' ORDER BY Name LIMIT 5",
                      'SELECT COUNT(Id) n, Status__c FROM Kit_Request__c GROUP BY Status__c',
                      'SELECT Id FROM Kit_Request__c WHERE Due_Date__c < TODAY',
                      'SELECT COUNT() FROM Kit_Request__c WHERE Due_Date__c < LAST_N_DAYS:2',
                      "SELECT Id, Owner.Profile.Name FROM Case WHERE (Status = 'New' OR Status = 'Open') AND NOT Priority = 'Low'",
                      "SELECT Id FROM Account WHERE Industry IN ('Biotech', 'Pharma') AND Type NOT IN ('Other') AND Rating != null",
                      "SELECT Id FROM Contact WHERE Interests__c INCLUDES ('a;b', 'c') AND Region__c EXCLUDES ('x')",
                      'SELECT Id FROM Order WHERE EffectiveDate >= 2026-10-01 AND CreatedDate < 2026-10-13T00:00:00Z',
                      'SELECT MAX(Amount) top, MIN(Amount) low, AVG(Amount), SUM(Amount), COUNT_DISTINCT(OwnerId) FROM Opportunity',
                      'SELECT Id FROM Account ORDER BY Name DESC NULLS LAST, CreatedDate ASC LIMIT 10 OFFSET 20',
                      "SELECT Id FROM Account WHERE Name = 'O\\'Brien \\\\ Co' AND AnnualRevenue > -5.5 AND IsDeleted = false"):
            with self.subTest(query=query):
                self.assertEqual(prep.validate_query(query), query)

    def test_everything_outside_the_grammar_is_refused(self):
        for query in ('SELECT Id FROM Account FOR VIEW', 'SELECT Id FROM Account FOR REFERENCE', 'SELECT Id FROM Account FOR UPDATE',
                      'SELECT Id FROM Account USING SCOPE mine', 'SELECT Id FROM Account ALL ROWS', 'SELECT Id FROM Account; DELETE',
                      'DELETE FROM Account', 'UPDATE Account SET Name = 1', 'SELECT Id FROM `Account`', 'SELECT $(whoami) FROM Account',
                      'SELECT Id FROM Account && sf data delete record', '',
                      # F06 and C01: subqueries, TYPEOF, the stateful UPDATE clauses, comments and a second statement
                      'SELECT Id, (SELECT Id FROM Contacts) FROM Account',
                      'SELECT TYPEOF What WHEN Account THEN Phone END FROM Event',
                      'SELECT Id FROM Account WHERE Id IN (SELECT AccountId FROM Contact)',
                      'SELECT Id FROM Account WHERE Name != null UPDATE TRACKING', 'SELECT Id FROM Account UPDATE VIEWSTAT',
                      'SELECT Id FROM Account WHERE Name != null FOR /* x */ UPDATE',
                      'SELECT Id FROM Account WHERE Name != null -- comment',
                      'SELECT Id FROM Account WHERE Name != null SELECT Id FROM Contact',
                      'SELECT Id FROM Account WITH SECURITY_ENFORCED', 'SELECT Id FROM Account WITH USER_MODE',
                      'SELECT Id FROM Account WHERE Id = :recordId', 'SELECT FIELDS(ALL) FROM Account LIMIT 1',
                      'SELECT Id FROM Account a', 'SELECT Id FROM Account, Contact', "SELECT Id FROM Account WHERE Name = 'open",
                      'SELECT Id FROM Account ＦＯＲ ＵＰＤＡＴＥ', 'SELECT Id FROM Account WHERE Name = "x"',
                      'SELECT Id FROM Account GROUP BY ROLLUP(Name)', 'SELECT Name n FROM Account', 'SELECT Id FROM Account LIMIT -1',
                      'SELECT Id FROM Account WHERE CreatedDate = LAST_N_DAYS', 'SELECT Id FROM Account WHERE Name = Other__c',
                      'SELECT Id, FROM Account', 'SELECT Id FROM Account WHERE', 'SELECT Id FROM Account HAVING COUNT(Id) > 1',
                      'SELECT Id FROM Account\x00', 'SELECT TYPEOF FROM Event', 'SELECT Id FROM Account\xa0WHERE Name = null',
                      'SELECT Id FROM Account LIMIT ５'):
            with self.subTest(query=query):
                with self.assertRaises(prep.Refused):
                    prep.validate_query(query)

    def test_validation_never_rewrites_the_query(self):
        for query in ("SELECT Id FROM Account WHERE Name = 'Ａ  Ｂ'", "SELECT  Id\nFROM Account WHERE Name = 'a  b'"):
            with self.subTest(query=query):
                self.assertEqual(prep.validate_query(query), query)  # F07


class FakeCli(Fixture):
    def setUp(self):
        super().setUp()
        binary = self.root / 'bin' / 'sf'
        binary.parent.mkdir()
        binary.write_text('#!' + sys.executable + '\n' + FAKE)
        binary.chmod(0o700)
        self.calls = self.root / 'calls.jsonl'
        self.state = self.root / 'state.json'
        self.set_state()
        patcher = patch.dict(os.environ, dict(PATH=str(binary.parent), HOME=str(self.root), PREP_CALLS=str(self.calls),
                                              PREP_STATE=str(self.state), PYTHONDONTWRITEBYTECODE='1'), clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        real = getattr(prep, 'scratch_dir', None)
        if real:
            def spy():
                path = real()
                self.addCleanup(shutil.rmtree, str(path), True)
                return path
            scratch = patch.object(prep, 'scratch_dir', spy)
            scratch.start()
            self.addCleanup(scratch.stop)

    def set_state(self, **extra):
        self.state.write_text(json.dumps(dict(dict(org=ORG, username=USER), **extra)))

    def log(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def mutations(self):
        return [c['args'] for c in self.log() if c['args'][:2] not in READS[:3] and c['args'][:2] != READS[3]]

    def run_prep(self, *extra):
        return self.cli('run', '--selector', 'maple', '--username', USER, '--org-id', ORG, *extra)

    def query(self, text):
        code, output = self.run_prep('--kind', 'query', '--query', text)
        self.assertEqual(code, 0, output)
        return json.loads(output)


class RunTests(FakeCli):
    def test_query_binds_first_then_runs_one_constructed_read(self):
        query = 'SELECT Id FROM Kit_Request__c WHERE Due_Date__c < TODAY'
        observed = self.query(query)['observed']
        self.assertEqual([c['args'][:2] for c in self.log()], [['org', 'display'], ['data', 'query'], ['data', 'query']])
        last = self.log()[-1]['args']
        self.assertEqual(last[last.index('--target-org') + 1], USER)
        self.assertEqual(last[last.index('--query') + 1], query)
        self.assertEqual((observed['totalSize'], observed['complete']), (2, True))

    def test_mutations_never_reach_the_cli_and_no_workspace_byte_changes(self):
        before = inventory(self.orgs)
        for extra in (('--kind', 'query', '--query', 'DELETE FROM Account'), ('--kind', 'describe', '--sobject', 'Account; rm -rf /'),
                      ('--kind', 'retrieve', '--metadata', 'CustomObject:X && sf data delete'),
                      ('--kind', 'query', '--query', 'SELECT Id FROM Account WHERE Name != null UPDATE TRACKING')):
            with self.subTest(extra=extra):
                code, output = self.run_prep(*extra)
                self.assertEqual(code, 3, output)
        for extra in (('--kind', 'query', '--query', 'SELECT COUNT() FROM Kit_Request__c'), ('--kind', 'describe', '--sobject', 'Kit_Request__c'),
                      ('--kind', 'retrieve', '--metadata', 'Flow:Kit_Escalation')):
            with self.subTest(extra=extra):
                code, output = self.run_prep(*extra)
                self.assertEqual(code, 0, output)
        self.assertEqual(self.mutations(), [])
        queries = [c['args'][c['args'].index('--query') + 1] for c in self.log() if c['args'][:2] == ['data', 'query']]
        self.assertEqual([q for q in queries if 'Organization' not in q], ['SELECT COUNT() FROM Kit_Request__c'])
        self.assertEqual(inventory(self.orgs), before)

    def test_invalid_input_makes_no_cli_call(self):
        for extra in (('--kind', 'describe', '--sobject', 'Kit_Request__c', '--clock', 'tomorrow'),
                      ('--kind', 'query', '--query', 'SELECT Id FROM Account FOR UPDATE')):
            with self.subTest(extra=extra):
                self.assertEqual(self.run_prep(*extra)[0], 3)
        self.assertEqual(self.log(), [])

    def test_binding_mismatch_runs_nothing_else(self):
        self.set_state(org='00D000000000002EAA')
        code, output = self.run_prep('--kind', 'describe', '--sobject', 'Kit_Request__c')
        self.assertEqual(code, 3)
        self.assertIn('binding check failed', output)
        self.assertEqual([c['args'][:2] for c in self.log()], [['org', 'display']])

    def test_retrieve_runs_from_one_vetted_scratch_that_holds_its_target(self):
        before = inventory(self.orgs)
        code, output = self.run_prep('--kind', 'retrieve', '--metadata', 'CustomObject:Kit_Request__c')
        self.assertEqual(code, 0, output)
        observed = json.loads(output)['observed']
        directory = Path(observed['directory'])
        call = [c for c in self.log() if c['args'][:3] == ['project', 'retrieve', 'start']][0]
        self.assertEqual(Path(call['args'][call['args'].index('--target-metadata-dir') + 1]), directory)
        self.assertEqual(Path(call['cwd']).resolve(), directory.parent.resolve())  # N3: cwd inside that scratch
        self.assertEqual(str(directory.parent.parent), os.path.realpath(prep.SCRATCH_BASE))
        self.assertEqual((observed['files'], observed['complete']), (['objects/X.object'], True))
        self.assertEqual(inventory(self.orgs), before)

    def test_scratch_ignores_tmpdir_and_checks_its_resolved_base(self):
        with patch.dict(os.environ, {'TMPDIR': str(self.folder)}), patch.object(prep.tempfile, 'tempdir', None):
            self.query('SELECT Id FROM Account')
            code, output = self.run_prep('--kind', 'retrieve', '--metadata', 'Flow:Kit_Escalation')
            self.assertEqual(code, 0, output)
        self.assertEqual(list(self.folder.iterdir()), [])
        for call in self.log():
            self.assertFalse(call['cwd'].startswith(str(self.orgs)), call)  # F05
        link = self.root / 'base-link'
        link.symlink_to(self.folder, target_is_directory=True)
        with patch.object(prep, 'SCRATCH_BASE', str(link)):
            code, output = self.run_prep('--kind', 'query', '--query', 'SELECT Id FROM Account')
        self.assertEqual(code, 3, output)
        self.assertIn('scratch', output)
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_a_query_result_needs_records_and_an_integer_total(self):
        for malformed in (None, [], {'records': []}, {'totalSize': '2', 'records': []}, {'totalSize': 2, 'records': 'x'},
                          {'totalSize': True, 'records': []}, {'totalSize': 1, 'records': [1]}):
            with self.subTest(result=malformed):
                self.set_state(result=malformed)
                code, output = self.run_prep('--kind', 'query', '--query', 'SELECT Id FROM Account')
                self.assertEqual(code, 3, output)  # F18
                self.assertIn('unusable', output)

    def test_large_or_partial_results_say_they_are_incomplete(self):
        self.set_state(rows=2001)
        observed = self.query('SELECT Id FROM Account')['observed']
        self.assertEqual((observed['totalSize'], len(observed['records']), observed['complete']), (2001, 2000, False))  # F19
        self.set_state(rows=3, total=5)
        self.assertFalse(self.query('SELECT Id FROM Account')['observed']['complete'])
        self.set_state(rows=2, done=False)
        self.assertFalse(self.query('SELECT Id FROM Account')['observed']['complete'])
        self.set_state(rows=0, total=7)
        observed = self.query('SELECT COUNT() FROM Kit_Request__c')['observed']
        self.assertEqual((observed['totalSize'], observed['complete']), (7, True))

    def test_cli_errors_keep_their_name_and_message_redacted(self):
        message = "No such column 'Bad__c' on entity 'Account'. Session 00D000000000001!AQ0AQExampleTokenValue123"
        for stream in ('stdout', 'stderr'):
            with self.subTest(stream=stream):
                self.set_state(error=['INVALID_FIELD', message], error_stream=stream)
                code, output = self.run_prep('--kind', 'query', '--query', 'SELECT Bad__c FROM Account')
                self.assertEqual(code, 3, output)  # F20
                error = json.loads(output)['error']
                self.assertEqual(error['name'], 'INVALID_FIELD')
                self.assertIn("No such column 'Bad__c' on entity 'Account'.", error['message'])
                self.assertNotIn('ExampleTokenValue123', output)


class VerdictTests(Fixture):
    def verdict(self, data, demo_time=None, code=0):
        self.save(data)
        actual, output = self.cli('verdict', '--results', self.results, *(['--demo-time', demo_time] if demo_time else []))
        self.assertEqual(actual, code, output)
        return json.loads(output)

    def outcome(self, *obligations, **extra):
        return self.verdict(results(*obligations, **extra))['verdict']

    def test_table_is_total_and_ordered(self):
        source = 'task-2026-10-14-0900-y.md § Amendments'
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
            # F10 flips the old expectation ('ready with exceptions'): an optional failure blocks like any other.
            (results(obligation(), obligation('t.md#opt', 'failed', proof=False, required=False)), 'not ready'),
            # F08 flips the old expectation ('ready'): a supersession that names no live obligation supersedes nothing.
            (results(obligation(), obligation('t.md#old', 'failed', proof=False, superseded_by='t2.md#B1/claim1')), 'not ready'),
            # R05 changed this case: the supersession's source is one this run read.
            (results(obligation(), obligation('t.md#old', 'failed', proof=False, superseded_by=KEY, supersession_source=source),
                     sources=[dict(path='task-2026-10-14-0900-y.md', state='read')]), 'ready'),
            (results(obligation(), obligation('t.md#B1/c2', 'passed', at='2000-01-01T00:00:00+00:00', proof=False)), 'not ready'),
            (results(), 'not ready'),
            (results(obligation(proof=False)), 'not ready'),
            (results(obligation(), sources=[dict(path='task-old.md', state='unreadable')]), 'not ready'),
            (results(obligation(), sources=[dict(path='other.md', state='quarantined')]), 'not ready'),
            (results(obligation(), sources=[dict(path='other.md', state='unrelated')]), 'ready'),
        ]
        for data, expected in cases:
            with self.subTest(expected=expected, obligations=[(o['key'], (o.get('result') or {}).get('status')) for o in data['obligations']]):
                self.assertEqual(self.verdict(data)['verdict'], expected)

    def test_supersession_needs_another_live_obligation_and_its_source(self):
        source = 'task-2026-10-14-0900-y.md § Amendments'
        read = [dict(path='task-2026-10-14-0900-y.md', state='read')]  # R05 changed this test: the source is a read source
        old = lambda **extra: obligation('t.md#I2', 'failed', kind='item', proof=False, **extra)  # noqa: E731
        self.assertEqual(self.outcome(obligation(), old(superseded_by=KEY, supersession_source=source), sources=read), 'ready')
        for bare in ('yes', 'task-2026-10-14-0900-y.md', 'unread-task.md § Amendments', 'task-2026-10-14-0900-y.md § '):
            with self.subTest(bare=bare):  # R05: provenance names a read source and a section
                self.assertEqual(self.outcome(obligation(), old(superseded_by=KEY, supersession_source=bare), sources=read), 'not ready')
        for extra in (dict(superseded_by='missing-task.md#missing', supersession_source=source),
                      dict(superseded_by='t.md#I2', supersession_source=source), dict(superseded_by=KEY),
                      dict(superseded_by=KEY, supersession_source=' '), dict(superseded_by='t.md#I3', supersession_source=source)):
            with self.subTest(extra=extra):
                retired = obligation('t.md#I3', 'passed', kind='item', proof=False, superseded_by=KEY, supersession_source=source)
                self.assertEqual(self.outcome(obligation(), retired, old(**extra), sources=read), 'not ready')
        for successor in (True, {'anything': 'goes'}, ['t.md#I3']):
            with self.subTest(successor=successor):
                data = results(obligation(), old(superseded_by=successor, supersession_source=source))
                self.assertEqual(prep.verdict(data, prep.now(NOW))['verdict'], 'not ready')
                self.verdict(data, code=3)

    def test_a_deliberately_dropped_optional_obligation_is_history(self):
        source = 'task-2026-10-13-1200-x.md § story.beats[0].claims'
        read = [dict(path='orgs/example/task-2026-10-13-1200-x.md', state='read')]  # R05: a read source, here by its file name
        dropped = lambda **extra: obligation('t.md#B1/c9', 'failed', proof=False, dropped=True, **extra)  # noqa: E731
        self.assertEqual(self.outcome(obligation(), dropped(required=False, drop_source=source), sources=read), 'ready')
        self.assertEqual(self.outcome(obligation(), dropped(required=True, drop_source=source), sources=read), 'not ready')
        self.assertEqual(self.outcome(obligation(), dropped(required=False), sources=read), 'not ready')
        self.assertEqual(self.outcome(obligation(), dropped(required=False, drop_source='SE withdrew it'), sources=read), 'not ready')

    def test_only_read_and_unrelated_sources_pass(self):
        for state in ('read', 'unrelated'):
            self.assertEqual(self.outcome(obligation(), sources=[dict(path='task.md', state=state)]), 'ready')
        for state in ('unknown', 'missing', 'READ', 'unreadable', 'quarantined', 'malformed', ''):
            with self.subTest(state=state):
                self.assertEqual(self.outcome(obligation(), sources=[dict(path='task.md', state=state)]), 'not ready')  # F09
        self.assertEqual(self.outcome(obligation(), sources=[dict(path='task.md', state='unreadable', required=False)]), 'not ready')
        for sources in ([dict(path='task.md', state=None)], [None]):
            with self.subTest(sources=sources):
                self.assertEqual(prep.verdict(results(obligation(), sources=sources), prep.now(NOW))['verdict'], 'not ready')
                self.verdict(results(obligation(), sources=sources), code=3)

    def test_optional_failures_and_unknowns_block(self):
        for status in ('failed', 'unknown', 'unavailable', 'open', 'nonsense', None):
            with self.subTest(status=status):
                gap = obligation('t.md#I2', status, kind='item', proof=False, required=False)
                self.assertEqual(self.outcome(obligation(), gap), 'not ready')  # F10
        self.assertEqual(self.outcome(obligation(), obligation('t.md#B1/c2', 'eye', proof=False, required=False)), 'ready with exceptions')

    def test_the_demo_time_defaults_to_now_and_expiry_applies_to_every_status(self):
        self.assertEqual(self.outcome(obligation(valid_until='2026-10-12')), 'not ready')  # F11: no --demo-time
        self.assertEqual(self.outcome(obligation(valid_until='2026-10-13')), 'ready')
        for status, kind in (('eye', 'claim'), ('visual_qa', 'visual_qa'), ('persona', 'persona'), ('passed', 'config')):
            with self.subTest(status=status):
                outcome = self.verdict(results(obligation(), obligation('t.md#B1/x', status, kind=kind, proof=False, valid_until='2026-10-12')))
                self.assertEqual(outcome['verdict'], 'not ready')
                self.assertIn('expires', ' '.join(outcome['blocking']))
        self.assertEqual(self.verdict(results(obligation(valid_until='2026-10-12')), '2026-10-11T10:00:00+02:00')['verdict'], 'not ready')

    def test_validity_window_is_checked_through_the_demo_time(self):
        data = results(obligation(valid_until='2026-10-14'))
        self.assertEqual(self.verdict(data, '2026-10-14T10:00:00+02:00')['verdict'], 'ready')
        self.assertEqual(self.verdict(data, '2026-10-15T10:00:00+02:00')['verdict'], 'not ready')

    def test_observation_times_must_fall_inside_this_run(self):
        for at in ('2000-01-01T00:00:00+00:00', '2026-10-13T14:00:00+02:00', '2026-10-13T17:00:00+02:00'):
            with self.subTest(at=at):
                self.assertEqual(self.outcome(obligation(at=at)), 'not ready')  # F12: a real time, outside this run
        # R06 changed these: a result without a usable time is refused outright, whatever its status.
        for at in ('not-a-time', '2026-10-13T15:00:00', None, '20261013T150000+0200'):
            for status in ('passed', 'failed', 'open'):
                with self.subTest(at=at, status=status):
                    self.assertIn("needs its result's at", self.verdict(results(obligation(), obligation('t.md#B1/c9', status, proof=False, at=at)), code=3)['refused'])
        self.verdict(results(obligation(), obligation('t.md#B1/eye', 'eye', proof=False, at=None)), code=3)
        for at in ('2026-10-13T13:00:00Z', '2026-10-13T15:00:00+0200', '2026-10-13 15:00+02:00', '2026-10-13T15:00:00.25+02:00'):
            with self.subTest(at=at):
                self.assertEqual(self.outcome(obligation(at=at)), 'ready')
        for extra in (dict(started_at=None), dict(started_at='2026-10-13T14:50:00'), dict(started_at='2026-10-13T16:30:00+02:00'),
                      dict(observed_at='2026-10-13T14:00:00+02:00'), dict(observed_at='2026-10-13T16:30:00+02:00')):
            with self.subTest(extra=extra):
                self.verdict(results(obligation(), **extra), code=3)

    def test_keys_are_task_qualified_and_unique(self):
        for key in ('B1/claim1', '#c1', 'task.md#', '#', 'task#c1', '.md#c1', 'task.md#c1\n', 'dir/task.md#c1', 'task.md#c 1'):
            with self.subTest(key=key):
                self.verdict(results(obligation(key)), code=3)  # F14
        self.verdict(results(obligation(), obligation()), code=3)
        self.assertEqual(self.outcome(obligation('a.b-c_d.md#B1/claim-1.x')), 'ready')

    def test_eye_is_only_for_claims_config_persona_and_visual_qa(self):
        for kind in ('item', 'job', 'checkpoint', 'manual', 'flip'):
            with self.subTest(kind=kind):
                outcome = self.verdict(results(obligation(), obligation('t.md#gap', 'eye', kind=kind, proof=False)))
                self.assertEqual(outcome['verdict'], 'not ready')  # C03
                self.assertIn('unknown', ' '.join(outcome['blocking']))
        for kind in ('claim', 'config', 'persona', 'visual_qa'):
            with self.subTest(kind=kind):
                self.assertEqual(self.outcome(obligation(), obligation('t.md#x', 'eye', kind=kind, proof=False)), 'ready with exceptions')
        self.assertEqual(self.outcome(obligation(), obligation('t.md#x', 'visual_qa', proof=False)), 'not ready')
        self.assertEqual(self.outcome(obligation(), obligation('t.md#x', 'persona', kind='item', proof=False)), 'not ready')

    def test_a_story_beat_without_checks_blocks(self):
        self.assertEqual(self.outcome(obligation(), beats=[beat()]), 'ready')
        self.assertEqual(self.outcome(obligation(), beats=[beat(), beat('task-2026-10-13-1200-x.md#B2', steps=[], climax=None)]), 'not ready')

    def test_malformed_results_exit_3_and_never_raise(self):
        def first(**changes):
            return lambda d: dict(d, obligations=[dict(d['obligations'][0], **changes)])
        mutations = [
            lambda d: [d], lambda d: dict(d, schema=True), lambda d: dict(d, sources=[None]),
            lambda d: dict(d, sources=[{'path': 1, 'state': 'read'}]), lambda d: dict(d, obligations={}),
            lambda d: dict(d, obligations=[['x']]), first(valid_until={'bad': 'date'}), first(valid_until='2026-13-01'),
            first(valid_until='20261013'), first(result=['passed']), first(result={'status': 1, 'at': STAMP}),
            first(result={'status': 'passed', 'at': 5}), first(required='yes'), first(proof_moment=1), first(text=5),
            first(beat=7), first(beat='B 1'), first(kind=3), first(superseded_by=True), first(dropped='yes'), first(fix=['x']),
            first(supersession_source=4), lambda d: dict(d, beats={}), lambda d: dict(d, beats=[1]),
            lambda d: dict(d, beats=[{'key': 'B1'}]), lambda d: dict(d, beats=[beat(steps='x')]),
            lambda d: dict(d, beats=[beat(steps=[{'do': 'a', 'expect': 'b', 'ref': 'nope.md#x'}])]),
            lambda d: dict(d, beats=[beat(steps=[{'do': 3, 'expect': 'b', 'ref': None}])]),
            lambda d: dict(d, beats=[beat(steps=[{'do': 'a', 'expect': 'b', 'ref': [KEY]}])]), lambda d: dict(d, beats=[beat(steps=[3])]),
            lambda d: dict(d, beats=[beat(climax=0)]), lambda d: dict(d, beats=[beat(climax=True)]),
            lambda d: dict(d, beats=[beat(climax=3)]), lambda d: dict(d, beats=[beat(transitions='x')]),
            lambda d: dict(d, beats=[beat(), beat()]), lambda d: dict(d, constraints=[1]),
            first(text='<!-- scout:end drift -->'), first(fix='Org-verified: tomorrow'), lambda d: dict(d, username=''),
        ]
        raw = ['not json', '[' * 100000, '{"schema":1,"schema":1}', '{"schema": NaN}']
        for number, mutate in enumerate(mutations + raw):
            with self.subTest(case=number):
                if isinstance(mutate, str):
                    self.results.write_text(mutate)
                else:
                    self.save(mutate(results(obligation())))
                for args in (('verdict',), ('render', '--folder', self.folder),
                             ('check', '--candidate', self.scratch / 'none.md', '--org-id', ORG, '--username', USER)):
                    try:
                        code, output = self.cli(args[0], '--results', self.results, *args[1:])
                    except Exception as error:  # F21: never raises
                        self.fail('%s raised %s' % (args[0], type(error).__name__))
                    self.assertEqual(code, 3, output)
                    self.assertIn('refused', output)


class RenderTests(Fixture):
    def test_a_new_file_carries_the_marker_and_the_five_regions_in_order(self):
        code, output, candidate = self.render(results(obligation()))
        self.assertEqual(code, 0, output)
        text = candidate.read_text()
        self.assertTrue(text.startswith(prep.MARKER + '\n'))
        self.assertEqual(list(prep.parse_regions(text)), list(prep.REGIONS))
        meta = json.loads(Path(str(candidate) + '.meta.json').read_text())
        self.assertEqual((meta['base'], meta['destination']), ('absent', str(self.destination)))
        self.assertFalse(self.destination.exists())

    def test_the_sections_carry_the_c3_fields(self):
        failed = obligation('task-2026-10-13-1200-x.md#B1/claim2', 'failed', proof=False, text='Status shows Overdue',
                            was='Overdue since 2026-10-12', now='New', fix='Run seed/kit-requests.apex with --reset')
        steps = [dict(do='Open the Overdue list view', expect='Two overdue rows', ref=KEY),
                 dict(do='Open R-0001', expect='Status shows Overdue', ref=failed['key']),
                 dict(do='Point at the owner', expect='Owner is the field rep', ref=None)]
        data = results(obligation(), failed, obligation('t.md#B1/qa', 'visual_qa', kind='visual_qa', proof=False, text='Badge colour'),
                       beats=[beat(steps=steps, climax=2)], constraints=['Agents stay inactive in this org edition'])
        code, output, candidate = self.render(data)
        self.assertEqual(code, 0, output)
        drift, checklist, path, seams, runs = (self.regions(candidate.read_text())[n] for n in prep.REGIONS)
        self.assertTrue(drift.startswith('Org-verified: %s against %s (%s) — not ready — 1 of 3 checks passed\n' % (STAMP, ORG, USER)))
        self.assertIn('- ✗ Status shows Overdue (%s) — was: Overdue since 2026-10-12; now: New (%s); fix: Run seed/kit-requests.apex with --reset'
                      % (failed['key'], prep.at_of(failed)), drift)  # F16; R06 changed it: every check shows its time
        self.assertIn('fix: Run seed/kit-requests.apex with --reset', checklist)
        for line in ('### task-2026-10-13-1200-x.md#B1 · Overdue kit requests — not ready',
                     '- Persona: Field rep · Login: rep@example.test · Start: Kit Requests app > Requests tab > R-0001',
                     '- Do: Open the Overdue list view → Expect: Two overdue rows ✓',
                     '- ★ Do: Open R-0001 → Expect: Status shows Overdue ✗',
                     '- Do: Point at the owner → Expect: Owner is the field rep',
                     '- Transition: Switch to the manager dashboard',
                     '- Say: Two overdue rows (proof moment) ✓ (%s)' % STAMP):
            self.assertIn(line + '\n', path)
        self.assertNotIn('Say: Status shows Overdue', path)  # verified claim lines only
        self.assertIn('- Visual QA: Badge colour (t.md#B1/qa) (%s)' % STAMP, seams)
        self.assertIn('- Fallback for task-2026-10-13-1200-x.md#B1 · Overdue kit requests: Show the saved screenshot', seams)
        self.assertIn('- Org constraint: Agents stay inactive in this org edition', seams)
        self.assertEqual(runs, '## Prep runs\n- %s — not ready — 1 of 3 checks passed\n' % STAMP)

    def test_story_order_is_first_appearance_and_beats_stay_per_task(self):
        data = results(obligation('a.md#B2/c1', beat='B2', text='First beat'),
                       obligation('a.md#B1/c1', beat='B1', text='Second beat', proof=False),
                       obligation('b.md#B1/c1', beat='B1', text='Different task beat', proof=False),
                       obligation('fix.md#I1', kind='item', beat='a.md#B2', text='Repaired list view', proof=False))
        code, output, candidate = self.render(data)
        self.assertEqual(code, 0, output)
        path = self.regions(candidate.read_text())['path']
        self.assertEqual(re.findall(r'(?m)^### (\S+)', path), ['a.md#B2', 'a.md#B1', 'b.md#B1'])  # F15
        self.assertLess(path.index('Repaired list view'), path.index('### a.md#B1'))
        code, output, candidate = self.render(dict(data, beats=[beat('b.md#B1', steps=[], climax=None), beat('a.md#B1', steps=[], climax=None)]))
        self.assertEqual(code, 0, output)
        self.assertEqual(re.findall(r'(?m)^### (\S+)', self.regions(candidate.read_text())['path']), ['b.md#B1', 'a.md#B1', 'a.md#B2'])

    def test_obligations_without_a_beat_render_under_general(self):
        data = results(obligation(beat=None))
        code, output, candidate = self.render(data)
        self.assertEqual(code, 0, output)
        path = self.regions(candidate.read_text())['path']
        self.assertIn('### General — ready\n- Say: Two overdue rows (proof moment) ✓ (%s)\n' % STAMP, path)  # F13
        self.assertEqual(self.gate(candidate, data)[0], 0)

    def test_prep_runs_accumulate(self):
        self.published(results(obligation(valid_until='2026-10-13'), obligation('t.md#B1/c2', 'failed', proof=False)))
        self.published(results(obligation(at='2026-10-13T15:25:00+02:00'), started_at='2026-10-13T15:20:00+02:00',
                               observed_at='2026-10-13T15:30:00+02:00'))
        runs = self.regions(self.destination.read_text())['runs']
        self.assertEqual(runs, '## Prep runs\n- %s — not ready — 1 of 2 checks passed\n- 2026-10-13T15:30:00+02:00 — ready — 1 of 1 checks passed\n'
                         % STAMP)  # F17

    def test_ownership_needs_the_marker_every_region_in_order_and_no_fence(self):
        code, output, candidate = self.render(results(obligation()))
        good = candidate.read_text()
        found = prep.parse_regions(good)
        drift, runs = good[found['drift']['start']:found['drift']['end']], good[found['runs']['start']:found['runs']['end']]
        copied = prep.region('seams', '## Known seams\nNone.\n')
        cases = {
            'copied region': '# Hand-made rehearsal notes\n\nExample from Scout:\n' + copied,
            'fenced copy': '# Hand-made rehearsal notes\n```markdown\n' + copied + '```\n',
            'marker below a title': '# My title\n' + good,
            'missing region': good[:found['seams']['start']] + good[found['seams']['end']:],
            'out of order': good.replace(drift, '\0').replace(runs, drift).replace('\0', runs),
            'fenced regions': good.replace(drift, '~~~\n' + drift + '~~~\n'),
            'open fence': good.replace(runs, '```\n' + runs),
            'copied markers twice': good + '\n' + good[good.index('<!--', 1):],
            'marker only': prep.MARKER + '\n# Notes\n',
            'malformed marker': prep.MARKER + '\n<!-- scout:begin path sha256=zz -->\n',
            'unclosed region': prep.MARKER + '\n<!-- scout:begin path sha256=' + 'a' * 64 + ' -->\nx\n',
            'nested regions': prep.MARKER + '\n<!-- scout:begin path sha256=' + 'a' * 64 + ' -->\n<!-- scout:begin seams sha256=' + 'a' * 64 + ' -->\n',
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                self.destination.write_text(text)
                code, output, candidate = self.render(results(obligation()))
                self.assertEqual(code, 3, output)  # F03
                self.assertEqual(self.destination.read_text(), text)
                self.assertFalse(candidate.exists())
        owned = good.replace(prep.MARKER + '\n', prep.MARKER + '\r\n# SE title\r\n```yaml\nscout: enabled\n```\n', 1) + '## SE notes\r\n'
        self.destination.write_text(owned)
        code, output, candidate = self.render(results(obligation(text='Updated observation')))
        self.assertEqual(code, 0, output)

    def test_prep_never_creates_or_follows_a_customer_folder(self):
        self.save(results(obligation()))
        linked = self.scratch / 'linked-folder'
        linked.symlink_to(self.folder, target_is_directory=True)
        for folder in (self.orgs / 'no-such-customer', linked):
            with self.subTest(folder=folder.name):
                code, output = self.cli('render', '--results', self.results, '--folder', folder)
                self.assertEqual(code, 3, output)  # C02
                self.assertIn('never creates', output)
        self.assertFalse((self.orgs / 'no-such-customer').exists())
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_an_se_edit_inside_a_region_refuses_regeneration(self):
        data = results(obligation())
        self.published(data)
        edited = self.destination.read_text().replace('## Known seams\n', '## Known seams\n- My own seam note\n')
        self.destination.write_text(edited)
        code, output, candidate = self.render(data)
        self.assertEqual(code, 3, output)  # X10
        self.assertIn('edited Scout region', output)
        self.assertEqual((self.destination.read_text(), candidate.exists()), (edited, False))

    def test_render_writes_only_into_a_new_scratch_folder_of_its_own(self):
        """R01 changed this test: no caller chooses where the candidate lands, so --out is gone."""
        task = self.folder / 'task-owned.md'
        task.write_text('ORIGINAL TASK EVIDENCE\n')
        self.save(results(obligation()))
        with self.assertRaises(SystemExit):  # argparse: --out is no longer an option
            self.cli('render', '--results', self.results, '--folder', self.folder, '--out', self.orgs / 'other' / 'task-new.md')
        first, second = (Path(json.loads(self.cli('render', '--results', self.results, '--folder', self.folder)[1])['candidate'])
                         for _ in range(2))
        base = Path(os.path.realpath(prep.SCRATCH_BASE))
        for candidate in (first, second):
            self.assertEqual(candidate.parent.parent, base)
            self.assertTrue(candidate.parent.name.startswith('scout-prep-'))
            self.assertEqual(stat.S_IMODE(candidate.parent.stat().st_mode), 0o700)
            self.assertTrue(prep.meta_path(candidate).is_file())
        self.assertNotEqual(first.parent, second.parent)  # every render gets a new folder; nothing is overwritten
        self.assertEqual(task.read_text(), 'ORIGINAL TASK EVIDENCE\n')
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ['task-owned.md'])
        self.assertEqual(sorted(p.name for p in self.orgs.iterdir()), ['example', 'other'])
        self.assertEqual([p.name for p in (self.orgs / 'other').iterdir()], ['task-2026-10-01-0900-other.md'])


class GateTests(Fixture):
    def test_the_gate_re_renders_every_region(self):
        _, _, candidate = self.render(results(obligation(text='Old task claim')))
        current = results(obligation('new-task.md#B9/claim9', text='Different claim', beat='B9'))
        code, output = self.gate(candidate, current)
        self.assertEqual(code, 3, output)  # F13: same totals, different claims
        self.assertIn('does not match the results', output)
        data = results(obligation())
        _, _, candidate = self.render(data)
        text = candidate.read_text()
        found = prep.parse_regions(text)['path']
        forged = prep.region('path', found['body'].replace('Two overdue rows', 'Three overdue rows'))
        candidate.write_text(text[:found['start']] + forged + text[found['end']:])
        self.assertIn('hand-assembled', self.gate(candidate, data)[1])  # Q03 changed it: a re-hashed region breaks the set line first
        _, _, candidate = self.render(data)
        self.assertEqual(self.gate(candidate, data), (0, 'prep: check pass\n'))

    def test_the_header_appears_exactly_once(self):
        data = results(obligation())
        _, _, candidate = self.render(data)
        text = candidate.read_text()
        for forged in (text + '\nOrg-verified: 2026-10-13 against 00D000000000002EAA (x) — ready\n',
                       '# Org-verified: another-org — ready\n\n' + text):
            with self.subTest(forged=forged[:30]):
                candidate.write_text(forged)
                code, output = self.gate(candidate, data)
                self.assertEqual(code, 3, output)  # F13
                self.assertIn('Org-verified', output)

    def test_gate_rejects_mismatched_stamp_identity_tampering_and_missing_results(self):
        data = results(obligation())
        _, _, candidate = self.render(data)
        self.assertEqual(self.gate(candidate, data, org='00D000000000002EAA')[0], 3)
        candidate.write_text(candidate.read_text().replace('— ready —', '— ready with exceptions —'))
        self.assertEqual(self.gate(candidate, data)[0], 3)
        _, _, candidate = self.render(data)
        candidate.write_text(candidate.read_text().replace('Two overdue rows', 'Three overdue rows'))
        self.assertIn('changed after rendering', self.gate(candidate, data)[1])
        data['obligations'].append(obligation('t.md#I9', None, kind='item', proof=False))
        _, _, candidate = self.render(data)
        self.assertIn('has no result', self.gate(candidate, data)[1])


class PublishTests(Fixture):
    def test_render_gate_publish_and_regenerate(self):
        data = results(obligation())
        published = self.published(data).decode()
        self.assertTrue(published.startswith(prep.MARKER + '\n'))
        self.assertIn('ready — 1 of 1 checks passed', published)
        note = '\n## My own notes\nKeep the Willowgate tab open.\r\n'
        with open(self.destination, 'w', newline='') as stream:
            stream.write(published + note)
        edited = self.destination.read_bytes()
        data['obligations'].append(obligation('t.md#B2/c', 'failed', beat='B2', proof=False))
        self.published(data)
        regenerated = self.destination.read_bytes().decode()
        self.assertTrue(regenerated.endswith(note))
        self.assertIn('not ready', regenerated)
        self.assertEqual([p.read_bytes() for p in self.backups()], [edited])
        self.assertEqual(self.staged(), [])

    def test_publish_runs_the_gate_and_refuses_what_scout_does_not_own(self):
        data = results(obligation())
        arbitrary = self.scratch / 'arbitrary.md'
        arbitrary.write_text('Arbitrary ungated output\n')
        self.assertEqual(self.publish(arbitrary, data)[0], 3)  # no render metadata
        Path(str(arbitrary) + '.meta.json').write_text(json.dumps(dict(schema=1, destination=str(self.destination), base='absent')))
        self.assertEqual(self.publish(arbitrary, data)[0], 3)  # F02: the gate refuses it
        self.assertFalse(self.destination.exists())
        _, _, candidate = self.render(data)
        self.assertEqual(self.publish(candidate, results(obligation(text='Another claim')))[0], 3)
        self.assertEqual(self.publish(candidate, data, org='00D000000000002EAA')[0], 3)
        self.destination.write_text('# My handmade file\nSE notes\n')
        code, output = self.publish(candidate, data)
        self.assertEqual(code, 3, output)
        self.assertEqual(self.destination.read_text(), '# My handmade file\nSE notes\n')
        self.destination.unlink()
        _, _, elsewhere = self.render(data)
        meta = Path(str(elsewhere) + '.meta.json')
        meta.write_text(json.dumps(dict(json.loads(meta.read_text()), destination=str(self.orgs / 'other' / 'demo-path.md'))))
        self.assertEqual(self.publish(elsewhere, data)[0], 3)
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.staged(), [])

    def test_a_save_after_render_is_never_overwritten(self):
        data = results(obligation())
        self.published(data)
        _, _, candidate = self.render(data)
        self.destination.write_text(self.destination.read_text() + '\nSE save after render\n')
        code, output = self.publish(candidate, data)
        self.assertEqual(code, 3, output)  # F01
        self.assertTrue(self.destination.read_text().endswith('SE save after render\n'))
        self.assertEqual((self.backups(), self.staged()), ([], []))

    def test_a_save_racing_the_move_to_backup_is_restored(self):
        data = results(obligation())
        self.published(data)
        _, _, candidate = self.render(data)
        real = os.rename
        def racing(source, destination, *args, **kwargs):
            if source == prep.NAME:  # R02 changed this hook: publish moves and links by name, relative to the folder's descriptor
                self.destination.write_text(self.destination.read_text() + '\nLAST SECOND SE SAVE\n')
            return real(source, destination, *args, **kwargs)
        with patch.object(prep.os, 'rename', racing):
            code, output = self.publish(candidate, data)
        self.assertEqual(code, 3, output)  # F01
        self.assertTrue(self.destination.read_text().endswith('LAST SECOND SE SAVE\n'))
        self.assertIn(str(self.destination), output)
        self.assertEqual(self.staged(), [])

    def test_a_save_between_the_move_and_the_link_keeps_both_files(self):
        data = results(obligation())
        previous = self.published(data)
        _, _, candidate = self.render(data)
        real = os.rename
        def racing(source, destination, *args, **kwargs):
            moved = real(source, destination, *args, **kwargs)
            if source == prep.NAME:  # R02 changed this hook: publish moves and links by name, relative to the folder's descriptor
                self.destination.write_text('NEW FILE SAVED BY THE EDITOR\n')
            return moved
        with patch.object(prep.os, 'rename', racing):
            code, output = self.publish(candidate, data)
        self.assertEqual(code, 3, output)  # F01: link never clobbers
        self.assertEqual(self.destination.read_text(), 'NEW FILE SAVED BY THE EDITOR\n')
        self.assertEqual([p.read_bytes() for p in self.backups()], [previous])
        self.assertIn(str(self.backups()[0]), output)
        self.assertEqual(self.staged(), [])

    def test_a_file_created_after_an_absent_render_is_kept(self):
        data = results(obligation())
        _, _, candidate = self.render(data)
        real = os.link
        def racing(source, destination, *args, **kwargs):
            if destination == prep.NAME:  # R02 changed this hook: publish moves and links by name, relative to the folder's descriptor
                self.destination.write_text('HAND-MADE, SAVED DURING PREP\n')
            return real(source, destination, *args, **kwargs)
        with patch.object(prep.os, 'link', racing):
            code, output = self.publish(candidate, data)
        self.assertEqual(code, 3, output)
        self.assertEqual(self.destination.read_text(), 'HAND-MADE, SAVED DURING PREP\n')
        self.assertEqual(self.staged(), [])

    def test_without_hard_links_nothing_changes(self):
        data = results(obligation())
        previous = self.published(data)
        data['obligations'][0]['text'] = 'Updated observation'
        _, _, candidate = self.render(data)
        with patch.object(prep.os, 'link', side_effect=OSError(errno.EXDEV, 'synthetic cross-device error')):
            code, output = self.publish(candidate, data)
        self.assertEqual(code, 4, output)
        self.assertEqual(self.destination.read_bytes(), previous)
        self.assertEqual((self.backups(), self.staged()), ([], []))

    def test_backups_and_the_destination_never_follow_a_symlink(self):
        data = results(obligation())
        self.published(data)
        previous = self.destination.read_bytes()
        other = self.orgs / 'other'
        before = inventory(other)
        work = self.folder / '.scout-work'
        work.symlink_to(other, target_is_directory=True)
        _, _, candidate = self.render(data)
        self.assertEqual(self.publish(candidate, data)[0], 3)  # F04
        work.unlink()
        work.mkdir()
        (work / 'prep').symlink_to(other, target_is_directory=True)
        _, _, candidate = self.render(data)
        self.assertEqual(self.publish(candidate, data)[0], 3)
        self.assertEqual(self.destination.read_bytes(), previous)
        self.destination.unlink()
        self.destination.symlink_to(other / 'task-2026-10-01-0900-other.md')
        self.assertEqual(self.render(data)[0], 3)
        self.assertEqual(inventory(other), before)

    def test_publication_changes_only_demo_path_and_adds_one_backup(self):
        data = results(obligation())
        previous = self.published(data)
        before = inventory(self.orgs)
        data['obligations'][0]['text'] = 'Updated observation'
        _, _, candidate = self.render(data)
        self.assertEqual(self.gate(candidate, data)[0], 0)
        self.assertEqual(inventory(self.orgs), before)  # F23: render and check write nothing in the workspace
        self.assertEqual(self.publish(candidate, data)[0], 0)
        after = inventory(self.orgs)
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        backup = self.backups()[0]
        self.assertEqual(changed, sorted(['example/.scout-work', 'example/.scout-work/prep', 'example/demo-path.md',
                                          str(backup.relative_to(self.orgs))]))
        self.assertEqual(backup.read_bytes(), previous)


class FixMatrixTests(FakeCli):
    """F23 and X15: a fix is a separate /scout task; prep never writes, and after a fix it runs again in full.

    R10: these are observation tests. They pin what prep observes and that it never writes; the SE's answer and the
    fix task itself are native behavior, graded by the battery's B5 and C05's route pins."""
    CLAIM = 'SELECT COUNT() FROM Kit_Request__c WHERE Due_Date__c < TODAY'
    FLIP = "SELECT Id, Status__c FROM Kit_Request__c WHERE Name = 'R-0001'"

    def org(self, overdue, status):
        self.set_state(answers={'COUNT()': {'total': overdue}, 'R-0001': {'records': [{'Id': 'a01', 'Status__c': status}]}})

    def prep_run(self, started, observed, extra=(), reuse=None):
        """One fresh, complete prep run: constructed checks, verdict, render, gate and publish."""
        self.clock = prep.now(started)
        claim, flip = reuse or (self.query(self.CLAIM), self.query(self.FLIP))
        obligations = [obligation('task.md#B1/claim1', 'passed' if claim['observed']['totalSize'] == 2 else 'failed', at=claim['at'],
                                  was='2 overdue', now=str(claim['observed']['totalSize']), fix='Rerun seed/kit.apex --refresh'),
                       obligation('task.md#FL1', 'passed' if flip['observed']['records'][0]['Status__c'] == 'New' else 'failed',
                                  kind='flip', proof=False, at=flip['at'], fix='Rerun seed/kit.apex --reset'), *extra]
        data = results(*obligations, started_at=started, observed_at=observed)
        self.clock = prep.now(observed)
        code, output, candidate = self.render(data)
        self.assertEqual(code, 0, output)
        self.assertEqual(self.gate(candidate, data)[0], 0)
        self.assertEqual(self.publish(candidate, data)[0], 0)
        return prep.verdict(data), (claim, flip)

    def test_no_or_silence_writes_nothing(self):
        for answer in ('no', 'silence'):
            with self.subTest(answer=answer):
                self.org(0, 'Escalated')
                outcome, _ = self.prep_run('2026-10-13T15:00:00+02:00', '2026-10-13T15:05:00+02:00')
                self.assertEqual(outcome['verdict'], 'not ready')
                before, calls = inventory(self.orgs), len(self.log())
                # No fix task runs; the next prep re-observes the same drift.
                outcome, _ = self.prep_run('2026-10-13T15:10:00+02:00', '2026-10-13T15:15:00+02:00')
                self.assertEqual(outcome['verdict'], 'not ready')
                self.assertEqual(self.mutations(), [])
                self.assertEqual(len(self.log()) - calls, 6)
                changed = {k for k, v in inventory(self.orgs).items() if before.get(k) != v}
                self.assertEqual({k for k in changed if not k.startswith('example/.scout-work')}, {'example/demo-path.md'})
                shutil.rmtree(str(self.folder))
                self.folder.mkdir()

    def test_yes_reruns_prep_in_full_and_never_reuses_an_old_observation(self):
        self.org(2, 'New')
        outcome, passing = self.prep_run('2026-10-13T15:00:00+02:00', '2026-10-13T15:05:00+02:00')
        self.assertEqual(outcome['verdict'], 'ready')
        self.org(0, 'Escalated')  # a rehearsal flipped the record and the dates aged out
        stale, _ = self.prep_run('2026-10-13T15:10:00+02:00', '2026-10-13T15:15:00+02:00', reuse=passing)
        self.assertEqual(stale['verdict'], 'not ready')  # N5 and F12: passes observed before this run don't count
        drifted, _ = self.prep_run('2026-10-13T15:20:00+02:00', '2026-10-13T15:25:00+02:00')
        self.assertEqual(drifted['verdict'], 'not ready')
        self.org(2, 'New')  # stands in for the approved /scout fix task
        fresh, _ = self.prep_run('2026-10-13T15:40:00+02:00', '2026-10-13T15:45:00+02:00')
        self.assertEqual(fresh['verdict'], 'ready')
        runs = self.regions(self.destination.read_text())['runs'].splitlines()[1:]
        self.assertEqual([line.split(' — ')[1] for line in runs], ['ready', 'not ready', 'not ready', 'ready'])
        self.assertEqual(self.mutations(), [])

    def test_yes_with_a_partial_failure_stays_not_ready(self):
        self.org(0, 'Escalated')
        self.prep_run('2026-10-13T15:00:00+02:00', '2026-10-13T15:05:00+02:00')
        self.org(0, 'New')  # the reset landed, the refresh did not
        outcome, _ = self.prep_run('2026-10-13T15:30:00+02:00', '2026-10-13T15:35:00+02:00')
        self.assertEqual(outcome['verdict'], 'not ready')
        drift = self.regions(self.destination.read_text())['drift']
        self.assertIn('task.md#B1/claim1', drift)
        self.assertNotIn('task.md#FL1', drift)
        self.assertEqual(self.mutations(), [])

    def test_yes_with_an_unsettled_job_stays_not_ready(self):
        self.org(2, 'New')
        for status in ('open', 'eye'):
            with self.subTest(status=status):
                job = obligation('task-fix.md#job1', status, kind='job', proof=False, text='Deploy job still running',
                                 at='2026-10-13T15:31:00+02:00')
                outcome, _ = self.prep_run('2026-10-13T15:30:00+02:00', '2026-10-13T15:35:00+02:00', extra=[job])
                self.assertEqual(outcome['verdict'], 'not ready')  # C03: a job is never 'check by eye'
        self.assertEqual(self.mutations(), [])

    def test_a_changed_binding_stops_the_fresh_prep(self):
        self.org(0, 'Escalated')
        _, old = self.prep_run('2026-10-13T15:00:00+02:00', '2026-10-13T15:05:00+02:00')
        self.set_state(org='00D000000000002EAA')
        code, output = self.run_prep('--kind', 'query', '--query', self.CLAIM)
        self.assertEqual(code, 3)
        self.assertIn('binding check failed', output)
        data = results(obligation(at='2026-10-13T15:00:00+02:00'), started_at='2026-10-13T15:00:00+02:00',
                       observed_at='2026-10-13T15:05:00+02:00')
        _, _, candidate = self.render(data)
        self.assertEqual(self.gate(candidate, data, org='00D000000000002EAA')[0], 3)
        self.assertEqual(self.mutations(), [])


class Round3Tests(FakeCli):
    """W9 round 3: the round-2 review findings R01–R12 and candidates R13, R14, R16 and R17, as ruled."""
    verdict = VerdictTests.verdict
    outcome = VerdictTests.outcome

    def test_r01_scratch_is_new_private_and_under_the_vetted_base(self):
        code, output = self.cli('scratch')
        self.assertEqual(code, 0, output)
        folder = Path(json.loads(output)['scratch'])
        self.assertEqual(folder.parent, Path(os.path.realpath(prep.SCRATCH_BASE)))
        self.assertTrue(folder.name.startswith('scout-prep-'))
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
        self.assertNotEqual(folder, Path(json.loads(self.cli('scratch')[1])['scratch']))

    def test_r03_a_later_demo_never_revives_an_expired_date(self):
        self.clock = prep.now('2026-10-14T00:30:00+02:00')
        run = dict(started_at='2026-10-14T00:10:00+02:00', observed_at='2026-10-14T00:25:00+02:00')
        expired = results(obligation(valid_until='2026-10-13', at='2026-10-14T00:20:00+02:00'), **run)
        for demo in (None, '2026-10-13T23:30:00-01:00', '2026-10-14T09:00:00+02:00'):
            with self.subTest(demo=demo):
                self.assertEqual(self.verdict(expired, demo)['verdict'], 'not ready')
        valid = results(obligation(valid_until='2026-10-14', at='2026-10-14T00:20:00+02:00'), **run)
        self.assertEqual(self.verdict(valid, '2026-10-14T09:00:00+02:00')['verdict'], 'ready')
        self.assertEqual(self.verdict(valid, '2026-10-15T09:00:00+02:00')['verdict'], 'not ready')

    def test_r04_a_manual_step_never_stands_in_for_the_proof_claim(self):
        manual = obligation('t.md#manual1', kind='manual', proof=True)
        self.assertEqual(self.verdict(results(manual))['blocking'], ['no proof-moment claim'])
        self.assertEqual(self.outcome(obligation(), manual), 'ready')

    def test_r06_a_failed_check_shows_its_time_in_the_path(self):
        code, output, candidate = self.render(results(obligation(), obligation('t.md#B1/c2', 'failed', proof=False)))
        self.assertEqual(code, 0, output)
        self.assertIn('- Check: ✗ Two overdue rows (t.md#B1/c2) — failed (%s)' % STAMP, self.regions(candidate.read_text())['path'])

    def test_r07_a_refused_check_still_names_its_time(self):
        code, output = self.run_prep('--kind', 'query', '--query', 'SELECT Id FROM Account; DELETE')
        self.assertEqual(code, 3, output)
        at = json.loads(output)['at']
        self.assertEqual(at, prep.now(NOW).isoformat(timespec='seconds'))
        self.assertEqual(self.verdict(results(obligation(), obligation('t.md#B1/c2', 'eye', proof=False, at=at)))['verdict'],
                         'ready with exceptions')

    def test_r08_a_failure_after_the_move_puts_the_file_back(self):
        data = results(obligation())
        original = self.published(data)
        _, _, candidate = self.render(data)
        real_read = prep.read_at

        def failing(directory, name):
            if name.startswith('demo-path.') and name != prep.NAME:
                raise PermissionError('concurrent ACL change')
            return real_read(directory, name)
        with patch.object(prep, 'read_at', failing):
            code, output = self.publish(candidate, data)
        self.assertEqual(code, 3, output)
        self.assertIn('is back at %s' % self.destination, output)
        self.assertEqual(self.destination.read_bytes(), original)
        self.assertEqual((self.backups(), self.staged()), ([], []))

    def test_r09_credentials_are_redacted_whole(self):
        message = ('INVALID_LOGIN password="first SECRETTAIL" secret: \'x y SECRET2\' '
                   'Authorization: Bearer abc+/BEARERTAIL== sid=00D000000000001!AQ4AQ.SECRET3')
        redacted = prep.cli_error({'name': 'INVALID_LOGIN', 'message': message})['message']
        for secret in ('SECRETTAIL', 'SECRET2', 'BEARERTAIL', 'SECRET3'):
            self.assertNotIn(secret, redacted)
        self.assertTrue(redacted.startswith('INVALID_LOGIN '))

    def test_r11_a_malformed_done_flag_is_unusable(self):
        for done in ('false', 0, None, 'true', 1):
            with self.subTest(done=done), self.assertRaises(prep.Refused):
                prep.query_observation({'records': [{'Id': 'a'}], 'totalSize': 1, 'done': done}, False)
        self.assertTrue(prep.query_observation({'records': [{'Id': 'a'}], 'totalSize': 1, 'done': True}, False)['complete'])
        self.assertTrue(prep.query_observation({'records': [{'Id': 'a'}], 'totalSize': 1}, False)['complete'])
        self.assertFalse(prep.query_observation({'records': [{'Id': 'a'}], 'totalSize': 2, 'done': False}, False)['complete'])

    def test_r12_an_unpaired_surrogate_is_a_schema_error(self):
        self.save(results(obligation(text='unpaired surrogate \ud800')))
        for command in (('verdict',), ('render', '--folder', self.folder)):
            with self.subTest(command=command[0]):
                code, output = self.cli(command[0], '--results', self.results, *command[1:])
                self.assertEqual(code, 3, output)
                self.assertIn('not valid Unicode', output)

    def test_r13_results_publish_only_into_the_folder_they_describe(self):
        code, output, _ = self.render(results(obligation(), folder=str(self.orgs / 'other')))
        self.assertEqual(code, 3, output)
        self.assertIn('collected for folder', output)
        good = results(obligation())
        code, output, candidate = self.render(good)
        self.assertEqual(code, 0, output)
        code, output = self.publish(candidate, dict(good, folder='orgs/other'))
        self.assertEqual(code, 3, output)
        self.assertFalse(self.destination.exists())
        for folder in ('example', str(self.folder)):
            with self.subTest(folder=folder):
                self.assertEqual(self.render(dict(good, folder=folder))[0], 0)

    def test_r14_a_retired_beat_neither_blocks_nor_renders(self):
        old = obligation('old.md#B1/c1', 'failed', beat='old.md#B1', superseded_by=KEY, supersession_source='old.md § Amendments')
        data = results(obligation(), old, beats=[beat('old.md#B1'), beat()], sources=[dict(path='old.md', state='read')])
        self.assertEqual(self.verdict(data)['verdict'], 'ready')
        code, output, candidate = self.render(data)
        self.assertEqual(code, 0, output)
        self.assertNotIn('old.md#B1', self.regions(candidate.read_text())['path'])


class Round4Tests(FakeCli):
    """W9 round 4: the round-3 review findings Q02, Q03, Q06, Q08–Q11 and candidates C01 and C02, as ruled. Q01, Q04, Q05 and Q07
    are crafted races outside the realistic threat model (Decisions, round 5)."""
    verdict = VerdictTests.verdict

    def berlin(self):
        """Q02's checks read this machine's zone; pin it, and restore it after."""
        saved = os.environ.get('TZ')
        os.environ['TZ'] = 'Europe/Berlin'
        time.tzset()

        def restore():
            if saved is None:
                os.environ.pop('TZ', None)
            else:
                os.environ['TZ'] = saved
            time.tzset()
        self.addCleanup(restore)

    def test_q02_a_daylight_saving_change_never_shifts_the_validity_day(self):
        self.berlin()
        self.clock = prep.now('2026-03-28T10:00:00+01:00')
        run = dict(started_at='2026-03-28T09:50:00+01:00', observed_at='2026-03-28T09:55:00+01:00')
        claim = lambda until: results(obligation(valid_until=until, at='2026-03-28T09:52:00+01:00'), **run)  # noqa: E731
        self.assertEqual(self.verdict(claim('2026-03-29'), '2026-03-30T00:30:00+02:00')['verdict'], 'not ready')  # spring forward
        self.assertEqual(self.verdict(claim('2026-03-30'), '2026-03-30T00:30:00+02:00')['verdict'], 'ready')
        self.clock = prep.now('2026-10-24T10:00:00+02:00')
        run = dict(started_at='2026-10-24T09:50:00+02:00', observed_at='2026-10-24T09:55:00+02:00')
        claim = lambda until: results(obligation(valid_until=until, at='2026-10-24T09:52:00+02:00'), **run)  # noqa: E731
        self.assertEqual(self.verdict(claim('2026-10-24'), '2026-10-25T23:30:00+01:00')['verdict'], 'not ready')  # fall back
        self.assertEqual(self.verdict(claim('2026-10-25'), '2026-10-25T23:30:00+01:00')['verdict'], 'ready')

    def test_q03_regions_from_different_renders_are_hand_assembled(self):
        good, bad = results(obligation()), results(obligation(), obligation('t.md#B1/c2', 'failed', proof=False))
        first, second = (self.render(data)[2].read_text() for data in (good, bad))
        one, two = prep.parse_regions(first), prep.parse_regions(second)
        mixed = first[:one['path']['start']] + second[two['path']['start']:two['path']['end']] + first[one['path']['end']:]
        self.destination.write_text(mixed)
        code, output, _ = self.render(good)
        self.assertEqual(code, 3, output)
        self.assertIn('hand-assembled', output)
        self.assertEqual(self.destination.read_text(), mixed)
        self.destination.write_text(first)  # a whole verbatim copy stays Scout's (R15)
        self.assertEqual(self.render(good)[0], 0)

    def test_q06_a_relative_folder_path_resolves_against_the_workspace(self):
        good = results(obligation())
        for folder in ('../../second-workspace/orgs/example', 'other/../../example', 'orgs/other'):
            with self.subTest(folder=folder):
                code, output, _ = self.render(dict(good, folder=folder))
                self.assertEqual(code, 3, output)
                self.assertIn('collected for folder', output)
        for folder in ('example', 'orgs/example', 'orgs/./example', str(self.folder)):
            with self.subTest(folder=folder):
                self.assertEqual(self.render(dict(good, folder=folder))[0], 0)

    def test_q09_offsets_out_of_range_are_not_iso(self):
        for at in ('2026-10-13T15:39:00+01:99', '2026-10-13T15:39:00+24:00', '2026-10-13T15:39:00+0199'):
            with self.subTest(at=at):
                self.assertIsNone(prep.parse_time(at))
                self.assertIn("needs its result's at", self.verdict(results(obligation(at=at)), code=3)['refused'])
        self.assertIsNotNone(prep.parse_time('2026-10-13T15:39:00+05:45'))

    def test_q10_a_failed_stage_leaves_nothing_behind(self):
        data = results(obligation())
        self.published(data)
        _, _, candidate = self.render(data)
        with patch.object(prep.os, 'fsync', side_effect=OSError(28, 'No space left on device')):
            code, output = self.publish(candidate, data)
        self.assertNotEqual(code, 0, output)
        self.assertEqual(self.staged(), [])
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ['.scout-work', 'demo-path.md'])

    def test_q11_the_destination_read_never_blocks_and_checks_the_descriptor(self):
        """F2 changed this pin: call read_nofollow itself on a FIFO. Without O_NONBLOCK it hangs past the timeout; without
        the descriptor check it returns empty bytes. Either way it fails."""
        fifo = self.root / 'fifo'
        os.mkfifo(str(fifo))
        probe = ('import sys; sys.path.insert(0, %r); import scout_prep as p\n'
                 'try:\n    p.read_nofollow(%r)\nexcept p.Refused as error:\n    print("REFUSED", error)\n') % (
                     str(Path(prep.__file__).parent), str(fifo))
        result = subprocess.run([sys.executable, '-S', '-B', '-c', probe], capture_output=True, text=True, timeout=10)
        self.assertIn('REFUSED', result.stdout, result.stderr)
        self.assertIn('not a regular file', result.stdout)

    def test_f1_a_dot_relative_folder_is_a_path(self):
        good = results(obligation())
        code, output, _ = self.render(dict(good, folder='./example'))
        self.assertEqual(code, 3, output)
        self.assertEqual(self.render(dict(good, folder='example'))[0], 0)

    def test_c1_unrelated_sources_are_listed_where_the_se_reads(self):
        data = results(obligation(), sources=[dict(path='old-customer-task.md', state='unrelated')])
        code, output, candidate = self.render(data)
        self.assertEqual(code, 0, output)
        self.assertIn('- Excluded as unrelated: old-customer-task.md', self.regions(candidate.read_text())['seams'])

    def test_c02_a_retired_beat_s_fallback_leaves_the_seams(self):
        old = obligation('old.md#B1/c1', 'failed', beat='old.md#B1', superseded_by=KEY, supersession_source='old.md § Amendments')
        retired = beat('old.md#B1', fallback='OLD RETIRED FALLBACK')
        data = results(obligation(), old, beats=[retired, beat()], sources=[dict(path='old.md', state='read')])
        code, output, candidate = self.render(data)
        self.assertEqual(code, 0, output)
        seams = self.regions(candidate.read_text())['seams']
        self.assertNotIn('OLD RETIRED FALLBACK', seams)
        self.assertIn('Show the saved screenshot', seams)


class BytecodeTests(unittest.TestCase):
    def test_the_helpers_write_no_bytecode_even_without_dash_b(self):
        with tempfile.TemporaryDirectory(prefix='scout-prep-pyc-') as temp:
            root = Path(temp)
            plugin = root / 'scripts'
            plugin.mkdir()
            for name in ('scout_target.py', 'scout_prep.py', 'scout_report_repair.py', 'scout_report_xml.py'):
                shutil.copyfile(str(SCRIPTS / name), str(plugin / name))
            env = {k: v for k, v in os.environ.items() if k not in ('PYTHONDONTWRITEBYTECODE', 'PYTHONPYCACHEPREFIX')}
            env.update(HOME=str(root), PYTHONPYCACHEPREFIX=str(root / 'cache'))
            for name in ('scout_target.py', 'scout_prep.py'):
                result = subprocess.run([sys.executable, '-S', str(plugin / name), '--help'], env=env, cwd=temp,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([str(p.relative_to(root)) for p in root.rglob('scout_*.pyc')], [])  # F22


if __name__ == '__main__':
    unittest.main()
