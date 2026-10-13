#!/usr/bin/env python3
"""Local /scout history: render, resolve owned checkpoints, discover and check."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from urllib.parse import urlsplit

_BUILD_SPEC = importlib.util.spec_from_file_location('scout_build', Path(__file__).with_name('scout_build.py'))
BUILD = importlib.util.module_from_spec(_BUILD_SPEC)
_BUILD_SPEC.loader.exec_module(BUILD)  # W10: complex-plan rules live in scout_build.py

DISPOSITIONS = ('applied', 'already_satisfied', 'failed', 'blocked', 'unverified', 'omitted')
SECTIONS = ('Verified — Applied This Build', 'Verified — Already Satisfied Before This Build',
            'Accounted-for Exceptions', 'Unresolved Work')
LOG_SECTIONS = ('Achieved State', 'What Was Deployed', 'What Was Skipped',
                'Completion Reconciliation', 'Companion Permission Set', 'Issues Encountered',
                'Docs Consulted', 'SE Must Do Next (in order)', 'How to Verify',
                'Open Questions for Next Session')
ARCH_SECTIONS = ('Customer Context & Value Spine', 'Demo Flow / Narrative Arc',
                 'Decision Log', 'Pointers (not duplicated here)')
KNOWN_TYPES = set('customobject customfield recordtype permissionset permissionsetassignment '
                 'customapplication customtab queue businessprocess pathassistant layout flexipage '
                 'data dataseeding record validationrule listview sharingrules sharingrule report '
                 'reportfolder reporttype customreporttype customsetting custommetadata '
                 'custommetadatatype globalvalueset standardvalueset'.split())
TYPE_ALIASES = {'pagelayout': 'layout', 'lightningapp': 'customapplication', 'path': 'pathassistant',
                'records': 'record', 'picklistvalues': 'standardvalueset'}
BUILD.KNOWN_TYPES, BUILD.TYPE_ALIASES = KNOWN_TYPES, TYPE_ALIASES  # W10 F7: complexity is derived from these
CHECKPOINT = re.compile(r'^### (PENDING|' + '|'.join(DISPOSITIONS) +
                        r') — component repair · attempt ([\w.-]+) · (\d{4}-\d\d-\d\d \d\d:\d\d)$')
OUTCOME = re.compile(r'^- \*\*Outcome: (' + '|'.join(DISPOSITIONS) + r')\.\*\* (\S.*)$', re.M)


class BlockError(ValueError):
    pass


def read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        raise OSError('expected a bounded regular file, not a symlink')
    return path.read_bytes().decode('utf-8')


def local(folder, name):
    # Only the workspace root may be an alias, never an org folder or its children.
    folder = folder.absolute()
    if folder.is_symlink() or not name or '..' in Path(name).parts:
        raise OSError('record path must stay inside its regular folder')
    folder = folder.parent.resolve(strict=True) / folder.name
    path = folder / name
    if Path(name).is_absolute():
        root = next((p for p in path.parents if p.resolve() == folder.parent), None)
        if root is None:
            raise OSError('record path escaped its workspace')
        path = folder.parent / path.relative_to(root)
    if not path.is_relative_to(folder):
        raise OSError('record path escaped its folder')
    relative = path.relative_to(folder)
    if any((folder / Path(*relative.parts[:n])).is_symlink() for n in range(len(relative.parts) + 1)):
        raise OSError('symlink path refused')
    return path


def markdown(text):
    """Mask fenced examples, preserving offsets; also return actual scout-items blocks."""
    visible, blocks, body, fence, info = [], [], [], '', ''
    for line in text.splitlines(keepends=True):
        match = re.match(r'^ {0,3}(`{3,}|~{3,})([^\r\n]*)', line)
        if not fence and match:
            fence, info = match[1], match[2].strip()
            body = []
        elif fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                if info == 'scout-items':
                    blocks.append(''.join(body))
                fence = ''
            else:
                body.append(line)
        else:
            visible.append(line)
            continue
        visible.append(''.join('\n' if c == '\n' else ' ' for c in line))
    return ''.join(visible), blocks


def headings(text):
    visible, _ = markdown(text)
    matches = list(re.finditer(r'^(#{1,6}) ([^\r\n]+)\r?$', visible, re.M))
    result = []
    for n, match in enumerate(matches):
        end = next((m.start() for m in matches[n + 1:] if len(m[1]) <= len(match[1])), len(text))
        result.append((match[2], len(match[1]), match.start(), end, visible[match.end():end]))
    return result


def document_header(text):
    visible, _ = markdown(text)
    for title, level, start, _, _ in headings(text):
        if start or level != 1:  # Only the opening document title belongs to the header.
            return visible[:start]
    return visible


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BlockError('duplicate JSON key')
        result[key] = value
    return result


def schema(record):
    def fields(obj, strings=(), lists=(), booleans=()):
        if not isinstance(obj, dict):
            raise BlockError('expected an object')
        for names, kind in ((strings, str), (lists, list), (booleans, bool)):
            for key in names:
                if type(obj.get(key)) is not kind:
                    raise BlockError('missing or invalid ' + key)
    fields(record, ('path', 'change_log'), ('items',))
    if type(record.get('schema')) is not int or record['schema'] != 1:
        raise BlockError('expected schema 1')
    if record['path'] not in ('complete-brief', 'ambiguous', 'open-ended'):
        raise BlockError('invalid route path')
    if not re.fullmatch(r'changes-\d{4}-\d\d-\d\d-\d{4}-[\w.-]+\.md', record['change_log']):
        raise BlockError('invalid change_log filename')
    ids, attempts = set(), set()
    for item in record['items']:
        fields(item, ('id', 'what', 'type', 'beat', 'category', 'criterion', 'proves', 'evidence',
                      'reason', 'seed_asset'), ('depends_on', 'components', 'attempts', 'grounding'), ('visual_qa',))
        if not re.fullmatch(r'I[1-9]\d*', item['id']) or item['id'] in ids:
            raise BlockError('invalid or duplicate item ID')
        ids.add(item['id'])
        if not item['type'].strip() or not item['what'].strip() or not item['criterion'].strip():
            raise BlockError('empty item type, what or criterion')
        if item['category'] not in ('autonomous', 'gated', 'never', 'docs-gated'):
            raise BlockError('invalid category')
        if not isinstance(item.get('readback', ''), str):
            raise BlockError('invalid readback')
        if 'disposition' not in item or (item['disposition'] is not None and not isinstance(item['disposition'], str)):
            raise BlockError('invalid disposition field')
        for key in ('depends_on', 'components', 'attempts'):
            if any(not isinstance(x, str) or not x for x in item[key]) or len(set(item[key])) != len(item[key]):
                raise BlockError('invalid ' + key)
        for attempt in item['attempts']:
            if not re.fullmatch(r'[\w.-]+', attempt) or attempt in attempts:
                raise BlockError('invalid or duplicate attempt ID')
            attempts.add(attempt)
        for entry in item['grounding']:
            fields(entry, ('assumption', 'source', 'ref', 'verdict'))
    history = record.get('history')
    fields(history, ('decisions', 'lessons', 'architecture'), ('proposed_entries',))
    for key, values in (('decisions', ('none', 'proposed', 'confirmed', 'edited', 'skipped')),
                        ('lessons', ('none', 'proposed', 'written', 'skipped')),
                        ('architecture', ('pending', 'created', 'reconciled', 'unchanged'))):
        if history[key] not in values:
            raise BlockError('invalid history ' + key)
    if any(not isinstance(x, str) or not x.strip() for x in history['proposed_entries']):
        raise BlockError('invalid proposed_entries')
    if 'arc_changed' in history and type(history['arc_changed']) is not bool:
        raise BlockError('invalid arc_changed')
    if not isinstance(history.get('reoffers', []), list):
        raise BlockError('invalid reoffers')
    for answer in history.get('reoffers', []):
        fields(answer, ('task', 'answer'))
        if not re.fullmatch(r'task-[\w.-]+\.md', answer['task']) or answer['answer'] not in ('confirmed', 'edited', 'skipped'):
            raise BlockError('invalid reoffer answer')
    story = record.get('story')
    if story is not None:
        fields(story, ('residual', 'audience', 'kp1', 'kp2', 'kp3', 'source'), ('beats',))
        beat_ids = set()
        for beat in story['beats']:
            fields(beat, ('id', 'name', 'persona', 'pain', 'climax'), ('claims',), ('proof_moment',))
            if not re.fullmatch(r'B[1-9]\d*', beat['id']) or beat['id'] in beat_ids:
                raise BlockError('invalid or duplicate beat ID')
            beat_ids.add(beat['id'])
            for claim in beat['claims']:
                fields(claim, ('text', 'item'))
    try:
        BUILD.validate(record)
    except ValueError as error:
        raise BlockError(str(error)) from error
    return record


def task_record(task):
    _, blocks = markdown(read(task))
    if len(blocks) != 1:
        raise BlockError('expected exactly one scout-items block')
    try:
        return schema(json.loads(blocks[0], object_pairs_hook=unique,
                                 parse_constant=lambda _: (_ for _ in ()).throw(BlockError('invalid JSON constant'))))
    except (ValueError, TypeError, RecursionError) as error:
        raise BlockError('invalid scout-items block: ' + str(error)[:160]) from error


def bucket(item):
    disposition = item['disposition']
    if disposition == 'applied':
        return (2, 'AWAITING_QA') if item['visual_qa'] else (0, 'applied')
    return {'already_satisfied': (1, 'already_satisfied'), 'omitted': (2, 'SKIPPED'),
            'failed': (3, 'FAILED'), 'blocked': (3, 'BLOCKED')}.get(disposition, (3, 'INCOMPLETE (unverified)'))


def overall(record):
    buckets = [bucket(i)[0] for i in record['items']]
    base = 'UNRESOLVED' if 3 in buckets else 'FINISHED_WITH_EXCEPTIONS' if 2 in buckets else 'FULLY_VERIFIED'
    return BUILD.overall(record, base)


def grounding_line(record):
    counts = {s: 0 for s in ('docs', 'skill', 'org', 'ungrounded')}
    for item in record['items']:
        for source in set(e['source'] for e in item['grounding']):
            if source in counts:
                counts[source] += 1
    return 'Grounding: %d items; %s' % (len(record['items']), '; '.join('%s %d' % pair for pair in counts.items()))


def render(record):
    rows = lambda items: ['- %s — %s — %s' % (i['id'], bucket(i)[1],
                            ' '.join((i['evidence'] + ' ' + i['reason']).split())) for i in items] or ['None.']
    output = [grounding_line(record), '', '## What Was Skipped',
              *rows(i for i in record['items'] if i['disposition'] == 'omitted'),
              '', '## Completion Reconciliation', 'Overall: ' + overall(record)]
    if BUILD.beats_line(record):
        output.append(BUILD.beats_line(record))
    for n, section in enumerate(SECTIONS):
        output += ['', '### ' + section, *rows(i for i in record['items'] if bucket(i)[0] == n)]
    return '\n'.join(output) + '\n'


def header_matches(text, task):
    visible, _ = markdown(text)
    header = visible.split('\n## ', 1)[0]
    refs = re.findall(r'^Task record: (.+)\r?$', header, re.M)
    return len(refs) == 1 and refs[0].strip().strip('`') in (task.name, str(task))


def own_body(body):
    """The owning section ends before the first nested heading; fences stay masked."""
    return re.split(r'^#{1,6} ', markdown(body)[0], maxsplit=1, flags=re.M)[0]


def outcome_values(body):
    # A value cannot cross a blank line or consume an unindented paragraph.
    marker = re.compile(r'(?i)^[ \t]*(?:[-*][ \t]+)?(?:\*\*)?(?:final[ \t]+)?outcome'
                        r'(?:[ \t]*\([^\r\n)]*\)|[ \t]*/[ \t]*read-back)?(?:\*\*)?[ \t]*:'
                        r'[ \t]*(?:\*\*)?[ \t]*([^\r\n]*)$')
    lines, values = markdown(body)[0].splitlines(), []
    for n, line in enumerate(lines):
        match = marker.fullmatch(line)
        if match:
            value = [match[1]]
            for continuation in lines[n + 1:]:
                if not continuation.strip() or not continuation.startswith((' ', '\t')):
                    break
                value.append(continuation)
            values.append('\n'.join(value))
    return values


def disposition_word(value):
    value = re.sub(r'[*`]', '', value).strip()
    value = re.sub(r'^-[ \t]+', '', value)
    value = re.sub(r'^(?:\([\w]+\)|I\d+:)[ \t]*', '', value)
    match = re.match(r'([\w]+)\b', value.strip(' \t_'))
    return match[1].lower() if match else ''


def own_outcome(body):
    body = own_body(body)
    outcomes = OUTCOME.findall(body.replace('\r\n', '\n'))
    markers = re.findall(r'^- \*\*Outcome:', body, re.M)
    if len(outcomes) != 1 or len(markers) != 1:
        return None
    outcome = outcomes[0][0]
    # Stale pending fields are normal; another final/non-final assertion is not.
    return outcome if all(disposition_word(v) in ('pending', outcome) for v in outcome_values(body)) else None


def status_fields(body, nested=False):
    # Preserve token offsets for resolve; markup cannot hide a pending field value.
    return re.finditer(r'(?im)^[ \t]*(?:-[ \t]+)?[*_`]*'
                       r'(outcome(?:[ \t]*/[ \t]*read-back)?|classification(?:[ \t]*/[ \t]*source)?|'
                       r'preedit_snapshot(?:\.status)?|rollback(?:_receipt)?|verification|cleanup|artifact(?:s)?|'
                       r'(?:first )?pre-edit artifact / source(?: / members)?|'
                       r'original flow activation \(flow only\)|preservation|exact bundle members)'
                       r'[*_`]*[ \t]*:[ \t*_`]*(pending)(?=$|[^\w]|_)', markdown(body)[0] if nested else own_body(body))


def existing_classification(text):
    # Template values can classify several named components before their evidence.
    for line in markdown(text)[0].splitlines():
        plain = re.sub(r'[*`]', '', line)
        field = re.match(r'(?i)^[ \t]*(?:- )?classification(?: / source)?[ \t]*:(.*)', plain)
        if field and re.search(r'(?i)(?:^|[:;])[ \t_]*existing(?=$|[^\w]|_)', field[1]):
            return True
    return False


def docs_url(reference):
    try:
        url = urlsplit(reference)
        return url.scheme in ('https', 'http') and bool(url.hostname) and not url.username and not re.search(r'\s', reference)
    except ValueError:
        return False


def resolve(task, record):
    log = local(task.parent, record['change_log'])
    original = read(log)
    if not header_matches(original, task) or log.stat().st_nlink != 1:
        raise OSError('resolve refused: log header does not name this task or file is shared')
    owners = {a: i for i in record['items'] for a in i['attempts']}
    sections = headings(original)
    matches = [(s, CHECKPOINT.fullmatch(original[s[2]:].splitlines()[0])) for s in sections]
    changes, updated = [], original
    for section, match in reversed(matches):
        if not match or match[2] not in owners or owners[match[2]]['disposition'] not in DISPOSITIONS:
            continue
        if sum(bool(m and m[2] == match[2]) for _, m in matches) != 1:
            continue
        outcome = own_outcome(section[4])
        if outcome is None:
            continue
        start, end = section[2:4]
        block = original[start:end]
        replacement = block
        prefix = len(block.splitlines(keepends=True)[0])
        for field in reversed(list(status_fields(block[prefix:]))):
            if field[1].lower().startswith('outcome'):
                replacement = replacement[:prefix + field.start(2)] + outcome + replacement[prefix + field.end(2):]
        replacement = re.sub(r'^### [^\r\n]+', '### %s — component repair · attempt %s · %s' %
                             (outcome, match[2], match[3]), replacement, count=1)
        if replacement != block:
            updated = updated[:start] + replacement + updated[end:]
            changes.append(match[2])
    if updated != original:
        mode = stat.S_IMODE(log.stat().st_mode)
        with tempfile.NamedTemporaryFile(dir=log.parent, delete=False) as temporary:
            temp = Path(temporary.name)
            try:
                temporary.write(updated.encode('utf-8'))
                temporary.flush()
                os.fsync(temporary.fileno())
                os.chmod(temp, mode)
                if read(log) != original:
                    raise OSError('log changed during resolve')
                os.replace(temp, log)
            finally:
                temp.unlink(missing_ok=True)
    print(json.dumps({'changed': list(reversed(changes)), 'log': str(log)}))


def check(task, record):
    findings, warnings = [], []
    def issue(rule, message, path=task, line=1, warning=False):
        (warnings if warning else findings).append(f'{path}:{line}: {rule}: ' + ('warning: ' if warning else '') + message)
    items = {i['id']: i for i in record['items']}
    story = record.get('story')
    proof_items = set()
    if record['path'] == 'open-ended' and (not story or not story['beats'] or
            story['source'] not in ('se-stated', 'se-confirmed') or not any(b['proof_moment'] for b in story['beats'])):
        issue('story', 'open-ended work requires beats and a sourced proof moment')
    if story:
        if story['source'] not in ('se-stated', 'se-confirmed'):
            issue('story', 'story source must be se-stated or se-confirmed')
        for beat in story['beats']:
            if any(not beat[k].strip() for k in ('name', 'persona', 'pain', 'climax')):
                issue('story', 'beat needs name, persona, pain and climax')
            if beat['proof_moment'] and not beat['claims']:
                issue('story', 'proof moment needs a claim with readback')
            for claim in beat['claims']:
                item = items.get(claim['item'])
                if not claim['text'].strip() or not item or not item.get('readback', '').strip():
                    issue('story', 'every claim needs an existing item with readback')
                if beat['proof_moment']:
                    proof_items.add(claim['item'])
    for item in items.values():
        identifier, disposition = item['id'], item['disposition']
        if disposition not in DISPOSITIONS:
            issue('disposition', identifier + ' needs one of the six dispositions')
        if disposition in ('applied', 'already_satisfied') and not item['evidence'].strip():
            issue('disposition', identifier + ' verified disposition needs evidence')
        if disposition == 'omitted' and not item['reason'].strip():
            issue('disposition', identifier + ' omitted without reason/decision source')
        if disposition == 'failed' and not all(
                (m := re.search(label + r':[ \t]*(.*?)(?=;|\n|(?:State left|rollback):|$)', item['reason'], re.I))
                and m[1].strip().strip('*_`').strip() for label in ('State left', 'rollback')):
            issue('disposition', identifier + ' failed: reason needs State left: ...; rollback: ...')
        if item['visual_qa'] and disposition != 'applied':
            issue('disposition', identifier + ' visual_qa only applies to applied')
        if record['path'] == 'open-ended':
            if not story or item['beat'] not in {b['id'] for b in story['beats']}:
                issue('story', identifier + ' needs an existing beat')
            if not item['proves'].strip() or item['proves'].strip() == '-':
                issue('story', identifier + ' needs proves or an explicit kept exception')
        for dependency in item['depends_on']:
            if dependency not in items:
                issue('dependency', identifier + ' has unknown dependency ' + dependency)
            elif disposition in ('applied', 'already_satisfied') and items[dependency]['disposition'] in ('failed', 'blocked', 'unverified', 'omitted', None):
                issue('dependency', identifier + ' depends on unresolved ' + dependency)
        grounded, docs, unavailable = item['grounding'], False, False
        for entry in grounded:
            source, reference, verdict = entry['source'], entry['ref'], entry['verdict']
            if not entry['assumption'].strip() or source not in ('docs', 'skill', 'org', 'ungrounded', 'lesson'):  # W10 F5: a retry may cite a lesson
                issue('grounding', identifier + ' invalid source or empty assumption')
            if source == 'docs':
                valid = docs_url(reference) and bool(verdict.strip())
                docs |= valid
                if not valid:
                    issue('grounding', identifier + ' docs needs URL and verdict')
            elif source == 'ungrounded':
                if reference or not verdict.strip():
                    issue('grounding', identifier + ' ungrounded needs empty ref and a reason')
                elif verdict.lower().startswith('docs unavailable'):
                    unavailable = True
                    issue('grounding', identifier + ': ' + verdict, warning=True)
            elif not reference.strip():
                issue('grounding', identifier + ' source needs a reference')
        kind = re.sub(r'[^a-z]', '', item['type'].lower())
        requires_docs = (item['category'] in ('gated', 'docs-gated') or identifier in proof_items or
                         TYPE_ALIASES.get(kind, kind) not in KNOWN_TYPES)
        if not grounded or (requires_docs and not (docs or unavailable)):
            issue('grounding', identifier + ' missing required grounding/Docs')
        if disposition == 'omitted' and re.search(r'ui[ -]only', item['reason'], re.I) and not docs:
            issue('grounding', identifier + ' UI-only omission needs a Docs citation')
        if item['seed_asset'] and not local(task.parent, item['seed_asset']).is_file():
            issue('seed-asset', identifier + ' seed asset missing')
    visited, active = set(), set()
    def visit(identifier):
        if identifier in active:
            issue('dependency', 'dependency cycle at ' + identifier)
        elif identifier not in visited:
            active.add(identifier)
            for dependency in items[identifier]['depends_on']:
                if dependency in items:
                    visit(dependency)
            active.remove(identifier)
            visited.add(identifier)
    for identifier in items:
        visit(identifier)
    if record['history']['decisions'] == 'proposed' and not record['history']['proposed_entries']:
        issue('history', 'proposed decisions need saved proposed_entries')
    log = local(task.parent, record['change_log'])
    if not log.exists():
        issue('log-header', 'named log missing', log)
    else:
        text = read(log)
        visible, _ = markdown(text)
        sections = headings(text)
        header = visible.split('\n## ', 1)[0]
        if (not re.match(r'^# Change Log — .+ — \d{4}-\d\d-\d\d \d{4}\r?$', header, re.M) or
                not header_matches(text, task) or not re.search(r'^Org: \S.+$', header, re.M) or
                not re.search(r'^Audit used: (?:scoped \(task record\)|`?audit-[^\r\n]+\.md`?)\r?$', header, re.M) or
                re.search(r'^Spec(?: SHA-256)?:', header, re.M) or grounding_line(record) not in header.splitlines()):
            issue('log-header', 'missing/mismatched template header, task pointer or Grounding line', log)
        required = [(2, name) for name in LOG_SECTIONS] + [(3, name) for name in SECTIONS]
        if any(i['seed_asset'] for i in items.values()):
            required.append((2, 'Script Deliverables'))
        if any(i['attempts'] for i in items.values()):
            required.append((2, 'Checkpoints'))
        if existing_classification(visible):
            required.append((2, 'Existing Component Before-State and Direct Repairs'))
        for level, name in required:
            found = [s for s in sections if s[1] == level and (re.sub(r' \([^()]*\)$', '', s[0]) == re.sub(r' \([^()]*\)$', '', name) or s[0].startswith(name + ' —'))]
            if len(found) != 1:
                issue('log-section', 'expected one ' + name, log)
        reconciliation = [s for s in sections if s[0] == 'Completion Reconciliation' and s[1] == 2]
        if reconciliation and any(i not in items for i in re.findall(r'^- (I\d+)\b', reconciliation[0][4], re.M)):
            issue('reconciliation', 'unknown item in reconciliation', log)
        skipped = [s for s in sections if s[0] == 'What Was Skipped' and s[1] == 2]
        if skipped and sorted(re.findall(r'^- (I\d+)\b', skipped[0][4], re.M)) != sorted(i['id'] for i in items.values() if i['disposition'] == 'omitted'):
            issue('reconciliation', 'What Was Skipped must contain exactly the omitted items', log)
        for item in items.values():
            occurrences = [s[0] for s in sections if s[1] == 3 and s[0] in SECTIONS and
                           reconciliation and reconciliation[0][2] < s[2] < reconciliation[0][3]
                           for _ in re.finditer(r'^- ' + item['id'] + r'\b', s[4], re.M)]
            if occurrences != [SECTIONS[bucket(item)[0]]]:
                issue('reconciliation', item['id'] + ' must appear exactly once in its mapped subsection', log)
        if not reconciliation or re.findall(r'^Overall: (\S+)\r?$', reconciliation[0][4], re.M) != [overall(record)]:
            issue('overall', 'expected ' + overall(record), log)
        checkpoint_sections = [s for s in sections if s[0] == 'Checkpoints' and s[1] == 2]
        recorded = {a for i in items.values() for a in i['attempts']}
        for section in sections:
            if checkpoint_sections and checkpoint_sections[0][2] < section[2] < checkpoint_sections[0][3]:
                match = CHECKPOINT.fullmatch(text[section[2]:].splitlines()[0])
                if checkpoint_heading(section[0]) and (not match or match[2] not in recorded):
                    issue('checkpoint', 'unrecorded checkpoint: ' + section[0], log)
        for item in items.values():
            attempted = item['disposition'] in ('applied', 'failed', 'unverified')
            if ((attempted and not item['attempts']) or
                    (item['disposition'] in ('blocked', 'omitted') and item['attempts'])):
                issue('checkpoint', item['id'] + ' attempt count disagrees with disposition', log)
            for attempt in item['attempts']:
                candidates = [s for s in sections if (m := CHECKPOINT.fullmatch(text[s[2]:].splitlines()[0])) and m[2] == attempt]
                valid = len(candidates) == 1
                if valid:
                    section = candidates[0]
                    match = CHECKPOINT.fullmatch(text[section[2]:].splitlines()[0])
                    outcome = own_outcome(section[4])
                    if ((attempted and attempt == item['attempts'][-1]) or item['disposition'] == 'already_satisfied') and outcome != item['disposition']:
                        issue('checkpoint', item['id'] + ' attempt outcome disagrees with disposition', log)
                    valid = (bool(checkpoint_sections) and checkpoint_sections[0][2] < section[2] < checkpoint_sections[0][3]
                             and checkpoint_sections[0][3] == len(text))
                    if item['disposition'] in DISPOSITIONS:
                        valid &= outcome is not None and match[1] == outcome and not any(status_fields(section[4], nested=True))
                    else:
                        valid &= match[1] == 'PENDING'
                if not valid:
                    issue('checkpoint', attempt + ' missing, duplicate, misplaced or unsettled outcome/fields', log)
    if record['history']['architecture'] in ('created', 'reconciled'):
        arch = local(task.parent, 'demo-architecture.md')
        if not arch.exists():
            issue('arch', 'architecture missing', arch)
        else:
            text = read(arch)
            visible, _ = markdown(text)
            visible = visible.replace('\r\n', '\n')
            header = visible.split('\n## ', 1)[0]
            if (not re.search(r'^# Demo Architecture — \S.+$', header, re.M) or
                    not re.search(r'^Last reconciled: \d{4}-\d\d-\d\d \d{4} by /scout$', header, re.M) or
                    not re.search(r'^Target Org: \S.+$', header, re.M) or
                    not re.search(r'^Reconciled through: `?' + re.escape(record['change_log']) + r'`?$', header, re.M)):
                issue('arch', 'missing template title/headers or current log stamp', arch)
            created = record['history']['architecture'] == 'created'
            map_text = text.replace('\r\n', '\n')
            map_sections = headings(map_text)
            lines = map_text.splitlines()
            owned = set(range(len(header.splitlines()))) if created else {
                n for n, line in enumerate(header.splitlines())
                if re.match(r'^(?:# Demo Architecture|Last reconciled:|Target Org:|Reconciled through:)', line)}
            stamp = re.compile(r'(?<![\w.-])' + re.escape(Path(record['change_log']).stem) + r'(?:\.md)?(?![\w.-])')
            decision_lines = set()
            for section in map_sections:
                if section[1] != 2 or section[0] not in ARCH_SECTIONS:
                    continue
                if section[0] == 'Decision Log':
                    decision_lines.update(range(map_text[:section[2]].count('\n') + 1, len(map_text[:section[3]].splitlines())))
                # Creation owns all nested text. Reconciliation preserves old SE sections.
                end = section[3] if created else next((s[2] for s in map_sections if section[2] < s[2] < section[3]), section[3])
                begin_line, end_line = map_text[:section[2]].count('\n'), len(map_text[:end].splitlines())
                owned.update(n for n in range(begin_line, end_line) if created or not lines[n].lstrip().startswith('>'))
                if section[0] == 'Demo Flow / Narrative Arc' and (created or record['history'].get('arc_changed')):
                    if any(len(line) > 320 for line in section[4].splitlines()
                           if created or not line.lstrip().startswith('>')):
                        issue('arch', 'arc beats must be <=320 characters', arch)
            # Current-task references are owned wherever they occur, including nested/SE sections.
            for n, line in enumerate(lines):
                current = bool(stamp.search(line)) and not (n < len(header.splitlines()) and line.startswith('Reconciled through:'))
                if current:
                    owned.add(n)
                    if len(line) > 320:
                        issue('arch', 'current-task lines must be <=320 characters', arch)
                if created and n in decision_lines and not line.startswith('#') and len(line) > 320:
                    issue('arch', 'new decision lines must be <=320 characters', arch)
                if n in decision_lines and (current or (created and line.startswith('- '))):
                    following = lines[n + 1:n + 2]
                    continuation = following and following[0].strip() and not re.match(r'^(?:- |#)', following[0])
                    if len(line) > 320 or continuation or not re.match(r'^- \*\*\[\d{4}-\d\d-\d\d\]\*\* — ', line):
                        issue('arch', 'current decision must be a dated line <=320 characters', arch)
            template = map_text if created else '\n'.join(lines[n] for n in sorted(owned))
            over = lambda value: len(value.splitlines()) > 350 or len(value.split()) > 3750
            if over(text):
                issue('arch', 'map exceeds 350 lines / 3750 words' + (' only due to SE sections' if not over(template) else ''),
                      arch, warning=not over(template))
    checkpoints, names = log_checkpoints(log) if log.exists() else ([], [])
    for rule, message in BUILD.check_findings(record, task.parent, checkpoints, names, markdown(read(task))[0]):
        issue(rule, message)
    print('\n'.join(findings + warnings) or f'{task}:1: check: pass')
    return 3 if findings else 0


def log_checkpoints(log):
    """W10 hook: the log's headings and owned checkpoints for scout_build.py, raw (fences included) and parsed."""
    text, checkpoints, names = read(log), [], []
    for title, _, start, end, body in headings(text):
        names.append(title)
        match = CHECKPOINT.fullmatch(text[start:].splitlines()[0])
        if match:
            checkpoints.append(dict(attempt=match[2], stamp=match[3], position=start, raw=text[start:end], visible=body,
                                    outcome=own_outcome(body), existing=existing_classification(body)))
    return checkpoints, names


def checkpoint_heading(title):
    return bool(re.match(r'(?i)^(?:PENDING[ \t]+[-—–][ \t]+\S|CHECKPOINT:[ \t]*PENDING\b)', title) or
                re.match(r'^(?:' + '|'.join(DISPOSITIONS) + r') — component repair · attempt ', title))


def pending(directory, org, username):
    incomplete = False
    for folder in sorted(directory.iterdir()):
        if folder.is_symlink():
            print(json.dumps({'state': 'incomplete', 'path': str(folder), 'reason': 'symlink folder refused'}))
            incomplete = True
            continue
        if not folder.is_dir():
            continue
        texts, unreadable = [], []
        try:
            paths = sorted(p for p in folder.iterdir() if re.fullmatch(r'(?:changes|task)-.*\.md', p.name))
        except OSError:
            print(json.dumps({'state': 'incomplete', 'path': str(folder), 'reason': 'cannot list history folder'}))
            incomplete = True
            continue
        for path in paths:
            try:
                texts.append((path, read(path)))
            except (OSError, UnicodeError):
                unreadable.append(path)
        identity = r'(?<![A-Za-z0-9])' + re.escape(org[:15]) + r'(?:[A-Za-z0-9]{3})?(?![A-Za-z0-9])'
        matched = any(re.search(identity, t) or (username and re.search(r'(?<![\w@.\-])' + re.escape(username) + r'(?![\w@.\-])', t)) for _, t in texts)
        identified = any(re.search(r'\b00D[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\b', t) or
                         re.search(r'(?im)^(?:Org|Target Org):[^\r\n]*[\w.+-]+@[\w.-]+', t) for _, t in texts)
        if unreadable and not matched and not identified:
            print(json.dumps({'state': 'incomplete', 'path': str(folder), 'reason': 'unreadable history; folder relevance unknown'}))
            incomplete = True
            continue
        for path in unreadable:
            print(json.dumps({'file': str(path), 'state': 'unclear' if matched else 'skipped', 'reason': 'unreadable history'}),
                  file=sys.stdout if matched else sys.stderr)
        if not matched:
            continue
        records = []
        for path, text in texts:
            for title, _, start, _, body in headings(text):
                if not checkpoint_heading(title):
                    continue
                state = checkpoint_state(text[start:].splitlines()[0], title, body)
                print(json.dumps({'file': str(path), 'line': text[:start].count('\n') + 1, 'state': state, 'heading': title}))
            if path.name.startswith('task-'):
                try:
                    records.append((path, task_record(path)))
                except BlockError:
                    if 'scout-items' in text or re.search(r'decisions["\s:]*proposed', text):
                        print(json.dumps({'file': str(path), 'state': 'unclear', 'reason': 'unparseable task record'}))
        answered = {a['task'] for _, r in records for a in r['history'].get('reoffers', [])}
        for path, record in records:
            if record['history']['decisions'] == 'proposed' and path.name not in answered:
                print(json.dumps({'file': str(path), 'folder': str(folder), 'state': 'proposed', 'proposed_entries': record['history']['proposed_entries']}))

    return 3 if incomplete else 0


def checkpoint_state(heading, title, body):
    """Discovery rules (current-task check/resolve deliberately remain stricter).

    Exact /scout outcome headings resolve. Exact PENDING needs its own canonical
    final line. Legacy component repair uses the last unfenced marker through
    the next same/higher heading: no marker is unresolved; a final value resolves;
    anything else is unclear. Unknown kinds are always unclear. Values stay on
    their own line plus immediate indented continuations, never across a blank.
    A value starts with one of five legacy final words, or is empty with at least
    one final continuation and no non-final disposition. Evidence-only lines are
    ignored. Labelled receipts/evidence/companion/artifact/source/query lines are
    evidence; other unknown labelled values are unclear, never inferred final.
    """
    own = CHECKPOINT.fullmatch(heading)
    if own:
        return 'resolved' if own[1] != 'PENDING' or own_outcome(body) else 'unresolved'
    if not re.match(r'(?i)^(?:PENDING[ \t]+[-—–][ \t]+|CHECKPOINT:[ \t]*PENDING[ \t]+[-—–][ \t]+)component repair\b', title):
        return 'unclear'
    values = outcome_values(body)
    return 'unresolved' if not values else 'resolved' if legacy_final(values[-1]) else 'unclear'


def legacy_final(marker):
    # Five legacy final words; omitted is a /scout-only final disposition.
    final = ('applied', 'already_satisfied', 'failed', 'blocked', 'unverified')
    lines = marker.splitlines()
    first = disposition_word(lines[0]) if lines else ''
    if first:
        return first in final
    dispositions = []
    for line in lines[1:]:
        word = disposition_word(line)
        labelled = re.match(r'^[ \t]*(?:-[ \t]+)?(?:\([\w]+\)|I\d+:)', re.sub(r'[*`]', '', line))
        # Labelled receipts are evidence; any other unknown labelled value is conservative.
        if labelled and word in ('receipt', 'evidence', 'companion', 'artifact', 'source', 'query'):
            continue
        if labelled or word in (*DISPOSITIONS, 'pending', 'partial', 'partially', 'not_applied', 'not', 'incomplete', 'unknown'):
            dispositions.append(word)
    return bool(dispositions) and all(w in final for w in dispositions)


def reconcile_plan(folder):
    if not folder.is_dir():
        raise OSError('expected a folder')
    arch = local(folder, 'demo-architecture.md')
    text = read(arch) if arch.exists() else ''
    header = document_header(text)
    stamp = re.search(r'^Reconciled through:[ \t]*`?changes-(\d{4}-\d\d-\d\d-\d{4})-', header, re.M)
    prior = stamp[1] if stamp else ''
    files = sorted((p for p in folder.glob('changes-*.md')
                    if (m := re.fullmatch(r'changes-(\d{4}-\d\d-\d\d-\d{4})-[\w.-]+\.md', p.name)) and m[1] > prior), reverse=True)
    for n, path in enumerate(files):
        print(json.dumps({'file': str(path), 'read': 'full' if n < 5 else 'last-section'}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('render', 'resolve', 'check', 'plan'):
        commands.add_parser(name).add_argument('--task', required=True, type=Path)
    sub = commands.add_parser('pending')
    sub.add_argument('--orgs-dir', required=True, type=Path)
    sub.add_argument('--org-id', required=True)
    sub.add_argument('--username')
    commands.add_parser('reconcile-plan').add_argument('--folder', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == 'pending' and not re.fullmatch(r'00D[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?', args.org_id):
        parser.error('expected a 15- or 18-character org ID')
    try:
        if args.command == 'pending':
            return pending(args.orgs_dir.resolve(strict=True), args.org_id, args.username)
        elif args.command == 'reconcile-plan':
            reconcile_plan(args.folder.resolve(strict=True))
        else:
            task = local(args.task.absolute().parent, args.task.name)
            record = task_record(task)
            if args.command == 'render':
                print(render(record), end='')
            elif args.command == 'plan':
                log = local(task.parent, record['change_log'])
                try:
                    print(json.dumps(BUILD.plan(record, log_checkpoints(log)[0] if log.exists() else [])))
                except BUILD.CycleError as error:
                    print(f'{task}:1: plan: {error}')
                    return 3
            elif args.command == 'resolve':
                resolve(task, record)
            else:
                return check(task, record)
    except BlockError as error:
        print(f'{getattr(args, "task", "history")}:1: block: {error}')
        return 3
    except (OSError, UnicodeError, ValueError, RuntimeError) as error:
        print(f'{getattr(args, "task", "history")}:1: read: could not safely read/update history ({type(error).__name__})')
        return 4
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
