---
name: demo-org-audit
description: >
  Format and procedure for auditing a Salesforce demo org.
  Used by /scout-sparring (via 3 parallel audit sub-agent prompt templates at .claude/prompts/audit-standard-objects.md, audit-apps-flows-agents.md, audit-custom-objects.md).
---

# Org Audit — Format & Procedure

Save to: `orgs/[alias]-[customer]/audit-[YYYY-MM-DD]-[HHmm].md`
- alias from `sf config get target-org`
- customer = lowercase-hyphenated customer name provided by SE during Stage 0 (e.g. `makana-medtech`, `deutsche-fachpflege`)
- HHmm = local time at audit creation (e.g. 0930, 1445)

Use MCP `retrieve_metadata` for metadata and `run_soql_query` for record counts.

If MCP unavailable: "Check .mcp.json is in the project root and restart VS Code."

## Required Content

### Standard Objects in Use
For each standard object commonly used in demos (Account, Contact, Opportunity, Case, Lead, and any others present):
- Label and API name
- Record count
- Record types available
- **Active page layout per record type** — query ProfileLayout via Tooling API:
  ```
  SELECT Layout.Name, RecordType.DeveloperName
  FROM ProfileLayout
  WHERE SobjectType = '[Object]'
  AND Profile.Name = 'System Administrator'
  ```
  List the active layout name for each record type. Flag these explicitly — they are the primary build surface.
- Key fields present on the active layout (retrieve layout XML, list fields by section)

### Custom Objects
- API name, label, record count
- Key fields and relationships
- Active page layout per record type (same ProfileLayout query as above)

### Existing Lightning Apps
- App API name and label
- Tabs included
- Which app is set as default for System Administrator — this is the primary demo app
- Note which standard objects are already tabbed in this app

### Existing Flows
- Name, type, active/inactive, trigger object, brief logic summary
- Flag any flows on objects likely to be used in the demo scenario

### Existing LWC Components
- Name, purpose if inferrable
- Which page(s) they appear on if determinable

### Existing Custom Permission Sets
- Custom only (exclude standard and managed)

### Existing Agentforce Agents and Topics
- If any: name, topics, active/inactive status

### Notable Gaps and Risks
- Fields or relationships missing from active layouts that would be needed for the demo scenario
- Objects with no records (data seeding required)
- Managed package components (prefixed) that cannot be modified
- Execution order conflicts from existing active flows
- Any components already marked ⚠️ from a previous session

---

## Audit Priority Flag

Mark the following clearly in the audit output with ★:
- The default Lightning app for System Administrator
- The active page layout for each standard object record type in scope
- Any existing custom objects directly relevant to the demo scenario

These starred items are the primary build surface. Scout Sparring will use them to anchor scenario design before proposing any new metadata.