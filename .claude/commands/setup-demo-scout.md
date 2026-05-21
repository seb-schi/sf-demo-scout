---
description: Migrate from clone-install Scout to the plugin (one-shot cleanup)
model: sonnet
---

# /setup-demo-scout — Migration cleanup command

This command is the migration helper for SEs moving from the
clone-install version of Scout to the plugin. It runs inside the
old clone-install workspace at `~/claude-projects/sf-demo-scout/`,
confirms the plugin is installed, and cleans up the old artifacts
so the plugin's bootstrap can take over cleanly.

## Step 1 — Detect context

Check whether you are running inside the clone-install workspace:

```bash
test -d ~/claude-projects/sf-demo-scout/.git && \
  test -f ~/claude-projects/sf-demo-scout/install.sh && \
  echo "CLONE_INSTALL_DETECTED" || echo "NO_CLONE_INSTALL"
```

If output is `NO_CLONE_INSTALL`, tell the SE:

> No clone-install workspace detected at
> `~/claude-projects/sf-demo-scout/`. If you came here from old
> documentation, you may already be on the plugin — try
> `/scout-sparring` or `/scout-switch-org`. If neither command
> exists, install the plugin:
>
> ```
> /plugin marketplace add https://github.com/seb-schi/sf-demo-scout-plugin.git
> /plugin install sf-demo-scout@scout
> ```

Then stop.

If output is `CLONE_INSTALL_DETECTED`, continue.

## Step 2 — Detect plugin install

Check whether the Scout plugin is installed and active. Two
independent signals — both must succeed:

```bash
test -f ~/.claude/plugins/installed_plugins.json && \
  grep -q "sf-demo-scout@scout" ~/.claude/plugins/installed_plugins.json && \
  test -d ~/.claude/plugins/cache/scout/sf-demo-scout && \
  echo "PLUGIN_DETECTED" || echo "NO_PLUGIN"
```

If output is `NO_PLUGIN`, tell the SE:

> The Scout plugin is not yet installed. Install it now:
>
> ```
> /plugin marketplace add https://github.com/seb-schi/sf-demo-scout-plugin.git
> /plugin install sf-demo-scout@scout
> ```
>
> After the install completes, restart Claude Code and run
> `/setup-demo-scout` again to finish the migration cleanup.

Then stop.

If output is `PLUGIN_DETECTED`, continue.

## Step 3 — Confirm with SE

Print this and wait for explicit confirmation:

> Plugin detected. Ready to clean up the old clone-install
> artifacts at `~/claude-projects/sf-demo-scout/`.
>
> What gets removed:
>   - `.git/` — clone-install git history
>   - `install.sh`, `bootstrap.sh`, `update.sh` — clone-install scripts
>   - `README.md` — clone-install readme
>   - `.claude/` — clone-install commands/skills/hooks/prompts
>     (the plugin provides its own at the global plugin scope)
>   - `force-app/`, `sfdx-project.json` — old SFDX scaffold (the
>     plugin's bootstrap will create a fresh one)
>   - `CLAUDE.md` — clone-install Claude Code instructions
>
> What stays:
>   - `orgs/` — your customer audits, specs, change logs
>   - `.sf/` — your active org configuration
>
> Type "yes" to proceed, anything else to abort.

If the SE does not type exactly `yes`, abort with:

> Aborted. No files changed. Run `/setup-demo-scout` again when
> you are ready.

## Step 4 — Clean up

Run the cleanup with a single bash invocation. Each removal is
guarded by `test -e` so the command is idempotent (safe to re-run
if a previous attempt was interrupted):

```bash
cd ~/claude-projects/sf-demo-scout && \
  rm -rf .git install.sh bootstrap.sh update.sh README.md .claude force-app sfdx-project.json CLAUDE.md && \
  echo "CLEANUP_DONE" || echo "CLEANUP_FAILED"
```

If output ends in `CLEANUP_DONE`, continue.

If `CLEANUP_FAILED`, tell the SE:

> Cleanup hit an error. Check the bash output above. Your
> `orgs/` directory is untouched. You can re-run
> `/setup-demo-scout` after fixing the underlying issue (most
> likely a permission problem).

Then stop.

## Step 5 — Verify

Confirm the workspace is in the expected post-migration state:

```bash
ls ~/claude-projects/sf-demo-scout/ 2>/dev/null
```

Expected output: `orgs` (and possibly `.sf` if you had an active
org configured).

If anything else remains, list it for the SE and ask whether to
remove. Don't auto-remove — could be SE work product.

## Step 6 — Hand over

Print this and stop:

> Migration complete. Your workspace at
> `~/claude-projects/sf-demo-scout/` now contains only your org
> data. The plugin will pick it up automatically on first command
> run.
>
> Try one of:
>
>   /scout-sparring     — Opus discovery sparring + spec generation
>   /scout-building     — Opus orchestrator for org deployment
>   /scout-switch-org   — change active demo org
>
> First-run note: the plugin's bootstrap will write a fresh
> `~/.config/sf-demo-scout/config.json`, set up SFDX scaffold,
> refresh your `.zshrc` Scout-managed block, and pre-cache the
> Salesforce MCP server. Takes ~30s the first time, silent on
> subsequent runs.
