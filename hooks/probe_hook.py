#!/usr/bin/env python3
"""Throwaway probe hook: prints the probe's version and root, and appends one line to the host's plugin data folder."""
import json
import os
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
version = (root / 'VERSION').read_text(encoding='utf-8').strip()
event = sys.argv[1] if len(sys.argv) > 1 else 'unknown'
line = 'scout-probe %s %s root=%s' % (version, event, root)
data = os.environ.get('PLUGIN_DATA') or os.environ.get('CLAUDE_PLUGIN_DATA')
if data:
    try:
        Path(data).mkdir(parents=True, exist_ok=True)
        with open(Path(data) / 'probe-hooks.log', 'a', encoding='utf-8') as log:
            log.write('%s %s\n' % (time.strftime('%Y-%m-%dT%H:%M:%S'), line))
    except OSError:
        pass
if event.startswith('cursor'):
    print(json.dumps({'additional_context': line}))
else:
    print(line)
