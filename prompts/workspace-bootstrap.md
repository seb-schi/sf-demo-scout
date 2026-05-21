# Workspace Bootstrap

Shared fragment Read by `/scout-sparring`, `/scout-building`, and
`/scout-switch-org` as their first step. Ensures Scout commands run
in the workspace directory regardless of where the SE invoked the
command, and triggers first-run setup if config.json is absent.

## Step 1: Ensure workspace dir exists + cd into it

Run this Bash:
```bash
mkdir -p "$HOME/claude-projects/sf-demo-scout"
cd "$HOME/claude-projects/sf-demo-scout"
```

`mkdir -p` is idempotent; the `cd` cannot fail after it. No abort branch.

## Step 2: Collision check

```bash
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

## Step 3: Config check + slow-path branch

```bash
if [ -f "$HOME/.config/sf-demo-scout/config.json" ]; then
  echo "CONFIG_PRESENT"
else
  echo "CONFIG_MISSING"
fi
```

- `CONFIG_PRESENT` — fast path. Proceed silently to the parent
  command's next step. The `cd` from Step 1 is in effect; all
  subsequent `orgs/...` etc. refs resolve against the workspace.

- `CONFIG_MISSING` — slow path. Read
  `${CLAUDE_PLUGIN_ROOT}/prompts/workspace-setup.md` and execute its
  procedure end-to-end. After it returns control (Step 9 of setup),
  proceed to the parent command's next step.

## After bootstrap

All subsequent `orgs/...`, `sparring-lessons.md`, `building-lessons.md`
refs in the parent command resolve against the workspace dir (Bash
context) thanks to the `cd` above. Read/Edit-context refs are
handled per the path-rewrite outcome from D-2b's empirical test (see
PLAN LOG).
