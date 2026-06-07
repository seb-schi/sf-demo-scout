---
name: demo-org-audit
description: >
  Format and procedure for auditing a Salesforce demo org — required content,
  priority flags, and ProfileLayout query patterns.
  TRIGGER when: audit sub-agents need the canonical output format, section
  structure, or ★ priority flag rules.
  DO NOT TRIGGER when: running the audit (sub-agent prompts have inlined
  procedures), generating specs, or deploying metadata.
---

# Org Audit — Format & Procedure

Save to: `orgs/[alias]-[customer]/audit-[YYYY-MM-DD]-[HHmm].md`
- alias from `sf config get target-org`
- customer = lowercase-hyphenated customer name provided by SE during Stage 0 (e.g. `makana-medtech`, `deutsche-fachpflege`)
- HHmm = local time at audit creation (e.g. 0930, 1445)

Use MCP `retrieve_metadata` for metadata and `run_soql_query` for record counts.

If MCP unavailable: "MCP is not responding. Quit VS Code fully (CMD+Q) and reopen."

## Required Content

### Standard Objects in Use
For each standard object commonly used in demos (Account, Contact, Opportunity, Case, Lead, and any others present):
- Label and API name
- Record count
- Record types available
- **Active page layout per record type** — query ProfileLayout via Tooling API:
  ```
  SELECT Layout.Name, RecordType.Name
  FROM ProfileLayout
  WHERE TableEnumOrId = '[Object]'
  AND Profile.Name = 'System Administrator'
  ```
  List the active layout name for each record type. Flag these explicitly — they are the primary build surface.
- Field-count signal (standard objects only): total field count + custom field count via `SELECT QualifiedApiName FROM FieldDefinition WHERE EntityDefinition.QualifiedApiName = '[Object]'`. Do NOT retrieve layout XML for the field dump — full field lists are fetched on demand at spec time (sparring Stage 5b), scoped to the locked scenario's objects.

### Custom Objects
- API name, label, record count
- Active page layout per record type (name only — same ProfileLayout query as above; no layout-XML field dump)

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