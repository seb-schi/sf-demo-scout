# Scout Setup — Refresh

Workspace already configured. Update CLIs, sync skills, refresh `.zshrc` block, bump config version.

**Idempotency contract:** every step below is idempotent and self-detecting. Re-running after an abort (e.g. SE returning from `/mcp` Slack auth) is safe and fast — completed steps fast-no-op via their own probes (`SLACK_MCP_ALREADY_REGISTERED`, `ZSHRC_UNCHANGED`, etc.). Always run end-to-end; do NOT skip steps trying to "resume" — the no-ops are the resume mechanism. Within the same CC session you may rely on conversation memory to fast-forward; across sessions, just run the full sequence — it will land in the right place naturally.

## a: Update Salesforce CLI

```bash
echo "UPDATING_SF_CLI"
npm install @salesforce/cli --global 2>&1 | tail -1
echo "SF_CLI_AT $(sf --version | head -1)"
```

## b: Update Claude Code CLI

```bash
echo "UPDATING_CLAUDE_CLI"
npm install @anthropic-ai/claude-code --global 2>&1 | tail -1
echo "CLAUDE_CLI_AT $(claude --version 2>/dev/null || echo 'unknown')"
```

If either npm command fails (non-zero exit), surface a one-line note ("[sf|claude] CLI update failed — continuing") and proceed. Don't abort.

## c: Slack MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/slack-mcp.md` and execute it with `mode=soft`. The prompt handles registration heal + auth probe; in soft mode failures surface notes and continue (heal-when-broken semantics). The `SLACK_MCP_REGISTERED` branch still aborts (TUI snapshot needs `/reload-plugins`).

## d: Sync upstream skills

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/skills-sync.md` and execute it with `mode=soft`. The prompt handles pyyaml install + skill sync; in soft mode `PYYAML_MISSING` surfaces a note and skips sync (refresh continues). Capture `[PLUGIN_VERSION]` (returned by the prompt) — step e needs it.

## e: Bump config.json `last_synced_plugin_version`

Substitute `[PLUGIN_VERSION]` with the value Read in step d:

```bash
python3 - "$HOME/.config/sf-demo-scout/config.json" "[PLUGIN_VERSION]" <<'PYEOF'
import json, sys
path, version = sys.argv[1], sys.argv[2]
with open(path) as f:
    data = json.load(f)
data["plugin_version"] = version
data["last_synced_plugin_version"] = version
with open(path, "w") as f:
    json.dump(data, f, indent=2)
PYEOF
echo "CONFIG_BUMPED"
```

## f: Refresh .zshrc managed block

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/zshrc-block.md` and execute it. Capture the result (`ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED`, plus optional `ANTHROPIC_MODEL_PRESENT`) — the orchestrator's done step needs it.

## Done

Refresh procedure complete. Return to the orchestrator. Pass the result of step f (`ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED`, plus optional `ANTHROPIC_MODEL_PRESENT`) so the done message can include the shell-refresh note.
