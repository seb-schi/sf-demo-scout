"""Offline history contracts, including synthetic long-lived demo folders."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import scout_history as history

ORG = '00D000000000001EAA'
USER = 'demo@example.test'


SECTIONS = ('Verified — Applied This Build', 'Verified — Already Satisfied Before This Build',
            'Accounted-for Exceptions', 'Unresolved Work')
LOG_SECTIONS = ('Achieved State', 'What Was Deployed', 'What Was Skipped', 'Completion Reconciliation',
                'Companion Permission Set', 'Issues Encountered', 'Docs Consulted',
                'SE Must Do Next (in order)', 'How to Verify', 'Open Questions for Next Session')
ARCH_SECTIONS = ('Customer Context & Value Spine', 'Demo Flow / Narrative Arc',
                 'Pointers (not duplicated here)', 'Decision Log')


def expected_render(data):
    # Independent specification oracle, deliberately not the implementation's constants or render.
    groups = [[], [], [], []]
    skipped = []
    mapping = {'applied': (0, 'applied'), 'already_satisfied': (1, 'already_satisfied'),
               'omitted': (2, 'SKIPPED'), 'failed': (3, 'FAILED'), 'blocked': (3, 'BLOCKED')}
    for value in data['items']:
        group, label = (2, 'AWAITING_QA') if value['visual_qa'] else mapping.get(value['disposition'], (3, 'INCOMPLETE (unverified)'))
        line = '- %s — %s — %s' % (value['id'], label, ' '.join((value['evidence'] + ' ' + value['reason']).split()))
        groups[group].append(line)
        if value['disposition'] == 'omitted': skipped.append(line)
    status = 'UNRESOLVED' if groups[3] else 'FINISHED_WITH_EXCEPTIONS' if groups[2] else 'FULLY_VERIFIED'
    counts = [sum(any(e['source'] == source for e in i['grounding']) for i in data['items'])
              for source in ('docs', 'skill', 'org', 'ungrounded')]
    lines = ['Grounding: %d items; docs %d; skill %d; org %d; ungrounded %d' % (len(data['items']), *counts),
             '', '## What Was Skipped', *(skipped or ['None.']), '', '## Completion Reconciliation', 'Overall: ' + status]
    for name, rows in zip(SECTIONS, groups): lines += ['', '### ' + name, *(rows or ['None.'])]
    return '\n'.join(lines) + '\n'


def item(identifier='I1', disposition='applied'):
    return dict(id=identifier, what='Add label', type='CustomField', beat='-', category='autonomous',
                criterion='Label matches', readback='sf sobject describe --target-org demo@example.test',
                proves='KP3', depends_on=[], components=['CustomField:Example__c.Label__c'], attempts=['A' + identifier[1:]] if disposition in ('applied', 'failed', 'unverified') else [],
                grounding=[dict(assumption='Field XML', source='skill', ref='field skill', verdict='authorable')],
                disposition=disposition, evidence='Describe confirms label', visual_qa=False,
                reason='State left: unchanged; rollback: not needed' if disposition == 'failed' else '', seed_asset='')


def record():
    return dict(schema=1, path='complete-brief', change_log='changes-2026-10-13-1200-example.md',
                story=None, items=[item()], history=dict(decisions='none', proposed_entries=[],
                lessons='none', architecture='unchanged'))


def checkpoint(attempt='A1', outcome='applied', heading='PENDING'):
    body = f'### {heading} — component repair · attempt {attempt} · 2026-10-13 12:00\n- outcome: pending\n'
    if outcome:
        body += f'- **Outcome: {outcome}.** read-back receipt\n'
    return body


class ScoutHistoryTests(unittest.TestCase):
    def record_report_marker(self, name='example'):
        from scout_report_repair import checkpoint_marker
        self.task.write_text(self.task.read_text() + '\n' + checkpoint_marker(Path(name)) + '\n')

    def test_r11_f1_real_writer_quotes_pending_report_folder_and_paths(self):
        from scout_report_repair import Repair
        for member, slug in (('Example/Pending', 'example'), ('Pending/Report', 'example'),
                             ('Example/Report', 'pending-example')):
            with self.subTest(member=member, slug=slug):
                self.folder = self.folder.parent / slug
                self.folder.mkdir(exist_ok=True)
                self.task = self.folder / self.task.name
                self.log = self.folder / self.data['change_log']
                repair_task = self.folder / '.scout-tasks' / 'repair-example'
                repair_task.mkdir(parents=True, exist_ok=True)
                receipt_log = self.folder / 'receipt.txt'
                receipt_log.write_text('')
                contract = dict(target=dict(username='pending@example.test', org_id=ORG), member=member,
                                baseline='pending/source.json', delta=dict(column='STATUS', operator='equals',
                                before='Pending', after='Closed'))
                state = dict(log=str(receipt_log), mutation='succeeded', acceptance='passed', recovery='verified',
                             original=dict(artifact=str(self.folder / 'pending-artifact')),
                             readback=str(repair_task / 'pending-readback.json'), job_id='pending-job')
                Repair(None).checkpoint(repair_task, contract, state, first=True)
                receipt = receipt_log.read_text()
                self.save(checkpoint() + '```text\n' + receipt + '```\n')
                self.task.write_text(self.task.read_text() + '\n<!-- scout-repair:repair-example -->\n')
                self.run_cli('resolve')
                self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])
                self.assertIn(receipt, self.log.read_text())

    def test_r11_f2_unrecorded_marker_names_exact_line_and_task_fix(self):
        marker = '<!-- scout-repair:repair-example -->'
        receipt = '```text\n' + marker + '\n- **Outcome / read-back:** applied\n<!-- /scout-repair:repair-example -->\n```\n'
        for record in ('', 'Report marker: repair-example', 'Report marker: `repair-example`', marker, '`'+marker+'`'):
            with self.subTest(record=record):
                self.save(checkpoint() + receipt)
                self.task.write_text(self.task.read_text() + '\n' + record + '\n')
                self.run_cli('resolve')
                code, output = self.run_cli()
                if marker in record:
                    self.assertEqual(code, 0, output)
                else:
                    self.assertEqual(code, 3, output)
                    self.assertIn(marker, output)
                    self.assertIn(self.task.name, output)
                    self.assertIn('record', output.lower())

    def test_r11_f2_foreign_receipts_do_not_skip_agreement(self):
        body = '```text\n<!-- scout-repair:foreign -->\n- Verification: failed\n<!-- /scout-repair:foreign -->\n```\n'
        for final in (False, True):
            self.save((checkpoint(heading='applied').replace('outcome: pending', 'outcome: applied') if final else checkpoint()) + body)
            before = self.log.read_bytes()
            self.run_cli('resolve')
            self.assertEqual(self.log.read_bytes(), before)
            self.assert_rule('checkpoint')

    def test_r10_attack_shortcut_references_preserve_link_bytes(self):
        extra = '- Evidence: [outcome: pending]\n\n[outcome: pending]: saved.json\n'
        self.save(checkpoint() + extra)
        self.run_cli('resolve')
        self.assertIn(extra, self.log.read_text())
        self.assert_rule('checkpoint')

    def test_r10_attack_paragraph_and_checkpoint_boundaries(self):
        for boundary in ('\n', '#### Notes\n', '```text\n', '- A separate note\n'):
            self.save(checkpoint() + '- Verification: applied\n' + boundary + 'failed is prose outside that value\n')
            self.run_cli('resolve')
            self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])
        self.data['items'][0].update(disposition='failed', attempts=['A1', 'A2'],
                                     reason='State left: unchanged; rollback: retained')
        self.save(checkpoint() + '### Read-back\n- Verification: applied\n' + checkpoint('A2', 'failed'))
        self.run_cli('resolve')
        self.assertIn('### applied — component repair · attempt A1', self.log.read_text())
        self.assertIn('### failed — component repair · attempt A2', self.log.read_text())
        self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])

    def test_r10_f1_labelled_paragraphs_include_lazy_continuations(self):
        for extra in ('- Verification: applied;\nfailed on refresh\n',
                      '- Verification: applied\nfailed\n',
                      '- Verification: applied\nalready_satisfied\n',
                      '> Verification: applied;\nfailed on refresh\n',
                      '```text\n- Verification: applied;\nfailed on refresh\n```\n',
                      '- Verification: applied\n  refresh receipt\nfailed\n'):
            for final in (False, True):
                with self.subTest(extra=extra, final=final):
                    source = checkpoint(heading='applied').replace('outcome: pending', 'outcome: applied') if final else checkpoint()
                    self.save(source + extra)
                    before = self.log.read_bytes()
                    self.run_cli('resolve')
                    self.assertEqual(self.log.read_bytes(), before)
                    self.assert_rule('checkpoint')

    def test_r10_f2_outcome_owns_deeper_labelled_subvalues(self):
        for extra in ('- Outcome:\n  I1: unknown\n', '- Outcome:\n  I1: applied\n  I2: waiting\n',
                      '- Outcome: applied\n  I1: applied\n  I2: unknown\n',
                      '- Outcome: pending\n  I1: applied\n'):
            for final in (False, True):
                with self.subTest(extra=extra, final=final):
                    source = checkpoint(heading='applied').replace('outcome: pending', 'outcome: applied') if final else checkpoint()
                    self.save(source + extra)
                    before = self.log.read_bytes()
                    self.run_cli('resolve')
                    self.assertEqual(self.log.read_bytes(), before)
                    self.assert_rule('checkpoint')
        self.save(checkpoint() + '- Outcome:\n  I1: applied\n  I2: applied\n')
        self.run_cli('resolve')
        self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])

    def test_r10_f3_links_urls_and_filenames_are_not_outcome_fields(self):
        for extra, expected in (('- Evidence: [outcome: read-back](saved.json)\n', 0),
                                ('- Evidence: [outcome: pending](saved.json)\n', 3),
                                ('- File: my-outcome:report.md\n', 0),
                                ('- URL: https://example.test/outcome:report\n', 0),
                                ('- Outcome:\n  [applied](saved.json)\n', 0),
                                ('- Outcome: [applied](saved.json)\n', 0)):
            with self.subTest(extra=extra):
                self.save(checkpoint() + extra)
                self.run_cli('resolve')
                self.assertIn(extra, self.log.read_text())
                self.assertEqual(self.run_cli()[0], expected, self.run_cli()[1])

    def test_r10_f4_only_recorded_report_markers_exempt_delta_values(self):
        for name in ('example', 'repair-unrelated'):
            receipt = ('```text\n<!-- scout-repair:' + name + ' -->\n'
                       '- **Requested delta / exclusions:** STATUS equals: "Pending" → "Closed"; unchanged\n'
                       '<!-- /scout-repair:' + name + ' -->\n```\n')
            self.save(checkpoint(heading='applied').replace('outcome: pending', 'outcome: applied') + receipt)
            self.task.write_text(self.task.read_text() + '\nReport marker: <!-- scout-repair:example -->\n')
            self.assertEqual(self.run_cli()[0], 0 if name == 'example' else 3)
            self.task.write_text(self.task.read_text() + '\nReport marker: <!-- scout-repair:' + name + ' -->\n')
            self.assertEqual(self.run_cli()[0], 0)

    def test_r10_f5_agreement_crosses_noncheckpoint_headings(self):
        for extra in ('- [ ] ```text\n  ### Read-back\n  Outcome: failed\n  ```\n',
                      '> - [ ] ```text\n>   ### Read-back\n>   Outcome: failed\n>   ```\n',
                      '### Read-back\nOutcome: failed\n', '### Read-back\nVerification: pending\n',
                      'Read-back\n----------\nOutcome: failed\n'):
            for final in (False, True):
                with self.subTest(extra=extra, final=final):
                    source = checkpoint(heading='applied').replace('outcome: pending', 'outcome: applied') if final else checkpoint()
                    self.save(source + extra)
                    self.run_cli('resolve')
                    self.assert_rule('checkpoint')
                    if 'Outcome: failed' in extra:
                        self.assertIn('### applied' if final else '### PENDING', self.log.read_text())

    def test_r9_attack_compound_dispositions_include_segment_labels(self):
        for extra in ('- Verification: applied; failed: stale read-back\n',
                      '- Detail:\n  failed: refresh; applied\n',
                      '- outcome: pending (failed on refresh)\n'):
            self.save(checkpoint() + extra)
            before = self.log.read_bytes()
            self.run_cli('resolve')
            self.assertEqual(self.log.read_bytes(), before)
            self.assert_rule('checkpoint')

    def test_r9_attack_outcome_table_values_remain_strict(self):
        for label in ('Outcome', 'Outcome (attempt: A1)'):
            for value in ('unknown', 'pending', 'failed'):
                self.save(checkpoint() + '| ' + label + ' | ' + value + ' |\n')
                before = self.log.read_bytes()
                self.run_cli('resolve')
                self.assertEqual(self.log.read_bytes(), before)
                self.assert_rule('checkpoint')
        self.save(checkpoint() + '| Outcome | applied |\n')
        self.run_cli('resolve')
        self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])

    def test_r9_attack_classification_presentation_keeps_raw_value(self):
        for field in ('- [receipt](saved.json) · classification: exi**sting\n',
                      '- classification: new\n  [receipt](saved.json;section)\n  existing\n'):
            self.save()
            self.log.write_text(self.log.read_text().replace(
                '## Existing Component Before-State and Direct Repairs\nPreserved.\n', '') + field)
            self.assertIn('Existing Component Before-State', self.assert_rule('log-section'))

    def test_r9_f1_all_compound_dispositions_and_continuations_agree(self):
        for extra in ('- Verification: applied; failed on refresh\n',
                      '- I1: applied · I2 failed\n', '- I1: applied | I2 failed\n',
                      '- Detail:\n  applied; failed on refresh\n',
                      '```text\nVerification: applied; failed on refresh\n```\n'):
            with self.subTest(extra=extra):
                self.save(checkpoint() + extra)
                before = self.log.read_bytes()
                self.assertEqual(self.run_cli('resolve')[0], 0)
                self.assertEqual(self.log.read_bytes(), before)
                self.assert_rule('checkpoint')
                self.save(checkpoint(heading='applied').replace('outcome: pending', 'outcome: applied') + extra)
                self.assert_rule('checkpoint')
        for extra in ('- Verification: applied; applied on refresh\n',
                      '- I1: applied · I2 applied\n', '- Detail:\n  applied; applied on refresh\n'):
            self.save(checkpoint() + extra)
            self.run_cli('resolve')
            self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])

    def test_r9_f2_container_fences_precede_boundaries_and_inventory(self):
        for prefix in ('> ', '> > ', '- ', '  - ', '1. ', '> - ', '    > '):
            for delimiter in ('```', '~~~~'):
                with self.subTest(prefix=prefix, delimiter=delimiter):
                    for field in ('Outcome: failed', 'Verification: pending'):
                        extra = (prefix + delimiter + 'text\n' + prefix + '### Read-back\n' +
                                 prefix + field + '\n' + prefix + delimiter + '\n')
                        self.save(checkpoint() + extra)
                        self.run_cli('resolve')
                        self.assert_rule('checkpoint')
                        if field == 'Outcome: failed':
                            self.assertIn('### PENDING — component repair', self.log.read_text())
                        self.save(checkpoint(heading='applied').replace('outcome: pending', 'outcome: applied') + extra)
                        self.assert_rule('checkpoint')
                    self.log.write_text('Org: ' + ORG + '\n' + prefix + delimiter + 'text\n' +
                                        prefix + '## PENDING — component repair\n' + prefix + delimiter + '\n')
                    self.assertEqual(self.pending_rows(), [])

    def test_r9_f2_fence_closes_only_with_same_container_prefix(self):
        for opening, wrong in (('> ', ''), ('> ', '> > '), ('- ', '  '), ('> - ', '> ')):
            text = ('Org: ' + ORG + '\n' + opening + '```text\n' + wrong + '```\n' +
                    '## PENDING — hidden\n' + opening + '```\n## PENDING — visible\n')
            self.log.write_text(text)
            rows = self.pending_rows()
            self.assertEqual([r['heading'] for r in rows], ['PENDING — visible'])

    def test_r9_f3_real_writer_exempts_only_delta_json_business_values(self):
        from scout_report_repair import Repair, code_span
        task = self.folder / '.report-repairs' / 'example'
        task.mkdir(parents=True)
        receipt_log = self.folder / 'receipt.txt'
        for prior, after in (('Open', 'Pending'), ('Pending', 'Closed'),
                             ('Pending "review"', 'Still Pending; outcome: failed'),
                             ('Pending\\review', 'Pending\nreview')):
            with self.subTest(prior=prior, after=after):
                receipt_log.write_text('')
                contract = dict(target=dict(username=USER, org_id=ORG), member='Example/Report', baseline='saved.json',
                                delta=dict(column='STATUS', operator='equals', before=prior, after=after))
                state = dict(log=str(receipt_log), mutation='succeeded', acceptance='passed', recovery='complete',
                             original=dict(artifact=str(self.folder / 'preedit')), readback=str(task / 'readback.json'))
                Repair(None).checkpoint(task, contract, state, first=True)
                receipt = receipt_log.read_text()
                self.save(checkpoint() + '```text\n' + receipt + '```\n')
                self.task.write_text(self.task.read_text() + '\nReport marker: <!-- scout-repair:example -->\n')
                self.run_cli('resolve')
                self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])
                self.assertIn(receipt, self.log.read_text())
                # Real writer placeholders elsewhere must remain findings.
                for replacement in (receipt.replace('existing; ' + code_span('saved.json'), 'unknown; pending'),
                                    receipt.replace('acceptance=' + code_span('passed') + ';', 'acceptance=passed; pending;'),
                                    receipt.replace('all other report metadata', 'pending; all other report metadata'),
                                    receipt.replace('<!-- /scout-repair:example -->', '<!-- /scout-repair:other -->'),
                                    receipt.replace('Requested delta / exclusions', 'Evidence')):
                    self.assertNotEqual(replacement, receipt)
                    self.save(checkpoint(heading='applied').replace('outcome: pending', 'outcome: applied') +
                              '```text\n' + replacement + '```\n')
                    self.task.write_text(self.task.read_text() + '\nReport marker: <!-- scout-repair:example -->\n')
                    self.assert_rule('checkpoint')

    def test_r9_f4_classification_offsets_survive_link_and_markup_prefix(self):
        for prefix in ('', '- [receipt](evidence/component-describe.json) · ', '- **receipt**: saved · '):
            for label in ('classification', '**classification**'):
                with self.subTest(prefix=prefix, label=label):
                    self.save()
                    self.log.write_text(self.log.read_text().replace(
                        '## Existing Component Before-State and Direct Repairs\nPreserved.\n', '') +
                        prefix + label + ': Report: new\n  ReportFolder: existing\n')
                    self.assertIn('Existing Component Before-State', self.assert_rule('log-section'))

    def test_r9_f5_only_valued_outcome_fields_are_mentions(self):
        for extra in ('#### Outcome\nSaved read-back.\n', '- Outcome:\n  applied\n',
                      '- Outcome:\n  > applied\n', '- Outcome:\n',
                      '- Evidence: [read-back](outcome.json)\n', '- File: outcome.json\n'):
            with self.subTest(extra=extra):
                self.save(checkpoint() + extra)
                self.run_cli('resolve')
                self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])
        for extra in ('- Outcome:\n  failed\n', '- Outcome:\n  unknown\n', '- Outcome:\n  pending\n',
                      '- Outcome:\n  applied; failed on refresh\n', '- Outcome:\n  applied\n  unknown\n',
                      '- Outcome: applied\n  unknown\n'):
            self.save(checkpoint() + extra)
            before = self.log.read_bytes()
            self.run_cli('resolve')
            self.assertEqual(self.log.read_bytes(), before)
            self.assert_rule('checkpoint')

    def test_r9_f6_unplaced_checkpoint_headings_fail_closed_with_line(self):
        for title in ('- step\n    - nested\n\n    ## PENDING — component repair',
                      '- step\n    > ## PENDING — component repair',
                      '            > - > 1. ## PENDING — component repair',
                      '\t\t## PENDING — component repair'):
            self.log.write_text('Org: ' + ORG + '\n\n' + title + '\nNo write yet.\n')
            rows = self.pending_rows()
            self.assertEqual(len(rows), 1, rows)
            self.assertEqual(rows[0]['state'], 'unclear', rows)
            self.assertEqual(rows[0]['line'], 3 + title.count('\n'), rows)

    def test_r8_attack_pending_only_backticks_exempt_content(self):
        for field in ('<!-- pending verification -->', '<span title="pending">read-back</span>',
                      '- Receipt: [saved](evidence/pending/result.json)'):
            for before_state in (False, True):
                self.save()
                text = self.log.read_text()
                self.log.write_text(text.replace('Preserved.', field) if before_state else text + field + '\n')
                self.assert_rule('checkpoint')

    def test_r8_attack_strict_agreement_strips_internal_presentation(self):
        for field in ('- out_come: failed', '- I2: fa_iled', '- I2: alrea_dy_satisfied',
                      '- I2: **failed**', '- outcome: applied\n  > failed',
                      '- I2: failed: saved.json', '- I2: applied; failed',
                      '- out_come: pending', '- I2: <!-- failed --> applied'):
            with self.subTest(field=field):
                self.save(checkpoint() + field + '\n')
                before = self.log.read_bytes()
                self.run_cli('resolve')
                self.assertEqual(self.log.read_bytes(), before)
                self.assert_rule('checkpoint')

    def test_r8_attack_receipt_mapping_and_disposition_continuation_controls(self):
        for receipt_value, outcome in (('already_satisfied', 'already_satisfied'),
                                       ('unverified (read-back missing)', 'unverified'),
                                       ('released by operator', 'unverified'),
                                       ('blocked — not_applied (confirmed unchanged)', 'failed')):
            self.data['items'][0].update(disposition=outcome, reason='State left: unchanged; rollback: retained')
            receipt = ('```text\n<!-- scout-repair:example -->\n- **Outcome / read-back:** ' + receipt_value +
                       '; receipt.json\n<!-- /scout-repair:example -->\n```\n')
            self.save(checkpoint(outcome=outcome) + '- Detail:\n  - I1: ' + outcome + '\n' + receipt)
            self.record_report_marker()
            self.run_cli('resolve')
            self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])
            self.save(checkpoint(outcome='applied') + receipt)
            self.record_report_marker()
            before = self.log.read_bytes()
            self.run_cli('resolve')
            self.assertEqual(self.log.read_bytes(), before)

    def test_r8_f1_discovery_only_owned_final_headings_resolve(self):
        for body, expected in (('No write yet.', 'unresolved'),
                               ('- outcome: pending', 'unclear'),
                               ('```text\nOUTCOME: failed\n```', 'unclear')):
            self.save(checkpoint(outcome=None).split('\n')[0] + '\n' + body)
            self.assertEqual(self.pending_rows()[0]['state'], expected)
        self.save(checkpoint())
        self.assertEqual(self.pending_rows()[0]['state'], 'unclear')
        for body in ('outcome: applied (pilot write in flight)', 'outcome: failed', ''):
            self.save(checkpoint(heading='applied', outcome=None).split('\n')[0] + '\n' + body)
            self.assertEqual(self.pending_rows()[0]['state'], 'resolved')
            self.assert_rule('checkpoint')

    def test_r8_f2_agreement_reads_continuations_fences_and_canonical_evidence(self):
        for extra in ('- outcome: applied\n  - I2: failed\n',
                      '- outcome: applied\n  failed\n',
                      '```text\noutcome: failed\n```\n',
                      '- Receipt: failed\n', '#### Read-back\n- I2: failed\n'):
            for heading in ('PENDING', 'applied'):
                with self.subTest(extra=extra, heading=heading):
                    self.save(checkpoint(heading=heading).replace('outcome: pending', 'outcome: applied') + extra)
                    before = self.log.read_bytes()
                    self.run_cli('resolve')
                    self.assertEqual(self.log.read_bytes(), before)
                    self.assert_rule('checkpoint')
        self.save(checkpoint().replace('read-back receipt', 'read-back receipt; outcome: failed'))
        before = self.log.read_bytes()
        self.run_cli('resolve')
        self.assertEqual(self.log.read_bytes(), before)
        self.assert_rule('checkpoint')

    def test_r8_f2_unrewritable_pending_outcome_refuses(self):
        self.save(checkpoint().replace('outcome: pending', 'out**come**: pending (pilot write in flight)'))
        before = self.log.read_bytes()
        self.assertEqual(self.run_cli('resolve')[0], 0)
        self.assertEqual(self.log.read_bytes(), before)
        self.assert_rule('checkpoint')

    def test_r8_f2_actual_report_receipts_map_to_route_dispositions(self):
        from scout_report_repair import Repair
        task = self.folder / '.report-repairs' / 'example'
        task.mkdir(parents=True)
        receipt_log = self.folder / 'receipt.txt'
        contract = dict(target=dict(username=USER, org_id=ORG), member='Example/Report', baseline='saved.json',
                        delta=dict(column='STATUS', operator='equals', before='Open', after='Closed'))
        for mutation, acceptance, disposition, release in (
                ('not_applied', 'failed', 'failed', False), ('unknown', 'unknown', 'unverified', True),
                ('succeeded', 'passed', 'applied', False), ('not_attempted', 'passed', 'already_satisfied', False),
                ('not_attempted', 'failed', 'blocked', False)):
            with self.subTest(disposition=disposition):
                receipt_log.write_text('')
                state = dict(log=str(receipt_log), mutation=mutation, acceptance=acceptance, recovery='complete',
                             original=dict(artifact=str(self.folder / 'preedit')), readback=str(task / 'readback.json'))
                if release:
                    state['release_evidence'] = 'operator confirmed recovery retained'
                if disposition == 'blocked':
                    state['error'] = 'precondition refused before launch'
                Repair(None).checkpoint(task, contract, state, first=True)
                receipt = '```text\n' + receipt_log.read_text() + '```\n'
                self.data['items'][0]['disposition'] = disposition
                self.data['items'][0]['reason'] = 'State left: unchanged; rollback: retained'
                self.save(checkpoint(outcome=disposition) + receipt)
                self.record_report_marker()
                self.run_cli('resolve')
                self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])
                self.assertIn(receipt, self.log.read_text())

    def test_r8_f3_lexical_pending_in_full_body_and_before_state(self):
        for field in ("- Verification: user isn't verified: pending; don't proceed",
                      '- Artifact: saved.json; pending', '| verification | "pending (read-back)" |',
                      '- Evidence: Status: “Pending”', 'Business status is Pending.',
                      '```text\nverification: pending\n```'):
            for location in ('checkpoint', 'before-state', 'receipt'):
                with self.subTest(field=field, location=location):
                    self.save()
                    text = self.log.read_text()
                    if location == 'before-state':
                        text = text.replace('Preserved.', field)
                    elif location == 'receipt':
                        text += '<!-- scout-repair:example -->\n' + field + '\n<!-- /scout-repair:example -->\n'
                    else:
                        text += field + '\n'
                    self.log.write_text(text)
                    self.assert_rule('checkpoint')
        for field in ('- Evidence: Status: `Pending`', '| verification | `pending (read-back)` |',
                      '- verification: ``pending``'):
            self.save()
            self.log.write_text(self.log.read_text() + field + '\n')
            self.assertEqual(self.run_cli()[0], 0)

    def test_r8_f4_heading_inventory_and_empty_boundary(self):
        for heading in ('PENDING — component repair\ncontinued title\n---',
                        '- step\n    ### PENDING — component repair',
                        '## pending — component\t repair'):
            self.log.write_text('Org: ' + ORG + '\n' + heading + '\nOutcome: failed\n')
            self.assertEqual([r['state'] for r in self.pending_rows()], ['unclear'])
        for boundary in ('##', '##   ', '> ##'):
            self.log.write_text('# Change Log — Example\n' + boundary + '\nTask record: ' + self.task.name + '\n' + checkpoint())
            before = self.log.read_bytes()
            self.assertEqual(self.run_cli('resolve')[0], 4)
            self.assertEqual(self.log.read_bytes(), before)
        self.log.write_text('#\nTask record: ' + self.task.name + '\n' + checkpoint())
        before = self.log.read_bytes()
        self.assertEqual(self.run_cli('resolve')[0], 4)
        self.assertEqual(self.log.read_bytes(), before)

    def test_r8_f5_classification_boundaries_continuations_and_eof(self):
        for field, expected in (('> classification:\n> existing\n', 3),
                                ('- classification: new · evidence: no existing component\n', 0),
                                ('- classification: new; evidence: existing elsewhere\n', 0),
                                ('- classification: new | evidence: existing elsewhere\n', 0),
                                ('- classification:', 3)):
            with self.subTest(field=field):
                self.save()
                self.log.write_text(self.log.read_text().replace(
                    '## Existing Component Before-State and Direct Repairs\nPreserved.\n', '') + field)
                self.assertEqual(self.run_cli()[0], expected)

    def test_r8_f7_setext_heading_underline_is_exempt_from_map_cap(self):
        self.data['history']['architecture'] = 'created'
        self.save()
        for ending in ('\n', ''):
            arch = self.architecture()
            arch.write_text(arch.read_text() + '\nNotes\n' + '=' * 321 + ending)
            self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])

    def test_r7_f1_legacy_never_resolves_and_reads_full_raw_body(self):
        for body in ('**Outcome:** applied', '**Outcome:**\n  - I1: pending\n  - **Outcome:** applied',
                     '    **Outcome:** applied', '```text\nOutcome: applied\n```',
                     '### Evidence\nAn OUTCOME is recorded', 'No writes yet.'):
            with self.subTest(body=body):
                self.log.write_text(f'Org: {ORG}\n## PENDING — component repair\n{body}\n')
                expected = 'unclear' if 'outcome' in body.lower() else 'unresolved'
                self.assertEqual(self.pending_rows()[0]['state'], expected)

    def test_r7_f2_one_agreement_rule_for_discovery_resolve_and_check(self):
        for extra in ('- **Outcome (attempt: A1):** failed\n',
                      '#### Read-back\n**Outcome:** failed\n',
                      '#### Read-back\n- **Outcome (attempt: A1):** pending\n',
                      'The outcome is still unknown.\n',
                      '| Outcome | failed |\n', '    - **Outcome: applied.** example\n'):
            with self.subTest(extra=extra):
                self.save(checkpoint() + extra)
                self.assertEqual(self.pending_rows()[0]['state'], 'unclear')
                before = self.log.read_bytes()
                self.assertEqual(self.run_cli('resolve')[0], 0)
                if extra == 'The outcome is still unknown.\n':
                    # Round-8 F5: prose with no valued outcome field is not a mention.
                    self.assertNotEqual(self.log.read_bytes(), before)
                    self.assertEqual(self.run_cli()[0], 0)
                    continue
                self.assertEqual(self.log.read_bytes(), before)
                self.assert_rule('checkpoint')
                self.save(checkpoint(heading='applied').replace('outcome: pending', 'outcome: applied') + extra)
                self.assertEqual(self.pending_rows()[0]['state'], 'resolved')
                self.assert_rule('checkpoint')

    def test_r7_f3_o5_replay_replaces_whole_compound_outcome_values(self):
        for status in ('- outcome: pending (pilot write in flight)',
                       '- Classification: new (seed) · preedit_snapshot.status: not_needed · outcome: pending (deploy in flight)',
                       '- outcome: pending (first); outcome: pending (second) | verification: complete',
                       '- outcome: **pending (deploy in flight)**',
                       '- **Outcome (attempt: A1):** pending (deploy in flight)'):
            with self.subTest(status=status):
                self.save(checkpoint().replace('- outcome: pending', status))
                self.assertEqual(self.pending_rows()[0]['state'], 'unclear')
                self.assertEqual(self.run_cli('resolve')[0], 0)
                after = self.log.read_text()
                self.assertIn('### applied — component repair', after)
                self.assertNotIn('in flight', after)
                self.assertNotIn('(first)', after)
                self.assertNotIn('(second)', after)
                self.assertIn('- **Outcome: applied.** read-back receipt', after)
                if status.startswith('- **Outcome ('):
                    self.assertIn('- **Outcome (attempt: A1):** applied', after)
                if 'outcome: **pending' in status:
                    self.assertIn('outcome: **applied**', after)
                self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])
                self.assertEqual(self.run_cli('resolve')[0], 0)
                self.assertEqual(self.log.read_text(), after)

    def test_r7_f3_f4_pending_values_in_full_sections_and_receipts(self):
        for field in ('- verification: complete\n  - pending', '- verification:\n  - I1: pending',
                      '> verification:\n>   pending', '- verification:\n  - [ ] pending',
                      '- **Classification / source:** Report: existing; ReportFolder: pending',
                      '- Receipt: saved.json; verification: **pen**ding',
                      '- Receipt: saved.json; readback: pen`ding`',
                      'Field | Value\n--- | ---\nRead-back | pending',
                      '| Field | Value |\n| --- | --- |\n| verification | **pending** |'):
            for location in ('own', 'nested', 'before-state', 'receipt'):
                with self.subTest(field=field, location=location):
                    self.save()
                    text = self.log.read_text()
                    if location == 'before-state':
                        text = text.replace('Preserved.', field)
                    elif location == 'receipt':
                        text += '```text\n<!-- scout-repair:example -->\n' + field + '\n<!-- /scout-repair:example -->\n```\n'
                        self.record_report_marker()
                    else:
                        text += ('#### Read-back\n' if location == 'nested' else '') + field + '\n'
                    self.log.write_text(text)
                    self.assertEqual(self.run_cli()[0], 0 if 'pen`ding`' in field else 3)

    def test_r7_f3_business_values_require_quotes_but_status_quotes_do_not_hide_pending(self):
        for quote in ('`', '"', "'"):
            self.save()
            self.log.write_text(self.log.read_text() + '- Evidence: Status: ' + quote + 'Pending' + quote + '\n')
            self.assertEqual(self.run_cli()[0], 0 if quote == '`' else 3)
        self.log.write_text(self.log.read_text() + '- Evidence: Status: Pending\n')
        self.assert_rule('checkpoint')

    def test_r7_f5_container_and_setext_headings_and_ownership_boundary(self):
        for title in ('> ## PENDING — component repair', '- ### PENDING — component repair',
                      'PENDING — component repair\n--------------------------'):
            with self.subTest(title=title):
                self.log.write_text(f'Org: {ORG}\n{title}\nOutcome: applied\n')
                self.assertEqual([r['state'] for r in self.pending_rows()], ['unclear'])
        self.log.write_text('# Change Log — Example\nNotes\n-----\nTask record: ' + self.task.name + '\n' + checkpoint())
        before = self.log.read_bytes()
        self.assertEqual(self.run_cli('resolve')[0], 4)
        self.assertEqual(self.log.read_bytes(), before)

    def test_r7_f6_classification_continuation_requires_before_state_only_after_attempt(self):
        for disposition in ('applied', 'already_satisfied', 'blocked'):
            with self.subTest(disposition=disposition):
                self.data['items'] = [item(disposition=disposition)]
                self.data['items'][0]['attempts'] = ['A1']
                self.save()
                self.log.write_text(self.log.read_text().replace(
                    '## Existing Component Before-State and Direct Repairs\nPreserved.\n', '') + '- classification:\n  existing\n')
                self.assertEqual(self.run_cli()[0], 3 if disposition == 'applied' else 0)

    def test_r7_f7_only_recognized_headings_escape_created_map_line_cap(self):
        self.data['history']['architecture'] = 'created'
        self.save()
        for prefix in ('#tag', '####### '):
            arch = self.architecture()
            arch.write_text(arch.read_text() + '\n## Notes\n' + prefix + 'x' * 321 + '\n')
            self.assert_rule('arch')

    def test_r7_f8_valid_recorded_settled_checkpoint_before_final_section(self):
        self.assertEqual(self.run_cli()[0], 0)
        text = self.log.read_text()
        prefix, body = text.split('## Checkpoints\n')
        self.log.write_text(prefix + body + '## Checkpoints\n')
        self.assert_rule('checkpoint')

    def test_r7_f10_created_map_line_budget_independent_of_word_budget(self):
        self.data['history']['architecture'] = 'created'
        self.save()
        arch = self.architecture()
        arch.write_text(arch.read_text() + '\n## Notes\n' + 'x\n' * 351)
        self.assertLess(len(arch.read_text().split()), 3750)
        self.assert_rule('arch')

    def test_r7_f11_lowercase_repair_candidate_but_not_business_prose(self):
        for title in ('pending — component repair', 'Component Repair: pending', 'Pending Approval'):
            self.log.write_text(f'Org: {ORG}\n## {title}\nNo writes yet.\n')
            self.assertEqual([r['state'] for r in self.pending_rows()], [] if title == 'Pending Approval' else ['unresolved'])

    def test_r7_attack_final_heading_conflict_cannot_be_rewritten(self):
        self.save(checkpoint(outcome='applied', heading='failed').replace('outcome: pending', 'outcome: applied'))
        self.assertEqual(self.pending_rows()[0]['state'], 'resolved')
        before = self.log.read_bytes()
        self.run_cli('resolve')
        self.assertEqual(self.log.read_bytes(), before)
        self.assert_rule('checkpoint')

    def test_r7_attack_hidden_outcome_mentions_fail_closed(self):
        for extra in ('<!-- outcome: failed -->', '<span title="outcome: failed">receipt</span>'):
            self.save(checkpoint() + extra + '\n')
            self.assertEqual(self.pending_rows()[0]['state'], 'unclear')
            before = self.log.read_bytes()
            self.run_cli('resolve')
            self.assertEqual(self.log.read_bytes(), before)

    def test_r7_attack_outcome_field_anywhere_in_line(self):
        for status in ('- Receipt saved; status notes outcome: pending (in flight)',
                       '- Attempt A1 recorded outcome: pending (in flight) · verification: complete'):
            self.save(checkpoint().replace('- outcome: pending', status))
            self.assertEqual(self.pending_rows()[0]['state'], 'unclear')
            self.run_cli('resolve')
            self.assertNotIn('in flight', self.log.read_text())
            self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])

    def test_r7_attack_quotes_exempt_business_values_only(self):
        for field in ('- verification:\n  `pending`', '| verification | `pending` |',
                      '| preedit_snapshot.status | "pending" |'):
            self.save()
            self.log.write_text(self.log.read_text() + field + '\n')
            self.assertEqual(self.run_cli()[0], 0 if '`pending`' in field else 3)
        self.save()
        self.log.write_text(self.log.read_text() + '| Status | `Pending` |\n')
        self.assertEqual(self.run_cli()[0], 0)

    def test_r7_attack_classification_list_value_and_raw_pending_heading(self):
        self.log.write_text(self.log.read_text().replace(
            '## Existing Component Before-State and Direct Repairs\nPreserved.\n', '') +
            '- classification:\n  - existing\n')
        with self.subTest(shape='classification list'):
            self.assert_rule('log-section')
        with self.subTest(shape='raw heading'):
            self.log.write_text(f'Org: {ORG}\n## <!-- PENDING --> component repair\nNo writes yet.\n')
            self.assertEqual([r['state'] for r in self.pending_rows()], ['unresolved'])

    def test_r7_attack_marked_receipt_outcomes_share_full_body_agreement(self):
        for receipt_outcome, expected in (('applied', 'resolved'), ('failed', 'unclear'), ('pending', 'unclear')):
            with self.subTest(receipt_outcome=receipt_outcome):
                receipt = ('```text\n<!-- scout-repair:example -->\n'
                           '- **Outcome / read-back:** ' + receipt_outcome + '; receipt.json\n'
                           '<!-- /scout-repair:example -->\n```\n')
                self.save(checkpoint() + receipt)
                self.record_report_marker()
                before = self.log.read_bytes()
                self.assertEqual(self.pending_rows()[0]['state'], 'unclear')
                self.run_cli('resolve')
                self.assertIn(receipt, self.log.read_text())
                if expected == 'unclear':
                    self.assertEqual(self.log.read_bytes(), before)
                    self.assert_rule('checkpoint')
                else:
                    self.assertEqual(self.run_cli()[0], 0)

    def test_r7_attack_whole_classification_value_including_table(self):
        for field in ('- classification: Report — existing',
                      '| Classification / source | Report: existing |'):
            for disposition in ('applied', 'already_satisfied', 'blocked'):
                with self.subTest(field=field, disposition=disposition):
                    self.data['items'] = [item(disposition=disposition)]
                    self.data['items'][0]['attempts'] = ['A1']
                    self.save()
                    self.log.write_text(self.log.read_text().replace(
                        '## Existing Component Before-State and Direct Repairs\nPreserved.\n', '') + field + '\n')
                    self.assertEqual(self.run_cli()[0], 3 if disposition == 'applied' else 0)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.folder = self.root / 'orgs' / 'example'
        self.folder.mkdir(parents=True)
        self.task = self.folder / 'task-2026-10-13-1200-example.md'
        self.data = record()
        self.save()

    def save(self, checkpoints=None):
        if checkpoints is None:
            checkpoints = ''.join(checkpoint(a, i['disposition'], i['disposition']).replace('outcome: pending', 'outcome: ' + i['disposition'])
                                  for i in self.data['items'] for a in i['attempts'] if i['disposition'])
        self.task.write_text(f'# Task\nOrg: {USER} ({ORG})\n\n```scout-items\n' + json.dumps(self.data) + '\n```\n')
        self.log = self.folder / self.data['change_log']
        self.log.write_text(f'# Change Log — Example — 2026-10-13 1200\nOrg: {USER} ({ORG})\n'
            f'Task record: {self.task.name}\nAudit used: scoped (task record)\n' + expected_render(self.data) +
            '\n'.join('## ' + s + '\nRecorded.\n' for s in LOG_SECTIONS if s not in
                      ('Completion Reconciliation', 'What Was Skipped')) +
            '## Existing Component Before-State and Direct Repairs\nPreserved.\n'
            '## Script Deliverables\nNone.\n' + ('## Checkpoints\n' + checkpoints if checkpoints else ''))

    def run_cli(self, command='check', *extra):
        args = [command, *extra] if extra else [command, '--task', str(self.task)]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = history.main(args)
        return code, output.getvalue()

    def assert_rule(self, rule, command='check'):
        code, output = self.run_cli(command)
        self.assertEqual(code, 3, output)
        self.assertIn(': ' + rule + ':', output)
        return output

    def test_valid_check_and_render_are_read_only(self):
        before = self.hashes()
        self.assertEqual(self.run_cli()[0], 0)
        code, output = self.run_cli('render')
        self.assertEqual(code, 0)
        self.assertIn('Overall: FULLY_VERIFIED', output)
        self.assertIn('Grounding: 1 items; docs 0; skill 1; org 0; ungrounded 0', output)
        self.assertEqual(before, self.hashes())

    def test_mapping_each_disposition_and_visual_qa(self):
        cases = [('applied', False, 0, 'FULLY_VERIFIED', 'applied'),
                 ('already_satisfied', False, 1, 'FULLY_VERIFIED', 'already_satisfied'),
                 ('applied', True, 2, 'FINISHED_WITH_EXCEPTIONS', 'AWAITING_QA'),
                 ('omitted', False, 2, 'FINISHED_WITH_EXCEPTIONS', 'SKIPPED'),
                 ('failed', False, 3, 'UNRESOLVED', 'FAILED'),
                 ('blocked', False, 3, 'UNRESOLVED', 'BLOCKED'),
                 ('unverified', False, 3, 'UNRESOLVED', 'INCOMPLETE (unverified)')]
        for disposition, visual, section, overall, label in cases:
            with self.subTest(disposition=disposition, visual=visual):
                value = item(disposition=disposition)
                value['visual_qa'] = visual
                if disposition == 'omitted':
                    value['reason'] = 'SE withdrew in confirmation'
                self.data['items'] = [value]
                self.save()
                self.assertEqual(self.run_cli()[0], 0)
                rendered = self.run_cli('render')[1]
                self.assertIn('Overall: ' + overall, rendered)
                self.assertIn('### ' + SECTIONS[section] + '\n- I1 — ' + label, rendered)
                skipped = rendered.split('## What Was Skipped\n')[1].split('\n## ')[0]
                self.assertEqual('- I1' in skipped, disposition == 'omitted')
        self.data['items'] = [item(), item('I2', 'blocked')]
        self.save()
        self.assertIn('UNRESOLVED', self.run_cli('render')[1])

    def test_block_missing_duplicate_malformed_and_schema(self):
        for text in ('no block', ('```scout-items\n' + json.dumps(record()) + '\n```\n') * 2,
                     '```scout-items\n{\n```', '```scout-items\n' + json.dumps(record())[:-1] + ', "schema": 1}\n```',
                     '```scout-items\n' + json.dumps(record())[:-1] + ', "note": NaN}\n```'):
            self.task.write_text(text)
            self.assert_rule('block')
        for key, value in [('schema', True), ('items', {}), ('history', None), ('path', 'unknown')]:
            with self.subTest(key=key):
                self.data = record()
                self.data[key] = value
                self.task.write_text('```scout-items\n' + json.dumps(self.data) + '\n```')
                self.assert_rule('block')

    def test_block_item_types_unique_ids_and_attempts(self):
        for key, value in [('depends_on', [None]), ('components', {}), ('type', ''), ('grounding', [None]),
                           ('visual_qa', 'false'), ('readback', []), ('attempts', ['A1', 'A1'])]:
            with self.subTest(key=key):
                self.data = record()
                self.data['items'][0][key] = value
                self.task.write_text('```scout-items\n' + json.dumps(self.data) + '\n```')
                self.assert_rule('block')
        self.data = record()
        self.data['items'] *= 2
        self.save()
        self.assert_rule('block')

    def test_disposition_unknown_omitted_failed_and_visual_qa(self):
        for disposition in (None, 'success', 'omitted', 'failed'):
            self.data['items'] = [item(disposition=disposition)]
            self.data['items'][0]['reason'] = ''
            self.save()
            self.assert_rule('disposition')
        self.data['items'] = [item(disposition='already_satisfied')]
        self.data['items'][0]['visual_qa'] = True
        self.save()
        self.assert_rule('disposition')
        self.data['items'] = [item()]
        self.data['items'][0]['evidence'] = ''
        self.save()
        self.assert_rule('disposition')

    def story(self):
        self.data['path'] = 'open-ended'
        self.data['items'][0]['beat'] = 'B1'
        self.data['story'] = dict(residual='See risk', audience='Manager', kp1='Late work', kp2='', kp3='Visible risk',
            source='se-confirmed', beats=[dict(id='B1', name='See risk', persona='Manager', pain='Late work',
            climax='Open overdue list', proof_moment=True, claims=[dict(text='One overdue record', item='I1')])])
        self.data['items'][0]['grounding'] = [dict(assumption='Overdue filtering', source='docs',
            ref='https://example.test/docs', verdict='supported')]

    def test_story_required_proof_source_claim_readback_and_proves(self):
        self.data['path'] = 'open-ended'
        self.save()
        self.assert_rule('story')
        self.story()
        self.save()
        self.assertEqual(self.run_cli()[0], 0)
        good = copy.deepcopy(self.data)
        for mutation in ('source', 'proof', 'claim', 'readback', 'proves'):
            self.data = copy.deepcopy(good)
            if mutation == 'source': self.data['story']['source'] = ''
            if mutation == 'proof': self.data['story']['beats'][0]['proof_moment'] = False
            if mutation == 'claim': self.data['story']['beats'][0]['claims'][0]['item'] = 'I9'
            if mutation == 'readback': self.data['items'][0]['readback'] = ''
            if mutation == 'proves': self.data['items'][0]['proves'] = ''
            self.save()
            self.assert_rule('story')

    def test_dependency_missing_cycle_and_unresolved_parent(self):
        self.data['items'][0]['depends_on'] = ['I9']
        self.save()
        self.assert_rule('dependency')
        self.data['items'] = [item(), item('I2')]
        self.data['items'][0]['depends_on'] = ['I2']
        self.data['items'][1]['depends_on'] = ['I1']
        self.save()
        self.assertIn('cycle', self.assert_rule('dependency'))
        self.data['items'][1]['depends_on'] = []
        for disposition in ('failed', 'blocked', 'unverified'):
            self.data['items'][1] = item('I2', disposition)
            self.save()
            self.assert_rule('dependency')

    def test_grounding_missing_gated_and_unknown_types(self):
        self.data['items'][0]['grounding'] = []
        self.save()
        self.assert_rule('grounding')
        for family in ('Flow', 'ApexClass', 'LWC', 'Agentforce', 'CaseSettings', 'Dashboard', 'NovelType'):
            self.data = record()
            self.data['items'][0]['type'] = family
            self.save()
            self.assert_rule('grounding')
        self.data = record()
        self.data['items'][0]['category'] = 'gated'
        self.save()
        self.assert_rule('grounding')

    def test_grounding_docs_url_verdict_proof_and_ui_only(self):
        self.story()
        self.data['items'][0]['grounding'][0]['ref'] = ''
        self.save()
        self.assert_rule('grounding')
        self.data['items'][0]['grounding'] = item()['grounding']
        self.save()
        self.assert_rule('grounding')
        self.data = record()
        self.data['items'][0].update(disposition='omitted', attempts=[], reason='Docs-confirmed UI-only')
        self.save()
        self.assert_rule('grounding')
        self.data['items'][0]['grounding'] = [dict(assumption='UI capability', source='docs',
            ref='https://example.test/docs', verdict='UI-only')]
        self.save()
        self.assertEqual(self.run_cli()[0], 0)
        self.data['items'][0]['grounding'][0]['verdict'] = ''
        self.save()
        self.assert_rule('grounding')

    def test_docs_unavailable_warning_and_other_ungrounded_findings(self):
        self.story()
        self.data['items'][0]['category'] = 'gated'
        entry = dict(assumption='Mechanism', source='ungrounded', ref='', verdict='Docs unavailable: SE accepted risk')
        self.data['items'][0]['grounding'] = [entry]
        self.save()
        code, output = self.run_cli()
        self.assertEqual(code, 0, output)
        self.assertIn('grounding: warning:', output)
        self.assertIn('ungrounded 1', self.run_cli('render')[1])
        entry['verdict'] = 'Not researched'
        self.save()
        self.assert_rule('grounding')
        entry.update(verdict='Docs unavailable', ref='https://example.test/fabricated')
        self.save()
        self.assert_rule('grounding')

    def test_log_header_missing_wrong_owner_and_grounding(self):
        for old, new in [('Task record: ' + self.task.name, 'Task record: task-other.md'),
                         ('Audit used:', 'Audit:'), ('Grounding:', 'Grounds:'), ('# Change Log', '# Log')]:
            self.save()
            self.log.write_text(self.log.read_text().replace(old, new))
            self.assert_rule('log-header')
        self.log.unlink()
        self.assert_rule('log-header')

    def test_log_sections_and_conditional_sections(self):
        for section in (*LOG_SECTIONS, *SECTIONS):
            self.save()
            self.log.write_text(self.log.read_text().replace(section, 'Missing section'))
            self.assert_rule('log-section')
        self.data['items'][0]['attempts'] = ['A1']
        self.save(checkpoint() + '- **Classification / source:** existing\n')
        self.log.write_text(self.log.read_text().replace('## Existing Component Before-State and Direct Repairs', '## Gone'))
        self.assert_rule('log-section')
        self.data['items'][0]['seed_asset'] = 'seed.sh'
        (self.folder / 'seed.sh').write_text('# synthetic\n')
        self.save(checkpoint())
        self.log.write_text(self.log.read_text().replace('## Script Deliverables', '## Gone'))
        self.assert_rule('log-section')

    def test_reconciliation_wrong_section_duplicate_and_semantic_text(self):
        self.log.write_text(self.log.read_text().replace('I1 — applied — Describe confirms label', 'I1 arbitrary evidence wording'))
        self.assertEqual(self.run_cli()[0], 0)
        self.log.write_text(self.log.read_text().replace('### Unresolved Work\nNone.', '### Unresolved Work\n- I1 — FAILED'))
        self.assert_rule('reconciliation')
        self.save()
        self.log.write_text(self.log.read_text().replace('- I1', '- I9'))
        self.assert_rule('reconciliation')

    def test_overall_wrong_and_visual_qa_never_fully_verified(self):
        self.data['items'][0]['visual_qa'] = True
        self.save()
        self.log.write_text(self.log.read_text().replace('FINISHED_WITH_EXCEPTIONS', 'FULLY_VERIFIED'))
        self.assert_rule('overall')

    def test_resolve_failed_then_applied_retry_idempotent_and_preserves_files(self):
        self.data['items'][0]['attempts'] = ['A1', 'A2']
        self.save(checkpoint('A1', 'failed') + checkpoint('A2'))
        (self.folder / 'notes.md').write_bytes(b'Hand-kept\r\n')
        before = self.hashes()
        self.assertEqual(self.run_cli('resolve')[0], 0)
        text = self.log.read_text()
        self.assertIn('### failed — component repair · attempt A1', text)
        self.assertIn('### applied — component repair · attempt A2', text)
        self.assertNotIn('outcome: pending', text)
        self.assertEqual(self.run_cli()[0], 0)
        after = self.hashes()
        self.assertEqual({k:v for k,v in before.items() if k != self.log}, {k:v for k,v in after.items() if k != self.log})
        self.assertIn('"changed": []', self.run_cli('resolve')[1])
        self.assertEqual(after, self.hashes())

    def test_resolve_missing_conflicting_outcomes_stay_pending(self):
        for body in (checkpoint(outcome=None), checkpoint() + '- **Outcome: failed.** second claim\n',
                     checkpoint() + '- **Outcome: not_applied.** unsupported second claim\n'):
            self.data['items'][0]['attempts'] = ['A1']
            self.save(body)
            before = self.log.read_bytes()
            self.assertEqual(self.run_cli('resolve')[0], 0)
            self.assertEqual(before, self.log.read_bytes())
            self.assert_rule('checkpoint')

    def test_checkpoint_missing_duplicate_unowned_and_pending_fields(self):
        self.data['items'][0]['attempts'] = ['A1']
        for body in ('', checkpoint() * 2, checkpoint(heading='applied')):
            self.save(body)
            self.assert_rule('checkpoint')
        self.save(checkpoint('UNOWNED') + checkpoint())
        self.run_cli('resolve')
        self.assertIn('### PENDING — component repair · attempt UNOWNED', self.log.read_text())
        self.data['items'][0]['disposition'] = None
        self.save(checkpoint(outcome=None))
        self.run_cli('resolve')
        self.assertIn('PENDING', self.log.read_text())
        self.assertNotIn(': checkpoint:', self.run_cli()[1])

    def test_resolve_wrong_task_header_refused_without_write(self):
        self.data['items'][0]['attempts'] = ['A1']
        self.save(checkpoint())
        self.log.write_text(self.log.read_text().replace(self.task.name, 'task-other.md'))
        before = self.hashes()
        self.assertEqual(self.run_cli('resolve')[0], 4)
        self.assertEqual(before, self.hashes())

    def test_seed_asset_and_path_escape_and_symlink(self):
        self.data['items'][0]['seed_asset'] = 'missing.sh'
        self.save()
        self.assert_rule('seed-asset')
        self.data['items'][0]['seed_asset'] = '../elsewhere.sh'
        self.save()
        self.assertEqual(self.run_cli()[0], 4)
        self.data['items'][0]['seed_asset'] = ''
        self.save()
        elsewhere = self.root / 'elsewhere.md'
        elsewhere.write_text(self.log.read_text())
        self.log.unlink()
        self.log.symlink_to(elsewhere)
        self.assertEqual(self.run_cli('resolve')[0], 4)

    def architecture(self, extra=''):
        arch = self.folder / 'demo-architecture.md'
        arch.write_text('# Demo Architecture — Example\nLast reconciled: 2026-10-13 1200 by /scout\n'
                        f'Target Org: demo ({USER})\nReconciled through: {self.data["change_log"]}\n' + extra +
                        '\n'.join('## ' + s + '\nRecorded.\n' for s in ARCH_SECTIONS) +
                        f'- **[2026-10-13]** — Keep fields. **Why:** scope. (see `{self.data["change_log"]}`)\n')
        return arch

    def test_arch_headers_stamp_entry_date_and_length(self):
        self.data['history']['architecture'] = 'created'
        self.save()
        self.assert_rule('arch')
        arch = self.architecture()
        self.assertEqual(self.run_cli()[0], 0)
        for before, after in [('by /scout', 'by someone'), ('Reconciled through:', 'Through:'),
                              ('[2026-10-13]', '[undated]'), ('Keep fields.', 'x' * 321)]:
            self.architecture()
            arch.write_text(arch.read_text().replace(before, after))
            self.assert_rule('arch')

    def test_history_proposed_entries_and_pending_reoffer(self):
        self.data['history']['decisions'] = 'proposed'
        self.save()
        self.assert_rule('history')
        self.data['history']['proposed_entries'] = ['Keep scope. Why: proof.']
        self.save()
        self.assertEqual(self.run_cli()[0], 0)
        code, output = self.run_cli('pending', '--orgs-dir', str(self.folder.parent), '--org-id', ORG)
        self.assertEqual(code, 0)
        self.assertEqual([json.loads(line)['proposed_entries'] for line in output.splitlines() if json.loads(line)['state'] == 'proposed'], [self.data['history']['proposed_entries']])

    def hashes(self):
        return {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.folder.rglob('*') if p.is_file()}

    def stress(self):
        names = []
        for n in range(25):
            name = f'changes-2026-{8 + n // 9:02d}-{1 + n % 9:02d}-1000-example.md'
            names.append(name)
            body = 'Free-form historical note.\n'
            if n in (8, 9, 10):
                endings = ['**Outcome**: APPLIED — receipt', '**Outcome:** failed — receipt', 'FINAL OUTCOME (attempt old): unverified']
                body = '## CHECKPOINT: PENDING - Component Repair (Attempt old)\n' + endings[n - 8] + '\n'
            elif n == 11:
                body = '### PENDING — component repair — attempt unresolved\nNo final marker.\n'
            elif n == 12:
                body = '### PENDING — component repair — attempt partial\n**Outcome**: PARTIALLY APPLIED - partial\n'
            elif n in (13, 14):
                body = checkpoint('old-' + str(n), heading='applied').replace('outcome: pending', 'outcome: applied')
            elif n >= 15:
                body = '## Achieved State\nHistorical read-back.\n## SE Must Do\nReview the visible screen.\n'
            (self.folder / name).write_text(f'# History\nOrg: {USER} ({ORG})\n' + body)
        for n in range(18):
            (self.folder / f'demo-spec-2026-08-{n+1:02d}.md').write_text('Historical synthetic spec.\n')
        for name in ('README.md', 'demo-path.md', 'archive/notes.md'):
            p = self.folder / name
            p.parent.mkdir(exist_ok=True)
            p.write_text('Hand-curated; not prune targets.\n')
        arch = self.architecture('## Current Live State\n' + ('live state ' * 200) + '\n')
        content = arch.read_text().replace(self.data['change_log'], names[0][:-3] + ' # historical comment')
        content += '\n'.join(f'- **[2026-08-01]** — Decision {n}. ' + 'synthetic ' * 94 for n in range(30))
        arch.write_text(content)
        sibling = self.folder.parent / 'unrelated'
        sibling.mkdir()
        (sibling / 'changes-2026-10-13-1000-other.md').write_text('# Other\n### PENDING — component repair\n')
        return names, arch

    def test_stress_pending_exact_counts_and_reconcile_read_cap(self):
        names, arch = self.stress()
        self.assertGreater(len(arch.read_text().split()), 3200)
        self.assertLess(len(arch.read_text().split()), 3500)
        code, output = self.run_cli('pending', '--orgs-dir', str(self.folder.parent), '--org-id', ORG[:15])
        self.assertEqual(code, 0)
        states = [json.loads(line)['state'] for line in output.splitlines()]
        self.assertEqual(states.count('unresolved'), 1)
        self.assertEqual(states.count('unclear'), 4)
        self.assertEqual(states.count('resolved'), 3)  # two owned historical plus current task
        code, output = self.run_cli('reconcile-plan', '--folder', str(self.folder))
        rows = [json.loads(line) for line in output.splitlines()]
        self.assertEqual(code, 0)
        self.assertEqual(len(rows), 25)  # 24 newer historical logs plus this task's log
        self.assertEqual([r['read'] for r in rows], ['full'] * 5 + ['last-section'] * 20)
        self.assertEqual([Path(r['file']).name for r in rows], sorted([*names[1:], self.log.name], reverse=True))
        self.assertEqual(self.run_cli()[0], 0)  # No linting of historical free-form logs or map.

    def test_stress_resolve_hashes_and_arch_budget_owner(self):
        self.stress()
        self.data['items'][0]['attempts'] = ['A1']
        self.save(checkpoint())
        before = self.hashes()
        self.assertEqual(self.run_cli('resolve')[0], 0)
        after = self.hashes()
        self.assertEqual([p for p in before if before[p] != after[p]], [self.log])
        self.data['history']['architecture'] = 'reconciled'
        self.data['items'][0]['attempts'] = ['A1']
        self.save()
        self.architecture('## Current Live State\n' + 'retained ' * 3800 + '\n')
        code, output = self.run_cli()
        self.assertEqual(code, 0, output)
        self.assertIn('arch: warning:', output)
        arch = self.architecture()
        arch.write_text(arch.read_text().replace('## Decision Log\n', '## Decision Log\n' + 'decision ' * 3800 + '\n'))
        self.assert_rule('arch')

    def test_pending_legacy_continuation_unknown_kind_and_username_match(self):
        self.log.write_text(f'# Log\nOrg: {USER}\n## PENDING — component repair\n**Outcome (old):**\n  applied\n'
                            '### Nested evidence\nreceipt\n## PENDING — data seed\n**Outcome: applied.**\n')
        self.task.unlink()  # Match by username, not the org ID in a neighboring task.
        code, output = self.run_cli('pending', '--orgs-dir', str(self.folder.parent), '--org-id', ORG, '--username', USER)
        self.assertEqual(code, 0)
        self.assertEqual([json.loads(s)['state'] for s in output.splitlines()], ['unclear', 'unclear'])  # R7 F1: legacy never resolves.

    def test_fenced_examples_do_not_supply_outcomes_or_headers(self):
        self.data['items'][0]['attempts'] = ['A1']
        self.save(checkpoint(outcome=None) + '```text\n- **Outcome: applied.** example\n```\n')
        before = self.log.read_bytes()
        self.assertEqual(self.run_cli('resolve')[0], 0)
        self.assertEqual(before, self.log.read_bytes())
        self.assert_rule('checkpoint')
        self.task.write_text('````markdown\n' + self.task.read_text() + '\n````\n')
        self.assert_rule('block')

    def test_exit_codes_usage_unreadable_and_system_python_without_site(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            history.main(['pending', '--orgs-dir', str(self.root), '--org-id', 'bad'])
        self.assertEqual(raised.exception.code, 2)
        code, _ = self.run_cli('check', '--task', str(self.root / 'missing.md'))
        self.assertEqual(code, 4)
        completed = subprocess.run(['/usr/bin/python3', '-S', str(Path(history.__file__)), 'check', '--task', str(self.task)],
                                   text=True, capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        with patch.object(Path, 'read_bytes', side_effect=PermissionError):
            self.assertEqual(self.run_cli()[0], 4)

    def test_malformed_docs_url_is_a_finding_and_proof_claim_cannot_be_empty(self):
        self.story()
        self.data['items'][0]['grounding'][0]['ref'] = 'https://[invalid'
        self.save()
        self.assert_rule('grounding')
        self.story()
        self.data['story']['beats'][0]['claims'] = []
        self.save()
        self.assert_rule('story')

    def test_arch_wrapped_entry_and_oversize_arc(self):
        self.data['history']['architecture'] = 'created'
        self.save()
        arch = self.architecture()
        arch.write_text(arch.read_text() + '  continuation text\n')
        self.assert_rule('arch')
        self.architecture()
        arch.write_text(arch.read_text().replace('## Demo Flow / Narrative Arc\n', '## Demo Flow / Narrative Arc\n1. ' + 'x' * 321 + '\n'))
        self.assert_rule('arch')

    def test_reconcile_uses_timestamp_not_customer_suffix_and_ignores_nonlogs(self):
        self.architecture()
        for name in ('changes-2026-10-13-1200-z-other.md', 'changes-not-a-log.md'):
            (self.folder / name).write_text('Not newer.\n')
        self.assertEqual(self.run_cli('reconcile-plan', '--folder', str(self.folder)), (0, ''))

    def test_legacy_per_item_outcome_continuations_and_no_partial_match(self):
        for value in ('**\n  - I1: applied\n  - I2: blocked', '** APPLIED — receipt', 'APPLIED — deployed', '\n  already_satisfied'):
            self.assertEqual(history.checkpoint_state('## PENDING — component repair', 'PENDING — component repair', 'Outcome: ' + value), 'unclear')
        for value in ('PARTIALLY APPLIED', '**\n  - I1: applied\n  - I2: pending', 'not_applied'):
            self.assertEqual(history.checkpoint_state('## PENDING — component repair', 'PENDING — component repair', 'Outcome: ' + value), 'unclear')

    def test_reconciliation_rejects_unknown_or_wrongly_skipped_item(self):
        for text in ('### Unresolved Work\n- I99 — FAILED', '## What Was Skipped\n- I1 — SKIPPED'):
            self.save()
            old = text.split('\n')[0] + '\nNone.'
            self.log.write_text(self.log.read_text().replace(old, text))
            self.assert_rule('reconciliation')


    def pending_rows(self, username=None):
        args = ['pending', '--orgs-dir', str(self.folder.parent), '--org-id', ORG]
        if username: args += ['--username', username]
        code, out = self.run_cli(*args)
        self.assertEqual(code, 0, out)
        return [json.loads(line) for line in out.splitlines()]

    def test_r4_f1_outcome_never_crosses_blank_or_unindented_line(self):
        for tail in ('\napplied the object; flow failed', 'applied the object; flow failed'):
            self.log.write_text(f'Org: {ORG}\n## PENDING — component repair\n**Outcome**:\n' + tail + '\n')
            self.assertEqual(self.pending_rows()[0]['state'], 'unclear')

    def test_r4_f6_eleven_history_shapes_and_marker_boundaries(self):
        # Structural reconstructions only; no source customer text or names.
        bodies = [('- outcome: pending (in flight)\n- **Outcome: applied.** receipt', 'unclear')] * 5
        bodies += [('- outcome: pending', 'unclear'),
                   ('FINAL OUTCOME (attempt EX): applied', 'unclear'),
                   ('**Outcome (EX):**\n  - (a) applied\n  - (b) already_satisfied\n  - (c) applied\n  - Companion: NEW PermissionSet Example', 'unclear'),
                   ('**Outcome:** PARTIALLY APPLIED', 'unclear')]
        text = f'Org: {ORG}\n'
        for n, (body, _) in enumerate(bodies):
            title = f'### PENDING — component repair · attempt EX-{n} · 2026-10-13 12:00' if n < 6 else '## CHECKPOINT: PENDING - Component Repair (Attempt EX)'
            text += title + '\n' + body + '\n'
        text += '## PENDING — data seed\n- outcome: pending\n## CHECKPOINT: PENDING — Diagnostic Example\n**Outcome:** pending\n'
        self.log.write_text(text)
        self.assertEqual([r['state'] for r in self.pending_rows()], [state for _, state in bodies] + ['unclear', 'unclear'])
        for value in ('**Outcome:** APPLIED — receipt\n  Evidence: saved.json',
                      '**Outcome (EX):**\n  - **I1:** applied\n  - I2: blocked\n  Receipt: saved.json',
                      '- outcome: pending\n**Outcome:** applied'):
            self.log.write_text(f'Org: {ORG}\n## PENDING — component repair\n' + value + '\n')
            self.assertEqual(self.pending_rows()[0]['state'], 'unclear')
        self.log.write_text(f'Org: {ORG}\n## Pending questions\n## Not pending work\n')
        self.assertEqual(self.pending_rows(), [])

    def test_r4_f7_scout_pending_without_final_is_unresolved(self):
        for body in ('- outcome: pending\n', '- **Outcome / read-back:** pending\n', 'No marker\n'):
            self.save(checkpoint(outcome=None) + body)
            self.assertEqual(self.pending_rows()[0]['state'], 'unclear')

    def test_r4_f8_resolve_edits_only_owned_unfenced_status_lines(self):
        receipt = '```text\n- outcome: pending\n```\n'
        foreign = '#### PENDING — component repair · attempt FOREIGN · 2026-10-13 12:00\n- verification: pending\n'
        self.save(checkpoint() + receipt + foreign)
        self.assertEqual(self.run_cli('resolve')[0], 0)
        text = self.log.read_text()
        self.assertIn(receipt, text)
        self.assertIn(foreign, text)
        self.assertIn('### PENDING — component repair · attempt A1', text)
        self.assert_rule('checkpoint')  # Foreign checkpoint cannot disappear from the inventory.
        self.save(checkpoint() + '- **Outcome / read-back:** failed — rejected\n')
        before = self.log.read_bytes()
        self.run_cli('resolve')
        self.assertEqual(before, self.log.read_bytes())

    def test_r4_f9_pending_business_values_are_not_status_fields(self):
        self.save(checkpoint().replace('read-back receipt', 'Status__c is `Pending`; readback confirms three rows') +
                  '- Notes: Status: `Pending`\n- classification: new — Status: `Pending` is the intended value\n')
        self.run_cli('resolve')
        self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])
        for key in ('classification', 'preedit_snapshot', 'outcome'):
            self.save(checkpoint() + '- ' + key + ': pending\n')
            if key != 'outcome': self.run_cli('resolve')
            self.assert_rule('checkpoint')

    def test_r4_f10_disposition_matches_last_attempt_and_inventory(self):
        for disposition, attempts, body in [('applied', [], ''), ('failed', [], ''), ('unverified', [], ''),
                ('applied', ['A1'], checkpoint(outcome='failed')), ('already_satisfied', ['A1'], checkpoint()),
                ('blocked', ['A1'], checkpoint()), ('omitted', ['A1'], checkpoint()),
                ('applied', ['A1'], checkpoint() + checkpoint('LOST', outcome=None))]:
            with self.subTest(disposition=disposition, attempts=attempts, body=body):
                self.data = record()
                self.data['items'][0].update(disposition=disposition, attempts=attempts, reason='State left: unchanged; rollback: not needed')
                self.save(body)
                self.run_cli('resolve')
                self.assert_rule('checkpoint')
        self.data = record()
        self.data['items'][0]['attempts'] = ['A1', 'A2']
        self.save(checkpoint('A1', 'failed') + checkpoint('A2', 'applied'))
        self.run_cli('resolve')
        self.assertEqual(self.run_cli()[0], 0)

    def test_r4_f11_workspace_symlink_accepted_but_child_links_refused(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        for command in ('check', 'resolve'):
            code, out = self.run_cli(command, '--task', str(alias / 'orgs' / 'example' / self.task.name))
            self.assertEqual(code, 0, out)
        log = self.log.read_text()
        self.log.unlink()
        peer = self.root / 'peer.md'
        peer.write_text(log)
        self.log.symlink_to(peer)
        self.assertEqual(self.run_cli('resolve')[0], 4)

    def test_r4_f12_literal_template_and_plain_existing_classification(self):
        self.save(checkpoint() + '- Classification: existing\n')
        self.run_cli('resolve')
        self.log.write_text(self.log.read_text().replace('Direct Repairs\n', 'Direct Repairs (if any)\n'))
        self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])
        self.log.write_text(self.log.read_text().replace('## Existing Component Before-State and Direct Repairs (if any)', '## Absent'))
        self.assert_rule('log-section')

    def test_r4_f13_map_only_lints_current_decisions_and_changed_arc(self):
        self.data['history']['architecture'] = 'reconciled'
        self.save()
        arch = self.architecture('## Current Live State\nSE note ' + self.log.name + '\n')
        arch.write_text(arch.read_text().replace('## Demo Flow / Narrative Arc\n', '## Demo Flow / Narrative Arc\n1. ' + 'old ' * 100 + '\n'))
        self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])
        self.data['history']['arc_changed'] = True
        self.save()
        self.assert_rule('arch')
        self.data['history']['arc_changed'] = False
        self.save()
        arch = self.architecture()
        arch.write_text(arch.read_text().replace('Keep fields.', 'x' * 321).replace('`' + self.log.name + '`', '`' + self.log.stem + '`'))
        self.assert_rule('arch')
        for extra in ('### SE annotations\n' + 'retained ' * 3800 + '\n', '> SE banner ' + 'retained ' * 3800 + '\n'):
            arch = self.architecture()
            arch.write_text(arch.read_text().replace('## Decision Log\n', '## Decision Log\n' + extra))
            code, out = self.run_cli()
            self.assertEqual(code, 0, out)
            self.assertIn('arch: warning:', out)

    def test_r4_f14_pending_reports_bad_files_and_malformed_proposals(self):
        self.save(checkpoint(outcome=None))
        sibling = self.folder.parent / 'aaa-other'
        sibling.mkdir()
        (sibling / 'changes-identity.md').write_text('Org: other@example.test\n')
        (sibling / 'changes-bad.md').write_bytes(b'Other\n\xff')
        (sibling / 'changes-link.md').symlink_to(self.log)
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            rows = self.pending_rows()
        self.assertEqual([r['state'] for r in rows if r['file'] == str(self.log)], ['unclear'])
        self.assertIn('changes-bad.md', errors.getvalue())
        self.assertIn('changes-link.md', errors.getvalue())
        (self.folder / 'changes-bad.md').write_bytes(b'Example\n\xff')
        self.task.write_text('```scout-items\n{"history":{"decisions":"proposed"},}\n```\n')
        rows = self.pending_rows()
        self.assertEqual(sum(r['state'] == 'unclear' for r in rows), 3)

    def test_r4_f15_independent_mapping_oracle_and_valid_guard_pins(self):
        self.assertEqual(history.render(self.data), expected_render(self.data))
        self.assertEqual(self.run_cli()[0], 0)
        self.log.write_text(self.log.read_text() + '## Later notes\n')
        self.assert_rule('checkpoint')
        self.data['items'] = [item(disposition='failed')]
        self.data['items'][0]['reason'] = 'State left: unchanged'
        self.save()
        self.assert_rule('disposition')
        self.data = record()
        self.save()
        self.log.write_text(self.log.read_text().replace('Org:', 'Owner:'))
        self.assert_rule('log-header')
        self.data['items'] = [item(), item('I2')]
        self.data['items'][1]['attempts'] = ['A1']
        self.save()
        self.assert_rule('block')
        self.task.unlink()
        self.log.write_text(f'Org: {USER}.uat\n## PENDING — component repair\n')
        self.assertEqual(self.pending_rows(USER), [])
        self.data = record()
        self.data['history']['architecture'] = 'created'
        self.save()
        arch = self.architecture()
        arch.write_text(arch.read_text().replace('Target Org:', 'Owner:'))
        self.assert_rule('arch')

    def test_r4_f16_story_header_folder_crlf_seed_type_and_beat_edges(self):
        self.story()
        self.data['path'] = 'complete-brief'
        self.data['story']['source'] = 'invented'
        self.save()
        self.assert_rule('story')
        for old, new in [('Audit used: scoped (task record)', 'Audit used: none'),
                         ('Audit used: scoped (task record)', 'Audit used: TBD'),
                         ('Audit used:', 'Spec: old.md\nAudit used:')]:
            self.data = record()
            self.save()
            self.log.write_text(self.log.read_text().replace(old, new))
            self.assert_rule('log-header')
        self.assertEqual(self.run_cli('reconcile-plan', '--folder', str(self.log))[0], 4)
        self.architecture().write_text('Reconciled through: none # next: ' + self.log.name + '\n')
        self.assertEqual(len(self.run_cli('reconcile-plan', '--folder', str(self.folder))[1].splitlines()), 1)
        self.data = record()
        self.data['history']['architecture'] = 'created'
        self.save(checkpoint())
        arch = self.architecture()
        for p in (self.log, arch): p.write_bytes(p.read_bytes().replace(b'\n', b'\r\n'))
        self.run_cli('resolve')
        raw = self.log.read_bytes()
        self.assertEqual(raw.count(b'\n'), raw.count(b'\r\n'))
        self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])
        seed = self.folder / 'seed.py'
        seed.write_text('# synthetic\n')
        self.data['items'][0]['seed_asset'] = str(seed)
        self.save()
        self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])
        for kind in ('Page Layout', 'Lightning App', 'Path', 'Records', 'Picklist values'):
            self.data = record()
            self.data['items'][0]['type'] = kind
            self.save()
            self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])
        self.story()
        self.data['items'][0]['beat'] = 'B99'
        self.save()
        self.assert_rule('story')

    def test_r4_f17_reoffer_answers_suppress_only_the_named_prior_task(self):
        self.data['history'].update(decisions='proposed', proposed_entries=['Keep scope.'])
        self.save()
        prior = self.task.name
        self.task = self.folder / 'task-2026-10-13-1300-example.md'
        self.data = record()
        self.data['history']['reoffers'] = [{'task': prior, 'answer': 'skipped'}]
        self.save()
        self.assertFalse(any(r['state'] == 'proposed' for r in self.pending_rows()))

    def test_r4_f17_lowercase_docs_unavailable(self):
        self.story()
        self.data['items'][0]['grounding'] = [dict(source='ungrounded', ref='', assumption='Mechanism', verdict='docs unavailable: SE accepted')]
        self.save()
        code, out = self.run_cli()
        self.assertEqual(code, 0, out)
        self.assertIn('grounding: warning:', out)



    def test_r4_attack_mixed_nonfinal_continuations_and_stem_boundary(self):
        for word in ('INCOMPLETE', 'unknown', 'not applied'):
            self.log.write_text(f'Org: {ORG}\n## PENDING — component repair\n**Outcome:**\n  - I1: applied\n  - I2: {word}\n')
            with self.subTest(word=word):
                self.assertEqual(self.pending_rows()[0]['state'], 'unclear')
        self.data['history']['architecture'] = 'reconciled'
        self.save()
        arch = self.architecture()
        # A different log sharing this stem must not make an old entry current.
        arch.write_text(arch.read_text().replace('Keep fields.', 'x' * 321).replace('`' + self.log.name + '`', '`' + self.log.stem + '-later.md`'))
        self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])



    def test_r4_attack_map_banner_and_fenced_template_budget(self):
        self.data['history']['architecture'] = 'reconciled'
        self.save()
        self.architecture('Hand-kept banner: ' + 'retained ' * 3800 + '\n')
        code, out = self.run_cli()
        self.assertEqual(code, 0, out)
        self.assertIn('arch: warning:', out)
        arch = self.architecture()
        arch.write_text(arch.read_text().replace('## Decision Log\n', '## Decision Log\n```text\n' + 'template ' * 3800 + '\n```\n'))
        self.assert_rule('arch')


    def test_r5_f1_legacy_outcomes_include_nested_sections_only_until_peer(self):
        for body, state in (
            ('**Outcome:** applied\n### Read-back\n**Outcome:** pending\n', 'unclear'),
            ('### Verification\n**Outcome:** applied\n', 'unclear'),
            ('**Outcome:** applied\n## Later notes\n**Outcome:** pending\n', 'unclear'),
            ('**Outcome:** applied\n### Evidence\n```text\n**Outcome:** pending\n```\n', 'unclear'),
        ):
            with self.subTest(body=body):
                self.log.write_text(f'Org: {ORG}\n## PENDING — component repair\n' + body)
                self.assertEqual(self.pending_rows()[0]['state'], state)

    def test_r5_f2_markup_and_template_pending_fields(self):
        self.assertEqual(self.run_cli()[0], 0)
        for field in ('preedit_snapshot.status: `pending`', 'verification: **pending**',
                      '**First pre-edit artifact / source / members:** pending',
                      '**Pre-edit artifact / source:** _pending_',
                      '**Original Flow activation (Flow only):** pending'):
            with self.subTest(field=field):
                self.save()
                self.log.write_text(self.log.read_text() + '- ' + field + '\n')
                self.assertEqual(self.run_cli()[0], 0 if '`pending`' in field else 3)
        self.save(checkpoint().replace('outcome: pending', 'outcome: `pending`'))
        self.assertEqual(self.run_cli('resolve')[0], 0)
        self.assertIn('outcome: `applied`', self.log.read_text())
        self.assertEqual(self.run_cli()[0], 0)

    def test_r5_f3_component_classification_requires_before_state(self):
        for value in ('Report and ReportFolder: existing; saved.json',
                      'Report and ReportFolder: _existing_; saved.json',
                      '`CustomField:Example__c.Label__c`: **existing**; saved.json',
                      'Report: new; ReportFolder: existing; saved.json'):
            with self.subTest(value=value):
                self.save()
                self.log.write_text(self.log.read_text() + '- **Classification / source:** ' + value + '\n')
                self.assertEqual(self.run_cli()[0], 0)
                self.log.write_text(self.log.read_text().replace(
                    '## Existing Component Before-State and Direct Repairs\nPreserved.\n', ''))
                self.assert_rule('log-section')

    def test_r5_f4_created_map_owns_nested_and_non_template_content(self):
        self.data['history']['architecture'] = 'created'
        self.save()
        for extra in ('### Accepted decisions\n- **[2026-10-13]** — ' + 'decision ' * 3800 + f' (see `{self.log.name}`)\n',
                      '### Notes\n' + 'note ' * 3800 + '\n',
                      '> ' + 'note ' * 3800 + '\n'):
            with self.subTest(prefix=extra[:30]):
                arch = self.architecture()
                arch.write_text(arch.read_text() + extra)
                self.assert_rule('arch')
        arch = self.architecture()
        arch.write_text(arch.read_text().replace('## Demo Flow / Narrative Arc\n',
                         '## Demo Flow / Narrative Arc\n### Beats\n1. ' + 'x' * 321 + '\n'))
        self.assert_rule('arch')

    def test_r5_f4_reconcile_owns_every_current_log_citation(self):
        self.data['history']['architecture'] = 'reconciled'
        self.save()
        for prefix in ('### Accepted decisions\n', '## Current Live State\n', '> '):
            with self.subTest(prefix=prefix):
                arch = self.architecture()
                arch.write_text(arch.read_text() + prefix + f'- **[2026-10-13]** — {"x" * 321} (see `{self.log.name}`)\n')
                self.assert_rule('arch')
        arch = self.architecture('## SE notes\n' + 'retained ' * 3800 + '\n')
        code, out = self.run_cli()
        self.assertEqual(code, 0, out)
        self.assertIn('arch: warning:', out)

    def test_r5_f5_reconcile_stamp_is_only_unfenced_header(self):
        arch = self.architecture()
        for tail in ('```text\nReconciled through: changes-2099-01-01-0000-example.md\n```\n',
                     'Reconciled through: changes-2099-01-01-0000-example.md\n'):
            with self.subTest(tail=tail):
                arch.write_text('Reconciled through: none — created from discovery\n## SE notes\n' + tail)
                code, out = self.run_cli('reconcile-plan', '--folder', str(self.folder))
                self.assertEqual(code, 0, out)
                self.assertEqual([json.loads(line)['file'] for line in out.splitlines()], [str(self.log)])

    def test_r5_f6_docs_gated_known_type_requires_docs(self):
        self.data['items'][0]['category'] = 'docs-gated'
        self.save()
        out = self.assert_rule('grounding')
        self.assertEqual(len(out.splitlines()), 1, out)
        self.data['items'][0]['grounding'] = [dict(source='docs', ref='https://example.test/fields',
                                                  assumption='Field XML', verdict='supported')]
        self.save()
        self.assertEqual(self.run_cli()[0], 0)

    def test_r5_f6_already_satisfied_cannot_depend_on_failed_parent(self):
        self.data['items'] = [item(disposition='failed'), item('I2', 'already_satisfied')]
        self.save()
        self.assertEqual(self.run_cli()[0], 0)
        self.data['items'][1]['depends_on'] = ['I1']
        self.save()
        out = self.assert_rule('dependency')
        self.assertEqual(len(out.splitlines()), 1, out)

    def test_r5_f6_reoffer_answer_suppresses_only_named_task(self):
        self.data['history'].update(decisions='proposed', proposed_entries=['Keep scope.'])
        self.save()
        first = self.task.name
        self.task = self.folder / 'task-2026-10-13-1300-example.md'
        self.save()
        second = self.task.name
        self.task = self.folder / 'task-2026-10-13-1400-example.md'
        self.data = record()
        self.data['history']['reoffers'] = [{'task': first, 'answer': 'skipped'}]
        self.save()
        proposed = [r for r in self.pending_rows() if r['state'] == 'proposed']
        self.assertEqual([Path(r['file']).name for r in proposed], [second])

    def test_r5_f8_labelled_evidence_is_not_a_disposition(self):
        for tail, state in (('I1: receipt saved.json', 'unclear'), ('(a) Evidence: saved.json', 'unclear'),
                            ('I2: pending', 'unclear'), ('I2: PARTIALLY APPLIED', 'unclear'),
                            ('I2: not applied', 'unclear'), ('I2: omitted', 'unclear')):
            with self.subTest(tail=tail):
                self.log.write_text(f'Org: {ORG}\n## PENDING — component repair\n**Outcome:**\n  - I1: applied\n  - {tail}\n')
                self.assertEqual(self.pending_rows()[0]['state'], state)

    def test_r5_f9_historical_outcome_heading_resolves_but_check_requires_body(self):
        for outcome in ('applied', 'already_satisfied', 'failed', 'blocked', 'unverified', 'omitted'):
            with self.subTest(outcome=outcome):
                self.save(checkpoint(outcome=None, heading=outcome))
                self.assertEqual(self.pending_rows()[0]['state'], 'resolved')
                self.assert_rule('checkpoint')

    def test_r5_f10_seed_and_task_share_workspace_alias(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        seed = self.folder / 'seed.sh'
        seed.write_text('# synthetic\n')
        self.data['items'][0]['seed_asset'] = str(alias / 'orgs' / self.folder.name / seed.name)
        self.save()
        code, out = self.run_cli('check', '--task', str(alias / 'orgs' / self.folder.name / self.task.name))
        self.assertEqual(code, 0, out)
        seed.unlink()
        target = self.root / 'other.sh'
        target.write_text('# synthetic\n')
        seed.symlink_to(target)
        self.assertEqual(self.run_cli('check', '--task', str(alias / 'orgs' / self.folder.name / self.task.name))[0], 4)

    def test_r5_f11_task_symlink_loop_is_unreadable(self):
        loop = self.folder / 'task-loop.md'
        loop.symlink_to(loop.name)
        code, out = self.run_cli('check', '--task', str(loop))
        self.assertEqual(code, 4, out)
        self.assertIn(': read:', out)

    def test_r5_f12_failed_requires_both_nonempty_fields(self):
        self.data['items'] = [item(disposition='failed')]
        self.save()
        self.assertEqual(self.run_cli()[0], 0)
        for reason in ('State left: ; rollback: not needed', 'State left: unchanged; rollback: ;',
                       'State left: rollback: not needed', 'State left: ` `; rollback: not needed'):
            with self.subTest(reason=reason):
                self.data['items'][0]['reason'] = reason
                self.save()
                self.assert_rule('disposition')

    def test_r5_f13_task_file_symlink_never_rewrites_target_log(self):
        self.save(checkpoint())
        sibling = self.folder.parent / 'other'
        sibling.mkdir()
        alias = sibling / self.task.name
        alias.symlink_to(self.task)
        before = self.log.read_bytes()
        for command in ('resolve', 'check', 'render'):
            code, out = self.run_cli(command, '--task', str(alias))
            self.assertEqual(code, 4, out)
            self.assertEqual(self.log.read_bytes(), before)

    def test_r5_f14_already_satisfied_attempts_must_all_be_noops(self):
        self.data['items'][0].update(disposition='already_satisfied', attempts=['A1', 'A2'])
        self.save()
        self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])
        for earlier in ('applied', 'failed', 'unverified', 'blocked', 'omitted'):
            with self.subTest(earlier=earlier):
                self.save(checkpoint('A1', earlier, earlier).replace('outcome: pending', 'outcome: ' + earlier) +
                          checkpoint('A2', 'already_satisfied', 'already_satisfied').replace('outcome: pending', 'outcome: already_satisfied'))
                self.assert_rule('checkpoint')
        self.data['items'][0]['attempts'] = []
        self.save()
        self.assertEqual(self.run_cli()[0], 0)

    def test_r5_f15_unknown_folder_relevance_is_incomplete(self):
        self.task.unlink()
        self.log.write_bytes(f'Org: {ORG}\n'.encode() + b'\xff')
        code, out = self.run_cli('pending', '--orgs-dir', str(self.folder.parent), '--org-id', ORG)
        self.assertEqual(code, 3, out)
        row = json.loads(out)
        self.assertEqual(row['state'], 'incomplete')
        self.assertEqual(row['path'], str(self.folder))
        self.assertTrue(row['reason'])

    def test_r5_f15_symlink_folder_is_incomplete_without_following(self):
        self.save(checkpoint(outcome=None))
        moved = self.root / 'moved'
        self.folder.rename(moved)
        self.folder.symlink_to(moved, target_is_directory=True)
        before = {p.name: p.read_bytes() for p in moved.iterdir()}
        code, out = self.run_cli('pending', '--orgs-dir', str(self.folder.parent), '--org-id', ORG)
        self.assertEqual(code, 3, out)
        self.assertEqual(json.loads(out)['state'], 'incomplete')
        self.assertEqual(json.loads(out)['path'], str(self.folder))
        self.assertEqual(before, {p.name: p.read_bytes() for p in moved.iterdir()})

    def test_r5_f16_unknown_kinds_and_legacy_omitted_are_unclear(self):
        for title, outcome in (('PENDING — Diagnostic FlowTest', 'applied'),
                               ('PENDING — data seed', 'applied'),
                               ('CHECKPOINT: PENDING — Diagnostic FlowTest', 'applied'),
                               ('PENDING — component repair', 'omitted')):
            with self.subTest(title=title):
                self.log.write_text(f'Org: {ORG}\n## {title}\n**Outcome:** {outcome}\n')
                self.assertEqual(self.pending_rows()[0]['state'], 'unclear')

    def test_r5_f17_proposals_include_folder_and_answers_are_folder_scoped(self):
        self.data['history'].update(decisions='proposed', proposed_entries=['Keep scope.'])
        self.save()
        original_folder, original_task = self.folder, self.task
        self.folder = self.folder.parent / 'other'
        self.folder.mkdir()
        self.task = self.folder / 'task-2026-10-13-1300-example.md'
        self.data = record()
        self.data['history']['reoffers'] = [{'task': original_task.name, 'answer': 'skipped'}]
        self.save()
        proposed = [r for r in self.pending_rows() if r['state'] == 'proposed']
        self.assertEqual(len(proposed), 1)
        self.assertEqual(proposed[0]['file'], str(original_task))
        self.assertEqual(proposed[0]['folder'], str(original_folder))


    def test_r5_attack_labelled_unknown_status_cannot_hide_among_receipts(self):
        for tail, state in (('I2: waiting', 'unclear'), ('I2: in_progress', 'unclear'),
                            ('I2: deferred', 'unclear'), ('I1: evidence saved.json', 'unclear')):
            with self.subTest(tail=tail):
                self.log.write_text(f'Org: {ORG}\n## PENDING — component repair\n**Outcome:**\n  - I1: applied\n  - {tail}\n')
                self.assertEqual(self.pending_rows()[0]['state'], state)

    def test_r6_f3_component_repair_anywhere_in_pending_heading(self):
        self.log.write_text(f'Org: {ORG}\n## PENDING — data seed for component repair\n**Outcome:** applied\n')
        self.assertEqual(self.pending_rows()[0]['state'], 'unclear')

    def test_r5_attack_reconcile_header_ends_at_any_section_heading(self):
        for heading in ('### Examples', '# Other document'):
            with self.subTest(heading=heading):
                self.architecture().write_text('Reconciled through: none\n' + heading +
                    '\nReconciled through: changes-2099-01-01-0000-example.md\n')
                code, out = self.run_cli('reconcile-plan', '--folder', str(self.folder))
                self.assertEqual(code, 0, out)
                self.assertEqual(len(out.splitlines()), 1)

    def test_r5_attack_created_decisions_cannot_hide_without_current_citation(self):
        self.data['history']['architecture'] = 'created'
        self.save()
        arch = self.architecture()
        arch.write_text(arch.read_text() + '### Accepted decision\n' + 'x' * 321 + '\n')
        self.assert_rule('arch')

    def test_r5_attack_unlistable_folder_is_incomplete(self):
        iterdir = Path.iterdir
        def guarded(path):
            if path == self.folder:
                raise PermissionError('synthetic unreadable folder')
            return iterdir(path)
        with patch.object(Path, 'iterdir', guarded):
            code, out = self.run_cli('pending', '--orgs-dir', str(self.folder.parent), '--org-id', ORG)
        self.assertEqual(code, 3, out)
        self.assertEqual(json.loads(out)['state'], 'incomplete')
        self.assertEqual(json.loads(out)['path'], str(self.folder))


    def test_r5_attack_emphasized_pending_outcome_is_resolved(self):
        self.save(checkpoint().replace('outcome: pending', 'outcome: **_pending_**'))
        self.assertEqual(self.run_cli('resolve')[0], 0)
        self.assertIn('outcome: **_applied_**', self.log.read_text())
        self.assertEqual(self.run_cli()[0], 0)

    def test_r5_attack_crlf_cannot_supply_failed_state(self):
        self.data['items'] = [item(disposition='failed')]
        self.data['items'][0]['reason'] = 'State left: \r\nrollback: not needed'
        self.save()
        self.assert_rule('disposition')


    def test_r5_attack_created_last_decision_line_without_newline_is_capped(self):
        self.data['history']['architecture'] = 'created'
        self.save()
        arch = self.architecture()
        arch.write_text(arch.read_text() + '### Accepted decisions\n' + 'x' * 321)
        self.assert_rule('arch')


    def test_r5_attack_nested_pending_field_is_checked_but_not_rewritten(self):
        nested = '#### Read-back\n- verification: `pending`\n'
        self.save(checkpoint() + nested)
        self.assertEqual(self.run_cli('resolve')[0], 0)
        self.assertTrue(self.log.read_text().endswith(nested))
        self.assertEqual(self.run_cli()[0], 0)
        self.save()
        self.log.write_text(self.log.read_text() + '#### Read-back\n```text\n- verification: pending\n```\nBusiness Status is Pending.\n')
        self.assert_rule('checkpoint')


    def test_r6_f1_every_legacy_value_part_requires_positive_evidence(self):
        for body in ('applied\n  - I2: pending', '\n  - applied\n  - waiting',
                     'applied\n  unexplained prose', 'applied; I2: pending',
                     'applied and waiting', 'applied, blocked', 'applied\n  - I2: omitted'):
            with self.subTest(body=body):
                self.assertEqual(history.checkpoint_state('## PENDING — component repair', 'PENDING — component repair', 'Outcome: ' + body), 'unclear')
        for body in ('applied\n  - Receipt: saved.json', '\n  - I1: applied\n  - I2: blocked',
                     'APPLIED — receipt\n  Evidence: saved.json'):
            self.assertEqual(history.checkpoint_state('## PENDING — component repair', 'PENDING — component repair', 'Outcome: ' + body), 'unclear')

    def test_r6_f2_scout_discovery_requires_complete_agreement(self):
        title = checkpoint(outcome=None).splitlines()[0]
        for extra, expected in (('#### Read-back\n**Outcome:** pending', 'unclear'),
                                ('#### Read-back\n**Outcome:** failed', 'unclear'),
                                ('#### Read-back\n**Outcome:** applied', 'resolved'),
                                ('- outcome: pending', 'resolved')):
            self.log.write_text(f'Org: {ORG}\n{title}\n- **Outcome: applied.** receipt\n{extra}\n')
            self.assertEqual(self.pending_rows()[0]['state'], 'unclear', extra)
        self.log.write_text(f'Org: {ORG}\n{title}\n**Outcome:** applied\n')
        self.assertEqual(self.pending_rows()[0]['state'], 'unclear')

    def test_r6_f3_all_uppercase_pending_atx_candidates_are_reported(self):
        for title in (' ## PENDING — component repair', '   ## **PENDING** — component repair',
                      '## `PENDING` — COMPONENT REPAIR', '### Attempt 2 — PENDING — component repair',
                      '### PENDING: component repair, attempt 3', '## Checkpoint (PENDING) — component repair',
                      '## PENDING — unknown kind'):
            self.log.write_text(f'Org: {ORG}\n{title}\nNo outcome yet.\n')
            rows = self.pending_rows()
            self.assertEqual(len(rows), 1, title)
            self.assertEqual(rows[0]['state'], 'unclear')
        self.log.write_text(f'Org: {ORG}\n## Pending Approval\nNo checkpoint\n')
        self.assertEqual(self.pending_rows(), [])

    def test_r6_f4_status_fields_ignore_presentation_not_status(self):
        for bullet in ('', '- ', '* ', '+ ', '1. ', '2) '):
            for label in ('verification', '**Outcome (A1)**', '`FINAL OUTCOME (attempt A1)`',
                          '__Classification / source__', 'preedit_snapshot.status'):
                for value in ('pending', '**pending**', '`pending`', '__pending__', '~~pending~~', '<em>pending</em>'):
                    with self.subTest(bullet=bullet,label=label,value=value):
                        self.save()
                        self.log.write_text(self.log.read_text() + bullet + label + ': ' + value + '\n')
                        self.assertEqual(self.run_cli()[0], 0 if value == '`pending`' else 3)
        self.save()
        self.log.write_text(self.log.read_text() + '* Evidence: Status__c is `Pending`\n')
        self.assertEqual(self.run_cli()[0], 0)

    def test_r6_f5_only_marked_report_receipt_exposes_classification(self):
        self.save()
        body = ('<!-- scout-repair:report-a1 -->\n### applied\n'
                '- **Attempt / org / exact component:** report-a1; demo@example.test; Report:Example/Report\n'
                '- **Classification / source:** Report and ReportFolder: existing; saved.json\n'
                '- **Outcome / read-back:** applied; mutation=confirmed; acceptance=met; saved.json\n'
                '<!-- /scout-repair:report-a1 -->\n')
        base = self.log.read_text().replace('## Existing Component Before-State and Direct Repairs\nPreserved.\n', '')
        self.log.write_text(base + '```text\n' + body + '```\n')
        self.assert_rule('log-section')
        self.log.write_text(base + '```text\n' + body.replace('scout-repair:', 'example:') + '```\n')
        self.assertEqual(self.run_cli()[0], 0)

    def test_r6_f6_before_state_only_for_changed_existing_attempt(self):
        for outcome in ('already_satisfied', 'blocked', 'applied', 'failed', 'unverified'):
            with self.subTest(outcome=outcome):
                self.data['items'] = [item(disposition=outcome)]
                self.data['items'][0]['attempts'] = ['A1']
                self.save()
                self.log.write_text(self.log.read_text().replace(
                    '## Existing Component Before-State and Direct Repairs\nPreserved.\n', '') +
                    '* **Classification / source:** Report: existing; saved.json\n')
                if outcome in ('already_satisfied','blocked'):
                    self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])
                else:
                    self.assert_rule('log-section')

    def test_r6_f7_log_ownership_must_be_in_real_header(self):
        for heading in ('### Notes',' ## Notes','### **Notes**'):
            self.log.write_text('# Change Log — Example\n' + heading + '\n' +
                                f'Task record: {self.task.name}\n' + checkpoint())
            before = self.log.read_bytes()
            self.assertEqual(self.run_cli('resolve')[0], 4)
            self.assertEqual(self.log.read_bytes(), before)

    def test_r6_f8_checkpoint_inventory_covers_entire_log(self):
        self.log.write_text(self.log.read_text().replace('## Checkpoints\n', checkpoint('LOST',outcome=None)+'## Checkpoints\n'))
        self.assert_rule('checkpoint')
        self.data['items'] = [item(disposition='already_satisfied')]
        self.save()
        self.log.write_text(self.log.read_text() + '## **PENDING** — component repair\n')
        self.assert_rule('checkpoint')

    def test_r6_f9_arch_caps_and_continuations_follow_ownership(self):
        self.data['history']['architecture'] = 'created'
        self.save()
        arch = self.architecture()
        arch.write_text(arch.read_text() + '\n## Custom section\n' + 'x' * 321 + '\n')
        self.assert_rule('arch')
        self.data['history']['architecture'] = 'reconciled'
        self.save()
        arch = self.architecture()
        arch.write_text(arch.read_text() + f'## Beats\n- Show the beat (see `{self.log.name}`)\n')
        self.assertEqual(self.run_cli()[0], 0)  # No dated form outside Decision Log.
        arch.write_text(arch.read_text() + '  continuation\n')
        self.assert_rule('arch')

    def test_r6_f10_unrelated_identity_requires_authoritative_fields(self):
        self.task.unlink()
        self.log.write_bytes(f'Org: {ORG}\n'.encode() + b'\xff')
        note = self.folder / 'changes-note.md'
        other_id = ORG.replace('001', '002')
        for text in ('```text\nOrg: other@example.test\n```\n',
                     '## Examples\nOrg: other@example.test\n',
                     f'An unrelated example ID: {other_id}\n'):
            note.write_text(text)
            code, out = self.run_cli('pending','--orgs-dir',str(self.folder.parent),'--org-id',ORG)
            self.assertEqual(code, 3, out)
            self.assertEqual(json.loads(out)['state'], 'incomplete')
        note.write_text('# Change Log\nOrg: other@example.test\n')
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.run_cli('pending','--orgs-dir',str(self.folder.parent),'--org-id',ORG), (0,''))

    def test_r6_f11_header_allows_bom_and_leading_blank_lines(self):
        for prefix in ('\n',' \n','\ufeff','\ufeff\n\n'):
            arch = self.architecture()
            arch.write_text(prefix + arch.read_text())
            self.assertEqual(self.run_cli('reconcile-plan','--folder',str(self.folder)),(0,''))
        self.save(checkpoint())
        self.log.write_text('\ufeff\n' + self.log.read_text())
        self.assertEqual(self.run_cli('resolve')[0], 0)
        self.assertIn('### applied', self.log.read_text())

    def test_r6_f12_parent_loop_exercises_runtimeerror_mapping_on_python39(self):
        loop = self.root / 'loop'
        loop.symlink_to(loop.name)
        script = Path(history.__file__)
        for path in (loop/'child/task.md', loop/'child/orgs/example/task.md'):
            result = subprocess.run(['/usr/bin/python3','-S',str(script),'check','--task',str(path)],
                                    capture_output=True,text=True)
            self.assertEqual(result.returncode,4,result.stdout+result.stderr)
            self.assertIn('(RuntimeError)',result.stdout)

    def test_r6_f13_consolidated_before_state_status_is_validated(self):
        for field in ('- **First pre-edit artifact / source / members:** `pending`',
                      '* **Outcome (A1):** pending', '+ rollback: __pending__'):
            self.save()
            self.log.write_text(self.log.read_text().replace('Preserved.\n',field+'\n'))
            self.assertEqual(self.run_cli()[0], 0 if '`pending`' in field else 3)

    def test_r6_f14_blocked_checkpoint_records_no_write_flow(self):
        self.data['items'] = [item(disposition='blocked')]
        self.data['items'][0]['attempts'] = ['A1','A2']
        self.save()
        self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])
        self.log.write_text(self.log.read_text() + '- classification: unknown; retrieve failed\n')
        # Round-8 F1: the compound segment's failed conflicts with canonical blocked.
        self.assert_rule('checkpoint')
        for earlier in ('applied','failed','unverified','already_satisfied'):
            self.save(checkpoint('A1',earlier,earlier).replace('outcome: pending','outcome: '+earlier)+
                      checkpoint('A2','blocked','blocked').replace('outcome: pending','outcome: blocked'))
            self.assert_rule('checkpoint')

    def test_r6_f15_reject_orgs_alias_nested_task_and_folder_alias(self):
        workspace = self.root / 'other-workspace'
        workspace.mkdir()
        (workspace/'orgs').symlink_to(self.folder.parent,target_is_directory=True)
        self.save(checkpoint())
        before = self.log.read_bytes()
        self.assertEqual(self.run_cli('resolve','--task',str(workspace/'orgs/example'/self.task.name))[0],4)
        self.assertEqual(self.log.read_bytes(),before)
        nested = self.folder/'session'
        nested.mkdir()
        self.task = nested/self.task.name
        self.folder = nested
        self.save(checkpoint())
        before = self.log.read_bytes()
        self.assertEqual(self.run_cli('resolve')[0],4)
        self.assertEqual(self.log.read_bytes(),before)
        alias = nested.parent.parent/'alias-org'
        alias.symlink_to(nested.parent,target_is_directory=True)
        self.assertEqual(self.run_cli('reconcile-plan','--folder',str(alias))[0],4)


    def test_r6_attack_inline_markup_cannot_split_pending_tokens(self):
        self.log.write_text(f'Org: {ORG}\n## **PEN**DING — component **repair**\n**Outcome:** applied\n')
        self.assertEqual([r['state'] for r in self.pending_rows()], ['unclear'])
        for field in ('- verification: **pen**ding', '- outcome: pen`ding`', '> * verification: pending'):
            self.save()
            self.log.write_text(self.log.read_text() + field + '\n')
            self.assertEqual(self.run_cli()[0], 0 if 'pen`ding`' in field else 3)

    def test_r6_attack_pending_status_indented_value(self):
        for field in ('- verification:\n  **pending**', '- **Outcome (A1):**\n  - pending'):
            self.save()
            self.log.write_text(self.log.read_text() + field + '\n')
            self.assert_rule('checkpoint')

    def test_r6_attack_marked_receipt_pending_field_is_real_evidence(self):
        self.save()
        self.record_report_marker()
        receipt = '<!-- scout-repair:example -->\n- verification: `pending`\n<!-- /scout-repair:example -->\n'
        self.log.write_text(self.log.read_text() + '```text\n' + receipt + '```\n')
        self.assertEqual(self.run_cli()[0], 0)
        self.save()
        self.log.write_text(self.log.read_text() + '```text\n' + receipt.replace('scout-repair:', 'example:') + '```\n')
        self.assertEqual(self.run_cli()[0], 0)

    def test_r6_attack_created_cap_counts_trailing_spaces_but_ignores_fences(self):
        self.data['history']['architecture'] = 'created'
        self.save()
        arch = self.architecture()
        arch.write_text(arch.read_text() + '\n## Notes\nA note' + ' ' * 321 + '\n')
        self.assert_rule('arch')
        arch = self.architecture()
        arch.write_text(arch.read_text().replace('## Demo Flow / Narrative Arc\n', '## Demo Flow / Narrative Arc\n```text\n' + 'x' * 500 + '\n```\n'))
        self.assertEqual(self.run_cli()[0], 0, self.run_cli()[1])


if __name__ == '__main__':
    unittest.main()
