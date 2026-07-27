# Workspace Bootstrap

Shared fragment Read by `/scout-sparring`, `/scout-building`, and `/scout-switch-org` as their first step. Single bash gate — two outcomes — one tool call.

## Step 1: Sanity gate

Run this Bash:

```bash
mkdir -p "$HOME/claude-projects/sf-demo-scout"
cd "$HOME/claude-projects/sf-demo-scout"
if [ ! -f "$HOME/.config/sf-demo-scout/config.json" ]; then
  echo "STATE=NO_CONFIG"
else
  echo "STATE=OK"
fi
```

Branch on output:

- `STATE=OK` → silent. Return control to the parent command's next step.

- `STATE=NO_CONFIG` → ABORT the parent command and emit:

  > "Scout isn't set up yet. Run `/scout-setup` to install — it handles fresh installs, refreshes, and repairs in one command. Then re-run your Scout command."

Do not proceed past this step on `STATE=NO_CONFIG`.

## After bootstrap

All subsequent `orgs/...` refs (including `orgs/lessons/`) in the parent command resolve against the workspace dir (Bash context) thanks to the `cd` above.
