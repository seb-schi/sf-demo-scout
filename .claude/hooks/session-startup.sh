#!/bin/bash
# SF Demo Prep — Session Startup Script
# Lives at: .claude/hooks/session-startup.sh
# Runs automatically via SessionStart hook when Claude Code launches.
# Handles: AWS SSO refresh, Salesforce org check, org folder + audit status.

OUTPUT=""

# --- 1. AWS SSO Check & Refresh ---
if ! aws sts get-caller-identity --profile claude &>/dev/null; then
  echo "⏳ AWS SSO session expired. Refreshing..." >&2
  aws sso login --profile claude 2>&1
  if ! aws sts get-caller-identity --profile claude &>/dev/null; then
    OUTPUT+="## ⚠️ AWS SSO login failed. Run manually: aws sso login --profile claude\n\n"
  else
    OUTPUT+="## ✅ AWS SSO refreshed successfully.\n\n"
  fi
else
  OUTPUT+="## ✅ AWS SSO session active.\n\n"
fi

# --- 2. Salesforce Org Check ---
DEFAULT_ORG=$(sf config get target-org --json 2>/dev/null | grep -o '"value":"[^"]*"' | head -1 | cut -d'"' -f4)
ORG_LIST=$(sf org list --json 2>/dev/null)
ORG_COUNT=$(echo "$ORG_LIST" | grep -c '"alias"' 2>/dev/null || echo "0")

if [ -z "$DEFAULT_ORG" ] || [ "$DEFAULT_ORG" = "null" ]; then
  OUTPUT+="## ⚠️ No default Salesforce org set.\n"
  OUTPUT+="$ORG_COUNT org(s) available. To connect:\n"
  OUTPUT+="  sf org login web --alias [name] --set-default\n\n"
elif ! echo "$ORG_LIST" | grep -q "\"alias\":\"$DEFAULT_ORG\""; then
  LOCAL_CONFIG=".sf/config.json"
  OUTPUT+="## ⚠️ Configured target-org '$DEFAULT_ORG' is not in the connected org list.\n"
  OUTPUT+="   This usually means a stale entry in $LOCAL_CONFIG (local scope overrides global).\n"
  OUTPUT+="   Fix: run /switch-org to reset, or edit $LOCAL_CONFIG manually.\n\n"
else
  ORG_DISPLAY=$(sf org display --target-org "$DEFAULT_ORG" --json 2>/dev/null)
  if [ -n "$ORG_DISPLAY" ]; then
    USERNAME=$(echo "$ORG_DISPLAY" | grep -o '"username":"[^"]*"' | head -1 | cut -d'"' -f4)
    ORG_ID=$(echo "$ORG_DISPLAY" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
    INSTANCE_URL=$(echo "$ORG_DISPLAY" | grep -o '"instanceUrl":"[^"]*"' | head -1 | cut -d'"' -f4)

    OUTPUT+="## ✅ Active Org\n"
    OUTPUT+="- **Alias:** $DEFAULT_ORG\n"
    OUTPUT+="- **Username:** $USERNAME\n"
    OUTPUT+="- **Org ID:** $ORG_ID\n"
    OUTPUT+="- **Instance:** $INSTANCE_URL\n"
    OUTPUT+="$ORG_COUNT org(s) available. Switch: /switch-org\n\n"

    # --- 3. Org Folder + Audit Check ---
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

# --- 4. CLAUDE.md Presence Check ---
if [ ! -f "CLAUDE.md" ]; then
  OUTPUT+="## ⚠️ No CLAUDE.md found. Are you in the sf-demo-prep project directory?\n\n"
fi

# --- 5. GitHub Update Check ---
if git rev-parse --git-dir &>/dev/null; then
  if git fetch origin main --quiet --depth=1 2>/dev/null; then
    LOCAL=$(git rev-parse HEAD 2>/dev/null)
    REMOTE=$(git rev-parse origin/main 2>/dev/null)
    if [ -n "$LOCAL" ] && [ -n "$REMOTE" ] && [ "$LOCAL" != "$REMOTE" ]; then
      osascript -e 'display notification "SF Demo Scout has updates available. Run: git pull" with title "SF Demo Scout — Update Available"' 2>/dev/null
      OUTPUT+="## ⚠️ SF Demo Scout has updates available.\n"
      OUTPUT+="   Run: git pull — then restart VS Code to pick up the changes.\n\n"
    fi
  fi
fi

# --- 6. Skill Drift Check ---
MANIFEST=".claude/skills-manifest.yaml"
STATE_FILE=".claude/.sync-state.json"
if [ -f "$MANIFEST" ]; then
  DRIFT_MSGS=""

  # (a) Orphan check: skill folders on disk that aren't in the manifest or homegrown
  if command -v python3 &>/dev/null && python3 -c 'import yaml' 2>/dev/null; then
    EXPECTED=$(python3 -c "
import yaml
with open('$MANIFEST') as f:
    m = yaml.safe_load(f) or {}
for s in m.get('skills', []):
    print(s['name'])
" 2>/dev/null)
    if [ -d ".claude/skills" ]; then
      for DIR in .claude/skills/*/; do
        [ -d "$DIR" ] || continue
        FOLDER=$(basename "$DIR")
        # Skip homegrown
        case "$FOLDER" in demo-*|pipeline-lessons) continue ;; esac
        if ! echo "$EXPECTED" | grep -qx "$FOLDER"; then
          DRIFT_MSGS+="  - orphan on disk: $FOLDER (not in manifest)\n"
        fi
      done
    fi

    # (b) Missing check: manifest entries with no folder on disk
    while IFS= read -r NAME; do
      [ -z "$NAME" ] && continue
      if [ ! -d ".claude/skills/$NAME" ]; then
        DRIFT_MSGS+="  - missing on disk: $NAME (declared in manifest)\n"
      fi
    done <<< "$EXPECTED"
  fi

  # (c) Upstream staleness: compare ls-remote HEAD against last-synced SHA
  #     Only for 'clone' type sources; skipped silently if no network or no state file.
  if [ -f "$STATE_FILE" ] && command -v python3 &>/dev/null && python3 -c 'import yaml' 2>/dev/null; then
    SOURCES=$(python3 -c "
import yaml
with open('$MANIFEST') as f:
    m = yaml.safe_load(f) or {}
for name, src in (m.get('sources') or {}).items():
    if src.get('type') == 'clone':
        print(f\"{name}|{src.get('repo','')}|{src.get('branch','main')}\")
" 2>/dev/null)
    while IFS='|' read -r SRC_NAME SRC_URL SRC_BRANCH; do
      [ -z "$SRC_NAME" ] && continue
      LAST_SHA=$(grep "\"$SRC_NAME\"" "$STATE_FILE" 2>/dev/null | head -1 | sed 's/.*: *"\([^"]*\)".*/\1/')
      [ -z "$LAST_SHA" ] && continue
      REMOTE_SHA=$(git ls-remote "$SRC_URL" "refs/heads/$SRC_BRANCH" 2>/dev/null | awk '{print $1}')
      if [ -n "$REMOTE_SHA" ] && [ "$REMOTE_SHA" != "$LAST_SHA" ]; then
        DRIFT_MSGS+="  - $SRC_NAME has new commits upstream\n"
      fi
    done <<< "$SOURCES"
  fi

  if [ -n "$DRIFT_MSGS" ]; then
    OUTPUT+="## ⚠️ Skill drift detected\n"
    OUTPUT+="$DRIFT_MSGS"
    OUTPUT+="   Run /sync-skills to reconcile.\n\n"
  fi
fi

# --- 7. install.sh Changed Since Last Run ---
# If install.sh changed in git since the last sync, session-startup flags it —
# some install.sh changes (new tools, env vars) can't be applied by /sync-skills.
if [ -f "$STATE_FILE" ] && [ -f "install.sh" ]; then
  LAST_SYNC_TS=$(grep '"synced_at"' "$STATE_FILE" 2>/dev/null | sed 's/.*: *"\([^"]*\)".*/\1/')
  if [ -n "$LAST_SYNC_TS" ]; then
    # Compare install.sh mtime to last sync timestamp (both in epoch seconds)
    INSTALL_MTIME=$(stat -f%m install.sh 2>/dev/null || stat -c%Y install.sh 2>/dev/null)
    LAST_SYNC_EPOCH=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$LAST_SYNC_TS" +%s 2>/dev/null \
      || date -d "$LAST_SYNC_TS" +%s 2>/dev/null)
    if [ -n "$INSTALL_MTIME" ] && [ -n "$LAST_SYNC_EPOCH" ] && [ "$INSTALL_MTIME" -gt "$LAST_SYNC_EPOCH" ]; then
      OUTPUT+="## ⚠️ install.sh changed since last sync\n"
      OUTPUT+="   Some install.sh changes can't be applied by /sync-skills (tool installs, env vars).\n"
      OUTPUT+="   In Terminal, from the repo root, run: bash install.sh\n\n"
    fi
  fi
fi

# --- 8. Ready ---
OUTPUT+="---\n"
OUTPUT+="**Ready.**\n"
OUTPUT+="  /scout-sparring  — Opus discovery sparring + spec generation\n"
OUTPUT+="  /scout-building  — Opus orchestrator for org deployment\n"
OUTPUT+="  /sync-skills     — pull latest external skills (per manifest)\n"
OUTPUT+="  /switch-org      — change active demo org\n"

echo -e "$OUTPUT"