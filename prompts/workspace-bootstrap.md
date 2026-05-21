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

- `CONFIG_MISSING` — slow path. Read
  `${CLAUDE_PLUGIN_ROOT}/prompts/workspace-setup.md` and execute its
  procedure end-to-end. After it returns control (Step 9 of setup),
  proceed to the parent command's next step.

- `CONFIG_PRESENT` — continue to Step 4 (plugin-version drift check).

## Step 4: Plugin-version drift check

Read `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json` (Read-tool path
resolution; bash shell expansion does not work for
`${CLAUDE_PLUGIN_ROOT}`). Extract the `version` field. Then read
`last_synced_plugin_version` from
`~/.config/sf-demo-scout/config.json`:

```bash
python3 - <<'PYEOF'
import json, os
cfg = os.path.expanduser("~/.config/sf-demo-scout/config.json")
with open(cfg) as f:
    data = json.load(f)
print(data.get("last_synced_plugin_version", "unknown"))
PYEOF
```

Compare the two values:

- **Match** — proceed silently to the parent command's next step.

- **Mismatch** (or `last_synced_plugin_version` is `unknown`) — emit
  a one-line status to the SE ("Scout updated; refreshing skills...")
  and run the sync inline. This is the auto-update-detection path
  from PLAN F-1c.

  Ensure pyyaml first (idempotent):

  ```bash
  if ! python3 -c 'import yaml' 2>/dev/null; then
    pip3 install --quiet --user pyyaml 2>/dev/null || pip3 install --quiet --break-system-packages pyyaml 2>/dev/null || true
  fi
  ```

  Then run the sync, substituting the `version` value extracted above
  as `[PLUGIN_VERSION]`:

  ```bash
  WORKSPACE_DIR="$HOME/claude-projects/sf-demo-scout" \
    PLUGIN_VERSION="[PLUGIN_VERSION]" \
    bash "${CLAUDE_PLUGIN_ROOT}/scripts/sync-skills.sh"
  ```

  On success (FAILED_COUNT=0), update config.json's
  `last_synced_plugin_version`:

  ```bash
  python3 - "$HOME/.config/sf-demo-scout/config.json" "[PLUGIN_VERSION]" <<'PYEOF'
  import json, sys
  path, version = sys.argv[1], sys.argv[2]
  with open(path) as f:
      data = json.load(f)
  data["last_synced_plugin_version"] = version
  with open(path, "w") as f:
      json.dump(data, f, indent=2)
  PYEOF
  ```

  On `FAILED_COUNT > 0`: do NOT update config.json (so the next
  bootstrap re-tries). Surface the warning to the SE inline:

  > "[F] of [N+F] skills failed to refresh. The parent command will
  > continue with the previous skill files. Retry later with
  > `/scout-sync-skills`."

  Then proceed to the parent command's next step.

## After bootstrap

All subsequent `orgs/...`, `sparring-lessons.md`, `building-lessons.md`
refs in the parent command resolve against the workspace dir (Bash
context) thanks to the `cd` above. Read/Edit-context refs are
handled per the path-rewrite outcome from D-2b's empirical test (see
PLAN LOG).
