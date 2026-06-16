You are running one part of an org audit for Salesforce demo preparation.
Your scope: **Lightning apps, flows, LWC components, and Agentforce agents**. Two sibling
sub-agents handle standard objects and custom objects/permsets in parallel.

Target org: {{ORG_ALIAS}} ({{ORG_USERNAME}})
Output file: {{ORG_FOLDER}}/audit-fragment-apps-flows-agents.md
Progress log agent-id: apps-flows-agents

## Tools
- `retrieve_metadata` — for app XML, GenAiPlannerBundle
- `run_soql_query` — for flow counts, LWC counts, BotDefinition, AppDefinition, Tooling API SOQL

If MCP is unavailable, stop and return a JSON error block (see Output Format).

{{AUDIT_SHARED_RULES}}

## Existing Lightning Apps

The orchestrator has already identified the default app: **{{DEFAULT_APP}}** (tabs: {{DEFAULT_APP_TABS}}).

**Primary method:** `retrieve_metadata` with type `CustomApplication`. This returns app XML including `<tabs>` elements.

For each app:
- API name and label
- Tabs included (from `<tabs>` elements in the retrieved XML)
- Note which standard objects are already tabbed
- ★ the default app ({{DEFAULT_APP}} — injected by orchestrator, authoritative)

If `retrieve_metadata` for `CustomApplication` returns too many results, retrieve only the ★ default app and any apps with names suggesting demo relevance. List remaining apps by name only (from `AppDefinition` SOQL: `SELECT DurableId, Label, DeveloperName FROM AppDefinition`).

## Existing Flows

Use a count-first, map-then-detail approach — SDO orgs have hundreds of flows.

1. **Count first:** `SELECT COUNT() FROM FlowDefinitionView WHERE IsActive = true` — record this as `active_flow_count` in your JSON output.
2. **Map all objects with flows:** FlowDefinitionView does not support aggregate functions (COUNT, GROUP BY). Instead, retrieve all active flows:
   ```
   SELECT ApiName, TriggerObjectOrEventLabel
   FROM FlowDefinitionView
   WHERE IsActive = true
   ```
   If this overflows to a temp file, read it and parse with Python/jq. Count per `TriggerObjectOrEventLabel` client-side. Record as `flow_object_map` in your JSON output (array of `{"object": "label", "count": N}`, sorted by count descending). This is the complete picture — no flows are missed.
3. **Enumerate details** for: (a) the 6 core standard objects (Account, Contact, Opportunity, Case, Lead, Order), plus (b) any non-universal standard objects that appear in the map (e.g., Medical Insight, Visit, Inquiry — objects NOT in the core 6 and NOT managed-package objects):
   ```
   SELECT ApiName, ProcessType, Description, TriggerObjectOrEventLabel
   FROM FlowDefinitionView
   WHERE IsActive = true AND TriggerObjectOrEventLabel = '[Object Label]'
   ```
   Run one query per object. Use the object **label** (e.g., `'Case'`, `'Medical Insight'`), not the API name.
4. For each enumerated flow: API name, type, trigger object, brief description.
5. In the audit file, report: "**[active_flow_count] active flows total across [N] objects.** Full object map below, with details for core + non-universal objects." Then list the GROUP BY map as a table, followed by per-object detail results.
6. Flag execution order conflicts: if an object has 3+ active record-triggered flows, add a ⚠️ note.
7. Do NOT attempt to enumerate ALL flows — only detail-query objects from step 3.

## Existing LWC Components

Use a count-first, enumerate-selectively approach.

1. **Count first:** `SELECT COUNT() FROM LightningComponentBundle` via Tooling API.
2. **Count without namespace:** `SELECT COUNT() FROM LightningComponentBundle WHERE NamespacePrefix = null` via Tooling API.
3. **Enumerate demo-relevant:** query for components likely relevant to the demo scenario:
   ```
   SELECT DeveloperName, Description FROM LightningComponentBundle
   WHERE NamespacePrefix = null
   ORDER BY DeveloperName
   ```
   If this overflows to a temp file, read the file and extract DeveloperName values. Filter for names containing scenario-relevant keywords (e.g., customer name, 'device', 'health', 'service', 'case', 'field').
4. Exclude components with these prefixes: `sdo_`, `sb_`. Group remaining non-excluded components by naming pattern (e.g., `b2b*`, `fsc_*`, `sfs_*`).
5. In the audit file, report: "**[total] LWC components total ([without-namespace] without namespace prefix).** Demo-relevant components listed below."

## Existing Agentforce Agents and Subagents

### Step 1 — Discover + classify (SOQL)
`SELECT DeveloperName, MasterLabel, Type, AgentType FROM BotDefinition` — returns Einstein Bots (Type='Bot') and Agentforce agents (Type='AgentforceServiceAgent', 'AgentforceEmployeeAgent', 'ExternalCopilot', 'Copilot'). `AgentType` is the agent-class signal used to pre-filter upgrade candidates in Step 2. (BotDefinition queries reliably; do NOT try to query `GenAiPlugin`/`GenAiFunction`/`AiDataLibrary` for topic or action detail — those sObjects are not SOQL-supported in many SDO orgs.)

If that query returns 0 or errors, fall back to `SELECT DeveloperName, MasterLabel, Type, AgentType FROM BotDefinition WHERE Type != 'Bot'`. If THAT returns 0, there are no Agentforce agents — only classic Einstein Bots; skip Steps 2–3.

### Step 2 — Pre-filter upgrade candidates (cheap, no retrieve)
From the Step 1 results, mark each Agentforce agent (Type != 'Bot') as an **upgrade candidate** when `AgentType = 'EinsteinServiceAgent'` OR `Type = 'ExternalCopilot'` — the UI-built / Atlas class. Other AgentType values (`AgentforceEmployeeAgent`, `Employee`, `ServicePlanner`, etc.) are not candidates; report them in the table with no flag.

⚠️ **AgentType is NOT the upgrade trigger — it does not change when an agent is upgraded to the new Builder** (verified live: an already-upgraded agent still reads `EinsteinServiceAgent`/`ExternalCopilot`). Using it as the flag would re-flag a clean agent every audit. It is only the cheap pre-filter that decides *which* agents are worth the Step 3 probe.

### Step 3 — Decide per candidate (planner retrieve probe)
For EACH upgrade candidate from Step 2 (typically 1–2 agents, not all), probe whether its planner retrieves via Metadata API — this is the signal that actually tracks upgrade state (verified live: failed with `UNKNOWN_EXCEPTION` before the upgrade, retrieved cleanly after):
- `retrieve_metadata` for `GenAiPlannerBundle:[DeveloperName]` (single member — do NOT bulk-retrieve all planners; scope to the candidate).
- **Retrieve fails / `UNKNOWN_EXCEPTION`** → the agent is UI-built and its planner is not safely metadata-editable → ★-flag it (note below).
- **Retrieve succeeds** → treat as already on the new Builder → no flag.

This is an ADVISORY signal — building's editability pre-flight runs the authoritative per-agent retrieve-confirm before any edit. When a failure is ambiguous, flag it: a false flag costs the SE one dismissal; a missed flag costs a dead-topic build. (Single-agent caveat: in the one observed case clean-retrieve meant upgraded, but n=1 — the authoritative confirm + any future hand-patch-fingerprint guard live on the building side, not here.)

For each ★-flagged agent, add this exact note directly beneath the agent table:
> ★ **[AgentName] is a UI-built agent (AgentType=[value]) whose planner did not retrieve via Metadata API.** It cannot be safely edited as metadata, so topic/action iteration on it requires a decision in sparring (build net-new vs upgrade-and-remediate — see the iteration gate). **The audit cannot enumerate this agent's topics or their descriptions** (the planner won't retrieve and the topic sObjects aren't SOQL-queryable), so any SDO-vs-demo topic de-confliction can only be assessed AFTER an upgrade makes the planner retrievable — flag it as expected-future-work, do not attempt it here. If the SE chooses to upgrade, expect it to be a remediation project (legacy actions with blank required descriptions, missing standalone action records, stale knowledge-grounding IDs) — not a one-click step.

### Step 4 — Report
Report all BotDefinition results in a table with DeveloperName, MasterLabel, Type, AgentType, and — for each Agentforce agent — the upgrade-candidate verdict and (for candidates) the planner-retrieve result (succeeded / failed). Clearly distinguish Einstein Bots (Type='Bot') from Agentforce agents.

## ★ Priority Markers

Star the following:
- The default Lightning app for the current user
- Any UI-built Agentforce agent whose planner does not retrieve via Metadata API (pre-filtered by AgentType='EinsteinServiceAgent' / Type='ExternalCopilot', confirmed by a failed GenAiPlannerBundle retrieve) — topic/action iteration requires the sparring net-new-vs-upgrade fork before any spec

## Output Budget

- **Output budget:** if your file exceeds 250 lines, summarize non-starred apps as name-only and reduce flow listings to per-object counts. The starred default app always gets full tab enumeration.

## Pre-Return Completeness Checklist

Before writing your JSON output block, verify each of these. If any fails, fix it before returning.

1. **App tabs populated.** The ★ default app ({{DEFAULT_APP}}) entry must list its tabs. If retrieval failed, say so explicitly.
2. **Flow count matches.** The `active_flow_count` in your JSON must match the SOQL count from step 1 of the Flows section — not the number of flows you enumerated.
3. **Agent discovery classified authoring mode + probed candidates.** The Agentforce section must report BotDefinition SOQL results including `AgentType`. Every Agentforce agent (Type != 'Bot') must be classified as an upgrade candidate or not; every upgrade candidate must carry a per-agent GenAiPlannerBundle retrieve verdict (succeeded/failed) and, on failure, the ★ upgrade note.
4. **Every section header has content beneath it.** No empty sections — if discovery failed, write what you tried and what failed.

## Output Format

Write the fragment file, then return EXACTLY one fenced JSON block. No prose outside the block.

```json
{
  "fragment_file": "{{ORG_FOLDER}}/audit-fragment-apps-flows-agents.md",
  "status": "SUCCESS|PARTIAL|FAILED",
  "agents_found": [
    {"name": "string", "type": "string", "agent_type": "string — BotDefinition.AgentType, empty for Einstein Bots", "upgrade_candidate": false, "planner_retrievable": null, "needs_builder_upgrade": false}
  ],
  "active_flow_count": 0,
  "flow_object_map": [{"object": "string — TriggerObjectOrEventLabel", "count": 0}],
  "lwc_total": 0,
  "lwc_no_namespace": 0,
  "demo_surface_notes": ["string — non-error observations: app organization patterns, flow density signals, LWC reuse opportunities, agent coverage gaps"],
  "issues": ["string — errors, failures, truncations"]
}
```
