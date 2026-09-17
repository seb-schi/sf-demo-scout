#!/bin/bash

case "${1:-}" in
  sf|claude) ;;
  *)
    echo "usage: setup-cli-refresh.sh sf|claude" >&2
    exit 64 ;;
esac

if [ "$1" = "sf" ]; then
  echo "CHECKING_SF_CLI"
  # Gate on what npm would ACTUALLY install here, not on `npm view` latest.
  # `npm view` ignores the SE's ~/.npmrc min-release-age policy (it returns the
  # raw registry latest even with @latest), so comparing against it falsely
  # reports "behind" whenever the newest release is younger than the policy
  # window. The dry-run resolve ("X => Y") honors min-release-age — it is the
  # only policy-aware signal. Skipping the reinstall when already on the newest
  # INSTALLABLE version is what protects the keychain-backed org-auth token from
  # a needless node rebuild (the empty-org-list footgun).
  SF_INSTALLED=$(sf --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
  SF_RESOLVED=$(npm install @salesforce/cli --global --dry-run 2>/dev/null \
    | grep -E '(^| )@salesforce/cli[[:space:]]' \
    | grep -oE '[0-9]+\.[0-9]+\.[0-9]+ *=> *[0-9]+\.[0-9]+\.[0-9]+' \
    | grep -oE '[0-9]+\.[0-9]+\.[0-9]+$' | head -1)
  SF_REGISTRY=$(npm view @salesforce/cli version 2>/dev/null)
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
    npm install @salesforce/cli --global > "$SF_LOG" 2>&1; SF_RC=$?
    tail -1 "$SF_LOG"; rm -f "$SF_LOG"
    # Capture the version-probe OUTPUT and its EXIT CODE separately; a probe that
    # exits non-zero must NOT be trusted even if its stdout contains a version
    # number, and only supported `@salesforce/cli/<semver>` output is parsed (an
    # arbitrary error string that merely contains a version cannot match).
    SF_VER_OUT=$(sf --version 2>/dev/null); SF_VER_RC=$?
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
else
  echo "CHECKING_CLAUDE_CLI"
  # Policy-aware gate — see step a's comment for why dry-run resolve, not `npm view`.
  CC_INSTALLED=$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
  CC_RESOLVED=$(npm install @anthropic-ai/claude-code --global --dry-run 2>/dev/null \
    | grep -E '(^| )@anthropic-ai/claude-code[[:space:]]' \
    | grep -oE '[0-9]+\.[0-9]+\.[0-9]+ *=> *[0-9]+\.[0-9]+\.[0-9]+' \
    | grep -oE '[0-9]+\.[0-9]+\.[0-9]+$' | head -1)
  CC_REGISTRY=$(npm view @anthropic-ai/claude-code version 2>/dev/null)
  if [ -z "$CC_INSTALLED" ] || [ -z "$CC_RESOLVED" ]; then
    echo "CLAUDE_CLI_CHECK_FAILED (offline or npm probe failed) — kept installed: ${CC_INSTALLED:-unknown}"
  elif [ "$CC_INSTALLED" = "$CC_RESOLVED" ]; then
    if [ -n "$CC_REGISTRY" ] && [ "$CC_RESOLVED" != "$CC_REGISTRY" ]; then
      echo "CLAUDE_CLI_HELD (installed $CC_INSTALLED; registry $CC_REGISTRY held by your npm min-release-age policy)"
    else
      echo "CLAUDE_CLI_CURRENT ($CC_INSTALLED)"
    fi
  else
    echo "UPDATING_CLAUDE_CLI ($CC_INSTALLED -> $CC_RESOLVED)"
    # Capture the installer exit status DIRECTLY — never through a pipe (see the
    # Salesforce block above for why `| tail-1` masked failures).
    CC_LOG=$(mktemp "${TMPDIR:-/tmp}/scout-cc-install.XXXXXX")
    npm install @anthropic-ai/claude-code --global > "$CC_LOG" 2>&1; CC_RC=$?
    tail -1 "$CC_LOG"; rm -f "$CC_LOG"
    # Version-probe output + exit code captured separately; parse only a supported
    # leading `<semver>` (claude --version prints e.g. `1.2.3 (Claude Code)`), and
    # only on a successful probe.
    CC_VER_OUT=$(claude --version 2>/dev/null); CC_VER_RC=$?
    CC_AFTER=""
    if [ "$CC_VER_RC" -eq 0 ]; then
      CC_AFTER=$(printf '%s\n' "$CC_VER_OUT" | sed -nE 's/^([0-9]+\.[0-9]+\.[0-9]+)( \(Claude Code\))?$/\1/p')
    fi
    if [ "$CC_RC" -ne 0 ]; then
      if [ -n "$CC_AFTER" ]; then
        echo "CLAUDE_CLI_UPDATE_FAILED (npm exit $CC_RC; version now reports $CC_AFTER — install may be partially applied)"
      else
        echo "CLAUDE_CLI_UPDATE_FAILED (npm exit $CC_RC; post-install version could not be verified)"
      fi
    elif [ "$CC_VER_RC" -ne 0 ] || [ -z "$CC_AFTER" ]; then
      echo "CLAUDE_CLI_UPDATE_UNVERIFIED (install exit 0 but the version probe failed or returned no supported version)"
    elif [ "$CC_AFTER" = "$CC_RESOLVED" ]; then
      echo "CLAUDE_CLI_UPDATED ($CC_INSTALLED -> $CC_AFTER)"
    elif [ "$CC_AFTER" = "$CC_INSTALLED" ]; then
      echo "CLAUDE_CLI_UPDATE_NOOP (install exit 0 but version unchanged — still $CC_AFTER)"
    else
      echo "CLAUDE_CLI_UPDATE_MISMATCH (install exit 0; observed $CC_AFTER, expected $CC_RESOLVED)"
    fi
  fi
fi
