#!/usr/bin/env python3
"""Complex-plan rules for /scout (W10): write order, authoring layers, beat verdicts, evidence references.

Pure functions over a parsed scout-items record; `scout_history.py` calls them for `plan`, `render` and
`check`. Standard library only, Python 3.9 or newer, and safe under -S.
"""
import importlib.util
import json
import re
from pathlib import Path

SETTLED_OK = ('applied', 'already_satisfied')
NOT_OK = ('failed', 'blocked', 'unverified', 'omitted')
CLAIM_RESULTS = ('passed', 'failed', 'dropped')
FLIP_RESULTS = ('passed', 'failed', 'not_rehearsable')
VERDICTS = ('verified', 'visual_qa', 'unverified', 'failed')
FLOW_MODES = ('flow_test_required', 'unsupported')
GATE = Path(__file__).resolve().parents[1] / 'prompts/building/agentforce-validation-gate.md'


class CycleError(ValueError):
    pass


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def validate(record):
    """Check the W10 block fields; raise ValueError naming the first problem."""
    if 'complex' in record and type(record['complex']) is not bool:
        raise ValueError('invalid complex flag')
    flips = set()
    story = record.get('story') or {'beats': []}
    for beat in story['beats']:
        for flip in beat.get('flips', []):
            if not isinstance(flip, str) or not re.fullmatch(r'FL[1-9]\d*', flip) or flip in flips:
                raise ValueError('invalid or duplicate flip ID')
            flips.add(flip)
        if 'flips' in beat and not isinstance(beat['flips'], list):
            raise ValueError('invalid flips')
        verification = beat.get('verification')
        if verification is not None and (not isinstance(verification, dict) or verification.get('verdict') not in VERDICTS
                                         or not isinstance(verification.get('evidence'), str)):
            raise ValueError('invalid beat verification')
        for claim in beat['claims']:
            if 'result' in claim and claim['result'] not in CLAIM_RESULTS:
                raise ValueError('invalid claim result')
    rehearsals = record.get('rehearsals', [])
    if not isinstance(rehearsals, list):
        raise ValueError('invalid rehearsals')
    for rehearsal in rehearsals:
        if (not isinstance(rehearsal, dict) or rehearsal.get('flip') not in flips or rehearsal.get('result') not in FLIP_RESULTS
                or not isinstance(rehearsal.get('evidence'), str)):
            raise ValueError('invalid rehearsal')
    for item in record['items']:
        if 'evidence_ref' in item and not _text(item['evidence_ref']):
            raise ValueError('invalid evidence_ref')
        if 'flow_validation' in item:
            flow = item['flow_validation']
            if (not isinstance(flow, dict) or not _text(flow.get('flow_api_name')) or flow.get('mode') not in FLOW_MODES
                    or not isinstance(flow.get('required_tests', []), list)):
                raise ValueError('invalid flow_validation')
        if 'obligations' in item:
            if not isinstance(item['obligations'], list) or not item['obligations']:
                raise ValueError('invalid obligations')
            seen = set()
            for obligation in item['obligations']:
                if (not isinstance(obligation, dict) or not _text(obligation.get('id')) or obligation['id'] in seen
                        or not isinstance(obligation.get('agent_runtime'), dict)):
                    raise ValueError('invalid obligation')
                seen.add(obligation['id'])


def plan(record):
    """Topological write order of depends_on, authoring layers, and the unsettled remainder."""
    items = {i['id']: i for i in record['items']}
    position = {identifier: n for n, identifier in enumerate(items)}
    for item in items.values():
        for dependency in item['depends_on']:
            if dependency not in items:
                raise CycleError(item['id'] + ' has unknown dependency ' + dependency)
    order, layers, done = [], [], set()
    remaining = set(items)
    while remaining:
        layer = sorted((i for i in remaining if set(items[i]['depends_on']) <= done), key=position.get)
        if not layer:
            raise CycleError('dependency cycle among ' + ', '.join(sorted(remaining, key=position.get)))
        layers.append(layer)
        order += layer
        done |= set(layer)
        remaining -= set(layer)
    blocked = {}
    for identifier in order:
        item = items[identifier]
        if item['disposition'] is None:
            failed = [d for d in item['depends_on']
                      if items[d]['disposition'] in NOT_OK or d in blocked]
            if failed:
                blocked[identifier] = failed
    unsettled = [i for i in order if items[i]['disposition'] is None and i not in blocked]
    return {'order': order, 'layers': layers, 'next': unsettled, 'blocked': blocked}


def beat_items(record, beat):
    claimed = {c['item'] for c in beat['claims']}
    return [i for i in record['items'] if i['beat'] == beat['id'] or i['id'] in claimed]


def beat_verdict(record, beat):
    """The computed verdict and its reasons; the order is failed, unverified, visual_qa, verified."""
    rehearsals = {}
    for rehearsal in record.get('rehearsals', []):
        rehearsals[rehearsal['flip']] = rehearsal['result']  # the last rehearsal of a flip counts
    reasons = {verdict: [] for verdict in VERDICTS}
    for claim in beat['claims']:
        result = claim.get('result')
        if result == 'failed':
            reasons['failed'].append('claim failed: ' + claim['text'][:60])
        elif result is None:
            reasons['unverified'].append('claim has no result: ' + claim['text'][:60])
    for flip in beat.get('flips', []):
        result = rehearsals.get(flip)
        if result == 'failed':
            reasons['failed'].append(flip + ' rehearsal failed')
        elif result is None:
            reasons['unverified'].append(flip + ' has no rehearsal result')
        elif result == 'not_rehearsable':
            reasons['visual_qa'].append(flip + ' could not be rehearsed safely')
    for item in beat_items(record, beat):
        if item['disposition'] not in SETTLED_OK:
            reasons['unverified'].append(item['id'] + ' is ' + str(item['disposition']))
        elif item['visual_qa']:
            reasons['visual_qa'].append(item['id'] + ' awaits visual QA')
    for verdict in ('failed', 'unverified', 'visual_qa'):
        if reasons[verdict]:
            return verdict, reasons[verdict]
    return 'verified', []


def overall(record, base):
    """Beat-aware Overall for complex tasks; simple tasks keep the item-only Overall."""
    if not record.get('complex') or not record.get('story'):
        return base
    verdicts = {beat_verdict(record, b)[0] for b in record['story']['beats']}
    if base == 'UNRESOLVED' or verdicts & {'failed', 'unverified'}:
        return 'UNRESOLVED'
    if base == 'FINISHED_WITH_EXCEPTIONS' or 'visual_qa' in verdicts:
        return 'FINISHED_WITH_EXCEPTIONS'
    return base


def beats_line(record):
    if not record.get('complex') or not record.get('story'):
        return None
    return 'Beats: ' + '; '.join('%s %s' % (b['id'], beat_verdict(record, b)[0]) for b in record['story']['beats'])


def _evidence(folder, reference):
    path = (folder / reference)
    if Path(reference).is_absolute() or '..' in Path(reference).parts:
        raise ValueError('evidence_ref must stay inside the folder')
    if any((folder / Path(*Path(reference).parts[:n])).is_symlink() for n in range(1, len(Path(reference).parts) + 1)):
        raise ValueError('evidence_ref symlink refused')
    if not path.is_file():
        raise ValueError('evidence_ref file missing')
    return json.loads(path.read_text(encoding='utf-8'))


def _assessor():
    spec = importlib.util.spec_from_file_location('scout_agentforce_evidence', Path(__file__).with_name('agentforce_evidence.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evidence_findings(folder, item):
    """X9: Flow and Agentforce items reference their contract's mandatory evidence."""
    kind = re.sub(r'[\s_-]', '', item['type']).lower()
    settled = item['disposition'] in SETTLED_OK
    if kind == 'flow':
        flow = item.get('flow_validation')
        if flow is None:
            return ['Flow item records no frozen flow_validation']
        if flow['mode'] == 'flow_test_required' and not flow.get('required_tests'):
            return ['flow_test_required needs every required test named']
        if flow['mode'] == 'unsupported':
            if not _text(flow.get('unsupported_reason')):
                return ['unsupported Flow validation needs its frozen reason']
            if item['disposition'] == 'applied' and not item['visual_qa']:
                return ['an unsupported Flow validation stays awaiting visual QA']
            return []
        if not settled:
            return []
        try:
            evidence = _evidence(folder, item.get('evidence_ref', ''))
        except (OSError, ValueError, UnicodeError) as error:
            return [str(error)]
        results = {r.get('test'): r for r in evidence.get('flow_tests', []) if isinstance(r, dict)}
        problems = []
        for test in flow['required_tests']:
            row = results.get(test)
            if row is None:
                problems.append('required Flow test %s has no result' % test)
            elif row.get('outcome') != 'Pass' or row.get('flow_api_name') != flow['flow_api_name'] or row.get('version') != flow.get('version'):
                problems.append('Flow test %s did not pass on the frozen flow and version' % test)
        return problems
    if kind in ('agentforce', 'agent', 'agentforceagent'):
        obligations = item.get('obligations')
        if not obligations:
            return ['Agentforce item records no obligations']
        if not settled:
            return []
        try:
            evidence = _evidence(folder, item.get('evidence_ref', ''))
            assessor, gate = _assessor(), GATE.read_bytes()
        except (OSError, ValueError, UnicodeError) as error:
            return [str(error)]
        contexts = {c.get('item_id'): c for c in evidence.get('agent_contexts', []) if isinstance(c, dict)}
        runtimes = evidence.get('agent_runtime', {}) if isinstance(evidence.get('agent_runtime'), dict) else {}
        problems = []
        for obligation in obligations:
            context, runtime = contexts.get(obligation['id']), runtimes.get(obligation['id'])
            if context is None or runtime is None:
                problems.append('obligation %s has no evidence' % obligation['id'])
                continue
            result = assessor.assess(obligation['agent_runtime'], context, runtime, gate)
            if result.get('assessment') != 'PASS':
                problems.append('obligation %s: %s' % (obligation['id'], result.get('reason', 'not passed')))
        return problems
    return []


def write_order_findings(record, positions):
    """X22 and C8 `plan`: no attempt before its prerequisites settled, in log order."""
    items = {i['id']: i for i in record['items']}
    problems = []
    for item in items.values():
        if not item['attempts']:
            continue
        first = min((positions.get(a) for a in item['attempts'] if positions.get(a) is not None), default=None)
        for dependency in item['depends_on']:
            prerequisite = items.get(dependency)
            if prerequisite is None:
                continue
            if prerequisite['disposition'] not in SETTLED_OK:
                problems.append('%s was attempted while its prerequisite %s is %s' % (item['id'], dependency, prerequisite['disposition']))
                continue
            last = max((positions.get(a) for a in prerequisite['attempts'] if positions.get(a) is not None), default=None)
            if first is not None and last is not None and last > first:
                problems.append('%s was attempted before its prerequisite %s settled' % (item['id'], dependency))
    return problems


def check_findings(record, folder, positions):
    """All W10 rules as (rule, message) pairs. Simple tasks are checked only for evidence and order."""
    findings = [('plan', m) for m in write_order_findings(record, positions)]
    try:
        plan(record)
    except CycleError as error:
        findings.append(('plan', str(error)))
    for item in record['items']:
        findings += [('evidence-ref', item['id'] + ': ' + m) for m in evidence_findings(folder, item)]
    if not record.get('complex'):
        return findings
    story = record.get('story')
    if not story or not story['beats']:
        return findings + [('story', 'a complex task needs story beats')]
    for beat in story['beats']:
        if beat['proof_moment'] and any(c.get('result') == 'dropped' for c in beat['claims']):
            findings.append(('story', beat['id'] + ' drops a required proof-moment claim'))
        verdict, reasons = beat_verdict(record, beat)
        recorded = (beat.get('verification') or {}).get('verdict')
        if recorded is None:
            findings.append(('beat', beat['id'] + ' has no recorded verification'))
        elif recorded != verdict:
            findings.append(('beat', '%s records %s but its evidence gives %s (%s)' % (beat['id'], recorded, verdict, '; '.join(reasons[:3]))))
    return findings
