# Scout Setup — Refresh

Workspace already configured. Apply `prompts/host-runtime.md`.

On Codex and Cursor run a.0, the Salesforce CLI ownership/update check a, and
`${CLAUDE_PLUGIN_ROOT}/prompts/setup/other-hosts.md` in place of b.5 and c.6.
Skip b: it reports on Claude. Use the host's own updater and configuration
controls; on a clone of Scout, offer `git -C "[PLUGIN_ROOT]" pull --ff-only` for
Scout's folder and for the official skills clone, each on the SE's yes. Unknown host must return before
any setup writes. On Claude, run the complete procedure below; in a self-repair
run, ask its one question first (`skills/scout-setup/SKILL.md`).

Refresh changes nothing outside Scout's own files except what a step below names:
it never edits shell files such as `~/.zshrc`, other tools' hooks or settings,
or permission rules in `~/.claude/settings.json`.

**Idempotency contract:** every step below is idempotent and self-detecting. Re-running after an SE-chosen `/mcp` action is safe — setup re-observes MCP status without modifying connections, and completed steps keep their no-op probes. Always run end-to-end; do NOT skip steps trying to "resume". Within the same CC session you may rely on conversation memory to fast-forward; across sessions, run the full sequence.

## a.0: Node toolchain probe (npm presence)

Some machines run a standalone Node with no `npm` on PATH. Without npm, the CLI version checks below can't run.

```bash
npm --version
```

A version number means `NPM_PRESENT`; an error such as "not found" or "not recognized" means `NPM_ABSENT`. The command is the same in every shell.

- `NPM_ABSENT`: **skip step a**; still run b for the read-only running-client report. Note that npm isn't on the PATH, so Scout can't prove npm owns the Salesforce CLI and skips its update check. This doesn't say how the CLI was installed, and it isn't an error.
- `NPM_PRESENT`: silent.

## a: Update Salesforce CLI (only if behind latest)

**Skip this step if a.0 reported `NPM_ABSENT`.**

The shipped helper reinstalls the global `sf` CLI only when this npm provably owns the active executable and it's behind the newest installable version, so the usual refresh is a true no-op. An unconditional reinstall churns the binary and can orphan the keychain-backed org logins across a Node rebuild; the SE then sees an empty org list.

Before running it, resolve this active Scout plugin installation's root from the current plugin context to a concrete absolute path, and substitute it for `/absolute/path/of/active/sf-demo-scout` below. Don't pass a literal `${CLAUDE_PLUGIN_ROOT}` to the shell, and don't search for or guess another cached plugin version. If it can't be resolved or the shipped script is missing (Python then can't open the file), surface `CLI_REFRESH_UNAVAILABLE`, skip the CLI update and continue setup; don't reconstruct the helper in the conversation.

```bash
python3 -B "/absolute/path/of/active/sf-demo-scout/scripts/setup_cli_refresh.py" sf
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

Then run the read-only model-routing report:

```bash
SCOUT_HOST=claude python3 -B "/absolute/path/of/active/sf-demo-scout/scripts/setup-model-report.py"
```

It reads settings files, the session environment, literal `.zshrc` assignments, VS Code and launchctl values, and changes none of them. Carry each reported older model's source and its provider-specific fix into the done summary verbatim; don't invent model IDs.

Every outcome continues setup; none aborts it. Pass every outcome line from steps a and b to the done step unchanged, including the running-client, floor and model-routing lines: `done.md` reports them.

## b.5: Salesforce's official plugins

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/official-plugins.md` and execute it. Carry its non-silent lines into the done summary.

## c.6: Salesforce Docs MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/salesforce-docs-mcp.md` and execute its read-only readiness check. Never infer absence from list output or auto-register a replacement.

Scout registers no other connection. Slack, Google Drive and similar tools come from the SE's own host connectors, if any; the done message carries the heads-up note about them.

## Done

Refresh procedure complete. Return to the orchestrator with every CLI and report outcome line from steps a and b, and the Docs MCP status line (registration and transport observations only, never proof of authentication or tool capability).
