#!/bin/bash
# SF Demo Prep — Session Startup Script
# Runs automatically via SessionStart when Claude Code launches.

# The plugin loads globally. Stay completely silent outside Scout's workspace.
SCOUT_WORKSPACE="${SCOUT_WORKSPACE:-$HOME/claude-projects/sf-demo-scout}"
if [ "$PWD" != "$SCOUT_WORKSPACE" ]; then
  exit 0
fi

OUTPUT=""
umask 077

# Resolve helpers relative to this shipped hook. Overrides are narrow test seams.
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SLUGIFY="${SCOUT_SLUGIFY:-$HOOK_DIR/../scripts/slugify.py}"
STARTUP_EVIDENCE="${SCOUT_STARTUP_EVIDENCE:-$HOOK_DIR/../scripts/startup-evidence.py}"
CACHE_DIR="${SCOUT_CACHE_DIR:-$HOME/.cache/sf-demo-scout}"
RUNTIME_BASE="${SCOUT_RUNTIME_DIR:-${TMPDIR:-/tmp}}"
SETTINGS_FILE="${SCOUT_SETTINGS_FILE:-$HOME/.claude/settings.json}"
SCOUT_CONFIG_FILE="${SCOUT_CONFIG_FILE:-$HOME/.config/sf-demo-scout/config.json}"
NETWORK_TIMEOUT="${SCOUT_NETWORK_TIMEOUT:-6}"
TODAY="$(date +%Y-%m-%d)"
CURRENT_UID="$(id -u)"
RUN_DIR=""
CACHE_READY=0
HELPER_READY=0

scout_slug() {
  if command -v python3 >/dev/null 2>&1 && [ -f "$SLUGIFY" ]; then
    PYTHONDONTWRITEBYTECODE=1 python3 -B "$SLUGIFY" "$1" 2>/dev/null
  fi
}

file_mode() {
  stat -f %Lp "$1" 2>/dev/null || stat -c %a "$1" 2>/dev/null
}

file_owner() {
  stat -f %u "$1" 2>/dev/null || stat -c %u "$1" 2>/dev/null
}

cleanup_runtime() {
  if [ -n "$RUN_DIR" ] && [ -d "$RUN_DIR" ]; then
    find "$RUN_DIR" -depth -delete 2>/dev/null
  fi
}
trap cleanup_runtime EXIT HUP INT TERM

if command -v python3 >/dev/null 2>&1 && [ -f "$STARTUP_EVIDENCE" ]; then
  HELPER_READY=1
else
  OUTPUT+="## ⚠️ Startup evidence helper unavailable; Salesforce and Slack state were not inferred.\n\n"
fi

if [ ! -e "$CACHE_DIR" ] && [ ! -L "$CACHE_DIR" ]; then
  mkdir -p -m 700 "$CACHE_DIR" 2>/dev/null
fi
if [ -d "$CACHE_DIR" ] && [ ! -L "$CACHE_DIR" ]; then
  chmod 700 "$CACHE_DIR" 2>/dev/null
  if [ "$(file_mode "$CACHE_DIR")" = "700" ] && [ "$(file_owner "$CACHE_DIR")" = "$CURRENT_UID" ]; then
    CACHE_READY=1
  fi
fi
if [ "$CACHE_READY" -eq 1 ]; then
  # Remove only Scout's known legacy raw-cache names; unrelated files are untouched.
  find "$CACHE_DIR" -maxdepth 1 -type f \( \
    -name 'org-list.????-??-??' -o \
    -name 'org-display-*.????-??-??' -o \
    -name 'mcp-list.????-??-??' \
  \) -delete 2>/dev/null
else
  OUTPUT+="## ⚠️ Startup evidence cache unavailable; live state may be incomplete.\n\n"
fi

if [ ! -d "$RUNTIME_BASE" ] && [ ! -L "$RUNTIME_BASE" ]; then
  mkdir -p -m 700 "$RUNTIME_BASE" 2>/dev/null
fi
if [ -d "$RUNTIME_BASE" ]; then
  # /tmp is a symlink on macOS. Resolve an existing base, then create a unique
  # private child rather than rejecting the platform's canonical temp path.
  RUNTIME_BASE="$(cd "$RUNTIME_BASE" 2>/dev/null && pwd -P)"
  RUN_DIR="$(mktemp -d "$RUNTIME_BASE/scout-startup.XXXXXX" 2>/dev/null)"
fi
if [ -z "$RUN_DIR" ]; then
  CACHE_READY=0
  OUTPUT+="## ⚠️ Startup evidence runtime unavailable; live state was not collected.\n\n"
fi

# Run a command with stdout at $2 and preserve its status. The child gets its
# own process group so timeout cleanup includes wrapper grandchildren.
run_bounded() {
  local secs="$1" dest="$2"
  shift 2
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
    my $status = $?;
    exit(128 + ($status & 127)) if ($status & 127);
    exit($status >> 8);
  ' "$secs" "$@" >"$dest" 2>/dev/null
}

cache_path() { printf '%s/%s.json\n' "$CACHE_DIR" "$1"; }
status_path() { printf '%s/%s.status\n' "$RUN_DIR" "$1"; }

cache_valid() {
  local key="$1" kind="$2" target="$3" file
  file="$(cache_path "$key")"
  [ -f "$file" ] && [ ! -L "$file" ] || return 1
  [ "$(file_mode "$file")" = "600" ] || return 1
  [ "$(file_owner "$file")" = "$CURRENT_UID" ] || return 1
  if [ -n "$target" ]; then
    PYTHONDONTWRITEBYTECODE=1 python3 -B "$STARTUP_EVIDENCE" validate "$kind" \
      --collected-date "$TODAY" --target "$target" <"$file" >/dev/null 2>&1
  else
    PYTHONDONTWRITEBYTECODE=1 python3 -B "$STARTUP_EVIDENCE" validate "$kind" \
      --collected-date "$TODAY" <"$file" >/dev/null 2>&1
  fi
}

discard_cache() {
  local file="$1"
  if [ -f "$file" ] || [ -L "$file" ]; then
    unlink "$file" 2>/dev/null
  fi
}

# Normalize before publishing. Every background call writes its own status;
# the parent waits on each PID explicitly and never relies on a bare wait.
cache_fill() {
  local key="$1" kind="$2" provenance="$3" secs="$4" target="$5"
  shift 5
  local file status raw normalized rc
  file="$(cache_path "$key")"
  status="$(status_path "$key")"
  if [ -z "$SCOUT_HOOK_NOCACHE" ] && cache_valid "$key" "$kind" "$target"; then
    printf 'cached\n' >"$status"
    return 0
  fi

  # A needed or forced refresh supersedes prior evidence before the probe.
  discard_cache "$file"
  if [ -d "$file" ] && [ ! -L "$file" ]; then
    printf 'cache-write\n' >"$status"
    return 1
  fi
  raw="$(mktemp "$RUN_DIR/raw.XXXXXX" 2>/dev/null)" || {
    printf 'cache-write\n' >"$status"; return 1;
  }
  # Stage beside the destination so the final rename is same-filesystem atomic.
  normalized="$(mktemp "$CACHE_DIR/.normalized.XXXXXX" 2>/dev/null)" || {
    unlink "$raw" 2>/dev/null; printf 'cache-write\n' >"$status"; return 1;
  }
  run_bounded "$secs" "$raw" "$@"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    printf 'exit:%s\n' "$rc" >"$status"
    unlink "$raw" 2>/dev/null
    unlink "$normalized" 2>/dev/null
    return 1
  fi
  if [ -n "$target" ]; then
    PYTHONDONTWRITEBYTECODE=1 python3 -B "$STARTUP_EVIDENCE" normalize "$kind" \
      --collected-date "$TODAY" --provenance "$provenance" --target "$target" \
      <"$raw" >"$normalized" 2>/dev/null
  else
    PYTHONDONTWRITEBYTECODE=1 python3 -B "$STARTUP_EVIDENCE" normalize "$kind" \
      --collected-date "$TODAY" --provenance "$provenance" \
      <"$raw" >"$normalized" 2>/dev/null
  fi
  rc=$?
  unlink "$raw" 2>/dev/null
  if [ "$rc" -ne 0 ]; then
    printf 'malformed\n' >"$status"
    unlink "$normalized" 2>/dev/null
    return 1
  fi
  chmod 600 "$normalized" 2>/dev/null && mv -f "$normalized" "$file" 2>/dev/null
  rc=$?
  if [ "$rc" -ne 0 ] || ! cache_valid "$key" "$kind" "$target"; then
    printf 'cache-write\n' >"$status"
    unlink "$normalized" 2>/dev/null
    discard_cache "$file"
    return 1
  fi
  printf 'fresh\n' >"$status"
  return 0
}

collect_config() {
  local status="$RUN_DIR/config.status" raw="$RUN_DIR/config.raw" normalized="$RUN_DIR/config.json" rc
  run_bounded "$NETWORK_TIMEOUT" "$raw" sf config get target-org --json
  rc=$?
  if [ "$rc" -ne 0 ]; then
    printf 'exit:%s\n' "$rc" >"$status"
    unlink "$raw" 2>/dev/null
    return 1
  fi
  PYTHONDONTWRITEBYTECODE=1 python3 -B "$STARTUP_EVIDENCE" normalize config \
    --collected-date "$TODAY" --provenance 'sf config get target-org --json' \
    <"$raw" >"$normalized" 2>/dev/null
  rc=$?
  unlink "$raw" 2>/dev/null
  if [ "$rc" -ne 0 ]; then
    printf 'malformed\n' >"$status"
    unlink "$normalized" 2>/dev/null
    return 1
  fi
  chmod 600 "$normalized" 2>/dev/null
  printf 'fresh\n' >"$status"
}

probe_status() { cat "$RUN_DIR/$1.status" 2>/dev/null; }

failure_reason() {
  local status="$1" rc
  case "$status" in
    malformed) printf 'malformed evidence' ;;
    cache-write) printf 'cache update failed' ;;
    exit:124) printf 'timed out' ;;
    exit:125) printf 'probe runner failed' ;;
    exit:127) printf 'command unavailable' ;;
    exit:*)
      rc="${status#exit:}"
      if [ "$rc" -ge 128 ] 2>/dev/null; then
        printf 'terminated by signal %s' "$((rc - 128))"
      else
        printf 'exit %s' "$rc"
      fi
      ;;
    *) printf 'no usable evidence' ;;
  esac
}

evidence_field() {
  local key="$1" kind="$2" field="$3" target="$4" file
  file="$(cache_path "$key")"
  if [ -n "$target" ]; then
    PYTHONDONTWRITEBYTECODE=1 python3 -B "$STARTUP_EVIDENCE" field "$kind" \
      --collected-date "$TODAY" --target "$target" --field "$field" <"$file" 2>/dev/null
  else
    PYTHONDONTWRITEBYTECODE=1 python3 -B "$STARTUP_EVIDENCE" field "$kind" \
      --collected-date "$TODAY" --field "$field" <"$file" 2>/dev/null
  fi
}

list_membership() {
  PYTHONDONTWRITEBYTECODE=1 python3 -B "$STARTUP_EVIDENCE" contains list \
    --collected-date "$TODAY" --target "$1" <"$(cache_path org-list)" 2>/dev/null
}

evidence_age_label() {
  local key="$1" kind="$2" target="$3" status collected
  status="$(probe_status "$key")"
  collected="$(evidence_field "$key" "$kind" collected_at_utc "$target")"
  if [ "$status" = "fresh" ]; then
    printf 'fresh evidence collected %s' "$collected"
  else
    printf 'cached evidence from %s' "$collected"
  fi
}

# --- 1. LLMGW Auth Check ---
if [ -f "$SETTINGS_FILE" ] && grep -q '"ANTHROPIC_AUTH_TOKEN"' "$SETTINGS_FILE" 2>/dev/null; then
  OUTPUT+="## ✅ LLMGW auth token present.\n\n"
else
  OUTPUT+="## ⚠️ No LLMGW auth token found in ~/.claude/settings.json\n"
  OUTPUT+="   Run the Claude Code installer first: see the 'Installing Claude Code for Solutions' canvas.\n\n"
fi

CONFIG_STATUS="unavailable"
LIST_STATUS="unavailable"
MCP_STATUS="unavailable"
DEFAULT_ORG=""
ORG_COUNT=""

# --- 2. Fan out independent probes ---
if [ "$HELPER_READY" -eq 1 ] && [ "$CACHE_READY" -eq 1 ] && [ -n "$RUN_DIR" ]; then
  cache_fill org-list list 'sf org list --json' "$NETWORK_TIMEOUT" '' sf org list --json &
  LIST_PID=$!
  if command -v claude >/dev/null 2>&1; then
    cache_fill mcp-list mcp 'claude mcp list' "$NETWORK_TIMEOUT" '' claude mcp list &
    MCP_PID=$!
  else
    printf 'exit:127\n' >"$RUN_DIR/mcp-list.status"
    MCP_PID=""
  fi
  collect_config &
  CONFIG_PID=$!
  wait "$LIST_PID"; LIST_WAIT_STATUS=$?
  if [ -n "$MCP_PID" ]; then wait "$MCP_PID"; MCP_WAIT_STATUS=$?; fi
  wait "$CONFIG_PID"; CONFIG_WAIT_STATUS=$?

  LIST_STATUS="$(probe_status org-list)"
  MCP_STATUS="$(probe_status mcp-list)"
  CONFIG_STATUS="$(probe_status config)"
fi

# --- 3. Slack MCP state ---
if [ "$MCP_STATUS" = "fresh" ] || [ "$MCP_STATUS" = "cached" ]; then
  SLACK_STATE="$(evidence_field mcp-list mcp state '')"
  if [ "$SLACK_STATE" = "not_connected" ]; then
    OUTPUT+="## ℹ️ Slack MCP registered but not connected ($(evidence_age_label mcp-list mcp '')).\n"
    OUTPUT+="   Run \`/mcp\` in this session, select 'slack', choose 'Authenticate'.\n\n"
  fi
elif command -v claude >/dev/null 2>&1 && [ "$HELPER_READY" -eq 1 ] && [ "$CACHE_READY" -eq 1 ]; then
  OUTPUT+="## ℹ️ Slack MCP connection check unavailable ($(failure_reason "$MCP_STATUS")).\n\n"
fi

# --- 4. Salesforce org evidence ---
if [ "$CONFIG_STATUS" = "fresh" ]; then
  CONFIG_STATE="$(PYTHONDONTWRITEBYTECODE=1 python3 -B "$STARTUP_EVIDENCE" field config \
    --collected-date "$TODAY" --field state <"$RUN_DIR/config.json" 2>/dev/null)"
  if [ "$CONFIG_STATE" = "present" ]; then
    DEFAULT_ORG="$(PYTHONDONTWRITEBYTECODE=1 python3 -B "$STARTUP_EVIDENCE" field config \
      --collected-date "$TODAY" --field target <"$RUN_DIR/config.json" 2>/dev/null)"
  fi
else
  OUTPUT+="## ⚠️ Default Salesforce org check unavailable ($(failure_reason "$CONFIG_STATUS")).\n\n"
fi

if [ "$LIST_STATUS" = "fresh" ] || [ "$LIST_STATUS" = "cached" ]; then
  ORG_COUNT="$(evidence_field org-list list org_count '')"
else
  OUTPUT+="## ⚠️ Connected org list unavailable ($(failure_reason "$LIST_STATUS")).\n\n"
fi

if [ "$CONFIG_STATUS" = "fresh" ] && [ "$CONFIG_STATE" = "absent" ]; then
  OUTPUT+="## ⚠️ No default Salesforce org set.\n"
  if [ -n "$ORG_COUNT" ]; then
    OUTPUT+="$ORG_COUNT org(s) available. To connect:\n"
  else
    OUTPUT+="Connected org count unavailable. To connect:\n"
  fi
  OUTPUT+="  sf org login web --alias [name] --set-default\n\n"
elif [ -n "$DEFAULT_ORG" ]; then
  LIST_MEMBERSHIP="unavailable"
  if [ -n "$ORG_COUNT" ]; then
    LIST_MEMBERSHIP="$(list_membership "$DEFAULT_ORG")"
    # One cached miss gets a fresh retry in case the org was connected today.
    if [ "$LIST_MEMBERSHIP" = "missing" ] && [ "$LIST_STATUS" = "cached" ]; then
      SCOUT_HOOK_NOCACHE=1 cache_fill org-list list 'sf org list --json' \
        "$NETWORK_TIMEOUT" '' sf org list --json
      LIST_STATUS="$(probe_status org-list)"
      if [ "$LIST_STATUS" = "fresh" ]; then
        ORG_COUNT="$(evidence_field org-list list org_count '')"
        LIST_MEMBERSHIP="$(list_membership "$DEFAULT_ORG")"
      else
        ORG_COUNT=""
        LIST_MEMBERSHIP="unavailable"
        OUTPUT+="## ⚠️ Connected org list unavailable ($(failure_reason "$LIST_STATUS")).\n\n"
      fi
    fi
  fi

  if [ "$LIST_MEMBERSHIP" = "missing" ]; then
    LOCAL_CONFIG=".sf/config.json"
    OUTPUT+="## ⚠️ Configured target-org '$DEFAULT_ORG' is not in the connected org list.\n"
    OUTPUT+="   This usually means a stale entry in $LOCAL_CONFIG (local scope overrides global).\n"
    OUTPUT+="   Fix: run /scout-sparring or /scout-building — they connect or switch the org inline — or edit $LOCAL_CONFIG manually.\n\n"
  else
    ALIAS_KEY="$(PYTHONDONTWRITEBYTECODE=1 python3 -B "$STARTUP_EVIDENCE" key "$DEFAULT_ORG" 2>/dev/null)"
    DISPLAY_KEY="org-display-$ALIAS_KEY"
    cache_fill "$DISPLAY_KEY" display 'sf org display --json' "$NETWORK_TIMEOUT" \
      "$DEFAULT_ORG" sf org display --target-org "$DEFAULT_ORG" --json
    DISPLAY_STATUS="$(probe_status "$DISPLAY_KEY")"
    if [ "$DISPLAY_STATUS" = "fresh" ] || [ "$DISPLAY_STATUS" = "cached" ]; then
      DISPLAY_STATE="$(evidence_field "$DISPLAY_KEY" display state "$DEFAULT_ORG")"
      DISPLAY_EVIDENCE="$(evidence_age_label "$DISPLAY_KEY" display "$DEFAULT_ORG")"
      if [ "$DISPLAY_STATE" = "connected" ]; then
        USERNAME="$(evidence_field "$DISPLAY_KEY" display username "$DEFAULT_ORG")"
        ORG_ID="$(evidence_field "$DISPLAY_KEY" display org_id "$DEFAULT_ORG")"
        INSTANCE_URL="$(evidence_field "$DISPLAY_KEY" display instance_url "$DEFAULT_ORG")"
        if [ "$DISPLAY_STATUS" = "fresh" ]; then
          OUTPUT+="## ✅ Active Org ($DISPLAY_EVIDENCE)\n"
        else
          OUTPUT+="## ℹ️ Active Org ($DISPLAY_EVIDENCE)\n"
        fi
        OUTPUT+="- **Alias:** $DEFAULT_ORG\n"
        OUTPUT+="- **Username:** $USERNAME\n"
        OUTPUT+="- **Org ID:** $ORG_ID\n"
        OUTPUT+="- **Instance:** $INSTANCE_URL\n"
        if [ -n "$ORG_COUNT" ]; then
          OUTPUT+="$ORG_COUNT org(s) available. To switch, say 'switch' when /scout-sparring or /scout-building asks.\n\n"
        else
          OUTPUT+="Connected org count unavailable.\n\n"
        fi

        # --- 5. Org Folder + Audit Check ---
        ORG_SLUG="$(scout_slug "$DEFAULT_ORG")"
        ORG_FOLDERS=""
        [ -n "$ORG_SLUG" ] && ORG_FOLDERS=$(ls -d "orgs/${ORG_SLUG}-"*/ 2>/dev/null)
        if [ -z "$ORG_SLUG" ]; then
          OUTPUT+="## ℹ️ Customer-folder lookup unavailable for $DEFAULT_ORG — couldn't derive a folder slug (python3 or scripts/slugify.py missing, or the alias has no usable slug). Not asserting folders are absent.\n\n"
        elif [ -n "$ORG_FOLDERS" ]; then
          FOLDER_COUNT=$(echo "$ORG_FOLDERS" | wc -l | tr -d ' ')
          OUTPUT+="## ℹ️ $FOLDER_COUNT customer folder(s) for $DEFAULT_ORG:\n"
          for FOLDER in $ORG_FOLDERS; do
            CUSTOMER=$(basename "$FOLDER" | sed "s/^${ORG_SLUG}-//")
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
              OUTPUT+="    Last change log: $(basename "$LATEST_CHANGES")\n"
            fi
          done
          OUTPUT+="\n"
        else
          OUTPUT+="## ℹ️ No customer folders for $DEFAULT_ORG — run /scout-sparring to create one.\n\n"
        fi
      else
        CONNECTED_STATUS="$(evidence_field "$DISPLAY_KEY" display connected_status "$DEFAULT_ORG")"
        OUTPUT+="## ⚠️ Org '$DEFAULT_ORG' is not connected ($CONNECTED_STATUS; $DISPLAY_EVIDENCE).\n\n"
      fi
    else
      OUTPUT+="## ⚠️ Org '$DEFAULT_ORG' evidence unavailable ($(failure_reason "$DISPLAY_STATUS")).\n\n"
    fi
  fi
fi

# --- 6. Plugin First-Run Nudge ---
if [ ! -f "$SCOUT_CONFIG_FILE" ]; then
  OUTPUT+="## ⚠️ Scout setup not yet complete.\n"
  OUTPUT+="   Run /scout-setup to install — handles fresh installs, refreshes, and repairs.\n\n"
fi

# --- 7. Ready ---
OUTPUT+="---\n"
OUTPUT+="**Ready.**\n"
OUTPUT+="  /scout-sparring  — Opus discovery sparring + spec generation\n"
OUTPUT+="  /scout-building  — Opus orchestrator for org deployment\n"
OUTPUT+="  /scout-setup     — install, refresh, or repair Scout\n"

printf '%b\n' "$OUTPUT"
