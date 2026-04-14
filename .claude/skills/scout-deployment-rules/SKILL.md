---
name: scout-deployment-rules
description: >
  Rules for deploying Flows, Apex, LWC, Agentforce, and Page Layouts in SF Demo Prep.
  Read before deploying any of these metadata types.
---

# Deployment Rules — Flows, Apex, LWC, Agentforce, Page Layouts

**Confirmation model:** one upfront confirmation per category before deployment begins. Once confirmed, deploy the full category autonomously — do not ask for input on individual files, MCP calls, or sub-steps.

**Notification pattern:** before presenting any confirmation gate, fire a macOS notification so the SE is alerted even if VS Code is in the background:
```bash
osascript -e 'display notification "[plain English description]" with title "SF Demo Scout — Input Needed"'
```

Note: macOS notifications require Terminal or VS Code to have notification permissions enabled in System Settings → Notifications. If notifications are not appearing, check this setting.

**Two-attempt rule:** if deployment fails twice, STOP, add to SE Manual Checklist, continue with remaining items.

---

## Page Layout Rules

Before modifying any page layout, identify which layout is actually active for the demo user.
Never retrieve "whichever layout comes first" — SDO orgs have many layouts per object and the first one is rarely the active one.

1. Query `ProfileLayout` via Tooling API to find the layout assigned to System Administrator for the target object and record type:
   ```
   SELECT Layout.Name, RecordType.DeveloperName
   FROM ProfileLayout
   WHERE SobjectType = '[Object]'
   AND Profile.Name = 'System Administrator'
   ```
2. Retrieve only the layout(s) returned by that query — not all layouts for the object
3. Modify and redeploy only the active layout
4. If multiple record types are in scope, run the query per record type and retrieve each assigned layout separately

Page layout modifications are safe operations — no SE confirmation required. But the ProfileLayout query is mandatory before every layout touch.

---

## Flow Rules

Scope: single-object, record-triggered only. No screen flows, scheduled flows, or subflows.

**Before deploying, fire notification and ask:**
```bash
osascript -e 'display notification "About to deploy flow: [FlowName] on [Object] — [plain English description]" with title "SF Demo Scout — Input Needed"'
```
> "About to deploy: [plain English description of what the flow does]. Proceed? (yes/no)"

Wait for confirmation. If yes, proceed with the full flow deployment autonomously:
1. Read `.claude/skills/sf-flow/SKILL.md` before generating any Flow XML
2. Validate generated XML against the sf-flow skill's 110-point checklist — work through it mentally, flag failures in the change log
3. Deploy as Draft first (`<status>Draft</status>`), confirm success, then activate
4. Check for existing flows on the same object via MCP `retrieve_metadata` — flag execution order conflicts in change log
5. Rollback: `sf project delete source --metadata Flow:[FlowApiName] --target-org [alias]`

**Complex flows always go to SE Manual Checklist:**
screen flows, scheduled/time-based flows, multi-object flows, subflows.

---

## Apex Rules

Scope: single-trigger, single-object. No cross-object Apex. No test classes (demo org).

**Before deploying, fire notification and ask:**
```bash
osascript -e 'display notification "About to deploy Apex: [ClassName/TriggerName] — [plain English description]" with title "SF Demo Scout — Input Needed"'
```
> "About to deploy: [plain English description]. Proceed? (yes/no)"

Wait for confirmation. If yes, proceed autonomously:
1. Run `run_code_analyzer` before deploying (if MCP available)
2. Rollback:
   - `sf project delete source --metadata ApexClass:[ClassName] --target-org [alias]`
   - `sf project delete source --metadata ApexTrigger:[TriggerName] --target-org [alias]`

---

## LWC Rules

Scope: demo-specific UI — Customer 360 Cards, custom record views, branded components.

**Before deploying, fire notification and ask:**
```bash
osascript -e 'display notification "About to deploy LWC: [ComponentName] — [plain English description]" with title "SF Demo Scout — Input Needed"'
```
> "About to deploy: [plain English description]. Proceed? (yes/no)"

Wait for confirmation. If yes, proceed autonomously:
1. Use MCP LWC expert tools when available (scaffolding, SLDS, validation)
2. Run `run_code_analyzer` before deploying (if MCP available)
3. Rollback: `sf project delete source --metadata LightningComponentBundle:[ComponentName] --target-org [alias]`

---

## Agentforce Rules

Scope: single agent, topic-based routing. No multi-agent orchestration, no custom model config.
Allowed metadata: `GenAiPlanner`, `GenAiPlugin`, `GenAiFunction`, `BotDefinition`, `PromptTemplate`.

**Before deploying, fire notification and ask:**
```bash
osascript -e 'display notification "About to deploy Agentforce agent: [AgentName] — [plain English description]" with title "SF Demo Scout — Input Needed"'
```
> "About to deploy: [plain English description of agent scope, topics, actions]. Proceed? (yes/no)"

Wait for confirmation. If yes, proceed autonomously:
1. Read `.claude/skills/sf-ai-agentforce/SKILL.md` before generating agent metadata
2. Check for existing agents/topics via MCP `retrieve_metadata` — flag conflicts in change log
3. Run `run_code_analyzer` on Apex backing actions (if MCP available)
4. Rollback:
   - `sf project delete source --metadata GenAiPlanner:[PlannerName] --target-org [alias]`
   - `sf project delete source --metadata BotDefinition:[BotName] --target-org [alias]`

**Always SE Manual Checklist:** multi-agent orchestration, custom model/LLM config, conversation design, persona tuning, agent testing.