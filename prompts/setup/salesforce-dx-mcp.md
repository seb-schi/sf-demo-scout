# Setup — Salesforce DX MCP readiness

`sf` is the machine-installed Salesforce CLI. Scout separately declares
`Salesforce_DX` in its plugin manifest; the active host starts that adapter with
`npx -y @salesforce/mcp`. An installed CLI or successful adapter pre-cache does
not prove the host started the MCP client or discovered its tools.

Apply `prompts/host-runtime.md` and `prompts/mcp-readiness.md`. Resolve the active
plugin root, substitute `[SCOUT_HOST]`, and run from the active project:

```bash
SCOUT_MCP_STATUS="/absolute/path/of/active/sf-demo-scout/scripts/setup-mcp-status.py"
if [ -f "$SCOUT_MCP_STATUS" ] && command -v python3 >/dev/null 2>&1; then
  python3 "$SCOUT_MCP_STATUS" --host "[SCOUT_HOST]" salesforce-dx
else
  echo "MCP_STATUS provider=salesforce-dx registration=unknown transport=unknown"
fi
```

Discover the DX tools in the current session. If `invalid_server_name` is
reported for an installed older Scout version, update Scout through the active
host's normal plugin update flow and start a fresh session. Do not edit the
installed cache or add a competing standalone registration. If policy blocks
the registration, preserve it and report the administrative restriction.

When startup or required tools are unavailable, report that observation and
retain the `sf` fallback. Do not authenticate or choose an org solely for this
check. Only a necessary read against the SE's explicitly selected, authorized
org establishes operation success. Return this status to the setup summary.
