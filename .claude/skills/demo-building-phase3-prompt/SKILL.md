---
name: demo-building-phase3-prompt
description: >
  Sub-agent prompt template for Phase 3 (Agentforce) deployment.
  Used by scout-building orchestrator — not invoked directly.
---

# Phase 3 Sub-Agent Prompt Template

The orchestrator reads this template, replaces `{{placeholders}}`, and passes
the result as the `prompt` parameter to `Agent(model="sonnet")`.

---

You are deploying an Agentforce agent to org {{ORG_ALIAS}} ({{ORG_USERNAME}}).
The SE has already confirmed this deployment. Work autonomously.
Use MCP tools for all operations.

## Deployment Rules
- Follow the developing-agentforce skill workflow exactly.
- Validate via sf agent validate authoring-bundle before publishing.
- Preview with sf agent preview before publishing.
- Publish, then activate.
- On failure: fix and retry once. If it fails twice, record as SKIPPED.

## What Earlier Phases Deployed
{{PRIOR_PHASES_SUMMARY}}

## Your Spec
{{SPEC_SECTIONS}}

## Reference: Agentforce Development
{{DEVELOPING_AGENTFORCE_SKILL}}

## Output Format
DEPLOYED:
- Agent: [name] — [published version, active/inactive]
- Backing Actions: [list with status]

SKIPPED:
- [Component]: [error]

ROLLBACK COMMANDS:
- [version rollback or delete commands]

ISSUES:
- [any warnings or notes]
