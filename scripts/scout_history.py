#!/usr/bin/env python3
"""Local /scout history: render, resolve owned checkpoints, discover and check."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
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
TYPE_ALIASES = {'pagelayout': 'layout', 'lightningapp': 'customapplication', 'path': 'pathassistant',
                'records': 'record', 'picklistvalues': 'standardvalueset'}
CHECKPOINT = re.compile(r'^### (PENDING|' + '|'.join(DISPOSITIONS) +
                        r') — component repair · attempt ([\w.-]+) · (\d{4}-\d\d-\d\d \d\d:\d\d)$')
OUTCOME = re.compile(r'^- \*\*Outcome: (' + '|'.join(DISPOSITIONS) + r')\.\*\* (\S.*)$', re.M)

CODE_SPAN = re.compile(r'(?<!`)(`+)(?!`)[^\r\n]*?(?<!`)\1(?!`)')
RECEIPT = re.compile(r'^<!-- scout-repair:([\w.-]+) -->\r?\n(.*?)'
                     r'^<!-- /scout-repair:\1 -->\r?$', re.M | re.S)


class BlockError(ValueError):
    pass


def read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        raise OSError('expected a bounded regular file, not a symlink')
    return path.read_bytes().decode('utf-8')


def orgs_directory(directory):
    directory = directory.absolute()
    if directory.name != 'orgs':
        # Diagnose an unreadable parent (including a loop) before rejecting its layout.
        directory.resolve(strict=True)
        raise OSError('expected an orgs directory')
    # Resolve only the workspace, the parent of orgs/, once. Never follow links below it.
    workspace = directory.parent.resolve(strict=True)
    directory = workspace / directory.name
    if directory.is_symlink() or not directory.is_dir():
        raise OSError('expected a regular orgs directory below the workspace')
    return directory


def org_folder(folder):
    folder = orgs_directory(folder.absolute().parent) / folder.name
    if folder.is_symlink() or not folder.is_dir():
        raise OSError('expected a regular direct child of orgs')
    return folder


def local(folder, name):
    folder = org_folder(folder)
    if not name or '..' in Path(name).parts:
        raise OSError('record path must stay inside its regular folder')
    path = folder / name
    if Path(name).is_absolute():
        root = next((p for p in path.parents if p.name == 'orgs' and orgs_directory(p) == folder.parent), None)
        if root is None:
            raise OSError('record path escaped its workspace')
        path = folder.parent / path.relative_to(root)
    if not path.is_relative_to(folder):
        raise OSError('record path escaped its folder')
    relative = path.relative_to(folder)
    if any((folder / Path(*relative.parts[:n])).is_symlink() for n in range(len(relative.parts) + 1)):
        raise OSError('symlink path refused')
    return path


def container_prefix(line):
    """The literal indentation/blockquote/list prefix, at any nesting depth."""
    return re.match(r'^(?:\ufeff)?[ \t]*(?:(?:>[ \t]*|(?:[-+*]|\d+[.)])[ \t]+)[ \t]*)*', line)[0]


def markdown(text):
    """Mask fenced examples, preserving offsets; also return actual scout-items blocks."""
    visible, blocks, body, fence, info, container = [], [], [], '', '', ''
    for line in text.splitlines(keepends=True):
        prefix = container_prefix(line)
        match = re.match(r'(`{3,}|~{3,})([^\r\n]*)', line[len(prefix):])
        if not fence and match:
            fence, info, container = match[1], match[2].strip(), prefix
            body = []
        elif fence:
            if (match and prefix == container and match[1][0] == fence[0] and
                    len(match[1]) >= len(fence) and not match[2].strip()):
                if info == 'scout-items' and not container.strip():
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
    """Inventory ATX/setext headings and their complete title spans, including containers."""
    visible, _ = markdown(text)
    matches, paragraph, offset, list_indent = [], [], 0, 0
    for line in visible.splitlines(keepends=True):
        clean = re.sub(r'^(?:\ufeff)?(?: {0,3}>[ \t]*)*', '', line).rstrip('\r\n')
        item = re.match(r'^( *)(?:[-+*]|\d+[.)])[ \t]+', clean)
        if item:
            list_indent = item.end()
            clean = clean[item.end():]
        elif list_indent and len(clean) - len(clean.lstrip()) >= list_indent:
            clean = clean[list_indent:].lstrip()
        elif clean.strip():
            list_indent = 0
        atx = re.fullmatch(r' {0,3}(#{1,6})(?:[ \t]+(.*))?', clean)
        if atx:
            matches.append((atx[2] or '', len(atx[1]), offset, offset + len(line)))
            paragraph = []
        elif paragraph and re.fullmatch(r'=+|-+', clean.strip()):
            matches.append(('\n'.join(title for title, _ in paragraph),
                            1 if clean.strip()[0] == '=' else 2, paragraph[0][1], offset + len(line)))
            paragraph = []
        elif clean.strip():
            paragraph.append((clean, offset))
        else:
            paragraph = []
        offset += len(line)
    result = []
    for n, (title, level, start, body) in enumerate(matches):
        end = next((m[2] for m in matches[n + 1:] if m[1] <= level), len(text))
        result.append((title, level, start, end, visible[body:end]))
    return result


def document_header(text):
    visible, _ = markdown(text)
    for n, (title, level, start, _, _) in enumerate(headings(text)):
        if not title.strip() or n or level != 1 or visible[:start].strip('\ufeff \t\r\n'):
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
    header = document_header(text)
    refs = re.findall(r'^Task record: (.+)\r?$', header, re.M)
    return len(refs) == 1 and refs[0].strip().strip('`') in (task.name, str(task))


def own_body(body):
    """The owning section ends before the first nested heading; fences stay masked."""
    sections = headings(body)
    return markdown(body)[0][:sections[0][2] if sections else len(body)]


def section_body(text, section):
    """Recover the full raw body; headings mask fences while preserving offsets."""
    return text[section[3] - len(section[4]):section[3]]


def checkpoint_range(text, section, sections):
    """Agreement ends at the next checkpoint or its Checkpoints section's end.

    Ordinary headings never truncate an attempt. Keep discovery's heading-based
    inventory unchanged, and preserve the original start of the body's text.
    """
    start, body = section[2], section[3] - len(section[4])
    end = next((s[3] for s in sections if s[0] == 'Checkpoints' and s[1] == 2 and s[2] < start < s[3]), len(text))
    end = next((s[2] for s in sections if start < s[2] < end and checkpoint_heading(s[0])), end)
    return (*section[:3], end, text[body:end])


def unmark(text, offsets=False):
    """Remove inline presentation; resolve alone needs character offsets preserved."""
    return re.sub(r'<[^>\r\n]*>|\]\([^\r\n)]*\)|[*`~\[\]\\]|_{2,}|(?<!\w)_(?=\w)|(?<=\w)_(?!\w)',
                  lambda m: ' ' * len(m[0]) if offsets else '', text)


def mask_code_spans(text):
    """Code-span data cannot supply labels or agreement; retain character offsets."""
    return CODE_SPAN.sub(lambda m: ' ' * len(m[0]), text)


def evidence_spans(line):
    """Links and path/URL tokens are evidence, never sources of field labels."""
    spans = [m.span() for m in CODE_SPAN.finditer(line)]
    spans += [m.span() for m in re.finditer(r'!?\[[^\]\r\n]*\](?:\([^\r\n)]*\)|\[[^\]\r\n]*\])|<[^\s<>]+:[^<>]*>', line)]
    for match in re.finditer(r'\S+', line):
        token = match[0].strip('`*_<>"\'(),;')
        if (len(token) > 1 and not token.endswith(':') and
                (re.search(r'[/\\]', token) or re.fullmatch(r'\S+\.[A-Za-z0-9]+', token))):
            spans.append(match.span())
    return spans


def evidence_mask(line):
    """Hide evidence from label recognition while preserving original offsets."""
    chars = list(line)
    for start, end in evidence_spans(line):
        chars[start:end] = ' ' * (end - start)
    return ''.join(chars)


def field_text(line):
    return unmark(evidence_mask(line), offsets=True)


def fields(body, offsets=False, masked=True):
    """Qualified/compound fields, fence-masked by default.

    Delimiters end the WHOLE value. Offsets refer to the original characters;
    inline presentation is removed only for interpreting labels and values.
    """
    offset = 0
    source = markdown(body)[0] if masked else body
    for line in mask_code_spans(source).splitlines(keepends=True):
        clean = field_text(line).rstrip('\r\n')
        value = r'([^;|\r\n]*?)(?= · |[;|]|$)'
        pattern = (r'(?:^[ \t]*(?:>[ \t]*)*(?:[-+][ \t]+|\d+[.)][ \t]+)?|[;|]| · )'
                   r'([\w /._-]+(?:\([^\r\n)]*\)[ \t]*)?):' + value)
        entries = []
        for match in re.finditer(pattern, clean):
            label = re.sub(r'\([^)]*\)', '', match[1]).strip().lower()
            label = re.sub(r'[\s/._-]', '', label)
            if label not in ('outcome', 'finaloutcome', 'outcomereadback'):
                entries.append((label, match.start(2), match.end(2)))
        # Outcome fields can occur anywhere on a compound line, not just its start.
        outcome = (r'\b(?:final[ \t]+)?outcome(?:[ \t]*/[ \t]*read-back)?'
                   r'[ \t]*(?:\([^\r\n)]*\)[ \t]*)?:' + value)
        entries.extend(('outcome', m.start(1), m.end(1)) for m in re.finditer(outcome, clean, re.I))
        for label, start, end in sorted(entries, key=lambda entry: entry[1]):
            value = unmark(line[start:end], offsets=offsets)
            yield label, value, offset + start, offset, source[offset:offset + len(line)].rstrip('\r\n')
        offset += len(line)


def own_outcome(body, receipt_ids=()):
    outcomes = OUTCOME.findall(own_body(body).replace('\r\n', '\n'))
    if len(outcomes) != 1:
        return None
    outcome = outcomes[0][0]
    return outcome if scout_agreement(body, outcome, receipt_ids) else None


def status_fields(body, nested=False, receipt_ids=()):
    """Lexical pending lint: backtick spans and the writer's JSON delta strings exempt."""
    # Equal-length backtick runs delimit a span; triple fence lines have no closer.
    visible = CODE_SPAN.sub('', mask_receipt_delta(body, receipt_ids))
    if re.search(r'\bpending\b', visible, re.I) or re.search(r'\bpending\b', unmark(visible), re.I):
        yield 'pending', 0, 0


def marked_receipts(text):
    return [match[2] for match in RECEIPT.finditer(text)]


def task_receipts(task):
    # Repair IDs are generated independently; never infer them from a filename.
    # The route requires every checkpoint marker to be recorded in this task.
    return set(re.findall(r'<!-- scout-repair:([\w.-]+) -->', read(task)))


def owned_receipt(match, receipt_ids):
    """Both exemptions require the exact marker recorded in this task."""
    return match[1] in receipt_ids


def mask_receipt_delta(text, receipt_ids=()):
    """Mask exactly the two JSON strings written by Repair.checkpoint, in paired receipts.

    Preserve offsets and every other character, including other quoted business
    values and pending placeholders. No receipt or delta is edited on disk.
    """
    string = r'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"'
    # Current writer labels are code spans, with arbitrary data inside each.
    labels = (r'(?P<column>`+)(?!`)[^\r\n]*?(?<!`)(?P=column)(?!`) '
              r'(?P<operator>`+)(?!`)[^\r\n]*?(?<!`)(?P=operator)(?!`)')
    delta = re.compile(r'^- \*\*Requested delta / exclusions:\*\* (?:' + labels +
                       r'|[^`\r\n:]+): (?P<before>' + string + r') → (?P<after>' + string + r')(?=;)', re.M)

    def receipt(match):
        if not owned_receipt(match, receipt_ids):
            return match[0]
        def values(row):
            value = row[0]
            for group in ('after', 'before'):
                start, end = row.start(group) - row.start(), row.end(group) - row.start()
                value = value[:start] + ' ' * (end - start) + value[end:]
            return value
        return delta.sub(values, match[0])

    return RECEIPT.sub(receipt, text)


def existing_classification(text):
    # Keep only the classification value, through its continuations or delimiter.
    for source in [text, *marked_receipts(text)]:
        visible = mask_code_spans(markdown(source)[0])
        values = []
        for label, value, start, offset, _ in fields(source, offsets=True):
            if label not in ('classification', 'classificationsource'):
                continue
            tail = visible[offset:].splitlines()[1:]
            # A delimiter on the first line ends the value before any continuation.
            first = visible[offset:].splitlines()[0]
            ended = bool(re.search(r' · |[;|]', first[start - offset + len(value):]))
            coded_value = CODE_SPAN.search(source[start:start + len(value)])
            value = unmark(first[start - offset:start - offset + len(value)])
            for line in tail:
                if ended or not line.strip() or not line.startswith((' ', '\t', '>')):
                    break
                clean = unmark(line)
                value += '\n' + re.split(r' · |[;|]', clean, maxsplit=1)[0]
                ended = bool(re.search(r' · |[;|]', clean))
            if not value.strip(' \t\r\n>+-'):
                if coded_value:
                    continue
                raise BlockError('empty classification value')
            values.append(value)
            # Separate component classifications in the adapter's compound label.
            if label == 'classificationsource':
                values.extend(re.findall(r'(?:^|;)\s*(?:Report|ReportFolder):\s*(existing|new|unknown)\b', unmark(first), re.I))
        for line in unmark(visible).splitlines():
            cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
            if len(cells) > 1 and re.sub(r'[\s/._-]', '', cells[0]).lower() in ('classification', 'classificationsource'):
                values.append(cells[1])
        if any(re.search(r'\bexisting\b', value, re.I) for value in values):
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
    receipt_ids = task_receipts(task)
    sections = headings(original)
    matches = [(checkpoint_range(original, s, sections), m) for s in sections
               if (m := CHECKPOINT.fullmatch(original[s[2]:].splitlines()[0]))]
    changes, updated = [], original
    for section, match in reversed(matches):
        if not match or match[2] not in owners or owners[match[2]]['disposition'] not in DISPOSITIONS:
            continue
        if sum(bool(m and m[2] == match[2]) for _, m in matches) != 1:
            continue
        body = section_body(original, section)
        outcome = own_outcome(body, receipt_ids)
        if outcome is None or (match[1] != 'PENDING' and match[1] != outcome):
            continue
        start, end = section[2:4]
        block = original[start:end]
        replacement = block
        prefix = len(block.splitlines(keepends=True)[0])
        for label, value, first, _, line in reversed(list(fields(own_body(block[prefix:]), offsets=True))):
            if label == 'outcome' and not OUTCOME.fullmatch(line):
                last = first + len(value)
                raw = block[prefix + first:prefix + last]
                if not unmark(raw).strip() or evidence_spans(raw):
                    continue
                # Preserve label closures and balanced value markup, not qualifiers.
                lead = re.match(r'[ \t*_`~]*', raw)[0]
                opening = re.search(r'[*_`~]*$', lead)[0]
                closing = opening[::-1]
                token = re.match(r'(?:pending|' + re.escape(outcome) + r')([*_`~]*)', raw[len(lead):], re.I)
                if not closing or not (raw.rstrip().endswith(closing) or (token and token[1] == closing)):
                    closing = ''
                value = lead + outcome + closing + re.search(r'[ \t]*$', raw)[0]
                replacement = replacement[:prefix + first] + value + replacement[prefix + last:]
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
    receipt_ids = task_receipts(task)
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
        owned = [checkpoint_range(text, s, sections) for s in sections
                 if CHECKPOINT.fullmatch(text[s[2]:].splitlines()[0])]
        header = document_header(text).lstrip('\ufeff \t\r\n')
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
        if any(own_outcome(section_body(text, s), receipt_ids) in ('applied', 'failed', 'unverified') and
               existing_classification(text[s[2]:s[3]]) for s in owned):
            required.append((2, 'Existing Component Before-State and Direct Repairs'))
        for section in sections:
            if section[1] == 2 and section[0].startswith('Existing Component Before-State and Direct Repairs'):
                if any(status_fields(text[section[2]:section[3]], nested=True, receipt_ids=receipt_ids)):
                    issue('checkpoint', 'pending before-state status fields', log)
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
            if checkpoint_heading(section[0]):
                match = CHECKPOINT.fullmatch(text[section[2]:].splitlines()[0])
                if not match or match[2] not in recorded:
                    issue('checkpoint', 'unrecorded checkpoint: ' + section[0], log)
                if not (len(checkpoint_sections) == 1 and checkpoint_sections[0][2] < section[2] < checkpoint_sections[0][3]
                        and checkpoint_sections[0][3] == len(text)):
                    issue('checkpoint', 'checkpoint outside final Checkpoints section: ' + section[0], log)
        for item in items.values():
            attempted = item['disposition'] in ('applied', 'failed', 'unverified')
            if ((attempted and not item['attempts']) or
                    (item['disposition'] == 'omitted' and item['attempts'])):
                issue('checkpoint', item['id'] + ' attempt count disagrees with disposition', log)
            for attempt in item['attempts']:
                candidates = [s for s in owned if (m := CHECKPOINT.fullmatch(text[s[2]:].splitlines()[0])) and m[2] == attempt]
                valid = len(candidates) == 1
                if valid:
                    section = candidates[0]
                    match = CHECKPOINT.fullmatch(text[section[2]:].splitlines()[0])
                    body = section_body(text, section)
                    outcome = own_outcome(body, receipt_ids)
                    if ((attempted and attempt == item['attempts'][-1]) or item['disposition'] in ('already_satisfied', 'blocked')) and outcome != item['disposition']:
                        issue('checkpoint', item['id'] + ' attempt outcome disagrees with disposition', log)
                    valid = (bool(checkpoint_sections) and checkpoint_sections[0][2] < section[2] < checkpoint_sections[0][3]
                             and checkpoint_sections[0][3] == len(text))
                    if item['disposition'] in DISPOSITIONS:
                        valid &= outcome is not None and match[1] == outcome and not any(status_fields(text[section[2]:section[3]], nested=True, receipt_ids=receipt_ids))
                    else:
                        valid &= match[1] == 'PENDING'
                if not valid:
                    issue('checkpoint', attempt + ' missing, duplicate, misplaced or unsettled outcome/fields', log)
        # Inspect each opener so a nested foreign pair still gets its diagnostic.
        for start in re.finditer(r'^<!-- scout-repair:[\w.-]+ -->\r?$', text, re.M):
            marker = RECEIPT.match(text, start.start())
            if marker and not owned_receipt(marker, receipt_ids):
                issue('checkpoint', 'unrecorded report marker; copy the marker <!-- scout-repair:' + marker[1] + ' -->' +
                      ' into task record ' + str(task) + ' (required before apply-report)', log,
                      line=text[:marker.start()].count('\n') + 1)
    if record['history']['architecture'] in ('created', 'reconciled'):
        arch = local(task.parent, 'demo-architecture.md')
        if not arch.exists():
            issue('arch', 'architecture missing', arch)
        else:
            text = read(arch)
            visible, _ = markdown(text)
            visible = visible.replace('\r\n', '\n')
            header = document_header(visible).replace('\ufeff', '', 1)
            if (not re.search(r'^# Demo Architecture — \S.+$', header, re.M) or
                    not re.search(r'^Last reconciled: \d{4}-\d\d-\d\d \d{4} by /scout$', header, re.M) or
                    not re.search(r'^Target Org: \S.+$', header, re.M) or
                    not re.search(r'^Reconciled through: `?' + re.escape(record['change_log']) + r'`?$', header, re.M)):
                issue('arch', 'missing template title/headers or current log stamp', arch)
            created = record['history']['architecture'] == 'created'
            map_text = text.replace('\r\n', '\n')
            map_sections = headings(map_text)
            lines = map_text.splitlines()
            visible_lines = markdown(map_text)[0].splitlines()
            heading_lines = {n for section in map_sections
                             for n in range(map_text[:section[2]].count('\n'),
                                            len(map_text[:section[3] - len(section[4])].splitlines()))}
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
                           if line.strip() and not headings(line) and
                           (created or not line.lstrip().startswith('>'))):
                        issue('arch', 'arc beats must be <=320 characters', arch)
            # Current-task references are owned wherever they occur, including nested/SE sections.
            for n, line in enumerate(visible_lines):
                current = bool(stamp.search(line)) and not (n < len(header.splitlines()) and line.startswith('Reconciled through:'))
                following = visible_lines[n + 1:n + 2]
                continuation = (following and following[0].strip() and n + 1 not in heading_lines and
                                not re.match(r'^(?:[-+*] |\d+[.)] )', following[0]))
                if current:
                    owned.add(n)
                    if len(line) > 320 or continuation:
                        issue('arch', 'current-task entries must be single lines <=320 characters', arch)
                if created and n not in heading_lines and (line.strip() or not lines[n].strip()) and len(line) > 320:
                    issue('arch', 'created map lines must be <=320 characters', arch)
                if n in decision_lines and (current or (created and line.startswith('- '))):
                    if len(line) > 320 or continuation or not re.match(r'^- \*\*\[\d{4}-\d\d-\d\d\]\*\* — ', line):
                        issue('arch', 'current decision must be a dated line <=320 characters', arch)
            template = map_text if created else '\n'.join(lines[n] for n in sorted(owned))
            over = lambda value: len(value.splitlines()) > 350 or len(value.split()) > 3750
            if over(text):
                issue('arch', 'map exceeds 350 lines / 3750 words' + (' only due to SE sections' if not over(template) else ''),
                      arch, warning=not over(template))
    print('\n'.join(findings + warnings) or f'{task}:1: check: pass')
    return 3 if findings else 0


def checkpoint_heading(title):
    return bool('PENDING' in title or 'PENDING' in unmark(title) or
                (re.search(r'\bpending\b', unmark(title), re.I) and
                 re.search(r'\bcomponent\s+repair\b', unmark(title), re.I)) or
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
        identified = any(re.search(
            r'(?im)^(?:Org|Target Org|Bound org ID):[^\r\n]*(?:\b00D[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\b' +
            (r'|[\w.+-]+@[\w.-]+' if path.name.startswith('changes-') else '') + ')', document_header(t))
            for path, t in texts)
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
            sections = headings(text)
            for title, _, start, end, body in sections:
                if not checkpoint_heading(title):
                    continue
                state = checkpoint_state(text[start:].splitlines()[0], title, text[end - len(body):end])
                print(json.dumps({'file': str(path), 'line': text[:start].count('\n') + 1, 'state': state, 'heading': title}))
            # Fail closed when a deeply nested/indented heading escaped inventory.
            # Title spans prevent duplicates, including multi-line setext titles.
            offset = 0
            lines = markdown(text)[0].splitlines(keepends=True)
            for n, line in enumerate(lines):
                clean = line[len(container_prefix(line)):].strip()
                atx = re.fullmatch(r'#{1,6}[ \t]+(.+)', clean)
                setext = n + 1 < len(lines) and re.fullmatch(
                    r'=+|-+', lines[n + 1][len(container_prefix(lines[n + 1])):].strip())
                title = atx[1] if atx else clean if setext else ''
                placed = any(s[2] <= offset < s[3] - len(s[4]) for s in sections)
                if checkpoint_heading(title) and not placed:
                    print(json.dumps({'file': str(path), 'line': n + 1, 'state': 'unclear', 'heading': title}))
                offset += len(line)
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
    """Discovery only: the exact owned FINAL heading is the sole resolved evidence.

    Every other candidate (owned PENDING included) is unclear if its full raw
    body mentions outcome, otherwise unresolved. Discovery never judges agreement.
    """
    own = CHECKPOINT.fullmatch(heading)
    if own and own[1] != 'PENDING':
        return 'resolved'
    return 'unclear' if re.search('outcome', body, re.I) else 'unresolved'


def receipt_outcome(value):
    """Map the report adapter's Outcome / read-back by the route's table."""
    value = value.strip().lower()
    if value in ('applied', 'already_satisfied', 'blocked'):
        return value
    if re.match(r'blocked — not_applied\b', value):
        return 'failed'
    if re.match(r'unverified\b', value) or value == 'released by operator':
        return 'unverified'
    if re.match(r'pending\b', value):
        return 'pending'
    return None


def paragraph_line(line):
    """Indent and structural boundaries for labelled paragraph values."""
    plain = line.rstrip('\r\n').expandtabs(4)
    while re.match(r'^[ ]*>', plain):
        plain = re.sub(r'^([ ]*)> ?', r'\1', plain, count=1)
    indent = len(plain) - len(plain.lstrip())
    content = plain.lstrip()
    boundary = (not content or bool(re.match(r'#{1,6}(?:\s|$)|`{3,}|~{3,}|(?:=+|-+)\s*$', content)))
    labelled = ':' in evidence_mask(content) or '|' in evidence_mask(content)
    item = bool(re.match(r'(?:[-+*]|\d+[.)])\s+', content))
    return indent, labelled or item, boundary


def paragraph_tail(lines, index):
    """Lazy/deeper continuations end at structure or a same/shallow peer field."""
    indent = paragraph_line(lines[index])[0]
    result = []
    for line in lines[index + 1:]:
        depth, peer, boundary = paragraph_line(line)
        if boundary or (peer and depth <= indent):
            break
        result.append(line)
    return result


def scout_agreement(body, outcome, receipt_ids=()):
    """One own canonical line plus agreement through the next checkpoint boundary.

    Labelled paragraph values include lazy/deeper continuations. Every disposition
    word there agrees. Outcome values are stricter: every word, item labels aside,
    is the canonical outcome. Only a single-line pending field at an exact writable
    own offset is exempt. Evidence links/paths are never field labels or rewrite
    targets; code spans supply no fields or agreement words. Report marker pairs
    occupy whole lines; task registration accepts the literal marker anywhere on a line.
    Only owned pairs exempt delta strings and map read-back outcomes by the route.
    Discovery has its separate fixed rule.
    """
    writable_lines = {offset for label, _, _, offset, _ in fields(own_body(body), offsets=True) if label == 'outcome'}
    receipts = [m for m in RECEIPT.finditer(body)
                if owned_receipt(m, receipt_ids)]
    normal = lambda value: value.translate(str.maketrans('', '', '*_`'))
    final = normal(outcome)
    words = r'\b(?:' + '|'.join(normal(value) for value in DISPOSITIONS) + r')\b'
    lines = mask_code_spans(mask_receipt_delta(body, receipt_ids)).splitlines(keepends=True)
    offset = 0
    for n, line in enumerate(lines):
        raw = line.rstrip('\r\n')
        canonical = OUTCOME.fullmatch(raw)
        if canonical and canonical[1] != outcome:
            return False
        source = canonical[2] if canonical else raw
        receipt = any(m.start(2) <= offset < m.end(2) for m in receipts)
        outcome_fields = [value.strip() for label, value, *_ in fields(source if receipt else normal(source), masked=False)
                          if label == 'outcome']
        cells = [cell.strip() for cell in normal(source).strip().strip('|').split('|')]
        table = len(cells) > 1 and any(label == 'outcome' and not value.strip()
                                     for label, value, *_ in fields(cells[0] + ':', masked=False))
        if table:
            outcome_fields.append(cells[1])
        if receipt:
            mapped = re.match(r'^- Outcome / read-back:', unmark(source))
            if outcome_fields and (not mapped or any(receipt_outcome(value) != outcome for value in outcome_fields)):
                return False
            offset += len(line)
            continue
        tail = paragraph_tail(lines, n) if ':' in evidence_mask(source) or table or outcome_fields else []
        for value in outcome_fields:
            if any(word.lower() != final for word in re.findall(words, normal(value), re.I)):
                return False
            if re.match(r'pending\b', value, re.I):
                writable = [v for label, v, *_ in fields(raw, offsets=True) if label == 'outcome']
                if (tail or table or canonical or offset not in writable_lines or
                        len(writable) != len(outcome_fields) or any(evidence_spans(v) for v in writable)):
                    return False
                continue
            content = normal(unmark(value + '\n' + ''.join(tail)))
            content = re.sub(r'\bI\d+\s*:', '', content, flags=re.I)
            if any(word.lower() != final for word in re.findall(r'\w+', content)):
                return False
        plain = normal(source)
        labelled = ':' in evidence_mask(source) or '|' in evidence_mask(source)
        continuation = bool(re.match(r'^(?:[ \t]+|>[ \t]*|[-+][ \t]+|\d+[.)][ \t]+)', plain))
        if (labelled or continuation) and any(word.lower() != final for word in re.findall(words, plain + '\n' + ''.join(map(normal, tail)), re.I)):
            return False
        offset += len(line)
    return True


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
            return pending(orgs_directory(args.orgs_dir), args.org_id, args.username)
        elif args.command == 'reconcile-plan':
            reconcile_plan(org_folder(args.folder))
        else:
            task = local(args.task.absolute().parent, args.task.name)
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
    except (OSError, UnicodeError, ValueError, RuntimeError) as error:
        print(f'{getattr(args, "task", "history")}:1: read: could not safely read/update history ({type(error).__name__})')
        return 4
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
