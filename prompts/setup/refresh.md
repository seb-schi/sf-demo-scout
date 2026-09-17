# Scout Setup — Refresh

Workspace already configured. Update CLIs, sync skills, refresh `.zshrc` block, bump config version.

**Idempotency contract:** every step below is idempotent and self-detecting. Re-running after an abort (e.g. SE returning from `/mcp` Slack auth) is safe and fast — completed steps fast-no-op via their own probes (`SLACK_MCP_ALREADY_REGISTERED`, `ZSHRC_UNCHANGED`, etc.). Always run end-to-end; do NOT skip steps trying to "resume" — the no-ops are the resume mechanism. Within the same CC session you may rely on conversation memory to fast-forward; across sessions, just run the full sequence — it will land in the right place naturally.

## a.0: Node toolchain probe (npm / npx presence)

Some machines run a DevBar/standalone-provided Node with no `npm`/`npx` on PATH.
That silently breaks two things: the CLI version gates below (steps a, b) probe via
`npm` and misreport its absence as "offline"; and the Salesforce DX MCP server —
declared in `plugin.json` as `npx -y @salesforce/mcp` — fails to launch every
session with `ENOENT: npx not found`. Probe both up front so the messages are
accurate.

```bash
command -v npm >/dev/null 2>&1 && echo "NPM_PRESENT" || echo "NPM_ABSENT"
command -v npx >/dev/null 2>&1 && echo "NPX_PRESENT" || echo "NPX_ABSENT"
```

- `NPM_ABSENT` — **skip steps a and b entirely** (do not run the CLI version gates;
  with no npm they only produce a false "offline" reading). Surface: "npm isn't on
  your PATH — Node here looks DevBar/standalone-provided. Skipping the `sf`/`claude`
  CLI update checks: neither is npm-managed on this machine (`sf` comes from AI
  Suite, `claude` self-updates natively), so there's nothing for npm to update. Not
  an error."
- `NPX_ABSENT` — surface a warning (does NOT block setup): "⚠️ `npx` isn't on your
  PATH, but the Salesforce DX MCP server launches via `npx -y @salesforce/mcp`. It
  will fail to start each session (`ENOENT: npx not found`), so the DX MCP
  metadata/SOQL/deploy tools won't be available — Scout falls back to the `sf` CLI
  where it can. To restore the MCP: install a Node that bundles npm/npx (e.g. `brew
  install node`) and make sure it precedes the DevBar Node on your PATH, then restart
  Claude Code."
- `NPM_PRESENT` / `NPX_PRESENT` — silent; proceed.

## a: Update Salesforce CLI (only if behind latest)

**Skip this step if a.0 reported `NPM_ABSENT`.**

Reinstall the global `sf` CLI ONLY when the installed version is behind the
latest published version. An unconditional `npm install --global` on every
refresh churns the global binary needlessly and can orphan the keychain-backed
org-auth token across a node rebuild — the SE then sees an empty/stale org list
and assumes their connections were lost (the auth files in `~/.sfdx` are never
actually deleted). Version-gating makes the common no-op case a true no-op.

Before invoking Bash, resolve this active Scout plugin installation's root from
the current plugin context to a concrete absolute path. Do not pass a literal
`${CLAUDE_PLUGIN_ROOT}` to the shell and do not search for or guess another
cached plugin version. Substitute the resolved absolute path below. If it cannot
be resolved or the shipped script is missing, surface `CLI_REFRESH_UNAVAILABLE`,
skip both CLI update steps, and continue setup; do not reconstruct the
implementation in the conversation.

```bash
SCOUT_CLI_REFRESH_SCRIPT="/absolute/path/of/active/sf-demo-scout/scripts/setup-cli-refresh.sh"
if [ ! -f "$SCOUT_CLI_REFRESH_SCRIPT" ]; then
  echo "CLI_REFRESH_UNAVAILABLE: shipped script not found at $SCOUT_CLI_REFRESH_SCRIPT"
else
  /bin/bash "$SCOUT_CLI_REFRESH_SCRIPT" sf
fi
```

## b: Update Claude Code CLI (only if behind latest)

**Skip this step if a.0 reported `NPM_ABSENT`.**

Same version-gate rationale as step a — reinstall only when behind latest.

```bash
SCOUT_CLI_REFRESH_SCRIPT="/absolute/path/of/active/sf-demo-scout/scripts/setup-cli-refresh.sh"
if [ ! -f "$SCOUT_CLI_REFRESH_SCRIPT" ]; then
  echo "CLI_REFRESH_UNAVAILABLE: shipped script not found at $SCOUT_CLI_REFRESH_SCRIPT"
else
  /bin/bash "$SCOUT_CLI_REFRESH_SCRIPT" claude
fi
```

Surface inline (report the OBSERVED outcome token, never the `->` target — the
token is computed from the actual post-install version, so it is the source of
truth; do not infer "updated" from the fact that an install command ran):
- `SF_CLI_CURRENT` / `CLAUDE_CLI_CURRENT` — silent (already on the newest installable version; the common case).
- `SF_CLI_UPDATED (X -> Y)` / `CLAUDE_CLI_UPDATED (X -> Y)` — one-line note that the CLI was updated, using the observed `Y`.
- `SF_CLI_HELD` / `CLAUDE_CLI_HELD` — one-line note: a newer version exists in the registry but the SE's npm `min-release-age` policy is intentionally holding it back; this is NOT an error — it will install on a future refresh once the release ages past the policy window. Name the installed version that was kept.
- `SF_CLI_UPDATE_NOOP` / `CLAUDE_CLI_UPDATE_NOOP` — one-line note: the install ran (exit 0) but the version didn't change; kept the installed version (rare — npm cache/policy edge). Don't claim an update.
- `SF_CLI_UPDATE_FAILED` / `CLAUDE_CLI_UPDATE_FAILED` — the installer exited non-zero. Surface a one-line note ("[sf|claude] CLI update didn't complete (installer error) — it'll retry on a future refresh"), proceed. Don't abort, don't claim an update, and don't assert the prior install is intact — if a version was observed, report it verbatim ("now reports [version]"); otherwise say the version couldn't be verified.
- `SF_CLI_UPDATE_UNVERIFIED` / `CLAUDE_CLI_UPDATE_UNVERIFIED` — install exited 0 but the post-install version probe failed or returned no supported version. One-line note ("couldn't verify the [sf|claude] CLI version after the update — continuing"). Never report UPDATED off an unverified probe.
- `SF_CLI_UPDATE_MISMATCH` / `CLAUDE_CLI_UPDATE_MISMATCH` — install exited 0 and a valid version was observed, but it is neither the prior version nor the resolved target. One-line note naming both ("[sf|claude] CLI now reports [observed], expected [target] — surfaced for you to check"). Don't imply the target was reached.
- `SF_CLI_CHECK_FAILED` / `CLAUDE_CLI_CHECK_FAILED` — one-line note ("couldn't check [sf|claude] CLI version — kept the installed one"), proceed.

## c: Slack MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/slack-mcp.md` and execute it. The prompt handles registration heal + auth probe; failures surface notes and continue (heal-when-broken semantics). The `SLACK_MCP_REGISTERED` branch still returns (TUI snapshot needs `/reload-plugins`).

## c.5: Google Workspace MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/google-mcp.md` and execute it. Heals the registration if the binary is present; surfaces a note and returns if the `mcp-adaptor` binary is absent or auth is pending. Never aborts.

## c.6: Salesforce Docs MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/salesforce-docs-mcp.md` and execute it. Heals the user-scope registration (idempotent — no-ops if already present); surfaces the manual command and returns on failure. Never aborts. This is the migration vehicle for existing installs whose Docs server was the old broken plugin-manifest one — the manifest declaration is gone on update, and this re-registers it at user scope.

## d: Refresh .zshrc managed block

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/zshrc-block.md` and execute it. Capture the result (`ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED`, plus optional `ANTHROPIC_MODEL_PRESENT`) — the orchestrator's done step needs it.

## d.7: Strip stale model pins across all surfaces (self-heal)

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/model-pin-strip.md` and execute its procedure (the fragment carries the full "why"; the `.zshrc` surface is handled by step d, where `zshrc-block.md` sweeps these keys as out-of-block stragglers). Carry any `PINS_REMOVED[...]` / `VSCODE_PINS_REMOVED` / `LAUNCHCTL_PINS_CLEARED` / VS-Code-restore-or-warn result into the done summary — the SE has a restart (and possibly a manual VS Code edit) pending.

## d.75: Repair stale MCP tool-name prefixes (self-heal)

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/repair-mcp-prefixes.py"`. Scout's allowlists shipped with unnamespaced MCP prefixes (`mcp__Salesforce_DX__*`) until 2026-07-27; plugin-provided MCP tools are actually namespaced `mcp__plugin_sf-demo-scout_<Server_Name>__<tool>`, so those entries matched nothing. The script rewrites them in place in the workspace and user-scope settings files. Idempotent, safe-fail, never aborts.

Surface inline:
- `MCP_PREFIX_OK` — silent.
- `MCP_PREFIX_FIXED <file>: N` — "Repaired N stale MCP tool-name entries in `<file>` (restart pending)."
- Any `MCP_PREFIX_SKIP` / `MCP_PREFIX_WRITE_FAILED` — one-line note, proceed.

## d.8: Scrub stale AI-Suite hooks (self-heal)

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/aisuite-scrub.md` and execute its procedure (the fragment carries the full "why"). If it emitted any `AISUITE_HOOKS_REMOVED` or `FLAGS`, carry that note into the done summary — a hook removal means a CC restart is pending.

## Done

Refresh procedure complete. Return to the orchestrator. Pass the result of step d (`ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED`, plus optional `ANTHROPIC_MODEL_PRESENT`) so the done message can include the shell-refresh note. Also pass the CLI outcome tokens from steps a and b (`*_CURRENT` / `*_UPDATED (X->Y)` / `*_HELD` / `*_UPDATE_NOOP` / `*_CHECK_FAILED`) so the done message reflects actual CLI status rather than asserting "current" unconditionally. If d.7 emitted any `PINS_REMOVED[...]`, `VSCODE_PINS_REMOVED`, `LAUNCHCTL_PINS_CLEARED`, or a VS-Code-restore/warn variant, the SE has a restart (and possibly a manual VS Code edit) pending — make sure that note survived into the done summary.
