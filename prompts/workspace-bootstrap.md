# Workspace Bootstrap

Shared fragment Read by `/scout-sparring` and `/scout-building` as their first step. Single bash gate — two outcomes — one tool call.

## Step 1: Sanity gate

Resolve `${CLAUDE_PLUGIN_ROOT}` to the absolute active Scout plugin directory,
then run this Bash with that literal path substituted:

```bash
WORKSPACE="$HOME/claude-projects/sf-demo-scout"
CONFIG="$HOME/.config/sf-demo-scout/config.json"
WORKSPACE_HELPER="[PLUGIN_ROOT]/scripts/setup-workspace.py"
PYTHON_EXE=$(type -P python3 2>/dev/null || true)
if [ -n "$PYTHON_EXE" ] && [ -f "$WORKSPACE_HELPER" ] \
    && mkdir -p "$WORKSPACE" && cd "$WORKSPACE" \
    && "$PYTHON_EXE" -B "$WORKSPACE_HELPER" verify \
      --workspace "$WORKSPACE" --config "$CONFIG" >/dev/null 2>&1; then
  echo "STATE=OK"
else
  echo "STATE=NO_CONFIG"
fi
```

Branch on output:

- `STATE=OK` → silent. Return control to the parent command's next step.

- `STATE=NO_CONFIG` → ABORT the parent command and emit:

  > "Scout isn't set up yet. Run `/scout-setup` to install — it handles fresh installs, refreshes, and repairs in one command. Then re-run your Scout command."

Do not proceed past this step on `STATE=NO_CONFIG`.

## After bootstrap

Do not rely on shell working-directory state persisting between tool calls. The
parent command must set `$HOME/claude-projects/sf-demo-scout` as the working
directory for each subsequent shell call, or begin that call with a checked
`cd` to the workspace. All subsequent `orgs/...` refs (including
`orgs/lessons/`) resolve against that explicit working directory.
