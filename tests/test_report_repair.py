"""Report repair contracts checked against captured CLI schemas and fixed paths."""
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import scout_report_repair as repair

FIXTURES = Path(__file__).parent / 'fixtures/report-repair'
MEMBER = 'Sales_Reports/Pipeline'
REPORT = 'reports/Sales_Reports/Pipeline.report-meta.xml'
FOLDER_PATH = 'reports/Sales_Reports.reportFolder-meta.xml'  # SDR source format, not helper-derived
BEFORE = b'''<?xml version="1.0" encoding="UTF-8"?>
<!-- retain document comment -->
<Report xmlns="http://soap.sforce.com/2006/04/metadata">
 <name>Pipeline</name><format>Summary</format>
 <filter><booleanFilter>1 AND 2</booleanFilter>
 <criteriaItems><column>STAGE_NAME</column><operator>equals</operator><value>Prospecting</value></criteriaItems>
 <criteriaItems><column>AMOUNT</column><operator>greaterThan</operator><value>100</value></criteriaItems>
 </filter><groupingsDown><field>OWNER</field></groupingsDown>
 <!-- retain me --><futureFeature mode="custom"> untouched </futureFeature>
</Report>'''
GOLD = BEFORE.replace(b'<value>Prospecting</value>', b'<value>Qualification</value>')
FOLDER = b'<ReportFolder xmlns="http://soap.sforce.com/2006/04/metadata"><name>Sales</name><folderShares><accessLevel>View</accessLevel><sharedTo>Sales</sharedTo><sharedToType>Group</sharedToType></folderShares></ReportFolder>'
TARGET = {'org_id': '00D000000000001EAA', 'username': 'maple@example.test'}
DELTA = {'column': 'STAGE_NAME', 'operator': 'equals', 'before': 'Prospecting', 'after': 'Qualification'}


def fixture(name):
    return json.loads((FIXTURES / (name + '.json')).read_text())


class FakeSalesforce:
    def __init__(self):
        self.source, self.folder = BEFORE, FOLDER
        self.target = dict(TARGET)
        self.trace = []
        self.mode = 'success'
        self.identity_unavailable = False
        self.missing = None
        self.status = fixture('synthetic-report-success')['result']

    def identity(self, selector, cwd):
        self.check_identity(self.target, cwd)
        return dict(self.target)

    def check_identity(self, target, cwd):
        self.trace.append(('identity', target['username']))
        if self.identity_unavailable or target != self.target:
            raise repair.RepairError('identity unavailable or rebound')

    def retrieve(self, target, member, project):
        self.trace.append(('retrieve', target, member))
        root = project / 'force-app/main/default'
        (root / REPORT).parent.mkdir(parents=True, exist_ok=True)
        if self.missing != 'report':
            (root / REPORT).write_bytes(self.source)
        if self.missing != 'folder':
            (root / FOLDER_PATH).write_bytes(self.folder)

    def deploy(self, target, member, project, receipt):
        self.trace.append(('deploy', target, member))
        root = project / 'force-app/main/default'
        assert [p.relative_to(root).as_posix() for p in root.rglob('*.xml')] == [REPORT]
        if self.mode == 'preflight':
            receipt.write_text(json.dumps(fixture('synthetic-deploy-error')))
            raise repair.RepairError('SourceConflictError')
        if self.mode != 'failed':
            self.source = (root / REPORT).read_bytes()
        if self.mode == 'lost':
            receipt.write_text('{"status":0,')
            raise TimeoutError('launch response lost')
        receipt.write_text(json.dumps(fixture('synthetic-deploy-start')))
        if self.mode == 'failed':
            self.status = fixture('synthetic-report-failed')['result']
        if self.mode == 'checkpoint-crash':
            raise TimeoutError('valid stdout saved; caller interrupted')
        return self.status['id']

    def report(self, target, job, project):
        self.trace.append(('report', target, job))
        return copy.deepcopy(self.status)


class ReportRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='scout2-report-test-')
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve()
        self.customer = self.workspace / 'orgs/maple-demo-maple'
        self.customer.mkdir(parents=True)
        (self.workspace / 'sfdx-project.json').write_text(json.dumps({
            'packageDirectories': [{'path': 'force-app', 'default': True}], 'sourceApiVersion': '66.0'}))
        self.request = self.customer / 'repair-request.md'
        self.request.write_text('Change Sales_Reports/Pipeline STAGE_NAME equals Prospecting to Qualification. Preserve the rest.')
        self.adapter = FakeSalesforce()
        self.engine = repair.Repair(self.adapter)

    def inspect(self, **kwargs):
        task = self.engine.inspect(str(self.workspace), str(self.customer), 'maple-demo', MEMBER,
                                   dict(DELTA), self.request, 'user request R1', **kwargs)
        return task, repair.json_read(task / 'result.json')['digest']

    def count(self, operation):
        return sum(row[0] == operation for row in self.adapter.trace)

    def test_exact_byte_delta_and_explicit_identity_with_fixed_source_paths(self):
        task, sha = self.inspect()
        self.adapter.trace.clear()
        result = self.engine.apply(task, sha)
        self.assertEqual(result['mutation'], 'job_recorded')
        self.assertEqual(self.count('retrieve'), 1)
        self.assertEqual(len(self.adapter.trace), 4)  # two queries, retrieve, deploy
        result = self.engine.verify(task, sha)
        self.assertEqual((result['outcome'], result['mutation'], result['acceptance'], result['recovery']),
                         ('applied', 'succeeded', 'passed', 'verified'))
        self.assertEqual(self.adapter.source, GOLD)
        self.assertEqual(self.adapter.folder, FOLDER)
        self.assertTrue(all(row[1] == TARGET['username'] for row in self.adapter.trace))
        pin = repair.json_read(task / 'original.json')
        self.assertEqual((Path(pin['artifact']) / 'source' / REPORT).read_bytes(), BEFORE)
        self.assertEqual(self.count('deploy'), 1)

    def test_identity_unavailable_or_rebound_prevents_write(self):
        for unavailable in (True, False):
            self.adapter.identity_unavailable = False
            self.adapter.target = dict(TARGET)
            task, sha = self.inspect()
            self.adapter.identity_unavailable = unavailable
            if not unavailable:
                self.adapter.target['org_id'] = '00D000000000002EAA'
            with self.assertRaises(repair.RepairError):
                self.engine.apply(task, sha)
        self.assertEqual(self.count('deploy'), 0)

    def test_absent_report_or_folder_finalizes_blocked_with_paths(self):
        for missing in ('report', 'folder'):
            self.adapter.missing = missing
            with self.assertRaises(FileNotFoundError):
                self.inspect()
            state = repair.json_read(self.engine.task / 'result.json')
            self.assertEqual(state['outcome'], 'blocked')
            self.assertIn(REPORT if missing == 'report' else FOLDER_PATH, state['error'])
            self.assertNotIn('PENDING — component repair', Path(state['log']).read_text())
        self.assertEqual(self.count('deploy'), 0)

    def test_unknown_alias_creates_no_task_or_pending_log(self):
        self.adapter.identity_unavailable = True
        with self.assertRaises(repair.RepairError):
            self.inspect()
        self.assertFalse((self.customer / '.scout-tasks').exists())
        self.assertEqual(list(self.customer.glob('changes-*')), [])

    def test_stale_report_or_folder_blocks_before_write(self):
        for kind in ('report', 'folder'):
            self.adapter.source, self.adapter.folder = BEFORE, FOLDER
            task, sha = self.inspect()
            if kind == 'report': self.adapter.source = BEFORE.replace(b'100', b'200')
            else: self.adapter.folder = FOLDER.replace(b'View', b'Manage')
            with self.assertRaises(repair.RepairError): self.engine.apply(task, sha)
        self.assertEqual(self.count('deploy'), 0)

    def test_defaults_change_does_not_invalidate_correct_repair(self):
        task, sha = self.inspect()
        self.engine.apply(task, sha)
        with patch.dict(os.environ, {'SF_TARGET_ORG': 'unrelated-user-change'}):
            self.assertEqual(self.engine.verify(task, sha)['outcome'], 'applied')
        self.assertEqual(self.count('deploy'), 1)

    def test_failed_deploy_reconciles_unchanged_and_releases_other_username(self):
        task, sha = self.inspect()
        self.adapter.mode = 'failed'
        self.engine.apply(task, sha)
        second, second_sha = self.inspect()
        with self.assertRaisesRegex(repair.RepairError, 'unresolved write'):
            self.engine.apply(second, second_sha)
        result = self.engine.reconcile(task, sha)
        self.assertEqual((result['outcome'], result['mutation']), ('not_applied', 'not_applied'))
        self.adapter.target['username'] = 'second@example.test'
        third, third_sha = self.inspect()
        self.adapter.mode = 'success'
        self.engine.apply(third, third_sha)
        self.assertEqual(self.count('deploy'), 2)

    def test_preflight_error_needs_recorded_reconciliation_then_releases(self):
        task, sha = self.inspect()
        self.adapter.mode = 'preflight'
        with self.assertRaises(repair.RepairError): self.engine.apply(task, sha)
        result = self.engine.reconcile(task, sha)
        self.assertEqual(result['outcome'], 'not_applied')
        self.assertTrue((task / 'resolution.json').exists())
        self.assertEqual(self.adapter.source, BEFORE)

    def test_unknown_launch_never_replays_or_accepts_matching_state(self):
        task, sha = self.inspect()
        self.adapter.mode = 'lost'
        with self.assertRaises(TimeoutError): self.engine.apply(task, sha)
        self.assertEqual(self.adapter.source, GOLD)
        self.assertEqual(self.engine.reconcile(task, sha)['outcome'], 'unverified')
        with self.assertRaises(repair.RepairError): self.engine.apply(task, sha)
        second, second_sha = self.inspect()
        # A hand-edited outcome does not invent a recorded resolution.
        state = repair.json_read(task / 'result.json');state['outcome'] = 'applied';repair.save(task / 'result.json', state)
        with self.assertRaisesRegex(repair.RepairError, 'unresolved write'):
            self.engine.apply(second, second_sha)
        self.assertEqual(self.count('deploy'), 1)

    def test_saved_stdout_recovers_job_after_caller_interruption(self):
        task, sha = self.inspect()
        self.adapter.mode = 'checkpoint-crash'
        with self.assertRaises(TimeoutError): self.engine.apply(task, sha)
        self.assertIsNone(repair.json_read(task / 'result.json')['job_id'])
        self.assertEqual(self.engine.reconcile(task, sha)['outcome'], 'applied')
        self.assertEqual(self.count('deploy'), 1)

    def test_operator_attribution_is_recorded_and_old_job_is_rejected(self):
        task, sha = self.inspect()
        self.adapter.mode = 'lost'
        with self.assertRaises(TimeoutError): self.engine.apply(task, sha)
        proof = self.customer / 'job-evidence.md';proof.write_text('Operator matched job to this attempt using deployment history, exact member and start time.')
        self.adapter.status['createdDate'] = '2020-01-01T00:00:00Z'
        with self.assertRaisesRegex(repair.RepairError, 'predates'):
            self.engine.reconcile(task, sha, self.adapter.status['id'], str(proof))
        self.assertIsNone(repair.json_read(task / 'result.json')['job_id'])
        self.adapter.status['createdDate'] = datetime.now(timezone.utc).isoformat()
        result = self.engine.reconcile(task, sha, self.adapter.status['id'], str(proof))
        self.assertEqual(result['outcome'], 'applied')
        self.assertIn('operator-provided', result['job_attribution'])

    def test_nonterminal_job_and_normalization_or_external_drift_stay_unverified(self):
        task, sha = self.inspect();self.engine.apply(task, sha)
        self.adapter.status = fixture('synthetic-report-queued')['result']
        self.assertEqual(self.engine.verify(task, sha)['outcome'], 'unverified')
        self.adapter.status = fixture('synthetic-report-success')['result']
        self.adapter.source = GOLD.replace(b' untouched ', b'normalized')
        result = self.engine.verify(task, sha)
        self.assertEqual((result['outcome'], result['mutation']), ('unverified', 'succeeded'))

    def test_recovery_failure_is_separate_from_accepted_mutation(self):
        task, sha = self.inspect();self.engine.apply(task, sha)
        (task / 'original.json').unlink()
        result = self.engine.verify(task, sha)
        self.assertEqual((result['outcome'], result['recovery']), ('applied', 'blocked'))
        self.assertFalse((task / 'original.json').exists())

    def test_extra_member_or_false_receipt_never_passes(self):
        task, sha = self.inspect();self.engine.apply(task, sha)
        self.adapter.status['details']['componentSuccesses'].append({'componentType':'ReportFolder','fullName':'Sales_Reports'})
        self.assertEqual(self.engine.verify(task, sha)['outcome'], 'unverified')

    def test_unavailable_identity_on_verify_retains_unknown_acceptance(self):
        task, sha = self.inspect();self.engine.apply(task, sha)
        self.adapter.identity_unavailable = True
        with self.assertRaises(repair.RepairError): self.engine.verify(task, sha)
        self.assertEqual(repair.json_read(task / 'result.json')['acceptance'], 'unverified')

    def test_moved_log_before_attempt_causes_no_launch_or_permanent_guard(self):
        task, sha = self.inspect()
        log = Path(repair.json_read(task / 'result.json')['log'])
        log.rename(log.with_suffix('.archived'))
        with self.assertRaises(FileNotFoundError): self.engine.apply(task, sha)
        state = repair.json_read(task / 'result.json')
        self.assertEqual(state['mutation'], 'not_attempted')
        self.assertFalse((task / 'launch.json').exists())
        self.assertEqual(self.count('deploy'), 0)
        # A new task can proceed after recording the failed attempt in a new log.
        second, second_sha = self.inspect()
        self.engine.apply(second, second_sha)
        self.assertEqual(self.count('deploy'), 1)

    def test_existing_legacy_log_has_one_updated_checkpoint_with_required_fields(self):
        log = self.customer / 'changes-2026-10-08-0900-maple.md'
        prefix = '# Prior history\nUser-authored text must survive.\n';log.write_text(prefix)
        task, sha = self.inspect()
        self.engine.apply(task, sha)
        self.assertIn('PENDING — component repair', log.read_text())
        self.engine.verify(task, sha)
        text = log.read_text()
        self.assertTrue(text.startswith(prefix))
        self.assertNotIn('PENDING — component repair', text)
        self.assertEqual(text.count('<!-- scout-repair:'), 1)
        for field in ('Attempt / org / exact component', 'Classification / source', 'Requested delta / exclusions',
                      'First pre-edit artifact / source / members', 'Outcome / read-back', 'Receipts / remaining action', 'Rollback'):
            self.assertIn(field, text)
        self.assertIn('/source/' + REPORT, text)
        self.assertEqual(list(self.customer.glob('changes-*.md')), [log])

    def test_noop_and_later_linked_task_need_no_amendment_engine(self):
        self.adapter.source = GOLD
        task, sha = self.inspect()
        self.assertEqual(self.engine.apply(task, sha)['outcome'], 'already_satisfied')
        self.assertFalse((task / 'original.json').exists())
        second, second_sha = self.inspect(previous_task=task)
        self.assertEqual(self.engine.apply(second, second_sha)['outcome'], 'already_satisfied')
        self.assertEqual(repair.json_read(second / 'contract.json')['previous_task'], str(task))
        self.assertEqual(self.count('deploy'), 0)

    def test_source_or_request_tamper_and_symlink_are_rejected(self):
        task, sha = self.inspect()
        (task / 'request.md').write_text('changed')
        with self.assertRaises(repair.RepairError): self.engine.apply(task, sha)
        link = self.workspace / 'request-link';link.symlink_to(self.request)
        with self.assertRaises(repair.RepairError): repair.read(link)
        self.assertEqual(self.count('deploy'), 0)

    def test_snapshot_failure_prevents_write(self):
        task, sha = self.inspect()
        original = repair.assets
        def reject(operation, **kwargs):
            if operation == 'preserve': raise repair.RepairError('injected snapshot error')
            return original(operation, **kwargs)
        with patch.object(repair, 'assets', side_effect=reject):
            with self.assertRaises(repair.RepairError): self.engine.apply(task, sha)
        self.assertEqual(self.count('deploy'), 0)

    def test_xml_byte_preservation_escaping_empty_values_and_prohibited_constructs(self):
        result, _ = repair.candidate(BEFORE, dict(DELTA, after='A&B <C>'))
        self.assertEqual(result, BEFORE.replace(b'Prospecting', b'A&amp;B &lt;C&gt;'))
        empty = BEFORE.replace(b'<value>Prospecting</value>', b'<value/>')
        result, _ = repair.candidate(empty, dict(DELTA, before=''))
        self.assertEqual(result, GOLD)
        bad = [BEFORE.replace(b'<filter>', b'<filter/><filter>'),
               BEFORE.replace(b'</Report>', b'<block/></Report>'),
               b'<!DOCTYPE Report [<!ENTITY e SYSTEM "file:///etc/passwd">]>' + BEFORE.split(b'?>',1)[1],
               BEFORE.replace(b'</Report>', b'<?bad x?></Report>')]
        for content in bad:
            with self.assertRaises(repair.RepairError): repair.candidate(content, DELTA)

    def test_comment_loss_is_not_a_metadata_mismatch(self):
        task, sha = self.inspect();self.engine.apply(task, sha)
        self.adapter.source = GOLD.replace(b'<!-- retain document comment -->', b'').replace(b'<!-- retain me -->', b'')
        self.assertEqual(self.engine.verify(task, sha)['outcome'], 'applied')

    def test_scalar_whitespace_is_data_not_formatting(self):
        empty = BEFORE.replace(b'<value>Prospecting</value>', b'<value/>')
        space = BEFORE.replace(b'<value>Prospecting</value>', b'<value> </value>')
        self.assertNotEqual(repair.signature(repair.xml(empty, 'Report')),
                            repair.signature(repair.xml(space, 'Report')))

    def test_live_fixture_schema_and_cache_org_override_guard(self):
        adapter = object.__new__(repair.Salesforce)
        observed = fixture('live-deploy-report-success')['result']
        self.assertEqual(observed['numberComponentsTotal'], 8)
        self.assertEqual(len(observed['details']['componentSuccesses']), 9)
        with patch.object(repair.Path, 'home', return_value=self.workspace):
            with patch.object(adapter, 'run', return_value=observed):
                self.assertEqual(adapter.report(TARGET['username'], observed['id'], self.workspace)['numberComponentsTotal'], 8)
            cache = self.workspace / '.sf/deploy-cache.json';cache.parent.mkdir()
            cache.write_text(json.dumps({observed['id']:{'target-org':'another-user'}}))
            with patch.object(adapter, 'run') as run:
                with self.assertRaisesRegex(repair.RepairError, 'cache overrides'):
                    adapter.report(TARGET['username'], observed['id'], self.workspace)
                run.assert_not_called()
            cache.write_text('[]')
            with self.assertRaisesRegex(repair.RepairError, 'malformed deployment cache'):
                adapter.report(TARGET['username'], observed['id'], self.workspace)

    def test_status_requires_neither_cli_nor_external_python_package(self):
        task, _ = self.inspect()
        command = [sys.executable, '-S', '-B', str(repair.ASSETS.with_name('scout-repair.py')),
                   '--sf-executable', '/missing', 'status', '--task-dir', str(task)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['outcome'], 'ready')

    def cli_fixture(self, mode='success'):
        state = self.workspace / 'fake-sf.json'
        state.write_text(json.dumps({'report': BEFORE.decode(), 'folder': FOLDER.decode(), 'mode': mode}))
        binary = self.workspace / 'bin';binary.mkdir()
        sf = binary / 'sf'
        sf.write_text('#!' + sys.executable + '\n' + (FIXTURES / 'sf_fixture.py').read_text())
        sf.chmod(0o700)
        env = dict(os.environ, PATH=str(binary), PYTHONDONTWRITEBYTECODE='1',
                   SCOUT_REPORT_TEST_STATE=str(state), SCOUT_REPORT_TEST_FIXTURES=str(FIXTURES.resolve()),
                   SCOUT_REPORT_SCRIPTS=str(repair.ASSETS.parent))
        def call(*args):
            result = subprocess.run([sys.executable, '-S', '-B', str(FIXTURES / 'cli_harness.py'), *args],
                                    capture_output=True, text=True, env=env)
            return result, json.loads(result.stdout)
        args = ['inspect-report', '--workspace-root', str(self.workspace), '--customer-dir', str(self.customer),
                '--target-org', 'maple-demo', '--report', MEMBER, '--column', 'STAGE_NAME', '--operator', 'equals',
                '--before', 'Prospecting', '--after', 'Qualification', '--request-file', str(self.request),
                '--request-reference', 'test instruction R1']
        return call, args, state

    def test_cli_end_to_end_uses_fixed_paths_real_envelopes_and_private_receipt(self):
        call, args, state_file = self.cli_fixture()
        process, state = call(*args)
        self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
        selectors = ['--task-dir', state['task'], '--contract-digest', state['digest']]
        process, state = call('apply-report', *selectors)
        self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
        self.assertEqual(state['mutation'], 'job_recorded')
        receipt = Path(state['task']) / 'deploy-start.json'
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
        process, state = call('verify-report', *selectors)
        self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
        self.assertEqual(state['outcome'], 'applied')
        self.assertEqual(json.loads(state_file.read_text())['report'].encode(), GOLD)
        for file in Path(state['task']).glob('*.json'):
            self.assertNotIn('SYNTHETIC-SECRET', file.read_text())

    def test_cli_error_json_records_missing_folder_task_and_log(self):
        call, args, _ = self.cli_fixture('missing-folder')
        process, state = call(*args)
        self.assertEqual(process.returncode, 1)
        self.assertEqual(state['outcome'], 'blocked')
        self.assertTrue(Path(state['task']).is_dir())
        self.assertTrue(Path(state['log']).is_file())
        self.assertIn(FOLDER_PATH, state['error'])
        self.assertNotIn('Traceback', process.stderr)

    def test_cli_deploy_error_envelope_reconciles_without_second_launch(self):
        call, args, state_file = self.cli_fixture('preflight')
        process, state = call(*args)
        self.assertEqual(process.returncode, 0, process.stdout)
        selectors = ['--task-dir', state['task'], '--contract-digest', state['digest']]
        process, state = call('apply-report', *selectors)
        self.assertEqual(process.returncode, 1)
        self.assertEqual(state['mutation'], 'attempted_unknown')
        process, state = call('reconcile-report', *selectors)
        self.assertEqual(process.returncode, 0, process.stdout)
        self.assertEqual(state['outcome'], 'not_applied')
        calls = json.loads(state_file.read_text())['calls']
        self.assertEqual(sum(c[:3] == ['project', 'deploy', 'start'] for c in calls), 1)

    def test_cli_guard_error_is_blocked_even_when_saved_task_is_ready(self):
        call, args, _ = self.cli_fixture()
        _, first = call(*args)
        first_selectors = ['--task-dir', first['task'], '--contract-digest', first['digest']]
        process, _ = call('apply-report', *first_selectors)
        self.assertEqual(process.returncode, 0)
        _, second = call(*args)
        process, result = call('apply-report', '--task-dir', second['task'], '--contract-digest', second['digest'])
        self.assertEqual(process.returncode, 1)
        self.assertEqual(result['outcome'], 'blocked')
        self.assertEqual(result['saved_outcome'], 'ready')
        self.assertIn('unresolved write', result['error'])


if __name__ == '__main__':
    unittest.main()
