"""W10 contracts: plan order and layers, beat verdicts, beat-aware Overall, write order and evidence references."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_scout_history as base
from test_scout_history import history, item

BUILD = history.BUILD
GATE_SHA = hashlib.sha256(BUILD.GATE.read_bytes()).hexdigest()


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


class Harness(unittest.TestCase):
    """The history suite's fixture, without re-running its tests."""
    setUp = base.ScoutHistoryTests.setUp
    save = base.ScoutHistoryTests.save
    run_cli = base.ScoutHistoryTests.run_cli
    assert_rule = base.ScoutHistoryTests.assert_rule

    def add_sections(self, *names):
        """Insert per-type log sections ahead of the final Checkpoints section."""
        text = self.log.read_text()
        block = ''.join('## %s\nRecorded.\n' % name for name in names)
        self.log.write_text(text.replace('## Checkpoints\n', block + '## Checkpoints\n', 1) if '## Checkpoints\n' in text else text + block)


def beat(identifier='B1', claims=(), flips=(), proof=True, verification=None):
    value = dict(id=identifier, name='Overdue list', persona='Manager', pain='Lost', climax='Two rows',
                 claims=[dict(text=text, item=owner, **({'result': result} if result else {})) for text, owner, result in claims],
                 proof_moment=proof)
    if flips:
        value['flips'] = list(flips)
    if verification:
        value['verification'] = dict(verdict=verification, evidence='own read-back')
    return value


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
        ]
        for kwargs, expected in cases:
            with self.subTest(kwargs=kwargs):
                self.complex_record(verification=None, **kwargs)
                self.assertEqual(self.verdict(), expected)

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

    def test_check_compares_recorded_and_computed_verdicts(self):
        self.complex_record(verification='verified')
        code, output = self.run_cli('check')
        self.assertEqual(code, 0, output)
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

    def test_schema_rejects_malformed_w10_fields(self):
        bad = [
            lambda d: d['story']['beats'][0].update(flips=['F1']),
            lambda d: d['story']['beats'][0].update(flips=['FL1', 'FL1']),
            lambda d: d.update(rehearsals=[dict(flip='FL9', result='passed', evidence='x')]),
            lambda d: d['story']['beats'][0]['claims'][0].update(result='maybe'),
            lambda d: d['story']['beats'][0].update(verification=dict(verdict='ok', evidence='x')),
            lambda d: d.update(complex='yes'),
        ]
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


class EvidenceTests(Harness):
    def flow(self, mode='flow_test_required', tests=('Overdue_Flip_Test',), evidence=None, visual_qa=False):
        self.data['items'] = items(('I1', 'applied', ()))
        flow_item = self.data['items'][0]
        flow_item.update(type='Flow', category='gated', visual_qa=visual_qa,
                         flow_validation=dict(flow_api_name='Overdue_Flag', mode=mode, required_tests=list(tests), version=3),
                         grounding=[dict(assumption='Flow XML', source='docs', ref='https://developer.salesforce.com/docs/x', verdict='supported')])
        if mode == 'unsupported':
            flow_item['flow_validation']['unsupported_reason'] = 'no FlowTest path for screen flows'
        if evidence is not None:
            (self.folder / 'flow-evidence.json').write_text(json.dumps(evidence))
            flow_item['evidence_ref'] = 'flow-evidence.json'
        self.save()
        self.add_sections('Flows Deployed (if any)', 'Execution Order Check')

    def test_flow_needs_frozen_validation_and_passing_required_tests(self):
        passing = {'flow_tests': [dict(test='Overdue_Flip_Test', outcome='Pass', flow_api_name='Overdue_Flag', version=3)]}
        self.flow(evidence=passing)
        code, output = self.run_cli('check')
        self.assertEqual(code, 0, output)
        for evidence, message in (({'flow_tests': []}, 'has no result'),
                                  ({'flow_tests': [dict(passing['flow_tests'][0], version=2)]}, 'frozen flow and version'),
                                  ({'flow_tests': [dict(passing['flow_tests'][0], outcome='Fail')]}, 'frozen flow and version')):
            with self.subTest(message=message):
                self.flow(evidence=evidence)
                self.assertIn(message, self.assert_rule('evidence-ref'))
        self.flow()
        self.assertIn('evidence_ref file missing', self.assert_rule('evidence-ref'))
        self.data['items'][0].pop('flow_validation')
        self.save()
        self.add_sections('Flows Deployed (if any)', 'Execution Order Check')
        self.assertIn('records no frozen flow_validation', self.assert_rule('evidence-ref'))

    def test_unsupported_flow_validation_stays_awaiting_visual_qa(self):
        self.flow(mode='unsupported', tests=())
        self.assertIn('stays awaiting visual QA', self.assert_rule('evidence-ref'))
        self.flow(mode='unsupported', tests=(), visual_qa=True)
        code, output = self.run_cli('check')
        self.assertEqual(code, 0, output)

    def agent(self, obligation_ids=('O1', 'O2'), covered=('O1', 'O2'), version='0Xx-version-7'):
        expected = {'agent_api_name': 'Demo_Agent', 'hero_action': 'Flag_Case', 'behavior': 'mutating', 'source_kind': 'agent_script',
                    'criteria': {'target': {'Case.Id': '500xx'}, 'before': {'Case.Flagged__c': False}, 'after': {'Case.Flagged__c': True}}}
        test = {'attempt_id': 'attempt-1', 'mode': 'session_turn', 'session_id': 's', 'turn_id': 't'}
        context = lambda oid: {'item_id': oid, 'agent_api_name': 'Demo_Agent', 'deployed_version_id': '0Xx-version-7',
                               'deployment_source': 'saved read-back', 'source_kind': 'agent_script', 'gate_sha256': GATE_SHA,
                               'test': dict(test, identity_source='saved test start', history=[])}
        runtime = {'agent_api_name': 'Demo_Agent', 'deployed_version_id': version, 'gate_sha256': GATE_SHA, 'test_identity': test,
                   'evidence_channel': 'live_preview',
                   'invocation': {'status': 'succeeded', 'action': 'Flag_Case', 'live_actions': True, 'simulated': False,
                                  'evidence_kind': 'live_trace', 'source': 'saved trace'},
                   'behavior': {'target': {'Case.Id': '500xx'}, 'before': {'Case.Flagged__c': False}, 'after': {'Case.Flagged__c': True},
                                'source': 'saved SOQL'},
                   'structure': {'method': 'agent_script_validation', 'result': 'pass', 'source': 'saved validation'}}
        self.data['items'] = items(('I1', 'applied', ()))
        self.data['items'][0].update(type='Agentforce', category='gated', evidence_ref='agent-evidence.json',
                                     obligations=[dict(id=o, agent_runtime=copy.deepcopy(expected)) for o in obligation_ids],
                                     grounding=[dict(assumption='Agent Script', source='docs', ref='https://developer.salesforce.com/docs/a', verdict='supported')])
        (self.folder / 'agent-evidence.json').write_text(json.dumps(
            {'agent_contexts': [context(o) for o in covered], 'agent_runtime': {o: copy.deepcopy(runtime) for o in covered}}))
        self.save()
        self.add_sections('Agentforce Deployed (if any)', 'Agentforce Current-Test Evidence (if any)')

    def test_agent_obligations_need_complete_passing_evidence(self):
        self.agent()
        code, output = self.run_cli('check')
        self.assertEqual(code, 0, output)
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

    def test_evidence_ref_stays_inside_the_folder(self):
        self.agent()
        self.data['items'][0]['evidence_ref'] = '../outside.json'
        self.save()
        self.add_sections('Agentforce Deployed (if any)', 'Agentforce Current-Test Evidence (if any)')
        self.assertIn('must stay inside the folder', self.assert_rule('evidence-ref'))


class SlotAndSectionTests(Harness):
    def test_non_terminal_job_holds_the_write_slot(self):
        self.data['items'] = items(('I1', 'unverified', ()), ('I2', 'applied', ()))
        self.data['items'][0]['reason'] = 'deploy timed out; job still queued'
        first = (base.checkpoint('A1', 'unverified', 'unverified').replace('outcome: pending', 'outcome: unverified') +
                 '- Deploy 0AfKa00000iDxZZKAS: status Queued at timeout\n')
        second = base.checkpoint('A2', 'applied', 'applied').replace('outcome: pending', 'outcome: applied')
        self.save(first + second)
        self.assertIn('A1 left job 0AfKa00000iDxZZKAS non-terminal, yet A2 started after it', self.assert_rule('plan'))
        self.save(first + '- Deploy 0AfKa00000iDxZZKAS: final status Succeeded (sf project deploy report)\n' + second)
        code, output = self.run_cli('check')
        self.assertNotIn('non-terminal', output)

    def test_per_type_sections_follow_the_template_conditions(self):
        self.data['items'] = items(('I1', 'applied', ()))
        self.data['items'][0].update(type='Apex', category='gated', grounding=[dict(
            assumption='Invocable Apex', source='docs', ref='https://developer.salesforce.com/docs/apex', verdict='supported')])
        self.save()
        self.assertIn('the log needs its "Apex Deployed" section', self.assert_rule('log-type-sections'))
        self.data['items'][0]['disposition'] = 'failed'
        self.data['items'][0]['reason'] = 'State left: unchanged; rollback: not needed'
        self.save()
        code, output = self.run_cli('check')
        self.assertNotIn('log-type-sections', output)


if __name__ == '__main__':
    unittest.main()
