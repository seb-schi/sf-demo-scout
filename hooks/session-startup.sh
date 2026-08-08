#!/bin/bash
# SF Demo Prep — Session Startup Script
# Lives at: ${CLAUDE_PLUGIN_ROOT}/hooks/session-startup.sh (plugin)
# Runs automatically via SessionStart hook when Claude Code launches.
# Handles: LLMGW auth check, Salesforce org check, org folder + audit status.
#
# Workspace gate: the plugin loads globally, but the banner is only useful
# inside the Scout workspace. Stay silent everywhere else.
#
# SessionStart runs on EVERY session, so it must stay fast. Three of the four
# subprocesses below are network-bound (measured cold: `claude mcp list` 4.8s,
# `sf org list` 4.3s, `sf org display` 0.8-2.3s). Two mechanisms keep that off
# the SE's launch path:
#   1. Same-day cache under ~/.cache/sf-demo-scout/ — the same damper pattern
#      the maintainer drift sensors use. `sf config get target-org` stays LIVE
#      (0.4s): it is cheap, and it is the one value that legitimately changes
#      between sessions.
#   2. The independent calls run in parallel, so a cold launch costs the
#      slowest one instead of their sum.
# Measured: ~10.5s before, 5.9s cold, 0.55s warm. Banner output is unchanged.
#
# Every subprocess is bounded. macOS ships no coreutils `timeout`, and an
# unreachable Salesforce previously hung startup with no upper bound at all.
# The bound must kill the whole process GROUP: `sf` and `claude` are wrappers
# that spawn children, and killing only the direct child leaves grandchildren
# holding the output pipe open — the read blocks even though the child is dead.
# Escape hatch: SCOUT_HOOK_NOCACHE=1 forces every value fresh.

SCOUT_WORKSPACE="${SCOUT_WORKSPACE:-$HOME/claude-projects/sf-demo-scout}"
if [ "$PWD" != "$SCOUT_WORKSPACE" ]; then
  exit 0
fi

OUTPUT=""

# --- 0. Bounded-call + same-day-cache helpers ---
CACHE_DIR="$HOME/.cache/sf-demo-scout"
TODAY=$(date +%Y-%m-%d)
mkdir -p "$CACHE_DIR" 2>/dev/null

# Drop entries from previous days. `find -delete` (never `rm -rf`) is the
# codified deletion idiom in this project — a compound command containing an
# `rm -rf` glob gets hard-denied by the workspace deny rules.
find "$CACHE_DIR" -maxdepth 1 -type f ! -name "*.$TODAY" -delete 2>/dev/null

# Run a command with stdout to $2, bounded by $1 seconds. perl forks, puts the
# child in its own process group, and signals the GROUP on alarm, so wrapper
# grandchildren die with it. Returns the command's exit code, or 124 on timeout.
run_bounded() {
  local secs="$1" dest="$2"; shift 2
  perl -e '
    my $secs = shift;
    my $pid = fork();
    exit 125 unless defined $pid;
    if ($pid == 0) { setpgrp(0,0); exec @ARGV or exit 127 }
    $SIG{ALRM} = sub {
      kill "TERM", -$pid; sleep 1; kill "KILL", -$pid;
      waitpid($pid, 0); exit 124;
    };
    alarm $secs;
    waitpid($pid, 0);
    alarm 0;
    exit($? >> 8);
  ' "$secs" "$@" >"$dest" 2>/dev/null
}

# Populate a same-day cache entry. Successful results only — including an
# empty-but-successful one. A timeout or error leaves no entry, so the next
# session retries instead of caching a lie. Safe to background.
#   $1 = cache key   $2 = timeout seconds   $3+ = command
cache_fill() {
  local key="$1" secs="$2"; shift 2
  local f="$CACHE_DIR/$key.$TODAY"
  if [ -z "$SCOUT_HOOK_NOCACHE" ] && [ -f "$f" ]; then return 0; fi
  local tmp="$f.partial.$$"
  if run_bounded "$secs" "$tmp" "$@"; then
    mv -f "$tmp" "$f" 2>/dev/null
  else
    find "$CACHE_DIR" -maxdepth 1 -name "$(basename "$tmp")" -delete 2>/dev/null
  fi
}
cache_read() { cat "$CACHE_DIR/$1.$TODAY" 2>/dev/null; }

# --- 1. LLMGW Auth Check ---
SETTINGS_FILE="$HOME/.claude/settings.json"
if [ -f "$SETTINGS_FILE" ] && grep -q '"ANTHROPIC_AUTH_TOKEN"' "$SETTINGS_FILE" 2>/dev/null; then
  OUTPUT+="## ✅ LLMGW auth token present.\n\n"
else
  OUTPUT+="## ⚠️ No LLMGW auth token found in ~/.claude/settings.json\n"
  OUTPUT+="   Run the Claude Code installer first: see the 'Installing Claude Code for Solutions' canvas.\n\n"
fi

# --- 2. Fan out the independent network calls ---
if command -v claude &>/dev/null; then
  cache_fill mcp-list 6 claude mcp list &
fi
cache_fill org-list 6 sf org list --json &
CONFIG_TMP="$CACHE_DIR/config-get.live.$$"
run_bounded 5 "$CONFIG_TMP" sf config get target-org --json
wait

DEFAULT_ORG=$(grep -oE '"value"[[:space:]]*:[[:space:]]*"[^"]*"' "$CONFIG_TMP" 2>/dev/null | head -1 | cut -d'"' -f4)
find "$CACHE_DIR" -maxdepth 1 -name "config-get.live.$$" -delete 2>/dev/null
ORG_LIST=$(cache_read org-list)
ORG_COUNT=$(echo "$ORG_LIST" | grep -cE '"alias"[[:space:]]*:' 2>/dev/null); ORG_COUNT=${ORG_COUNT:-0}

# --- 3. Slack MCP Auth State ---
# OAuth token lives in macOS Keychain (Claude Code-credentials),
# not in ~/.claude.json — the JSON file only records registration.
# `claude mcp list` actively probes the connection.
# Silent when connected; one-line hint when registered-but-not-connected.
# Silent when not registered at all (opt-in feature).
SLACK_STATUS=$(cache_read mcp-list | grep -E '^slack:' || true)
if [ -n "$SLACK_STATUS" ]; then
  if echo "$SLACK_STATUS" | grep -q "✓ Connected"; then
    : # Connected — stay silent.
  else
    OUTPUT+="## ℹ️ Slack MCP registered but not connected.\n"
    OUTPUT+="   Run \`/mcp\` in this session, select 'slack', choose 'Authenticate'.\n\n"
  fi
fi

# --- 4. Salesforce Org Check ---
if [ -z "$DEFAULT_ORG" ] || [ "$DEFAULT_ORG" = "null" ]; then
  OUTPUT+="## ⚠️ No default Salesforce org set.\n"
  OUTPUT+="$ORG_COUNT org(s) available. To connect:\n"
  OUTPUT+="  sf org login web --alias [name] --set-default\n\n"
else
  # A miss against the cached list may only mean the SE connected this org
  # after today's list was cached. Refetch once before warning about drift.
  if ! echo "$ORG_LIST" | grep -qE "\"alias\"[[:space:]]*:[[:space:]]*\"$DEFAULT_ORG\""; then
    SCOUT_HOOK_NOCACHE=1 cache_fill org-list 6 sf org list --json
    ORG_LIST=$(cache_read org-list)
    ORG_COUNT=$(echo "$ORG_LIST" | grep -cE '"alias"[[:space:]]*:' 2>/dev/null); ORG_COUNT=${ORG_COUNT:-0}
  fi

  if ! echo "$ORG_LIST" | grep -qE "\"alias\"[[:space:]]*:[[:space:]]*\"$DEFAULT_ORG\""; then
    LOCAL_CONFIG=".sf/config.json"
    OUTPUT+="## ⚠️ Configured target-org '$DEFAULT_ORG' is not in the connected org list.\n"
    OUTPUT+="   This usually means a stale entry in $LOCAL_CONFIG (local scope overrides global).\n"
    OUTPUT+="   Fix: run /scout-sparring or /scout-building — they connect or switch the org inline — or edit $LOCAL_CONFIG manually.\n\n"
  else
    # Keyed by alias, so switching org self-invalidates this entry. Aliases can
    # contain spaces ("AFD360 L3 Training"), so sanitize before using as a name.
    ALIAS_KEY=$(printf '%s' "$DEFAULT_ORG" | tr -C '[:alnum:]._-' '_')
    cache_fill "org-display-$ALIAS_KEY" 6 sf org display --target-org "$DEFAULT_ORG" --json
    ORG_DISPLAY=$(cache_read "org-display-$ALIAS_KEY")
    if [ -n "$ORG_DISPLAY" ]; then
      USERNAME=$(echo "$ORG_DISPLAY" | grep -oE '"username"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | cut -d'"' -f4)
      ORG_ID=$(echo "$ORG_DISPLAY" | grep -oE '"id"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | cut -d'"' -f4)
      INSTANCE_URL=$(echo "$ORG_DISPLAY" | grep -oE '"instanceUrl"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | cut -d'"' -f4)

      OUTPUT+="## ✅ Active Org\n"
      OUTPUT+="- **Alias:** $DEFAULT_ORG\n"
      OUTPUT+="- **Username:** $USERNAME\n"
      OUTPUT+="- **Org ID:** $ORG_ID\n"
      OUTPUT+="- **Instance:** $INSTANCE_URL\n"
      OUTPUT+="$ORG_COUNT org(s) available. To switch, say 'switch' when /scout-sparring or /scout-building asks.\n\n"

      # --- 5. Org Folder + Audit Check ---
      # Find customer folders for this org alias (pattern: orgs/[alias]-[customer]/)
      ORG_FOLDERS=$(ls -d orgs/${DEFAULT_ORG}-*/ 2>/dev/null)
      if [ -n "$ORG_FOLDERS" ]; then
        FOLDER_COUNT=$(echo "$ORG_FOLDERS" | wc -l | tr -d ' ')
        OUTPUT+="## ℹ️ $FOLDER_COUNT customer folder(s) for $DEFAULT_ORG:\n"
        for FOLDER in $ORG_FOLDERS; do
          CUSTOMER=$(basename "$FOLDER" | sed "s/^${DEFAULT_ORG}-//")
          LATEST_AUDIT=$(ls -t "$FOLDER"/audit-*.md 2>/dev/null | head -1)
          if [ -n "$LATEST_AUDIT" ]; then
            AUDIT_AGE=$(( ( $(date +%s) - $(stat -f%m "$LATEST_AUDIT" 2>/dev/null || stat -c%Y "$LATEST_AUDIT" 2>/dev/null) ) / 86400 ))
            AUDIT_FILE=$(basename "$LATEST_AUDIT")
            if [ "$AUDIT_AGE" -gt 7 ]; then
              OUTPUT+="  - $CUSTOMER: audit ($AUDIT_FILE) is ${AUDIT_AGE}d old — consider refreshing\n"
            else
              OUTPUT+="  - $CUSTOMER: audit $AUDIT_FILE (${AUDIT_AGE}d ago) ✅\n"
            fi
          else
            OUTPUT+="  - $CUSTOMER: no audit found — run /scout-sparring\n"
          fi
          LATEST_CHANGES=$(ls -t "$FOLDER"/changes-*.md 2>/dev/null | head -1)
          if [ -n "$LATEST_CHANGES" ]; then
            OUTPUT+="    Last change log: $(basename $LATEST_CHANGES)\n"
          fi
        done
        OUTPUT+="\n"
      else
        OUTPUT+="## ℹ️ No customer folders for $DEFAULT_ORG — run /scout-sparring to create one.\n\n"
      fi
    else
      OUTPUT+="## ⚠️ Org '$DEFAULT_ORG' auth expired. Re-authenticate:\n"
      OUTPUT+="  sf org login web --alias $DEFAULT_ORG\n\n"
    fi
  fi
fi

# --- 7. Plugin First-Run Nudge ---
# If the SE installed the plugin but never ran /scout-setup,
# config.json is absent and the workspace is unconfigured. Surface
# a one-line nudge so they know what to do next.
if [ ! -f "$HOME/.config/sf-demo-scout/config.json" ]; then
  OUTPUT+="## ⚠️ Scout setup not yet complete.\n"
  OUTPUT+="   Run /scout-setup to install — handles fresh installs, refreshes, and repairs.\n\n"
fi

# --- 8. Ready ---
OUTPUT+="---\n"
OUTPUT+="**Ready.**\n"
OUTPUT+="  /scout-sparring  — Opus discovery sparring + spec generation\n"
OUTPUT+="  /scout-building  — Opus orchestrator for org deployment\n"
OUTPUT+="  /scout-setup     — install, refresh, or repair Scout\n"

echo -e "$OUTPUT"
