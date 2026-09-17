# Scout Setup — Done

Compose the closing message. The orchestrator passes you two pieces of context:
- `STATE` — `FRESH` or `REFRESH`
- `ZSHRC_MODIFIED` — boolean (true if step j / step d reported `ZSHRC_MODIFIED`)

Read `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json` and extract `version`.

## Compose

**If STATE was FRESH:**

> "✓ Scout is set up and ready. Workspace at `~/claude-projects/sf-demo-scout/`.
>
> FYI — run `/scout-sparring` next to start a demo; if no org is connected yet, it'll offer to connect one for you."

**If STATE was REFRESH:**

> "✓ Scout refreshed to v[VERSION].
>
> **Close + reopen this Claude tab** to pick up any updated commands. (If running in VS Code and the new tab still feels stale, fully restart VS Code.) Then continue your work."

(The CLI status line, if any, is appended below from the step a/b outcome tokens — do NOT assert "CLIs current" here, since the policy-held case is current-by-policy but not registry-latest.)

## Append (any branch)

**If `ZSHRC_MODIFIED` is true:** append before the close:

> "Note: Scout tidied its block in your `~/.zshrc` — it no longer sets any environment variables there. Open a new terminal window for non-Claude-Code shell sessions to pick up the change — current Claude Code session is unaffected."

**If STATE was REFRESH:** compose at most one CLI status line from the step a/b outcome tokens and append before the close (skip entirely if both CLIs were `*_CURRENT` — the refresh line already implies current):

> - Any `*_UPDATED (X -> Y)` — "Updated [Salesforce CLI / Claude Code] to [Y]."
> - Any `*_HELD` — "Note: a newer [Claude Code / Salesforce CLI] ([registry version]) is available, but your npm `min-release-age` policy is holding it back for now — it'll install automatically on a future refresh once it ages past your policy window. Kept [installed version]."
> - Any `*_UPDATE_NOOP` or `*_CHECK_FAILED` — "Couldn't confirm [Salesforce CLI / Claude Code] is on the newest version — kept the installed one ([version])."
> - Any `*_UPDATE_FAILED` — "The [Salesforce CLI / Claude Code] update didn't complete (installer error) — it'll retry on a future refresh." (If a version was observed, add "It currently reports [version]."; otherwise add "Its current version couldn't be verified." — do NOT claim the prior install is intact.)
> - Any `*_UPDATE_UNVERIFIED` — "Couldn't verify the [Salesforce CLI / Claude Code] version after the update — continuing; it'll re-check on a future refresh."
> - Any `*_UPDATE_MISMATCH` — "Heads-up: [Salesforce CLI / Claude Code] now reports [observed], but [target] was expected — worth a quick check."
> - Any `*_NOT_NPM_OWNED` — "Scout left [Salesforce CLI / Claude Code] unchanged because the active executable belongs to another installation; use that installation's updater."
> - Any `*_OWNERSHIP_UNVERIFIED` — "Scout couldn't prove that npm owns the active [Salesforce CLI / Claude Code], so it safely skipped the update."

If an MCP status was not `registration=registered transport=connected`, append
one concise readiness note using the provider fragment's guidance. Even a
connected status describes transport only: never call it authenticated or claim
its required tools work before discovery and the first real use.

**If STATE was REFRESH and `ZSHRC_MODIFIED` is true:** also append before the close:

> "Heads-up: Scout no longer manages model selection. Any `ANTHROPIC_DEFAULT_*_MODEL` exports it previously set in your shell have been removed, and Scout no longer pins a default model in `~/.claude/settings.json` — pick whatever model you want with `/model` (the `/scout-sparring` and `/scout-building` commands will remind you to switch to Opus when you run them)."
