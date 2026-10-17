#!/bin/bash

case "${1:-}" in
  sf) ;;
  *)
    echo "usage: setup-cli-refresh.sh sf" >&2
    exit 64 ;;
esac

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
OWNER_HELPER="$SCRIPT_DIR/setup-cli-owner.py"
NPM_EXE=$(type -P npm 2>/dev/null || true)
PYTHON_EXE=$(type -P python3 2>/dev/null || true)
CLI_EXE=$(type -P "$1" 2>/dev/null || true)
if [ -z "$NPM_EXE" ] || [ -z "$PYTHON_EXE" ] || [ -z "$CLI_EXE" ] \
    || [ ! -f "$OWNER_HELPER" ]; then
  OWNER_RESULT=unavailable
else
  OWNER_RESULT=$("$PYTHON_EXE" "$OWNER_HELPER" "$1" "$NPM_EXE" "$CLI_EXE" 2>/dev/null) \
    || OWNER_RESULT=unavailable
fi

if [ "$OWNER_RESULT" != "owned" ]; then
  if [ "$OWNER_RESULT" = "different" ]; then
    echo "SF_CLI_NOT_NPM_OWNED (active executable belongs to another installation; skipped update)"
  else
    echo "SF_CLI_OWNERSHIP_UNVERIFIED (npm ownership could not be proved; skipped update)"
  fi
  exit 0
fi

echo "CHECKING_SF_CLI"
# Gate on what npm would ACTUALLY install here, not on `npm view` latest.
# `npm view` ignores the SE's ~/.npmrc min-release-age policy (it returns the
# raw registry latest even with @latest), so comparing against it falsely
# reports "behind" whenever the newest release is younger than the policy
# window. The dry-run resolve ("X => Y") honors min-release-age — it is the
# only policy-aware signal. Skipping the reinstall when already on the newest
# INSTALLABLE version is what protects the keychain-backed org-auth token from
# a needless node rebuild (the empty-org-list footgun).
SF_VER_OUT=$("$CLI_EXE" --version 2>/dev/null); SF_VER_RC=$?
SF_VER_MATCHES=$(printf '%s\n' "$SF_VER_OUT" \
  | sed -nE 's|^@salesforce/cli/([0-9]+\.[0-9]+\.[0-9]+)([[:space:]].*)?$|\1|p')
SF_VER_COUNT=$(printf '%s\n' "$SF_VER_MATCHES" | awk 'NF { count++ } END { print count + 0 }')
SF_INSTALLED=""
if [ "$SF_VER_RC" -eq 0 ] && [ "$SF_VER_COUNT" -eq 1 ]; then
  SF_INSTALLED=$(printf '%s\n' "$SF_VER_MATCHES" | awk 'NF { print; exit }')
fi

SF_DRY_OUT=""; SF_DRY_RC=125
if [ -n "$SF_INSTALLED" ]; then
  SF_DRY_OUT=$("$NPM_EXE" install @salesforce/cli --global --dry-run 2>/dev/null); SF_DRY_RC=$?
fi
SF_RESOLVE_MATCHES=$(printf '%s\n' "$SF_DRY_OUT" \
  | sed -nE 's#^(add|change)[[:space:]]+@salesforce/cli[[:space:]]+([0-9]+\.[0-9]+\.[0-9]+)[[:space:]]*=>[[:space:]]*([0-9]+\.[0-9]+\.[0-9]+)[[:space:]]*$#\2 \3#p')
SF_RESOLVE_COUNT=$(printf '%s\n' "$SF_RESOLVE_MATCHES" | awk 'NF { count++ } END { print count + 0 }')
SF_RESOLVED_FROM=""; SF_RESOLVED=""
if [ "$SF_DRY_RC" -eq 0 ] && [ "$SF_RESOLVE_COUNT" -eq 1 ]; then
  SF_RESOLVED_FROM=$(printf '%s\n' "$SF_RESOLVE_MATCHES" | awk 'NF { print $1; exit }')
  SF_RESOLVED=$(printf '%s\n' "$SF_RESOLVE_MATCHES" | awk 'NF { print $2; exit }')
fi
if [ "$SF_RESOLVED_FROM" != "$SF_INSTALLED" ]; then
  SF_RESOLVED=""
fi

SF_REGISTRY=""
if [ -n "$SF_INSTALLED" ] && [ -n "$SF_RESOLVED" ]; then
  SF_REGISTRY=$("$NPM_EXE" view @salesforce/cli version 2>/dev/null)
fi
if [ -z "$SF_INSTALLED" ] || [ -z "$SF_RESOLVED" ]; then
  echo "SF_CLI_CHECK_FAILED (offline or npm probe failed) — kept installed: ${SF_INSTALLED:-unknown}"
elif [ "$SF_INSTALLED" = "$SF_RESOLVED" ]; then
  if [ -n "$SF_REGISTRY" ] && [ "$SF_RESOLVED" != "$SF_REGISTRY" ]; then
    echo "SF_CLI_HELD (installed $SF_INSTALLED; registry $SF_REGISTRY held by your npm min-release-age policy)"
  else
    echo "SF_CLI_CURRENT ($SF_INSTALLED)"
  fi
else
  echo "UPDATING_SF_CLI ($SF_INSTALLED -> $SF_RESOLVED)"
  # Capture the installer exit status DIRECTLY — never through a pipe. The old
  # form (`npm install ... 2>&1 | tail -1`) made $? the exit of `tail` (always 0),
  # so a failed install was invisible. Log to a temp file for the display line.
  SF_LOG=$(mktemp "${TMPDIR:-/tmp}/scout-sf-install.XXXXXX")
  "$NPM_EXE" install @salesforce/cli --global > "$SF_LOG" 2>&1; SF_RC=$?
  tail -1 "$SF_LOG"; rm -f "$SF_LOG"
  # Capture the version-probe OUTPUT and its EXIT CODE separately; a probe that
  # exits non-zero must NOT be trusted even if its stdout contains a version
  # number, and only supported `@salesforce/cli/<semver>` output is parsed (an
  # arbitrary error string that merely contains a version cannot match).
  SF_VER_OUT=$("$CLI_EXE" --version 2>/dev/null); SF_VER_RC=$?
  SF_AFTER=""
  if [ "$SF_VER_RC" -eq 0 ]; then
    SF_AFTER=$(printf '%s\n' "$SF_VER_OUT" | sed -nE 's|^@salesforce/cli/([0-9]+\.[0-9]+\.[0-9]+)([[:space:]].*)?$|\1|p')
  fi
  if [ "$SF_RC" -ne 0 ]; then
    # Install failed — failure regardless of the probe. Do NOT promise the old
    # install survived (an installer can partially change state before failing).
    if [ -n "$SF_AFTER" ]; then
      echo "SF_CLI_UPDATE_FAILED (npm exit $SF_RC; version now reports $SF_AFTER — install may be partially applied)"
    else
      echo "SF_CLI_UPDATE_FAILED (npm exit $SF_RC; post-install version could not be verified)"
    fi
  elif [ "$SF_VER_RC" -ne 0 ] || [ -z "$SF_AFTER" ]; then
    echo "SF_CLI_UPDATE_UNVERIFIED (install exit 0 but the version probe failed or returned no supported version)"
  elif [ "$SF_AFTER" = "$SF_RESOLVED" ]; then
    echo "SF_CLI_UPDATED ($SF_INSTALLED -> $SF_AFTER)"
  elif [ "$SF_AFTER" = "$SF_INSTALLED" ]; then
    echo "SF_CLI_UPDATE_NOOP (install exit 0 but version unchanged — still $SF_AFTER)"
  else
    echo "SF_CLI_UPDATE_MISMATCH (install exit 0; observed $SF_AFTER, expected $SF_RESOLVED)"
  fi
fi
