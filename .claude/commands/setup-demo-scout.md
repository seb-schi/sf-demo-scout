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

Print this exactly, then stop. Do NOT continue past this step — the SE
needs to run the slash commands one at a time, then re-invoke
`/setup-demo-scout` for the cleanup phase.

> SF Demo Scout is now a Claude Code plugin. Finish the migration by
> running these slash commands **one at a time** — paste, hit Enter,
> wait for confirmation, then move to the next.
>
> ---
>
> **Step 1.** Add the plugin marketplace:
>
>     /plugin marketplace add https://github.com/seb-schi/sf-demo-scout-plugin.git
>
> Wait for: `Successfully added marketplace: scout`
>
> ---
>
> **Step 2.** Install the plugin:
>
>     /plugin install sf-demo-scout@scout
>
> Wait for: `✓ Installed sf-demo-scout`
>
> ---
>
> **Step 3.** Activate the plugin without restarting:
>
>     /reload-plugins
>
> ---
>
> **Step 4.** Re-run this migration command — it will detect the plugin
> and finish cleanup:
>
>     /setup-demo-scout
>
> ---
>
> Your org data at `~/claude-projects/sf-demo-scout/orgs/` is preserved
> throughout.

Stop after this message. Do NOT proceed to cleanup until the SE
re-runs `/setup-demo-scout` post-install.

## Step 2B — Plugin installed: clean up + hand over

Confirm with the SE first. Print this and wait for explicit `yes`:

> Plugin detected. Ready to clean up the old clone-install
> scaffolding at `~/claude-projects/sf-demo-scout/`.
>
> What stays:
>   - `orgs/` — your customer audits, specs, change logs
>   - `.sf/` — your active org configuration
>
> Everything else in that directory will be removed (it was the
> clone-install repo and the trampoline payload — both obsolete now
> that the plugin owns command/skill/hook content).
>
> Type `yes` to proceed, anything else to abort.

If the SE does not type exactly `yes`, abort with:

> Aborted. No files changed. Run `/setup-demo-scout` again when you
> are ready, or run any plugin command (`/scout-sparring`,
> `/scout-switch-org`) — bootstrap will detect the leftover
> clone-install state and prompt you again.

If `yes`, run cleanup. Inverted logic: enumerate what to KEEP, delete
the rest. This way the cleanup is robust against future trampoline
payload additions:

```bash
cd ~/claude-projects/sf-demo-scout && \
  find . -maxdepth 1 -mindepth 1 \
    ! -name 'orgs' \
    ! -name '.sf' \
    ! -name '.DS_Store' \
    -exec rm -rf {} + && \
  echo "CLEANUP_DONE" || echo "CLEANUP_FAILED"
```

If output is `CLEANUP_FAILED`, tell the SE:

> Cleanup hit an error. Check the bash output above. Your `orgs/`
> directory is untouched. Most likely cause: a permission issue. Fix
> manually, then re-run `/setup-demo-scout`.

Stop on `CLEANUP_FAILED`.

## Step 3 — Verify

```bash
ls -A ~/claude-projects/sf-demo-scout/ 2>/dev/null
```

Expected: `orgs`, `.sf`, possibly `.DS_Store`. If anything else
remains, list it for the SE and ask whether to remove. Do not
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
