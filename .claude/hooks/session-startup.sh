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
else
  ORG_DISPLAY=$(sf org display --target-org "$DEFAULT_ORG" --json 2>/dev/null)
  if [ -n "$ORG_DISPLAY" ]; then
    USERNAME=$(echo "$ORG_DISPLAY" | grep -o '"username":"[^"]*"' | head -1 | cut -d'"' -f4)

    # Use "orgId" specifically — "id" matches multiple fields in sf org display output.
    # Fallback to matching any "id" value starting with "00D" (org ID prefix) for older CLI versions.
    ORG_ID=$(echo "$ORG_DISPLAY" | grep -o '"orgId":"[^"]*"' | head -1 | cut -d'"' -f4)
    if [ -z "$ORG_ID" ]; then
      ORG_ID=$(echo "$ORG_DISPLAY" | grep -o '"id":"00D[^"]*"' | head -1 | cut -d'"' -f4)
    fi

    ORG_ID_SHORT="${ORG_ID:0:6}"
    OUTPUT+="## ✅ Active org: $DEFAULT_ORG ($USERNAME)\n"
    OUTPUT+="$ORG_COUNT org(s) available. Switch: sf config set target-org [alias]\n\n"

    # --- 3. Org Folder + Audit Check ---
    ORG_FOLDER="orgs/${DEFAULT_ORG}-${ORG_ID_SHORT}"
    if [ -d "$ORG_FOLDER" ]; then
      LATEST_AUDIT=$(ls -t "$ORG_FOLDER"/audit-*.md 2>/dev/null | head -1)
      if [ -n "$LATEST_AUDIT" ]; then
        AUDIT_AGE=$(( ( $(date +%s) - $(stat -f%m "$LATEST_AUDIT" 2>/dev/null || stat -c%Y "$LATEST_AUDIT" 2>/dev/null) ) / 86400 ))
        AUDIT_FILE=$(basename "$LATEST_AUDIT")
        if [ "$AUDIT_AGE" -gt 7 ]; then
          OUTPUT+="## ⚠️ Org audit ($AUDIT_FILE) is ${AUDIT_AGE} days old — consider refreshing.\n\n"
        else
          OUTPUT+="## ✅ Org audit: $AUDIT_FILE (${AUDIT_AGE}d ago)\n\n"
        fi
        LATEST_CHANGES=$(ls -t "$ORG_FOLDER"/changes-*.md 2>/dev/null | head -1)
        if [ -n "$LATEST_CHANGES" ]; then
          OUTPUT+="## ℹ️ Last change log: $(basename $LATEST_CHANGES)\n\n"
        fi
      else
        OUTPUT+="## ℹ️ Org folder exists but no audit found — run /scout-sparring to create one.\n\n"
      fi
    else
      OUTPUT+="## ℹ️ No org folder found for $DEFAULT_ORG — a new audit will be created on first run.\n\n"
    fi
  else
    OUTPUT+="## ⚠️ Org '$DEFAULT_ORG' auth expired. Re-authenticate:\n"
    OUTPUT+="  sf org login web --alias $DEFAULT_ORG\n\n"
  fi
fi

# --- 4. CLAUDE.md Placeholder Check ---
if [ -f "CLAUDE.md" ]; then
  if grep -q "\[YOUR ORG USERNAME\]" CLAUDE.md 2>/dev/null; then
    OUTPUT+="## ⚠️ CLAUDE.md still has placeholder org details. Run /setup-demo-scout.\n\n"
  fi
else
  OUTPUT+="## ⚠️ No CLAUDE.md found. Are you in the sf-demo-prep project directory?\n\n"
fi

# --- 5. GitHub Update Check ---
if git rev-parse --git-dir &>/dev/null; then
  if git fetch origin main --quiet --depth=1 2>/dev/null; then
    LOCAL=$(git rev-parse HEAD 2>/dev/null)
    REMOTE=$(git rev-parse origin/main 2>/dev/null)
    if [ -n "$LOCAL" ] && [ -n "$REMOTE" ] && [ "$LOCAL" != "$REMOTE" ]; then
      OUTPUT+="## ⚠️ SF Demo Scout has updates available.\n"
      OUTPUT+="   Run: git pull — then restart VS Code to pick up the changes.\n\n"
    fi
  fi
fi

# --- 6. Ready ---
OUTPUT+="---\n"
OUTPUT+="**Ready.**\n"
OUTPUT+="  /scout-sparring  — Opus 4.6 discovery sparring + spec generation\n"
OUTPUT+="  /scout-building  — Sonnet 4.6 org deployment from completed spec\n"
OUTPUT+="  /switch-org      — change active demo org\n"

echo -e "$OUTPUT"