---
description: One-shot migration from clone-install Scout to the plugin
model: sonnet
---

# /setup-demo-scout — Plugin migration handler

Production `update.sh` ends with `exec claude "/setup-demo-scout"`,
so this command is the SE's first contact with Claude Code after the
trampoline lands. Two states to handle:

A) Plugin not yet installed — give the SE the install instructions, stop.
B) Plugin already installed — clean up trampoline scaffolding, hand over.

## Step 1 — Detect plugin install

```bash
test -f ~/.claude/plugins/installed_plugins.json && \
  grep -q "sf-demo-scout@scout" ~/.claude/plugins/installed_plugins.json && \
  test -d ~/.claude/plugins/cache/scout/sf-demo-scout && \
  echo "PLUGIN_DETECTED" || echo "NO_PLUGIN"
```

If output is `NO_PLUGIN`, go to Step 2A.
If `PLUGIN_DETECTED`, go to Step 2B.

## Step 2A — Plugin not installed: install instructions

Print this exactly, then stop:

> SF Demo Scout has moved to a Claude Code plugin. To finish the
> migration, run these two slash commands now:
>
>     /plugin marketplace add https://github.com/seb-schi/sf-demo-scout-plugin.git
>     /plugin install sf-demo-scout@scout
>
> After the install completes, **quit and relaunch Claude Code**, then
> run `/setup-demo-scout` once more. It will detect the plugin, clean
> up the old clone-install artifacts, and hand you over to
> `/scout-sparring` or `/scout-switch-org`.
>
> Your org data at `~/claude-projects/sf-demo-scout/orgs/` is preserved
> throughout.

Stop after this message. Do NOT proceed to cleanup until the SE
re-runs `/setup-demo-scout` post-install.

## Step 2B — Plugin installed: clean up + hand over

Confirm with the SE first. Print this and wait for explicit `yes`:

> Plugin detected. Ready to clean up the old clone-install
> artifacts at `~/claude-projects/sf-demo-scout/`.
>
> What gets removed:
>   - `.git/`, `install.sh`, `bootstrap.sh`, `update.sh`, `README.md`,
>     `.claude/` — clone-install scaffolding
>   - `force-app/`, `sfdx-project.json`, `CLAUDE.md` — old SFDX scaffold
>     and instructions (the plugin's bootstrap will recreate the SFDX
>     scaffold on first command run)
>
> What stays:
>   - `orgs/` — your customer audits, specs, change logs
>   - `.sf/` — your active org configuration
>
> Type "yes" to proceed, anything else to abort.

If the SE does not type exactly `yes`, abort with:

> Aborted. No files changed. Run `/setup-demo-scout` again when you
> are ready, or run any plugin command (`/scout-sparring`,
> `/scout-switch-org`) — bootstrap will detect the leftover
> clone-install state and prompt you again.

If `yes`, run cleanup with a single bash invocation. Each removal
guarded by `test -e` so the command is idempotent:

```bash
cd ~/claude-projects/sf-demo-scout && \
  for path in .git install.sh bootstrap.sh update.sh README.md .claude force-app sfdx-project.json CLAUDE.md; do
    [ -e "$path" ] && rm -rf "$path"
  done && \
  echo "CLEANUP_DONE" || echo "CLEANUP_FAILED"
```

If output is `CLEANUP_FAILED`, tell the SE:

> Cleanup hit an error. Check the bash output above. Your `orgs/`
> directory is untouched. Most likely cause: a permission issue. Fix
> manually, then re-run `/setup-demo-scout`.

Stop on `CLEANUP_FAILED`.

## Step 3 — Verify

```bash
ls ~/claude-projects/sf-demo-scout/ 2>/dev/null
```

Expected: `orgs` (and `.sf` if an org was configured). If anything
else remains, list it for the SE and ask whether to remove. Do not
auto-remove — could be SE work product.

## Step 4 — Hand over

Print this, then stop:

> Migration complete. Your workspace at
> `~/claude-projects/sf-demo-scout/` now contains only your org data.
> The plugin's bootstrap will pick it up automatically on your next
> command.
>
> Try one of:
>
>   /scout-sparring     — Opus discovery sparring + spec generation
>   /scout-building     — Opus orchestrator for org deployment
>   /scout-switch-org   — change active demo org
>
> First-run note: the plugin's bootstrap installs missing prereqs
> (Node, Python, sf CLI), pre-caches the Salesforce MCP server,
> creates a fresh SFDX scaffold, syncs upstream skills, and refreshes
> your `.zshrc` Scout-managed block. ~30s the first time, silent on
> subsequent runs.
