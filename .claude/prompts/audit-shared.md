# Audit Sub-Agent — Shared Rules

All 3 audit sub-agents (standard objects, apps/flows/agents, custom objects) follow the rules below. The orchestrator injects this fragment via the `{{AUDIT_SHARED_RULES}}` placeholder in each sub-agent prompt.

## Overflow File Handling

When an MCP tool result exceeds the character limit, the harness saves it to a temp
file and tells you the path. **Do not skip the section.** Instead:
1. Read the temp file in chunks (use the Read tool with offset/limit).
2. If the file contains JSON, use Bash with `python3 -c` or `jq` to extract the fields you need.
3. If the file is too large even for chunked reading, narrow your original query (add WHERE clauses, reduce fields) and retry.
4. Only report "could not enumerate" after at least one parse attempt on the overflow file.

## Fallback Rule

If any discovery query returns 0 records or fails with an error, try at least one alternative method before reporting "none found":
- If SOQL fails → try `retrieve_metadata` with the corresponding metadata type
- If `retrieve_metadata` fails → try SOQL on the corresponding sObject
- If both fail → report "none found" with both methods attempted and error messages

Never report an empty section based on a single failed or empty query.

## Working Pattern

- Retrieve metadata in small batches.
- Write the output file as a single Write at the end — your scope is bounded enough to fit the output cap.
- If a single retrieve call returns an unmanageable payload, narrow the query and continue.
