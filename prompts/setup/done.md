# Scout Setup — Done

Compose the closing message from what the orchestrator passes: `STATE` (`FRESH` or `REFRESH`), `ZSHRC_MODIFIED` (true if step j or step d reported it), every CLI outcome line and the optional MCP status notes. Read `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json` and extract `version`.

The message is one readiness result, then only the follow-ups below that apply. A check that came back current or silent gets no line.

## Readiness result

On Codex, describe the verified workspace setup or refresh and the actual CLI and provider outcomes, and say to start a fresh Codex task after updating the installed plugin. Skip the Claude-tab, Opus, model-pin and shell-repair notices for the Claude steps that didn't run. Workspace readiness doesn't establish DX or optional MCP readiness. The wording below applies only to Claude.

**If STATE was FRESH:** "✓ Scout is set up and ready. Workspace at `~/claude-projects/sf-demo-scout/`. Run `/scout` next to spar on or build a demo, naming your demo org; connect the org first if it isn't yet."

**If STATE was REFRESH:** "✓ Scout refreshed to v[VERSION]. Close and reopen this Claude tab to pick up updated commands; in VS Code, restart VS Code if the new tab still feels stale."

When the official-plugins step's last line is `OFFICIAL_READINESS blocked …`, or it printed no `OFFICIAL_READINESS` line at all, say instead that Scout is set up (or refreshed), but building needs Salesforce's official plugins: see the note below. That step's lines are the note. When it reported `restart=needed`, end with "Run `/reload-plugins` (or restart Claude Code) before building."

## Follow-ups

**If `ZSHRC_MODIFIED` is true:** "Scout tidied its block in your `~/.zshrc`: it no longer sets environment variables there, and `~/.local/bin` is on your PATH. For an existing file, the pre-edit backup is `~/.zshrc.scout-bak-zshrc` (beside the target if `.zshrc` is a symlink). Open a new shell to load it; this Claude Code session and already-running processes keep their current environment." `ZSHRC_MODIFIED` alone doesn't establish that model mappings exist.

**CLI outcomes (REFRESH):** one plain line for each CLI whose outcome isn't `*_CURRENT`, using the versions its outcome line observed. The outcome token is the truth: never the `->` target, and never the fact that an install command ran.
- `*_UPDATED (X -> Y)`: updated to the observed `Y`.
- `*_HELD`: a newer version exists, but the SE's npm `min-release-age` policy holds it back on purpose, and it installs on a future refresh. Name the kept version. Not an error.
- `*_UPDATE_NOOP` or `*_CHECK_FAILED`: couldn't confirm it's on the newest version; name the version it reports. Not an update.
- `*_UPDATE_FAILED`: "The [Salesforce CLI / Claude Code] update didn't complete (installer error); it'll retry on a future refresh." Then "It currently reports [version]." if a version was observed, else "Its current version couldn't be verified." Never say the prior install is intact: a failed install may be partial.
- `*_UPDATE_UNVERIFIED`: couldn't verify the version after the update. Never report it as updated.
- `*_UPDATE_MISMATCH`: it now reports [observed], but [target] was expected, so it's worth a check. Don't imply the target was reached.
- `CLAUDE_CLI_NOT_NPM_OWNED (native install updates itself; Scout left it alone)`: "Claude Code uses the native install, which updates itself; Scout left it alone."
- Other `*_NOT_NPM_OWNED`: the active executable belongs to another installation, so Scout left it to that installation's updater. Not an error.
- `*_OWNERSHIP_UNVERIFIED`: Scout couldn't prove npm owns the active CLI, so it skipped the update. Name no installer.
- `CLI_REFRESH_UNAVAILABLE`, `NPM_ABSENT`, `NPX_ABSENT`: the note `refresh.md` gives for it.

**Running client (Claude):** when setup printed a floor notice, couldn't verify the running client, or a Claude CLI install ran (`CLAUDE_CLI_UPDATED` or any `CLAUDE_CLI_UPDATE_*`), give the running client's observed version or why it's unverified, with any floor notice and its provider-specific advice. A CLI updated on PATH doesn't establish that the desktop or IDE client updated.

**Model routing:** setup's read-only model report, as `model-pin-strip.md` says. Only an actual settings change needs a restart note.

**MCP connections:** for each status other than `registration=registered transport=connected`, one short note using the provider fragment's guidance. A connected status describes transport only: never call it authenticated, or say its tools work, before discovery and the first real use.
