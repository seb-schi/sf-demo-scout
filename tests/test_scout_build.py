"""W10 contracts: plan order, layers and readiness, job settlement and the write slot, beat verdicts, the
beat-aware Overall, write order, retries, per-type log sections and evidence references."""
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_scout_history as base
from test_scout_history import history, item

BUILD = history.BUILD
GATE_SHA = hashlib.sha256(BUILD.GATE.read_bytes()).hexdigest()
DEPLOY = '0AfKa00000iDxZZKAS'
BULK = '750Ka00000iDxZZKAS'
DOCS = dict(assumption='Documented behavior', source='docs', ref='https://developer.salesforce.com/docs/w10-fixture', verdict='supported')


def items(*specs):
    """specs: (id, disposition, depends_on)"""
    result = []
    for identifier, disposition, depends in specs:
        value = item(identifier, disposition)
        value['depends_on'] = list(depends)
        result.append(value)
    return result


def story(*beats):
    return dict(residual='One list', audience='Manager', kp1='Lost requests', kp2='gap', kp3='One list',
                source='se-confirmed', beats=list(beats))


def beat(identifier='B1', claims=(), flips=(), proof=True, verification=None):
    value = dict(id=identifier, name='Overdue list', persona='Manager', pain='Lost', climax='Two rows',
                 claims=[dict(text=text, item=owner, **({'result': result} if result else {})) for text, owner, result in claims],
                 proof_moment=proof)
    if flips:
        value['flips'] = list(flips)
    if verification:
        value['verification'] = dict(verdict=verification, evidence='own read-back')
    return value


def complex_story(data, verdict='verified'):
    """Make the task complex with one proof beat over I1, recording `verdict` (an oracle, not the code's verdict)."""
    data['complex'] = True
    data['items'][0]['beat'] = 'B1'
    data['story'] = story(beat('B1', claims=[('Shows the flag', 'I1', 'passed')], verification=verdict))


def cp(attempt, outcome='applied', body='', at='2026-10-13 12:00'):
    """A settled checkpoint with its own outcome heading and line, plus extra body lines."""
    return '### %s — component repair · attempt %s · %s\n- outcome: %s\n- **Outcome: %s.** read-back receipt\n%s' % (
        outcome, attempt, at, outcome, outcome, body)


def job(reference, status=None, launched=None, settled=None):
    fields = [('status', status), ('launched', launched), ('settled', settled)]
    return '- job: ' + reference + ''.join('; %s: %s' % (k, v) for k, v in fields if v) + '\n'


LIVE = job('agent publish', 'Active', '2026-10-13T12:00:00', '2026-10-13T12:02:00')


class Harness(unittest.TestCase):
    """The history suite's fixture, without re-running its tests."""
    setUp = base.ScoutHistoryTests.setUp
    run_cli = base.ScoutHistoryTests.run_cli
    assert_rule = base.ScoutHistoryTests.assert_rule

    def save(self, checkpoints=None):
        """The history suite's save. R2-F6 changed it: an applied or already_satisfied Agentforce item's default
        checkpoint records its publish settling Active, as build.md's job line requires, so the agent is live."""
        if checkpoints is None:
            checkpoints = ''.join(
                base.checkpoint(a, i['disposition'], i['disposition']).replace('outcome: pending', 'outcome: ' + i['disposition'])
                + (LIVE if BUILD.family(i['type']) == 'agentforce' and i['disposition'] in BUILD.SETTLED_OK else '')
                for i in self.data['items'] for a in i['attempts'] if i['disposition'])
        base.ScoutHistoryTests.save(self, checkpoints)

    def add_sections(self, *names):
        """Insert per-type log sections ahead of the final Checkpoints section."""
        text = self.log.read_text()
        block = ''.join('## %s\nRecorded.\n' % name for name in names)
        self.log.write_text(text.replace('## Checkpoints\n', block + '## Checkpoints\n', 1) if '## Checkpoints\n' in text else text + block)

    def passes(self, command='check'):
        code, output = self.run_cli(command)
        self.assertEqual(code, 0, output)
        return output


class PlanTests(Harness):
    def plan(self):
        code, output = self.run_cli('plan')
        return code, (json.loads(output) if code == 0 else output)

    def test_order_and_layers_follow_dependencies(self):
        self.data['items'] = items(('I1', None, ()), ('I2', None, ('I1',)), ('I3', None, ('I1',)), ('I4', None, ('I2', 'I3')))
        self.save('')
        code, result = self.plan()
        self.assertEqual(code, 0, result)
        self.assertEqual(result['order'], ['I1', 'I2', 'I3', 'I4'])
        self.assertEqual(result['layers'], [['I1'], ['I2', 'I3'], ['I4']])
        self.assertEqual(result['next'], ['I1', 'I2', 'I3', 'I4'])

    def test_cycle_and_unknown_dependency_exit_3(self):
        self.data['items'] = items(('I1', None, ('I2',)), ('I2', None, ('I1',)))
        self.save('')
        code, output = self.plan()
        self.assertEqual(code, 3)
        self.assertIn('dependency cycle', output)
        self.data['items'] = items(('I1', None, ('I9',)))
        self.save('')
        code, output = self.plan()
        self.assertEqual(code, 3)
        self.assertIn('unknown dependency I9', output)

    def test_unsatisfied_prerequisites_block_dependents_transitively(self):
        for state in ('failed', 'blocked', 'unverified', 'omitted'):
            with self.subTest(state=state):
                self.data['items'] = items(('I1', state, ()), ('I2', None, ('I1',)), ('I3', None, ('I2',)), ('I4', None, ()))
                self.data['items'][0]['reason'] = 'State left: unchanged; rollback: not needed' if state == 'failed' else 'withdrawn by SE'
                self.save('')
                code, result = self.plan()
                self.assertEqual(code, 0, result)
                self.assertEqual(result['blocked'], {'I2': ['I1'], 'I3': ['I2']})
                self.assertEqual(result['next'], ['I4'])

    def test_resume_order_skips_settled_items(self):
        self.data['items'] = items(('I1', 'applied', ()), ('I2', None, ('I1',)))
        self.save()
        code, result = self.plan()
        self.assertEqual(result['next'], ['I2'])
        self.assertEqual(result['blocked'], {})

    def test_ready_needs_settled_prerequisites_and_a_free_slot(self):
        """C1: `ready` is what may be written now; `next` stays the unsettled remainder."""
        self.data['items'] = items(('I1', None, ()), ('I2', None, ('I1',)), ('I3', None, ('I2',)))
        self.save('')
        code, result = self.plan()
        self.assertEqual((result['ready'], result['open_jobs'], result['next']), (['I1'], [], ['I1', 'I2', 'I3']))
        self.data['items'][0].update(disposition='applied', attempts=['A1'])
        self.save(cp('A1', body=job(DEPLOY, 'Succeeded', '2026-10-13T12:00:05', '2026-10-13T12:04:10')))
        self.assertEqual(self.plan()[1]['ready'], ['I2'])
        self.data['items'][1]['attempts'] = ['A2']  # in flight: reconcile it, never replay it
        self.save(cp('A1', body=job(DEPLOY, 'Succeeded', '2026-10-13T12:00:05', '2026-10-13T12:04:10')) +
                  base.checkpoint('A2', None) + '- launched: 2026-10-13T12:05:00\n')
        self.assertEqual(self.plan()[1]['ready'], [])

    def test_an_open_job_empties_ready_and_is_listed(self):
        self.data['items'] = items(('I1', 'unverified', ()), ('I2', None, ()))
        self.data['items'][0]['reason'] = 'Queued job must settle first'
        self.save(cp('A1', 'unverified', job(DEPLOY, 'Queued', '2026-10-13T12:00:05')))
        code, result = self.plan()
        self.assertEqual(code, 0, result)
        self.assertEqual(result['open_jobs'], [{'attempt': 'A1', 'item': 'I1', 'job': DEPLOY}])
        self.assertEqual((result['ready'], result['next']), ([], ['I2']))


class BeatTests(Harness):
    def complex_record(self, claims=(('Two rows', 'I1', 'passed'),), flips=(), rehearsals=(), verification='verified', disposition='applied', visual_qa=False):
        self.data['complex'] = True
        self.data['items'] = items(('I1', disposition, ()))
        self.data['items'][0].update(beat='B1', visual_qa=visual_qa, grounding=[dict(
            assumption='List view filter', source='docs', ref='https://help.salesforce.com/s/articleView?id=x', verdict='supported')])
        if disposition == 'failed':
            self.data['items'][0]['reason'] = 'State left: unchanged; rollback: not needed'
        if disposition in ('blocked', 'omitted'):
            self.data['items'][0]['reason'] = 'withdrawn by SE'
        self.data['story'] = story(beat('B1', claims, flips, verification=verification))
        self.data['rehearsals'] = [dict(flip=f, result=r, evidence='rolled back; read-back clean') for f, r in rehearsals]
        self.save()

    def verdict(self):
        record = history.task_record(self.task)
        return BUILD.beat_verdict(record, record['story']['beats'][0])[0]

    def test_verdict_table_is_total_and_ordered(self):
        # F6 changed this table's fixture: each row now records the beat's own evidence, since a beat without it is unverified.
        cases = [
            (dict(), 'verified'),
            (dict(flips=('FL1',), rehearsals=(('FL1', 'passed'),)), 'verified'),
            (dict(visual_qa=True), 'visual_qa'),
            (dict(flips=('FL1',), rehearsals=(('FL1', 'not_rehearsable'),)), 'visual_qa'),
            (dict(claims=(('Two rows', 'I1', None),)), 'unverified'),
            (dict(flips=('FL1',)), 'unverified'),
            (dict(disposition='failed'), 'unverified'),
            (dict(disposition='blocked'), 'unverified'),
            (dict(disposition='omitted'), 'unverified'),
            (dict(claims=(('Two rows', 'I1', 'failed'),)), 'failed'),
            (dict(flips=('FL1',), rehearsals=(('FL1', 'failed'),), visual_qa=True), 'failed'),
            (dict(claims=(('Two rows', 'I1', 'failed'), ('Badge', 'I1', None)), visual_qa=True), 'failed'),
            (dict(claims=(('Two rows', 'I1', None),), visual_qa=True), 'unverified'),
            (dict(flips=('FL1',), rehearsals=(('FL1', 'failed'), ('FL1', 'passed'))), 'verified'),
            (dict(claims=(('Two rows', 'I1', 'dropped'),)), 'unverified'),
            (dict(verification=None), 'unverified'),
        ]
        for kwargs, expected in cases:
            with self.subTest(kwargs=kwargs):
                self.complex_record(**kwargs)
                self.assertEqual(self.verdict(), expected)

    def test_empty_evidence_never_verifies(self):
        """F6: a passed rehearsal and a verified beat both need evidence."""
        self.complex_record(flips=('FL1',), rehearsals=(('FL1', 'passed'),))
        self.data['rehearsals'][0]['evidence'] = ' '
        self.save()
        self.assertEqual(self.verdict(), 'unverified')
        self.assertIn('B1 records verified but its evidence gives unverified', self.assert_rule('beat'))
        self.assertIn('Beats: B1 unverified', self.run_cli('render')[1])
        self.complex_record()
        self.data['story']['beats'][0]['verification']['evidence'] = ''
        self.save()
        self.assertEqual(self.verdict(), 'unverified')
        self.assertIn('Overall: UNRESOLVED', self.run_cli('render')[1])

    def test_dropped_optional_claim_is_history(self):
        """F9 and C6: `"required":false` plus `dropped` creates no obligation, even in a proof beat."""
        self.complex_record(claims=(('Two rows', 'I1', 'passed'), ('Extra badge', 'I2', 'dropped')))
        self.data['items'] += items(('I2', 'omitted', ()))
        self.data['items'][1].update(reason='SE cut the optional badge', grounding=[dict(DOCS)])  # W3: every proof-beat claim's item needs Docs
        self.data['story']['beats'][0]['claims'][1]['required'] = False
        self.save()
        self.assertEqual(self.verdict(), 'verified')
        self.passes()
        self.data['story']['beats'][0]['claims'][1]['required'] = True
        self.save()
        self.assertEqual(self.verdict(), 'unverified')
        self.assertIn('B1 drops a required proof-moment claim', self.assert_rule('story'))

    def test_dropping_a_required_claim_is_a_finding_in_any_beat(self):
        self.complex_record(claims=(('Two rows', 'I1', 'passed'), ('Badge', 'I1', 'dropped')), verification='unverified')
        self.data['story']['beats'][0]['proof_moment'] = False
        self.save()
        self.assertIn('B1 drops a required claim', self.assert_rule('story'))

    def test_overall_is_beat_aware_only_for_complex_tasks(self):
        self.complex_record(claims=(('Two rows', 'I1', None),), verification='unverified')
        self.assertEqual(history.overall(history.task_record(self.task)), 'UNRESOLVED')
        self.complex_record(visual_qa=False, flips=('FL1',), rehearsals=(('FL1', 'not_rehearsable'),), verification='visual_qa')
        record = history.task_record(self.task)
        self.assertEqual(history.overall(record), 'FINISHED_WITH_EXCEPTIONS')
        self.assertIn('Beats: B1 visual_qa', history.render(record))
        record['complex'] = False
        self.assertEqual(history.overall(record), 'FULLY_VERIFIED')
        self.assertNotIn('Beats:', history.render(record))

    def test_render_and_check_share_one_verdict(self):
        """F8: a dropped required proof claim, or a complex task with no story, never renders clean."""
        self.complex_record(claims=(('Two rows', 'I1', 'dropped'),))
        rendered = self.run_cli('render')[1]
        self.assertIn('Overall: UNRESOLVED', rendered)
        self.assertIn('Beats: B1 unverified', rendered)
        output = self.assert_rule('story')
        self.assertIn('overall: expected UNRESOLVED', output)
        self.assertIn('B1 records verified but its evidence gives unverified', output)
        self.complex_record()
        self.data['story'] = None
        self.save()
        rendered = self.run_cli('render')[1]
        self.assertIn('Overall: UNRESOLVED', rendered)
        self.assertIn('Beats: none recorded', rendered)
        self.assertIn('a complex task needs story beats', self.assert_rule('story'))

    def test_check_compares_recorded_and_computed_verdicts(self):
        self.complex_record(verification='verified')
        self.passes()
        self.complex_record(claims=(('Two rows', 'I1', None),), verification='verified')
        self.assertIn('B1 records verified but its evidence gives unverified', self.assert_rule('beat'))
        self.complex_record(verification=None)
        self.assertIn('B1 has no recorded verification', self.assert_rule('beat'))

    def test_complex_task_needs_beats_and_keeps_proof_claims(self):
        self.complex_record()
        self.data['story'] = None
        self.save()
        self.assertIn('a complex task needs story beats', self.assert_rule('story'))
        self.complex_record(claims=(('Two rows', 'I1', 'dropped'),), verification='verified')
        self.assertIn('B1 drops a required proof-moment claim', self.assert_rule('story'))

    def test_complexity_is_derived_never_trusted(self):
        """F7: three or more items, or any gated or Docs-gated type, make a task complex whatever `complex` says."""
        self.data['items'] = items(('I1', 'applied', ()), ('I2', 'applied', ()))
        self.save()
        self.passes()  # two autonomous items stay simple
        self.data['items'] += items(('I3', 'applied', ()))
        self.save()
        self.assertIn('a complex task needs story beats', self.assert_rule('story'))
        self.assertIn('Overall: UNRESOLVED', self.run_cli('render')[1])
        self.data['complex'] = False
        self.save()
        self.assertIn('"complex":false, but this task has three or more items or a gated or Docs-gated type', self.assert_rule('story'))
        for spelling in ('RecordTriggeredFlow', 'Apex Class', 'GenAiPlannerBundle', 'LightningComponentBundle', 'Dashboard'):
            with self.subTest(spelling=spelling):
                self.data = base.record()
                self.data['items'][0].update(type=spelling, category='autonomous', grounding=[dict(DOCS)])
                self.save()
                self.assertIn('a complex task needs story beats', self.assert_rule('story'))

    def test_schema_rejects_malformed_w10_fields(self):
        bad = [
            lambda d: d['story']['beats'][0].update(flips=['F1']),
            lambda d: d['story']['beats'][0].update(flips=['FL1', 'FL1']),
            lambda d: d.update(rehearsals=[dict(flip='FL9', result='passed', evidence='x')]),
            lambda d: d['story']['beats'][0]['claims'][0].update(result='maybe'),
            lambda d: d['story']['beats'][0]['claims'][0].update(required='no'),
            lambda d: d['story']['beats'][0].update(verification=dict(verdict='ok', evidence='x')),
            lambda d: d.update(complex='yes'),
            lambda d: d['items'][0].update(agent_version=''),
            lambda d: d['items'][0]['grounding'][0].update(attempt=''),
        ]
        flow = dict(flow_api_name='Overdue_Flag', mode='flow_test_required', required_tests=['T'], version=3)
        for key, value in (('version', True), ('version', 0), ('version', '3'), ('active_version', 2.0),
                           ('required_tests', ['T', 'T']), ('required_tests', ['']), ('unsupported_reason', 7)):
            bad.append(lambda d, key=key, value=value: d['items'][0].update(flow_validation=dict(flow, **{key: value})))
        bad.append(lambda d: d['items'][0].update(flow_validation=dict(flow, mode='unsupported', unsupported_reason='screen flow')))
        for mutate in bad:
            with self.subTest(mutate=mutate):
                self.complex_record(flips=('FL1',), rehearsals=(('FL1', 'passed'),))
                mutate(self.data)
                self.save()
                self.assert_rule('block')


class WriteOrderTests(Harness):
    def test_attempt_before_prerequisite_settles_is_a_plan_finding(self):
        self.data['items'] = items(('I1', 'applied', ()), ('I2', 'applied', ('I1',)))
        self.save(base.checkpoint('A2', 'applied', 'applied').replace('outcome: pending', 'outcome: applied') +
                  base.checkpoint('A1', 'applied', 'applied').replace('outcome: pending', 'outcome: applied'))
        self.assertIn('I2 was attempted before its prerequisite I1 settled', self.assert_rule('plan'))

    def test_attempt_with_unsatisfied_prerequisite_is_a_plan_finding(self):
        self.data['items'] = items(('I1', 'omitted', ()), ('I2', 'failed', ('I1',)))
        self.data['items'][0]['reason'] = 'withdrawn by SE'
        self.save()
        self.assertIn('I2 was attempted while its prerequisite I1 is omitted', self.assert_rule('plan'))

    def test_omitted_prerequisite_fails_the_dependency_rule(self):
        self.data['items'] = items(('I1', 'omitted', ()), ('I2', 'applied', ('I1',)))
        self.data['items'][0]['reason'] = 'withdrawn by SE'
        self.save()
        self.assertIn('I2 depends on unresolved I1', self.assert_rule('dependency'))

    def test_order_compares_with_the_first_settling_attempt(self):
        """F4: a later approved amendment to a prerequisite does not reorder its settled dependents."""
        self.data['items'] = items(('I1', 'applied', ()), ('I2', 'applied', ('I1',)))
        self.data['items'][0]['attempts'] = ['A1', 'A3']
        self.save(cp('A1') + cp('A2') + cp('A3'))
        self.passes()
        self.save(cp('A1', 'failed') + cp('A2') + cp('A3'))  # I1 first settled in A3, after A2
        self.assertIn('I2 was attempted before its prerequisite I1 settled', self.assert_rule('plan'))


class EvidenceTests(Harness):
    def flow(self, mode='flow_test_required', tests=('Overdue_Flip_Test',), evidence=None, visual_qa=False):
        self.data['items'] = items(('I1', 'applied', ()))
        flow_item = self.data['items'][0]
        flow_item.update(type='Flow', category='gated', visual_qa=visual_qa,
                         flow_validation=dict(flow_api_name='Overdue_Flag', mode=mode, required_tests=list(tests), version=3),
                         grounding=[dict(assumption='Flow XML', source='docs', ref='https://developer.salesforce.com/docs/x', verdict='supported')])
        if mode == 'unsupported':
            flow_item['flow_validation']['unsupported_reason'] = 'no FlowTest path for screen flows'
        elif not visual_qa:
            flow_item['flow_validation']['active_version'] = 3
        if evidence is not None:
            (self.folder / 'flow-evidence.json').write_text(json.dumps(evidence))
            flow_item['evidence_ref'] = 'flow-evidence.json'
        complex_story(self.data, 'visual_qa' if visual_qa else 'verified')
        self.save()
        self.add_sections('Flows Deployed (if any)', 'Execution Order Check')

    def row(self, **changes):
        return dict(dict(test='Overdue_Flip_Test', outcome='Pass', flow_api_name='Overdue_Flag', version=3, org_id=base.ORG), **changes)

    def test_flow_needs_frozen_validation_and_passing_required_tests(self):
        # C2 changed this fixture: a passing row now carries the bound org, and the item its active version.
        self.flow(evidence={'flow_tests': [self.row()]})
        self.passes()
        for evidence, message in (({'flow_tests': []}, 'has no result'),
                                  ({'flow_tests': [self.row(version=2)]}, 'frozen flow and version'),
                                  ({'flow_tests': [self.row(outcome='Fail')]}, 'frozen flow and version'),
                                  ({'flow_tests': [self.row(), self.row(outcome='Fail')]}, 'has 2 rows')):
            with self.subTest(message=message):
                self.flow(evidence=evidence)
                self.assertIn(message, self.assert_rule('evidence-ref'))
        self.flow()
        self.assertIn('evidence_ref file missing', self.assert_rule('evidence-ref'))
        self.data['items'][0].pop('flow_validation')
        self.save()
        self.add_sections('Flows Deployed (if any)', 'Execution Order Check')
        self.assertIn('records no frozen flow_validation', self.assert_rule('evidence-ref'))

    def test_flow_version_is_a_positive_integer_compared_strictly(self):
        """F10: never absent, never a bool, in flow_validation and in every test row."""
        self.flow(evidence={'flow_tests': [self.row()]})
        self.data['items'][0]['flow_validation'].pop('version')
        self.save()
        self.add_sections('Flows Deployed (if any)', 'Execution Order Check')
        self.assertIn('records no positive integer version', self.assert_rule('evidence-ref'))
        for version in (True, None, '3', 3.0):
            with self.subTest(version=version):
                row = self.row(version=version) if version is not None else {k: v for k, v in self.row().items() if k != 'version'}
                self.flow(evidence={'flow_tests': [row]})
                self.assertIn('frozen flow and version', self.assert_rule('evidence-ref'))

    def test_flow_evidence_carries_org_terminal_outcome_and_active_version(self):
        """C2: test rows name the bound org and a terminal outcome; activation reads back the tested version."""
        for row, message in ((self.row(org_id='00D000000000999EAA'), 'not the bound org'),
                             ({k: v for k, v in self.row().items() if k != 'org_id'}, 'not the bound org'),
                             (self.row(outcome='Pending'), 'has no terminal outcome'),
                             (self.row(outcome='pass'), 'has no terminal outcome')):
            with self.subTest(message=message, row=row):
                self.flow(evidence={'flow_tests': [row]})
                self.assertIn(message, self.assert_rule('evidence-ref'))
        self.flow(evidence={'flow_tests': [self.row(org_id=base.ORG[:15])]})
        self.passes()  # the 15-character form names the same org
        for active in (2, None):
            with self.subTest(active=active):
                self.flow(evidence={'flow_tests': [self.row()]})
                if active is None:
                    self.data['items'][0]['flow_validation'].pop('active_version')
                else:
                    self.data['items'][0]['flow_validation']['active_version'] = active
                self.save()
                self.add_sections('Flows Deployed (if any)', 'Execution Order Check')
                self.assertIn('active_version', self.assert_rule('evidence-ref'))
        self.flow(evidence={'flow_tests': [self.row()]})
        self.task.write_text(self.task.read_text().replace(base.ORG + ')', base.ORG + '); copied from 00D000000000002EAA'))
        self.assertIn('names 2 bound org IDs', self.assert_rule('evidence-ref'))  # R2-F8 renamed the binding message

    def test_unsupported_flow_validation_stays_awaiting_visual_qa(self):
        self.flow(mode='unsupported', tests=())
        self.assertIn('stays awaiting visual QA', self.assert_rule('evidence-ref'))
        self.flow(mode='unsupported', tests=(), visual_qa=True)
        self.passes()

    def test_unsupported_reason_nests_inside_flow_validation(self):
        """C4: the documented shape nests the reason; a sibling reason is named as misplaced."""
        self.flow(mode='unsupported', tests=(), visual_qa=True)
        self.data['items'][0]['unsupported_reason'] = self.data['items'][0]['flow_validation'].pop('unsupported_reason')
        self.save()
        self.add_sections('Flows Deployed (if any)', 'Execution Order Check')
        self.assertIn('inside flow_validation (a sibling unsupported_reason is misplaced)', self.assert_rule('evidence-ref'))

    def test_flow_rules_cover_already_satisfied(self):
        """F11: an existing Flow is not behaviorally verified because authoring was unnecessary."""
        self.flow(mode='unsupported', tests=())
        self.data['items'][0].update(disposition='already_satisfied', attempts=[])
        complex_story(self.data)
        self.save('')
        self.assertIn('stays awaiting visual QA', self.assert_rule('evidence-ref'))
        self.flow()
        self.data['items'][0].update(disposition='already_satisfied', attempts=[])
        self.save('')
        self.assertIn('evidence_ref file missing', self.assert_rule('evidence-ref'))
        self.flow(evidence={'flow_tests': [self.row()]})
        self.data['items'][0].update(disposition='already_satisfied', attempts=[])
        self.save('')
        self.passes()

    def test_documented_flow_unavailability_is_visual_qa(self):
        """F12: an unavailable required test, with its reason, passes only as visual QA."""
        unavailable = self.row(outcome='unavailable', reason='FlowTest API unavailable in this org')
        self.flow(evidence={'flow_tests': [unavailable]}, visual_qa=True)
        self.passes()
        self.assertIn('Overall: FINISHED_WITH_EXCEPTIONS', self.run_cli('render')[1])
        self.assertIn('Beats: B1 visual_qa', self.run_cli('render')[1])
        self.flow(evidence={'flow_tests': [unavailable]})
        self.assertIn('documented unavailable: visual QA, never a pass', self.assert_rule('evidence-ref'))
        self.flow(evidence={'flow_tests': [dict(unavailable, reason='')]}, visual_qa=True)
        self.assertIn('unavailable without its reason', self.assert_rule('evidence-ref'))

    def test_unattempted_items_need_no_evidence(self):
        """C5: a gated item blocked at its gate, or withdrawn before authoring, owes no contract evidence."""
        for disposition in ('blocked', 'omitted'):
            for kind in ('Flow', 'Agentforce'):
                with self.subTest(disposition=disposition, kind=kind):
                    self.data = base.record()
                    self.data['items'][0].update(type=kind, category='gated', disposition=disposition, attempts=[],
                                                 grounding=[dict(DOCS)], reason='SE denied the gated category')
                    complex_story(self.data, 'unverified')
                    self.save('')
                    code, output = self.run_cli('check')
                    self.assertNotIn('evidence-ref', output)
                    self.assertNotIn('log-type-sections', output)

    def test_type_families_are_normalized_by_keyword(self):
        """C3: no spelling bypasses a type-conditioned rule."""
        for spelling, message in (('RecordTriggeredFlow', 'records no frozen flow_validation'),
                                  ('Screen Flow', 'records no frozen flow_validation'),
                                  ('Agent', 'records no obligations'), ('Bot', 'records no obligations'),
                                  ('GenAiPlannerBundle', 'records no obligations'),
                                  ('AiAuthoringBundle', 'records no obligations')):
            with self.subTest(spelling=spelling):
                self.data = base.record()
                self.data['items'][0].update(type=spelling, category='gated', grounding=[dict(DOCS)])
                complex_story(self.data)
                self.save()
                self.assertIn(message, self.assert_rule('evidence-ref'))
        for spelling, section in (('ApexTrigger', 'Apex Deployed'), ('Apex Class', 'Apex Deployed'),
                                  ('LightningComponentBundle', 'LWC Deployed'), ('lwc', 'LWC Deployed')):
            with self.subTest(spelling=spelling):
                self.data = base.record()
                self.data['items'][0].update(type=spelling, category='gated', grounding=[dict(DOCS)])
                complex_story(self.data)
                self.save()
                self.assertIn('"%s"' % section, self.assert_rule('log-type-sections'))

    def test_evidence_documents_are_shape_checked(self):
        """F15: a wrong shape is an evidence-ref finding, never a crash."""
        for text in ('[]', '"x"', '{"flow_tests": {}}', '{"flow_tests": [1]}', '{"flow_tests": [{"test": "Overdue_Flip_Test", "version": [3]}]}',
                     '{', '[' * 5000 + ']' * 5000):
            with self.subTest(text=text[:40]):
                self.flow(evidence={})
                (self.folder / 'flow-evidence.json').write_text(text)
                self.assert_rule('evidence-ref')
        passing = json.dumps(self.row())
        self.flow(evidence={})
        (self.folder / 'flow-evidence.json').write_text('{"flow_tests": [%s], "flow_tests": [%s]}' % (json.dumps(self.row(outcome='Fail')), passing))
        self.assertIn('evidence file repeats key flow_tests', self.assert_rule('evidence-ref'))
        for text in ('[]', '{"agent_contexts": {}, "agent_runtime": {}}', '{"agent_contexts": [1], "agent_runtime": {}}',
                     '{"agent_contexts": [], "agent_runtime": {"O1": 1}}',
                     '{"agent_contexts": [{"item_id": "O1", "deployed_version_id": ["0Xx-version-7"]}], "agent_runtime": {"O1": {}, "O2": {}}}'):
            with self.subTest(text=text):
                self.agent()
                (self.folder / 'agent-evidence.json').write_text(text)
                self.assert_rule('evidence-ref')

    def agent(self, obligation_ids=('O1', 'O2'), covered=('O1', 'O2'), version='0Xx-version-7'):
        # F17 changed this fixture: each obligation has its own action, target and fields.
        def acceptance(oid):
            field = {'O1': 'Case.Flagged__c', 'O2': 'Case.Escalated__c'}.get(oid, 'Case.%s__c' % oid)
            return {'agent_api_name': 'Demo_Agent', 'hero_action': {'O1': 'Flag_Case', 'O2': 'Escalate_Case'}.get(oid, 'Act_' + oid),
                    'behavior': 'mutating', 'source_kind': 'agent_script',
                    'criteria': {'target': {'Case.Id': '500xx-' + oid}, 'before': {field: False}, 'after': {field: True}}}
        test = {'attempt_id': 'attempt-1', 'mode': 'session_turn', 'session_id': 's', 'turn_id': 't'}
        context = lambda oid: {'item_id': oid, 'agent_api_name': 'Demo_Agent', 'deployed_version_id': '0Xx-version-7',
                               'deployment_source': 'saved read-back', 'source_kind': 'agent_script', 'gate_sha256': GATE_SHA,
                               'test': dict(test, identity_source='saved test start', history=[])}
        def runtime(oid):
            criteria = acceptance(oid)['criteria']
            return {'agent_api_name': 'Demo_Agent', 'deployed_version_id': version, 'gate_sha256': GATE_SHA, 'test_identity': test,
                    'evidence_channel': 'live_preview',
                    'invocation': {'status': 'succeeded', 'action': acceptance(oid)['hero_action'], 'live_actions': True,
                                   'simulated': False, 'evidence_kind': 'live_trace', 'source': 'saved trace'},
                    'behavior': dict(copy.deepcopy(criteria), source='saved SOQL'),
                    'structure': {'method': 'agent_script_validation', 'result': 'pass', 'source': 'saved validation'}}
        self.data['items'] = items(('I1', 'applied', ()))
        self.data['items'][0].update(type='Agentforce', category='gated', evidence_ref='agent-evidence.json', agent_version='0Xx-version-7',
                                     obligations=[dict(id=o, agent_runtime=acceptance(o)) for o in obligation_ids],
                                     grounding=[dict(assumption='Agent Script', source='docs', ref='https://developer.salesforce.com/docs/a', verdict='supported')])
        (self.folder / 'agent-evidence.json').write_text(json.dumps(
            {'agent_contexts': [context(o) for o in covered], 'agent_runtime': {o: runtime(o) for o in covered}}))
        complex_story(self.data)
        self.save()
        self.add_sections('Agentforce Deployed (if any)', 'Agentforce Current-Test Evidence (if any)')

    def agent_evidence(self, change):
        path = self.folder / 'agent-evidence.json'
        evidence = json.loads(path.read_text())
        change(evidence)
        path.write_text(json.dumps(evidence))

    def test_agent_obligations_need_complete_passing_evidence(self):
        self.agent()
        self.passes()
        self.agent(covered=('O1',))
        self.assertIn('obligation O2 has no evidence', self.assert_rule('evidence-ref'))
        self.agent(covered=('O1', 'O3'))
        self.assertIn('obligation O2 has no evidence', self.assert_rule('evidence-ref'))
        self.agent(version='0Xx-version-6')
        self.assertIn('different deployed version', self.assert_rule('evidence-ref'))
        self.data['items'][0].pop('obligations')
        self.save()
        self.add_sections('Agentforce Deployed (if any)', 'Agentforce Current-Test Evidence (if any)')
        self.assertIn('records no obligations', self.assert_rule('evidence-ref'))

    def test_distinct_obligations_and_the_wrong_obligations_file(self):
        """F17 and X9: one obligation per action and assertion; a valid file for the wrong obligation fails."""
        self.agent()
        self.agent_evidence(lambda e: e['agent_runtime'].update(O2=copy.deepcopy(e['agent_runtime']['O1'])))
        self.assertIn('obligation O2: current invocation is not the required hero action', self.assert_rule('evidence-ref'))
        self.agent()
        self.data['items'][0]['obligations'][1]['agent_runtime'] = copy.deepcopy(self.data['items'][0]['obligations'][0]['agent_runtime'])
        self.save()
        self.add_sections('Agentforce Deployed (if any)', 'Agentforce Current-Test Evidence (if any)')
        self.assertIn('obligations O1 and O2 have identical acceptance', self.assert_rule('evidence-ref'))

    def test_agent_version_binds_the_whole_evidence_file(self):
        """F13: the task's own publish and activation read-back names the version the file must describe."""
        self.agent()
        def stale(evidence):
            for context in evidence['agent_contexts']:
                context['deployed_version_id'] = '0Xx-version-6'
            for runtime in evidence['agent_runtime'].values():
                runtime['deployed_version_id'] = '0Xx-version-6'
        self.agent_evidence(stale)
        self.assertIn('evidence is for a different deployed version', self.assert_rule('evidence-ref'))
        self.agent()
        self.data['items'][0].pop('agent_version')
        self.save()
        self.add_sections('Agentforce Deployed (if any)', 'Agentforce Current-Test Evidence (if any)')
        self.assertIn('records no agent_version', self.assert_rule('evidence-ref'))

    def test_documented_agent_unavailability_is_visual_qa(self):
        """F12: an unavailable runtime passes only as visual QA; other UNAVAILABLE reasons still fail."""
        def unavailable(evidence):
            for runtime in evidence['agent_runtime'].values():
                runtime['invocation']['status'] = 'unavailable'
        self.agent()
        self.agent_evidence(unavailable)
        self.assertIn('documents an unavailable runtime: visual QA, never a pass', self.assert_rule('evidence-ref'))
        self.agent()
        self.agent_evidence(unavailable)
        self.data['items'][0].update(visual_qa=True, reason='Preview cannot invoke a session-context action')
        complex_story(self.data, 'visual_qa')
        self.save()
        self.add_sections('Agentforce Deployed (if any)', 'Agentforce Current-Test Evidence (if any)')
        self.assertIn('"Actions Unverified in Preview"', self.assert_rule('log-type-sections'))
        self.add_sections('Actions Unverified in Preview (if any)')
        self.passes()
        self.assertIn('Overall: FINISHED_WITH_EXCEPTIONS', self.run_cli('render')[1])
        self.agent_evidence(lambda e: e['agent_runtime']['O1'].update(gate_sha256='0' * 64))
        self.assertIn('stale validation-gate digest', self.assert_rule('evidence-ref'))

    def test_unavailable_reason_is_the_assessors(self):
        """F12 relies on this wording; a change in agentforce_evidence.py must fail here, not open the path."""
        self.agent()
        record = history.task_record(self.task)
        evidence = json.loads((self.folder / 'agent-evidence.json').read_text())
        runtime = evidence['agent_runtime']['O1']
        runtime['invocation']['status'] = 'unavailable'
        result = BUILD._assessor().assess(record['items'][0]['obligations'][0]['agent_runtime'], evidence['agent_contexts'][0],
                                          runtime, BUILD.GATE.read_bytes())
        self.assertEqual((result['assessment'], result['reason']), ('UNAVAILABLE', BUILD.UNAVAILABLE_INVOCATION))

    def test_evidence_ref_stays_inside_the_folder(self):
        self.agent()
        self.data['items'][0]['evidence_ref'] = '../outside.json'
        self.save()
        self.add_sections('Agentforce Deployed (if any)', 'Agentforce Current-Test Evidence (if any)')
        self.assertIn('must stay inside the folder', self.assert_rule('evidence-ref'))


class JobTests(Harness):
    """X5 and F1-F3: positive settlement, launch and settle times, and the one serial write slot."""

    def two(self, first, second, dispositions=('unverified', 'applied')):
        self.data['items'] = items(('I1', dispositions[0], ()), ('I2', dispositions[1], ()))
        self.data['items'][0]['reason'] = 'deploy timed out; job still queued' if dispositions[0] == 'unverified' else ''
        self.save(first + second)

    def test_non_terminal_job_holds_the_write_slot(self):
        # F2 and F3 changed this test's second half: settlement is a terminal `status:` field with its times, never prose.
        first = cp('A1', 'unverified', '- Deploy %s: status Queued at timeout\n' % DEPLOY)
        second = cp('A2', at='2026-10-13 12:20')
        self.two(first, second)
        self.assertIn('A1 left job %s non-terminal, yet A2 started after it' % DEPLOY, self.assert_rule('plan'))
        self.two(cp('A1', 'unverified', '- Deploy %s: final status Succeeded (sf project deploy report)\n' % DEPLOY), second)
        self.assertIn('non-terminal', self.assert_rule('plan'))
        settled = cp('A1', body=job(DEPLOY, 'Succeeded', '2026-10-13T12:00:05', '2026-10-13T12:09:58'))
        self.two(settled, second, ('applied', 'applied'))
        self.passes()

    def test_a_job_settles_only_with_a_terminal_status_field(self):
        """F1 and F2: an applied, already_satisfied or failed item can't carry an unsettled job."""
        launched = '2026-10-13T12:00:05'
        for body in ('- Deploy %s: status Queued at timeout; read-back currently matches.\n' % DEPLOY,
                     '- Launch receipt: %s; report did not return status.\n' % DEPLOY,
                     '- Deploy %s: status Queued; polling failed.\n' % DEPLOY,
                     job(DEPLOY, 'Queued', launched), job(DEPLOY, 'Failed to poll', launched), job(DEPLOY, None, launched),
                     '```json\n{"id":"%s","status":"Queued"}\n```\n- launched: %s\n' % (DEPLOY, launched),
                     job(BULK, 'InProgress', launched), job(BULK, 'Succeeded', launched, '2026-10-13T12:01:00')):
            for disposition in ('applied', 'failed'):
                with self.subTest(body=body, disposition=disposition):
                    self.data = base.record()
                    self.data['items'][0]['disposition'] = disposition
                    self.data['items'][0]['reason'] = 'State left: unchanged; rollback: not needed' if disposition == 'failed' else ''
                    self.save(cp('A1', disposition, body))
                    self.assertIn('I1 is %s, but attempt A1 has an unsettled job' % disposition, self.assert_rule('plan'))
        self.data = base.record()
        self.data['items'][0].update(disposition='unverified', reason='Job still queued')
        self.save(cp('A1', 'unverified', job(DEPLOY, 'Queued', launched)))
        self.passes()  # honest: unverified while the job may still land; `plan` shows the open job

    def test_settlement_through_check_for_each_executor_family(self):
        """F17: Metadata deploys, Bulk jobs, Agentforce publishes and Email-to-Case's apply script; sync writes carry no job."""
        times = ('2026-10-13T12:00:05', '2026-10-13T12:03:00')
        cases = [('CustomField', job(DEPLOY, 'Succeeded', *times), True), ('CustomField', job(DEPLOY, 'SucceededPartial', *times), True),
                 ('CustomField', job(DEPLOY, 'canceled', *times), True), ('CustomField', job(DEPLOY, 'InProgress', times[0]), False),
                 ('Data', job(BULK, 'JobComplete', *times), True), ('Data', job(BULK, 'Aborted', *times), True),
                 ('Data', job(BULK, 'Succeeded', *times), False), ('Data', job(BULK, 'UploadComplete', times[0]), False),
                 ('Data', '- Synchronous upsert of 4 Account rows; describe and SOQL read-back attached.\n', True),
                 ('Agentforce', job('agent publish', 'Active', *times), True), ('Agentforce', job('agent publish', 'NeedsUICommit', *times), True),
                 ('Agentforce', job('agent publish', 'Published', *times), False),
                 ('Email-to-Case', job('apply script', 'Completed', *times), True), ('Email-to-Case', job('apply script', 'Active', *times), False),
                 ('CustomField', job('deploy without its ID', 'Succeeded', *times), False)]
        for kind, body, settles in cases:
            with self.subTest(kind=kind, body=body):
                self.data = base.record()
                self.data['items'][0]['type'] = kind
                self.save(cp('A1', body=body))
                output = self.run_cli()[1]
                self.assertEqual('has an unsettled job' not in output, settles, output)

    def test_launch_and_settle_times_order_the_global_slot(self):
        """F3: an attempt that starts inside another attempt's open job interval is a finding, in any log order."""
        first = cp('A1', body=job(DEPLOY, 'Succeeded', '2026-10-13T12:00:00', '2026-10-13T12:10:00'))
        for second, overlaps in ((cp('A2', body='- launched: 2026-10-13T12:05:00\n', at='2026-10-13 12:05'), True),
                                 (cp('A2', body='- launched: 2026-10-13T12:00:00\n'), True),
                                 (cp('A2', body='- launched: 2026-10-13T12:10:30\n', at='2026-10-13 12:10'), False),
                                 (cp('A2', at='2026-10-13 12:05'), True),
                                 (cp('A2', at='2026-10-13 12:10'), False),
                                 (cp('A2', body=job(BULK, 'JobComplete', '2026-10-13T12:09:00', '2026-10-13T12:12:00'), at='2026-10-13 12:09'), True)):
            for order in ('log', 'reversed'):
                with self.subTest(second=second, order=order):
                    self.data['items'] = items(('I1', 'applied', ()), ('I2', 'applied', ()))
                    self.save(first + second if order == 'log' else second + first)
                    output = self.run_cli()[1]
                    self.assertEqual("before A1's job" in output, overlaps, output)

    def test_job_times_are_recorded_and_well_formed(self):
        for body, message in ((job(DEPLOY, 'Succeeded', None, '2026-10-13T12:10:00'), 'without a launched: time'),
                              (job(DEPLOY, 'Succeeded', '2026-10-13T12:00:00'), 'without a settled: time'),
                              (job(DEPLOY, 'Succeeded', '2026-10-13T12:10:00', '2026-10-13T12:00:00'), 'settled before it launched'),
                              (job(DEPLOY, 'Succeeded', '2026-10-13 12:00', '2026-10-13T12:10:00'), 'not an ISO time with seconds'),
                              (job(DEPLOY, 'Succeeded', '2026-10-13T12:00:00Z', '2026-10-13T12:10:00'), 'mix zoned and local times')):
            with self.subTest(message=message):
                self.data = base.record()
                self.save(cp('A1', body=body))
                self.assertIn(message, self.assert_rule('plan'))
        self.data = base.record()
        self.save(cp('A1', body='- job: %s\n- status: Succeeded\n- launched: 2026-10-13T12:00:00.250+02:00\n- settled: 2026-10-13T12:10:00+02:00\n' % DEPLOY))
        self.passes()  # one job may take checkpoint-level fields
        for line in ('- **job:** `%s` status: Succeeded launched: 2026-10-13T12:00:00 settled: 2026-10-13T12:10:00\n' % DEPLOY,
                     '- job: %s, status: Succeeded, launched: 2026-10-13T12:00:00, settled: 2026-10-13T12:10:00\n' % DEPLOY):
            with self.subTest(line=line):
                self.save(cp('A1', body=line))
                self.passes()
        self.save(cp('A1', body=job(DEPLOY, 'Succeeded', '2026-10-13T12:00:00+99:99', '2026-10-13T12:10:00')))
        self.assertIn('not an ISO time with seconds', self.assert_rule('plan'))
        self.data['items'] = items(('I1', 'applied', ()), ('I2', 'applied', ()))
        self.save(cp('A1', body=job(DEPLOY, 'Queued', '2026-10-13T12:00:00')) + cp('A2', at='2026-02-30 12:05'))
        self.assertIn('A1 left job %s non-terminal, yet A2 started after it' % DEPLOY, self.assert_rule('plan'))  # no crash on a bad heading date

    def test_the_routes_job_template_parses(self):
        """The `job:` line exactly as commands/scout.md prints it, filled in, settles; a non-terminal one doesn't."""
        command = (Path(__file__).resolve().parents[1] / 'commands/scout.md').read_text()
        template = re.search(r'`(- job:<ID>;[^`]+)`', command)[1]
        def filled(status):
            return (template.replace('<ID>', DEPLOY).replace('<terminal>', status)
                    .replace('<YYYY-MM-DDTHH:MM:SS>', '2026-10-13T12:00:05').replace('<…>', '2026-10-13T12:09:58') + '\n')
        self.save(cp('A1', body=filled('Succeeded')))
        self.passes()
        self.save(cp('A1', body=filled('InProgress')))
        self.assertIn('has an unsettled job', self.assert_rule('plan'))

    def test_a_retry_records_its_error_grounding(self):
        """RB3 and F5, for complex tasks: a retry cites the covering lesson or the Docs search of the verbatim error."""
        def retry(*entries):
            self.data = base.record()
            self.data['items'][0].update(attempts=['A1', 'A2'], grounding=[dict(DOCS), *entries])
            complex_story(self.data)
            self.save(cp('A1', 'failed', '- Error: status 1; file excluded by .forceignore\n') + cp('A2', at='2026-10-13 12:20'))
        retry()
        self.assertIn('I1 retried in A2 after failed A1 without a grounding entry', self.assert_rule('grounding'))
        retry(dict(assumption='status 1: excluded file', source='skill', ref='deploy skill', verdict='ok', attempt='A2'))
        self.assert_rule('grounding')
        retry(dict(assumption='status 1: excluded file', source='lesson', ref='', verdict='covered', attempt='A2'))
        self.assert_rule('grounding')
        retry(dict(assumption='status 1: excluded file', source='lesson', ref='L-forceignore-01', verdict='covered', attempt='A9'))
        self.assertIn('names A9, which is not one of its attempts', self.assert_rule('grounding'))
        retry(dict(assumption='status 1: excluded file', source='lesson', ref='L-forceignore-01', verdict='covered', attempt='A2'))
        self.passes()
        retry(dict(assumption='status 1: excluded file', source='docs', verdict='forceignore excludes deploy paths', attempt='A2',
                   ref='https://developer.salesforce.com/docs/w10-forceignore-fixture'))
        self.passes()

    def test_per_type_sections_follow_the_template_conditions(self):
        """F14: the template's conditions decide each section, never the final disposition."""
        # F14 changed this test: an attempted Apex item needs its section even when it failed.
        for disposition in ('applied', 'failed'):
            with self.subTest(disposition=disposition):
                self.data = base.record()
                self.data['items'][0].update(type='Apex', category='gated', disposition=disposition, grounding=[dict(DOCS)],
                                             reason='State left: unchanged; rollback: not needed' if disposition == 'failed' else '')
                complex_story(self.data, 'verified' if disposition == 'applied' else 'unverified')
                self.save()
                self.assertIn('the log needs its "Apex Deployed" section', self.assert_rule('log-type-sections'))
        self.data['items'][0].update(type='Flow', flow_validation=dict(flow_api_name='F', mode='unsupported', unsupported_reason='screen'))
        self.save(cp('A1', 'failed', '- Deployment succeeded and Flow is active; own behavior read-back failed.\n'))
        output = self.assert_rule('log-type-sections')
        self.assertIn('"Execution Order Check"', output)
        self.assertIn('"Flows Deployed"', output)
        self.data['items'][0].update(disposition='already_satisfied', attempts=[], reason='')
        self.save('')
        self.assertNotIn('log-type-sections', self.run_cli()[1])

    def test_agent_sections_follow_liveness_and_incumbency(self):
        evidence = EvidenceTests.agent
        evidence(self)
        self.data['items'][0].update(disposition='unverified', reason='NeedsUICommit: publish route 404; NOT live')
        self.save()
        self.add_sections('Agentforce Deployed (if any)', 'Agentforce Current-Test Evidence (if any)')
        self.assertIn('"Agent Not Live"', self.assert_rule('log-type-sections'))
        evidence(self)
        self.data['items'][0]['what'] = 'Modify Existing Agent Demo_Agent'
        self.save(cp('A1', body='- Classification / source: existing; Demo_Agent original version 0Xx-version-6.\n' + LIVE))
        self.add_sections('Agentforce Deployed (if any)', 'Agentforce Current-Test Evidence (if any)')
        self.assertIn('"Existing Agent Before-State"', self.assert_rule('log-type-sections'))
        self.add_sections('Existing Agent Before-State (only for modified incumbent agents)')
        self.passes()


class Round3Tests(Harness):
    """W10 round 3: Astra's round-2 findings R2-F1 to R2-F12, and candidates C1 and C4 as ruled."""

    def test_r2_f1_job_lines_count_inside_fences(self):
        self.save(cp('A1', body='```text\n' + job(DEPLOY, 'Succeeded', '2026-10-13T12:00:00', '2026-10-13T12:05:00') + '```\n'))
        self.passes()  # a fenced receipt's own fields settle its job
        EvidenceTests.agent(self)
        self.save(cp('A1', body='```text\n' + job('agent publish', 'InProgress', '2026-10-13T12:00:00') + '```\n'))
        self.add_sections('Agentforce Deployed (if any)', 'Agentforce Current-Test Evidence (if any)', 'Agent Not Live')
        self.assertIn('has an unsettled job (agent publish', self.assert_rule('plan'))
        self.assertEqual([j['job'] for j in json.loads(self.run_cli('plan')[1])['open_jobs']], ['agent publish'])

    def test_r2_f2_a_proof_moment_needs_an_active_claim(self):
        complex_story(self.data)
        self.data['path'] = 'open-ended'
        self.data['story']['beats'][0]['claims'][0].update(result='dropped', required=False)
        self.save()
        output = self.assert_rule('story')
        self.assertIn('proof moment needs a claim with readback', output)
        self.assertIn('B1 is the proof moment but has no active claim', output)
        self.assertIn('Overall: UNRESOLVED', self.run_cli('render')[1])

    def test_r2_f3_every_job_holds_the_write_slot(self):
        self.save(cp('A1', body=job(DEPLOY, 'Succeeded', '2026-10-13T12:00:00', '2026-10-13T12:10:00') +
                     job(BULK, 'JobComplete', '2026-10-13T12:05:00', '2026-10-13T12:06:00')))
        self.assertIn("A1 (job %s) launched before A1's job %s settled" % (BULK, DEPLOY), self.assert_rule('plan'))
        self.data['items'] = items(('I1', 'unverified', ()), ('I2', 'already_satisfied', ()))
        self.data['items'][0]['reason'] = 'deploy remains queued'
        self.data['items'][1]['attempts'] = ['A2']
        queued = cp('A1', 'unverified', job(DEPLOY, 'Queued', '2026-10-13T12:00:00'))
        self.save(queued + cp('A2', 'already_satisfied', job(BULK, 'JobComplete', '2026-10-13T12:05:00', '2026-10-13T12:06:00')))
        self.assertIn('A1 left job %s non-terminal, yet A2 started after it' % DEPLOY, self.assert_rule('plan'))
        self.save(queued + cp('A2', 'already_satisfied'))
        self.assertNotIn('yet A2 started', self.run_cli()[1])  # it submitted nothing, so it wrote nothing

    def test_r2_f4_write_order_follows_recorded_times(self):
        self.data['items'] = items(('I1', 'applied', ()), ('I2', 'applied', ('I1',)))
        self.save(cp('A1', body=job(DEPLOY, 'Succeeded', '2026-10-13T12:10:00', '2026-10-13T12:11:00'), at='2026-10-13 12:10') +
                  cp('A2', body=job(BULK, 'JobComplete', '2026-10-13T12:00:00', '2026-10-13T12:01:00')))
        self.assertIn('I2 was attempted before its prerequisite I1 settled', self.assert_rule('plan'))
        prerequisite = cp('A1', body=job(DEPLOY, 'Succeeded', '2026-10-13T12:00:00', '2026-10-13T12:05:00'))
        dependent = cp('A2', body=job(BULK, 'JobComplete', '2026-10-13T12:05:01', '2026-10-13T12:06:00'), at='2026-10-13 12:05')
        self.save(dependent + prerequisite)
        self.passes()  # the times prove the order, whatever the log's order

    def test_r2_f5_retries_follow_the_order_attempts_ran(self):
        complex_story(self.data)
        self.data['items'][0]['attempts'] = ['A2', 'A1', 'A3']
        self.data['items'][0]['grounding'].append(dict(assumption='A1 failure covered', source='lesson', ref='L1', verdict='covered', attempt='A3'))
        self.save(cp('A1', 'failed', '- Error: failed first write.\n') + cp('A2', at='2026-10-13 12:10') + cp('A3', at='2026-10-13 12:20'))
        output = self.assert_rule('grounding')
        self.assertIn('I1 lists attempts A2, A1, A3, but its checkpoints ran A1, A2, A3', output)
        self.assertIn('I1 retried in A2 after failed A1', output)

    def test_r2_f6_agent_not_live_follows_the_publish(self):
        EvidenceTests.agent(self)
        self.data['items'][0].update(disposition='failed', reason='State left: published but Inactive; rollback: unchanged')
        self.data['story']['beats'][0]['verification']['verdict'] = 'unverified'
        self.save(cp('A1', 'failed', job('agent publish', 'Inactive', '2026-10-13T12:00:00', '2026-10-13T12:05:00')))
        self.add_sections('Agentforce Deployed (if any)', 'Agentforce Current-Test Evidence (if any)')
        self.assertIn('"Agent Not Live"', self.assert_rule('log-type-sections'))
        EvidenceTests.agent(self)
        self.data['items'][0].update(disposition='unverified', reason='Version active; runtime probe timed out')
        self.data['story']['beats'][0]['verification']['verdict'] = 'unverified'
        self.save(cp('A1', 'unverified', job('agent publish', 'Active', '2026-10-13T12:00:00', '2026-10-13T12:05:00')))
        self.add_sections('Agentforce Deployed (if any)', 'Agentforce Current-Test Evidence (if any)')
        self.assertNotIn('Agent Not Live', self.run_cli()[1])

    def test_r2_f7_a_dropped_optional_claim_is_history(self):
        complex_story(self.data)
        self.data['items'][0]['grounding'] = [dict(DOCS)]  # I1's active proof claim still owes Docs
        self.data['story']['beats'][0]['claims'].append(dict(text='Withdrawn extra', item='I2', result='dropped', required=False))
        self.data['items'].append(item('I2', 'omitted'))
        self.data['items'][1].update(reason='SE withdrew the optional field', beat='-', readback='')
        self.save()
        self.passes()  # no proof-moment Docs obligation, no readback for an item only a withdrawn claim names

    def test_r2_f8_only_a_binding_line_binds(self):
        EvidenceTests.flow(self, evidence={'flow_tests': [EvidenceTests.row(self)]})
        self.task.write_text(self.task.read_text() + '\n## Request verbatim\n'
                             'Build this in the bound demo org, never in our production org 00D000000000999EAA.\n'
                             '> Target org: 00D000000000998EAA, quoted from an old email\n'
                             '- Request (verbatim, for our demo org): not 00D000000000997EAA\n')
        self.passes()
        self.task.write_text(self.task.read_text().replace('Org: ', 'Owner: ', 1))
        self.assertIn('names 0 bound org IDs', self.assert_rule('evidence-ref'))

    def test_r2_f9_rows_beyond_the_required_ones_keep_their_shape(self):
        EvidenceTests.flow(self, evidence={'flow_tests': [EvidenceTests.row(self), EvidenceTests.row(self, test='Extra_Test', version=True)]})
        self.assertIn('flow_tests row 2 needs', self.assert_rule('evidence-ref'))

    def test_r2_f10_a_boolean_row_version_never_matches_version_1(self):
        EvidenceTests.flow(self, evidence={'flow_tests': [EvidenceTests.row(self, version=True)]})
        self.data['items'][0]['flow_validation'].update(version=1, active_version=1)
        self.save()
        self.add_sections('Flows Deployed (if any)', 'Execution Order Check')
        self.assertIn('did not run on the frozen flow and version 1', self.assert_rule('evidence-ref'))

    def test_r2_f11_time_zone_offsets_are_validated(self):
        self.save(cp('A1', body=job(DEPLOY, 'Succeeded', '2026-10-13T12:00:00+00:90', '2026-10-13T12:05:00+00:90')))
        self.assertIn('is not an ISO time with seconds', self.assert_rule('plan'))
        self.save(cp('A1', body=job(DEPLOY, 'Succeeded', '2026-10-13T12:00:00+05:30', '2026-10-13T12:05:00+05:30')))
        self.passes()

    def test_r2_f12_the_route_lists_the_lesson_source(self):
        route = (Path(BUILD.__file__).resolve().parents[1] / 'commands/scout.md').read_text()
        self.assertIn('Sources: `docs|skill|org|lesson|ungrounded`', route)

    def test_c1_pending_names_a_prior_task_open_job(self):
        self.data['items'][0].update(disposition='unverified', reason='Queued at timeout; never terminal')
        self.save(cp('A1', 'unverified', job(DEPLOY, 'Queued', '2026-10-13T12:00:00')))
        rows = [r for r in base.ScoutHistoryTests.pending_rows(self) if r.get('file') == str(self.log)]
        self.assertEqual([(r['state'], r.get('open_jobs')) for r in rows], [('resolved', [DEPLOY])])
        self.save(cp('A1', 'unverified', job(DEPLOY, 'Succeeded', '2026-10-13T12:00:00', '2026-10-13T12:20:00')))
        rows = [r for r in base.ScoutHistoryTests.pending_rows(self) if r.get('file') == str(self.log)]
        self.assertEqual([(r['state'], r.get('open_jobs')) for r in rows], [('resolved', None)])

    def test_c4_sections_count_at_the_template_level(self):
        EvidenceTests.agent(self)
        self.data['items'][0]['what'] = 'Modify Existing Agent Demo_Agent'
        self.save(cp('A1', body='- Classification / source: existing; original version 0Xx-version-6.\n' + LIVE +
                     '#### Existing Agent Before-State\nA scratch note, not the template section.\n'))
        self.add_sections('Agentforce Deployed (if any)', 'Agentforce Current-Test Evidence (if any)')
        self.assertIn('"Existing Agent Before-State"', self.assert_rule('log-type-sections'))
        self.add_sections('Existing Agent Before-State (only for modified incumbent agents)')
        self.passes()


if __name__ == '__main__':
    unittest.main()
