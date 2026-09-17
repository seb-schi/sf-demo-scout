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

Resolve `${CLAUDE_PLUGIN_ROOT}` to the absolute active Scout plugin directory,
then run this Bash with those literal paths substituted. A failed workspace
directory change or missing verifier is an abort, never a setup state.

```bash
WORKSPACE="$HOME/claude-projects/sf-demo-scout"
CONFIG="$HOME/.config/sf-demo-scout/config.json"
WORKSPACE_HELPER="[PLUGIN_ROOT]/scripts/setup-workspace.py"
if ! mkdir -p "$WORKSPACE" || ! cd "$WORKSPACE"; then
  echo "SETUP_ABORTED (workspace unavailable)"
  exit 1
fi
if [ ! -f "$WORKSPACE_HELPER" ]; then
  echo "SETUP_ABORTED (shipped workspace helper missing)"
  exit 1
fi
PYTHON_EXE=$(type -P python3 2>/dev/null || true)
if [ -z "$PYTHON_EXE" ]; then
  echo "STATE=FRESH"
elif "$PYTHON_EXE" -B "$WORKSPACE_HELPER" verify \
    --workspace "$WORKSPACE" --config "$CONFIG" >/dev/null 2>&1; then
  echo "STATE=REFRESH"
else
  echo "STATE=FRESH"
fi
```

Capture the STATE value — Step 3 (Done) needs it. `STATE=FRESH` includes an
interrupted or partial install even when `config.json` exists; the fresh path
is idempotent and repairs missing mandatory artifacts without replacing valid
incumbent workspace files or config.

## Step 2: Dispatch

Branch on STATE:

- `STATE=FRESH` → Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/fresh-install.md` and execute its procedure end-to-end.
- `STATE=REFRESH` → Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/refresh.md` and execute its procedure end-to-end.

Both `fresh-install.md` and `refresh.md` end by emitting one of `ZSHRC_UNCHANGED` / `ZSHRC_MODIFIED` (and optionally `ANTHROPIC_MODEL_PRESENT`). Capture that result — Step 3 needs it.

If the dispatched prompt aborts (e.g. brew missing or pyyaml missing), STOP. Do NOT proceed to Step 3. The abort messages already tell the SE what to do next. Optional MCP checks return with their observed status; an unavailable check or pending connection does not abort setup.

## Step 3: Done

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/done.md` and execute it. Pass the captured `STATE`, the boolean `ZSHRC_MODIFIED` (true if step j / step d emitted `ZSHRC_MODIFIED`), all CLI outcome tokens and optional MCP status notes so the closing message preserves unresolved checks and connections.
