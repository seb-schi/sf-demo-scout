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

## Step 2: Compute update state (only when STATE=OK)

Run this Bash. It writes the rendered banner (or empty file) to `.claude/.update-block` for the parent command to include in its first SE-facing reply. Mirrors the SessionStart hook's three-flag logic so SEs invoking Scout commands from any cwd see the same notice.

```bash
mkdir -p .claude
CATALOG_FILE="$HOME/.claude/plugins/marketplaces/scout/.claude-plugin/plugin.json"
INSTALLED_FILE="$HOME/.claude/plugins/installed_plugins.json"
CONFIG_FILE="$HOME/.config/sf-demo-scout/config.json"

if [ -f "$CATALOG_FILE" ] && [ -f "$INSTALLED_FILE" ] && [ -f "$CONFIG_FILE" ]; then
  UPDATE_STATE=$(python3 -c "
import json
try:
    catalog = json.load(open('$CATALOG_FILE')).get('version', '')
    inst_d = json.load(open('$INSTALLED_FILE'))
    installed = ''
    entries = inst_d.get('plugins', {}).get('sf-demo-scout@scout', [])
    if entries:
        installed = entries[0].get('version', '')
    synced = json.load(open('$CONFIG_FILE')).get('last_synced_plugin_version', '')
    if not (catalog and installed and synced):
        print('UNKNOWN')
    elif catalog != installed:
        print('UPDATE_AVAILABLE')
    elif installed != synced:
        print('SETUP_PENDING')
    else:
        print('ALIGNED')
except Exception:
    print('UNKNOWN')
" 2>/dev/null)
else
  UPDATE_STATE="UNKNOWN"
fi

case "$UPDATE_STATE" in
  UPDATE_AVAILABLE)
    cat > .claude/.update-block <<'EOF'
> 🆕 SF Demo Scout update available — see `#sf-demo-scout` on Slack for details.
> To apply: run `/scout-setup`, then close + reopen this Claude tab.
EOF
    ;;
  SETUP_PENDING)
    cat > .claude/.update-block <<'EOF'
> 🆕 SF Demo Scout update downloaded — run `/scout-setup` to finish installation. See `#sf-demo-scout` on Slack for details.
EOF
    ;;
  *)
    : > .claude/.update-block
    ;;
esac
```

## After bootstrap

All subsequent `orgs/...`, `sparring-lessons.md`, `building-lessons.md` refs in the parent command resolve against the workspace dir (Bash context) thanks to the `cd` above.

Each parent command MUST start its first SE-facing reply by Reading `.claude/.update-block` and including its contents verbatim at the top of the reply (file is always present after this fragment runs; empty file = no banner content). The file is workspace-relative, so it resolves correctly post-`cd`.
