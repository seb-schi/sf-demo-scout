#!/bin/bash
# SF Demo Prep — Session Startup Script
# Lives at: ${CLAUDE_PLUGIN_ROOT}/hooks/session-startup.sh (plugin)
# Runs automatically via SessionStart hook when Claude Code launches.
# Handles: LLMGW auth check, Salesforce org check, org folder + audit status.
#
# Workspace gate: the plugin loads globally, but the banner is only useful
# inside the Scout workspace. Stay silent everywhere else.

SCOUT_WORKSPACE="${SCOUT_WORKSPACE:-$HOME/claude-projects/sf-demo-scout}"
if [ "$PWD" != "$SCOUT_WORKSPACE" ]; then
  exit 0
fi

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
  OUTPUT+="   Fix: run /scout-switch-org to reset, or edit $LOCAL_CONFIG manually.\n\n"
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
    OUTPUT+="$ORG_COUNT org(s) available. Switch: /scout-switch-org\n\n"

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

# --- 6. Plugin Update Check ---
# Compares the installed plugin version (from CC's installed_plugins.json)
# against the catalog cache's plugin.json (refreshed by autoUpdate at
# session start). When versions differ, writes .claude/.update-available
# so /scout-sparring surfaces an inline note in its Stage 2 prompt.
# autoUpdate fetches the new content silently in the background; the SE
# still needs to run /reload-plugins (Terminal CC) or quit + relaunch
# (VS Code extension) for the new version to take effect.
#
# §6.4 below adds a one-shot post-update confirmation banner when the
# installed version finally catches up to the catalog version — proves
# autoUpdate + reload landed end-to-end. State is tracked in
# .claude/.last-seen-plugin-version (plain version string).
FLAG_FILE=".claude/.update-available"
LAST_SEEN_FILE=".claude/.last-seen-plugin-version"
INSTALLED_FILE="$HOME/.claude/plugins/installed_plugins.json"
CATALOG_FILE="$HOME/.claude/plugins/marketplaces/scout/.claude-plugin/plugin.json"
mkdir -p .claude

if [ -f "$INSTALLED_FILE" ] && [ -f "$CATALOG_FILE" ]; then
  INSTALLED_VERSION=$(python3 -c "
import json
try:
    d = json.load(open('$INSTALLED_FILE'))
    entries = d.get('plugins', {}).get('sf-demo-scout@scout', [])
    print(entries[0].get('version', '') if entries else '')
except Exception:
    pass
" 2>/dev/null)
  CATALOG_VERSION=$(python3 -c "
import json
try:
    print(json.load(open('$CATALOG_FILE')).get('version', ''))
except Exception:
    pass
" 2>/dev/null)

  if [ -n "$INSTALLED_VERSION" ] && [ -n "$CATALOG_VERSION" ]; then
    # --- 6.1. Update available branch ---
    if [ "$INSTALLED_VERSION" != "$CATALOG_VERSION" ]; then
      REQUIRES_RELOAD=$(python3 -c "
import json
try:
    d = json.load(open('$CATALOG_FILE'))
    print('true' if d.get('requires_reload', False) else 'false')
except Exception:
    print('false')
" 2>/dev/null)
      {
        echo "installed_version=$INSTALLED_VERSION"
        echo "catalog_version=$CATALOG_VERSION"
        echo "requires_reload=$REQUIRES_RELOAD"
      } > "$FLAG_FILE"
      if [ "$REQUIRES_RELOAD" = "true" ]; then
        OUTPUT+="## 🆕 SF Demo Scout update available — see #sf-demo-scout on Slack for details.\n"
        OUTPUT+="   To apply: run /scout-setup, then close + reopen this Claude tab.\n\n"
      else
        OUTPUT+="## 🆕 SF Demo Scout update available — see #sf-demo-scout on Slack for details.\n"
        OUTPUT+="   To apply: run /scout-setup.\n\n"
      fi
    # --- 6.4. Post-update confirmation branch ---
    # installed == catalog. Either steady state, fresh install, or just-upgraded.
    else
      rm -f "$FLAG_FILE"
      if [ ! -f "$LAST_SEEN_FILE" ]; then
        # First-ever run: silently establish baseline. /scout-setup already
        # confirmed install — no duplicate hook banner.
        echo "$INSTALLED_VERSION" > "$LAST_SEEN_FILE"
      else
        LAST_SEEN=$(cat "$LAST_SEEN_FILE" 2>/dev/null)
        if [ "$LAST_SEEN" != "$INSTALLED_VERSION" ]; then
          OUTPUT+="## ✅ Scout updated to $INSTALLED_VERSION — see #sf-demo-scout for what changed.\n\n"
          echo "$INSTALLED_VERSION" > "$LAST_SEEN_FILE"
        fi
      fi
    fi
  fi
fi

# --- 6.5. Plugin First-Run Nudge ---
# If the SE installed the plugin but never ran /scout-setup,
# config.json is absent and the workspace is unconfigured. Surface
# a one-line nudge so they know what to do next.
if [ ! -f "$HOME/.config/sf-demo-scout/config.json" ]; then
  OUTPUT+="## ⚠️ Scout setup not yet complete.\n"
  OUTPUT+="   Run /scout-setup to install — handles fresh installs, refreshes, and repairs.\n\n"
fi

# --- 7. Ready ---
OUTPUT+="---\n"
OUTPUT+="**Ready.**\n"
OUTPUT+="  /scout-sparring  — Opus discovery sparring + spec generation\n"
OUTPUT+="  /scout-building  — Opus orchestrator for org deployment\n"
OUTPUT+="  /scout-switch-org — change active demo org\n"
OUTPUT+="  /scout-setup     — install, refresh, or repair Scout\n"

echo -e "$OUTPUT"