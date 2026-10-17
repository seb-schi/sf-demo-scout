#!/usr/bin/env python3
"""Read-only demo-day prep for /scout: constructed checks, a total verdict, and a safe demo-path.md.

Subcommands:
  scratch  make a new, private scratch folder under the vetted base, for the results file
  run      execute one allowlisted read-only check against the bound org (query, describe, retrieve)
  verdict  compute the readiness verdict from a results file
  render   write the candidate demo-path.md and its metadata into a new scratch folder of its own, and name it
  check    gate a candidate against its results and the bound identity (exit 0 before publishing)
  publish  gate again, then replace demo-path.md without ever losing a concurrent save

Standard library only, Python 3.9 or newer, safe under -S and -B. Exit codes: 0 pass, 2 usage,
3 findings or refusal, 4 couldn't read or run.
"""
from __future__ import annotations

import argparse
import datetime
import errno
try:
    import fcntl
except ImportError:  # not on every platform; only recovery messages use it
    fcntl = None
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
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
RECORDS = 2000
SCRATCH_BASE = '/tmp'
NAME = 'demo-path.md'
MARKER = '<!-- scout:demo-path -->'
SET = re.compile(r'^<!-- scout:set sha256=([0-9a-f]{64}) -->$')
STATES = ('passed', 'failed', 'unavailable', 'open', 'unknown', 'eye', 'visual_qa', 'persona')
EXCEPTIONS = {'eye': ('claim', 'config', 'persona', 'visual_qa'), 'visual_qa': ('visual_qa',), 'persona': ('persona',)}
LABELS = {'eye': 'check by eye', 'visual_qa': 'visual QA', 'persona': 'persona access'}
KINDS = ('claim', 'item', 'flip', 'checkpoint', 'job', 'manual', 'config', 'persona', 'visual_qa')
SOURCES = ('read', 'unrelated')
REGIONS = ('drift', 'checklist', 'path', 'seams', 'runs')
TEXT_FIELDS = ('text', 'was', 'now', 'fix', 'superseded_by', 'supersession_source', 'drop_source')
BEGIN = re.compile(r'^<!-- scout:begin ([a-z]+) sha256=([0-9a-f]{64}) -->$')
END = re.compile(r'^<!-- scout:end ([a-z]+) -->$')
FENCE = re.compile(r' {0,3}(`{3,}|~{3,})')
KEY = re.compile(r'[\w.-]+\.md#[\w/.-]+')
BEAT = re.compile(r'[\w.-]+')
DATE = re.compile(r'\d{4}-\d{2}-\d{2}', re.A)
TIME = re.compile(r'(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(:\d{2}(?:\.\d{1,6})?)?(Z|[+-]\d{2}:?\d{2})', re.A)
HEADER = re.compile(r'org-verified\s*:', re.I)
RESERVED = re.compile(r'scout:(?:begin|end|demo-path|set)|org-verified\s*:', re.I)
BREAKS = re.compile(r'[\r\n\x0b\x0c\x1c-\x1e\x85\u2028\u2029]+')
# Whole credentials, including quoted values with spaces and bearer tokens with +, / and =.
SECRET = re.compile(r'00D[A-Za-z0-9]{12,15}![^\s"\'<>]+|\bBearer\s+[A-Za-z0-9._~+/=-]+|\b(?:access_?token|refresh_?token|'
                    r'session_?id|sid|password|passwd|client_?secret|secret)\b["\']?\s*[:=]\s*'
                    r'(?:"(?:[^"\\]|\\.)*"?|\'(?:[^\'\\]|\\.)*\'?|[^\s"\',;]+)', re.I)
IDENT = r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*'
TOKEN = re.compile(r"""(?P<space>[ \t\r\n]+)
    | (?P<string>'(?:[^'\\]|\\.)*')
    | (?P<datetime>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|[+-]\d{2}:\d{2}))
    | (?P<date>\d{4}-\d{2}-\d{2})
    | (?P<number>-?\d+(?:\.\d+)?)
    | (?P<word>""" + IDENT + r""")
    | (?P<op><=|>=|!=|<>|=|<|>)
    | (?P<punct>[(),:])""", re.X | re.S | re.A)
RESERVED_WORDS = {'SELECT', 'FROM', 'WHERE', 'GROUP', 'BY', 'ORDER', 'LIMIT', 'OFFSET', 'AND', 'OR', 'NOT', 'IN', 'LIKE',
                  'INCLUDES', 'EXCLUDES', 'ASC', 'DESC', 'NULLS', 'FIRST', 'LAST', 'NULL', 'TRUE', 'FALSE', 'WITH', 'FOR',
                  'UPDATE', 'USING', 'SCOPE', 'TYPEOF', 'WHEN', 'THEN', 'ELSE', 'END', 'HAVING', 'ALL', 'ROWS'}
AGGREGATES = ('COUNT', 'COUNT_DISTINCT', 'SUM', 'MIN', 'MAX', 'AVG')
UNITS = '(?:DAYS|WEEKS|MONTHS|QUARTERS|YEARS|FISCAL_QUARTERS|FISCAL_YEARS)'
DATE_WORD = re.compile(r'TODAY|YESTERDAY|TOMORROW|(?:LAST|THIS|NEXT)_(?:WEEK|MONTH|QUARTER|YEAR|FISCAL_QUARTER|FISCAL_YEAR)'
                       r'|(?:LAST|NEXT)_90_DAYS', re.I)
DATE_N = re.compile(r'(?:LAST|NEXT)_N_' + UNITS + '|N_' + UNITS + '_AGO', re.I)


class Refused(Exception):
    """A check, a gate or a publication that must not proceed; `error` keeps a CLI failure's name and message."""

    def __init__(self, reason, error=None):
        super().__init__(reason)
        self.error = error


class Soql:
    """SELECT … FROM one object [WHERE …] [GROUP BY …] [ORDER BY …] [LIMIT n] [OFFSET n], nothing else."""

    def __init__(self, query):
        self.items, self.at, self.count_only = tokens(query), 0, False

    def refuse(self):
        raise Refused('query outside the read-only grammar')

    def peek(self, ahead=0):
        index = self.at + ahead
        return self.items[index] if index < len(self.items) else (None, None)

    def keyword(self, *words):
        kind, value = self.peek()
        if kind == 'word' and value.upper() in words:
            self.at += 1
            return True
        return False

    def expect(self, *words):
        if not self.keyword(*words):
            self.refuse()

    def punct(self, symbol):
        if self.peek() == ('punct', symbol):
            self.at += 1
            return True
        return False

    def need(self, symbol):
        if not self.punct(symbol):
            self.refuse()

    def take(self, kinds, test=lambda value: True):
        kind, value = self.peek()
        if kind not in kinds or not test(value):
            self.refuse()
        self.at += 1

    def field(self):
        self.take(('word',), lambda value: value.upper() not in RESERVED_WORDS)

    def parse(self):
        self.expect('SELECT')
        self.select_list()
        self.expect('FROM')
        # Order and Group are standard objects, so only they may share a clause word.
        self.take(('word',), lambda value: '.' not in value and value.upper() not in RESERVED_WORDS - {'ORDER', 'GROUP'})
        if self.keyword('WHERE'):
            self.condition()
        if self.keyword('GROUP'):
            self.expect('BY')
            self.field()
            while self.punct(','):
                self.field()
        if self.keyword('ORDER'):
            self.expect('BY')
            self.order_list()
        for clause in ('LIMIT', 'OFFSET'):
            if self.keyword(clause):
                self.take(('number',), str.isdigit)
        if self.at != len(self.items):
            self.refuse()
        return self

    def select_list(self):
        if self.peek()[0] == 'word' and self.peek()[1].upper() == 'COUNT' and self.peek(1) == ('punct', '(') \
                and self.peek(2) == ('punct', ')'):
            self.at += 3
            self.count_only = True
            return
        while True:
            if self.aggregate():
                kind, value = self.peek()
                if kind == 'word' and '.' not in value and value.upper() not in RESERVED_WORDS:
                    self.at += 1  # the aggregate's alias
            else:
                self.field()
            if not self.punct(','):
                return

    def aggregate(self):
        kind, value = self.peek()
        if kind == 'word' and value.upper() in AGGREGATES and self.peek(1) == ('punct', '('):
            self.at += 2
            self.field()
            self.need(')')
            return True
        return False

    def condition(self):
        self.conjunction()
        while self.keyword('OR'):
            self.conjunction()

    def conjunction(self):
        self.negation()
        while self.keyword('AND'):
            self.negation()

    def negation(self):
        if self.keyword('NOT'):
            self.negation()
        elif self.punct('('):
            self.condition()
            self.need(')')
        else:
            self.comparison()

    def comparison(self):
        self.field()
        if self.peek()[0] == 'op':
            self.at += 1
            self.literal()
        elif self.keyword('NOT'):
            self.expect('IN')
            self.literal_list(self.literal)
        elif self.keyword('IN'):
            self.literal_list(self.literal)
        elif self.keyword('LIKE'):
            self.take(('string',))
        elif self.keyword('INCLUDES', 'EXCLUDES'):
            self.literal_list(lambda: self.take(('string',)))
        else:
            self.refuse()

    def literal(self):
        kind, value = self.peek()
        if kind in ('string', 'number', 'date', 'datetime'):
            self.at += 1
        elif kind == 'word' and (value.upper() in ('NULL', 'TRUE', 'FALSE') or DATE_WORD.fullmatch(value)):
            self.at += 1
        elif kind == 'word' and DATE_N.fullmatch(value) and self.peek(1) == ('punct', ':') \
                and self.peek(2)[0] == 'number' and self.peek(2)[1].isdigit():
            self.at += 3
        else:
            self.refuse()

    def literal_list(self, item):
        self.need('(')
        item()
        while self.punct(','):
            item()
        self.need(')')

    def order_list(self):
        while True:
            if not self.aggregate():
                self.field()
            self.keyword('ASC', 'DESC')
            if self.keyword('NULLS'):
                self.expect('FIRST', 'LAST')
            if not self.punct(','):
                return


def tokens(query):
    """SOQL as tokens; any character outside the token set (comments, `;`, `$`, fullwidth letters) refuses it."""
    found, position = [], 0
    while position < len(query):
        match = TOKEN.match(query, position)
        if not match:
            raise Refused('query outside the read-only grammar')
        if match.lastgroup != 'space':
            found.append((match.lastgroup, match.group()))
        position = match.end()
    return found


def parse_query(query):
    """One read-only SELECT in the constrained grammar, at most 4,000 characters."""
    if not isinstance(query, str) or not query or len(query) > 4000:
        raise Refused('query outside the read-only grammar')
    return Soql(query).parse()


def validate_query(query):
    """Validation reads tokens and passes the original text through unchanged, string literals included."""
    parse_query(query)
    return query


def current_time():
    return datetime.datetime.now().astimezone()


def parse_time(value):
    """An ISO time with a timezone (Z, ±HH:MM or ±HHMM), read alike on every Python; otherwise None."""
    match = TIME.fullmatch(value) if isinstance(value, str) else None
    if not match:
        return None
    day, minutes, seconds, zone = match.groups()
    seconds = seconds or ':00'
    if '.' in seconds:
        whole, fraction = seconds.split('.')
        seconds = whole + '.' + fraction.ljust(6, '0')
    zone = '+00:00' if zone == 'Z' else zone if ':' in zone else zone[:3] + ':' + zone[3:]
    if int(zone[1:3]) > 23 or int(zone[4:6]) > 59:  # +01:99 is no offset
        return None
    try:
        return datetime.datetime.fromisoformat('%sT%s%s%s' % (day, minutes, seconds, zone))
    except ValueError:
        return None


def parse_date(value):
    try:
        return datetime.date.fromisoformat(value) if isinstance(value, str) and DATE.fullmatch(value) else None
    except ValueError:
        return None


def now(clock=None):
    """A given time, which needs a timezone; without one, the current local time."""
    if clock is None:
        return current_time()
    moment = parse_time(clock)
    if moment is None:
        raise Refused('times need ISO format with a timezone')
    return moment


def scratch_dir():
    """Scratch lives under a vetted base (the system's root-owned, sticky /tmp), whatever TMPDIR says."""
    base = os.path.realpath(SCRATCH_BASE)
    try:
        info = os.stat(base)
    except OSError as error:
        raise Refused('no vetted scratch base') from error
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or not info.st_mode & stat.S_ISVTX:
        raise Refused('no vetted scratch base: %s must resolve to a root-owned, sticky directory' % SCRATCH_BASE)
    path = os.path.realpath(tempfile.mkdtemp(prefix='scout-prep-', dir=base))
    if os.path.dirname(path) != base:
        raise Refused('scratch left its vetted base')
    return Path(path)


def redact(text, limit=2000):
    return SECRET.sub('[redacted]', BREAKS.sub(' ', text))[:limit]


def envelope_of(output):
    if not output or len(output) > LIMIT:
        return None
    try:
        return decode(output)
    except (ValueError, UnicodeError, RecursionError):
        return None


def cli_error(*envelopes):
    """The CLI error's name and message, redacted, so the error can be searched verbatim."""
    for envelope in envelopes:
        if isinstance(envelope, dict) and (isinstance(envelope.get('name'), str) or isinstance(envelope.get('message'), str)):
            return {key: redact(envelope[key]) if isinstance(envelope.get(key), str) else '' for key in ('name', 'message')}
    return None


def run_cli(args, scratch=None):
    """One constructed CLI call whose cwd is a vetted scratch directory, never the folder."""
    executable = shutil.which('sf')
    if not executable:
        raise Refused('Salesforce CLI unavailable')
    own = scratch is None
    scratch = scratch or scratch_dir()
    try:
        result = subprocess.run([executable, *args, '--json'], cwd=str(scratch), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError) as error:
        raise Refused('CLI unavailable or timed out') from error
    finally:
        if own:
            try:
                os.rmdir(scratch)  # only if the CLI left it empty
            except OSError:
                pass
    if len(result.stdout) > LIMIT:
        raise Refused('CLI response exceeds the limit')
    envelope = envelope_of(result.stdout)
    status = envelope.get('status') if isinstance(envelope, dict) else None
    if result.returncode or type(status) is not int or status != 0:
        raise Refused('CLI operation failed', cli_error(envelope, envelope_of(result.stderr)))
    return envelope.get('result'), scratch


def query_observation(result, count_only):
    """A usable result has a records list and an integer totalSize; at most 2,000 records come back."""
    records = result.get('records') if isinstance(result, dict) else None
    total = result.get('totalSize') if isinstance(result, dict) else None
    done = result.get('done', True) if isinstance(result, dict) else None
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records) or type(total) is not int or total < 0 \
            or type(done) is not bool:  # A malformed done flag never reads as complete
        raise Refused('CLI returned an unusable query result')
    complete = done and len(records) <= RECORDS and (count_only or len(records) == total)
    return {'totalSize': total, 'records': records[:RECORDS], 'complete': complete}


def run_check(kind, selector, username, org, query=None, sobject=None, metadata=None, clock=None):
    """Validate, bind, then one constructed read-only call. Nothing stored is executed."""
    if clock is not None:
        now(clock)
    if kind == 'query':
        count_only = parse_query(query).count_only
    elif kind == 'describe':
        if not re.fullmatch(IDENT, sobject or ''):
            raise Refused('invalid sObject name')
    elif kind == 'retrieve':
        if not re.fullmatch(r'[A-Za-z]+:[A-Za-z0-9_.\- ]+', metadata or ''):
            raise Refused('invalid metadata member')
    else:
        raise Refused('unsupported check kind')
    try:
        scout_target.bind(selector, {'username': username, 'org_id': org})
    except (scout_target.Unverified, scout_target.Mismatch) as error:
        raise Refused('binding check failed: ' + str(error)) from error
    if kind == 'query':
        result, _ = run_cli(['data', 'query', '--target-org', username, '--query', query])
        observed = query_observation(result, count_only)
    elif kind == 'describe':
        result, _ = run_cli(['sobject', 'describe', '--sobject', sobject, '--target-org', username])
        fields = result.get('fields') if isinstance(result, dict) else None
        if not isinstance(fields, list):
            raise Refused('CLI returned an unusable describe result')
        observed = {'fields': sorted(f['name'] for f in fields if isinstance(f, dict) and isinstance(f.get('name'), str))}
    else:
        scratch = scratch_dir()
        target = scratch / 'metadata'
        target.mkdir()
        run_cli(['project', 'retrieve', 'start', '--metadata', metadata, '--target-metadata-dir', str(target),
                 '--unzip', '--target-org', username], scratch)
        files = sorted(str(p.relative_to(target)) for p in target.rglob('*') if p.is_file())
        observed = {'directory': str(target), 'files': files[:RECORDS], 'complete': len(files) <= RECORDS}
    return {'kind': kind, 'observed': observed, 'at': now(clock).isoformat(timespec='seconds')}


def observed_at(clock=None):
    """The time a check was attempted, even when the helper refused it."""
    try:
        return now(clock).isoformat(timespec='seconds')
    except Refused:
        return current_time().isoformat(timespec='seconds')


def read_exact(path):
    """Read text without newline translation, so CRLF and every other byte survive."""
    with open(path, encoding='utf-8', newline='') as stream:
        return stream.read()


def digest(content):
    return hashlib.sha256(content).hexdigest()


def stated(value):
    return isinstance(value, str) and bool(value.strip())


def strings(value):
    """Every string in a JSON value, keys included, walked without recursion."""
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            stack.extend(item)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)


def check_obligation(obligation):
    """A task-qualified key, and every field the verdict and renderer read has its type."""
    if not isinstance(obligation, dict) or not isinstance(obligation.get('key'), str) or not KEY.fullmatch(obligation['key']):
        raise Refused('every obligation needs a key of the form <task file>.md#<local id>')
    beat = obligation.get('beat')
    if not isinstance(obligation.get('kind'), str) or (beat is not None and not (
            isinstance(beat, str) and (BEAT.fullmatch(beat) or KEY.fullmatch(beat)))):
        raise Refused('%s needs a kind, and a beat that is null, a beat ID or a beat key' % obligation['key'])
    if any(name in obligation and not isinstance(obligation[name], bool) for name in ('required', 'proof_moment')) \
            or not isinstance(obligation.get('dropped'), (bool, type(None))) \
            or any(not isinstance(obligation.get(name), (str, type(None))) for name in TEXT_FIELDS):
        raise Refused('%s has a field of the wrong type' % obligation['key'])
    if obligation.get('valid_until') is not None and parse_date(obligation['valid_until']) is None:
        raise Refused('%s needs valid_until as YYYY-MM-DD or null' % obligation['key'])
    result = obligation.get('result')
    if result is not None and (not isinstance(result, dict) or not isinstance(result.get('status'), (str, type(None)))
                               or not isinstance(result.get('at'), (str, type(None)))):
        raise Refused('%s needs a result of the form {"status":…,"observed":…,"at":…} or null' % obligation['key'])
    if isinstance(result, dict) and result.get('status') is not None and parse_time(result.get('at')) is None:
        raise Refused('%s needs its result\'s at: an ISO time with a timezone, the helper\'s or date\'s' % obligation['key'])


def check_beat(entry, keys):
    """A beat carries the demo path's fields with their types, and every step's ref names an obligation."""
    if not isinstance(entry, dict) or not isinstance(entry.get('key'), str) or not KEY.fullmatch(entry['key']):
        raise Refused('every beat needs a key of the form <task file>.md#<beat id>')
    steps, transitions, climax = entry.get('steps', []), entry.get('transitions', []), entry.get('climax')
    if any(not isinstance(entry.get(name), (str, type(None))) for name in ('name', 'persona', 'login', 'start', 'fallback')) \
            or not isinstance(steps, list) or not isinstance(transitions, list) \
            or not all(isinstance(line, str) for line in transitions):
        raise Refused('beat %s has a field of the wrong type' % entry['key'])
    for step in steps:
        ref = step.get('ref') if isinstance(step, dict) else None
        if not isinstance(step, dict) or not isinstance(step.get('do'), str) \
                or not isinstance(step.get('expect'), (str, type(None))) or not (ref is None or isinstance(ref, str) and ref in keys):
            raise Refused('beat %s needs steps of the form {"do":…,"expect":…,"ref":<obligation key>|null}' % entry['key'])
    if climax is not None and (type(climax) is not int or not 1 <= climax <= len(steps)):
        raise Refused('beat %s needs climax as the number of one of its steps, or null' % entry['key'])


def load_results(path):
    """Every field the verdict, renderer and gate read is checked here; malformed input is refused, never raised."""
    try:
        data = decode(read_exact(path))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise Refused('results are not valid JSON') from error
    if not isinstance(data, dict) or type(data.get('schema')) is not int or data['schema'] != 1:
        raise Refused('results need schema 1')
    for key in ('folder', 'org_id', 'username', 'started_at', 'observed_at'):
        if not stated(data.get(key)):
            raise Refused('results need ' + key)
    started, observed = parse_time(data['started_at']), parse_time(data['observed_at'])
    if started is None or observed is None or not started <= observed <= current_time():
        raise Refused('started_at and observed_at need ISO times with a timezone, in order, and no later than now')
    lists = [data.get(name, []) for name in ('sources', 'beats', 'constraints')] + [data.get('obligations')]
    if not all(isinstance(value, list) for value in lists):
        raise Refused('results need sources, obligations, beats and constraints as lists')
    if not all(isinstance(s, dict) and stated(s.get('path')) and isinstance(s.get('state'), str) for s in data.get('sources', [])):
        raise Refused('every source needs a path and a state')
    keys = set()
    for obligation in data['obligations']:
        check_obligation(obligation)
        if obligation['key'] in keys:
            raise Refused('duplicate obligation key ' + obligation['key'])
        keys.add(obligation['key'])
    beats = set()
    for entry in data.get('beats', []):
        check_beat(entry, keys)
        if entry['key'] in beats:
            raise Refused('duplicate beat ' + entry['key'])
        beats.add(entry['key'])
    if not all(isinstance(line, str) for line in data.get('constraints', [])):
        raise Refused('constraints need to be strings')
    for text in strings(data):
        try:
            text.encode('utf-8')
        except UnicodeEncodeError as error:  # An unpaired surrogate is a schema error, never a crash
            raise Refused('results text is not valid Unicode') from error
    if any(RESERVED.search(unicodedata.normalize('NFKC', text)) for text in strings(data)):
        raise Refused('results text may not contain a Scout marker or an Org-verified line')
    return data


def provenance(value, read):
    """A source reference is `<path>§<section>`, naming a source this run read (its path as listed, or
    its file name) and a section in it."""
    if not stated(value) or '§' not in value:
        return False
    path, section = (part.strip() for part in value.split('§', 1))
    return bool(path and section) and (path in read or path in {Path(r).name for r in read})


def history(obligation, keyed, read=frozenset()):
    """A superseded or deliberately dropped obligation leaves the verdict only with a named source:
    the amendment's, reconciliation's or record's `<path>§<section>`, the path being one of this run's read sources."""
    successor, dropped = obligation.get('superseded_by'), obligation.get('dropped')
    if successor is None and dropped in (None, False):
        return None
    if successor is not None:
        target = keyed.get(successor) if isinstance(successor, str) else None
        if target is None or target is obligation or target.get('superseded_by') is not None \
                or target.get('dropped') not in (None, False) or dropped not in (None, False) \
                or not provenance(obligation.get('supersession_source'), read):
            return 'blocking', 'superseded_by must name another live obligation, with supersession_source as a read source\'s <path>§<section>'
        return 'history', 'superseded by %s (%s)' % (successor, obligation['supersession_source'])
    if dropped is not True or obligation.get('required', True) is not False or not provenance(obligation.get('drop_source'), read):
        return 'blocking', 'only an optional obligation can be dropped, with drop_source as a read source\'s <path>§<section>'
    return 'history', 'dropped (%s)' % obligation['drop_source']


def state_of(obligation, keyed, started, moment, demo, read=frozenset()):
    """One state per obligation, and anything unrecognized fails closed.
    Every result needs its observation time inside this run, whatever its status."""
    retired = history(obligation, keyed, read)
    if retired:
        return retired
    result = obligation.get('result')
    if not isinstance(result, dict):
        return 'blocking', 'no result'
    status, kind = result.get('status'), obligation.get('kind')
    if kind not in KINDS or status not in STATES:
        return 'blocking', 'unrecognized kind or state'
    at = parse_time(result.get('at'))
    timed = at is not None and started is not None and started <= at <= moment
    untimed = 'observation time missing, or outside this prep run'
    if status in EXCEPTIONS and kind not in EXCEPTIONS[status]:
        return 'blocking', 'unknown: %s is no result for a %s' % (status, kind) + ('' if timed else '; ' + untimed)
    if status != 'passed' and status not in EXCEPTIONS:
        return 'blocking', status + ('' if timed else '; ' + untimed)
    until = obligation.get('valid_until')
    if until is not None and (parse_date(until) is None or parse_date(until) < demo.date()):
        return 'blocking', 'expires before the demo (%s)' % until
    if not timed:
        return 'blocking', untimed
    return ('passed', '') if status == 'passed' else ('exception', LABELS[status])


def classify(data, demo_time=None):
    """Every obligation with its state, in results order. Expiry runs through the demo, and never before now.
    Date-only validity reads in this machine's timezone, by its rules at the demo's instant, so naming a
    later demo can't revive an expired date and a daylight-saving change can't shift the day."""
    moment = current_time()
    demo = max(moment, demo_time) if isinstance(demo_time, datetime.datetime) and demo_time.tzinfo else moment
    demo = demo.astimezone()  # This machine's zone rules at the demo's instant, not today's offset
    obligations = data.get('obligations') if isinstance(data.get('obligations'), list) else []
    entries = [o for o in obligations if isinstance(o, dict)]
    keyed = {o['key']: o for o in entries if isinstance(o.get('key'), str)}
    started = parse_time(data.get('started_at'))
    sources = data.get('sources') if isinstance(data.get('sources'), list) else []
    read = frozenset(s['path'].strip() for s in sources if isinstance(s, dict) and s.get('state') == 'read' and stated(s.get('path')))
    return [(o,) + state_of(o, keyed, started, moment, demo, read) for o in entries]


def key_of(obligation):
    return clean(obligation.get('key')) or 'an unkeyed obligation'


def beats_of(data):
    beats = data.get('beats')
    return [b for b in beats if isinstance(b, dict) and isinstance(b.get('key'), str)] if isinstance(beats, list) else []


def beat_of(obligation):
    """A beat belongs to its task; a bare beat ID takes the task file from the obligation's key."""
    beat = obligation.get('beat')
    if not isinstance(beat, str) or not beat:
        return None
    return beat if '#' in beat else str(obligation.get('key', '')).split('#', 1)[0] + '#' + beat


def gaps(data, rows):
    """What blocks before any single obligation does."""
    reasons = []
    sources = data.get('sources', [])
    for source in sources if isinstance(sources, list) else [None]:
        state = source.get('state') if isinstance(source, dict) else None
        if state not in SOURCES:
            path = clean(source.get('path')) if isinstance(source, dict) else ''
            reasons.append('source %s is %s' % (path or 'unnamed', clean(state) or 'of unknown state'))
    obligations = data.get('obligations')
    if not isinstance(obligations, list) or len(rows) != len(obligations):
        reasons.append('malformed obligations')
    live = [o for o, state, _ in rows if state != 'history']
    required = [o for o in live if o.get('required', True) is not False]
    if not required:
        reasons.append('no recoverable story or proof moment')
    elif not any(o.get('proof_moment') is True and o.get('kind') == 'claim' for o in required):
        reasons.append('no proof-moment claim')  # A manual step or other kind never stands in for it
    checked, retired = {beat_of(o) for o in live}, retired_beats(rows)
    reasons += ['%s has no checks' % clean(b['key']) for b in beats_of(data) if b['key'] not in checked | retired]
    return reasons


def retired_beats(rows):
    """A beat whose every obligation is history (superseded or dropped) is retired, not unchecked."""
    live = {beat_of(o) for o, state, _ in rows if state != 'history'}
    return {beat_of(o) for o, state, _ in rows if state == 'history'} - live - {None}


def verdict_from(data, rows):
    """The ordered, total table: not ready, then ready with exceptions, then ready."""
    reasons, exceptions, passed, total = gaps(data, rows), [], 0, 0
    for obligation, state, why in rows:
        if state == 'history':
            continue
        total += 1
        if state == 'passed':
            passed += 1
        elif state == 'exception':
            exceptions.append('%s: %s' % (key_of(obligation), why))
        else:
            reasons.append('%s: %s' % (key_of(obligation), why))
    result = 'not ready' if reasons else 'ready with exceptions' if exceptions else 'ready'
    return {'verdict': result, 'passed': passed, 'total': total, 'blocking': reasons, 'exceptions': exceptions}


def verdict(data, demo_time=None):
    return verdict_from(data, classify(data, demo_time))


def clean(value):
    """Rendered text stays on one line, so it can never forge a marker, a fence or a header line."""
    if value is None:
        return ''
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return BREAKS.sub(' ', text).strip()


def label(obligation):
    text = clean(obligation.get('text'))
    return '%s (%s)' % (text, key_of(obligation)) if text else key_of(obligation)


def status_of(obligation):
    result = obligation.get('result')
    return result.get('status') if isinstance(result, dict) else None


def at_of(obligation):
    result = obligation.get('result')
    return (clean(result.get('at')) if isinstance(result, dict) else '') or 'not observed'


def now_of(obligation):
    """A drift entry's now, as the results state it, or else what the check observed."""
    if obligation.get('now') is not None:
        return clean(obligation['now'])
    result = obligation.get('result')
    observed = clean(result.get('observed')) if isinstance(result, dict) else ''
    return (observed[:199] + '…' if len(observed) > 200 else observed) or 'not observed'


def header(data, outcome):
    return 'Org-verified: %s against %s (%s) — %s — %d of %d checks passed' % (
        clean(data.get('observed_at')), clean(data.get('org_id')), clean(data.get('username')),
        outcome['verdict'], outcome['passed'], outcome['total'])


def block(lines, heading=1):
    return '\n'.join(lines + (['None.'] if len(lines) == heading else [])) + '\n'


def beat_label(key, entry):
    name = clean(entry.get('name'))
    return clean(key) + (' · ' + name if name else '')


def beat_status(rows):
    states = [state for _, state, _ in rows]
    if not states:
        return 'not ready (no checks)'
    return 'not ready' if 'blocking' in states else 'ready with exceptions' if 'exception' in states else 'ready'


def step_mark(ref, states):
    if ref is None:
        return ''
    state = states.get(ref) if isinstance(ref, str) else None
    return {'passed': ' ✓', 'exception': ' (check by eye)', 'blocking': ' ✗'}.get(state, ' (unverified)')


def drift_section(data, outcome, live):
    """demo-path.md section 1: each failed check, what it was, what it is now, and the fix."""
    lines = [header(data, outcome), '', '## Drift since the build']
    for obligation, state, _ in live:
        if state == 'blocking' and status_of(obligation) == 'failed':  # Every check shows when it was observed
            lines.append('- ✗ %s — was: %s; now: %s (%s); fix: %s' % (label(obligation), clean(obligation.get('was')) or 'not recorded',
                                                                      now_of(obligation), at_of(obligation),
                                                                      clean(obligation.get('fix')) or 'none offered yet'))
    return block(lines, 3)


def checklist_section(data, rows, live):
    """demo-path.md section 2: every blocking gap, with its fix where the results name one."""
    lines = ['## Pre-demo checklist'] + ['- ' + reason for reason in gaps(data, rows)]
    for obligation, state, why in live:
        if state == 'blocking':
            fix = clean(obligation.get('fix'))
            lines.append('- %s — %s%s' % (label(obligation), clean(why), '; fix: ' + fix if fix else ''))
    return block(lines)


def beat_lines(entry, rows, states):
    """demo-path.md section 3: who and where, Do and Expect rows with ✓ on verified values, ★ on the climax, transitions, then
    the verified claim lines to say out loud and the beat's other checks."""
    lines, who = [], [entry.get(name) for name in ('persona', 'login', 'start')]
    if any(stated(value) for value in who):
        lines.append('- Persona: %s · Login: %s · Start: %s' % tuple(clean(value) or 'not recorded' for value in who))
    steps, climax = entry.get('steps'), entry.get('climax')
    for number, step in enumerate(steps if isinstance(steps, list) else [], 1):
        if isinstance(step, dict):
            star = '★ ' if type(climax) is int and climax == number else ''
            expect = clean(step.get('expect'))
            lines.append('- %sDo: %s%s%s' % (star, clean(step.get('do')), ' → Expect: ' + expect if expect else '',
                                             step_mark(step.get('ref'), states)))
    transitions = entry.get('transitions')
    lines += ['- Transition: ' + clean(line) for line in (transitions if isinstance(transitions, list) else [])]
    for obligation, state, why in rows:
        proof = ' (proof moment)' if obligation.get('proof_moment') is True else ''
        if state == 'passed' and obligation.get('kind') == 'claim':
            lines.append('- Say: %s%s ✓ (%s)' % (clean(obligation.get('text')) or key_of(obligation), proof, at_of(obligation)))
        elif state == 'passed':
            lines.append('- Check: ✓ %s%s (%s)' % (label(obligation), proof, at_of(obligation)))
        elif state == 'exception':
            lines.append('- Check: %s — %s%s (%s)' % (why, label(obligation), proof, at_of(obligation)))
        else:
            lines.append('- Check: ✗ %s%s — %s (%s)' % (label(obligation), proof, clean(why), at_of(obligation)))
    return lines


def path_section(data, live, rows=()):
    """demo-path.md section 3: beats in story order (first appearance), per task; beatless obligations under General."""
    entries = {b['key']: b for b in beats_of(data)}
    states = {o['key']: state for o, state, _ in live if isinstance(o.get('key'), str)}
    retired = retired_beats(rows)
    order = [b['key'] for b in beats_of(data) if b['key'] not in retired]  # A retired beat leaves the path
    order += [k for k in dict.fromkeys(beat_of(o) for o, _, _ in live) if k is not None and k not in order]
    if any(beat_of(o) is None for o, _, _ in live):
        order.append(None)
    lines = ['## The path']
    for key in order:
        rows = [row for row in live if beat_of(row[0]) == key]
        lines.append('### %s — %s' % (beat_label(key, entries.get(key, {})) if key else 'General', beat_status(rows)))
        lines += beat_lines(entries.get(key, {}), rows, states)
    return block(lines)


def seams_section(data, live, rows=()):
    """demo-path.md section 4: check-by-eye, visual-QA and persona-access items, each live beat's fallback, and org constraints."""
    lines, retired = ['## Known seams'], retired_beats(rows)
    lines += ['- %s: %s (%s)' % (why[0].upper() + why[1:], label(o), at_of(o)) for o, state, why in live if state == 'exception']
    lines += ['- Fallback for %s: %s' % (beat_label(b['key'], b), clean(b['fallback'])) for b in beats_of(data)
              if stated(b.get('fallback')) and b['key'] not in retired]
    constraints = data.get('constraints')
    lines += ['- Org constraint: ' + clean(line) for line in (constraints if isinstance(constraints, list) else [])]
    sources = data.get('sources')
    lines += ['- Excluded as unrelated: ' + clean(s.get('path')) for s in (sources if isinstance(sources, list) else [])
              if isinstance(s, dict) and s.get('state') == 'unrelated']  # Excluded and listed
    return block(lines)


def runs_section(data, outcome, previous):
    """demo-path.md section 5: earlier run lines are kept and this run's line is appended."""
    current = '- %s — %s — %d of %d checks passed' % (clean(data.get('observed_at')), outcome['verdict'], outcome['passed'],
                                                      outcome['total'])
    return '\n'.join(['## Prep runs'] + list(previous) + [current]) + '\n'


def run_lines(body):
    return [line for line in body.split('\n')[1:] if line.startswith('- ')]


def region_bodies(data, demo_time, previous):
    """The five sections come from the results alone, so the gate can render them again."""
    rows = classify(data, demo_time)
    outcome = verdict_from(data, rows)
    live = [row for row in rows if row[1] != 'history']
    return {'drift': drift_section(data, outcome, live), 'checklist': checklist_section(data, rows, live),
            'path': path_section(data, live, rows), 'seams': seams_section(data, live, rows),
            'runs': runs_section(data, outcome, previous)}, outcome


def region(name, body):
    body = body if body.endswith('\n') else body + '\n'
    return '<!-- scout:begin %s sha256=%s -->\n%s<!-- scout:end %s -->\n' % (name, digest(body.encode()), body, name)


def lines_of(text):
    """Lines end at LF (CRLF included); no other Unicode separator splits a line."""
    pieces = text.split('\n')
    return [piece + '\n' for piece in pieces[:-1]] + ([pieces[-1]] if pieces[-1] else [])


def parse_regions(text):
    """Scout's regions in file order; refuses malformed, nested or duplicated markers."""
    found, current, start, content_start, recorded, offset = {}, None, None, None, None, 0
    for line in lines_of(text):
        bare = line.rstrip('\r\n')
        begin, end = BEGIN.match(bare), END.match(bare)
        if 'scout:begin' in bare and not begin or 'scout:end' in bare and not end:
            raise Refused('malformed Scout marker')
        if begin:
            if current is not None or begin[1] in found:
                raise Refused('nested or duplicate Scout region')
            current, start, recorded, content_start = begin[1], offset, begin[2], offset + len(line)
        elif end:
            if current != end[1]:
                raise Refused('unmatched Scout region end')
            found[current] = dict(start=start, end=offset + len(line), body=text[content_start:offset], sha=recorded)
            current = None
        offset += len(line)
    if current is not None:
        raise Refused('unclosed Scout region')
    return found


def fenced(lines):
    """Indexes of lines inside a Markdown code fence; an unclosed fence runs to the end of the file."""
    inside, fence = [], None
    for number, line in enumerate(lines):
        bare = line.rstrip('\r\n')
        match = FENCE.match(bare)
        if fence is None:
            if match:
                fence = match.group(1)
                inside.append(number)
        else:
            inside.append(number)
            if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence) \
                    and not bare.strip().strip(fence[0]):
                fence = None
    return inside


def owned_regions(text):
    """Scout owns a file only with its marker on line 1 and all five regions, once each, in order, outside fences."""
    lines = lines_of(text)
    if not lines or lines[0].rstrip('\r\n') != MARKER or any(line.rstrip('\r\n') == MARKER for line in lines[1:]):
        raise Refused('hand-made demo-path.md (no single Scout marker on line 1): leaving it untouched; offer a new file name')
    regions = parse_regions(text)
    if list(regions) != list(REGIONS):
        raise Refused("demo-path.md lacks Scout's five regions in order: leaving it untouched; offer a new file name")
    inside = fenced(lines)
    if any(BEGIN.match(lines[number].rstrip('\r\n')) or END.match(lines[number].rstrip('\r\n')) for number in inside):
        raise Refused('Scout markers inside a code fence: leaving demo-path.md untouched; offer a new file name')
    sets = [n for n, line in enumerate(lines) if 'scout:set' in line]
    match = SET.match(lines[sets[0]].rstrip('\r\n')) if len(sets) == 1 else None
    if not match or sets[0] in inside or any(r['start'] <= sum(map(len, lines[:sets[0]])) < r['end'] for r in regions.values()) \
            or match[1] != set_digest(regions[name]['sha'] for name in REGIONS):
        raise Refused('demo-path.md is hand-made or hand-assembled (its regions are not one Scout render): leaving it '
                      'untouched; offer a new file name')
    return regions


def set_digest(shas):
    """One digest over the five region hashes, in order, binding them to a single render."""
    return digest(''.join(shas).encode())


def set_line(bodies):
    return '<!-- scout:set sha256=%s -->' % set_digest(digest(bodies[name].encode()) for name in REGIONS)


def compose(existing, data, demo_time):
    """Regenerate Scout's five regions in place, keeping every other byte; a new file gets the skeleton."""
    if existing is None:
        bodies, outcome = region_bodies(data, demo_time, [])
        return MARKER + '\n' + set_line(bodies) + '\n# Demo path\n\n' + '\n'.join(region(name, bodies[name]) for name in REGIONS), outcome
    regions = owned_regions(existing)
    edited = [name for name in REGIONS if digest(regions[name]['body'].encode()) != regions[name]['sha']]
    if edited:
        raise Refused('the SE edited Scout region "%s"; offer a new file instead' % edited[0])
    bodies, outcome = region_bodies(data, demo_time, run_lines(regions['runs']['body']))
    pieces, cursor = [], 0
    for name in REGIONS:
        pieces += [existing[cursor:regions[name]['start']], region(name, bodies[name])]
        cursor = regions[name]['end']
    text = ''.join(pieces) + existing[cursor:]
    return re.sub(r'(?m)^<!-- scout:set sha256=[0-9a-f]{64} -->(?=\r?$)', set_line(bodies), text, count=1), outcome


def same_folder(data, folder):
    """The results were collected for this folder: their `folder` is its name, its path relative to the
    workspace (`orgs/<folder>`), or its absolute path."""
    named = Path(data['folder'])
    if not re.search(r'[/\\]', data['folder']):  # Decide on the spelling, before Path drops a leading ./
        same = named.name == folder.name
    else:  # A path, relative to the workspace (orgs/<folder>), or absolute
        same = (named if named.is_absolute() else folder.parent.parent / named).resolve() == folder
    if not same:
        raise Refused('the results were collected for folder %s, not %s' % (clean(data['folder']), folder))


def checked_folder(folder):
    """Prep never creates a folder; the folder must already be a real directory, not a symlink."""
    path = Path(folder)
    if path.is_symlink() or not path.is_dir():
        raise Refused('no such customer folder; prep never creates one')
    return path.resolve()


def read_nofollow(path):
    """Read a regular file without following a symlink or blocking on a FIFO swapped in."""
    with open(os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise Refused('demo-path.md is not a regular file: leaving it untouched')
        return stream.read()


def read_destination(path):
    """The destination is a regular file or absent."""
    try:
        info = os.lstat(str(path))
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        raise Refused('demo-path.md is not a regular file: leaving it untouched')
    return read_nofollow(path)


def text_of(content):
    try:
        return None if content is None else content.decode('utf-8')
    except UnicodeError as error:
        raise Refused('demo-path.md is not UTF-8 text: leaving it untouched') from error


def render(folder, data, demo_time):
    """The candidate text, plus the sha256 (or 'absent') of the destination it was rendered from."""
    destination = checked_folder(folder) / NAME
    same_folder(data, destination.parent)
    current = read_destination(destination)
    text, outcome = compose(text_of(current), data, demo_time)
    return text, dict(outcome, base='absent' if current is None else digest(current), destination=str(destination))


def meta_path(candidate):
    return Path(str(candidate) + '.meta.json')


def create(path, text):
    """Exclusive create, never through a symlink."""
    try:
        descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError as error:
        raise Refused('--out must name a new file; %s exists' % path) from error
    with open(descriptor, 'w', encoding='utf-8', newline='') as stream:
        stream.write(text)


def discard(path):
    try:
        os.unlink(str(path))
    except OSError:
        pass


def write_candidate(text, outcome):
    """The candidate and its metadata are new files in a new scratch folder of the helper's own,
    under the vetted base, so no caller chooses where they land."""
    out = scratch_dir() / 'demo-path.candidate.md'
    create(meta_path(out), json.dumps({'schema': 1, 'destination': outcome['destination'], 'base': outcome['base']}))
    try:
        create(out, text)
    except BaseException:
        discard(meta_path(out))
        raise
    return out


def candidate_base(candidate, destination):
    """The destination's sha256, or 'absent', exactly as render recorded it beside the candidate."""
    try:
        meta = decode(read_exact(meta_path(candidate)))
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        raise Refused('the candidate has no render metadata; render it again') from error
    base = meta.get('base') if isinstance(meta, dict) else None
    if not isinstance(meta, dict) or meta.get('schema') != 1 or meta.get('destination') != str(destination) \
            or not isinstance(base, str) or not (base == 'absent' or re.fullmatch(r'[0-9a-f]{64}', base)):
        raise Refused('the candidate was rendered for another destination; render it again')
    return base


def gate(candidate, data, org, username, demo_time):
    """The candidate must be exactly what these results render, for the bound identity."""
    problems = []
    if data.get('org_id') != org or data.get('username') != username:
        problems.append('results name another org or user than the binding')
    try:
        regions = owned_regions(candidate)
    except Refused as error:
        regions = None
        problems.append(str(error))
    if regions:
        problems += ['region %s changed after rendering' % name for name in REGIONS
                     if digest(regions[name]['body'].encode()) != regions[name]['sha']]
        bodies, outcome = region_bodies(data, demo_time, run_lines(regions['runs']['body'])[:-1])
        problems += ['region %s does not match the results' % name for name in REGIONS if regions[name]['body'] != bodies[name]]
    else:
        outcome = verdict(data, demo_time)
    stamps = [line.rstrip('\r\n') for line in lines_of(candidate) if HEADER.search(unicodedata.normalize('NFKC', line))]
    if stamps != [header(data, outcome)]:
        problems.append('the Org-verified header must appear exactly once and match the results')
    problems += [key_of(o) + ' has no result' for o, state, _ in classify(data, demo_time)
                 if state != 'history' and not (isinstance(o.get('result'), dict) and o['result'].get('status'))]
    return problems


DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def open_directory(name, parent=None, create=False):
    """A directory opened without following a symlink, created first if asked. Every later step goes
    through the descriptor, so swapping a path component after this check can't redirect a move."""
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent)
        except FileExistsError:
            pass
    try:
        return os.open(name, DIRECTORY, dir_fd=parent)
    except OSError as error:
        raise Refused('%s is not a plain directory: nothing was replaced' % name) from error


def read_at(directory, name):
    """A regular file's bytes, relative to a directory descriptor and never through a symlink; None when absent."""
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        return None
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise Refused('%s is not a regular file: leaving it untouched' % name) from error
        raise
    with open(descriptor, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise Refused('%s is not a regular file: leaving it untouched' % name)
        return stream.read()


def exists_at(directory, name):
    try:
        os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def discard_at(directory, name):
    try:
        os.unlink(name, dir_fd=directory)
    except OSError:
        pass


def same_directory(parent, name, descriptor):
    """Is `name` in `parent` still the very directory `descriptor` holds, not swapped, moved or replaced?"""
    try:
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except OSError:
        return False
    held = os.fstat(descriptor)
    return stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == (held.st_dev, held.st_ino)


def stage(home, candidate):
    """The staged copy is a new file in the destination's own folder, by descriptor, so linking it in is atomic."""
    for _ in range(100):
        name = '%s.tmp-%s' % (NAME, secrets.token_hex(6))
        try:
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=home)
        except FileExistsError:
            continue
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(candidate.encode('utf-8'))
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            discard_at(home, name)  # A failed stage (a full disk, say) leaves nothing behind
            raise
        return name
    raise Refused('could not stage the candidate: nothing was replaced')


def restore(prep, backup, home, shown, destination):
    """Put the moved file back without clobbering a newer save; if one exists, keep both and name them."""
    try:
        os.link(backup, NAME, src_dir_fd=prep, dst_dir_fd=home, follow_symlinks=False)
    except OSError as error:
        if exists_at(home, NAME):
            raise Refused('kept both files: the newest demo-path.md at %s, and the one moved aside at %s'
                          % (destination, shown)) from error
        raise Refused('could not put demo-path.md back; its bytes are at %s' % shown) from error
    discard_at(prep, backup)


def publish(folder, candidate_path, data, org, username, demo_time):
    """Gate again, then replace without ever losing a concurrent save.

    After the gate, every step runs through descriptors for the folder and its `.scout-work/prep`, and the move
    aside is checked to have landed in this folder's own backup directory. Any failure after the move puts the
    file back, or names where its bytes are.
    """
    destination = checked_folder(folder) / NAME
    same_folder(data, destination.parent)
    candidate = read_exact(candidate_path)
    base = candidate_base(candidate_path, destination)
    problems = gate(candidate, data, org, username, demo_time)
    if problems:
        raise Refused('the candidate fails the gate: ' + '; '.join(problems))
    home = open_directory(str(destination.parent))
    held = [home]
    try:
        current = read_at(home, NAME)
        if (current is None) != (base == 'absent') or (current is not None and digest(current) != base):
            raise Refused('demo-path.md changed after render; nothing was replaced, so render again')
        if compose(text_of(current), data, demo_time)[0] != candidate:
            raise Refused('the candidate is not a fresh render of demo-path.md and these results')
        work = prep = None
        if current is not None:
            work = open_directory('.scout-work', home, create=True)
            held.append(work)
            prep = open_directory('prep', work, create=True)
            held.append(prep)
        staged = stage(home, candidate)
        probe = staged + '.link'
        try:
            os.link(staged, probe, src_dir_fd=home, dst_dir_fd=home, follow_symlinks=False)  # Without hard links nothing moves
            if current is None:
                try:
                    os.link(staged, NAME, src_dir_fd=home, dst_dir_fd=home, follow_symlinks=False)
                except FileExistsError as error:
                    raise Refused('a demo-path.md appeared during prep; kept it, and the candidate at %s' % candidate_path) from error
                return {'published': str(destination), 'backup': None}
            backup = 'demo-path.%s.md' % datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            shown = destination.parent / '.scout-work' / 'prep' / backup
            if exists_at(prep, backup):
                raise Refused('backup name taken; nothing was replaced, so publish again')
            try:
                os.rename(NAME, backup, src_dir_fd=home, dst_dir_fd=prep)  # Whatever was saved last moves, whole
            except OSError as error:
                raise Refused('could not move demo-path.md aside (%s); nothing was replaced' % type(error).__name__) from error
            try:
                if not (same_directory(home, '.scout-work', work) and same_directory(work, 'prep', prep)):
                    raise Refused('.scout-work/prep changed during publication')
                if digest(read_at(prep, backup) or b'') != base:
                    raise Refused('demo-path.md was saved during publication')
                os.link(staged, NAME, src_dir_fd=home, dst_dir_fd=home, follow_symlinks=False)  # No clobber
            except FileExistsError as error:
                raise Refused('a new demo-path.md was saved during publication; kept it at %s, and the previous one at %s'
                              % (destination, shown)) from error
            except BaseException as error:  # Put it back, or name where its bytes are
                restore(prep, backup, home, shown, destination)
                reason = str(error) if isinstance(error, Refused) else 'publication failed (%s)' % type(error).__name__
                raise Refused('%s; demo-path.md is back at %s and nothing was replaced' % (reason, destination)) from error
            return {'published': str(destination), 'backup': str(shown)}
        finally:
            discard_at(home, probe)
            discard_at(home, staged)
    finally:
        for descriptor in reversed(held):
            os.close(descriptor)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('scratch')
    run = commands.add_parser('run')
    run.add_argument('--kind', required=True, choices=('query', 'describe', 'retrieve'))
    for flag in ('--selector', '--username', '--org-id'):
        run.add_argument(flag, required=True)
    run.add_argument('--query')
    run.add_argument('--sobject')
    run.add_argument('--metadata')
    run.add_argument('--clock')
    for name in ('verdict', 'render', 'check', 'publish'):
        sub = commands.add_parser(name)
        sub.add_argument('--results', required=True)
        sub.add_argument('--demo-time')
        if name in ('render', 'publish'):
            sub.add_argument('--folder', required=True)
        if name in ('check', 'publish'):
            sub.add_argument('--candidate', required=True)
            sub.add_argument('--org-id', required=True)
            sub.add_argument('--username', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'scratch':
            print(json.dumps({'scratch': str(scratch_dir())}))
            return 0
        if args.command == 'run':
            print(json.dumps(run_check(args.kind, args.selector, args.username, args.org_id, args.query,
                                       args.sobject, args.metadata, args.clock)))
            return 0
        data = load_results(args.results)
        demo_time = now(args.demo_time)
        if args.command == 'verdict':
            print(json.dumps(verdict(data, demo_time)))
            return 0
        if args.command == 'render':
            text, outcome = render(args.folder, data, demo_time)
            candidate = write_candidate(text, outcome)
            print(json.dumps({'candidate': str(candidate), 'verdict': outcome['verdict'], 'base': outcome['base']}))
            return 0
        if args.command == 'publish':
            print(json.dumps(publish(args.folder, args.candidate, data, args.org_id, args.username, demo_time)))
            return 0
        problems = gate(read_exact(args.candidate), data, args.org_id, args.username, demo_time)
        print('\n'.join('prep: ' + p for p in problems) or 'prep: check pass')
        return 3 if problems else 0
    except Refused as error:
        payload = dict({'refused': str(error)}, **({'error': error.error} if error.error else {}))
        if args.command == 'run':  # A check the helper refuses still has its observation time
            payload['at'] = observed_at(args.clock)
        print(json.dumps(payload))
        return 3
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        print(json.dumps({'reason': 'could not read or run (%s)' % type(error).__name__}))
        return 4


if __name__ == '__main__':
    raise SystemExit(main())
