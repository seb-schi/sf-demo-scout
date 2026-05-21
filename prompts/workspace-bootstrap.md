# Workspace Bootstrap

Shared fragment Read by `/scout-sparring`, `/scout-building`, and
`/scout-switch-org` as their first step. Ensures Scout commands run in
the workspace directory regardless of where the SE invoked the command.

This is the **D-2a skeleton** — silent `cd` + collision check only. The
detect-and-fix logic for missing workspace creation, SFDX scaffold,
`~/.config/sf-demo-scout/config.json`, `.zshrc` block, and Slack MCP
user-scope guidance lands in D-2b/c.

## Step 1: cd into workspace

Run this Bash:
```
cd "$HOME/claude-projects/sf-demo-scout" 2>/dev/null || {
  echo "WORKSPACE_MISSING"
  exit 1
}
```

If the command exits 1 (workspace dir does not exist), abort the parent
command and emit this message verbatim to the SE:

> "Scout workspace not found at `~/claude-projects/sf-demo-scout/`.
> Phase D-2b will automate setup. For now, run this once in a terminal:
>
> ```
> mkdir -p ~/claude-projects/sf-demo-scout/orgs
> ```
>
> Then re-run the Scout command."

Do not proceed past this step if cd failed.

## Step 2: Collision check

Still inside the workspace dir, check for plugin + clone-install
coexistence:
```
if [ -d .git ] && [ -f install.sh ]; then echo "COLLISION"; fi
```

If output is `COLLISION`, abort the parent command and emit:

> "Detected both **plugin install** AND **clone-install** of Scout at
> `~/claude-projects/sf-demo-scout/`. They cannot coexist — MCP servers,
> hooks, and commands will double-load.
>
> Pick one path:
> - **Keep plugin** (recommended): `rm -rf ~/claude-projects/sf-demo-scout/.git ~/claude-projects/sf-demo-scout/install.sh ~/claude-projects/sf-demo-scout/.claude` — preserves your `orgs/` data.
> - **Keep clone-install**: `/plugin uninstall sf-demo-scout@scout` then quit and relaunch Claude Code.
>
> Then re-run the Scout command."

Do not proceed past this step if collision detected.

## After bootstrap

All subsequent `orgs/...`, `sparring-lessons.md`, `building-lessons.md`
refs in the parent command resolve against the workspace dir (Bash
context) thanks to the `cd` above.
