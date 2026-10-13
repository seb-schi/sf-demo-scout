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


def item(identifier='I1', disposition='applied'):
    return dict(id=identifier, what='Add label', type='CustomField', beat='-', category='autonomous',
                criterion='Label matches', readback='sf sobject describe --target-org demo@example.test',
                proves='KP3', depends_on=[], components=['CustomField:Example__c.Label__c'], attempts=[],
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
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.folder = self.root / 'orgs' / 'example'
        self.folder.mkdir(parents=True)
        self.task = self.folder / 'task-2026-10-13-1200-example.md'
        self.data = record()
        self.save()

    def save(self, checkpoints=''):
        self.task.write_text(f'# Task\nOrg: {USER} ({ORG})\n\n```scout-items\n' + json.dumps(self.data) + '\n```\n')
        self.log = self.folder / self.data['change_log']
        self.log.write_text(f'# Change Log — Example — 2026-10-13 1200\nOrg: {USER} ({ORG})\n'
            f'Task record: {self.task.name}\nAudit used: scoped (task record)\n' + history.render(self.data) +
            '\n'.join('## ' + s + '\nRecorded.\n' for s in history.LOG_SECTIONS if s not in
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
                self.assertIn('### ' + history.SECTIONS[section] + '\n- I1 — ' + label, rendered)
                skipped = rendered.split('## What Was Skipped\n')[1].split('\n## ')[0]
                self.assertEqual('- I1' in skipped, disposition == 'omitted')
        self.data['items'] = [item(), item('I2', 'blocked')]
        self.save()
        self.assertIn('UNRESOLVED', self.run_cli('render')[1])

    def test_block_missing_duplicate_malformed_and_schema(self):
        for text in ('no block', '```scout-items\n{}\n```\n' * 2,
                     '```scout-items\n{\n```', '```scout-items\n{"schema":1,"schema":1}\n```',
                     '```scout-items\nNaN\n```'):
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
        self.data['items'][0].update(disposition='omitted', reason='Docs-confirmed UI-only')
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
        for section in (*history.LOG_SECTIONS, *history.SECTIONS):
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
        for body in (checkpoint(outcome=None), checkpoint() + '- **Outcome: failed.** second claim\n'):
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
                        '\n'.join('## ' + s + '\nRecorded.\n' for s in history.ARCH_SECTIONS) +
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
        self.assertEqual(json.loads(output)['proposed_entries'], self.data['history']['proposed_entries'])

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
        self.assertEqual(states.count('unclear'), 1)
        self.assertEqual(states.count('resolved'), 5)
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
        self.data['items'][0]['attempts'] = []
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
        self.assertEqual([json.loads(s)['state'] for s in output.splitlines()], ['resolved', 'unclear'])

    def test_fenced_examples_do_not_supply_outcomes_or_headers(self):
        self.data['items'][0]['attempts'] = ['A1']
        self.save(checkpoint(outcome=None) + '```text\n- **Outcome: applied.** example\n```\n')
        self.assertEqual(self.run_cli('resolve')[0], 0)
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
        for value in ('**\n  - I1: applied\n  - I2: blocked', '** APPLIED — receipt', '\n  already_satisfied'):
            self.assertTrue(history.legacy_final(value), value)
        for value in ('PARTIALLY APPLIED', '**\n  - I1: applied\n  - I2: pending', 'not_applied'):
            self.assertFalse(history.legacy_final(value), value)

    def test_reconciliation_rejects_unknown_or_wrongly_skipped_item(self):
        for text in ('### Unresolved Work\n- I99 — FAILED', '## What Was Skipped\n- I1 — SKIPPED'):
            self.save()
            old = text.split('\n')[0] + '\nNone.'
            self.log.write_text(self.log.read_text().replace(old, text))
            self.assert_rule('reconciliation')


if __name__ == '__main__':
    unittest.main()
