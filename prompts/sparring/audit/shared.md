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
- **Reading back a `retrieve_metadata` result: read the CONVERTED source path, not the result-JSON `fileName`.** The SE workspace (`~/claude-projects/sf-demo-scout/`) is a source-format SFDX project (it has `force-app/` and `sfdx-project.json`), so `retrieve_metadata` converts what it pulls into source format under `force-app/main/default/<type-dir>/`. The `fileName` field in the tool's result JSON (e.g. `unpackaged/applications/Field_Sales.app`) is the in-ZIP MDAPI path and does NOT exist on disk — reading it fails. To read retrieved XML, use the converted path: `force-app/main/default/<type-dir>/<FullName>.<ext>-meta.xml`. Common type-dirs: CustomApplication → `applications/<Name>.app-meta.xml`; CustomObject → `objects/<Name>/<Name>.object-meta.xml`; Profile → `profiles/<Name>.profile-meta.xml`; FlexiPage → `flexipages/<Name>.flexipage-meta.xml`; Layout → `layouts/<Name>.layout-meta.xml`. If a read still misses (unusual conversion target), `find force-app/main/default -name '<Name>*'` ONCE to locate it — do not loop. Pass `directory` = the SE workspace root to `retrieve_metadata` so conversion lands in this project's `force-app/`.
- **Working-file location: `{{SCOUT_TMPDIR}}` only.** Every transient file you write during the audit — ad-hoc `package.xml`-style manifests, intermediate XML chunks, anything that isn't your output fragment or a progress-log line — goes inside `{{SCOUT_TMPDIR}}` (an absolute path the orchestrator passes in via the envelope). Name manifests `manifest-audit-<scope>.xml` (e.g. `manifest-audit-layouts.xml`) and pass the full path `{{SCOUT_TMPDIR}}/manifest-audit-<scope>.xml` as the `manifest` argument to `retrieve_metadata`. Do NOT write working files at the repo root (`~/claude-projects/sf-demo-scout/`) and do NOT write them at the customer folder root (`{{ORG_FOLDER}}/`) — those locations are for SE-visible artifacts (audit outputs, progress log, deployment scaffolding). The orchestrator wipes `{{SCOUT_TMPDIR}}` (via `find … -delete`) on entry and on successful exit, so anything inside is treated as disposable scratch.

## Progress Log — failures only

The audit runs in the BACKGROUND while the SE answers discovery questions. Each `echo >> .audit-progress.log` you run renders as a Bash card in the SE's main chat (the VS Code extension streams background sub-agent tool calls inline — there is no harness knob to suppress this). Routine per-section heartbeats therefore crowd out the SE's discovery prompts with no benefit, because the SE is busy answering questions, not watching the log. So: **do NOT emit routine progress heartbeats.** Do not announce `starting`, per-section completions, `writing fragment`, or `done`.

**Emit ONE log line only on a section FAILURE**, so a failed audit is still debuggable from the log:
```
Bash: echo "[$(date +%H:%M:%S)] [<your-agent-id>] ⚠️ <section>: <one-line reason>" >> {{ORG_FOLDER}}/.audit-progress.log
```
Your agent-id is declared at the top of your prompt (`Progress log agent-id:`). Use it verbatim. Never read this file back. Continue with your normal fallbacks after logging — the failure line is in addition to, not instead of, your error handling. Opus does not read this file; the orchestrator writes coarse phase markers to it separately.
