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

## d: Refresh .zshrc managed block

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/zshrc-block.md` and execute it. Capture the result (`ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED`, plus optional `ANTHROPIC_MODEL_PRESENT`) — the orchestrator's done step needs it.

## Done

Refresh procedure complete. Return to the orchestrator. Pass the result of step d (`ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED`, plus optional `ANTHROPIC_MODEL_PRESENT`) so the done message can include the shell-refresh note.
