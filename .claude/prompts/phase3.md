You are deploying an Agentforce agent to org {{ORG_ALIAS}} ({{ORG_USERNAME}}).
The SE has already confirmed this deployment. Work autonomously.
Use MCP tools for all operations.
Salesforce Docs MCP (`salesforce_docs_search`, `salesforce_docs_fetch`) is available. Agent Script ships features monthly — proactively consult docs for any non-trivial Agent Script element (subagents, before_reasoning hooks, filtered visibility, action chaining) before writing the bundle. Also consult on unfamiliar deploy errors before retry.

## Skills Available
Invoke these skills via the Skill tool:
- `developing-agentforce` — agent spec, validation, preview, publish, activate
- `testing-agentforce` — ad-hoc smoke testing via `sf agent preview` (Mode A only — used after activate)
- `demo-docs-consultation` — decision tree for when to consult Salesforce Docs MCP

## Deployment Rules

**Two-attempt rule:** if a deployment fails twice, STOP that item, record it as SKIPPED in your JSON output with the error message, and continue with remaining items.

**Unfamiliar errors:** if the error message is not self-evident, invoke the `demo-docs-consultation` skill before the second attempt. Record the consultation in `docs_consulted`.

### New Agent (Agent Script path)
Scope: single agent, topic-based routing with Apex or Flow backing actions.
1. Invoke `developing-agentforce` skill — follow its "Create an Agent" workflow.
2. Check for existing agents via `retrieve_metadata` — flag conflicts in `issues`.
3. Run `run_code_analyzer` on Apex backing actions (if MCP available).
4. Validate via `sf agent validate authoring-bundle` before publishing.
5. Preview with `sf agent preview` before publishing.
6. Publish, then activate.
7. Rollback:
   - `sf project delete source --metadata AiAuthoringBundle:[AgentName] --target-org [alias]`
   - `sf project delete source --metadata ApexClass:[ClassName] --target-org [alias]`

### Modify Existing Agent (version-safe path)
For agents already in the org. Every publish creates a new version; rollback via `sf agent activate --version-number N`.
1. Invoke `developing-agentforce` skill — follow its "Modify an Existing Agent" workflow.
2. Note the current active version number before changes (rollback target).
3. Comprehend existing agent structure, update Agent Spec.
4. Validate and preview before publishing.
5. Publish (creates new version), then activate.
6. Rollback:
   - `sf agent deactivate --json --api-name [AgentName] --target-org [alias]`
   - `sf agent activate --json --api-name [AgentName] --version-number [N] --target-org [alias]`

### Smoke Test (after activate — both paths)
1. Read the spec's "Smoke test utterances" list. If none specified, generate 3 from topic descriptions.
2. Start preview: `sf agent preview start --json --authoring-bundle [AgentName] -o [alias]`
3. Send each utterance: `sf agent preview send --json --session-id [ID] --utterance "[message]" --authoring-bundle [AgentName] -o [alias]`
4. End session: `sf agent preview end --json --session-id [ID] --authoring-bundle [AgentName] -o [alias]`
5. Evaluate: correct topic? Expected backing action? Coherent response?
6. Record in `smoke_test` JSON output.
A failed smoke test does NOT block deployment. Record failures in `issues`.

### Always Out of Scope (skip with reason "SE Manual Checklist")
- Multi-agent orchestration
- Custom model/LLM config
- Channel assignment and configuration
- Production-scale test suites (Testing Center batch regression — Mode B)

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
  "smoke_test": {
    "ran": true,
    "utterances": [
      {"message": "string", "passed": true, "notes": "string"}
    ]
  },
  "skipped": [
    {"component": "string", "reason": "string"}
  ],
  "rollback_commands": ["string"],
  "docs_consulted": [
    {"question": "string", "url": "string", "verdict": "string"}
  ],
  "issues": ["string"]
}
```
