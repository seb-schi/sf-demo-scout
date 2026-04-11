# SF Demo Prep — Claude Code Instructions

## Org
- Alias: demo-org
- Username: [YOUR ORG USERNAME]
- Org ID: [YOUR ORG ID]
- Instance: [YOUR ORG INSTANCE URL]
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
- Deploy simple Apex (see Apex Rules below)
- Deploy simple LWC components (see LWC Rules below)

## NEVER Without Explicit SE Confirmation
- Delete existing metadata or records
- Modify existing profiles or existing permission sets
- Touch anything prefixed `sb_` or `managed__`
- Deploy flows — NEVER attempt Flow XML deployment under any circumstance
- Deploy Apex triggers or classes (see Apex Rules)
- Deploy LWC components (see LWC Rules)

## Working Pattern
1. State what you will do and why before every operation
2. Retrieve current state before writing anything — use MCP retrieve_metadata
3. Deploy in small increments — never batch unrelated changes
4. After each deploy: confirm success via deploy status or MCP feedback
5. On failure: explain error in plain English, fix only the failing element, redeploy
6. After every deployment: run the Companion Permission Set (see below)
7. IMPORTANT: If context is getting long, save progress to `deployment-log.md` and tell the SE to start a fresh session referencing that file

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

If MCP is unavailable, fall back to:
```
sf data query --target-org demo-org --query "SELECT Id FROM PermissionSet WHERE Name='[NAME]'"
sf data query --target-org demo-org --query "SELECT Id FROM User WHERE Username='[USERNAME]'"
sf data create record --sobject PermissionSetAssignment --values "PermissionSetId=[PS_ID] AssigneeId=[USER_ID]" --target-org demo-org
```

## Flow XML — BANNED
NEVER deploy Flow XML. For any flow in the spec:
- Use MCP retrieve_metadata to inspect existing flows in the org
- Describe what the new flow does in plain English
- Flag any execution order conflicts with existing flows
- Add step-by-step build instructions to the SE Manual Checklist section of the Deployment Summary
- Move on to the next deployable item

## Apex Rules
Apex is allowed ONLY for simple record-triggered automations under these conditions:
1. STOP and explain in plain English what the code will do before writing it
2. Wait for explicit SE confirmation ("yes, deploy this")
3. Keep to single-trigger, single-object scope — no cross-object Apex
4. No test classes required (demo org, not production)
5. Run `run_code_analyzer` on the Apex before deploying (if MCP available)
6. Always provide a rollback command alongside deployment:
   ```
   sf project delete source --metadata ApexClass:[ClassName] --target-org demo-org
   sf project delete source --metadata ApexTrigger:[TriggerName] --target-org demo-org
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
   sf project delete source --metadata LightningComponentBundle:[ComponentName] --target-org demo-org
   ```
6. If the LWC fails to deploy on second attempt, STOP — add it to the SE Manual Checklist instead

## Org Audit Format
When auditing the org, use MCP retrieve_metadata to pull comprehensive metadata.
Save to `org-audit-[DATE].md`:
- Custom objects (API name, label, record count if feasible via run_soql_query)
- Key fields and relationships per object
- Existing flows (name, type, active/inactive, trigger object, key logic summary)
- Existing LWC components (name, purpose if inferrable from source)
- Existing permission sets (custom only)
- Gaps relative to the demo spec or standard HLS scenario

## Demo Spec Input
Specs arrive from Demo Scout in this structure:

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

When receiving a spec:
1. Read the FULL spec before any action
2. Find and read the most recent `org-audit-*.md` file in this project
3. Cross-check the spec against the org audit — flag conflicts with existing metadata, flows, and LWCs
4. Use MCP retrieve_metadata to verify anything uncertain — the org audit may be stale
5. Flag any ⚠️ items with the SE before proceeding
6. Execute Claude Code Instructions ONLY — never touch SE Manual Checklist items
7. After all deployments complete, produce the Deployment Summary (see below)

## Deployment Summary — MANDATORY FINAL STEP
After completing all deployments, produce a summary and save to `deployment-summary-[CUSTOMER]-[DATE].md`. Also output the full summary to the terminal.

```markdown
# Deployment Summary — [Customer] — [Date]

## What Was Deployed
[Every component created or modified, grouped by type]

## What the SE Must Do Next (in order)
1. [Prioritised manual steps — flows first, then layout arrangement, then data refinement]
2. [Be specific: "Open App Builder > Patient Record Page > drag Status field to top-right panel"]

## How to Verify
[Step-by-step test sequence: navigate here, click this, expect that]

## Issues Encountered
[Anything that failed, was skipped, or needs attention — include error messages]

## Apex Deployed (if any)
[Class/trigger names, plain-English description, rollback commands]

## LWC Deployed (if any)
[Component names, plain-English description, rollback commands]

## Bring Back to Demo Scout
[Open questions, suggested next iteration, anything the SE should feed back]
```
