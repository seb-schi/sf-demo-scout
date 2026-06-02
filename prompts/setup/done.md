# Scout Setup — Done

Compose the closing message. The orchestrator passes you two pieces of context:
- `STATE` — `FRESH`, `COLLISION`, or `REFRESH`
- `ZSHRC_MODIFIED` — boolean (true if step j / step d reported `ZSHRC_MODIFIED`)

Read `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`. Extract `requires_reload` (default `false` if absent) and `version`.

## Compose

**If STATE was FRESH or COLLISION:**

> "✓ Scout is set up and ready. Workspace at `~/claude-projects/sf-demo-scout/`.
>
> FYI — run `/scout-switch-org` next to connect a demo org, then `/scout-sparring` to start a demo."

**If STATE was REFRESH and `requires_reload: false`:**

> "✓ Scout refreshed to v[VERSION]. CLIs current. You're good to keep working."

**If STATE was REFRESH and `requires_reload: true`:**

> "✓ Scout refreshed to v[VERSION] (command surface changed). CLIs current.
>
> **Close + reopen this Claude tab** to load the new commands. (If running in VS Code and the new tab still feels stale, fully restart VS Code.) Then continue your work."

## Append (any branch)

**If `ZSHRC_MODIFIED` is true:** append before the close:

> "Note: Scout refreshed your shell environment. Open a new terminal window for non-Claude-Code shell sessions to pick up the changes — current Claude Code session is unaffected."

**If STATE was REFRESH and `ZSHRC_MODIFIED` is true:** also append before the close:

> "Heads-up: Scout no longer manages model selection. Any `ANTHROPIC_DEFAULT_*_MODEL` exports it previously set in your shell have been removed — set them yourself if you want a specific Bedrock model profile, or rely on the `opus[1m]` default in `~/.claude/settings.json` (resolves to whatever your CC build calls Opus, with the 1M window)."
