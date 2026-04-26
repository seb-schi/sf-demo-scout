# Audit Orchestration Procedure

Execute this procedure to run a fresh 3-agent parallel audit.

## Pre-Spawn Setup (orchestrator runs directly)

1. Clean stale fragments: `rm -f orgs/[alias]-[customer]/audit-fragment-*.md`
2. Initialize progress log — truncate the file and write a header so the SE-facing link opens to a non-empty file:
   ```
   printf "=== Audit started %s for %s ===\nSub-agents: standard-objects, apps-flows-agents, custom-objects\n\n" "$(date '+%Y-%m-%d %H:%M:%S')" "[alias]-[customer]" > orgs/[alias]-[customer]/.audit-progress.log
   ```
3. Resolve the current user Id: `run_soql_query` with `SELECT Id FROM User WHERE Username = '[username from Stage 2]' LIMIT 1`. Record as `CURRENT_USER_ID`.
4. Resolve the candidate default app — 2 SOQL queries:
   - `SELECT AppDefinitionId FROM UserAppInfo WHERE UserId = '[CURRENT_USER_ID]'`
   - `SELECT DurableId, Label, DeveloperName FROM AppDefinition WHERE DurableId = '[AppDefinitionId]'`
   Record the Label as `CANDIDATE_APP` and the DeveloperName as `CANDIDATE_APP_DEVELOPER_NAME`.

5. **Confirm with the SE before retrieve.** The user's currently-open app is not always the right audit surface — common offenders are SE home-bases like Q Branch, Demo Wizard, and setup apps that exist in most demo orgs but are out of scope for customer demos. Emit exactly this message, then wait for the SE's reply:

   > "Detected default app: **[CANDIDATE_APP]**. Audit into this app, or is a different app the demo surface? Reply `yes` to proceed, or name the app to audit instead (e.g. `Service Console`, `Sales`)."

   - If the SE replies `yes` (or equivalent): keep `CANDIDATE_APP` / `CANDIDATE_APP_DEVELOPER_NAME`.
   - If the SE names a different app: re-query `SELECT DurableId, Label, DeveloperName FROM AppDefinition WHERE Label = '[SE's input]' OR DeveloperName = '[SE's input]' LIMIT 1`. Replace `CANDIDATE_APP` / `CANDIDATE_APP_DEVELOPER_NAME` with the result. If the query returns 0 rows, tell the SE "No app matching `[input]` — reply with a different name or `skip` to audit core objects only" and loop.
   - If the SE replies `skip`: set `DEFAULT_APP` to "UNKNOWN" and `DEFAULT_APP_TABS` to the 6 core objects only. Skip step 6.

6. Retrieve the confirmed app's tabs: `retrieve_metadata` with type `CustomApplication`, member `[CANDIDATE_APP_DEVELOPER_NAME]`. Extract `<tabs>` elements.
   Record: `DEFAULT_APP` = `CANDIDATE_APP`, `DEFAULT_APP_DEVELOPER_NAME` = `CANDIDATE_APP_DEVELOPER_NAME`, `DEFAULT_APP_TABS` = list of tab API names.
   **On retrieve failure, short-circuit to core-6 immediately.** Set `DEFAULT_APP_TABS` to the 6 core objects only and continue. Do NOT attempt AppTabDefinition, AppMenuItem, or other Tooling API fallbacks — they are unreliable for custom/managed apps and waste orchestrator budget. The SE already confirmed the app name; a retrieve failure means the app's metadata is not accessible (managed package, permission boundary), and core-6 is the correct answer.

## Sub-Agent Dispatch

Read these 3 prompt templates:
- `.claude/prompts/audit-standard-objects.md`
- `.claude/prompts/audit-apps-flows-agents.md`
- `.claude/prompts/audit-custom-objects.md`

Read `.claude/prompts/audit-shared.md` once — its content fills `{{AUDIT_SHARED_RULES}}` in all 3 sub-agent prompts.

Fill placeholders in each: `{{ORG_ALIAS}}`, `{{ORG_USERNAME}}`, `{{CUSTOMER}}`, `{{YYYY-MM-DD}}`, `{{HHMM}}`, `{{DEFAULT_APP}}`, `{{DEFAULT_APP_TABS}}`, `{{AUDIT_SHARED_RULES}}`.

Spawn all 3 in parallel:
- `Agent(description="Org audit: standard objects", model="sonnet", prompt=[standard objects prompt])`
- `Agent(description="Org audit: apps/flows/agents", model="sonnet", prompt=[apps/flows/agents prompt])`
- `Agent(description="Org audit: custom objects", model="sonnet", prompt=[custom objects prompt])`

**Immediately after spawning, emit this SE-facing note** (single message, exactly this format — fill in the real path):

> Audit sub-agents running in parallel. Live status → [.audit-progress.log](orgs/[alias]-[customer]/.audit-progress.log) — click to open, VS Code auto-updates as sub-agents append. Typical runtime 5-10 min on SDO-scale orgs.

Then wait for all 3 to return. Do not read the progress log — it is SE-facing only.

## Post-Return Processing

As each sub-agent returns, extract the fenced JSON block. Parse it.
- `status: SUCCESS` or `status: PARTIAL` -> collect the JSON.
- `status: FAILED` or missing/malformed JSON -> flag that sub-agent's section as failed.
- If 2+ sub-agents fail -> show the raw outputs, ask the SE to retry in a fresh window or skip the audit entirely.

Check the standard-objects sub-agent's `demo_surface_notes` for non-universal standard objects with data — these hint at which industry cloud the org uses. Record for Stage 4.

## Spot-Check Pass (2 targeted queries — always run)

Run these SOQL queries in parallel:
- `SELECT COUNT() FROM BotDefinition` — agent count
- `SELECT COUNT() FROM FlowDefinitionView WHERE IsActive = true` — active flow count

Compare each against the sub-agent JSON fields:
- **Flow count:** compare against apps/flows/agents sub-agent's `active_flow_count`. Mismatch means the sub-agent's count query failed — flag it.
- **Agent count:** compare against apps/flows/agents sub-agent's `agents_found` array length. If spot-check finds >0 but sub-agent reported 0, query `SELECT DeveloperName, MasterLabel, Type FROM BotDefinition` and include the results in the consolidated summary.
- For any mismatch >20% or zero-vs-nonzero: flag to the SE: "Sub-agent reported [X] but spot-check found [Y]. The [section] may be incomplete."

Default app is not spot-checked here — the orchestrator resolved it authoritatively in pre-spawn setup.

## Consolidation (no raw markdown reading)

Merge the 3 JSON summaries + spot-check corrections into one consolidated summary:
- `default_app`: from orchestrator pre-spawn (ground truth)
- `default_app_tabs`: from orchestrator pre-spawn (ground truth)
- `active_layouts`: union of standard objects + custom objects sub-agent arrays
- `relevant_custom_objects`: from custom objects sub-agent
- `agents_found`: from apps/flows/agents sub-agent (corrected by spot-check if needed)
- `active_flow_count`: from spot-check (ground truth)
- `notable_gaps`: collect `issues` arrays from all 3 sub-agents
- `demo_surface_notes`: collect `demo_surface_notes` arrays from all 3 sub-agents

## Notable Gaps Narrative

Using the consolidated JSON summary — especially `demo_surface_notes` from all 3 sub-agents — write a "Notable Gaps and Risks" section. This is cross-cutting synthesis: what the org's metadata means for the demo scenario.

Concatenate fragment files:
```
cat orgs/[alias]-[customer]/audit-fragment-standard-objects.md \
    orgs/[alias]-[customer]/audit-fragment-apps-flows-agents.md \
    orgs/[alias]-[customer]/audit-fragment-custom-objects.md \
    > orgs/[alias]-[customer]/audit-[YYYY-MM-DD]-[HHMM].md
```

Append the Notable Gaps section (written by Opus from the JSON summaries) to the end of that file.

## Cleanup & Validation

1. Delete the 3 fragment files after successful concatenation.
2. **Star marker validation:** Grep the consolidated audit file for `★`. If 0 matches, flag to the SE: "The audit file has no ★ markers — build surface identification may have failed." Keep the progress log in place — SE may need the heartbeat history to debug which sub-agent failed to star-flag.
3. Delete the progress log — `rm -f orgs/[alias]-[customer]/.audit-progress.log`. Run this only after star-marker validation passes; on validation failure, leave the log so the SE can inspect sub-agent heartbeats.
