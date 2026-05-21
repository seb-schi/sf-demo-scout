---
description: Force-refresh upstream Scout skills from manifest
model: sonnet
---

# /scout-sync-skills — Force skill refresh

Manual escape hatch for resyncing the upstream skills declared in
`${CLAUDE_PLUGIN_ROOT}/skills-manifest.yaml`. Doesn't require a plugin
version bump — useful when SE knows the upstream `forcedotcom/sf-skills`
repo updated but the plugin hasn't republished.

## Step 1: Bootstrap

Read `${CLAUDE_PLUGIN_ROOT}/prompts/workspace-bootstrap.md` and execute
its procedure. After it returns control, continue here.

## Step 2: Ensure pyyaml is available

The sync engine parses the manifest via Python YAML. If pyyaml is
missing, install it user-scope (no sudo). Idempotent.

```bash
if ! python3 -c 'import yaml' 2>/dev/null; then
  pip3 install --quiet --user pyyaml 2>/dev/null || pip3 install --quiet --break-system-packages pyyaml 2>/dev/null || true
fi
python3 -c 'import yaml; print("PYYAML_OK")' 2>/dev/null || echo "PYYAML_MISSING"
```

If output is `PYYAML_MISSING`, ABORT and emit:

> "Scout's skill sync needs Python's pyyaml module, which couldn't
> auto-install. Run this in a terminal, then re-invoke the command:
>
> ```
> pip3 install --user pyyaml
> ```"

## Step 3: Run sync

First, Read `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`. Extract
the `version` field as a string (Read-tool path resolution; bash shell
expansion does not work for `${CLAUDE_PLUGIN_ROOT}` — see
[[project_plugin_root_no_shell_expansion]] for why).

Then run the sync, substituting `[PLUGIN_VERSION]` literally:

```bash
WORKSPACE_DIR="$HOME/claude-projects/sf-demo-scout" \
  PLUGIN_VERSION="[PLUGIN_VERSION]" \
  bash "${CLAUDE_PLUGIN_ROOT}/scripts/sync-skills.sh"
```

Surface the SYNCED / FAILED / PRUNED counts inline. On `FAILED_COUNT > 0`,
also print the FAILED= lines so the SE can see which skills broke.

## Step 4: Update config.json with last-synced version

```bash
CONFIG="$HOME/.config/sf-demo-scout/config.json"
if [ -f "$CONFIG" ]; then
  python3 - "$CONFIG" "[PLUGIN_VERSION]" <<'PYEOF'
import json, sys
path, version = sys.argv[1], sys.argv[2]
with open(path) as f:
    data = json.load(f)
data["last_synced_plugin_version"] = version
with open(path, "w") as f:
    json.dump(data, f, indent=2)
PYEOF
  echo "CONFIG_UPDATED"
else
  echo "CONFIG_MISSING"
fi
```

If `CONFIG_MISSING`, emit a one-line note ("Config not yet present —
run any other Scout command once to initialise.") but don't abort;
the sync itself succeeded.

## Step 5: Confirm to SE

> "Skills synced from upstream. [N] skills refreshed, [M] failed,
> [P] orphans pruned. Skills now live at
> `~/claude-projects/sf-demo-scout/.claude/skills/`."

If FAILED_COUNT > 0:

> "[N] skills failed to sync. The previous skill files (if any) are
> still in place. You can retry: `/scout-sync-skills`. If a specific
> upstream is broken, the manifest at
> `${CLAUDE_PLUGIN_ROOT}/skills-manifest.yaml` shows which repo + branch
> failed."
