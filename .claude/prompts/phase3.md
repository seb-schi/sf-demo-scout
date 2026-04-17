You are deploying an Agentforce agent to org {{ORG_ALIAS}} ({{ORG_USERNAME}}).
The SE has already confirmed this deployment. Work autonomously.
Use MCP tools for all operations.

## Skills Available
Invoke this skill via the Skill tool for the full ADLC workflow:
- `developing-agentforce` — agent spec, validation, preview, publish, activate

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

## Output Format
Return EXACTLY one fenced JSON block matching this schema. Do not include any prose outside the block.

```json
{
  "phase": 3,
  "deployed": {
    "agent": {"api_name": "string", "version": 0, "status": "Active|Inactive"},
    "backing_actions": [{"type": "ApexClass|Flow", "api_name": "string", "status": "SUCCESS|FAILED"}]
  },
  "skipped": [
    {"component": "string", "reason": "string"}
  ],
  "rollback_commands": ["string"],
  "issues": ["string"]
}
```
