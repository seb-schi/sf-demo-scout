#!/usr/bin/env python3
"""Local /scout history: render, resolve owned checkpoints, discover and check."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from urllib.parse import urlsplit

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
    path = folder / name
    if not name or Path(name).is_absolute() or '..' in Path(name).parts:
        raise OSError('record path must stay inside its folder')
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise OSError('symlink path refused')
    if not path.resolve().is_relative_to(folder.resolve()):
        raise OSError('record path escaped its folder')
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
    return 'UNRESOLVED' if 3 in buckets else 'FINISHED_WITH_EXCEPTIONS' if 2 in buckets else 'FULLY_VERIFIED'


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
    for n, section in enumerate(SECTIONS):
        output += ['', '### ' + section, *rows(i for i in record['items'] if bucket(i)[0] == n)]
    return '\n'.join(output) + '\n'


def header_matches(text, task):
    visible, _ = markdown(text)
    header = visible.split('\n## ', 1)[0]
    refs = re.findall(r'^Task record: (.+)\r?$', header, re.M)
    return len(refs) == 1 and refs[0].strip().strip('`') in (task.name, str(task))


def own_outcome(body):
    outcomes = OUTCOME.findall(body)
    return outcomes[0][0] if len(outcomes) == 1 else None


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
        replacement = re.sub(r'^### [^\n]+', '### %s — component repair · attempt %s · %s' %
                             (outcome, match[2], match[3]), block, count=1)
        replacement = re.sub(r'(?im)(\boutcome\s*:\s*)pending\b', lambda m: m[1] + outcome, replacement)
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
        if disposition == 'omitted' and not item['reason'].strip():
            issue('disposition', identifier + ' omitted without reason/decision source')
        if disposition == 'failed' and not (re.search(r'State left:\s*\S', item['reason'], re.I) and
                                            re.search(r'rollback:\s*\S', item['reason'], re.I)):
            issue('disposition', identifier + ' failed: reason needs State left: ...; rollback: ...')
        if item['visual_qa'] and disposition != 'applied':
            issue('disposition', identifier + ' visual_qa only applies to applied')
        if record['path'] == 'open-ended' and not item['proves'].strip():
            issue('story', identifier + ' needs proves')
        for dependency in item['depends_on']:
            if dependency not in items:
                issue('dependency', identifier + ' has unknown dependency ' + dependency)
            elif disposition in ('applied', 'already_satisfied') and items[dependency]['disposition'] in ('failed', 'blocked', 'unverified', None):
                issue('dependency', identifier + ' depends on unresolved ' + dependency)
        grounded, docs, unavailable = item['grounding'], False, False
        for entry in grounded:
            source, reference, verdict = entry['source'], entry['ref'], entry['verdict']
            if not entry['assumption'].strip() or source not in ('docs', 'skill', 'org', 'ungrounded'):
                issue('grounding', identifier + ' invalid source or empty assumption')
            if source == 'docs':
                valid = docs_url(reference) and bool(verdict.strip())
                docs |= valid
                if not valid:
                    issue('grounding', identifier + ' docs needs URL and verdict')
            elif source == 'ungrounded':
                if reference or not verdict.strip():
                    issue('grounding', identifier + ' ungrounded needs empty ref and a reason')
                elif verdict.startswith('Docs unavailable'):
                    unavailable = True
                    issue('grounding', identifier + ': ' + verdict, warning=True)
            elif not reference.strip():
                issue('grounding', identifier + ' source needs a reference')
        requires_docs = (item['category'] in ('gated', 'docs-gated') or identifier in proof_items or
                         re.sub(r'[^a-z]', '', item['type'].lower()) not in KNOWN_TYPES)
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
                not re.search(r'^Audit used: \S.+$', header, re.M) or grounding_line(record) not in header.splitlines()):
            issue('log-header', 'missing/mismatched template header, task pointer or Grounding line', log)
        required = [(2, name) for name in LOG_SECTIONS] + [(3, name) for name in SECTIONS]
        if any(i['seed_asset'] for i in items.values()):
            required.append((2, 'Script Deliverables'))
        if any(i['attempts'] for i in items.values()):
            required.append((2, 'Checkpoints'))
        if re.search(r'Classification[^\n]*:\*\*[^\n]*\bexisting\b', visible, re.I):
            required.append((2, 'Existing Component Before-State and Direct Repairs'))
        for level, name in required:
            found = [s for s in sections if s[1] == level and (s[0] == name or s[0].startswith(name + ' —'))]
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
        for item in items.values():
            for attempt in item['attempts']:
                candidates = [s for s in sections if (m := CHECKPOINT.fullmatch(text[s[2]:].splitlines()[0])) and m[2] == attempt]
                valid = len(candidates) == 1
                if valid:
                    section = candidates[0]
                    match = CHECKPOINT.fullmatch(text[section[2]:].splitlines()[0])
                    outcome = own_outcome(section[4])
                    valid = (bool(checkpoint_sections) and checkpoint_sections[0][2] < section[2] < checkpoint_sections[0][3]
                             and checkpoint_sections[0][3] == len(text))
                    if item['disposition'] in DISPOSITIONS:
                        valid &= outcome is not None and match[1] == outcome and not re.search(r'(?im)^\s*-?\s*[^\n:]+:\s*[^\n]*\bpending\b', section[4])
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
            header = visible.split('\n## ', 1)[0]
            if (not re.search(r'^# Demo Architecture — \S.+$', header, re.M) or
                    not re.search(r'^Last reconciled: \d{4}-\d\d-\d\d \d{4} by /scout$', header, re.M) or
                    not re.search(r'^Target Org: \S.+$', header, re.M) or
                    not re.search(r'^Reconciled through: `?' + re.escape(record['change_log']) + r'`?$', header, re.M)):
                issue('arch', 'missing template title/headers or current log stamp', arch)
            for n, line in enumerate(visible.splitlines(), 1):
                if record['change_log'] in line and not line.startswith('Reconciled through:'):
                    following = visible.splitlines()[n:n + 1]
                    continuation = following and following[0].strip() and not re.match(r'^(?:- |#)', following[0])
                    if len(line) > 320 or continuation or not re.match(r'^- \*\*\[\d{4}-\d\d-\d\d\]\*\* — ', line):
                        issue('arch', 'current decision must be a dated line <=320 characters', arch, n)
            for section in headings(text):
                if section[0] == 'Demo Flow / Narrative Arc' and any(len(line) > 320 for line in section[4].splitlines()):
                    issue('arch', 'arc beats must be <=320 characters', arch)
            template = text
            for section in reversed(headings(text)):
                if section[1] == 2 and section[0] not in ARCH_SECTIONS:
                    template = template[:section[2]] + template[section[3]:]
            over = lambda value: len(value.splitlines()) > 350 or len(value.split()) > 3750
            if over(text):
                issue('arch', 'map exceeds 350 lines / 3750 words' + (' only due to SE sections' if not over(template) else ''),
                      arch, warning=not over(template))
    print('\n'.join(findings + warnings) or f'{task}:1: check: pass')
    return 3 if findings else 0


def pending(directory, org, username):
    for folder in sorted(p for p in directory.iterdir() if p.is_dir() and not p.is_symlink()):
        files = sorted(set(folder.glob('changes-*.md')) | set(folder.glob('task-*.md')))
        texts = [(p, read(p)) for p in files]
        identity = r'(?<![A-Za-z0-9])' + re.escape(org[:15]) + r'(?:[A-Za-z0-9]{3})?(?![A-Za-z0-9])'
        if not any(re.search(identity, t) or (username and re.search(r'(?<![\w@.\-])' + re.escape(username) + r'(?![\w@.\-])', t)) for _, t in texts):
            continue
        for path, text in texts:
            for title, _, start, _, body in headings(text):
                if not re.search(r'\bPENDING\b', title, re.I) and not CHECKPOINT.fullmatch(text[start:].splitlines()[0]):
                    continue
                state = 'unclear'
                if CHECKPOINT.fullmatch(text[start:].splitlines()[0]) and not title.startswith('PENDING'):
                    state = 'resolved'
                elif re.search(r'pending', title, re.I) and re.search(r'component repair', title, re.I):
                    markers = re.findall(r'(?im)^.*?\b(?:final\s+)?outcome\b[^:\n]*:\s*([^\n]*(?:\n[ \t]+[^\n]+)*)', body)
                    if not markers:
                        state = 'unresolved'
                    elif all(legacy_final(m) for m in markers):
                        state = 'resolved'
                print(json.dumps({'file': str(path), 'line': text[:start].count('\n') + 1, 'state': state, 'heading': title}))
            if path.name.startswith('task-'):
                try:
                    record = task_record(path)
                except BlockError:
                    continue  # Historical free-form tasks are leads, not lint targets.
                if record['history']['decisions'] == 'proposed':
                    print(json.dumps({'file': str(path), 'state': 'proposed', 'proposed_entries': record['history']['proposed_entries']}))


def legacy_final(marker):
    values = [line.strip().strip('*').strip() for line in marker.splitlines() if line.strip().strip('*').strip()]
    return bool(values) and all(re.match(r'(?i)^(?:-\s*(?:[^:]+:\s*)?)?(?:applied|already_satisfied|failed|blocked|unverified)\b', v) for v in values)


def reconcile_plan(folder):
    arch = local(folder, 'demo-architecture.md')
    text = read(arch) if arch.exists() else ''
    stamp = re.search(r'^Reconciled through:.*?changes-(\d{4}-\d\d-\d\d-\d{4})-', text, re.M)
    prior = stamp[1] if stamp else ''
    files = sorted((p for p in folder.glob('changes-*.md')
                    if (m := re.fullmatch(r'changes-(\d{4}-\d\d-\d\d-\d{4})-[\w.-]+\.md', p.name)) and m[1] > prior), reverse=True)
    for n, path in enumerate(files):
        print(json.dumps({'file': str(path), 'read': 'full' if n < 5 else 'last-section'}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('render', 'resolve', 'check'):
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
            pending(args.orgs_dir.resolve(strict=True), args.org_id, args.username)
        elif args.command == 'reconcile-plan':
            reconcile_plan(args.folder.resolve(strict=True))
        else:
            task = args.task.absolute()
            record = task_record(task)
            if args.command == 'render':
                print(render(record), end='')
            elif args.command == 'resolve':
                resolve(task, record)
            else:
                return check(task, record)
    except BlockError as error:
        print(f'{getattr(args, "task", "history")}:1: block: {error}')
        return 3
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        print(f'{getattr(args, "task", "history")}:1: read: could not safely read/update history ({type(error).__name__})')
        return 4
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
