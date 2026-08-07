---
name: scout-setup
description: >
  One-stop install, refresh, and repair for Scout.
  Run on first install, after a Scout update, or whenever something feels broken.
  Idempotent — safe to re-run any time.
allowed-tools: Read, Write, Edit, Bash
---

# Scout Setup — Install, Refresh, Repair

You are the setup orchestrator. This command is idempotent and state-driven: detect what needs doing, dispatch to the matching prompt, then hand off to the done prompt. Each state's procedure is in its own file so this command stays small and reliable. Read each prompt fully and execute its procedure end-to-end before returning here.

## Step 1: Detect State

Run this Bash:

```bash
mkdir -p "$HOME/claude-projects/sf-demo-scout"
cd "$HOME/claude-projects/sf-demo-scout"
if [ ! -f "$HOME/.config/sf-demo-scout/config.json" ]; then
  echo "STATE=FRESH"
else
  echo "STATE=REFRESH"
fi
```

Capture the STATE value — Step 3 (Done) needs it.

## Step 2: Dispatch

Branch on STATE:

- `STATE=FRESH` → Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/fresh-install.md` and execute its procedure end-to-end.
- `STATE=REFRESH` → Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/refresh.md` and execute its procedure end-to-end.

Both `fresh-install.md` and `refresh.md` end by emitting one of `ZSHRC_UNCHANGED` / `ZSHRC_MODIFIED` (and optionally `ANTHROPIC_MODEL_PRESENT`). Capture that result — Step 3 needs it.

If the dispatched prompt aborts (e.g. brew missing, pyyaml missing, Slack MCP just-registered, Slack auth needed), STOP. Do NOT proceed to Step 3. The abort messages already tell the SE what to do next.

## Step 3: Done

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/done.md` and execute it. Pass the captured `STATE` and the boolean `ZSHRC_MODIFIED` (true if step j / step d emitted `ZSHRC_MODIFIED`) so it can compose the right closing message.
