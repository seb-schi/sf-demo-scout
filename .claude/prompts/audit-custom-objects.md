You are running one part of an org audit for Salesforce demo preparation.
Your scope: **custom objects and custom permission sets**. Two sibling sub-agents
handle standard objects and apps/flows/agents/LWC in parallel.

Target org: {{ORG_ALIAS}} ({{ORG_USERNAME}})
Output file: orgs/{{ORG_ALIAS}}-{{CUSTOMER}}/audit-fragment-custom-objects.md

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

For each unmanaged custom object that looks demo-relevant:
- API name, label
- Record count: `SELECT COUNT() FROM [ObjectApiName]`
- Record types (if any)
- Active page layout:
  1. **First:** try ProfileLayout: `SELECT Layout.Name, RecordType.Name FROM ProfileLayout WHERE TableEnumOrId = '[ObjectApiName]' AND Profile.Name = 'System Administrator'`
  2. **If ProfileLayout returns 0 rows** (common for objects without record types): query the Tooling API by layout name pattern — `TableEnumOrId` stores the entity key ID for custom objects, not the API name, so you cannot filter by API name:
     ```
     SELECT Name, TableEnumOrId FROM Layout WHERE Name LIKE '[Object Label]%Layout%'
     ```
     Use the object **label** (e.g., `Makana Device`), not the API name. This returns all layouts whose name matches the object. If only one exists, that is the active layout. If multiple exist, note all and flag that the active one is ambiguous.
  3. **If both fail:** report "No layout found (ProfileLayout empty, Tooling Layout query returned 0)" — do not guess layout names.
- Key fields on layout (retrieve layout XML, same annotation rules as standard objects: `(Required)`, `(Readonly)`, `(Edit)`)
- **Related Lists on the ★ active layout** — from the same layout XML, list the `<relatedList>` entries.

For remaining unmanaged custom objects (not demo-relevant), list them in a summary table with API name and label only. Note total count of managed package objects as a single line.

## Existing Custom Permission Sets

`SELECT Name, Label, Description FROM PermissionSet WHERE IsCustom = true AND NamespacePrefix = null`

If the result overflows to a temp file, parse it (see Overflow File Handling). Group by prefix pattern. Always surface permission sets whose names match the customer name or ★-flagged custom objects.

## ★ Priority Markers

Star the following:
- Any existing custom objects that look directly relevant to common demo scenarios (medical devices, field service parts, custom industry objects)

## Output Budget

- **Output budget:** if your file exceeds 250 lines, trim non-starred custom objects to a summary table (API name, label, count). Starred objects always get full layout + field content.

## Pre-Return Completeness Checklist

Before writing your JSON output block, verify each of these. If any fails, fix it before returning.

1. **Custom object layouts resolved.** Every ★ custom object must have a layout entry — from ProfileLayout, Tooling API Layout query, or explicit "not found after N methods."
2. **Layout field content exists for all ★ layouts.** Every ★-marked active layout must have a "Key Fields" subsection. If layout XML retrieval failed, note the failure explicitly.
3. **Permission sets listed.** At minimum a count. If the full list overflowed, report the count and any demo-relevant matches.
4. **Every section header has content beneath it.**

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
  "custom_permset_count": 0,
  "demo_surface_notes": ["string — non-error observations: custom object patterns, industry-specific metadata, permission set coverage, data model signals"],
  "issues": ["string — errors, failures, truncations"]
}
```
