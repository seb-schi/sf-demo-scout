"""Scout 2.0.1: the fresh rc1 review's F2, F4 and F5, reproduced first, as W13's plan gate revised them."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_scout_history as base
from test_scout_build import BULK, DEPLOY, DOCS, Harness, complex_story, cp, items, job

LATER = 'changes-2026-10-14-0900-example.md'


def later_log(folder, receipts, org=base.ORG, user=base.USER):
    """A later task's change log in `folder`, holding only its reconciliation receipts."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / LATER).write_text('# Change Log — Example — 2026-10-14 0900\nOrg: %s (%s)\nTask record: task-2026-10-14-0900-example.md\n\n'
                                '## Reconciled Jobs\n%s\n## Checkpoints\n' % (user, org, ''.join('- reconciled: %s\n' % r for r in receipts)))


class ReconciliationTests(Harness):
    """F2 (R1–R3): a later task's receipt settles another task's job for good; anything else leaves it open."""

    def rows(self):
        return [(r.get('open_jobs'), r.get('reconciled_jobs'))
                for r in base.ScoutHistoryTests.pending_rows(self) if r.get('file') == str(self.log)]

    def open_job(self, reference=DEPLOY, status='InProgress'):
        self.data['items'][0].update(disposition='unverified', reason='Timed out; never terminal')
        self.save(cp('A1', 'unverified', job(reference, status, '2026-10-13T12:00:00')))

    def test_without_a_receipt_the_job_stays_open(self):
        self.open_job()
        later_log(self.folder, [])
        self.assertEqual(self.rows(), [([DEPLOY], None)])

    def test_a_terminal_word_or_not_found_with_its_read_back_settles_it(self):
        for receipt in ('job %s; status: Succeeded' % DEPLOY, 'job %s; status: Failed' % DEPLOY,
                        'job %s; status: FinalizingDeployFailed' % DEPLOY,
                        'job %s; status: not found; read-back: Account.Region__c is absent' % DEPLOY,
                        'job %s; status: Succeeded' % DEPLOY[:15]):
            with self.subTest(receipt=receipt):
                self.open_job()
                later_log(self.folder, [receipt])
                self.assertEqual(self.rows(), [(None, [DEPLOY])])

    def test_anything_else_settles_nothing(self):
        for receipt in ('job %s; status: not found' % DEPLOY, 'job %s; status: not found; read-back:' % DEPLOY,
                        'job %s; status: InProgress' % DEPLOY, 'job %s; status: `Pending`' % DEPLOY,
                        'job %s; status: InvalidDeployIdError' % DEPLOY, 'job %s; status: unavailable; read-back: absent' % DEPLOY,
                        'job 0AfKa00000iDxYYKAS; status: Succeeded', '%s; status: Succeeded' % DEPLOY, 'job %s' % DEPLOY):
            with self.subTest(receipt=receipt):
                self.open_job()
                later_log(self.folder, [receipt])
                self.assertEqual(self.rows(), [([DEPLOY], None)])

    def test_a_receipt_counts_across_folders_of_the_bound_org_only(self):
        self.open_job()
        later_log(self.root / 'orgs' / 'example-two', ['job %s; status: Succeeded' % DEPLOY])
        self.assertEqual(self.rows(), [(None, [DEPLOY])])
        (self.root / 'orgs' / 'example-two' / LATER).unlink()
        later_log(self.root / 'orgs' / 'other-org', ['job %s; status: Succeeded' % DEPLOY],
                  org='00D000000000002EAA', user='other@example.test')
        self.assertEqual(self.rows(), [([DEPLOY], None)])

    def test_a_bulk_job_settles_by_its_own_words(self):
        for receipt, settled in (('job %s; status: JobComplete' % BULK, True), ('job %s; status: Succeeded' % BULK, False),
                                 ('job %s; status: not found; read-back: 12 rows present' % BULK, True)):
            with self.subTest(receipt=receipt):
                self.open_job(BULK)
                later_log(self.folder, [receipt])
                self.assertEqual(self.rows(), [(None, [BULK])] if settled else [([BULK], None)])

    def test_a_submission_without_an_id_settles_by_log_attempt_and_label(self):
        key = 'changes-2026-10-13-1200-example.md · attempt A1 · apply script'
        for receipt, settled in (('%s; status: unavailable; read-back: enableEmailToCase true' % key, True),
                                 ('%s; status: Completed' % key, True),
                                 ('%s; status: unavailable' % key, False),
                                 ('%s; status: not found; read-back: absent' % key, False),
                                 ('%s; status: unavailable; read-back: true' % key.replace('A1', 'A2'), False),
                                 ('%s; status: unavailable; read-back: true' % key.replace('apply script', 'publish'), False)):
            with self.subTest(receipt=receipt):
                self.open_job('apply script', 'Running')
                later_log(self.folder, [receipt])
                self.assertEqual(self.rows(), [(None, ['apply script'])] if settled else [(['apply script'], None)])

    def test_a_legacy_checkpoints_job_settles_by_its_id(self):
        self.save('### PENDING — component repair\n- Deploy %s submitted.\n' % DEPLOY)
        self.assertEqual(self.rows(), [([DEPLOY], None)])
        later_log(self.folder, ['job %s; status: not found; read-back: the field is absent' % DEPLOY])
        self.assertEqual(self.rows(), [(None, [DEPLOY])])

    def test_check_accepts_a_log_carrying_the_section(self):
        self.save()
        self.log.write_text(self.log.read_text().replace(
            '## Checkpoints\n', '## Reconciled Jobs\n- reconciled: job %s; status: Succeeded\n\n## Checkpoints\n' % DEPLOY, 1))
        self.passes()


class StatusWordTests(Harness):
    """F4: Salesforce's DeployStatus words, per the Metadata API's DeployResult; W3's lint is unchanged (X5)."""

    def unverified(self, body):
        self.data['items'][0].update(disposition='unverified', reason='Timed out while queued')
        self.save(cp('A1', 'unverified', body))

    def test_finalizing_deploy_failed_settles_a_failed_deploy(self):
        self.data['items'][0].update(disposition='failed', reason='State left: unchanged; rollback: not needed')
        self.save(cp('A1', 'failed', job(DEPLOY, 'FinalizingDeployFailed', '2026-10-13T12:00:00', '2026-10-13T12:04:00')))
        self.passes()

    def test_a_queued_deploy_records_pending_in_backticks(self):
        self.unverified(job(DEPLOY, '`Pending`', '2026-10-13T12:00:00'))
        self.passes()

    def test_pending_outside_backticks_is_still_a_finding(self):
        for body in (job(DEPLOY, 'Pending', '2026-10-13T12:00:00'),
                     job(DEPLOY, '`Pending`', '2026-10-13T12:00:00') + '- Verification: applied; job: %s; status: pending\n' % DEPLOY,
                     '- job: %s; status: Succeeded (read-back pending); launched: 2026-10-13T12:00:00; settled: 2026-10-13T12:02:00\n' % DEPLOY):
            with self.subTest(body=body):
                self.unverified(body)
                self.assertIn('unsettled outcome/fields', self.run_cli('check')[1])


class HonestRecordTests(Harness):
    """F5: two records the route asks for, which `check` must accept."""

    def retry(self, entry):
        complex_story(self.data)
        self.data['items'][0].update(attempts=['A1', 'A2'], grounding=[DOCS, dict(entry, attempt='A2')])
        self.save(cp('A1', 'failed', job(DEPLOY, 'Failed', '2026-10-13T12:00:00', '2026-10-13T12:02:00')) +
                  cp('A2', 'applied', job(DEPLOY[:-3] + 'AAA', 'Succeeded', '2026-10-13T12:05:00', '2026-10-13T12:07:00'),
                     at='2026-10-13 12:05'))
        return self.run_cli('check')

    def test_a_retry_with_docs_unavailable_all_session(self):
        entry = dict(assumption='The error is transient', source='ungrounded', ref='', verdict='Docs unavailable: search failed')
        code, output = self.retry(entry)
        self.assertEqual(code, 0, output)
        self.assertIn('warning: I1: Docs unavailable', output)
        code, output = self.retry(dict(entry, verdict='Seemed transient'))
        self.assertIn('without a grounding entry', output)  # an ungrounded guess is no stand-in

    def test_a_companion_set_drops_the_failed_item_it_no_longer_grants(self):
        self.data['items'] = items(('I1', 'applied', ()), ('I2', 'failed', ()), ('I3', 'applied', ('I1',)))
        self.data['items'][2].update(type='PermissionSet', what='Companion set', components=['PermissionSet:Demo_Companion'])
        self.save()
        code, output = self.run_cli('check')
        self.assertEqual(code, 0, output)
        self.data['items'][2]['depends_on'] = ['I1', 'I2']
        self.save()
        self.assertIn('I3 depends on unresolved I2', self.run_cli('check')[1])


if __name__ == '__main__':
    unittest.main()
