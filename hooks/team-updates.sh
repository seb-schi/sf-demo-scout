#!/bin/bash
# Scout team mode: teammates' updates at each prompt (UserPromptSubmit), for lane and Lifecycle Center teams. With no team on this machine it exits at
# once; otherwise local reads only (a session's first prompt does one short, bounded fetch). It never blocks the
# prompt: any failure prints nothing.
TEAMS="${SCOUT_TEAMS_FILE:-$HOME/.config/sf-demo-scout/teams.json}"
[ -f "$TEAMS" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
payload="$(cat)"  # both helpers read the same prompt payload
printf '%s' "$payload" | python3 -B "${BASH_SOURCE[0]%/*}/../scripts/scout_team.py" updates --hook 2>/dev/null
printf '%s' "$payload" | python3 -B "${BASH_SOURCE[0]%/*}/../scripts/scout_lc.py" updates --hook 2>/dev/null
exit 0
