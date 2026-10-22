"""Build cards: one per finished task, shared only on the builder's yes, and a summary that carries counts only."""
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
import scout_card as card
import scout_history as history

PRIVATE = ('Acme Pharma', 'maple@example.test', '00D000000000001EAA', 'maple-acme', 'task-2026-11-03')


def item(identifier, kind, disposition='applied'):
    return dict(id=identifier, what='Build for Acme Pharma', type=kind, beat='-', category='autonomous',
                criterion='Visible to maple@example.test', readback='sf sobject describe --target-org maple@example.test',
                proves='KP1', depends_on=[], components=['CustomObject:Acme_Visit__c'],
                attempts=['A' + identifier[1:]] if disposition in ('applied', 'failed', 'unverified') else [],
                grounding=[dict(assumption='Object XML', source='skill', ref='object skill', verdict='authorable')],
                disposition=disposition, evidence='Read back in 00D000000000001EAA', visual_qa=False,
                reason='State left: unchanged; rollback: not needed' if disposition == 'failed' else '',
                seed_asset='')


def record(items):
    return dict(schema=1, path='complete-brief', change_log='changes-2026-11-03-1200-acme.md', story=None, items=items,
                history=dict(decisions='none', proposed_entries=[], lessons='none', architecture='unchanged'))


class ScoutCardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='scout-card-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.feedback = self.root / 'feedback'
        patcher = patch.dict(os.environ, {'SCOUT_FEEDBACK_DIR': str(self.feedback)})
        patcher.start()
        self.addCleanup(patcher.stop)
        moment = datetime.datetime(2026, 11, 3, 15, 20, tzinfo=datetime.timezone.utc)
        patcher = patch.object(card, 'now', return_value=moment)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.folder = self.root / 'workspace' / 'orgs' / 'maple-acme'
        self.folder.mkdir(parents=True)
        self.task = self.task_file('task-2026-11-03-1200-acme.md',
                                   [item('I1', 'CustomObject'), item('I2', 'Flow', 'failed'),
                                    item('I3', 'FlexiPage', 'already_satisfied'), item('I4', 'Data', 'omitted'),
                                    item('I5', 'CustomField')])

    def task_file(self, name, items):
        path = self.folder / name
        path.write_text('# Task for Acme Pharma\n\n```scout-items\n' + json.dumps(record(items)) + '\n```\n')
        return path

    def run_card(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            try:
                code = card.main(list(args))
            except SystemExit as exit_:
                code = exit_.code
        self.assertNotIn('Traceback', output.getvalue())
        return code, json.loads(output.getvalue()) if output.getvalue().strip() else {}

    def handover(self, task=None, *more):
        return self.run_card('handover', '--task', str(task or self.task), '--host', 'claude', *more)

    def cards(self):
        return sorted((self.feedback / 'cards').rglob('card-*.json'))

    def test_every_build_ends_with_its_card_as_it_would_be_posted_and_cards_off_stops_it(self):
        code, data = self.handover(None, '--logbook', '--products', '["Service"]')
        self.assertEqual(code, 0, data)
        self.assertEqual(data['card']['state'], 'offered')
        post, question = data['lines']
        self.assertEqual(post, 'Build card, as it would be posted: Scout build card: 5 task items (Data model 2, '
                               'Automation 1, Experience and UI 1, Data 1). Scout\'s checks: 2 applied, 1 already '
                               'there, 1 failed, 1 skipped. Products: Service. Built through a shared logbook. '
                               '(Scout %s on Claude Code)' % card.scout_version())
        self.assertIn('a Slack channel (name it', question)
        self.assertIn('`share`', question)
        self.assertIn('stays on this machine', question)
        [path] = self.cards()
        self.assertTrue(card.valid(json.loads(path.read_text())))
        self.assertEqual(self.handover()[1], {'lines': [], 'card': {'state': 'existing',
                                                                    'file': path.relative_to(self.feedback).as_posix()}})
        self.assertEqual(len(self.cards()), 1, 'reopening a task never offers a second card')
        text = path.read_text() + (self.feedback / 'index.json').read_text() + json.dumps(data)
        for private in PRIVATE + (str(self.task),):
            self.assertNotIn(private, text)
        self.assertEqual(self.run_card('cards', 'off'), (0, {'cards': 'off'}))
        other = self.task_file('task-2026-11-03-1300-other.md', [item('I1', 'ApexClass')])
        self.assertEqual(self.handover(other)[1], {'lines': [], 'card': None})
        self.assertEqual(len(self.cards()), 1)

    def test_a_saved_channel_is_named_and_only_a_real_channel_name_is_saved(self):
        for name in ('#Sales Team', 'https://example.test/archives/C123', '', '#' + 'x' * 81):
            self.assertEqual(self.run_card('channel', '--set', name)[0], 3, name)
        self.assertEqual(self.run_card('channel', '--set', 'demo-builders'), (0, {'channel': '#demo-builders'}))
        self.assertIn('Share it in #demo-builders?', self.handover()[1]['lines'][1])
        self.assertEqual(self.run_card('channel', '--clear'), (0, {'channel': None}))

    def test_a_bare_share_posts_exactly_the_preview_and_the_card_is_posted_once(self):
        self.run_card('channel', '--set', '#demo-builders')
        preview = self.handover()[1]['lines'][0].split('as it would be posted: ', 1)[1]
        code, data = self.run_card('share-text', '--task', str(self.task))
        self.assertEqual((code, data['text'], data['text_shown'], data['channel_shown']), (0, preview, True, True),
                         'saving and reloading the card never changes the text')
        code, data = self.run_card('posting', '--task', str(self.task), '--digest', data['digest'])
        self.assertEqual((code, data), (0, {'text': preview, 'channel': '#demo-builders'}))
        self.assertIn('may already be in #demo-builders', self.run_card('share-text', '--task', str(self.task))[1]['reason'])
        self.assertEqual(self.run_card('posting', '--task', str(self.task), '--digest', 'f' * 16)[0], 3)
        self.assertEqual(self.run_card('shared', '--task', str(self.task)), (0, {'state': 'shared'}))
        code, data = self.run_card('share-text', '--task', str(self.task))
        self.assertEqual(code, 3, 'one post per card')
        self.assertIn('shared already', data['reason'])

    def test_added_words_or_an_earlier_answer_need_the_text_shown_again(self):
        self.run_card('channel', '--set', '#demo-builders')
        self.handover()
        before = self.run_card('share-text', '--task', str(self.task))[1]['digest']
        code, data = self.run_card('answer', '--task', str(self.task), '--rating', 'good', '--time-kind', 'hours',
                                   '--hours', '3', '--comment', 'The Flow builder needed two tries; pages were quick.')
        self.assertEqual((code, data['state']), (0, 'answered'), data)
        self.assertIn('Time saved, my estimate: about 3 hours. How it went: good. In my words: '
                      '“The Flow builder needed two tries; pages were quick.”', data['text'])
        self.assertEqual(self.run_card('posting', '--task', str(self.task), '--digest', before)[0], 3,
                         'never a text the builder did not approve')
        for _ in range(2):  # fetching a preview proves nothing: an interrupted turn may never have shown it
            code, data = self.run_card('share-text', '--task', str(self.task))
            self.assertEqual((code, data['text_shown'], data['channel_shown']), (0, False, True))
        for private in PRIVATE:
            self.assertNotIn(private, data['text'])
        self.assertEqual(self.run_card('posting', '--task', str(self.task), '--digest', data['digest'])[1]['text'],
                         data['text'], 'shown and approved, then posted')
        self.run_card('channel', '--set', '#elsewhere')
        self.assertEqual(self.run_card('not-posted', '--task', str(self.task)), (0, {'state': 'answered'}))
        self.assertEqual(self.run_card('posting', '--task', str(self.task), '--digest', data['digest'])[0], 3,
                         'a new channel is shown and approved first')

    def test_a_post_whose_local_save_failed_is_never_sent_twice(self):
        self.run_card('channel', '--set', '#demo-builders')
        self.handover()
        self.run_card('posting', '--task', str(self.task), '--digest',
                      self.run_card('share-text', '--task', str(self.task))[1]['digest'])
        with patch.object(card, 'mutate', side_effect=card.Unreadable('No space left on device')):
            self.assertEqual(self.run_card('shared', '--task', str(self.task))[0], 4, 'the post went out; the save failed')
        code, data = self.run_card('share-text', '--task', str(self.task))
        self.assertEqual(code, 3, 'a later session sees the post may be out')
        self.assertIn('ask the builder to check', data['reason'])
        self.assertEqual(self.run_card('not-posted', '--task', str(self.task)), (0, {'state': 'offered'}))
        self.assertEqual(self.run_card('share-text', '--task', str(self.task))[0], 0)

    def test_answers_update_the_same_card_and_a_bare_history_answer_leaves_it_offered(self):
        self.handover()
        [path] = self.cards()
        self.assertEqual(json.loads(path.read_text())['state'], 'offered', 'no card answer: still offered')
        self.assertEqual(self.run_card('answer', '--task', str(self.task))[0], 3, 'an answer says something')
        self.assertEqual(self.run_card('answer', '--task', str(self.task), '--time-kind', 'hours')[0], 3)
        code, data = self.run_card('answer', '--task', str(self.task), '--time-kind', 'time_lost')
        self.assertEqual((code, data['state']), (0, 'answered'), 'a partial answer is fine')
        self.assertIn('It cost me time.', data['text'])
        self.assertEqual(self.run_card('answer', '--task', str(self.task), '--time-kind', 'none', '--hours', '1')[0], 3)
        self.assertEqual(len(self.cards()), 1)
        other = self.task_file('task-2026-11-03-1300-other.md', [item('I1', 'ApexClass')])
        self.assertEqual(self.run_card('answer', '--task', str(other), '--rating', 'ok')[0], 3, 'no card yet')

    def test_a_task_record_named_by_a_relative_or_missing_path_is_refused_with_its_reason(self):
        for args, reason in ((('handover', '--task', self.task.name, '--host', 'claude'), 'full path'),
                             (('handover', '--task', str(self.folder / 'task-2026-11-03-1300-missing.md'), '--host',
                               'claude'), 'no task record'),
                             (('answer', '--task', self.task.name, '--rating', 'good'), 'full path'),
                             (('share-text', '--task', self.task.name), 'full path')):
            code, data = self.run_card(*args)
            self.assertEqual(code, 3, args)
            self.assertIn(reason, data['reason'])
        self.assertEqual(self.cards(), [], 'no card from a wrong path')
        self.assertEqual(self.handover()[1]['card']['state'], 'offered', 'the full path works')

    def test_short_times_read_in_minutes_and_one_hour_in_the_singular(self):
        self.handover()
        for kind, hours, words in (('hours', '0.33', 'Time saved, my estimate: about 20 minutes.'),
                                   ('hours', '0.01', 'Time saved, my estimate: about 1 minute.'),
                                   ('hours', '0.999', 'Time saved, my estimate: about 1 hour.'),
                                   ('hours', '0.9917', 'Time saved, my estimate: about 1 hour.'),
                                   ('hours', '1', 'Time saved, my estimate: about 1 hour.'),
                                   ('hours', '2.5', 'Time saved, my estimate: about 2.5 hours.'),
                                   ('time_lost', '0.25', 'It cost me time, about 15 minutes.')):
            code, data = self.run_card('answer', '--task', str(self.task), '--time-kind', kind, '--hours', hours)
            self.assertEqual(code, 0, data)
            self.assertIn(words, data['text'])

    def test_comments_in_any_language_pass_and_obvious_identifiers_are_refused(self):
        self.handover()
        for comment in ('Ping maple@example.test', 'Broke on acme.my.salesforce.com', 'See 00D000000000001EAA',
                        'Record a0B5g00000XyZ12AAA failed', 'Hidden\u200bnote', 'Flip \u202eit'):
            code, data = self.run_card('answer', '--task', str(self.task), '--comment', comment)
            self.assertEqual(code, 3, comment)
            self.assertIn('rephrase', data['reason'])
        for comment in ('Persian: می\u200cخواهم',
                        'Team \U0001F468\u200d\U0001F469\u200d\U0001F467 loved it', 'Grüße, 合格'):
            self.assertEqual(self.run_card('answer', '--task', str(self.task), '--comment', comment)[0], 0, comment)

    def test_every_type_the_task_record_knows_has_a_category(self):
        for kind in sorted(history.KNOWN_TYPES | set(history.TYPE_ALIASES)):
            self.assertNotEqual(card.category(kind), 'Other', kind)
        for kind, expected in (('Flow', 'Automation'), ('ApexTrigger', 'Automation'), ('ApexClass', 'Code'),
                               ('LightningComponentBundle', 'Code'), ('GenAiPlannerBundle', 'AI and agents'),
                               ('GenAiPromptTemplate', 'AI and agents'), ('PermissionSetGroup', 'Security and access'),
                               ('Dashboard', 'Analytics'), ('Page Layout', 'Experience and UI'),
                               ('Custom Object', 'Data model'), ('EmailTemplate', 'Other')):
            self.assertEqual(card.category(kind), expected, kind)

    def test_an_interrupted_save_never_gives_a_task_a_second_card(self):
        original = card.write_atomic

        def disk_full_for_cards(path, value, *, exclusive=False):
            if exclusive:
                raise card.Unreadable('couldn\'t write %s: No space left on device' % path)
            return original(path, value, exclusive=exclusive)

        with patch.object(card, 'write_atomic', side_effect=disk_full_for_cards):
            self.assertEqual(self.handover()[0], 4)
        self.assertEqual(self.cards(), [])
        code, data = self.handover()
        self.assertEqual((code, data['card']['state']), (0, 'offered'), 'the next handover makes the card, once')
        [path] = self.cards()
        index = json.loads((self.feedback / 'index.json').read_text())
        self.assertEqual(list(index['tasks'].values()), [path.relative_to(self.feedback).as_posix()],
                         'the index keeps forward slashes on every platform')
        self.assertEqual(self.handover()[1]['card']['state'], 'existing')

    def test_malformed_files_are_kept_as_they_are(self):
        self.feedback.mkdir(parents=True, exist_ok=True)
        (self.feedback / 'index.json').write_text('{"schema": 1, "tasks": ')
        self.assertEqual(self.handover()[0], 4)
        self.assertEqual((self.feedback / 'index.json').read_text(), '{"schema": 1, "tasks": ')
        (self.feedback / 'index.json').unlink()
        self.handover()
        [path] = self.cards()
        path.write_text('{"schema": 1}')
        self.assertEqual(self.run_card('answer', '--task', str(self.task), '--rating', 'good')[0], 4)
        self.assertEqual(path.read_text(), '{"schema": 1}')
        (self.feedback / 'settings.json').write_text('{"schema": 7}')
        self.assertEqual(self.run_card('cards', 'off')[0], 4)
        self.assertEqual((self.feedback / 'settings.json').read_text(), '{"schema": 7}')

    def test_the_summary_counts_valid_cards_only_states_its_denominators_and_names_nothing(self):
        month = self.feedback / 'cards' / '2026-10'
        month.mkdir(parents=True)
        base = dict(schema=1, scout_version='2.5.0', host='claude', state='answered', rating='good',
                    categories={'Data model': 2, 'Automation': 1}, products=['Service'], logbook=False,
                    comment='Acme Pharma loved it, ask maple@example.test', previewed=None,
                    dispositions={'applied': 3, 'already_satisfied': 0, 'failed': 0, 'blocked': 0, 'unverified': 0,
                                  'omitted': 0})
        cards = [dict(base, time_saved={'kind': 'hours', 'hours': 3}, state='shared'),
                 dict(base, time_saved={'kind': 'hours', 'hours': 1.5}, host='codex', logbook=True),
                 dict(base, time_saved={'kind': 'unknown'}, rating='ok'),
                 dict(base, time_saved={'kind': 'time_lost', 'hours': 2}, rating='poor'),
                 dict(base, state='offered', rating=None, time_saved=None)]
        for number, value in enumerate(cards):
            value.update(card_id='c-%06x' % number, created_at='2026-10-%02dT10:00:00Z' % (number + 1))
            (month / ('card-202610%02d-1000-%06x.json' % (number + 1, number))).write_text(json.dumps(value))
        (month / 'card-20261020-1000-ffffff.json').write_text(json.dumps(dict(cards[0], host='Acme Pharma laptop')))
        (month / 'card-20261021-1000-eeeeee.json').write_text('{broken')
        code, data = self.run_card('summary')
        self.assertEqual(code, 0, data)
        self.assertEqual(data['month'], '2026-10', 'the default is last month')
        counts = data['counts']
        self.assertEqual((counts['cards'], counts['answered'], counts['shared'], counts['unanswered']), (5, 4, 1, 1))
        self.assertEqual((counts['hours_sum'], counts['hours_median'], counts['hours_answers']), (4.5, 2.25, 2))
        self.assertEqual(counts['time_answers'], {'hours': 2, 'unknown': 1, 'none': 0, 'time_lost': 1})
        self.assertEqual(counts['built'], {'Data model': 10, 'Automation': 5})
        self.assertEqual(counts['hosts'], {'claude': 4, 'codex': 1})
        self.assertEqual(sorted(data['invalid_cards']), ['card-20261020-1000-ffffff.json',
                                                         'card-20261021-1000-eeeeee.json'])
        self.assertIn('over 2 hour answers', data['text'])
        self.assertIn('Tasks through a shared logbook: 1 of 5.', data['text'])
        public = json.dumps({'text': data['text'], 'counts': counts})
        for private in PRIVATE + ('loved it', 'card-2026'):
            self.assertNotIn(private, public)
        self.assertEqual(self.run_card('summary', '--month', '2026-13')[0], 3)
        self.assertEqual(self.run_card('summary', '--month', '2026-09')[1]['counts']['cards'], 0)

    def test_a_file_an_editor_saves_meanwhile_is_never_overwritten(self):
        self.feedback.mkdir(parents=True)
        settings = self.feedback / 'settings.json'
        settings.write_text(json.dumps({'schema': 1, 'cards': 'on', 'channel': None}))
        original = card.read_json

        def an_editor_saves(path, empty):
            value = original(path, empty)
            if path == settings:
                settings.write_text(json.dumps({'schema': 1, 'cards': 'on', 'channel': '#theirs'}) + '\n')
            return value

        with patch.object(card, 'read_json', side_effect=an_editor_saves):
            code, data = self.run_card('cards', 'off')
        self.assertEqual(code, 4)
        self.assertIn('nothing was overwritten', data['reason'])
        self.assertIn('#theirs', settings.read_text())

    @unittest.skipIf(os.name == 'nt', 'checks POSIX permission bits, which Windows doesn\'t keep')
    def test_cards_live_in_private_folders_outside_the_workspace(self):
        self.handover()
        [path] = self.cards()
        self.assertFalse(str(path).startswith(str(self.root / 'workspace')))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)


if __name__ == '__main__':
    unittest.main()
