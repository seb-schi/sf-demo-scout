# Scout Setup — Refresh

Workspace already configured. Apply `prompts/host-runtime.md`.

On Codex run a.0, the Salesforce CLI ownership/update check a, and the provider
checks c/c.5/c.6. Skip b and every d step: those report on or repair Claude and
its shell integration. Return `ZSHRC_UNCHANGED`; use Codex's own updater and
configuration controls. Unknown host must return before any setup writes.
On Claude, run the complete procedure below; in a self-repair run, ask its one question first (`commands/scout-setup.md`).

**Idempotency contract:** every step below is idempotent and self-detecting. Re-running after an SE-chosen `/mcp` action is safe — setup re-observes MCP status without modifying connections, and completed repair steps retain their existing no-op probes (`ZSHRC_UNCHANGED`, etc.). Always run end-to-end; do NOT skip steps trying to "resume". Within the same CC session you may rely on conversation memory to fast-forward; across sessions, run the full sequence.

## a.0: Node toolchain probe (npm presence)

Some machines run a standalone Node with no `npm` on PATH. Without npm, the CLI version checks below can't run.

```bash
command -v npm >/dev/null 2>&1 && echo "NPM_PRESENT" || echo "NPM_ABSENT"
```

- `NPM_ABSENT`: **skip step a**; still run b for the read-only running-client report. Note that npm isn't on the PATH, so Scout can't prove npm owns the Salesforce CLI and skips its update check. This doesn't say how the CLI was installed, and it isn't an error.
- `NPM_PRESENT`: silent.

## a: Update Salesforce CLI (only if behind latest)

**Skip this step if a.0 reported `NPM_ABSENT`.**

The shipped helper reinstalls the global `sf` CLI only when this npm provably owns the active executable and it's behind the newest installable version, so the usual refresh is a true no-op. An unconditional reinstall churns the binary and can orphan the keychain-backed org logins across a Node rebuild; the SE then sees an empty org list.

Before invoking Bash, resolve this active Scout plugin installation's root from the current plugin context to a concrete absolute path, and substitute it below. Don't pass a literal `${CLAUDE_PLUGIN_ROOT}` to the shell, and don't search for or guess another cached plugin version. If it can't be resolved or the shipped script is missing, surface `CLI_REFRESH_UNAVAILABLE`, skip the CLI update and continue setup; don't reconstruct the helper in the conversation.

```bash
SCOUT_CLI_REFRESH_SCRIPT="/absolute/path/of/active/sf-demo-scout/scripts/setup-cli-refresh.sh"
if [ ! -f "$SCOUT_CLI_REFRESH_SCRIPT" ]; then
  echo "CLI_REFRESH_UNAVAILABLE: shipped script not found at $SCOUT_CLI_REFRESH_SCRIPT"
else
  /bin/bash "$SCOUT_CLI_REFRESH_SCRIPT" sf
fi
```

## b: Report the running Claude Code client

Claude Code's native installs and the desktop app update themselves, so setup doesn't update Claude Code. Report the client this session runs on, and whether it meets Scout's floor (the floor notice says how to update), with the same root resolution as step a. Run it even if a.0 reported `NPM_ABSENT`.

```bash
SCOUT_CLIENT_VERSION="/absolute/path/of/active/sf-demo-scout/scripts/client-version.py"
if [ -f "$SCOUT_CLIENT_VERSION" ] && command -v python3 >/dev/null 2>&1; then
  SCOUT_HOST=claude python3 -B "$SCOUT_CLIENT_VERSION" setup
else
  echo "Running Claude client binary: unverified — Python or the shipped helper is unavailable"
fi
```

Every outcome continues setup; none aborts it. Pass every outcome line from steps a and b to the done step unchanged, including the running-client and floor lines: `done.md` reports them.

## b.5: Salesforce's official plugins

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/official-plugins.md` and execute it. Carry its non-silent lines into the done summary.

## c: Slack MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/slack-mcp.md` and execute its read-only readiness check. It preserves every existing or possibly omitted registration and never auto-registers or authenticates.

## c.5: Google Workspace MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/google-mcp.md` and execute its read-only readiness check. The adaptor prerequisite is checked only when offering the historical default for an explicit SE choice.

## c.6: Salesforce Docs MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/salesforce-docs-mcp.md` and execute its read-only readiness check. Never infer absence from list output or auto-register a replacement.

## d: Refresh .zshrc managed block

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/zshrc-block.md` and execute it. Capture the result (`ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED`, plus optional `ANTHROPIC_MODEL_PRESENT`) — the orchestrator's done step needs it.

## d.7: Preserve model routing and clean retired Scout settings

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/model-pin-strip.md` and execute its procedure (the fragment carries the full "why"; the `.zshrc` surface is handled by step d and preserves model mappings). Carry any cleanup or preservation result into the done summary — only an actual settings change needs a restart note.

## d.8: Scrub stale AI-Suite hooks (self-heal)

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/aisuite-scrub.md` and execute its procedure (the fragment carries the full "why"). If it emitted any `AISUITE_HOOKS_REMOVED` or `FLAGS`, carry that note into the done summary — a hook removal means a CC restart is pending.

## Done

Refresh procedure complete. Return to the orchestrator with step d's result (`ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED`, plus optional `ANTHROPIC_MODEL_PRESENT`), every CLI outcome line from steps a and b, the three MCP status lines (registration and transport observations only, never proof of authentication or tool capability), and d.7's preservation flags and actual cleanup results.
