"""Report repair contracts checked against captured CLI schemas and fixed paths."""
import copy
import contextlib
import io
from datetime import datetime, timedelta, timezone
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
        if self.mode == 'no-job':
            receipt.write_text('{"status":1,"name":"NetworkError"}')
            raise repair.RepairError('launch response unavailable')
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

    def test_r12_f1_writer_ignores_inline_boundary_data(self):
        task, sha = self.inspect()
        contract = repair.json_read(task / 'contract.json')
        state = repair.json_read(task / 'result.json')
        marker, closer = repair.checkpoint_marker(task), f'<!-- /scout-repair:{task.name} -->'
        contract['delta']['after'] = marker + ' and ' + closer
        self.engine.checkpoint(task, contract, state)
        log = Path(state['log'])
        first = log.read_text()
        self.engine.checkpoint(task, contract, state)
        self.assertEqual(log.read_text(), first)
        # An inline example isn't a replaceable checkpoint, even with both tokens.
        log.write_text('Example: ' + marker + ' ' + closer + '\n')
        with self.assertRaisesRegex(repair.RepairError, 'checkpoint missing'):
            self.engine.checkpoint(task, contract, state)
        self.assertEqual(log.read_text(), 'Example: ' + marker + ' ' + closer + '\n')

    def test_r11_inspect_cli_names_exact_marker_and_recording_requirement(self):
        args = ['scout-repair.py', 'inspect-report', '--workspace-root', str(self.workspace),
                '--customer-dir', str(self.customer), '--target-org', 'example', '--report', MEMBER,
                '--column', DELTA['column'], '--operator', DELTA['operator'], '--before', DELTA['before'],
                '--after', DELTA['after'], '--request-file', str(self.request), '--request-reference', 'R1']
        for missing, expected in ((None, 0), ('report', 1)):
            self.adapter.missing = missing
            with self.subTest(missing=missing):
                output = io.StringIO()
                with patch.object(sys, 'argv', args), patch.object(repair, 'Salesforce', return_value=self.adapter), contextlib.redirect_stdout(output):
                    self.assertEqual(repair.main(), expected)
                result = json.loads(output.getvalue())
                marker = '<!-- scout-repair:' + Path(result['task']).name + ' -->'
                self.assertEqual(result.get('checkpoint_marker'), marker)
                self.assertIn(marker, Path(result['log']).read_text())
                requirement = '\n'.join(result.get('requirements', []))
                for value in (marker, 'task record', 'before apply-report'):
                    self.assertIn(value, requirement)
                self.assertEqual(self.count('deploy'), 0)

    def test_r11_writer_keeps_own_pending_placeholders_plain(self):
        task, _ = self.inspect()
        log = repair.json_read(task / 'result.json')['log']
        text = Path(log).read_text()
        self.assertIn('acceptance=pending;', text)
        self.assertIn('; pending\n', text)
        contract = repair.json_read(task / 'contract.json')
        del contract['baseline']
        state = repair.json_read(task / 'result.json')
        self.engine.checkpoint(task, contract, state)
        self.assertIn('unknown; pending\n', Path(log).read_text())

    def test_r11_writer_data_spans_survive_backticks_and_newlines(self):
        from scout_history import status_fields
        task, _ = self.inspect()
        contract = repair.json_read(task / 'contract.json')
        state = repair.json_read(task / 'result.json')
        for value in ('pending`path', 'pending``path\nnext line', '`pending`\r\npath'):
            with self.subTest(value=value):
                contract.update(member='Pending/Pending', baseline={'source': value})
                contract['target']['username'] = 'pending@example.test'
                state.update(mutation='not_attempted', acceptance='failed', recovery='verified',
                             original={'artifact': value}, readback={'source': value}, job_id=value, error=value)
                self.engine.checkpoint(task, contract, state)
                receipt = Path(state['log']).read_text()
                self.assertEqual(list(status_fields(receipt, receipt_ids={task.name})), [])
                self.assertIn(repair.code_span(value), receipt)
                self.assertNotIn('\nnext line', receipt)

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

    def release_proof(self):
        proof = self.customer / 'release-review.md'
        proof.write_text('Operator reviewed deployment history after launch and the current report read-back.')
        return str(proof)

    def age_launch(self, task, seconds=600):
        launch = repair.json_read(task / 'launch.json')
        launch['started_at'] = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
        repair.save(task / 'launch.json', launch)

    def snapshot(self):
        return {str(p.relative_to(self.workspace)): (p.read_bytes(), p.stat().st_mode & 0o7777,
                                                          p.stat().st_ino, p.stat().st_mtime_ns)
                for p in self.workspace.rglob('*') if p.is_file()}

    def test_operator_release_retains_uncertainty_and_allows_one_new_deploy(self):
        for mode in ('no-job', 'normalized'):
            with self.subTest(mode=mode):
                self.adapter.source = BEFORE
                task, sha = self.inspect()
                self.adapter.mode = 'no-job' if mode == 'no-job' else 'success'
                if mode == 'no-job':
                    with self.assertRaises(repair.RepairError):
                        self.engine.apply(task, sha)
                else:
                    self.engine.apply(task, sha)
                    self.adapter.source = GOLD.replace(b' untouched ', b'normalized')
                unverified = self.engine.reconcile(task, sha)
                self.assertEqual(unverified['outcome'], 'unverified')
                before_deploys = self.count('deploy')
                self.age_launch(task)
                proof = self.release_proof()
                result = self.engine.reconcile(task, sha, release_evidence=proof)
                self.assertEqual(result['outcome'], 'released_unverified')
                resolution = repair.json_read(task / 'resolution.json')
                for key in ('mutation', 'acceptance', 'job_id'):
                    self.assertEqual(resolution[key], unverified[key])
                self.assertEqual(resolution['readback'], result['readback'])
                self.assertEqual((task / 'release-evidence.md').read_bytes(), Path(proof).read_bytes())
                self.assertIn('### unverified — released by operator', Path(result['log']).read_text())
                self.assertIn(str(task / 'release-evidence.md'), Path(result['log']).read_text())
                self.assertEqual(self.count('deploy'), before_deploys)
                before = self.snapshot()
                self.adapter.trace.clear()
                with self.assertRaisesRegex(repair.RepairError, r'resolved \(released_unverified\); start a new task'):
                    self.engine.verify(task, sha)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.adapter.trace, [])
                # Propose a fresh delta from the observed normalized value.
                self.adapter.mode = 'success'
                delta = dict(DELTA, before='Prospecting' if mode == 'no-job' else 'Qualification', after='Negotiation')
                second = self.engine.inspect(str(self.workspace), str(self.customer), 'maple-demo', MEMBER,
                                             delta, self.request, 'follow-up instruction', previous_task=task)
                second_sha = repair.json_read(second / 'result.json')['digest']
                self.engine.apply(second, second_sha)
                self.assertEqual(self.engine.verify(second, second_sha)['outcome'], 'applied')
                self.assertEqual(self.count('deploy'), 1)

    def test_release_requests_on_other_outcomes_and_terminal_rechecks_write_nothing(self):
        proof = self.release_proof()
        for kind in ('ready', 'applied', 'not_applied', 'already_satisfied'):
            with self.subTest(kind=kind):
                self.adapter.source = GOLD if kind == 'already_satisfied' else BEFORE
                self.adapter.mode = 'failed' if kind == 'not_applied' else 'success'
                self.adapter.status = fixture('synthetic-report-success')['result']
                task, sha = self.inspect()
                if kind != 'ready':
                    result = self.engine.apply(task, sha)
                    if kind != 'already_satisfied':
                        result = self.engine.verify(task, sha)
                    self.assertEqual(result['outcome'], kind)
                    self.assertTrue((task / 'resolution.json').exists())
                self.adapter.source = BEFORE.replace(b'100', b'777')  # later UI drift
                self.adapter.trace.clear()
                before = self.snapshot()
                if kind == 'ready':
                    result = self.engine.reconcile(task, sha, release_evidence=proof)
                    self.assertEqual((result['outcome'], result['action']), ('ready', 'nothing to release'))
                else:
                    for method, kwargs in ((self.engine.verify, {}), (self.engine.reconcile, {}),
                                           (self.engine.reconcile, {'release_evidence': proof})):
                        with self.assertRaisesRegex(repair.RepairError, 'resolved .*start a new task'):
                            method(task, sha, **kwargs)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.adapter.trace, [])

    def test_release_reconciles_normally_before_deciding_and_validates_immutable_evidence(self):
        task, sha = self.inspect(); self.engine.apply(task, sha)
        # Fresh successful receipt wins; invalid release evidence is not consumed.
        result = self.engine.reconcile(task, sha, release_evidence='/missing')
        self.assertEqual((result['outcome'], result['action']), ('applied', 'nothing to release'))
        self.assertFalse((task / 'release-evidence.md').exists())
        self.adapter.source = BEFORE
        task, sha = self.inspect(); self.adapter.mode = 'no-job'
        with self.assertRaises(repair.RepairError): self.engine.apply(task, sha)
        self.age_launch(task)
        proof = Path(self.release_proof())
        empty = self.customer / 'empty.md'; empty.write_text(' \n')
        large = self.customer / 'large.md'; large.write_bytes(b'x' * (repair.LIMIT + 1))
        link = self.customer / 'link.md'; link.symlink_to(proof)
        for invalid in (empty, large, link, self.customer, Path('relative.md')):
            with self.subTest(path=invalid), self.assertRaises(repair.RepairError):
                self.engine.reconcile(task, sha, release_evidence=str(invalid))
            self.assertFalse((task / 'resolution.json').exists())
            self.assertFalse((task / 'release-evidence.md').exists())
        # Simulate evidence copied before an interrupted checkpoint.
        (task / 'release-evidence.md').write_text('earlier evidence')
        with self.assertRaisesRegex(repair.RepairError, 'release evidence changed'):
            self.engine.reconcile(task, sha, release_evidence=str(proof))
        self.assertEqual((task / 'release-evidence.md').read_text(), 'earlier evidence')
        self.assertFalse((task / 'resolution.json').exists())
        proof.write_text('earlier evidence')
        self.assertEqual(self.engine.reconcile(task, sha, release_evidence=str(proof))['outcome'], 'released_unverified')

    def test_checkpoint_preserves_existing_change_log_mode(self):
        log = self.customer / 'changes-2026-10-12-0900-maple.md'
        log.write_text('# Existing log\n'); log.chmod(0o644)
        task, sha = self.inspect()
        self.assertEqual(log.stat().st_mode & 0o777, 0o644)
        self.engine.apply(task, sha); self.engine.verify(task, sha)
        self.assertEqual(log.stat().st_mode & 0o777, 0o644)
        self.assertEqual((task / 'result.json').stat().st_mode & 0o777, 0o600)

    def test_failed_release_finalization_stays_pending_and_retries_same_evidence(self):
        task, sha = self.inspect(); self.adapter.mode = 'no-job'
        with self.assertRaises(repair.RepairError): self.engine.apply(task, sha)
        self.age_launch(task)
        proof = self.release_proof()
        with patch.object(self.engine, 'resolve', side_effect=OSError('injected resolution failure')):
            with self.assertRaises(OSError):
                self.engine.reconcile(task, sha, release_evidence=proof)
        result = repair.json_read(task / 'result.json')
        self.assertEqual(result['outcome'], 'unverified')
        self.assertIn('PENDING — component repair', Path(result['log']).read_text())
        self.assertFalse((task / 'resolution.json').exists())
        second, second_sha = self.inspect()
        with self.assertRaisesRegex(repair.RepairError, 'unresolved write'):
            self.engine.apply(second, second_sha)
        self.assertEqual(self.engine.reconcile(task, sha, release_evidence=proof)['outcome'], 'released_unverified')
        self.assertEqual(self.count('deploy'), 1)

    def test_host_interruption_between_release_checkpoint_and_resolution_is_recoverable(self):
        task, sha = self.inspect(); self.adapter.mode = 'no-job'
        with self.assertRaises(repair.RepairError): self.engine.apply(task, sha)
        self.age_launch(task)
        proof = self.release_proof()
        with patch.object(self.engine, 'resolve', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.engine.reconcile(task, sha, release_evidence=proof)
        self.assertFalse((task / 'resolution.json').exists())
        second, second_sha = self.inspect()
        with self.assertRaisesRegex(repair.RepairError, 'unresolved write'):
            self.engine.apply(second, second_sha)
        result = self.engine.reconcile(task, sha, release_evidence=proof)
        self.assertEqual(result['outcome'], 'released_unverified')
        self.assertTrue((task / 'resolution.json').exists())
        self.assertEqual(self.count('deploy'), 1)

    def test_release_refuses_nonterminal_known_job_and_blocks_new_attempt(self):
        task, sha = self.inspect()
        self.engine.apply(task, sha)
        self.age_launch(task, 3600)
        proof = self.release_proof()
        for done in (False, None, 'true', 1):
            self.adapter.status = fixture('synthetic-report-queued')['result']
            self.adapter.status['done'] = done
            with self.assertRaisesRegex(repair.RepairError, 'until done is true'):
                self.engine.reconcile(task, sha, release_evidence=proof)
            self.assertFalse((task / 'resolution.json').exists())
            self.assertFalse((task / 'release-evidence.md').exists())
        second, second_sha = self.inspect()
        with self.assertRaisesRegex(repair.RepairError, 'unresolved write'):
            self.engine.apply(second, second_sha)
        self.assertEqual(self.count('deploy'), 1)
        self.adapter.status = fixture('synthetic-report-success')['result']
        self.assertEqual(self.engine.reconcile(task, sha, release_evidence=proof)['outcome'], 'applied')

    def test_no_job_release_waits_ten_minutes_and_rejects_future_launch(self):
        task, sha = self.inspect()
        self.adapter.mode = 'no-job'
        with self.assertRaises(repair.RepairError):
            self.engine.apply(task, sha)
        proof = self.release_proof()
        for age in (0, 599, -3600):
            now = datetime.now(timezone.utc)
            self.age_launch(task, age)
            with patch.object(repair, 'datetime', wraps=datetime) as frozen:
                frozen.now.return_value = now
                with self.assertRaisesRegex(repair.RepairError, 'until 10 minutes'):
                    self.engine.reconcile(task, sha, release_evidence=proof)
            self.assertFalse((task / 'resolution.json').exists())
            self.assertFalse((task / 'release-evidence.md').exists())
        second, second_sha = self.inspect()
        with self.assertRaisesRegex(repair.RepairError, 'unresolved write'):
            self.engine.apply(second, second_sha)
        self.age_launch(task, 600)
        self.assertEqual(self.engine.reconcile(task, sha, release_evidence=proof)['outcome'], 'released_unverified')
        self.assertEqual(self.count('deploy'), 1)

    def test_launch_intent_and_keyboard_interrupt_windows_reconcile_from_disk(self):
        for window in ('before-result', 'during-deploy'):
            with self.subTest(window=window):
                task, sha = self.inspect()
                save = repair.save
                def interrupt_result(file, value, **kwargs):
                    if file == task / 'result.json' and (task / 'launch.json').exists():
                        raise KeyboardInterrupt()
                    return save(file, value, **kwargs)
                context = (patch.object(repair, 'save', side_effect=interrupt_result)
                           if window == 'before-result' else
                           patch.object(self.adapter, 'deploy', side_effect=KeyboardInterrupt))
                with context, self.assertRaises(KeyboardInterrupt):
                    self.engine.apply(task, sha)
                self.assertEqual(repair.json_read(task / 'result.json')['outcome'], 'ready')
                if window == 'before-result':
                    self.assertEqual(repair.json_read(task / 'result.json')['mutation'], 'not_attempted')
                    result = self.engine.reconcile(task, sha)
                    self.assertEqual((result['outcome'], result['mutation']), ('unverified', 'attempted_unknown'))
                self.age_launch(task)
                result = self.engine.reconcile(task, sha, release_evidence=self.release_proof())
                self.assertEqual(result['outcome'], 'released_unverified')
                self.assertTrue((task / 'resolution.json').exists())
                self.assertEqual(self.count('deploy'), 0)

    def test_terminal_cli_refusals_report_recorded_outcome_without_writes(self):
        for kind in ('applied', 'not_applied', 'already_satisfied'):
            self.adapter.source = GOLD if kind == 'already_satisfied' else BEFORE
            self.adapter.mode = 'failed' if kind == 'not_applied' else 'success'
            self.adapter.status = fixture('synthetic-report-success')['result']
            task, sha = self.inspect()
            self.engine.apply(task, sha)
            if kind != 'already_satisfied':
                self.engine.verify(task, sha)
            before = self.snapshot()
            self.adapter.trace.clear()
            output = io.StringIO()
            args = ['scout-repair.py', 'verify-report', '--task-dir', str(task), '--contract-digest', sha]
            with patch.object(sys, 'argv', args), patch.object(repair, 'Salesforce', return_value=self.adapter), contextlib.redirect_stdout(output):
                code = repair.main()
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output.getvalue())['outcome'], kind)
            self.assertEqual(self.snapshot(), before)
            self.assertEqual(self.adapter.trace, [])
            log = Path(repair.json_read(task / 'result.json')['log']).read_text()
            self.assertNotIn('verify or reconcile before replay', log)
            self.assertIn('resolved; start a new task', log)

    def test_read_rejects_leaf_swaps_and_bounds_growth_on_one_descriptor(self):
        file = self.customer / 'race.md'
        secret = self.customer / 'unread.md'
        secret.write_bytes(b'unread data')
        original_open = os.open
        for kind in ('symlink', 'fifo'):
            file.write_bytes(b'original')
            def swapped(name, flags, *args, **kwargs):
                self.assertTrue(flags & os.O_NOFOLLOW)
                self.assertTrue(flags & os.O_NONBLOCK)
                file.unlink()
                file.symlink_to(secret) if kind == 'symlink' else os.mkfifo(file)
                return original_open(name, flags, *args, **kwargs)
            with patch.object(repair.os, 'open', side_effect=swapped):
                with self.assertRaises((OSError, repair.RepairError)):
                    repair.read(file)
            file.unlink()
        file.write_bytes(b'x')
        original_stat, original_read = os.fstat, os.read
        sizes = []
        def grown(fd):
            result = original_stat(fd)
            with file.open('ab') as output:
                output.write(b'x' * (repair.LIMIT + 100))
            return result
        def bounded(fd, amount):
            data = original_read(fd, amount)
            sizes.append(len(data))
            return data
        with patch.object(repair.os, 'fstat', side_effect=grown), patch.object(repair.os, 'read', side_effect=bounded):
            with self.assertRaisesRegex(repair.RepairError, 'bounded regular'):
                repair.read(file)
        self.assertEqual(sum(sizes), repair.LIMIT + 1)

    def test_exclusive_evidence_publication_cannot_leave_empty_destination(self):
        destination = self.customer / 'release-evidence.md'
        content = b'Complete operator evidence\n'
        def interrupt(source, target):
            self.assertEqual(Path(source).read_bytes(), content)
            self.assertFalse(Path(target).exists())
            raise KeyboardInterrupt()
        with patch.object(repair.os, 'link', side_effect=interrupt), self.assertRaises(KeyboardInterrupt):
            repair.write(destination, content, exclusive=True)
        self.assertFalse(destination.exists())
        self.assertEqual(list(self.customer.glob('.repair-*')), [])
        repair.write(destination, content, exclusive=True)
        with self.assertRaises(FileExistsError):
            repair.write(destination, b'changed', exclusive=True)
        self.assertEqual(destination.read_bytes(), content)
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)

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
        self.assertNotIn("{'org_id':", text)
        self.assertNotIn("{'after':", text)
        self.assertIn(' → ', text)
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

    def test_cli_operator_release_and_terminal_refusal(self):
        call, args, state_file = self.cli_fixture('no-job')
        process, state = call(*args)
        self.assertEqual(process.returncode, 0)
        selectors = ['--task-dir', state['task'], '--contract-digest', state['digest']]
        process, state = call('apply-report', *selectors)
        self.assertEqual(process.returncode, 1)
        self.age_launch(Path(state['task']))
        process, state = call('reconcile-report', *selectors, '--release-evidence', self.release_proof())
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(state['outcome'], 'released_unverified')
        before = self.snapshot()
        process, state = call('verify-report', *selectors)
        self.assertEqual(process.returncode, 1)
        self.assertIn('resolved (released_unverified); start a new task', state['error'])
        self.assertEqual(state['outcome'], 'released_unverified')
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(sum(c[:3] == ['project', 'deploy', 'start']
                             for c in json.loads(state_file.read_text())['calls']), 1)


if __name__ == '__main__':
    unittest.main()
