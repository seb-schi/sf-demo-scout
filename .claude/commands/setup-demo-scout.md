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

**This is a one-time migration command.** After cleanup completes, it
disappears with the rest of the trampoline scaffolding. From then on,
`/scout-sparring`, `/scout-building`, and `/scout-switch-org` (provided
by the plugin) are the SE's day-to-day commands.

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

Print this exactly, then stop. **Slash commands MUST start at column 0
(no indent), so SEs can copy-paste straight from Terminal.** Indented
slash commands break paste behaviour in Terminal.app and similar
emulators.

Print this verbatim:

> Welcome! SF Demo Scout is now a Claude Code plugin. This is a
> **one-time migration** — once you finish the four steps below,
> Scout commands will be globally available wherever you launch Claude
> Code, you'll get auto-updates, and you'll never run `update.sh`
> again.
>
> Run these slash commands **one at a time** — paste, hit Enter, wait
> for the confirmation message, then move to the next.
>
> ---
>
> **Step 1.** Add the plugin marketplace:
>
> /plugin marketplace add https://github.com/seb-schi/sf-demo-scout-plugin.git
>
> Wait for: `Successfully added marketplace: scout`
>
> ---
>
> **Step 2.** Install the plugin (use **user scope** when prompted, so
> the plugin is available across all your projects):
>
> /plugin install sf-demo-scout@scout
>
> Wait for: `✓ Installed sf-demo-scout`
>
> ---
>
> **Step 3.** Activate the plugin without restarting:
>
> /reload-plugins
>
> ---
>
> **Step 4.** Re-run this migration command — it will detect the
> plugin and finish cleanup:
>
> /setup-demo-scout
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

Print this verbatim, then stop:

> 🎉 **Migration complete.** Welcome to plugin-Scout!
>
> **What's better now:**
> - Scout commands are **global** — `/scout-sparring`,
>   `/scout-building`, `/scout-switch-org` work in any Claude Code
>   session, regardless of which directory you launched from.
> - **Auto-updates** — when a new Scout version ships, the plugin
>   marketplace picks it up automatically. No more `bash update.sh`.
> - **Cleaner workspace** — your `~/claude-projects/sf-demo-scout/`
>   directory now contains only your data (`orgs/` + `.sf/`). Skills,
>   commands, hooks, prompts all live in plugin land.
> - **Faster sessions** — MCP servers pre-cached, prereqs verified,
>   skill manifest synced on first run.
>
> **Recommended next step:** run `/scout-switch-org` to confirm your
> active org. Pick one from the list — that's all you need to start
> demo prep.
>
>     /scout-switch-org
>
> Once an org is active, `/scout-sparring` (discovery + spec
> generation) and `/scout-building` (deployment) are ready when you
> need them.
