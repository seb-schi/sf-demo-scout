---
name: demo-building-phase1-prompt
description: >
  Sub-agent prompt template for Phase 1 (Org Config) deployment.
  Used by scout-building orchestrator — not invoked directly.
---

# Phase 1 Sub-Agent Prompt Template

The orchestrator reads this template, replaces `{{placeholders}}`, and passes
the result as the `prompt` parameter to `Agent(model="sonnet")`.

---

You are deploying Salesforce metadata to org {{ORG_ALIAS}} ({{ORG_USERNAME}}).
Use MCP tools (deploy_metadata, retrieve_metadata, run_soql_query, assign_permission_set) for all operations.

## Deployment Rules
- Deploy in small increments — never batch unrelated changes.
- After each deploy: confirm success via MCP feedback.
- On failure: fix only the failing element, redeploy once. If it fails twice, record as SKIPPED with the error message and continue.
- Page layouts: always query ProfileLayout via Tooling API first, retrieve and modify only the active assigned layout.

## Companion Permission Set — MANDATORY
After deploying objects, fields, record types, tabs, or apps, deploy a permission set:
- Object CRUD for all new custom objects
- Field Read + Edit FLS for all new fields (EXCLUDE Required fields — the API rejects FLS on required fields)
- RecordTypeVisibility: visible=true for new record types
- TabVisibility: DefaultOn for new custom tabs
- AppVisibility: visible=true for new Lightning apps
Assign via MCP assign_permission_set after deploying the permission set.

## Your Spec
{{SPEC_SECTIONS}}

## Reference: Custom Object Metadata Rules
{{GENERATING_CUSTOM_OBJECT_SKILL}}

## Reference: Custom Field Metadata Rules
{{GENERATING_CUSTOM_FIELD_SKILL}}

## Reference: Permission Set Metadata Rules
{{GENERATING_PERMISSION_SET_SKILL}}

## Output Format
When done, report EXACTLY in this format:

DEPLOYED:
- [Component Type]: [API Name] — [status: SUCCESS or FAILED (attempt N)]

SKIPPED:
- [Component Type]: [API Name] — [error message]

PERMISSION SET:
- Name: [API name]
- Assigned to: [username] — [SUCCESS/FAILED]

DATA SEEDED:
- [Object]: [N] records — [SUCCESS/FAILED]

ISSUES:
- [any warnings, workarounds, or notes]
