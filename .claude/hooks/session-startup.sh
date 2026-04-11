#!/bin/bash
# SF Demo Prep — Session Startup Script
# Runs automatically via SessionStart hook when Claude Code launches.
# Handles: AWS SSO refresh, Salesforce org check, model/context info.

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
  OUTPUT+="Available orgs ($ORG_COUNT found). To connect:\n"
  OUTPUT+="  sf org login web --alias [name] --set-default\n\n"
else
  # Check if default org is still authenticated
  if sf org display --target-org "$DEFAULT_ORG" --json &>/dev/null; then
    USERNAME=$(sf org display --target-org "$DEFAULT_ORG" --json 2>/dev/null | grep -o '"username":"[^"]*"' | head -1 | cut -d'"' -f4)
    OUTPUT+="## ✅ Salesforce org: $DEFAULT_ORG ($USERNAME)\n"
    OUTPUT+="$ORG_COUNT org(s) available. Switch with: sf config set target-org [alias]\n\n"
  else
    OUTPUT+="## ⚠️ Org '$DEFAULT_ORG' auth expired. Re-authenticate:\n"
    OUTPUT+="  sf org login web --alias $DEFAULT_ORG\n\n"
  fi
fi

# --- 3. CLAUDE.md Org Block Check ---
if [ -f "CLAUDE.md" ]; then
  if grep -q "\[YOUR ORG USERNAME\]" CLAUDE.md 2>/dev/null; then
    OUTPUT+="## ⚠️ CLAUDE.md still has placeholder org details. Update the ## Org section.\n\n"
  fi
else
  OUTPUT+="## ⚠️ No CLAUDE.md found in this directory. Are you in the sf-demo-prep project?\n\n"
fi

# --- 4. Recent Org Audit ---
LATEST_AUDIT=$(ls -t org-audit-*.md 2>/dev/null | head -1)
if [ -n "$LATEST_AUDIT" ]; then
  AUDIT_AGE=$(( ( $(date +%s) - $(stat -f%m "$LATEST_AUDIT" 2>/dev/null || stat -c%Y "$LATEST_AUDIT" 2>/dev/null) ) / 86400 ))
  if [ "$AUDIT_AGE" -gt 7 ]; then
    OUTPUT+="## ℹ️ Org audit ($LATEST_AUDIT) is ${AUDIT_AGE} days old. Consider re-running.\n\n"
  else
    OUTPUT+="## ✅ Recent org audit: $LATEST_AUDIT (${AUDIT_AGE}d ago)\n\n"
  fi
else
  OUTPUT+="## ℹ️ No org audit found. Run one before starting Demo Scout.\n\n"
fi

# --- 5. Model Info ---
OUTPUT+="---\n"
OUTPUT+="**Ready.** Type \`/demo-scout\` to start sparring, or describe what you need.\n"
OUTPUT+="Tip: \`/model opusplan\` for Opus sparring + Sonnet deployment.\n"

echo -e "$OUTPUT"
