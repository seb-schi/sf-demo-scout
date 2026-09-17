# Setup — Slack MCP readiness

Slack is optional. It supports canvas and channel lookups, and Scout degrades
when its tools are unavailable. This check is read-only: it never registers,
removes, repairs, authenticates, or reads credentials.

Resolve the active Scout plugin root from the current plugin context. Use only
that concrete absolute path; do not search cached plugin versions or pass a
literal `${CLAUDE_PLUGIN_ROOT}` to the shell. Then run:

```bash
SCOUT_MCP_STATUS="/absolute/path/of/active/sf-demo-scout/scripts/setup-mcp-status.py"
if [ -f "$SCOUT_MCP_STATUS" ] && command -v python3 >/dev/null 2>&1; then
  python3 "$SCOUT_MCP_STATUS" slack
else
  echo "MCP_STATUS provider=slack registration=unknown transport=unknown"
fi
```

The helper emits fixed vocabulary only. Registration and transport are not
proof of authentication or tool capability.

- `registration=registered transport=connected` — say Slack is registered and
  its transport reports connected. At the first Slack-dependent operation,
  discover the required tools; only a successful real call establishes usability.
- `transport=authentication_required` — ask the SE to run `/mcp`, select the
  existing Slack entry, and authenticate. Do not start auth yourself.
- `transport=failed|disabled|pending|unknown` — preserve the existing entry.
  Report its state and suggest inspecting it in `/mcp`; never remove or recreate
  an unfamiliar or unhealthy connection.
- `registration=ambiguous` — say more than one entry may match Slack and ask the
  SE to inspect `/mcp`. Do not choose or modify one.
- `registration=not_observed|unknown` — explain that `claude mcp list` can omit
  entries, so this does not prove absence. Offer this last-known default only as
  an explicit SE choice; never run it automatically:

  ```text
  claude mcp add -s user -t http --client-id 188160004832.9210129962818 --callback-port 3118 slack https://mcp.slack.com/mcp
  ```

The client id and callback port are reviewed Scout defaults, not universal
compatibility claims. After any SE-chosen registration, they can reload plugins
and use `/mcp` to authenticate. Return to the dispatching prompt.
