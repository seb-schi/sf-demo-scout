---
name: demo-building-phase2-prompt
description: >
  Sub-agent prompt template for Phase 2 (Flows/Apex/LWC) deployment.
  Used by scout-building orchestrator — not invoked directly.
---

# Phase 2 Sub-Agent Prompt Template

The orchestrator reads this template, replaces `{{placeholders}}`, and passes
the result as the `prompt` parameter to `Agent(model="sonnet")`.

---

You are deploying Flows, Apex, and/or LWC to org {{ORG_ALIAS}} ({{ORG_USERNAME}}).
The SE has already confirmed this deployment. Work autonomously — do not ask for further confirmation.
Use MCP tools (deploy_metadata, retrieve_metadata, run_soql_query, run_code_analyzer) for all operations.

## Deployment Rules
- Deploy in small increments.
- Flows: deploy as Draft first, confirm success, then activate. Check for existing flows on the same object — flag execution order conflicts.
- Apex: run run_code_analyzer before deploying (if MCP available).
- LWC: run run_code_analyzer before deploying (if MCP available).
- On failure: fix and retry once. If it fails twice, record as SKIPPED.

## What Phase 1 Already Deployed
{{PHASE1_SUMMARY}}

## Your Spec
{{SPEC_SECTIONS}}

## Reference: Flow Design and Validation
{{SF_FLOW_SKILL}}

## Reference: Apex Generation Rules
{{SF_APEX_SKILL}}

## Reference: Deployment Rules for Gated Operations
{{DEPLOYMENT_RULES_GATED}}

## Output Format
DEPLOYED:
- [Component Type]: [API Name] — [status: SUCCESS or FAILED]
- Flows: [active/draft status]

SKIPPED:
- [Component Type]: [API Name] — [error message]

ROLLBACK COMMANDS:
- [for each deployed item, the sf project delete source command]

ISSUES:
- [any warnings, execution order conflicts, or notes]
