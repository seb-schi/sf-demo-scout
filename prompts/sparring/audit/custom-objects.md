You are running one part of an org audit for Salesforce demo preparation.
Your scope: **custom objects and custom permission sets**. Two sibling sub-agents
handle standard objects and apps/flows/agents/LWC in parallel.

Target org: {{ORG_ALIAS}} ({{ORG_USERNAME}})
Output file: orgs/{{ORG_ALIAS}}-{{CUSTOMER}}/audit-fragment-custom-objects.md
Progress log agent-id: custom-objects

Active LRP map for this org's default app: {{ACTIVE_LRP_MAP}} — this is the **custom-object-scoped slice** prepared by the orchestrator. Every entry's `object` ends in `__c`. **Standard-object LRPs (Case, Account, Opportunity, Lead, Contact, Order, ServiceResource, MessagingSession, etc.) are owned by the sibling standard-objects sub-agent — never emit `active_lrps` entries for them, even if a stale or unsliced map happens to include one.** If you see a non-`__c` entry in `{{ACTIVE_LRP_MAP}}`, drop it silently and add a `discovery_notes` entry: `"ACTIVE_LRP_MAP contained non-custom entry [Object] — orchestrator slice may have drifted"`.

**Two independent axes — do not conflate them:**

- **Enumeration scope** (which custom objects this fragment covers) is driven by your own discovery query below, NOT by `{{ACTIVE_LRP_MAP}}`. A custom object is in scope if it is unmanaged AND has any of: record_count > 0, looks demo-relevant by naming pattern (industry terms, customer name, scenario keywords), or appears in `{{ACTIVE_LRP_MAP}}`. The LRP map is one input to relevance, not the gate.

- **LRP classification scope** (which `active_lrps` entries this fragment emits) is bounded strictly by `{{ACTIVE_LRP_MAP}}`. Only objects in the sliced map get `active_lrps` entries.

Concretely: if the discovery query surfaces `AI_Agent__c` (record_count > 0, demo-relevant) but it is NOT in `{{ACTIVE_LRP_MAP}}`, the object IS enumerated (record count, layout, fields, related lists) and gets NO `active_lrps` entry. If `Reply_Rec_Demo_Helper__c` is in `{{ACTIVE_LRP_MAP}}` AND demo-relevant by enumeration, it gets BOTH — full object enumeration AND an `active_lrps` entry.

For each in-scope (`__c`) LRP-map entry whose `object` matches a custom object you classify as demo-relevant, apply the same composition classification treatment as the standard-objects sub-agent:

- For `system_default` entries (lrp is null): no FlexiPage retrieve. Record `composition_class: "system_default", gap_risk: false, field_sections: []` and proceed. The classic Page Layout add is the right surface.
- For all other entries: retrieve the LRP XML and classify by `force:detailPanel` vs `flexipage:fieldSection`, ★🚨 if `gap_risk: true`, enumerate field sections using the same Facet-indirection traversal as standard-objects (see its "Active Lightning Record Page per Object — composition classification" section for the canonical procedure — same XML shape, same column resolution).

Each entry in `active_lrps` carries the full breadcrumb (`record_type`, `resolution_level`, `source`) so the spec author can trace where the assignment came from. The audit fragment formatting matches the standard-objects sub-agent.

Add an `active_lrps` array to your JSON output using the schema below.

## Tools
- `retrieve_metadata` — for layout XML retrieval
- `run_soql_query` — for record counts, ProfileLayout queries, EntityDefinition, Tooling API SOQL

If MCP is unavailable, stop and return a JSON error block (see Output Format).

{{AUDIT_SHARED_RULES}}

## Custom Objects

**Discovery query:**
```
SELECT QualifiedApiName, Label FROM EntityDefinition
WHERE KeyPrefix LIKE 'a%' AND IsCustomizable = true
ORDER BY Label
```
This returns all custom objects. Filter out managed package objects (those where `QualifiedApiName` contains a namespace prefix — pattern: `namespace__ObjectName__c` with two sets of double underscores before `__c`). Keep unmanaged objects only (pattern: `ObjectName__c` with only one `__c` at the end, no namespace prefix).

**Bulk-fetch pattern (default):** the 2026-05-20 field run hit the sub-agent tool budget (>90 calls) on a customer SDO because layout discovery was per-object with a fallback retry loop. Replace per-object iteration with two bulk calls up front:

**Step C1 — Bulk ProfileLayout query.** After demo-relevance enumeration produces the in-scope `__c` set (call it `IN_SCOPE_CUSTOM`), run a single SOQL:
```
SELECT Layout.Name, RecordType.Name, TableEnumOrId
FROM ProfileLayout
WHERE TableEnumOrId IN ('Obj1__c', 'Obj2__c', ...)
  AND Profile.Name = 'System Administrator'
```
Group results by `TableEnumOrId` to build a per-object layout map. Objects with 0 ProfileLayout rows (common for objects without record types) carry through to step C2's Tooling fallback. Note: `TableEnumOrId` returns the entity key ID for custom objects, but `IN` accepts the API name list because Salesforce normalises both sides — verify in the result set, and if a row's `TableEnumOrId` looks like an ID (e.g. `01I...`), reverse-resolve via the `EntityDefinition.QualifiedApiName` lookup you already ran in discovery.

**Step C2 — Tooling Layout fallback for objects with no ProfileLayout row.** Single bulk Tooling SOQL across the unresolved set:
```
SELECT Name, TableEnumOrId FROM Layout WHERE Name LIKE '[Obj1 Label]%' OR Name LIKE '[Obj2 Label]%' OR ...
```
(Tooling Layout supports `OR` across `LIKE` patterns; cap at 10-clause OR groups if the unresolved set is larger — re-run in batches of 10.) Match results back to objects by label-prefix. If multiple layouts match an object, capture all and flag the active-layout ambiguity in `discovery_notes`. If neither C1 nor C2 yields a layout for a given object, record "No layout found (ProfileLayout empty, Tooling Layout returned 0)" — do not guess.

**Per-object data after the bulk pass:**
- API name, label
- Record count: `SELECT COUNT() FROM [ObjectApiName]` (still per-object — counts cannot be bulked across heterogeneous objects)
- Record types (if any)
- Active page layout: the resolved name from C1/C2 (name only — no layout XML retrieve)

Do NOT retrieve classic-layout XML for custom objects. Layout *names* from C1/C2 are sufficient at proposal stage; the full field list is fetched on demand at sparring Stage 5b (describe-before-spec), scoped to the objects the locked scenario touches. A field-count signal is NOT emitted for custom objects — "has custom fields?" is definitionally yes, so the signal carries no information (it is emitted for standard objects only, where customization is a real question).

For remaining unmanaged custom objects (not demo-relevant), list them in a summary table with API name and label only. Note total count of managed package objects as a single line.

**Demo-relevance heuristic** (apply when classifying which unmanaged custom objects warrant full enumeration vs summary-table):
- Always demo-relevant: any object with record_count > 0, any object whose name contains the customer name (from {{CUSTOMER}}), any object in `{{ACTIVE_LRP_MAP}}`.
- Heuristically demo-relevant: names containing scenario-domain keywords (e.g. for service: `Case`, `Service`, `Agent`, `Bot`, `Reply`; for sales: `Opportunity`, `Quote`, `Pipeline`; for industry: cloud-specific terms).
- Default to inclusion when uncertain — under-enumeration silently hides candidate build surfaces. Over-enumeration is recoverable via the summary-table fallback for non-starred objects.

## Existing Custom Permission Sets

`SELECT Name, Label, Description FROM PermissionSet WHERE IsCustom = true AND NamespacePrefix = null`

If the result overflows to a temp file, parse it (see Overflow File Handling). Group by prefix pattern. Always surface permission sets whose names match the customer name or ★-flagged custom objects.

## ★ Priority Markers

Star the following:
- The active page layout for every custom object in scope (active layout is always ★ once resolved via ProfileLayout or the Tooling API Layout fallback)
- Any existing custom objects that look directly relevant to common demo scenarios (medical devices, field service parts, custom industry objects) — these are also ★, and their active layout inherits ★ automatically

"★ active layout" in this file means the layout resolved by the ProfileLayout / Tooling API Layout fallback for an in-scope custom object.

## Output Budget

- **Output budget:** with per-layout field content removed, starred custom objects carry name + label + record count + record types + active layout name + (where mapped) LRP composition. If the fragment exceeds 200 lines, trim non-starred custom objects to a summary table (API name, label, count).

## Pre-Return Completeness Checklist

Before writing your JSON output block, verify each of these. If any fails, fix it before returning.

1. **Custom object layouts resolved.** Every ★ custom object must have a layout entry — from ProfileLayout, Tooling API Layout query, or explicit "not found after N methods." **Layout names must be the bare metadata API name** as stored in `Layout.Name` — do NOT prefix with the object name. The Tooling API returns the name in round-trippable form; preserving it lets downstream specs pass it directly to `retrieve_metadata`.
2. **Permission sets listed.** At minimum a count. If the full list overflowed, report the count and any demo-relevant matches.
3. **Every section header has content beneath it.**

## Output Format

Write the fragment file, then return EXACTLY one fenced JSON block. No prose outside the block.

```json
{
  "fragment_file": "orgs/{{ORG_ALIAS}}-{{CUSTOMER}}/audit-fragment-custom-objects.md",
  "status": "SUCCESS|PARTIAL|FAILED",
  "relevant_custom_objects": ["string — API names of ★-flagged custom objects"],
  "active_layouts": [
    {"object": "string", "record_type": "string|null", "layout_name": "string"}
  ],
  "active_lrps": [
    {
      "object": "string",
      "record_type": "string|null",
      "lrp_developer_name": "string|null",
      "resolution_level": "profile_recordtype|app_recordtype|app_default|org_default|system_default",
      "source": "string|null",
      "composition_class": "record_detail|field_section|mixed|custom|unretrievable|system_default",
      "gap_risk": false,
      "field_sections": [
        {
          "label": "string",
          "section_facet_uuid": "string|null",
          "columns": [
            {
              "column_index": 1,
              "facet_uuid": "string — Facet UUID of the leaf field-bearing region; deploy targets this",
              "fields": ["string — field API name (Record. prefix stripped)"]
            }
          ]
        }
      ]
    }
  ],
  "custom_permset_count": 0,
  "demo_surface_notes": ["string — non-error observations: custom object patterns, industry-specific metadata, permission set coverage, data model signals"],
  "discovery_notes": ["string — things that worked differently than the prompt assumed; e.g. orchestrator slice drift, unexpected ACTIVE_LRP_MAP shape"],
  "issues": ["string — errors, failures, truncations"]
}
```
