---
name: deployment-rules
description: >
  Rules for deploying Flows, Apex, LWC, and Agentforce in SF Demo Prep.
  Read before deploying any of these metadata types.
---

# Deployment Rules — Flows, Apex, LWC, Agentforce

All types require explicit SE confirmation before deployment.
Two-attempt rule: if deployment fails twice, STOP and add to SE Manual Checklist.

---

## Flow Rules

Scope: single-object, record-triggered only. No screen flows, scheduled flows, or subflows.

1. Explain in plain English what the flow will do — wait for SE confirmation
2. Read `.claude/skills/sf-flow/SKILL.md` before generating any Flow XML
3. Validate generated XML against the sf-flow skill's 110-point checklist — work through it mentally, flag failures to the SE
4. Deploy as Draft first (`<status>Draft</status>`), confirm success, then activate
5. Check for existing flows on the same object via MCP `retrieve_metadata` — flag execution order conflicts
6. Rollback: `sf project delete source --metadata Flow:[FlowApiName] --target-org [alias]`

**Complex flows always go to SE Manual Checklist:**
screen flows, scheduled/time-based flows, multi-object flows, subflows.

---

## Apex Rules

Scope: single-trigger, single-object. No cross-object Apex. No test classes (demo org).

1. Explain in plain English — wait for SE confirmation
2. Run `run_code_analyzer` before deploying (if MCP available)
3. Rollback:
   - `sf project delete source --metadata ApexClass:[ClassName] --target-org [alias]`
   - `sf project delete source --metadata ApexTrigger:[TriggerName] --target-org [alias]`

---

## LWC Rules

Scope: demo-specific UI — Customer 360 Cards, custom record views, branded components.

1. Explain in plain English — wait for SE confirmation
2. Use MCP LWC expert tools when available (scaffolding, SLDS, validation)
3. Run `run_code_analyzer` before deploying (if MCP available)
4. Rollback: `sf project delete source --metadata LightningComponentBundle:[ComponentName] --target-org [alias]`

---

## Agentforce Rules

Scope: single agent, topic-based routing. No multi-agent orchestration, no custom model config.
Allowed metadata: `GenAiPlanner`, `GenAiPlugin`, `GenAiFunction`, `BotDefinition`, `PromptTemplate`.

1. Explain in plain English — wait for SE confirmation
2. Read `.claude/skills/sf-ai-agentforce/SKILL.md` before generating agent metadata
3. Check for existing agents/topics via MCP `retrieve_metadata` — flag conflicts
4. Run `run_code_analyzer` on Apex backing actions (if MCP available)
5. Rollback:
   - `sf project delete source --metadata GenAiPlanner:[PlannerName] --target-org [alias]`
   - `sf project delete source --metadata BotDefinition:[BotName] --target-org [alias]`

**Always SE Manual Checklist:** multi-agent orchestration, custom model/LLM config, conversation design, persona tuning, agent testing.