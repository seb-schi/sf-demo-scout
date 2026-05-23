# Workspace Bootstrap

Shared fragment Read by `/scout-sparring`, `/scout-building`, and `/scout-switch-org` as their first step. Single bash gate — three outcomes — one tool call.

## Step 1: Sanity gate

Run this Bash:

```bash
mkdir -p "$HOME/claude-projects/sf-demo-scout"
cd "$HOME/claude-projects/sf-demo-scout"
if [ -d .git ] && [ -f install.sh ]; then
  echo "STATE=COLLISION"
elif [ ! -f "$HOME/.config/sf-demo-scout/config.json" ]; then
  echo "STATE=NO_CONFIG"
else
  echo "STATE=OK"
fi
```

Branch on output:

- `STATE=OK` → silent. Return control to the parent command's next step.

- `STATE=NO_CONFIG` → ABORT the parent command and emit:

  > "Scout isn't set up yet. Run `/scout-setup` to install — it handles fresh installs, refreshes, and repairs in one command. Then re-run your Scout command."

- `STATE=COLLISION` → ABORT the parent command and emit:

  > "Detected both **plugin install** AND **clone-install** of Scout at `~/claude-projects/sf-demo-scout/`. They cannot coexist — MCP servers, hooks, and commands will double-load.
  >
  > Run `/scout-setup` to scrub the old clone-install residue and continue. Your `orgs/` data is preserved."

Do not proceed past this step on `STATE=NO_CONFIG` or `STATE=COLLISION`.

## After bootstrap

All subsequent `orgs/...`, `sparring-lessons.md`, `building-lessons.md` refs in the parent command resolve against the workspace dir (Bash context) thanks to the `cd` above.
