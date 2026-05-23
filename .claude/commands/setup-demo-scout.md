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

## Critical: paste-friendly output

When you print Step 2A's instructions, the slash commands MUST be on
their own bare lines — NOT inside blockquotes (`>`), NOT inside code
fences. Markdown renderers add leading whitespace to blockquote
content, which the SE's terminal copies verbatim when they
select+copy, breaking the slash command on paste.

The narrative paragraphs CAN be in a blockquote. The slash commands
themselves must be plain lines, surrounded by blank lines so they're
visually distinct.

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

### 2A.0 — Pre-write marketplace entry (silent)

Before printing instructions, merge the Scout marketplace entry into user-scope `~/.claude/settings.json` so the SE's `/plugin marketplace add` step finds it already registered with `autoUpdate: true`. CC honours the existing entry; the manual command becomes a no-op confirmation. Idempotent.

```bash
USER_SETTINGS="$HOME/.claude/settings.json"
mkdir -p "$(dirname "$USER_SETTINGS")"

python3 - "$USER_SETTINGS" <<'PYEOF'
import json, os, sys, tempfile
path = sys.argv[1]
ENTRY = {
    "source": {"source": "git", "url": "https://github.com/seb-schi/sf-demo-scout.git"},
    "autoUpdate": True,
}

if os.path.exists(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"USER_SETTINGS_PARSE_ERROR: {e}")
        sys.exit(0)
else:
    data = {}

if not isinstance(data, dict):
    print("USER_SETTINGS_NOT_OBJECT"); sys.exit(0)

marketplaces = data.setdefault("extraKnownMarketplaces", {})
if not isinstance(marketplaces, dict):
    print("USER_SETTINGS_MARKETPLACES_NOT_OBJECT"); sys.exit(0)

existing = marketplaces.get("scout")
if existing == ENTRY:
    print("MARKETPLACE_ENTRY_PRESENT"); sys.exit(0)

marketplaces["scout"] = ENTRY

tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".settings.", suffix=".tmp")
try:
    with os.fdopen(tmp_fd, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.rename(tmp_path, path)
except Exception as e:
    try: os.unlink(tmp_path)
    except OSError: pass
    print(f"USER_SETTINGS_WRITE_FAILED: {e}"); sys.exit(0)

print("MARKETPLACE_ENTRY_WRITTEN")
PYEOF
```

Interpret the single output line:
- `MARKETPLACE_ENTRY_PRESENT` — proceed silently to instructions below.
- `MARKETPLACE_ENTRY_WRITTEN` — surface a one-line note before instructions: *"Pre-registered Scout marketplace in your global settings (with auto-updates on)."*
- Any error line — surface it, but proceed to instructions below. The SE's manual `/plugin marketplace add` will write the entry without `autoUpdate: true` as a fallback. Not blocking.

Then print this verbatim. Note the formatting: narrative as blockquote,
slash commands as bare lines on their own.

> Welcome! SF Demo Scout is now a Claude Code plugin. This is a
> **one-time migration** — once you finish the four steps below,
> Scout commands will be globally available wherever you launch
> Claude Code, you'll get auto-updates, and you'll never run
> `update.sh` again.
>
> Run the four slash commands **one at a time** — paste, hit Enter,
> wait for the confirmation, then move to the next. Don't paste them
> all together.

---

**Step 1.** Add the plugin marketplace.

> 🟡 **Paste exactly — no leading or trailing spaces.**

```
/plugin marketplace add https://github.com/seb-schi/sf-demo-scout.git
```

Wait for: `Successfully added marketplace: scout`

---

**Step 2.** Install the plugin.

> 🟡 **Paste exactly — no leading or trailing spaces.**

```
/plugin install sf-demo-scout@scout
```

> ⚠️ When Claude Code asks for install scope, **pick `User scope`**.
> This makes the plugin available across all your projects, not just
> this directory. The choice happens in the install dialog — pick
> User, not Project.

Wait for: `✓ Installed sf-demo-scout`

---

**Step 3.** Activate the plugin without restarting.

> 🟡 **Paste exactly — no leading or trailing spaces.**

```
/reload-plugins
```

Wait for: `Reloaded: ... plugins · ... skills · ... agents` (numbers vary).

---

**Step 4.** Re-run this migration command. It will detect the plugin
and finish cleanup automatically.

> 🟡 **Paste exactly — no leading or trailing spaces.**

```
/setup-demo-scout
```

---

> Your org data at `~/claude-projects/sf-demo-scout/orgs/` is preserved
> throughout.
>
> Stuck? Ping `#sf-demo-scout` on Slack — the team monitors the channel,
> and the Scout Slackbot skill can answer most questions.

Stop after this message. Do NOT proceed to cleanup until the SE
re-runs `/setup-demo-scout` post-install.

## Step 2B — Plugin installed: clean up + hand over (no confirmation gate)

By the time the SE reaches this step, they have already:
1. Run `bash update.sh` and confirmed there
2. Installed the marketplace + plugin
3. Reloaded plugins
4. Re-invoked `/setup-demo-scout`

A fifth "type yes to proceed" gate is friction without safety value
— `orgs/` and `.sf/` are protected by the keep-list, the SE can only
get here by deliberately driving the migration forward, and there's
no useful "abort" branch (re-running won't undo anything; aborting
just leaves an inconsistent state).

Print this status update, then proceed straight to cleanup:

> Plugin detected. Cleaning up the old clone-install scaffolding.
> Your existing customer demo work and Salesforce project structure are preserved.

Run cleanup. Inverted logic: enumerate what to KEEP, delete the rest.
Robust against future trampoline payload additions:

```bash
cd ~/claude-projects/sf-demo-scout && \
  find . -maxdepth 1 -mindepth 1 \
    ! -name 'orgs' \
    ! -name '.sf' \
    ! -name '.sfdx' \
    ! -name 'force-app' \
    ! -name 'sfdx-project.json' \
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

Expected: `orgs`, `force-app`, `sfdx-project.json`, possibly `.sf`,
`.sfdx`, `.DS_Store`. If anything else remains, list it for the SE
and ask whether to remove. Do not auto-remove — could be SE work
product.

## Step 4 — Hand over

Print this verbatim, then stop:

> 🎉 **Migration complete.** Welcome to plugin-Scout!
>
> **What's better now:**
> - Scout commands are **global** — `/scout-sparring`,
>   `/scout-building`, `/scout-switch-org` work in any Claude Code
>   session, regardless of which directory you launched from.
> - **Greatly simplified updates** — new Scout versions arrive
>   automatically; a banner tells you when to run `/scout-setup` to
>   finish installing right inside Claude Code. No more `bash update.sh`
>   inside Terminal, no more reloading of apps.
> - **Cleaner workspace** — your `~/claude-projects/sf-demo-scout/`
>   directory now contains only your data (`orgs/`) and the Salesforce
>   project shell (`force-app/` + `sfdx-project.json`). Skills,
>   commands, hooks, prompts all live in plugin land.
> - **Faster sessions** — MCP servers pre-cached, prereqs verified,
>   skill manifest synced on first run.
>
> **Recommended next step:** run `/scout-setup` to finish setup —
> it syncs the skill manifest, verifies prereqs, and primes the
> workspace for the new plugin layout.

```
/scout-setup
```

> Once setup completes, run `/scout-switch-org` to pick your active
> org, then `/scout-sparring` (discovery + spec generation) and
> `/scout-building` (deployment) are ready when you need them.
>
> Questions or issues? Ping `#sf-demo-scout` on Slack. The Scout
> Slackbot skill can also answer most "how do I X?"
> questions — just ask in any session.
