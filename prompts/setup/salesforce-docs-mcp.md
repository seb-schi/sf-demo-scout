# Setup — Salesforce Docs MCP readiness

Salesforce Docs is optional and supports release checks and deploy-error
research. This check is read-only: it never registers, removes, repairs, or
attempts authentication.

Resolve the active Scout plugin root from the current plugin context. Use only
that concrete absolute path; do not search cached plugin versions or pass a
literal `${CLAUDE_PLUGIN_ROOT}` to the shell. Then run:

```bash
SCOUT_MCP_STATUS="/absolute/path/of/active/sf-demo-scout/scripts/setup-mcp-status.py"
if [ -f "$SCOUT_MCP_STATUS" ] && command -v python3 >/dev/null 2>&1; then
  python3 "$SCOUT_MCP_STATUS" salesforce-docs
else
  echo "MCP_STATUS provider=salesforce-docs registration=unknown transport=unknown"
fi
```

Registration and transport do not prove that required tools are published.

- `registration=registered transport=connected` — say the server is registered
  and its transport reports connected. Discover the required Docs tools at the
  first Docs-dependent operation; only a successful real call establishes
  usability.
- `transport=authentication_required|failed|disabled|pending|unknown` — preserve
  the existing entry, report the state, and suggest inspecting it in `/mcp`.
  Do not remove or recreate it, even if its name or launcher is unfamiliar.
- `registration=ambiguous` — ask the SE to inspect `/mcp`; do not choose or
  modify an entry.
- `registration=not_observed|unknown` — explain that list output can omit
  entries, so this does not prove absence. Offer this last-known default only as
  an explicit SE choice; never run it automatically:

  ```text
  claude mcp add -s user --transport http salesforce-docs https://salesforce-docs-76258744c9d7.herokuapp.com/api/mcp
  ```

The endpoint is a reviewed Scout deployment default, not a universal
compatibility claim. Return to the dispatching prompt.
