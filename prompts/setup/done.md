# Scout Setup — Done

Compose the closing message from what the orchestrator passes: `STATE` (`FRESH` or `REFRESH`), every CLI and report outcome line and the Docs MCP status note. Read `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json` and extract `version`.

The message is one readiness result, then only the follow-ups below that apply. A check that came back current or silent gets no line.

## Readiness result

On Codex and Cursor, describe the verified workspace setup or refresh and the actual CLI and provider outcomes, and say to start a new chat after updating Scout (on Codex, restart the app to fetch the update). Skip the Claude-tab, Opus and model-routing notices for the Claude steps that didn't run. Workspace readiness doesn't establish optional MCP readiness. The wording below applies only to Claude.

**If STATE was FRESH:** "✓ Scout is set up and ready. Workspace at `~/claude-projects/sf-demo-scout/`. Run `/scout` next to spar on or build a demo, naming your demo org; connect the org first if it isn't yet."

**If STATE was REFRESH:** "✓ Scout refreshed to v[VERSION]. Close and reopen this Claude tab to pick up updated commands; in VS Code, restart VS Code if the new tab still feels stale."

When the official-plugins step's last line is `OFFICIAL_READINESS blocked …`, or it printed no `OFFICIAL_READINESS` line at all, say instead that Scout is set up (or refreshed), but building needs Salesforce's official plugins: see the note below. That step's lines are the note. When it reported `restart=needed`, end with "Run `/reload-plugins` (or restart Claude Code) before building."

## Follow-ups

**Connected tools, every time, one short line:** "Scout can use whatever your coding tool has connected, such as Slack or Google Drive. Check what's connected in your environment: when you ask Scout to look something up, it may read from those tools."

**Salesforce CLI outcome (REFRESH):** one plain line when its outcome isn't `SF_CLI_CURRENT`, using the versions its outcome line observed. The outcome token is the truth: never the `->` target, and never the fact that an install command ran.
- `SF_CLI_UPDATED (X -> Y)`: updated to the observed `Y`.
- `SF_CLI_HELD`: a newer version exists, but the builder's npm `min-release-age` policy holds it back on purpose, and it installs on a future refresh. Name the kept version. Not an error.
- `SF_CLI_UPDATE_NOOP` or `SF_CLI_CHECK_FAILED`: couldn't confirm it's on the newest version; name the version it reports. Not an update.
- `SF_CLI_UPDATE_FAILED`: "The Salesforce CLI update didn't complete (installer error); it'll retry on a future refresh." Then "It currently reports [version]." if a version was observed, else "Its current version couldn't be verified." Never say the prior install is intact: a failed install may be partial.
- `SF_CLI_UPDATE_UNVERIFIED`: couldn't verify the version after the update. Never report it as updated.
- `SF_CLI_UPDATE_MISMATCH`: it now reports [observed], but [target] was expected, so it's worth a check. Don't imply the target was reached.
- `SF_CLI_NOT_NPM_OWNED`: the active executable belongs to another installation, so Scout left it to that installation's updater. Not an error.
- `SF_CLI_OWNERSHIP_UNVERIFIED`: Scout couldn't prove npm owns the active CLI, so it skipped the update. Name no installer.
- `SF_CLI_WINDOWS_INSTALLER`: the Salesforce CLI here is the Windows installer's copy, so Scout skipped its update. Scout's own steps still work with it, but its launcher sits in a folder with a space, and a quoted argument in the coding tool's own `sf` calls breaks it (`'C:\Program' is not recognized`). The fix: uninstall **Salesforce CLI** in Settings → Apps (saved logins stay), then run `npm.cmd install --global @salesforce/cli` in a new PowerShell window, and quit and reopen the app. Not an error; one note.
- `CLI_REFRESH_UNAVAILABLE`, `NPM_ABSENT`: the note `refresh.md` gives for it.

**Running client (Claude):** when setup printed a floor notice or couldn't verify the running client, give the running client's observed version or why it's unverified, with any floor notice and its provider-specific advice. Setup doesn't update Claude Code, and a CLI updated on PATH doesn't establish that the desktop or IDE client updated.

**Model routing:** setup's read-only model report, as the step that ran it says. It changes nothing, so it never needs a restart note.

**Auto-update:** when setup reported `AUTOUPDATE_LEFT_AS_CHOSEN`, its one line.

**Self-repair:** after a run Scout started itself, one line on what it repaired. If the builder said no to the held steps, name each as skipped, with `/scout-setup` to run them any time.

**Docs MCP connection:** for a status other than `registration=registered transport=connected`, one short note using the Docs fragment's guidance. A connected status describes transport only: never call it authenticated, or say its tools work, before discovery and the first real use.
