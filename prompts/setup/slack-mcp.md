# Setup — Slack MCP readiness

Slack is optional. It supports canvas and channel lookups, and Scout degrades
when its tools are unavailable. This check is read-only: it never registers,
removes, repairs, authenticates, or reads credentials.

Apply `prompts/host-runtime.md` and `prompts/mcp-readiness.md`. Select the active
host explicitly; substitute `[SCOUT_HOST]` with `claude`, `codex`, or `unknown`.
Run from the active project directory so Codex sees its effective project policy.
Resolve the active Scout plugin root from the current plugin context. Use only
that concrete absolute path; do not search cached plugin versions or pass a
literal `${CLAUDE_PLUGIN_ROOT}` to the shell. Then run:

```bash
SCOUT_MCP_STATUS="/absolute/path/of/active/sf-demo-scout/scripts/setup-mcp-status.py"
if [ -f "$SCOUT_MCP_STATUS" ] && command -v python3 >/dev/null 2>&1; then
  python3 "$SCOUT_MCP_STATUS" --host "[SCOUT_HOST]" slack
else
  echo "MCP_STATUS provider=slack registration=unknown transport=unknown"
fi
```

For Codex, interpret `policy`, `reason`, and `policy_id` using the shared
readiness procedure. `enabled` is not a connection check. On managed-policy
denial preserve the existing registration and hand its identity to workspace
support; do not suggest authentication or re-registration. Discover approved
session tools even when the CLI reports `not_observed` or is unavailable.

The registration commands and `/mcp` authentication instructions below are
**Claude-only**. On Codex use its installed connector/MCP controls and the
organization-approved configuration; do not run or offer `claude mcp add`,
Claude OAuth flags, or DevBar authentication as a Codex policy remedy.
For an unknown host, report unknown and do not offer a host-specific command.

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
- `registration=not_observed|unknown` — explain that the active host's listing can omit
  entries, so this does not prove absence. Offer this last-known default only as
  an explicit SE choice; never run it automatically:

  ```text
  claude mcp add -s user -t http --client-id 188160004832.9210129962818 --callback-port 3118 slack https://mcp.slack.com/mcp
  ```

The client id and callback port are reviewed Scout defaults, not universal
compatibility claims. After any SE-chosen registration, they can reload plugins
and use `/mcp` to authenticate. Return to the dispatching prompt.
