#!/usr/bin/env python3
"""Complex-plan rules for /scout (W10): write order, readiness, job settlement, beat verdicts, evidence references.

Pure functions over a parsed scout-items record and the task log's checkpoints; `scout_history.py` calls them for
`plan`, `render` and `check`. Standard library only, Python 3.9 or newer, and safe under -S.
"""
from datetime import datetime, timedelta, timezone
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
FLOW_FAILURES = ('Fail', 'Error', 'Skip')
GATE = Path(__file__).resolve().parents[1] / 'prompts/building/agentforce-validation-gate.md'
UNAVAILABLE_INVOCATION = 'current invocation evidence is unavailable'  # agentforce_evidence.py's reason, pinned by a test
EVIDENCE_LIMIT = 4 * 1024 * 1024

# F7: W3's autonomous type table; scout_history.py hands over its own, so the two never drift.
KNOWN_TYPES, TYPE_ALIASES = frozenset(), {}

# C3: type families by keyword, first match wins, so no spelling bypasses a type-conditioned rule.
FAMILIES = (('flow', ('flow',)), ('agentforce', ('agent', 'bot', 'genai', 'aiauthoring')), ('apex', ('apex', 'trigger')),
            ('lwc', ('lwc', 'lightningcomponentbundle', 'lightningwebcomponent')), ('emailtocase', ('emailtocase', 'casesettings')))
GATED = tuple(name for name, _ in FAMILIES)

# F14: sections the change-log template asks for whenever an item of the family was attempted.
TYPE_SECTIONS = {'flow': ('Flows Deployed', 'Execution Order Check'), 'apex': ('Apex Deployed',), 'lwc': ('LWC Deployed',),
                 'agentforce': ('Agentforce Deployed', 'Agentforce Current-Test Evidence'),
                 'businessprocess': ('Business Processes Deployed',), 'pathassistant': ('Paths Deployed',)}  # R3-F6

# F2: each executor family's explicit terminal vocabulary. Job IDs key by prefix; submissions without one by item family.
JOB_ID = re.compile(r'(?<![A-Za-z0-9])(?:0Af|750)[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?(?![A-Za-z0-9])')
VOCABULARY = {'0Af': ('Metadata API deploy', ('Succeeded', 'SucceededPartial', 'Failed', 'Canceled')),
              '750': ('Bulk job', ('JobComplete', 'Failed', 'Aborted')),
              'agentforce': ('Agentforce publish', ('Active', 'Inactive', 'NeedsUICommit', 'Failed')),
              'emailtocase': ('Email-to-Case apply script', ('Completed', 'Failed'))}
FIELD = re.compile(r'(?i)^[ \t]*(?:[-*+][ \t]*)?(job|status|launched|settled)[ \t]*:[ \t]*(.*)$')
PART = re.compile(r'(?i)^[ \t]*(status|launched|settled)[ \t]*:[ \t]*(.*?)[ \t]*$')
ISO = re.compile(r'(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d):(\d\d)(?:[.,](\d{1,9}))?(Z|[+-]\d\d:?\d\d)?')
ORG_ID = re.compile(r'(?<![A-Za-z0-9])00D[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?(?![A-Za-z0-9])')
BINDING = re.compile(r'(?i)^[ \t]*(?:[-+][ \t]+)?(?:bound|binding|target|org)\b[^:\r\n]*:(.*)$')
BINDING_SECTION = re.compile(r'(?i)^#{2,6}[ \t]+(?:bound|binding|target|org)\b')


class CycleError(ValueError):
    pass


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _positive(value):
    """F10: a version is a positive integer, never a bool or a float."""
    return type(value) is int and value > 0


def family(item_type):
    """C3: the item's type family (flow, agentforce, apex, lwc, emailtocase), or its letters for any other type."""
    kind = re.sub(r'[^a-z]', '', item_type.lower())
    for name, keys in FAMILIES:
        if any(key in kind.replace('workflow', '') for key in keys):
            return name
    return kind


def autonomous(item):
    """F7: a type outside every gated family that W3 lists as known; anything else is gated or Docs-gated."""
    kind = re.sub(r'[^a-z]', '', item['type'].lower())
    return family(item['type']) not in GATED and TYPE_ALIASES.get(kind, kind) in KNOWN_TYPES


def derived_complex(record):
    """F7: three or more items, or any gated or Docs-gated type."""
    return len(record['items']) >= 3 or not all(autonomous(i) for i in record['items'])


def is_complex(record):
    """F7: complexity is derived, never trusted; `"complex":true` can add it but `false` can't remove it."""
    return record.get('complex') is True or derived_complex(record)


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
            if 'required' in claim and type(claim['required']) is not bool:
                raise ValueError('invalid claim required flag')
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
        if 'agent_version' in item and not _text(item['agent_version']):
            raise ValueError('invalid agent_version')
        if any('attempt' in entry and not _text(entry['attempt']) for entry in item['grounding']):
            raise ValueError('invalid grounding attempt')
        if 'flow_validation' in item:
            flow = item['flow_validation']
            tests = flow.get('required_tests', []) if isinstance(flow, dict) else None
            if (not isinstance(flow, dict) or not _text(flow.get('flow_api_name')) or flow.get('mode') not in FLOW_MODES
                    or not isinstance(tests, list) or any(not _text(t) for t in tests) or len(set(tests)) != len(tests)
                    or (flow['mode'] == 'unsupported' and tests)
                    or any(key in flow and not _positive(flow[key]) for key in ('version', 'active_version'))
                    or ('unsupported_reason' in flow and not isinstance(flow['unsupported_reason'], str))):
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


# ---- Jobs, settlement and the serial write slot (X5, F1-F3) ----

def _moment(value):
    """F3: an ISO time with seconds, optionally zoned; None when malformed."""
    match = ISO.fullmatch(re.sub(r'\s*\([^()]*\)$', '', value.strip()))
    if not match:
        return None
    year, month, day, hour, minute, second = (int(match[n]) for n in range(1, 7))
    offset = 0
    if match[8] not in (None, 'Z'):
        hours, minutes = int(match[8][1:3]), int(match[8][-2:])
        if hours > 23 or minutes > 59:  # R2-F11: +00:90 is not an offset
            return None
        offset = int(match[8][0] + '1') * (hours * 60 + minutes)
    try:
        zone = timezone(timedelta(minutes=offset)) if match[8] else None
        moment = datetime(year, month, day, hour, minute, second, int((match[7] or '0').ljust(6, '0')[:6]), zone)
        if zone:
            moment.astimezone(timezone.utc)  # R3-F7: out of range in UTC is malformed, never a crash
        return moment
    except (ValueError, OverflowError):
        return None


def _word(value):
    """A status field's value: one word, an optional trailing parenthetical, no markup."""
    value = re.sub(r'\s*\([^()]*\)$', '', (value or '').strip()).strip(' .')
    return value if re.fullmatch(r'\w+', value) else value or None


def _fields(text):
    """`job:` lines (their IDs and inline fields) and checkpoint-level status, launched and settled, fences included."""
    lines, level = [], {}
    for line in text.splitlines():
        match = FIELD.match(re.sub(r'[*`]', '', line))
        if not match:
            continue
        parts = re.split(r'\s*[;·|,]\s*|\s+(?=(?:status|launched|settled)\s*:)', match[2], flags=re.I)
        entry = level if match[1].lower() != 'job' else {'ref': parts[0].strip(), 'ids': [m[0] for m in JOB_ID.finditer(parts[0])]}
        if entry is level:
            level[match[1].lower()] = parts[0].strip()
        for part in parts[1:]:
            field = PART.match(part)
            if field:
                entry[field[1].lower()] = field[2]
        if entry is not level:
            lines.append(entry)
    return lines, level


def checkpoint_state(checkpoint, item):
    """F1-F3: one checkpoint's jobs and submissions, whether each settled, its times and its format problems.

    Job lines, their fields and job IDs count wherever they appear, fences included (R2-F1: a fenced receipt
    is still a submission). Settlement is positive: a terminal word from the family's vocabulary in a `status:`
    field on the same checkpoint. Checkpoint-level fields apply to a lone job. A submission without an ID takes
    its item's family, or its own label's when no item owns the attempt (`pending`, on another task's log).
    """
    kind = family(item['type']) if item else ''
    lines, level = _fields(checkpoint['raw'])
    jobs, problems = {}, []

    def entry(key, ref, vocabulary, explicit=False):
        job = jobs.setdefault(key, {'ref': ref, 'vocabulary': vocabulary, 'status': None, 'launched': None, 'settled': None,
                                    'explicit': False})
        job['explicit'] |= explicit  # recorded on a `job:` line, not only mentioned
        return job
    for number, line in enumerate(lines):  # R3-F1: an executor label is no identity; each such line is its own submission
        targets = [entry(i[:15], i, i[:3], True) for i in line['ids']] or [
            entry('~%d:%s' % (number, line['ref'].lower()), line['ref'] or 'submission', kind or family(line['ref']), True)]
        for job in targets:
            for key in ('status', 'launched', 'settled'):
                if line.get(key):
                    job[key] = line[key]
    for match in JOB_ID.finditer(checkpoint['raw']):
        entry(match[0][:15], match[0], match[0][:3])
    for key in ('launched', 'settled'):
        for job in jobs.values():
            job[key] = job[key] or level.get(key)
    if len(jobs) == 1 and level.get('status'):
        job = next(iter(jobs.values()))
        job['status'] = job['status'] or level['status']
    for key, text in [('launched', level.get('launched'))] + [(k, j[k]) for j in jobs.values() for k in ('launched', 'settled')]:
        if text and _moment(text) is None:
            problems.append('%s: %s: "%s" is not an ISO time with seconds' % (checkpoint['attempt'], key, text))
    for job in jobs.values():
        name, words = VOCABULARY.get(job['vocabulary'], (None, ()))
        status = _word(job['status'])
        job['terminal'] = any(status is not None and status.lower() == w.lower() for w in words)
        if job['status'] is None:
            job['why'] = 'no status: field'
        elif name is None:
            job['why'] = 'a submission without its job ID'
        elif not job['terminal']:
            job['why'] = 'status %s is not terminal for a %s (%s)' % (job['status'], name, '|'.join(words))
        job['launched_at'] = _moment(job['launched']) if job['launched'] else None
        job['settled_at'] = _moment(job['settled']) if job['settled'] and job['terminal'] else None
        if job['launched'] is None:
            problems.append('%s records job %s without a launched: time' % (checkpoint['attempt'], job['ref']))
        if job['terminal'] and job['settled'] is None:
            problems.append('%s settled job %s without a settled: time' % (checkpoint['attempt'], job['ref']))
        if job['launched_at'] and job['settled_at'] and _comparable(job['launched_at'], job['settled_at']) and job['settled_at'] < job['launched_at']:
            problems.append('%s says job %s settled before it launched' % (checkpoint['attempt'], job['ref']))
    return {'attempt': checkpoint['attempt'], 'position': checkpoint['position'], 'outcome': checkpoint.get('outcome'),
            'stamp': checkpoint['stamp'], 'jobs': jobs, 'problems': problems, 'open': [j for j in jobs.values() if not j['terminal']],
            'launched': _moment(level['launched']) if level.get('launched') else None}


def _comparable(*moments):
    return len({m.tzinfo is None for m in moments if m is not None}) <= 1


def _sort_key(moment):
    return moment.replace(tzinfo=None) if moment.tzinfo is None else moment.astimezone(timezone.utc).replace(tzinfo=None)


def _start(state, exclude):
    """When an attempt started, as (earliest, latest): its own jobs' launch, else its `launched:`, else its heading minute.

    Jobs it shares with the holder are excluded, so a retry that cites an earlier attempt's job isn't dated by it.
    """
    own = [j['launched_at'] for key, j in state['jobs'].items() if key not in exclude]
    if own and all(own):
        first = min(own, key=_sort_key)
        return first, first
    if not own and state['launched']:
        return state['launched'], state['launched']
    try:
        heading = datetime.strptime(state['stamp'], '%Y-%m-%d %H:%M')
    except ValueError:
        return None
    return heading, heading + timedelta(seconds=59, microseconds=999999)


def _slot(job):
    """F3: a job's hold on the write slot, (launched, settled), settled None while open; None when unknown."""
    if not job['launched_at']:
        return None
    if not job['terminal']:
        return job['launched_at'], None
    return (job['launched_at'], job['settled_at']) if job['settled_at'] else None


def _within(slot, window):
    """F3: True when a start window certainly falls inside a slot, False when certainly not, None if unknown."""
    begin, end = slot
    earliest, latest = window
    if not _comparable(begin, earliest, end):
        return None
    if earliest >= begin and (end is None or latest < end):
        return True
    if latest < begin or (end is not None and earliest >= end):
        return False
    return None


def _starts(state, holder_state, holder):
    """F3 and R2-F3: what in `state` claims the slot, as (who, window): each of its own jobs' launch, or for an
    attempt that records no job of its own its start. The holder's job, cited again by a later attempt, is the
    same job. Only an attempt that records no submission and is already_satisfied wrote nothing."""
    shared = {k for k in holder_state['jobs'] if not k.startswith('~')} if state is not holder_state else set()  # R3-F2
    own = [j for k, j in state['jobs'].items() if j is not holder and k not in shared]
    if own:
        name = (lambda j: '%s (job %s)' % (state['attempt'], j['ref'])) if state is holder_state else (lambda j: state['attempt'])
        return [(name(j), (j['launched_at'], j['launched_at']) if j['launched_at'] else None) for j in own]
    if state is holder_state or (state['outcome'] == 'already_satisfied' and not state['jobs']):
        return []
    return [(state['attempt'], _start(state, shared))]


def job_findings(record, checkpoints):
    """X5 and F1-F3: settlement, launch and settle times, and the one serial write slot across every attempt."""
    owners = {a: i for i in record['items'] for a in i['attempts']}
    states = [checkpoint_state(c, owners.get(c['attempt'])) for c in checkpoints]
    problems = [p for s in states for p in s['problems']]
    moments = [m for s in states for j in s['jobs'].values() for m in (j['launched_at'], j['settled_at']) if m]
    moments += [s['launched'] for s in states if s['launched']]
    if not _comparable(*moments):
        problems.append('launched: and settled: times mix zoned and local times; use one form')
    for state in states:
        item = owners.get(state['attempt'])
        if state['jobs'] and (state['outcome'] == 'already_satisfied' or (item and item['disposition'] == 'already_satisfied')):
            problems.append('%s records a submission (%s), so it wrote; already_satisfied means nothing was written'
                            % (state['attempt'], next(iter(state['jobs'].values()))['ref']))  # R3-C2
        if item and item['disposition'] in ('applied', 'already_satisfied', 'failed') and state['open']:
            job = state['open'][0]
            problems.append('%s is %s, but attempt %s has an unsettled job (%s: %s); it stays unverified until a terminal status'
                            % (item['id'], item['disposition'], state['attempt'], job['ref'], job.get('why', 'not terminal')))
    for holder_state in states:
        for holder in holder_state['jobs'].values():
            slot = _slot(holder)
            for state in states:
                if state is not holder_state and state['attempt'] == holder_state['attempt']:
                    continue
                for who, window in _starts(state, holder_state, holder):
                    inside = _within(slot, window) if slot and window else None
                    if inside is None:  # unknown: an open job holds the slot against everything logged after it
                        inside = not holder['terminal'] and state['position'] > holder_state['position']
                    if inside and not holder['terminal']:
                        problems.append('%s left job %s non-terminal, yet %s started after it' % (holder_state['attempt'], holder['ref'], who))
                    elif inside:
                        problems.append("%s launched before %s's job %s settled (%s)" % (who, holder_state['attempt'], holder['ref'], holder['settled']))
    return list(dict.fromkeys(problems))


def open_jobs(record, checkpoints):
    """C1: every job this task's log hasn't settled, with its attempt and item."""
    owners = {a: i for i in record['items'] for a in i['attempts']}
    result = []
    for checkpoint in checkpoints:
        item = owners.get(checkpoint['attempt'])
        for job in checkpoint_state(checkpoint, item)['open']:
            result.append({'attempt': checkpoint['attempt'], 'item': item['id'] if item else None, 'job': job['ref']})
    return result


# ---- Plan and write order (C3, C1, X22, F4) ----

def order(record):
    """The topological write order of depends_on and the authoring layers; CycleError on a cycle or unknown ID."""
    items = {i['id']: i for i in record['items']}
    position = {identifier: n for n, identifier in enumerate(items)}
    for item in items.values():
        for dependency in item['depends_on']:
            if dependency not in items:
                raise CycleError(item['id'] + ' has unknown dependency ' + dependency)
    result, layers, done = [], [], set()
    remaining = set(items)
    while remaining:
        layer = sorted((i for i in remaining if set(items[i]['depends_on']) <= done), key=position.get)
        if not layer:
            raise CycleError('dependency cycle among ' + ', '.join(sorted(remaining, key=position.get)))
        layers.append(layer)
        result += layer
        done |= set(layer)
        remaining -= set(layer)
    return result, layers


def plan(record, checkpoints=()):
    """Write order, authoring layers, the blocked and unsettled remainder, open jobs, and what is ready to write.

    C1: `ready` holds unattempted items whose prerequisites are all applied or already_satisfied, and is empty
    while any job is open; `next` stays the whole unsettled remainder.
    """
    items = {i['id']: i for i in record['items']}
    write_order, layers = order(record)
    blocked = {}
    for identifier in write_order:
        item = items[identifier]
        if item['disposition'] is None:
            failed = [d for d in item['depends_on'] if items[d]['disposition'] in NOT_OK or d in blocked]
            if failed:
                blocked[identifier] = failed
    unsettled = [i for i in write_order if items[i]['disposition'] is None and i not in blocked]
    jobs = open_jobs(record, checkpoints)
    ready = [] if jobs else [i for i in unsettled if not items[i]['attempts']
                             and all(items[d]['disposition'] in SETTLED_OK for d in items[i]['depends_on'])]
    return {'order': write_order, 'layers': layers, 'next': unsettled, 'blocked': blocked, 'open_jobs': jobs, 'ready': ready}


def _states(record, checkpoints):
    """Each attempt's first checkpoint, parsed by checkpoint_state with its owning item."""
    owners = {a: i for i in record['items'] for a in i['attempts']}
    states = {}
    for checkpoint in checkpoints:
        if checkpoint['attempt'] not in states:
            states[checkpoint['attempt']] = checkpoint_state(checkpoint, owners.get(checkpoint['attempt']))
    return states


def _earliest(windows):
    """The earliest of several (earliest, latest) windows, as one window; None when any is unknown or incomparable."""
    if not windows or not all(windows) or not _comparable(*(w[0] for w in windows)):
        return None
    return min((w[0] for w in windows), key=_sort_key), min((w[1] for w in windows), key=_sort_key)


def _settle(state):
    """When an attempt's work settled, as a window: its last job's terminal time, else (synchronous) its start."""
    if state['jobs']:
        settled = [j['settled_at'] for j in state['jobs'].values()]
        return (max(settled, key=_sort_key),) * 2 if all(settled) and _comparable(*settled) else None
    return _start(state, set())


def _chronology(item, states):
    """R2-F5 and R3-F3: an item's attempts in the order they ran. Each pair whose recorded start windows are comparable
    and disjoint is ordered by time; every other pair keeps log order. Uncertain or incomparable windows never
    disable a certain comparison, nor turn an earliest possible time into a definite order."""
    present = sorted((a for a in item['attempts'] if a in states), key=lambda a: states[a]['position'])
    windows = {a: _start(states[a], set()) for a in present}

    def before(x, y):
        wx, wy = windows[x], windows[y]
        return bool(wx and wy and _comparable(wx[0], wy[0]) and wx[1] < wy[0])
    after = {a: {b for b in present if b != a and before(b, a)} for a in present}
    order, done = [], set()
    while len(order) < len(present):
        ready = [a for a in present if a not in done and after[a] <= done] or [a for a in present if a not in done]
        order.append(ready[0])  # log order among the attempts whose certain predecessors have run
        done.add(ready[0])
    return order


def write_order_findings(record, checkpoints):
    """X22, F4 and R2-F4: a dependent's first attempt starts after its prerequisite's first settling attempt settled.
    Recorded times decide when they are certain; log position decides the rest."""
    items = {i['id']: i for i in record['items']}
    states = _states(record, checkpoints)
    problems = []
    for item in items.values():
        if not item['attempts']:
            continue
        mine = [states[a] for a in item['attempts'] if a in states]
        for dependency in item['depends_on']:
            prerequisite = items.get(dependency)
            if prerequisite is None:
                continue
            if prerequisite['disposition'] not in SETTLED_OK:
                problems.append('%s was attempted while its prerequisite %s is %s' % (item['id'], dependency, prerequisite['disposition']))
                continue
            settling = [states[a] for a in prerequisite['attempts'] if a in states and states[a]['outcome'] in SETTLED_OK]
            if not mine or not settling:
                continue
            start, settled = _earliest([_start(s, set()) for s in mine]), _earliest([_settle(s) for s in settling])
            early = None
            if start and settled and _comparable(start[0], settled[0]):
                early = True if start[1] < settled[0] else False if start[0] >= settled[1] else None
            if early is None:
                early = min(s['position'] for s in settling) > min(s['position'] for s in mine)
            if early:
                problems.append('%s was attempted before its prerequisite %s settled' % (item['id'], dependency))
    return problems


def retry_findings(record, checkpoints):
    """RB3, F5 and R2-F5: a retry, the attempt that ran next after a failed one on the same item, cites its covering
    lesson or Docs search. The attempts array lists them in the order they ran, as W3's last-outcome rule assumes."""
    states = _states(record, checkpoints)
    problems = []
    for item in record['items']:
        chronology = _chronology(item, states)
        listed = [a for a in item['attempts'] if a in states]
        if listed != chronology:
            problems.append('%s lists attempts %s, but its checkpoints ran %s; list them in the order they ran'
                            % (item['id'], ', '.join(listed), ', '.join(chronology)))
        for previous, attempt in zip(chronology, chronology[1:]):
            if states[previous]['outcome'] != 'failed':
                continue
            if not any(e.get('attempt') == attempt and e['source'] in ('lesson', 'docs') and e['ref'].strip() for e in item['grounding']):
                problems.append('%s retried in %s after failed %s without a grounding entry {"attempt":"%s"} citing the covering '
                                'lesson or the Docs search of the verbatim error (source lesson or docs, with its ref)'
                                % (item['id'], attempt, previous, attempt))
        for entry in item['grounding']:
            if 'attempt' in entry and entry['attempt'] not in item['attempts']:
                problems.append('%s grounding names %s, which is not one of its attempts' % (item['id'], entry['attempt']))
    return problems


# ---- Beats and the beat-aware Overall (X1, X2, X21, F6, F8, F9) ----

def _active(claim):
    """F9 and C6: a dropped claim marked `"required":false` is history, not an obligation; claims default to required."""
    return not (claim.get('result') == 'dropped' and claim.get('required') is False)


def beat_items(record, beat):
    claimed = {c['item'] for c in beat['claims'] if _active(c)}
    return [i for i in record['items'] if i['beat'] == beat['id'] or i['id'] in claimed]


def beat_verdict(record, beat):
    """The computed verdict and its reasons; the order is failed, unverified, visual_qa, verified."""
    rehearsals = {}
    for rehearsal in record.get('rehearsals', []):
        rehearsals[rehearsal['flip']] = rehearsal  # the last rehearsal of a flip counts
    reasons = {verdict: [] for verdict in VERDICTS}
    if not _text((beat.get('verification') or {}).get('evidence')):
        reasons['unverified'].append(beat['id'] + ' records no verification evidence')
    if beat.get('proof_moment') and not any(_active(c) for c in beat['claims']):  # R2-F2: withdrawal never erases the proof
        reasons['unverified'].append(beat['id'] + ' is the proof moment but has no active claim')
    items = {i['id']: i for i in record['items']}
    for claim in beat['claims']:
        result = claim.get('result')
        if _active(claim) and (claim.get('item') not in items or not _text(items[claim['item']].get('readback'))):
            reasons['unverified'].append('claim has no existing item with a read-back: ' + claim['text'][:60])  # R3-F5
        if result == 'failed':
            reasons['failed'].append('claim failed: ' + claim['text'][:60])
        elif result is None:
            reasons['unverified'].append('claim has no result: ' + claim['text'][:60])
        elif result == 'dropped' and _active(claim):
            reasons['unverified'].append('required claim dropped: ' + claim['text'][:60])
    for flip in beat.get('flips', []):
        rehearsal = rehearsals.get(flip)
        result = rehearsal['result'] if rehearsal else None
        if result == 'failed':
            reasons['failed'].append(flip + ' rehearsal failed')
        elif result is None:
            reasons['unverified'].append(flip + ' has no rehearsal result')
        elif result == 'not_rehearsable':
            reasons['visual_qa'].append(flip + ' could not be rehearsed safely')
        elif not _text(rehearsal['evidence']):
            reasons['unverified'].append(flip + ' passed without rehearsal evidence')
    for item in beat_items(record, beat):
        if item['disposition'] not in SETTLED_OK:
            reasons['unverified'].append(item['id'] + ' is ' + str(item['disposition']))
        elif item['visual_qa']:
            reasons['visual_qa'].append(item['id'] + ' awaits visual QA')
    for verdict in ('failed', 'unverified', 'visual_qa'):
        if reasons[verdict]:
            return verdict, reasons[verdict]
    return 'verified', []


def beats(record):
    """F8: the one computation of beat verdicts that `render`, Overall and `check` all use; None for a simple task."""
    if not is_complex(record):
        return None
    return [(b['id'],) + beat_verdict(record, b) for b in (record.get('story') or {}).get('beats') or []]


def overall(record, base):
    """X2 and F8: a failed or unverified beat, or a complex task without beats, is UNRESOLVED; visual QA is an exception."""
    verdicts = beats(record)
    if verdicts is None:
        return base
    found = {verdict for _, verdict, _ in verdicts}
    if base == 'UNRESOLVED' or not verdicts or found & {'failed', 'unverified'}:
        return 'UNRESOLVED'
    if base == 'FINISHED_WITH_EXCEPTIONS' or 'visual_qa' in found:
        return 'FINISHED_WITH_EXCEPTIONS'
    return base


def beats_line(record):
    verdicts = beats(record)
    if verdicts is None:
        return None
    return 'Beats: ' + ('; '.join('%s %s' % (identifier, verdict) for identifier, verdict, _ in verdicts) or 'none recorded')


# ---- Evidence references (X9, C2, C5, F10-F13, F15) ----

def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('evidence file repeats key ' + key)
        result[key] = value
    return result


def _evidence(folder, reference):
    path = (folder / reference)
    if Path(reference).is_absolute() or '..' in Path(reference).parts:
        raise ValueError('evidence_ref must stay inside the folder')
    if any((folder / Path(*Path(reference).parts[:n])).is_symlink() for n in range(1, len(Path(reference).parts) + 1)):
        raise ValueError('evidence_ref symlink refused')
    if not reference or not path.is_file():
        raise ValueError('evidence_ref file missing')
    if path.stat().st_size > EVIDENCE_LIMIT:
        raise ValueError('evidence_ref file is larger than 4 MiB')
    try:
        return json.loads(path.read_bytes().decode('utf-8'), object_pairs_hook=_unique,
                          parse_constant=lambda name: (_ for _ in ()).throw(ValueError('evidence file uses ' + name)))
    except RecursionError:
        raise ValueError('evidence file nests too deeply') from None
    except json.JSONDecodeError as error:
        raise ValueError('evidence file is not JSON: ' + error.msg) from None


def _assessor():
    spec = importlib.util.spec_from_file_location('scout_agentforce_evidence', Path(__file__).with_name('agentforce_evidence.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bound_orgs(task_visible):
    """C2, R2-F8 and R3-F4: the org IDs of the task record's binding, outside fences, as 15-character keys.

    The binding is where Scout records it: a header line, before the first `##` section, whose label starts with
    Bound, Binding, Target or Org (as `pending` reads a folder's org); or any line of a section so titled. Every
    other section (the request, amendments, provenance) and every quote is ignored, whatever its lines say.
    """
    found, section = set(), 'header'
    for line in task_visible.splitlines():
        heading = re.match(r'^(#{1,6})[ \t]+\S', line)
        if heading:
            if len(heading[1]) >= 2:
                section = 'binding' if BINDING_SECTION.match(line) else 'other'
            continue
        text = re.sub(r'[*_`]', '', line)
        if text.lstrip().startswith('>'):
            continue
        if section == 'binding' or (section == 'header' and BINDING.match(text)):
            found |= {m[0][:15] for m in ORG_ID.finditer(text)}
    return sorted(found)


def _flow_findings(folder, item, orgs):
    flow = item.get('flow_validation')
    if flow is None:
        return ['Flow item records no frozen flow_validation']
    if flow['mode'] == 'flow_test_required' and not flow.get('required_tests'):
        return ['flow_test_required needs every required test named']
    if flow['mode'] == 'unsupported' and not _text(flow.get('unsupported_reason')):
        misplaced = ' (a sibling unsupported_reason is misplaced)' if 'unsupported_reason' in item else ''
        return ['unsupported Flow validation needs its frozen reason inside flow_validation' + misplaced]
    if item['disposition'] not in SETTLED_OK:
        return []
    carries = '' if item['disposition'] == 'applied' else '; already_satisfied cannot carry visual QA'
    if not _positive(flow.get('version')):
        return ['Flow item records no positive integer version']
    if flow['mode'] == 'unsupported':
        return [] if item['visual_qa'] and not carries else ['an unsupported Flow validation stays awaiting visual QA' + carries]
    try:
        evidence = _evidence(folder, item.get('evidence_ref', ''))
    except (OSError, ValueError, UnicodeError) as error:
        return [str(error)]
    rows = evidence.get('flow_tests') if isinstance(evidence, dict) else None
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        return ['evidence file needs a "flow_tests" list of objects']
    required = set(flow['required_tests'])
    for n, row in enumerate(rows, 1):  # R2-F9: rows beyond the required ones still need their shape; required rows meet their contract below
        if isinstance(row.get('test'), str) and row['test'] in required:
            continue
        if (not _text(row.get('test')) or not _text(row.get('flow_api_name')) or not _positive(row.get('version'))
                or not (isinstance(row.get('org_id'), str) and ORG_ID.fullmatch(row['org_id']))):
            return ['flow_tests row %d needs a test, a flow_api_name, a positive integer version and an org_id' % n]
    if len(orgs) != 1:
        return ['the task record names %d bound org IDs; state the binding once, as a header line such as '
                '"Target: <alias> · <username> · <org ID>" or in a "Target" section' % len(orgs)]
    problems, unavailable = [], []
    for test in flow['required_tests']:
        matches = [r for r in rows if r.get('test') == test]
        if len(matches) != 1:
            problems.append('required Flow test %s has %s' % (test, '%d rows; keep one current result' % len(matches) if matches else 'no result'))
            continue
        row = matches[0]
        org = row.get('org_id')
        if row.get('flow_api_name') != flow['flow_api_name'] or not _positive(row.get('version')) or row['version'] != flow['version']:
            problems.append('Flow test %s did not run on the frozen flow and version %d' % (test, flow['version']))
        elif not (isinstance(org, str) and ORG_ID.fullmatch(org) and org[:15] == orgs[0]):
            problems.append('Flow test %s names org %s, not the bound org %s' % (test, org, orgs[0]))
        elif row.get('outcome') == 'unavailable':
            if _text(row.get('reason')):
                unavailable.append(test)
            else:
                problems.append('Flow test %s is unavailable without its reason' % test)
        elif row.get('outcome') in FLOW_FAILURES:
            problems.append('Flow test %s did not pass on the frozen flow and version (%s)' % (test, row['outcome']))
        elif row.get('outcome') != 'Pass':
            problems.append('Flow test %s has no terminal outcome (Pass, Fail, Error, Skip, or unavailable with its reason)' % test)
    if problems:
        return problems
    if unavailable:
        return [] if item['visual_qa'] and not carries else ['Flow test %s is documented unavailable: visual QA, never a pass; record "visual_qa":true%s' % (', '.join(unavailable), carries)]
    if not item['visual_qa'] and flow.get('active_version') != flow['version']:
        return ['Flow active_version %s, read back after activation, must equal version %d' % (flow.get('active_version'), flow['version'])]
    return []


def _agent_findings(folder, item):
    obligations = item.get('obligations')
    if not obligations:
        return ['Agentforce item records no obligations']
    problems = []
    for n, obligation in enumerate(obligations):
        twin = next((o for o in obligations[:n] if json.dumps(o['agent_runtime'], sort_keys=True) == json.dumps(obligation['agent_runtime'], sort_keys=True)), None)
        if twin:
            problems.append('obligations %s and %s have identical acceptance; each action and assertion needs its own inputs' % (twin['id'], obligation['id']))
    if item['disposition'] not in SETTLED_OK:
        return problems
    version = item.get('agent_version')
    if not _text(version):
        return problems + ['Agentforce item records no agent_version from its own publish and activation read-back']
    try:
        evidence = _evidence(folder, item.get('evidence_ref', ''))
        assessor, gate = _assessor(), GATE.read_bytes()
    except (OSError, ValueError, UnicodeError) as error:
        return problems + [str(error)]
    contexts = evidence.get('agent_contexts') if isinstance(evidence, dict) else None
    runtimes = evidence.get('agent_runtime') if isinstance(evidence, dict) else None
    if (not isinstance(contexts, list) or not all(isinstance(c, dict) for c in contexts)
            or not isinstance(runtimes, dict) or not all(isinstance(r, dict) for r in runtimes.values())):
        return problems + ['evidence file needs "agent_contexts" objects and "agent_runtime" objects keyed by obligation ID']
    unavailable = []
    for obligation in obligations:
        found = [c for c in contexts if c.get('item_id') == obligation['id']]
        runtime = runtimes.get(obligation['id'])
        if not found or runtime is None:
            problems.append('obligation %s has no evidence' % obligation['id'])
            continue
        if len(found) > 1:
            problems.append('obligation %s has %d agent_contexts; keep one' % (obligation['id'], len(found)))
            continue
        stale = [v for v in (found[0].get('deployed_version_id'), runtime.get('deployed_version_id')) if v != version]
        if stale:
            problems.append('obligation %s: evidence is for a different deployed version (%s), not agent_version %s'
                            % (obligation['id'], json.dumps(stale[0])[:80], version))
            continue
        try:
            result = assessor.assess(obligation['agent_runtime'], found[0], runtime, gate)
        except (TypeError, ValueError, KeyError, AttributeError, RecursionError) as error:
            result = {'assessment': 'INVALID', 'reason': 'evidence could not be assessed (%s)' % type(error).__name__}
        invocation = runtime.get('invocation') if isinstance(runtime.get('invocation'), dict) else {}
        if result.get('assessment') == 'PASS':
            continue
        if (result.get('assessment'), result.get('reason')) == ('UNAVAILABLE', UNAVAILABLE_INVOCATION) and invocation.get('status') == 'unavailable':
            unavailable.append(obligation['id'])
            continue
        problems.append('obligation %s: %s' % (obligation['id'], result.get('reason', 'not passed')))
    if not problems and unavailable and not (item['visual_qa'] and item['disposition'] == 'applied'):
        carries = '' if item['disposition'] == 'applied' else '; already_satisfied cannot carry visual QA'
        problems.append('obligation %s documents an unavailable runtime: visual QA, never a pass; record "visual_qa":true%s'
                        % (', '.join(unavailable), carries))
    return problems


def evidence_findings(folder, item, orgs=()):
    """X9: Flow and Agentforce items reference their contract's mandatory evidence.

    C5: only items with attempts, or already_satisfied ones (F11), owe it. F12: a documented unavailability is
    visual QA, never a pass.
    """
    kind = family(item['type'])
    if kind not in ('flow', 'agentforce') or (not item['attempts'] and item['disposition'] != 'already_satisfied'):
        return []
    return _flow_findings(folder, item, list(orgs)) if kind == 'flow' else _agent_findings(folder, item)


def unavailable_runtime(folder, item):
    """F12 and F14: does an Agentforce item rest on a documented unavailable runtime (actions unverified in preview)?"""
    if family(item['type']) != 'agentforce' or item['disposition'] not in SETTLED_OK or not item['visual_qa']:
        return False
    try:
        runtimes = _evidence(folder, item.get('evidence_ref', '')).get('agent_runtime')
    except (OSError, ValueError, UnicodeError, AttributeError):
        return False
    return isinstance(runtimes, dict) and any(isinstance(r, dict) and isinstance(r.get('invocation'), dict)
                                              and r['invocation'].get('status') == 'unavailable' for r in runtimes.values())


# ---- Log sections (C6, F14) ----

def _has(section_names, name):
    return any(s == name or s.startswith(name + ' (') or s.startswith(name + ' —') for s in section_names)


def agent_live(item, states):
    """F14 and R2-F6: an attempted agent is live when its last recorded publish settled Active, whatever its
    behavioural verification found."""
    publishes = []
    for attempt in _chronology(item, states):
        jobs = [j for j in states[attempt]['jobs'].values() if j['vocabulary'] == 'agentforce']
        if len(jobs) > 1 and all(j['launched_at'] for j in jobs) and _comparable(*(j['launched_at'] for j in jobs)):
            jobs.sort(key=lambda j: _sort_key(j['launched_at']))  # R3-C1: by recorded launch, line order breaking ties
        publishes += jobs
    return bool(publishes) and publishes[-1]['terminal'] and _word(publishes[-1]['status']).lower() == 'active'


def type_section_findings(record, checkpoints, section_names, folder=None):
    """F14: the change-log template's own conditions decide each section, never the final disposition.
    Sections count at the template's own level, `##` (R2-C4); the caller passes those names."""
    existing = {c['attempt'] for c in checkpoints if c.get('existing')}
    states = _states(record, checkpoints)
    problems = []
    for item in record['items']:
        kind = family(item['type'])
        if not item['attempts']:
            continue
        needed = list(TYPE_SECTIONS.get(kind, ()))
        if kind == 'agentforce':
            if not agent_live(item, states):
                needed.append('Agent Not Live')
            if existing & set(item['attempts']):
                needed.append('Existing Agent Before-State')
            if folder is not None and unavailable_runtime(folder, item):
                needed.append('Actions Unverified in Preview')
        for name in needed:
            if not _has(section_names, name):
                problems.append('%s is an attempted %s item; the log needs its "%s" section' % (item['id'], item['type'], name))
    return problems


def check_findings(record, folder, checkpoints=(), section_names=(), task_visible=''):
    """All W10 rules as (rule, message) pairs. Every task gets the job, order, evidence and section rules;
    complex tasks (F7) also get the beat, story and retry rules."""
    checkpoints = list(checkpoints)
    findings = [('plan', m) for m in write_order_findings(record, checkpoints)]
    findings += [('plan', m) for m in job_findings(record, checkpoints)]
    try:
        order(record)
    except CycleError as error:
        findings.append(('plan', str(error)))
    orgs = bound_orgs(task_visible)
    for item in record['items']:
        findings += [('evidence-ref', item['id'] + ': ' + m) for m in evidence_findings(folder, item, orgs)]
    findings += [('log-type-sections', m) for m in type_section_findings(record, checkpoints, section_names, folder)]
    if record.get('complex') is False and derived_complex(record):
        findings.append(('story', '"complex":false, but this task has three or more items or a gated or Docs-gated type'))
    verdicts = beats(record)
    if verdicts is None:
        return findings
    findings += [('grounding', m) for m in retry_findings(record, checkpoints)]
    if not verdicts:
        return findings + [('story', 'a complex task needs story beats')]
    for beat, (identifier, verdict, reasons) in zip(record['story']['beats'], verdicts):
        if any(c.get('result') == 'dropped' and _active(c) for c in beat['claims']):
            findings.append(('story', '%s drops a required %sclaim' % (identifier, 'proof-moment ' if beat['proof_moment'] else '')))
        recorded = (beat.get('verification') or {}).get('verdict')
        if recorded is None:
            findings.append(('beat', identifier + ' has no recorded verification'))
        elif recorded != verdict:
            findings.append(('beat', '%s records %s but its evidence gives %s (%s)' % (identifier, recorded, verdict, '; '.join(reasons[:3]))))
    return findings
