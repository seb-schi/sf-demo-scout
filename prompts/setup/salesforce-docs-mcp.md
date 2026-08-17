# Setup — Salesforce Docs MCP (registration)

This prompt takes no parameters. Any failure surfaces a note and returns
(never aborts setup). The Salesforce Docs MCP powers `salesforce_docs_search`
/ `salesforce_docs_fetch` — release-gated feature checks and unfamiliar deploy
error recovery during sparring and building. The runtime already degrades
gracefully when it's absent, so setup does not hard-block on it.

**Why user scope, not `plugin.json`.** The server is a bare HTTP endpoint with
NO OAuth. Claude Code now runs an OAuth Dynamic Client Registration probe
(POST `/register`) by default for **plugin-manifest-declared** `type: http`
servers — the bare server has no `/register` route, so the probe 404s, the
server shows "needs authentication", and its tools never publish (transport
"Connected" ≠ tools available). Registering at **user scope**
(`claude mcp add -s user`) does NOT trigger that probe — same URL, clean
connect. So Docs lives in `~/.claude.json` alongside Slack and Google, not in
the plugin manifest. The server name is `salesforce-docs` — the
vendor-canonical name from Salesforce's official Claude Code install command
(matching it lets Scout and the LS Booster Pack co-register on ONE server
instead of colliding).

## Step 1: Registration (idempotent)

```bash
if claude mcp list 2>/dev/null | grep -qE '^[[:space:]]*salesforce-docs[[:space:]]*:'; then
  echo "SFDOCS_MCP_ALREADY_REGISTERED"
else
  if claude mcp add -s user --transport http \
      salesforce-docs https://salesforce-docs-76258744c9d7.herokuapp.com/api/mcp >/dev/null 2>&1; then
    echo "SFDOCS_MCP_REGISTERED"
  else
    echo "SFDOCS_MCP_REGISTRATION_FAILED"
  fi
fi
```

Surface inline:

- `SFDOCS_MCP_ALREADY_REGISTERED` — silent. Done.
- `SFDOCS_MCP_REGISTERED` — Salesforce Docs was just registered mid-session.
  The `/mcp` TUI uses an in-memory snapshot from session start and won't show
  the new server until plugins reload. Surface and return:
  > "Registered the Salesforce Docs MCP (user scope) — this is what lets Scout
  > verify release-gated features and diagnose deploy errors against the real
  > docs. Run `/reload-plugins` now to make it live (no auth needed — it's a
  > bare HTTP server). Then re-run `/scout-setup` anytime to finish up."
- `SFDOCS_MCP_REGISTRATION_FAILED` — surface and CONTINUE:
  > "⚠️ Salesforce Docs MCP registration failed — release-gated feature checks
  > and deploy-error doc lookups will be skipped until it's connected (Scout
  > degrades gracefully). Run manually, then re-run `/scout-setup` anytime:
  >
  > ```
  > claude mcp add -s user --transport http salesforce-docs https://salesforce-docs-76258744c9d7.herokuapp.com/api/mcp
  > ```
  > Setup continues."

## Done

Return to the dispatching prompt.
