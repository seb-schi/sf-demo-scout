"""Scout 2.0.1: the fresh rc1 review's F2, F4 and F5, reproduced first, as W13's plan gate revised them."""
from datetime import datetime
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_scout_history as base
from test_scout_build import BULK, DEPLOY, DOCS, Harness, complex_story, cp, items, job

LATER = 'changes-2026-11-20-0900-example.md'  # round 3 (M1): past every job's retention; the window tests set their own


def later_log(folder, receipts, org=base.ORG, user=base.USER, header=None, newline='\n', body='', name=LATER):
    """A later task's change log in `folder`, holding only its reconciliation receipts."""
    folder.mkdir(parents=True, exist_ok=True)
    header = 'Org: %s (%s)\n' % (user, org) if header is None else header
    text = ('# Change Log — Example — later\n%sTask record: task-later-example.md\n\n%s'
            '## Reconciled Jobs\n%s\n## Checkpoints\n' % (header, body, ''.join('- reconciled: %s\n' % r for r in receipts)))
    (folder / name).write_bytes(text.replace('\n', newline).encode('utf-8'))


class ReconciliationTests(Harness):
    """F2 (R1–R3): a later task's receipt settles another task's job for good; anything else leaves it open."""

    def rows(self):
        return [(r.get('open_jobs'), r.get('reconciled_jobs'))  # with --username, as the route runs it
                for r in base.ScoutHistoryTests.pending_rows(self, base.USER) if r.get('file') == str(self.log)]

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
        """Round 3 (M2): with no time recorded, its log's modification time bounds the launch; edits only delay it."""
        self.save('### PENDING — component repair\n- Deploy %s submitted.\n' % DEPLOY)
        self.assertEqual(self.rows(), [([DEPLOY], None)])
        later_log(self.folder, ['job %s; status: not found; read-back: the field is absent' % DEPLOY])
        for written, settled in ((datetime(2026, 10, 1, 9, 0), True), (datetime(2026, 11, 1, 9, 0), False)):
            with self.subTest(written=written):
                os.utime(self.log, (written.timestamp(), written.timestamp()))
                self.assertEqual(self.rows(), [(None, [DEPLOY])] if settled else [([DEPLOY], None)])

    def test_not_found_counts_only_past_the_jobs_retention(self):
        """Round 3 (M1): 31 days after a deploy's launch, 8 after a Bulk job's, counted to the receipt log's own time."""
        for reference, name, settled in ((DEPLOY, 'changes-2026-10-14-0900-example.md', False),
                                         (DEPLOY, 'changes-2026-11-13-1100-example.md', False),
                                         (DEPLOY, 'changes-2026-11-13-1300-example.md', True),
                                         (BULK, 'changes-2026-10-21-1100-example.md', False),
                                         (BULK, 'changes-2026-10-21-1300-example.md', True),
                                         (DEPLOY, 'changes-later-example.md', False)):  # no time in the name
            with self.subTest(reference=reference, name=name):
                for old in self.folder.glob('changes-*-example.md'):
                    if old != self.log:
                        old.unlink()
                self.open_job(reference)
                later_log(self.folder, ['job %s; status: not found; read-back: absent' % reference], name=name)
                self.assertEqual(self.rows(), [(None, [reference])] if settled else [([reference], None)])

    def test_a_refreshed_sandboxs_old_job_is_certainly_not_found(self):
        """Round 3 (M2): the job's own log names another org ID, so the bound org can't have it, whatever its age."""
        self.open_job()
        self.log.write_text(self.log.read_text().replace('(%s)' % base.ORG, '(00D000000000002EAA)', 1))
        later_log(self.folder, ['job %s; status: not found; read-back: the field is absent' % DEPLOY],
                  name='changes-2026-10-14-0900-example.md')
        self.assertEqual(self.rows(), [(None, [DEPLOY])])

    def test_only_the_logs_own_header_names_the_org(self):
        """Round 2 (F2): mentions elsewhere, or a header naming another org, never admit a log's receipts."""
        receipt = ['job %s; status: not found; read-back: the field is absent' % DEPLOY]
        for header, body, settled in (
                ('Org: Demo (%s, 00D000000000002EAA)\n' % base.USER, '', False),  # same username, another org's ID
                ('Org: Other (other@example.test, 00D000000000002EAA)\n', '## Notes\nCopied from %s.\n\n' % base.ORG, False),
                ('', '## Notes\nOrg: %s (%s)\n\n' % (base.USER, base.ORG), False),  # a section's line is no header
                ('Org: Demo (%s)\n' % base.USER, '', True),  # the template's header names the username only
                ('Org: Demo (%s)\n' % base.ORG, '', True),
                ('Org: Demo (%s)\nOrg ID: 00D000000000002EAA\n' % base.USER, '', False),  # round 3 (R2-F1): a split header
                ('Org: Demo (%s)\nOrg ID: %s\n' % (base.USER, base.ORG), '', True)):
            with self.subTest(header=header, body=body):
                self.open_job()
                later_log(self.folder, receipt, header=header, body=body)
                self.assertEqual(self.rows(), [(None, [DEPLOY])] if settled else [([DEPLOY], None)])

    def test_a_submission_settles_only_by_its_own_familys_words(self):
        """Round 2 (F3): a label that names its family keeps that family's terminal words."""
        key = 'changes-2026-10-13-1200-example.md · attempt A1 · Email-to-Case apply script'
        for status, settled in (('Active', False), ('Completed', True)):
            with self.subTest(status=status):
                self.open_job('Email-to-Case apply script', 'Running')
                later_log(self.folder, ['%s; status: %s; read-back: enableEmailToCase true' % (key, status)])
                label = 'Email-to-Case apply script'
                self.assertEqual(self.rows(), [(None, [label])] if settled else [([label], None)])

    def test_the_key_is_exact_apart_from_spacing(self):
        """Round 2 (F4): the filename, attempt and label match exactly; only runs of spaces fold."""
        key = 'changes-2026-10-13-1200-example.md · attempt A1 · apply script'
        for name, settled in ((key, True), (key.replace(' · ', '  ·  '), True), (key.replace('A1', 'a1'), False),
                              (key.replace('apply script', 'Apply script'), False)):
            with self.subTest(name=name):
                self.open_job('apply script', 'Running')
                later_log(self.folder, ['%s; status: unavailable; read-back: enableEmailToCase true' % name])
                self.assertEqual(self.rows(), [(None, ['apply script'])] if settled else [(['apply script'], None)])

    def test_crlf_line_endings_keep_a_receipt(self):
        """Round 2 (F5)."""
        self.open_job()
        later_log(self.folder, ['job %s; status: not found; read-back: the field is absent' % DEPLOY], newline='\r\n')
        self.assertEqual(self.rows(), [(None, [DEPLOY])])

    def test_a_fenced_receipt_settles_nothing(self):
        """Round 2 (C2): a quoted or drafted receipt inside a fence isn't a status read."""
        self.open_job()
        later_log(self.folder, [], body='Draft, not yet read:\n```\n- reconciled: job %s; status: Succeeded\n```\n\n' % DEPLOY)
        self.assertEqual(self.rows(), [([DEPLOY], None)])

    def test_markup_on_a_receipt_is_stripped_as_on_job_lines(self):
        """Round 2 (N1): backticks and bold don't hide a receipt, and an asterisk bullet still counts."""
        for line in ('- reconciled: job `%s`; status: `not found`; read-back: `Region__c` absent' % DEPLOY,
                     '- reconciled: job **%s**; status: **Succeeded**' % DEPLOY,
                     '- **reconciled:** job %s; status: Succeeded' % DEPLOY,
                     '* reconciled: job %s; status: Succeeded' % DEPLOY):
            with self.subTest(line=line):
                self.open_job()
                later_log(self.folder, [], body='## Notes\nNone.\n\n')
                text = (self.folder / LATER).read_text().replace('## Reconciled Jobs\n', '## Reconciled Jobs\n' + line + '\n', 1)
                (self.folder / LATER).write_text(text)
                self.assertEqual(self.rows(), [(None, [DEPLOY])])

    def test_pending_prints_each_open_jobs_receipt_key(self):
        """Round 2 (N1): the exact name to copy, for a job ID, a submission, and an ID outside 0Af and 750."""
        rows = lambda: [r for r in base.ScoutHistoryTests.pending_rows(self, base.USER) if r.get('file') == str(self.log)]  # noqa: E731
        for reference, key in ((DEPLOY, 'job ' + DEPLOY),
                               ('apply script', 'changes-2026-10-13-1200-example.md · attempt A1 · apply script'),
                               ('707Ka00000AbCdE', 'changes-2026-10-13-1200-example.md · attempt A1 · 707Ka00000AbCdE')):
            with self.subTest(reference=reference):
                self.open_job(reference, 'Running')
                self.assertEqual([r.get('receipt_keys') for r in rows()], [[key]])
                later_log(self.folder, ['%s; status: unavailable; read-back: no rows' % key if not key.startswith('job ')
                                        else '%s; status: Succeeded' % key])
                self.assertEqual([(r.get('open_jobs'), r.get('reconciled_jobs')) for r in rows()], [(None, [reference])])
                (self.folder / LATER).unlink()

    def test_an_agent_publish_settles_only_by_its_versions_status(self):
        """Round 2 (N3) and round 3 (M3): a publish settles by its family's words, or, when no version of the agent
        exists, by `unavailable` with its read-back."""
        key = 'changes-2026-10-13-1200-example.md · attempt A1 · agent publish'
        for status, settled in (('unavailable; read-back: no BotVersion exists', True), ('unavailable', False),
                                ('Completed', False), ('JobComplete', False), ('Active', True), ('NeedsUICommit', True)):
            with self.subTest(status=status):
                self.open_job('agent publish', 'Publishing')
                later_log(self.folder, ['%s; status: %s' % (key, status)])
                self.assertEqual(self.rows(), [(None, ['agent publish'])] if settled else [(['agent publish'], None)])

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
                     '- job: %s; status: Succeeded (read-back pending); launched: 2026-10-13T12:00:00; settled: 2026-10-13T12:02:00\n' % DEPLOY):
            with self.subTest(body=body):
                self.unverified(body)
                self.assertIn('unsettled outcome/fields', self.run_cli('check')[1])

    def test_x5s_compound_line_on_a_settled_attempt(self):
        """Round 2 (N5): X5's shape, an applied attempt whose job settled. Only the lint decides it."""
        settled = job(DEPLOY, 'Succeeded', '2026-10-13T12:00:00', '2026-10-13T12:02:00')
        for word, passes in (('pending', False), ('`pending`', True)):
            with self.subTest(word=word):
                self.save(cp('A1', 'applied', settled + '- Verification: applied; job: %s; status: %s\n' % (DEPLOY, word)))
                code, output = self.run_cli('check')
                self.assertEqual(code == 0, passes, output)


class HonestRecordTests(Harness):
    """F5: two records the route asks for, which `check` must accept."""

    def retry(self, entry):
        """Round 2 (F6): the whole session is degraded, so the design entry is degraded too, and each attempt has its
        own deploy."""
        complex_story(self.data)
        design = dict(assumption='Field metadata', source='ungrounded', ref='', verdict='Docs unavailable: search failed')
        self.data['items'][0].update(attempts=['A1', 'A2'], grounding=[design, dict(entry, attempt='A2')])
        self.save(cp('A1', 'failed', job(DEPLOY, 'Failed', '2026-10-13T12:00:00', '2026-10-13T12:02:00')) +
                  cp('A2', 'applied', job('0AfKa00000jEyAAKAS', 'Succeeded', '2026-10-13T12:05:00', '2026-10-13T12:07:00'),
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
