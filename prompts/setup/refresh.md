# Scout Setup — Refresh

Workspace already configured. Apply `prompts/host-runtime.md`.

On Codex run a.0, the Salesforce CLI ownership/update check a, and the provider
checks c/c.5/c.6. Skip b and every d step: those update or repair Claude and its
shell integration. Return `ZSHRC_UNCHANGED`; use Codex's own updater and
configuration controls. Unknown host must return before any setup writes.
On Claude, run the complete procedure below.

**Idempotency contract:** every step below is idempotent and self-detecting. Re-running after an SE-chosen `/mcp` action is safe — setup re-observes MCP status without modifying connections, and completed repair steps retain their existing no-op probes (`ZSHRC_UNCHANGED`, etc.). Always run end-to-end; do NOT skip steps trying to "resume". Within the same CC session you may rely on conversation memory to fast-forward; across sessions, run the full sequence.

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

- `NPM_ABSENT` — **skip step a**; still run b for the read-only running-client report. Surface: "npm isn't on your
  PATH, so Scout cannot prove npm owns either active CLI and will not run npm
  update checks. This does not identify how either CLI was installed; use each
  installation's own updater. Not an error."
- `NPX_ABSENT` — surface a warning (does NOT block setup): "⚠️ `npx` isn't on your
  PATH, but the Salesforce DX MCP server launches via `npx -y @salesforce/mcp`. It
  will fail to start each session (`ENOENT: npx not found`), so the DX MCP
  metadata/SOQL/deploy tools won't be available — Scout falls back to the `sf` CLI
  where it can. To restore the MCP: install a Node that bundles npm/npx (e.g. `brew
  install node`) and make sure it precedes the DevBar Node on your PATH, then start a fresh session in the active host."
- `NPM_PRESENT` / `NPX_PRESENT` — silent; proceed.

## a: Update Salesforce CLI (only if behind latest)

**Skip this step if a.0 reported `NPM_ABSENT`.**

Reinstall the global `sf` CLI ONLY when the active executable is proven to be
owned by this npm and the installed version is behind the latest installable
version. An unconditional `npm install --global` on every
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

Run even if a.0 reported `NPM_ABSENT`: the helper skips updates when ownership
cannot be proved and still reports the running client. Set `SCOUT_HOST=claude`
for this helper call after resolving the host through `host-runtime.md`.

Same ownership and version-gate rationale as step a. Native, standalone,
shadowed, malformed, or unverifiable installations are left to their own
updater and are never migrated automatically.

```bash
SCOUT_CLI_REFRESH_SCRIPT="/absolute/path/of/active/sf-demo-scout/scripts/setup-cli-refresh.sh"
if [ ! -f "$SCOUT_CLI_REFRESH_SCRIPT" ]; then
  echo "CLI_REFRESH_UNAVAILABLE: shipped script not found at $SCOUT_CLI_REFRESH_SCRIPT"
else
  SCOUT_HOST=claude /bin/bash "$SCOUT_CLI_REFRESH_SCRIPT" claude
fi
```

Surface inline (report the OBSERVED outcome token, never the `->` target — the
token is computed from the actual post-install version, so it is the source of
truth; do not infer "updated" from the fact that an install command ran):
Carry the running-client version (or its unverified reason) and any Scout floor
line into the setup message on every outcome, including current. The CLI updated
on PATH can differ from the desktop/IDE client identified by its executable path.
- `SF_CLI_CURRENT` / `CLAUDE_CLI_CURRENT` — silent (already on the newest installable version; the common case).
- `SF_CLI_UPDATED (X -> Y)` / `CLAUDE_CLI_UPDATED (X -> Y)` — one-line note that the CLI was updated, using the observed `Y`.
- `SF_CLI_HELD` / `CLAUDE_CLI_HELD` — one-line note: a newer version exists in the registry but the SE's npm `min-release-age` policy is intentionally holding it back; this is NOT an error — it will install on a future refresh once the release ages past the policy window. Name the installed version that was kept.
- `SF_CLI_UPDATE_NOOP` / `CLAUDE_CLI_UPDATE_NOOP` — one-line note: the install ran (exit 0) but the version didn't change; kept the installed version (rare — npm cache/policy edge). Don't claim an update.
- `SF_CLI_UPDATE_FAILED` / `CLAUDE_CLI_UPDATE_FAILED` — the installer exited non-zero. Surface a one-line note ("[sf|claude] CLI update didn't complete (installer error) — it'll retry on a future refresh"), proceed. Don't abort, don't claim an update, and don't assert the prior install is intact — if a version was observed, report it verbatim ("now reports [version]"); otherwise say the version couldn't be verified.
- `SF_CLI_UPDATE_UNVERIFIED` / `CLAUDE_CLI_UPDATE_UNVERIFIED` — install exited 0 but the post-install version probe failed or returned no supported version. One-line note ("couldn't verify the [sf|claude] CLI version after the update — continuing"). Never report UPDATED off an unverified probe.
- `SF_CLI_UPDATE_MISMATCH` / `CLAUDE_CLI_UPDATE_MISMATCH` — install exited 0 and a valid version was observed, but it is neither the prior version nor the resolved target. One-line note naming both ("[sf|claude] CLI now reports [observed], expected [target] — surfaced for you to check"). Don't imply the target was reached.
- `SF_CLI_CHECK_FAILED` / `CLAUDE_CLI_CHECK_FAILED` — one-line note ("couldn't check [sf|claude] CLI version — kept the installed one"), proceed.
- `CLAUDE_CLI_NOT_NPM_OWNED (native install updates itself; Scout left it alone)` — "Claude Code uses the native install, which updates itself; Scout left it alone." The helper proves this from the active executable's real path inside `$HOME/.local/share/claude/versions/`.
- Other `SF_CLI_NOT_NPM_OWNED` / `CLAUDE_CLI_NOT_NPM_OWNED` — one-line note that the active executable belongs to another installation, so Scout left it to that installation's updater. Do not call this an error.
- `SF_CLI_OWNERSHIP_UNVERIFIED` / `CLAUDE_CLI_OWNERSHIP_UNVERIFIED` — one-line note that npm ownership could not be proved, so Scout safely skipped the update. Name an installer only for the proved native-path case above; otherwise do not imply which installer owns it.

## b.5: Salesforce's official plugins

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/official-plugins.md` and execute it. Carry its non-silent lines into the done summary.

## c: Slack MCP

First read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/salesforce-dx-mcp.md` and run
its host-aware DX readiness check. Preserve its status in the setup summary.

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/slack-mcp.md` and execute its read-only readiness check. It preserves every existing or possibly omitted registration and never auto-registers or authenticates.

## c.5: Google Workspace MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/google-mcp.md` and execute its read-only readiness check. The adaptor prerequisite is checked only when offering the historical default for an explicit SE choice.

## c.6: Salesforce Docs MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/salesforce-docs-mcp.md` and execute its read-only readiness check. Never infer absence from list output or auto-register a replacement.

## d: Refresh .zshrc managed block

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/zshrc-block.md` and execute it. Capture the result (`ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED`, plus optional `ANTHROPIC_MODEL_PRESENT`) — the orchestrator's done step needs it.

## d.7: Preserve model routing and clean retired Scout settings

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/model-pin-strip.md` and execute its procedure (the fragment carries the full "why"; the `.zshrc` surface is handled by step d and preserves model mappings). Carry any cleanup or preservation result into the done summary — only an actual settings change needs a restart note.

## d.75: Repair stale MCP tool-name prefixes (self-heal)

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/repair-mcp-prefixes.py" --host claude`. Scout's allowlists shipped with unnamespaced MCP prefixes (`mcp__Salesforce_DX__*`) until 2026-07-27; plugin-provided MCP tools are actually namespaced `mcp__plugin_sf-demo-scout_<Server_Name>__<tool>`, so those entries matched nothing. The script rewrites them in place in the workspace and user-scope settings files. Idempotent, safe-fail, never aborts.

Surface inline:
- `MCP_PREFIX_OK` — silent.
- `MCP_PREFIX_FIXED <file>: N` — "Repaired N stale MCP tool-name entries in `<file>` (restart pending)."
- Any `MCP_PREFIX_SKIP` / `MCP_PREFIX_WRITE_FAILED` — one-line note, proceed.

## d.8: Scrub stale AI-Suite hooks (self-heal)

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/aisuite-scrub.md` and execute its procedure (the fragment carries the full "why"). If it emitted any `AISUITE_HOOKS_REMOVED` or `FLAGS`, carry that note into the done summary — a hook removal means a CC restart is pending.

## Done

Refresh procedure complete. Return to the orchestrator. Pass the result of step d (`ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED`, plus optional `ANTHROPIC_MODEL_PRESENT`) so the done message can include the shell-refresh note. Also pass every CLI outcome token from steps a and b, including `*_NOT_NPM_OWNED` and `*_OWNERSHIP_UNVERIFIED`, so the done message reflects the actual status. Pass all four MCP status lines as registration/transport observations only; they never prove authentication or tool capability. Carry d.7 preservation flags and actual cleanup results into the done summary; read-only mapping checks need no restart.
