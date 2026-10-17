# MCP readiness in the active host

Use the active host and plugin root from `prompts/host-runtime.md`. This check is read-only: it never registers, removes, authenticates or repairs a server.

1. **Use the exposed tools.** Discover the tools in the current session, approved connectors included, match the operations this task needs and inspect their input schemas. A CLI listing can't see every host-managed connector, so never reject a usable session tool because a CLI is missing or omits it. Historical `mcp__...` spellings in Scout prompts name intended operations; use the discovered names and schemas. A worker discovers its own tools: the caller's discovery doesn't guarantee what the worker sees.
2. **Diagnose registration only when needed,** with the shipped helper, run from the active task's project folder. Substitute the host and one of `salesforce-docs`, `slack` or `google`:

   ```bash
   python3 "/absolute/path/of/active/sf-demo-scout/scripts/setup-mcp-status.py" --host "[SCOUT_HOST]" "[PROVIDER]"
   ```

   If the helper or its interpreter is missing, the status is unknown. Don't reconstruct the probe, and never dump raw diagnostics such as `codex mcp list --json`: they may carry credentials.
3. **Read the fields as observations:**
   - `policy=blocked reason=managed_requirements`: keep the registration; report the provider, host, reason and any policy ID, and hand the server's exact name and transport identity to workspace support. Authentication, renaming, proxies or re-registration don't resolve a policy denial.
   - `reason=user_disabled`: an explicit disablement. Report it and leave the entry alone.
   - `reason=invalid_server_name`: a packaging or configuration error; start no authentication flow.
   - `registration=ambiguous`: inspect the matching entries without choosing one.
   - `registration=unknown|not_observed` or `reason=missing_cli|probe_failed`: inconclusive. Unknown isn't absent or disconnected.
   - `transport=authentication_required|failed|disabled|pending`: report that exact observation. Suggest authentication only for an actual authentication failure, through the host's own controls.
   - Codex's `policy=permitted reason=enabled` describes configuration, and Claude's `transport=connected` describes transport. Neither proves the tools work; if they don't appear, check the session's startup status.
4. **Proceed only with tools actually discovered** for the operation. When one is missing, name the unavailable capability and use the caller's fallback or skip path; not every missing tool is an authentication problem. Only the first successful necessary call proves usability, so never write merely to test readiness. A requested canvas write keeps the caller's approval step.
