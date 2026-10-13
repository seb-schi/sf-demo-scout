#!/usr/bin/env python3
"""Read-only demo-day prep for /scout (W9): constructed checks, a total verdict, and a safe demo-path.md.

Subcommands:
  run      execute one allowlisted read-only check against the bound org (query, describe, retrieve)
  verdict  compute the readiness verdict from a results file
  render   build the candidate demo-path.md from a results file and the folder's current file
  check    gate a candidate against its results and the bound identity (exit 0 before publishing)
  publish  replace demo-path.md atomically, preserving every byte outside Scout's regions

Standard library only, Python 3.9 or newer, safe under -S and -B. Exit codes: 0 pass, 2 usage,
3 findings or refusal, 4 couldn't read or run.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import scout_target
    from scout_report_repair import LIMIT, decode
except ImportError:
    print(json.dumps({'reason': 'prep helper dependencies unavailable'}))
    raise SystemExit(4)

TIMEOUT = 120
STATES = ('passed', 'failed', 'unavailable', 'open', 'unknown', 'eye', 'visual_qa', 'persona')
EXCEPTIONS = ('eye', 'visual_qa', 'persona')
KINDS = ('claim', 'item', 'flip', 'checkpoint', 'job', 'manual', 'config', 'persona', 'visual_qa')
VERDICTS = ('ready', 'ready with exceptions', 'not ready')
REGIONS = ('drift', 'checklist', 'path', 'seams', 'runs')
BEGIN = re.compile(r'^<!-- scout:begin ([a-z]+) sha256=([0-9a-f]{64}) -->$')
END = re.compile(r'^<!-- scout:end ([a-z]+) -->$')
IDENT = r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*'
QUERY = re.compile(r'SELECT\s+(?P<fields>.+?)\s+FROM\s+(?P<object>' + IDENT + r')'
                   r'(?:\s+WHERE\s+(?P<where>.+?))?(?:\s+GROUP\s+BY\s+(?P<group>.+?))?'
                   r'(?:\s+ORDER\s+BY\s+(?P<order>.+?))?(?:\s+LIMIT\s+(?P<limit>\d{1,5}))?', re.I | re.S)
FORBIDDEN = re.compile(r'\b(?:FOR\s+(?:VIEW|REFERENCE|UPDATE)|USING\s+SCOPE|ALL\s+ROWS)\b|[;`\\]|\$\(|&&|\|\|', re.I)


class Refused(Exception):
    """A check, a gate or a publication that must not proceed."""


def validate_query(query):
    """The constrained SOQL grammar (N2): one read-only SELECT, no stateful or locking clause."""
    text = ' '.join(unicodedata.normalize('NFKC', query).split())
    if FORBIDDEN.search(text) or not QUERY.fullmatch(text) or len(text) > 4000:
        raise Refused('query outside the read-only grammar')
    return text


def now(clock=None):
    moment = datetime.datetime.fromisoformat(clock) if clock else datetime.datetime.now().astimezone()
    if moment.tzinfo is None:
        raise Refused('times need a timezone')
    return moment


def run_cli(args):
    executable = shutil.which('sf')
    if not executable:
        raise Refused('Salesforce CLI unavailable')
    scratch = Path(tempfile.mkdtemp(prefix='scout-prep-'))
    try:
        result = subprocess.run([executable, *args, '--json'], cwd=scratch, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError) as error:
        raise Refused('CLI unavailable or timed out') from error
    if result.returncode or len(result.stdout) > LIMIT:
        raise Refused('CLI operation failed')
    try:
        envelope = decode(result.stdout)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise Refused('CLI returned unusable JSON') from error
    if not isinstance(envelope, dict) or envelope.get('status') != 0:
        raise Refused('CLI operation failed')
    return envelope.get('result'), scratch


def run_check(kind, selector, username, org, query=None, sobject=None, metadata=None, clock=None):
    """X6, X7, N3: bind first, then one constructed read-only call. Nothing stored is executed."""
    try:
        scout_target.bind(selector, {'username': username, 'org_id': org})
    except (scout_target.Unverified, scout_target.Mismatch) as error:
        raise Refused('binding check failed: ' + str(error)) from error
    if kind == 'query':
        result, _ = run_cli(['data', 'query', '--target-org', username, '--query', validate_query(query or '')])
        observed = {'totalSize': result.get('totalSize') if isinstance(result, dict) else None,
                    'records': (result or {}).get('records', [])[:200] if isinstance(result, dict) else []}
    elif kind == 'describe':
        if not re.fullmatch(IDENT, sobject or ''):
            raise Refused('invalid sObject name')
        result, _ = run_cli(['sobject', 'describe', '--sobject', sobject, '--target-org', username])
        observed = {'fields': sorted(f.get('name', '') for f in (result or {}).get('fields', []) if isinstance(f, dict))}
    elif kind == 'retrieve':
        if not re.fullmatch(r'[A-Za-z]+:[A-Za-z0-9_.\- ]+', metadata or ''):
            raise Refused('invalid metadata member')
        target = Path(tempfile.mkdtemp(prefix='scout-prep-retrieve-'))
        result, _ = run_cli(['project', 'retrieve', 'start', '--metadata', metadata, '--target-metadata-dir', str(target),
                             '--unzip', '--target-org', username])
        observed = {'directory': str(target), 'files': sorted(str(p.relative_to(target)) for p in target.rglob('*') if p.is_file())[:200]}
    else:
        raise Refused('unsupported check kind')
    return {'kind': kind, 'observed': observed, 'at': now(clock).isoformat(timespec='seconds')}


def read_exact(path):
    """Read text without newline translation, so CRLF and every other byte survive (X10)."""
    with open(path, encoding='utf-8', newline='') as stream:
        return stream.read()


def load_results(path):
    data = json.loads(read_exact(path))
    if not isinstance(data, dict) or data.get('schema') != 1:
        raise Refused('results need schema 1')
    for key in ('folder', 'org_id', 'username', 'observed_at'):
        if not isinstance(data.get(key), str) or not data[key]:
            raise Refused('results need ' + key)
    if not isinstance(data.get('obligations'), list) or not isinstance(data.get('sources', []), list):
        raise Refused('results need obligations and sources lists')
    keys = set()
    for obligation in data['obligations']:
        if not isinstance(obligation, dict) or not isinstance(obligation.get('key'), str) or '#' not in obligation['key']:
            raise Refused('every obligation needs a task-qualified key')  # X4: task file plus local ID
        if obligation['key'] in keys:
            raise Refused('duplicate obligation key ' + obligation['key'])
        keys.add(obligation['key'])
    return data


def normalized(obligation, demo_time):
    """X1, round 2: every state maps to one class, and anything unrecognized fails closed."""
    if obligation.get('superseded_by'):
        return 'superseded', 'superseded by ' + str(obligation['superseded_by'])
    result = obligation.get('result') if isinstance(obligation.get('result'), dict) else {}
    status = result.get('status')
    kind = obligation.get('kind')
    if kind not in KINDS or status not in STATES:
        return 'blocking', 'unrecognized kind or state'
    if status == 'passed':
        until = obligation.get('valid_until')
        if until and demo_time and datetime.date.fromisoformat(until) < demo_time.date():
            return 'blocking', 'passes now but expires before the demo (%s)' % until
        if not result.get('at'):
            return 'blocking', 'a pass with no observation time'
        return 'passed', ''
    if status in EXCEPTIONS:
        return 'exception', status.replace('_', ' ')
    return 'blocking', status


def verdict(data, demo_time=None):
    """The ordered, total table: not ready, then ready with exceptions, then ready."""
    reasons, exceptions, passed, total = [], [], 0, 0
    for source in data.get('sources', []):
        if source.get('state') in ('unreadable', 'quarantined', 'malformed') and source.get('required', True):
            reasons.append('source %s is %s' % (source.get('path'), source.get('state')))  # N1
    required = [o for o in data['obligations'] if o.get('required', True)]
    if not [o for o in required if normalized(o, demo_time)[0] != 'superseded']:
        reasons.append('no recoverable story or proof moment')
    elif not any(o.get('proof_moment') for o in required if normalized(o, demo_time)[0] != 'superseded'):
        reasons.append('no proof-moment obligation')
    for obligation in data['obligations']:
        state, why = normalized(obligation, demo_time)
        if state == 'superseded':
            continue
        total += 1
        if state == 'passed':
            passed += 1
        elif state == 'exception' or not obligation.get('required', True):
            exceptions.append('%s: %s' % (obligation['key'], why or 'optional and not passed'))
        else:
            reasons.append('%s: %s' % (obligation['key'], why))
    result = 'not ready' if reasons else 'ready with exceptions' if exceptions else 'ready'
    return {'verdict': result, 'passed': passed, 'total': total, 'blocking': reasons, 'exceptions': exceptions}


def header(data, outcome):
    return 'Org-verified: %s against %s (%s) — %s — %d of %d checks passed' % (
        data['observed_at'], data['org_id'], data['username'], outcome['verdict'], outcome['passed'], outcome['total'])


def region(name, body):
    body = body if body.endswith('\n') else body + '\n'
    return '<!-- scout:begin %s sha256=%s -->\n%s<!-- scout:end %s -->\n' % (name, hashlib.sha256(body.encode()).hexdigest(), body, name)


def mark(obligation, demo_time):
    state = normalized(obligation, demo_time)[0]
    status = (obligation.get('result') or {}).get('status')
    return '✓' if state == 'passed' else 'check by eye' if status in EXCEPTIONS else '✗'


def regions_for(data, demo_time):
    outcome = verdict(data, demo_time)
    live = [o for o in data['obligations'] if normalized(o, demo_time)[0] != 'superseded']
    drift = [o for o in live if mark(o, demo_time) == '✗']
    beats = sorted({o.get('beat') for o in live if o.get('beat')}, key=lambda b: (len(b), b))
    path = [header(data, outcome), '']
    for beat in beats:
        rows = [o for o in live if o.get('beat') == beat]
        status = 'not ready' if any(mark(o, demo_time) == '✗' for o in rows) else (
            'ready with exceptions' if any(mark(o, demo_time) != '✓' for o in rows) else 'ready')
        path.append('### %s — %s' % (beat, status))
        for o in rows:
            star = ' ★' if o.get('proof_moment') else ''
            path.append('- %s %s%s (%s)' % (mark(o, demo_time), o.get('text') or o['key'], star, (o.get('result') or {}).get('at', 'not observed')))
        path.append('')
    return {
        'drift': '\n'.join(['## Drift since the build'] + ['- %s: %s' % (o['key'], (o.get('result') or {}).get('observed', 'not observed')) for o in drift] + (['None.'] if not drift else [])),
        'checklist': '\n'.join(['## Pre-demo checklist'] + ['- ' + r for r in outcome['blocking']] + (['None.'] if not outcome['blocking'] else [])),
        'path': '\n'.join(['## The path'] + path),
        'seams': '\n'.join(['## Known seams'] + ['- ' + e for e in outcome['exceptions']] + (['None.'] if not outcome['exceptions'] else [])),
        'runs': '\n'.join(['## Prep runs', '- %s: %s' % (data['observed_at'], outcome['verdict'])]),
    }, outcome


def parse_regions(text):
    """Scout's regions in file order; refuses malformed, nested or duplicated markers (X10)."""
    found, current, start, lines = {}, None, None, text.splitlines(keepends=True)
    offset = 0
    for line in lines:
        bare = line.rstrip('\r\n')
        begin, end = BEGIN.match(bare), END.match(bare)
        if 'scout:begin' in bare and not begin or 'scout:end' in bare and not end:
            raise Refused('malformed Scout marker')
        if begin:
            if current is not None or begin[1] in found:
                raise Refused('nested or duplicate Scout region')
            current, start, recorded = begin[1], offset, begin[2]
            content_start = offset + len(line)
        elif end:
            if current != end[1]:
                raise Refused('unmatched Scout region end')
            found[current] = dict(start=start, end=offset + len(line), body=text[content_start:offset], sha=recorded)
            current = None
        offset += len(line)
    if current is not None:
        raise Refused('unclosed Scout region')
    return found


def render(folder, data, demo_time):
    path = Path(folder) / 'demo-path.md'
    contents, outcome = regions_for(data, demo_time)
    if not path.exists():
        return '# Demo path\n\n' + ''.join(region(n, contents[n]) + '\n' for n in REGIONS), outcome
    text = read_exact(path)
    regions = parse_regions(text)
    if not regions:
        raise Refused('hand-made demo-path.md: leaving it untouched; the assessment goes inline')  # X11
    for name, found in regions.items():
        if hashlib.sha256(found['body'].encode()).hexdigest() != found['sha']:
            raise Refused('the SE edited Scout region "%s"; offer a new file instead' % name)  # X10
    pieces, cursor = [], 0
    for name, found in sorted(regions.items(), key=lambda item: item[1]['start']):
        pieces.append(text[cursor:found['start']])
        pieces.append(region(name, contents[name]) if name in contents else text[found['start']:found['end']])
        cursor = found['end']
    pieces.append(text[cursor:])
    missing = [n for n in REGIONS if n not in regions]
    return ''.join(pieces) + ''.join('\n' + region(n, contents[n]) for n in missing), outcome


def gate(candidate, data, org, username, demo_time):
    """C4 and X6: the candidate's stamp and verdict must match its results and the bound identity."""
    outcome = verdict(data, demo_time)
    problems = []
    if data['org_id'] != org or data['username'] != username:
        problems.append('results name another org or user than the binding')
    if header(data, outcome) not in candidate:
        problems.append('header missing, or its verdict or counts differ from the results')
    regions = parse_regions(candidate)
    for name in REGIONS:
        if name not in regions:
            problems.append('missing Scout region ' + name)
        elif hashlib.sha256(regions[name]['body'].encode()).hexdigest() != regions[name]['sha']:
            problems.append('region %s changed after rendering' % name)
    for obligation in data['obligations']:
        result = obligation.get('result')
        if normalized(obligation, demo_time)[0] != 'superseded' and not (isinstance(result, dict) and result.get('status')):
            problems.append(obligation['key'] + ' has no result')
    return problems


def publish(folder, candidate_path):
    """X12, X10, N6: back up, re-check, stage on the destination filesystem, replace atomically."""
    folder = Path(folder)
    destination = folder / 'demo-path.md'
    candidate = read_exact(candidate_path)
    before = destination.read_bytes() if destination.exists() else None
    if before is not None:
        parse_regions(before.decode('utf-8'))
        backups = folder / '.scout-work' / 'prep'
        backups.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        (backups / ('demo-path.%s.md' % stamp)).write_bytes(before)
    handle, staged = tempfile.mkstemp(prefix='demo-path.md.tmp-', dir=folder)
    try:
        with os.fdopen(handle, 'wb') as stream:
            stream.write(candidate.encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        current = destination.read_bytes() if destination.exists() else None
        if current != before:
            raise Refused('demo-path.md changed during prep; the previous copy is in .scout-work/prep')
        os.replace(staged, destination)
    finally:
        if os.path.exists(staged):
            os.unlink(staged)
    return str(destination)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run')
    run.add_argument('--kind', required=True, choices=('query', 'describe', 'retrieve'))
    for flag in ('--selector', '--username', '--org-id'):
        run.add_argument(flag, required=True)
    run.add_argument('--query')
    run.add_argument('--sobject')
    run.add_argument('--metadata')
    run.add_argument('--clock')
    for name in ('verdict', 'render', 'check'):
        sub = commands.add_parser(name)
        sub.add_argument('--results', required=True)
        sub.add_argument('--demo-time')
        if name == 'render':
            sub.add_argument('--folder', required=True)
            sub.add_argument('--out', required=True)
        if name == 'check':
            sub.add_argument('--candidate', required=True)
            sub.add_argument('--org-id', required=True)
            sub.add_argument('--username', required=True)
    pub = commands.add_parser('publish')
    pub.add_argument('--folder', required=True)
    pub.add_argument('--candidate', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'run':
            print(json.dumps(run_check(args.kind, args.selector, args.username, args.org_id, args.query,
                                       args.sobject, args.metadata, args.clock)))
            return 0
        if args.command == 'publish':
            print(json.dumps({'published': publish(args.folder, args.candidate)}))
            return 0
        data = load_results(args.results)
        demo_time = now(args.demo_time) if args.demo_time else None
        if args.command == 'verdict':
            print(json.dumps(verdict(data, demo_time)))
            return 0
        if args.command == 'render':
            text, outcome = render(args.folder, data, demo_time)
            with open(args.out, 'w', encoding='utf-8', newline='') as stream:
                stream.write(text)
            print(json.dumps({'candidate': args.out, 'verdict': outcome['verdict']}))
            return 0
        problems = gate(read_exact(args.candidate), data, args.org_id, args.username, demo_time)
        print('\n'.join('prep: ' + p for p in problems) or 'prep: check pass')
        return 3 if problems else 0
    except Refused as error:
        print(json.dumps({'refused': str(error)}))
        return 3
    except (OSError, UnicodeError, ValueError) as error:
        print(json.dumps({'reason': 'could not read or run (%s)' % type(error).__name__}))
        return 4


if __name__ == '__main__':
    raise SystemExit(main())
