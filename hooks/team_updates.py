#!/usr/bin/env python3
"""Scout team mode: teammates' updates at each prompt (UserPromptSubmit), for lane and Lifecycle Center teams.

Claude Code runs it through run-hook.cmd. With no team on this machine it exits at once; otherwise local reads
only (a session's first prompt does one short, bounded fetch). It reads the prompt payload once and gives the
same bytes to both helpers. It never blocks the prompt: any failure prints nothing.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
HELPERS = ("scout_team.py", "scout_lc.py")


def main() -> int:
    if os.name == "nt":  # team mode on Windows comes later
        return 0
    teams = Path(os.environ.get("SCOUT_TEAMS_FILE") or "~/.config/sf-demo-scout/teams.json").expanduser()
    if not teams.is_file():
        return 0
    try:
        payload = sys.stdin.buffer.read().rstrip(b"\n")  # as the shell's $(cat) read it
    except (OSError, ValueError):
        payload = b""
    for helper in HELPERS:
        try:
            subprocess.run([sys.executable, "-B", str(SCRIPTS / helper), "updates", "--hook"], input=payload,
                           stderr=subprocess.DEVNULL, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
