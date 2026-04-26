#!/bin/bash
# SF Demo Prep — Session Startup Script
# Lives at: .claude/hooks/session-startup.sh
# Runs automatically via SessionStart hook when Claude Code launches.
# Handles: LLMGW auth check, Salesforce org check, org folder + audit status.

OUTPUT=""

# --- 1. LLMGW Auth Check ---
SETTINGS_FILE="$HOME/.claude/settings.json"
if [ -f "$SETTINGS_FILE" ] && grep -q '"ANTHROPIC_AUTH_TOKEN"' "$SETTINGS_FILE" 2>/dev/null; then
  OUTPUT+="## ✅ LLMGW auth token present.\n\n"
else
  OUTPUT+="## ⚠️ No LLMGW auth token found in ~/.claude/settings.json\n"
  OUTPUT+="   Run the Claude Code installer first: see the 'Installing Claude Code for Solutions' canvas.\n\n"
fi

# --- 2. Slack MCP Auth State ---
# OAuth token lives in macOS Keychain (Claude Code-credentials),
# not in ~/.claude.json — the JSON file only records registration.
# `claude mcp list` actively probes the connection.
# Silent when connected; one-line hint when registered-but-not-connected.
# Silent when not registered at all (opt-in feature).
if command -v claude &>/dev/null; then
  SLACK_STATUS=$(claude mcp list 2>/dev/null | grep -E '^slack:' || true)
  if [ -n "$SLACK_STATUS" ]; then
    if echo "$SLACK_STATUS" | grep -q "✓ Connected"; then
      : # Connected — stay silent.
    else
      OUTPUT+="## ℹ️ Slack MCP registered but not connected.\n"
      OUTPUT+="   Run \`/mcp\` in this session, select 'slack', choose 'Authenticate'.\n\n"
    fi
  fi
fi

# --- 3. Salesforce Org Check ---
DEFAULT_ORG=$(sf config get target-org --json 2>/dev/null | grep -oE '"value"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | cut -d'"' -f4)
ORG_LIST=$(sf org list --json 2>/dev/null)
ORG_COUNT=$(echo "$ORG_LIST" | grep -cE '"alias"[[:space:]]*:' 2>/dev/null || echo "0")

if [ -z "$DEFAULT_ORG" ] || [ "$DEFAULT_ORG" = "null" ]; then
  OUTPUT+="## ⚠️ No default Salesforce org set.\n"
  OUTPUT+="$ORG_COUNT org(s) available. To connect:\n"
  OUTPUT+="  sf org login web --alias [name] --set-default\n\n"
elif ! echo "$ORG_LIST" | grep -qE "\"alias\"[[:space:]]*:[[:space:]]*\"$DEFAULT_ORG\""; then
  LOCAL_CONFIG=".sf/config.json"
  OUTPUT+="## ⚠️ Configured target-org '$DEFAULT_ORG' is not in the connected org list.\n"
  OUTPUT+="   This usually means a stale entry in $LOCAL_CONFIG (local scope overrides global).\n"
  OUTPUT+="   Fix: run /switch-org to reset, or edit $LOCAL_CONFIG manually.\n\n"
else
  ORG_DISPLAY=$(sf org display --target-org "$DEFAULT_ORG" --json 2>/dev/null)
  if [ -n "$ORG_DISPLAY" ]; then
    USERNAME=$(echo "$ORG_DISPLAY" | grep -oE '"username"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | cut -d'"' -f4)
    ORG_ID=$(echo "$ORG_DISPLAY" | grep -oE '"id"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | cut -d'"' -f4)
    INSTANCE_URL=$(echo "$ORG_DISPLAY" | grep -oE '"instanceUrl"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | cut -d'"' -f4)

    OUTPUT+="## ✅ Active Org\n"
    OUTPUT+="- **Alias:** $DEFAULT_ORG\n"
    OUTPUT+="- **Username:** $USERNAME\n"
    OUTPUT+="- **Org ID:** $ORG_ID\n"
    OUTPUT+="- **Instance:** $INSTANCE_URL\n"
    OUTPUT+="$ORG_COUNT org(s) available. Switch: /switch-org\n\n"

    # --- 4. Org Folder + Audit Check ---
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

# --- 5. CLAUDE.md Presence Check ---
if [ ! -f "CLAUDE.md" ]; then
  OUTPUT+="## ⚠️ No CLAUDE.md found. Are you in the sf-demo-prep project directory?\n\n"
fi

# --- 6. GitHub Update Check ---
# Writes .claude/.update-available when behind main so /scout-sparring
# can surface the notice in its Stage 1 gate. Deleted when current.
FLAG_FILE=".claude/.update-available"
if git rev-parse --git-dir &>/dev/null; then
  if git fetch origin main --quiet --depth=1 2>/dev/null; then
    LOCAL=$(git rev-parse HEAD 2>/dev/null)
    REMOTE=$(git rev-parse origin/main 2>/dev/null)
    if [ -n "$LOCAL" ] && [ -n "$REMOTE" ] && [ "$LOCAL" != "$REMOTE" ]; then
      COMMITS_BEHIND=$(git rev-list --count "$LOCAL..$REMOTE" 2>/dev/null || echo "?")
      # Extract the first 3 bullets under the most recent ## YYYY-MM-DD header in CHANGELOG.md
      RECENT=$(awk '
        /^## [0-9]{4}-[0-9]{2}-[0-9]{2}/ { if (seen) exit; seen=1; next }
        seen && /^- / { print; count++; if (count==3) exit }
      ' CHANGELOG.md 2>/dev/null | sed 's/^- //' | tr '\n' '|' | sed 's/|$//' | sed 's/|/ | /g')
      {
        echo "commits_behind=$COMMITS_BEHIND"
        echo "recent_changes=$RECENT"
      } > "$FLAG_FILE"
      OUTPUT+="## ⚠️ SF Demo Scout update available ($COMMITS_BEHIND commit(s) behind) — /scout-sparring will prompt you.\n\n"
    else
      rm -f "$FLAG_FILE"
    fi
  fi
fi

# --- 7. Ready ---
OUTPUT+="---\n"
OUTPUT+="**Ready.**\n"
OUTPUT+="  /scout-sparring  — Opus discovery sparring + spec generation\n"
OUTPUT+="  /scout-building  — Opus orchestrator for org deployment\n"
OUTPUT+="  /switch-org      — change active demo org\n"

echo -e "$OUTPUT"