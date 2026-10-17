#!/bin/bash
# SF Demo Prep — Session Startup Script
# Runs via SessionStart. Host-specific checks never consult another host.

# Client notices apply globally; org/status probes remain workspace-scoped.
CLIENT_HELPER_DIR="$(cd "${BASH_SOURCE[0]%/*}/../scripts" && pwd)"
CLIENT_EVIDENCE="${SCOUT_STARTUP_EVIDENCE:-$CLIENT_HELPER_DIR/startup-evidence.py}"
CLIENT_VERSION="$CLIENT_HELPER_DIR/client-version.py"
SCOUT_CLIENT_FLOOR=""
source "${CLIENT_VERSION%/*}/client-cache.sh"
if ! scout_current_client_cached && command -v python3 >/dev/null 2>&1 && [ -f "$CLIENT_EVIDENCE" ]; then
  SCOUT_CLIENT_FLOOR=$(python3 -B "$CLIENT_VERSION" floor 2>/dev/null) || SCOUT_CLIENT_FLOOR=""
fi
scout_emit_context() {
  local rendered
  if [ -n "$SCOUT_CLIENT_FLOOR" ]; then
    if rendered=$(python3 -B "$CLIENT_EVIDENCE" hook-output --floor-line "$SCOUT_CLIENT_FLOOR" 2>/dev/null); then
      printf '%s\n' "$rendered"
      return
    fi
    return 1
  fi
  return 1
}
# The expanded path is data, quoted for the reader rather than evaluated.
SCOUT_RULES_BLOCK=""
SCOUT_RULES_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
case "$SCOUT_RULES_ROOT" in
  /*)
    if [[ "$SCOUT_RULES_ROOT" != *$'\n'* && "$SCOUT_RULES_ROOT" != *$'\r'* ]]; then
      SCOUT_RULES_PATH="${SCOUT_RULES_ROOT%/}/AGENTS.md"
      SCOUT_RULES_PATH="${SCOUT_RULES_PATH//\\/\\\\}"
      SCOUT_RULES_PATH="${SCOUT_RULES_PATH//\"/\\\"}"
      printf -v SCOUT_RULES_BLOCK 'Scout is installed. Before any Salesforce org change, including a quick fix outside a Scout command, read "%s" and follow it.\nGet the SE'\''s explicit confirmation before:\n- Delete existing metadata or records\n- Modify existing profiles or permission sets\n- Touch anything prefixed `sb_` or `managed__`' "$SCOUT_RULES_PATH"
      [ $((${#SCOUT_RULES_BLOCK} + 2)) -le 600 ] || SCOUT_RULES_BLOCK=""
    fi ;;
esac

scout_legacy_context() {
  if [ "$1" = inside ]; then
    printf '%b\n' "$OUTPUT"
  elif [ -n "$SCOUT_OFFICIAL_NOTICE" ]; then
    printf '%b' "$SCOUT_OFFICIAL_NOTICE"
  fi
}
scout_finish_context() {
  local scope="$1" context
  local LC_ALL=C  # Byte count is a conservative trigger for the Unicode-aware bound.
  if [ -n "$SCOUT_RULES_BLOCK" ]; then
    # A sentinel preserves the legacy trailing newlines through command substitution.
    context=$(printf '%s\n\n' "$SCOUT_RULES_BLOCK"; scout_legacy_context "$scope"; printf '\034')
    context=${context%$'\034'}
    if [ -n "$context" ]; then
      printf '%s' "$context" | scout_emit_context || printf '%s' "$context"
      return
    fi
  fi
  scout_legacy_context "$scope" | scout_emit_context || scout_legacy_context "$scope"
}
# Resolve helpers relative to this shipped hook. Overrides are narrow test seams.
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_STATUS_SCRIPT="${SCOUT_MCP_STATUS_SCRIPT:-$HOOK_DIR/../scripts/setup-mcp-status.py}"
SCOUT_ACTIVE_HOST="unknown"
if command -v python3 >/dev/null 2>&1 && [ -f "$MCP_STATUS_SCRIPT" ]; then
  SCOUT_ACTIVE_HOST="$(python3 -B "$MCP_STATUS_SCRIPT" --detect-host 2>/dev/null)"
fi

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

# Salesforce's official plugins, which Scout builds with (Claude only; never blocks). A client notice, so it applies in
# every folder: an SE whose Scout updated while they work outside the workspace still learns that setup is needed.
SCOUT_OFFICIAL_NOTICE=""
OFFICIAL_SCRIPT="${SCOUT_OFFICIAL_SCRIPT:-$HOOK_DIR/../scripts/scout_official.py}"
if [ "$SCOUT_ACTIVE_HOST" = "claude" ] && command -v python3 >/dev/null 2>&1 && [ -f "$OFFICIAL_SCRIPT" ] \
    && OFFICIAL_OUT="$(mktemp "${TMPDIR:-/tmp}/scout-official.XXXXXX" 2>/dev/null)"; then
  # Local reads only, but bounded anyway: a stalled config folder must never stall the session start.
  PYTHONDONTWRITEBYTECODE=1 run_bounded 3 "$OFFICIAL_OUT" python3 -B "$OFFICIAL_SCRIPT" resolve --host claude \
    --plugin salesforce-development --launch-dir "$PWD"
  OFFICIAL_STATE="$(python3 -B -c 'import json, sys; print(json.load(open(sys.argv[1]))["state"])' "$OFFICIAL_OUT" 2>/dev/null)"
  rm -f "$OFFICIAL_OUT"
  case "$OFFICIAL_STATE" in
    installed|"") ;;
    conflict) SCOUT_OFFICIAL_NOTICE="## ℹ️ Two copies of Salesforce's official plugin are switched on. Run \`/scout-setup\` to switch the extra one off.\n\n" ;;
    *) SCOUT_OFFICIAL_NOTICE="## ℹ️ Scout builds with Salesforce's official plugins, which aren't set up yet. Run \`/scout-setup\` once.\n\n" ;;
  esac
fi

SCOUT_WORKSPACE="${SCOUT_WORKSPACE:-$HOME/claude-projects/sf-demo-scout}"
if [ "$PWD" != "$SCOUT_WORKSPACE" ]; then
  scout_finish_context outside
  exit 0
fi

OUTPUT=""
umask 077

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
  OUTPUT+="## ⚠️ Startup evidence helper unavailable; Salesforce state was not inferred.\n\n"
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
  # Remove only Scout's known legacy cache names, including the org-list and MCP caches that
  # startup no longer writes; unrelated files are untouched.
  find "$CACHE_DIR" -maxdepth 1 -type f \( \
    -name 'org-list.????-??-??' -o \
    -name 'org-display-*.????-??-??' -o \
    -name 'mcp-list.????-??-??' -o \
    -name 'org-list.json' -o \
    -name 'mcp-list.json' \
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
if [ "$SCOUT_ACTIVE_HOST" = "claude" ]; then
  if [ -f "$SETTINGS_FILE" ] && grep -q '"ANTHROPIC_AUTH_TOKEN"' "$SETTINGS_FILE" 2>/dev/null; then
    OUTPUT+="## ✅ LLMGW auth token present.\n\n"
  else
    OUTPUT+="## ⚠️ No LLMGW auth token found in ~/.claude/settings.json\n"
    OUTPUT+="   Run the Claude Code installer first: see the 'Installing Claude Code for Solutions' canvas.\n\n"
  fi
fi

# --- 1b. Salesforce's official plugins: the notice computed before the workspace gate ---
OUTPUT+="$SCOUT_OFFICIAL_NOTICE"

CONFIG_STATUS="unavailable"
DEFAULT_ORG=""

# --- 2. The default org's config ---
if [ "$HELPER_READY" -eq 1 ] && [ "$CACHE_READY" -eq 1 ] && [ -n "$RUN_DIR" ]; then
  collect_config
  CONFIG_STATUS="$(probe_status config)"
fi

# --- 3. Salesforce org evidence ---
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

if [ "$CONFIG_STATUS" = "fresh" ] && [ "$CONFIG_STATE" = "absent" ]; then
  OUTPUT+="## ⚠️ No default Salesforce org set.\n"
  OUTPUT+="   Name the org in your /scout request. If it isn't connected yet, Scout offers to open Salesforce's login page for you.\n\n"
elif [ -n "$DEFAULT_ORG" ]; then
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
      OUTPUT+="To work in another org, name it in your /scout request.\n\n"
    else
      CONNECTED_STATUS="$(evidence_field "$DISPLAY_KEY" display connected_status "$DEFAULT_ORG")"
      OUTPUT+="## ⚠️ Org '$DEFAULT_ORG' is not connected ($CONNECTED_STATUS; $DISPLAY_EVIDENCE).\n\n"
    fi
  else
    OUTPUT+="## ⚠️ Org '$DEFAULT_ORG' evidence unavailable ($(failure_reason "$DISPLAY_STATUS")).\n\n"
  fi
fi

# --- 4. Plugin First-Run Nudge ---
if [ ! -f "$SCOUT_CONFIG_FILE" ]; then
  OUTPUT+="## ⚠️ Scout setup not yet complete.\n"
  OUTPUT+="   Run /scout-setup to install — handles fresh installs, refreshes, and repairs.\n\n"
fi

# --- 5. Ready ---
OUTPUT+="---\n"
OUTPUT+="**Ready.**\n"
OUTPUT+="  /scout           — Scout 2.0: spar, build, fix or prep a demo in one session\n"
OUTPUT+="  /scout-setup     — install, refresh, or repair Scout\n"
OUTPUT+="  (/scout-sparring and /scout-building are classic names; they now open /scout.)\n"

scout_finish_context inside
