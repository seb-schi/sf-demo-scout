# Scout Setup — Refresh

Workspace already configured. Update CLIs, sync skills, refresh `.zshrc` block, bump config version.

**Idempotency contract:** every step below is idempotent and self-detecting. Re-running after an abort (e.g. SE returning from `/mcp` Slack auth) is safe and fast — completed steps fast-no-op via their own probes (`SLACK_MCP_ALREADY_REGISTERED`, `ZSHRC_UNCHANGED`, etc.). Always run end-to-end; do NOT skip steps trying to "resume" — the no-ops are the resume mechanism. Within the same CC session you may rely on conversation memory to fast-forward; across sessions, just run the full sequence — it will land in the right place naturally.

## a: Update Salesforce CLI (only if behind latest)

Reinstall the global `sf` CLI ONLY when the installed version is behind the
latest published version. An unconditional `npm install --global` on every
refresh churns the global binary needlessly and can orphan the keychain-backed
org-auth token across a node rebuild — the SE then sees an empty/stale org list
and assumes their connections were lost (the auth files in `~/.sfdx` are never
actually deleted). Version-gating makes the common no-op case a true no-op.

```bash
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
  npm install @salesforce/cli --global 2>&1 | tail -1
  SF_AFTER=$(sf --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
  if [ "$SF_AFTER" = "$SF_INSTALLED" ]; then
    echo "SF_CLI_UPDATE_NOOP (install ran but version unchanged — still $SF_AFTER)"
  else
    echo "SF_CLI_UPDATED ($SF_INSTALLED -> $SF_AFTER)"
  fi
fi
```

## b: Update Claude Code CLI (only if behind latest)

Same version-gate rationale as step a — reinstall only when behind latest.

```bash
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
  npm install @anthropic-ai/claude-code --global 2>&1 | tail -1
  CC_AFTER=$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
  if [ "$CC_AFTER" = "$CC_INSTALLED" ]; then
    echo "CLAUDE_CLI_UPDATE_NOOP (install ran but version unchanged — still $CC_AFTER)"
  else
    echo "CLAUDE_CLI_UPDATED ($CC_INSTALLED -> $CC_AFTER)"
  fi
fi
```

Surface inline (report the OBSERVED outcome token, never the `->` target — the
token is computed from the actual post-install version, so it is the source of
truth; do not infer "updated" from the fact that an install command ran):
- `SF_CLI_CURRENT` / `CLAUDE_CLI_CURRENT` — silent (already on the newest installable version; the common case).
- `SF_CLI_UPDATED (X -> Y)` / `CLAUDE_CLI_UPDATED (X -> Y)` — one-line note that the CLI was updated, using the observed `Y`.
- `SF_CLI_HELD` / `CLAUDE_CLI_HELD` — one-line note: a newer version exists in the registry but the SE's npm `min-release-age` policy is intentionally holding it back; this is NOT an error — it will install on a future refresh once the release ages past the policy window. Name the installed version that was kept.
- `SF_CLI_UPDATE_NOOP` / `CLAUDE_CLI_UPDATE_NOOP` — one-line note: the install ran but the version didn't change; kept the installed version (rare — npm cache/policy edge). Don't claim an update.
- `SF_CLI_CHECK_FAILED` / `CLAUDE_CLI_CHECK_FAILED` — one-line note ("couldn't check [sf|claude] CLI version — kept the installed one"), proceed.
- If an `npm install` that DID run fails (non-zero exit), surface a one-line note ("[sf|claude] CLI update failed — continuing") and proceed. Don't abort.

## c: Slack MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/slack-mcp.md` and execute it with `mode=soft`. The prompt handles registration heal + auth probe; in soft mode failures surface notes and continue (heal-when-broken semantics). The `SLACK_MCP_REGISTERED` branch still returns (TUI snapshot needs `/reload-plugins`).

## c.5: Google Workspace MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/google-mcp.md` and execute it with `mode=soft`. Heals the registration if the binary is present; surfaces a note and returns if the `mcp-adaptor` binary is absent or auth is pending. Never aborts.

## d: Refresh .zshrc managed block

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/zshrc-block.md` and execute it. Capture the result (`ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED`, plus optional `ANTHROPIC_MODEL_PRESENT`) — the orchestrator's done step needs it.

## d.7: Strip stale model pins across all surfaces (self-heal)

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/model-pin-strip.md` and execute its procedure. It removes stale model pins (`ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL` + `modelOverrides`) and the two retired knobs (`MAX_THINKING_TOKENS`, `CLAUDE_CODE_MAX_OUTPUT_TOKENS`) from the two `~/.claude` settings JSON files, VS Code's user settings (JSONC, backup/validate/restore), and launchctl GUI env — freeing the `/model` picker and clearing the output-length value Scout used to set. The `.zshrc` surface is handled by step d (`zshrc-block.md` sweeps these as out-of-block stragglers). Idempotent, safe-fail, never aborts. Carry any `PINS_REMOVED[...]` / `VSCODE_PINS_REMOVED` / `LAUNCHCTL_PINS_CLEARED` / VS-Code-restore-or-warn result into the done summary — the SE has a restart (and possibly a manual VS Code edit) pending.

## d.8: Scrub stale AI-Suite hooks (self-heal)

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/aisuite-scrub.md` and execute its procedure. It removes only `~/.aisuite/`-rooted hook entries (which throw every turn once AI Suite is uninstalled) from the two `~/.claude` settings JSON files, and surfaces — without touching — any leftover aisuite cert path or plugin/marketplace config. Idempotent, safe-fail, never aborts. If it emitted any `AISUITE_HOOKS_REMOVED` or `FLAGS`, carry that note into the done summary (a hook removal means a CC restart is pending).

## Done

Refresh procedure complete. Return to the orchestrator. Pass the result of step d (`ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED`, plus optional `ANTHROPIC_MODEL_PRESENT`) so the done message can include the shell-refresh note. Also pass the CLI outcome tokens from steps a and b (`*_CURRENT` / `*_UPDATED (X->Y)` / `*_HELD` / `*_UPDATE_NOOP` / `*_CHECK_FAILED`) so the done message reflects actual CLI status rather than asserting "current" unconditionally. If d.7 emitted any `PINS_REMOVED[...]`, `VSCODE_PINS_REMOVED`, `LAUNCHCTL_PINS_CLEARED`, or a VS-Code-restore/warn variant, the SE has a restart (and possibly a manual VS Code edit) pending — make sure that note survived into the done summary.
