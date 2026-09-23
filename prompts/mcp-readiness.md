# MCP readiness in the active host

Use the active host and plugin root from `prompts/host-runtime.md`. This is a
read-only check; it does not register, remove, authenticate, or repair servers.

1. Discover the tools available in the current session, including approved
   connectors. Match the specific operations needed for this task and inspect
   their input schemas. A CLI listing cannot see every host-managed connector.
   Do not reject a usable session tool just because a CLI is missing or omits it.
2. When registration diagnosis is needed, run the shipped helper from the same
   project working directory as the active task. Substitute the host and one of
   `salesforce-dx`, `salesforce-docs`, `slack`, or `google`:

   ```bash
   python3 "/absolute/path/of/active/sf-demo-scout/scripts/setup-mcp-status.py" --host "[SCOUT_HOST]" "[PROVIDER]"
   ```

   If the helper/interpreter is missing, status is unknown. Do not reconstruct
   the probe or dump raw `codex mcp list --json`: it may contain credentials.
3. Interpret the independent fields:
   - `policy=blocked reason=managed_requirements`: preserve the registration;
     report the provider, active host, managed-requirements reason, and policy ID
     when emitted. Ask workspace support to review the exact existing server
     name and transport identity in the host's configuration UI. For Docs the
     reviewed identity is `salesforce-docs` at
     `https://salesforce-docs-76258744c9d7.herokuapp.com/api/mcp`. Authentication,
     renaming, proxies, or re-registration do not resolve a policy denial.
   - `reason=user_disabled`: report explicit disablement; leave the entry alone.
   - `reason=invalid_server_name`: report the packaging/configuration error;
     do not start an authentication flow.
   - `registration=ambiguous`: inspect matching entries without choosing one.
   - `registration=unknown|not_observed` or `reason=missing_cli|probe_failed`:
     this is inconclusive, not proof that the provider is absent or disconnected.
   - `transport=authentication_required|failed|disabled|pending`: report that
     exact observation. Suggest authentication only for an actual authentication
     failure, using the active host's controls.
   - `policy=permitted reason=enabled` in Codex describes effective
     configuration only. Startup, transport, authentication, and tool readiness
     remain unknown; inspect the active session's startup status if tools fail
     to appear. Claude's `transport=connected` also does not prove tool capability.
4. Proceed only with tools actually discovered for the required operation. When
   a tool is missing, report which capability is unavailable and use the
   caller's fallback or skip path. Do not diagnose every missing capability as
   an authentication problem. Only the first successful necessary call proves
   usability; never perform a write merely as a readiness test. For a requested
   canvas write, preserve the caller's existing approval step.

Historical `mcp__...` spellings in Scout prompts identify intended operations.
Use the active host's discovered names and schemas. A worker must discover its
own tools too; caller discovery does not guarantee worker tool exposure.
