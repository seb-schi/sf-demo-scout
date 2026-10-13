#!/usr/bin/env python3
"""Bound displayed startup context while retaining its leading Scout rules."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

LIMIT = 10000
FOLDERS = re.compile(r'(?m)^## ℹ️ \d+ customer folder\(s\) for [^\n]+:\n(?P<rows>(?:[^\n]+\n)+)\n')


def units(text: str) -> int:
    # Also stay below a JavaScript host's UTF-16 length for non-BMP characters.
    return len(text.encode('utf-16-le')) // 2


def folder_marker(count: int) -> str:
    return f'…and {count} more folder{"s" if count != 1 else ""} in `orgs/`\n' if count else ''


def bound_context(context: str, workspace: Path, slug: str) -> str:
    if units(context) <= LIMIT:
        return context
    match = FOLDERS.search(context)
    if match:
        entries = re.findall(r'(?m)^  - [^\n]*\n(?:    [^\n]*\n)*', match['rows'])
        if ''.join(entries) == match['rows']:
            prefix, suffix = context[:match.start('rows')], context[match.end('rows'):]
            modified = {}
            try:
                for folder in (workspace / 'orgs').iterdir():
                    if folder.is_dir() and folder.name.startswith(slug + '-'):
                        modified['  - ' + folder.name[len(slug)+1:] + ': '] = folder.stat().st_mtime_ns
            except OSError:
                pass  # Missing timestamps keep deterministic original-order ties.
            entries.sort(key=lambda entry: next((stamp for name, stamp in modified.items()
                                                 if entry.startswith(name)), 0), reverse=True)
            kept = []
            for entry in entries:
                omitted = len(entries) - len(kept) - 1
                marker = folder_marker(omitted)
                if units(prefix + ''.join(kept) + entry + marker + suffix) > LIMIT:
                    break
                kept.append(entry)
            marker = folder_marker(len(entries)-len(kept))
            context = prefix + ''.join(kept) + marker + suffix
    if units(context) > LIMIT:
        # Bounded individual evidence fields can still exceed the combined limit.
        marker = '\n…additional startup context omitted to fit the host limit; saved org files are unchanged.\n'
        context = context.encode('utf-16-le')[:2*(LIMIT-units(marker))].decode('utf-16-le', errors='ignore') + marker
    return context


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--slug', required=True)
    args = parser.parse_args()
    content = sys.stdin.buffer.read(4 * 1024 * 1024 + 1)
    if len(content) > 4 * 1024 * 1024:
        raise ValueError('startup context too large')
    sys.stdout.buffer.write(bound_context(content.decode('utf-8'), args.workspace, args.slug).encode('utf-8'))


if __name__ == '__main__':
    main()
