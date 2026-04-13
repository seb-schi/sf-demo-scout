# SF Demo Prep — Claude Code Instructions

## Org
> **Documentation only.** All slash commands read org identity from `sf config get target-org`
> at runtime. These values are for human reference only.

- Alias: scout-testing
- Username: admin@scout-testing.demo
- Org ID: 00DgL00000PZGOXUA5
- Instance: https://storm-28561183a3066b.my.salesforce.com
- Type: Personal demo org — destructive operations permitted with prior explanation

## MCP Tools
Salesforce DX MCP Server configured in .mcp.json. Prefer MCP over CLI:
- `retrieve_metadata` — inspect org state
- `deploy_metadata` — push changes
- `run_soql_query` — data verification
- `assign_permission_set` — assign permission sets
- `list_all_orgs` — verify org connections
- `run_code_analyzer` — quality gate for Apex/LWC
- LWC expert tools — scaffolding, SLDS, validation

Fall back to `sf` CLI if MCP is unavailable.

## Allowed Operations
- Create/modify custom objects, fields, record types
- Create new permission sets and assign to current user
- Create Lightning apps and custom tabs
- Seed demo data on single objects (no cross-object)
- Page layout field additions (active layout only — query ProfileLayout first)
- Simple record-triggered flows — SE confirmation required
- Simple Apex — SE confirmation required
- Simple LWC — SE confirmation required
- Simple Agentforce agents — SE confirmation required

**Before deploying Flows, Apex, LWC, or Agentforce:** read @.claude/skills/deployment-rules/SKILL.md

## NEVER Without Explicit SE Confirmation
- Delete existing metadata or records
- Modify existing profiles or permission sets
- Touch anything prefixed `sb_` or `managed__`
- Deploy flows, Apex, LWC, or Agentforce without SE confirmation
- Complex flows (screen, scheduled, multi-object, subflows) — always SE Manual Checklist

## Working Pattern
1. State what you will do and why before every operation
2. Retrieve current state before writing — prefer MCP retrieve_metadata
3. Deploy in small increments — never batch unrelated changes
4. After each deploy: confirm success via deploy status or MCP feedback
5. On failure: explain error in plain English, fix only the failing element, redeploy
6. After every deployment: run the Companion Permission Set (see below)
7. If context is getting long, save progress to the change log and tell the SE to start a fresh session

## Companion Permission Set — MANDATORY
After every deployment creating objects, fields, record types, tabs, or apps:

- Object CRUD for all new custom objects
- Field Read + Edit FLS for all new fields (EXCLUDE Required fields — API rejects FLS)
- RecordTypeVisibility: visible=true for new record types
- TabVisibility: DefaultOn for new custom tabs
- AppVisibility: visible=true for new Lightning apps

Assign via MCP `assign_permission_set`. If unavailable, read alias from `sf config get target-org`:
```
sf data query --target-org [ALIAS] --query "SELECT Id FROM PermissionSet WHERE Name='[NAME]'"
sf data query --target-org [ALIAS] --query "SELECT Id FROM User WHERE Username='[USERNAME]'"
sf data create record --sobject PermissionSetAssignment --values "PermissionSetId=[PS_ID] AssigneeId=[USER_ID]" --target-org [ALIAS]
```

## File Locations
- Per-org history: `orgs/[alias]-[customer]/` (audits, change logs, specs)
- Lessons learned: @.claude/skills/lessons/SKILL.md
- Deployment rules: @.claude/skills/deployment-rules/SKILL.md
- Org audit format: @.claude/skills/org-audit/SKILL.md
- Change log template: @.claude/skills/change-log/SKILL.md
- Spec output format: @.claude/skills/spec-format/SKILL.md