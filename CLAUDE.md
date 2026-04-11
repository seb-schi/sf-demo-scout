# SF Demo Prep — Claude Code Instructions

## Org
> **Documentation only.** All slash commands read org identity from `sf config get target-org`
> at runtime. The values below are for human reference and are updated by `/setup-demo-scout`
> and `/switch-org`. Do not use these values programmatically.

- Alias: [DEMO ORG ALIAS]
- Username: [YOUR ORG USER NAME]
- Org ID: [YOUR ORG ID]
- Instance: https://[YOUR ORG INSTANCE].my.salesforce.com
- Type: Personal demo org — destructive operations permitted with prior explanation

## MCP Tools
This project has a Salesforce DX MCP Server configured in .mcp.json.
Use MCP tools whenever available — they give you structured org access:
- Use `retrieve_metadata` to inspect org state (objects, fields, flows, LWCs)
- Use `deploy_metadata` to push changes to the org
- Use `run_soql_query` for data verification and record checks
- Use `assign_permission_set` to assign permission sets (replaces the manual SOQL+create pattern)
- Use `list_all_orgs` to verify org connections
- Use LWC expert tools when building Lightning Web Components (see LWC Rules)
- Use `run_code_analyzer` as a quality gate before deploying Apex or LWC

If MCP tools are unavailable, fall back to sf CLI commands.

## Allowed Operations
- Retrieve and inspect any metadata (prefer MCP retrieve_metadata)
- Create or modify custom objects, fields, record types
- Create new permission sets and assign to current user
- Create Lightning apps and custom tabs
- Seed demo data on single objects only (no cross-object lookups)
- Modify page layouts (field additions only — not visual arrangement)
- Deploy simple record-triggered flows (see Flow Rules below)
- Deploy simple Apex (see Apex Rules below)
- Deploy simple LWC components (see LWC Rules below)

## NEVER Without Explicit SE Confirmation
- Delete existing metadata or records
- Modify existing profiles or existing permission sets
- Touch anything prefixed `sb_` or `managed__`
- Deploy flows without SE confirmation (see Flow Rules)
- Deploy Apex triggers or classes (see Apex Rules)
- Deploy LWC components (see LWC Rules)

## Working Pattern
1. State what you will do and why before every operation
2. Retrieve current state before writing anything — use MCP retrieve_metadata
3. Deploy in small increments — never batch unrelated changes
4. After each deploy: confirm success via deploy status or MCP feedback
5. On failure: explain error in plain English, fix only the failing element, redeploy
6. After every deployment: run the Companion Permission Set (see below)
7. IMPORTANT: If context is getting long, save progress to the org change log and tell the SE to start a fresh session referencing that file

## Companion Permission Set — MANDATORY
After every deployment that creates objects, fields, record types, tabs, or apps, deploy a companion permission set in the same operation.

Include:
- Object CRUD for all new custom objects
- Field Read + Edit FLS for all new custom fields (EXCLUDE Required fields — API rejects FLS on these)
- RecordTypeVisibility: visible=true for all new record types
- TabVisibility: DefaultOn for all new custom tabs
- AppVisibility: visible=true for all new Lightning apps

Then assign using MCP:
- Use `assign_permission_set` to assign to the current user

If MCP is unavailable, fall back to (replace [ALIAS] with the active org alias from `sf config get target-org`):
```
sf data query --target-org [ALIAS] --query "SELECT Id FROM PermissionSet WHERE Name='[NAME]'"
sf data query --target-org [ALIAS] --query "SELECT Id FROM User WHERE Username='[USERNAME]'"
sf data create record --sobject PermissionSetAssignment --values "PermissionSetId=[PS_ID] AssigneeId=[USER_ID]" --target-org [ALIAS]
```

## Flow Rules
Simple record-triggered flows are allowed under these conditions:
1. STOP and explain in plain English what the flow will do before writing it
2. Wait for explicit SE confirmation ("yes, deploy this")
3. Use the sf-flow skill — read `skills/sf-flow/SKILL.md` before generating any Flow XML
4. Scope: single-object, record-triggered only — no screen flows, no scheduled flows, no subflows
5. Run the sf-flow validation script on the generated XML before deploying:
   ```
   python3 ~/.claude/skills/sf-flow/hooks/scripts/validate_flow.py [flow-file.flow-meta.xml]
   ```
6. Deploy as Draft first:
   - Set `<status>Draft</status>` in the XML
   - Deploy and confirm success
   - Then edit to `<status>Active</status>` and redeploy
7. Use MCP `retrieve_metadata` to check for existing flows on the same object before deploying — flag execution order conflicts with the SE
8. Always provide a rollback command alongside deployment:
   ```
   sf project delete source --metadata Flow:[FlowApiName] --target-org [alias]
   ```
9. If the flow fails to deploy on second attempt, STOP — revert to SE Manual Checklist:
   - Describe what the flow should do in plain English
   - List step-by-step build instructions for the SE

**Complex flows always go to SE Manual Checklist (no exceptions):**
- Screen flows
- Scheduled / time-based flows
- Flows referencing multiple objects
- Subflows

## Apex Rules
Apex is allowed ONLY for simple record-triggered automations under these conditions:
1. STOP and explain in plain English what the code will do before writing it
2. Wait for explicit SE confirmation ("yes, deploy this")
3. Keep to single-trigger, single-object scope — no cross-object Apex
4. No test classes required (demo org, not production)
5. Run `run_code_analyzer` on the Apex before deploying (if MCP available)
6. Always provide a rollback command alongside deployment:
   ```
   sf project delete source --metadata ApexClass:[ClassName] --target-org [alias]
   sf project delete source --metadata ApexTrigger:[TriggerName] --target-org [alias]
   ```
7. If the Apex fails to deploy on second attempt, STOP — add it to the SE Manual Checklist instead

## LWC Rules
LWC components are allowed for demo-specific UI (Customer 360 Cards, custom record views, branded components) under these conditions:
1. STOP and explain in plain English what the component will do before writing it
2. Wait for explicit SE confirmation ("yes, build this")
3. Use MCP LWC expert tools when available:
   - `create_lwc_component_from_prd` for scaffolding
   - `guide_design_general` and `explore_slds_blueprints` for SLDS compliance
   - `guide_lwc_development` and `guide_lwc_best_practices` for code quality
   - `validate_and_optimize` as a quality gate before deployment
4. Run `run_code_analyzer` on the LWC before deploying (if MCP available)
5. Always provide a rollback command alongside deployment:
   ```
   sf project delete source --metadata LightningComponentBundle:[ComponentName] --target-org [alias]
   ```
6. If the LWC fails to deploy on second attempt, STOP — add it to the SE Manual Checklist instead

## Org Audit Format
Audits are stored per org in: `orgs/[alias]-[ORG_ID_SHORT]/`

When auditing the org, use MCP retrieve_metadata to pull comprehensive metadata.
Save to `orgs/[alias]-[ORG_ID_SHORT]/audit-[YYYY-MM-DD].md`

Include:
- Custom objects (API name, label, record count if feasible via run_soql_query)
- Key fields and relationships per object
- Existing flows (name, type, active/inactive, trigger object, key logic summary)
- Existing LWC components (name, purpose if inferrable from source)
- Existing custom permission sets (custom only)
- Notable gaps or risks relative to standard HLS demo scenarios

## Org Folder Structure
All per-org history lives under `orgs/`:

```
orgs/
  [alias]-[ORG_ID_SHORT]/
    audit-[YYYY-MM-DD].md        ← org state snapshots
    changes-[YYYY-MM-DD]-[CUSTOMER].md  ← deployment change logs
```

Specs are customer-scoped and live in the project root:
```
demo-spec-[CUSTOMER]-[YYYY-MM-DD].md
```

## Demo Spec Input
Specs are generated by /scout-sparring and follow this structure:

```
# Demo Spec — [Customer]
## Customer Context
## Scenario: [Name]
## Claude Code Instructions
  - Objects & Fields
  - Record Types
  - Permission Set
  - Data Seeding
  - Page Layouts
  - Lightning App / Tabs
  - Apex (if any — requires SE confirmation)
  - LWC Components (if any — requires SE confirmation)
## SE Manual Checklist
```

When executing a spec via /scout-building:
1. Read the FULL spec before any action
2. Load the most recent audit from `orgs/[alias]-[ORG_ID_SHORT]/`
3. Cross-check the spec against the org audit — flag conflicts with existing metadata, flows, and LWCs
4. Use MCP retrieve_metadata to verify anything uncertain — the org audit may be stale
5. Flag any ⚠️ items with the SE before proceeding
6. Execute Claude Code Instructions ONLY — never touch SE Manual Checklist items
7. After all deployments complete, write the change log (see below)

## Change Log — MANDATORY FINAL STEP
After completing all deployments, write a change log and save to:
`orgs/[alias]-[ORG_ID_SHORT]/changes-[YYYY-MM-DD]-[CUSTOMER].md`

Also output the full change log to the terminal.

```markdown
# Change Log — [Customer] — [Date]
Org: [alias] ([username])
Spec: demo-spec-[CUSTOMER]-[DATE].md
Audit used: audit-[YYYY-MM-DD].md

## What Was Deployed
[Every component created or modified, grouped by type]
[Include API names, not just labels]

## What Was Skipped
[Items not deployed and why — conflicts, SE decision, second-attempt failure]

## Companion Permission Set
[Name, what it covers, assignment status]

## Apex Deployed (if any)
[Class/trigger names, plain-English description]
Rollback:
  sf project delete source --metadata ApexClass:[ClassName] --target-org [alias]
  sf project delete source --metadata ApexTrigger:[TriggerName] --target-org [alias]

## LWC Deployed (if any)
[Component names, plain-English description]
Rollback:
  sf project delete source --metadata LightningComponentBundle:[ComponentName] --target-org [alias]

## Issues Encountered
[Errors, workarounds, anything that needed a second attempt]

## SE Must Do Next (in order)
1. [Prioritised manual steps — flows first, then layout arrangement, then data refinement]
2. [Be specific: "Open App Builder > Patient Record Page > drag Status field to top-right panel"]

## How to Verify
[Step-by-step test sequence: navigate here, click this, expect that]

## Open Questions for Next Session
[Unresolved items, suggested follow-up, anything to feed back into sparring]
```