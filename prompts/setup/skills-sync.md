# Setup — Skills Sync

The orchestrator passes one parameter:
- `mode` — `strict` (fresh-install: PYYAML_MISSING aborts) or `soft` (refresh: PYYAML_MISSING surfaces note, continues).

Sync upstream skills via the manifest-driven `sync-skills.sh` script.

## Step 1: Ensure pyyaml

```bash
if ! python3 -c 'import yaml' 2>/dev/null; then
  pip3 install --quiet --user pyyaml 2>/dev/null || pip3 install --quiet --break-system-packages pyyaml 2>/dev/null || true
fi
python3 -c 'import yaml; print("PYYAML_OK")' 2>/dev/null || echo "PYYAML_MISSING"
```

On `PYYAML_MISSING`:
- `mode=strict`: ABORT:
  > "Scout's skill sync needs Python's pyyaml module, which couldn't auto-install. Run this in a terminal, then re-run `/scout-setup`:
  >
  > ```
  > pip3 install --user pyyaml
  > ```"
- `mode=soft`: surface the same note, then SKIP Step 2 and return to dispatcher (sync needs pyyaml). Refresh continues at the next step in the dispatching prompt.

## Step 2: Sync

Read `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`. Extract the `version` field as a string for `[PLUGIN_VERSION]`. ALSO resolve `${CLAUDE_PLUGIN_ROOT}` to its absolute filesystem path (the directory the plugin.json you just Read lives in, minus `/.claude-plugin`) and substitute as `[PLUGIN_ROOT]` below — `${CLAUDE_PLUGIN_ROOT}` does NOT expand inside Bash shell context, only inside Read-tool path arguments, so the bash invocation must receive the literal absolute path.

```bash
CLAUDE_PLUGIN_ROOT="[PLUGIN_ROOT]" \
  WORKSPACE_DIR="$HOME/claude-projects/sf-demo-scout" \
  PLUGIN_VERSION="[PLUGIN_VERSION]" \
  bash "[PLUGIN_ROOT]/scripts/sync-skills.sh"
```

Surface SYNCED/FAILED/PRUNED counts. On `FAILED_COUNT > 0`, also print FAILED= lines so the SE sees which skills broke. Do NOT abort — return to dispatcher.

## Done

Return to the dispatching prompt. Pass `[PLUGIN_VERSION]` back so the dispatcher can reuse it (avoids a second plugin.json read).
