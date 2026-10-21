# Setup — Salesforce Docs MCP readiness

Salesforce Docs grounds release checks and deploy-error research. Scout's
docs source is the Agentforce Labs Salesforce Docs MCP, a public server that
needs no account or token (https://labs.agentforce.com/docs/salesforce-docs-mcp).
This check reads first; it registers the server only on the builder's yes, and never
removes, repairs or authenticates anything.

Apply `prompts/host-runtime.md` and `prompts/mcp-readiness.md`. Select the active
host explicitly; substitute `[SCOUT_HOST]` with `claude`, `codex`, `cursor` or `unknown`.
Run from the active project directory so Codex sees its effective project policy.
Resolve the active Scout plugin root from the current plugin context. Use only
that concrete absolute path; do not search cached plugin versions or pass a
literal `${CLAUDE_PLUGIN_ROOT}` to the shell. Then run:

```bash
python3 -B "/absolute/path/of/active/sf-demo-scout/scripts/setup-mcp-status.py" --host "[SCOUT_HOST]" salesforce-docs
```

Use the host contract's `[PYTHON]` in place of `python3`. If Python or the helper
can't start, the status is
`MCP_STATUS provider=salesforce-docs registration=unknown transport=unknown`.

For Codex, interpret `policy`, `reason`, and `policy_id` using the shared
readiness procedure. `enabled` is not a connection check. On managed-policy
denial preserve the existing registration and hand its identity to workspace
support; do not suggest authentication or re-registration. Discover approved
session tools even when the CLI reports `not_observed` or is unavailable.

The registration command and `/mcp` instructions below are **Claude-only**. On
Codex and Cursor, offer the registration through `prompts/setup/other-hosts.md`
step 2 instead, and never run or offer `claude mcp add` or Claude OAuth flags
there. For an unknown host, report unknown and do not offer a host-specific
command.

Registration and transport do not prove that required tools are published.

- `registration=registered transport=connected` — say the server is registered
  and its transport reports connected. Discover the required Docs tools at the
  first Docs-dependent operation; only a successful real call establishes
  usability.
- `transport=authentication_required|failed|disabled|pending|unknown` — preserve
  the existing entry, report the state, and suggest inspecting it in `/mcp`.
  Do not remove or recreate it, even if its name or launcher is unfamiliar.
- `registration=ambiguous` — ask the builder to inspect `/mcp`; do not choose or
  modify an entry.
- `registration=not_observed|unknown` — explain that list output can omit
  entries, so this does not prove absence. Offer to add the Agentforce Labs
  Salesforce Docs MCP, in one plain question, and run this only on the builder's yes:

  ```text
  claude mcp add -s user --transport http salesforce-docs https://salesforce-docs-76258744c9d7.herokuapp.com/api/mcp
  ```

  On a no, carry on: items that need Docs are recorded as ungrounded until a
  docs source is available.

Return to the dispatching prompt.
