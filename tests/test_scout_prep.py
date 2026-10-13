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
import subprocess
import sys
import tempfile
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

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = prep.main([str(a) for a in args])
        return code, output.getvalue()

    def save(self, data):
        self.results.write_text(json.dumps(data))

    def render(self, data, demo_time=None):
        self.save(data)
        self.renders += 1
        candidate = self.scratch / ('candidate-%d.md' % self.renders)
        extra = ['--demo-time', demo_time] if demo_time else []
        code, output = self.cli('render', '--results', self.results, '--folder', self.folder, '--out', candidate, *extra)
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
            (results(obligation(), obligation('t.md#old', 'failed', proof=False, superseded_by=KEY, supersession_source=source)), 'ready'),
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

    def test_supersession_needs_another_live_obligation_and_its_source(self):
        source = 'task-2026-10-14-0900-y.md § Amendments'
        old = lambda **extra: obligation('t.md#I2', 'failed', kind='item', proof=False, **extra)  # noqa: E731
        self.assertEqual(self.outcome(obligation(), old(superseded_by=KEY, supersession_source=source)), 'ready')
        for extra in (dict(superseded_by='missing-task.md#missing', supersession_source=source),
                      dict(superseded_by='t.md#I2', supersession_source=source), dict(superseded_by=KEY),
                      dict(superseded_by=KEY, supersession_source=' '), dict(superseded_by='t.md#I3', supersession_source=source)):
            with self.subTest(extra=extra):
                retired = obligation('t.md#I3', 'passed', kind='item', proof=False, superseded_by=KEY, supersession_source=source)
                self.assertEqual(self.outcome(obligation(), retired, old(**extra)), 'not ready')
        for successor in (True, {'anything': 'goes'}, ['t.md#I3']):
            with self.subTest(successor=successor):
                data = results(obligation(), old(superseded_by=successor, supersession_source=source))
                self.assertEqual(prep.verdict(data, prep.now(NOW))['verdict'], 'not ready')
                self.verdict(data, code=3)

    def test_a_deliberately_dropped_optional_obligation_is_history(self):
        source = 'task-2026-10-13-1200-x.md § story.beats[0].claims'
        dropped = lambda **extra: obligation('t.md#B1/c9', 'failed', proof=False, dropped=True, **extra)  # noqa: E731
        self.assertEqual(self.outcome(obligation(), dropped(required=False, drop_source=source)), 'ready')
        self.assertEqual(self.outcome(obligation(), dropped(required=True, drop_source=source)), 'not ready')
        self.assertEqual(self.outcome(obligation(), dropped(required=False)), 'not ready')

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
        for at in ('not-a-time', '2026-10-13T15:00:00', '2000-01-01T00:00:00+00:00', '2026-10-13T14:00:00+02:00',
                   '2026-10-13T17:00:00+02:00', None, '20261013T150000+0200'):
            with self.subTest(at=at):
                self.assertEqual(self.outcome(obligation(at=at)), 'not ready')  # F12
        self.assertEqual(self.outcome(obligation(), obligation('t.md#B1/eye', 'eye', proof=False, at=None)), 'not ready')
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
                for args in (('verdict',), ('render', '--folder', self.folder, '--out', self.scratch / ('c%d.md' % number)),
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
        self.assertIn('- ✗ Status shows Overdue (%s) — was: Overdue since 2026-10-12; now: New; fix: Run seed/kit-requests.apex with --reset'
                      % failed['key'], drift)  # F16
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
                code, output = self.cli('render', '--results', self.results, '--folder', folder, '--out', self.scratch / (folder.name + '.md'))
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

    def test_out_is_a_new_file_outside_every_customer_folder(self):
        task = self.folder / 'task-owned.md'
        task.write_text('ORIGINAL TASK EVIDENCE\n')
        self.save(results(obligation()))
        linked = self.scratch / 'into-folder'
        linked.symlink_to(self.folder, target_is_directory=True)
        link = self.scratch / 'link.md'
        link.symlink_to(task)
        for out in (task, self.orgs / 'other' / 'new-candidate.md', self.folder / 'new.md', self.orgs / 'stray.md', linked / 'x.md', link):
            with self.subTest(out=out):
                code, output = self.cli('render', '--results', self.results, '--folder', self.folder, '--out', out)
                self.assertEqual(code, 3, output)  # F04
        self.assertEqual(task.read_text(), 'ORIGINAL TASK EVIDENCE\n')
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ['task-owned.md'])
        self.assertEqual(sorted(p.name for p in self.orgs.iterdir()), ['example', 'other'])
        fresh = self.scratch / 'fresh.md'
        self.assertEqual(self.cli('render', '--results', self.results, '--folder', self.folder, '--out', fresh)[0], 0)
        before = fresh.read_bytes()
        self.assertEqual(self.cli('render', '--results', self.results, '--folder', self.folder, '--out', fresh)[0], 3)
        self.assertEqual(fresh.read_bytes(), before)


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
        self.assertIn('does not match the results', self.gate(candidate, data)[1])
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
            if Path(source) == self.destination:
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
            if Path(source) == self.destination:
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
            if Path(destination) == self.destination:
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
    """F23 and X15: a fix is a separate /scout task; prep never writes, and after a fix it runs again in full."""
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
