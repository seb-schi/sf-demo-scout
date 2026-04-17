---
name: sync-skills
description: >
  Pull the latest skill versions from Jaganpro, AFV, and ADLC based on
  .claude/skills-manifest.yaml. Adds new skills, updates existing ones,
  prunes orphans. Run whenever session-startup flags skill drift, or
  manually after editing the manifest.
allowed-tools: Bash, Read
---

# Sync External Skills

You are syncing the SF Demo Scout skill set against `.claude/skills-manifest.yaml`.

## Step 1: Run the sync engine

```bash
bash .claude/scripts/sync-skills.sh
```

Capture the full output — it emits `SYNCED=`, `FAILED=`, `PRUNED=` lines plus `*_COUNT` totals.

## Step 2: Report to the SE

Parse the output and produce a summary in this exact shape:

```
## Skill Sync — [YYYY-MM-DD HH:MM]

✅ Synced (N): [comma-separated list]
🗑️  Pruned (N): [comma-separated list, or "none"]
❌ Failed (N): [list with reasons, or "none"]

Sync state: .claude/.sync-state.json
```

If `FAILED_COUNT` is 0 and `PRUNED_COUNT` is 0, end with:

> "All skills up to date."

If there were prunes, end with:

> "⚠️ Pruned skills removed from disk. If any running command depends on them, restore the manifest entry and re-sync."

If there were failures, end with:

> "⚠️ Some skills failed to sync. Check network / manifest paths / upstream repo state. Previously-synced copies of failed skills remain on disk."

## Step 3: Notify the SE

Fire one macOS notification at the end so the SE is alerted even if VS Code is backgrounded:

```bash
osascript -e 'display notification "Skill sync complete: [counts]" with title "SF Demo Scout — Sync"' 2>/dev/null
```

## Rules

- Do not edit `.claude/skills-manifest.yaml` from this command. The SE edits it; /sync-skills only applies.
- Do not touch homegrown skills (`demo-*`, `pipeline-lessons`). The sync engine excludes them by prefix — do not second-guess.
- If the sync engine exits with code 1 (manifest unreadable), report the error and stop. Do not attempt a partial recovery.
