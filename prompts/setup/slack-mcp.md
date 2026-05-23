# Setup — Slack MCP (registration + auth probe)

The orchestrator passes one parameter:
- `mode` — `strict` (fresh-install: any failure aborts setup) or `soft` (refresh: failures surface a note and continue).

Slack MCP is user-scope (lives in `~/.claude.json`, not `plugin.json`) because it requires per-SE OAuth. The OAuth `client-id` and `callback-port` are required for the auth flow to work — bare URL is not enough. Lifted from pre-plugin `install.sh` §7.

## Step 1: Registration (idempotent)

```bash
if claude mcp list 2>/dev/null | grep -qE '^[[:space:]]*slack[[:space:]]*:'; then
  echo "SLACK_MCP_ALREADY_REGISTERED"
else
  if claude mcp add -s user -t http \
      --client-id 188160004832.9210129962818 \
      --callback-port 3118 \
      slack https://mcp.slack.com/mcp >/dev/null 2>&1; then
    echo "SLACK_MCP_REGISTERED"
  else
    echo "SLACK_MCP_REGISTRATION_FAILED"
  fi
fi
```

Surface inline:

- `SLACK_MCP_ALREADY_REGISTERED` — silent. Proceed to Step 2.
- `SLACK_MCP_REGISTERED` — Slack was just registered mid-session. The `/mcp` TUI uses an in-memory snapshot taken at session start and won't show the new server until plugins reload. **ABORT regardless of mode** (TUI snapshot blocks the auth flow either way):
  > "Registered Slack MCP. Run `/reload-plugins` now, then run `/mcp`, select 'slack', and select 'Authenticate'. Choose 'Salesforce Internal' from the Workspace dropdown menu, then select 'Allow'.
  >
  > Once finished, return here and re-run `/scout-setup` to finish up."

  In `soft` mode the message wording shifts slightly (refresh path is heal-when-broken):
  > "Re-registered Slack MCP (was missing — likely manual removal). Run `/reload-plugins` now, then run `/mcp`, select 'slack', and select 'Authenticate'. Choose 'Salesforce Internal' from the Workspace dropdown menu, then select 'Allow'.
  >
  > Once finished, return here and re-run `/scout-setup` to finish up."

  Skip Step 2 on this branch — the TUI doesn't have the row yet, so probing is pointless.
- `SLACK_MCP_REGISTRATION_FAILED` —
  - `mode=strict`: surface and ABORT:
    > "Slack MCP registration failed. Run this manually, then re-run `/scout-setup`:
    >
    > ```
    > claude mcp add -s user -t http --client-id 188160004832.9210129962818 --callback-port 3118 slack https://mcp.slack.com/mcp
    > ```"
  - `mode=soft`: surface and CONTINUE to Step 2:
    > "⚠️ Slack MCP registration failed during refresh. Run manually: `claude mcp add -s user -t http --client-id 188160004832.9210129962818 --callback-port 3118 slack https://mcp.slack.com/mcp`. Refresh continues."

## Step 2: Auth probe

```bash
security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null | \
  python3 -c "import json,sys; d=json.loads(sys.stdin.read()); oauth=d.get('mcpOAuth',{}); slack=[k for k in oauth if k.startswith('slack')]; tok=oauth[slack[0]].get('accessToken') if slack else None; print('authenticated' if tok else 'needs_auth')" 2>/dev/null || echo "needs_auth"
```

On `authenticated` — silent. Done.

On `needs_auth`:
- `mode=strict`: ABORT:
  > "Slack MCP needs authentication before Scout setup can finish. It powers customer canvas lookups during sparring and the post-deployment handover canvas.
  >
  > Run `/mcp`, select 'slack', and select 'Authenticate'. Choose 'Salesforce Internal' from the Workspace dropdown menu, then select 'Allow'.
  >
  > Once finished, return here and re-run `/scout-setup` to finish up."
- `mode=soft`: surface and CONTINUE:
  > "⚠️ Slack MCP needs re-authentication. Run `/mcp` → 'slack' → 'Authenticate' when convenient. Refresh continues."

## Done

Return to the dispatching prompt.
