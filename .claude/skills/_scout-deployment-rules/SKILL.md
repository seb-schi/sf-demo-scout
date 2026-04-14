---
name: _scout-deployment-rules
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

Two paths depending on whether the agent is new or existing. Both use the ADLC skill suite (`developing-agentforce`, `testing-agentforce`, `observing-agentforce`). Deploy Agentforce **last** in any session — the ADLC skills are large and consume significant context.

**Context check:** Before loading any Agentforce skill, assess remaining context. If the session has already deployed org config (fields, layouts, data, flows, permissions), write a partial change log first. If context is tight, save the partial log and tell the SE to start a fresh session for the agent deployment.

### New Agent (Agent Script path)

Scope: single agent, topic-based routing with Apex or Flow backing actions.

**Before deploying, fire notification and ask:**
```bash
osascript -e 'display notification "About to deploy new Agentforce agent: [AgentName] — [plain English description]" with title "SF Demo Scout — Input Needed"'
```
> "About to deploy new agent: [plain English description of agent scope, topics, actions]. Proceed? (yes/no)"

Wait for confirmation. If yes, proceed autonomously:
1. Load `developing-agentforce` skill — follow its "Create an Agent" workflow
2. Check for existing agents via MCP `retrieve_metadata` — flag conflicts in change log
3. Run `run_code_analyzer` on Apex backing actions (if MCP available)
4. Validate via `sf agent validate authoring-bundle` before publishing
5. Preview with `sf agent preview` and live actions before publishing
6. Publish, then activate
7. Rollback:
   - New agent: `sf project delete source --metadata AiAuthoringBundle:[AgentName] --target-org [alias]`
   - Backing Apex: `sf project delete source --metadata ApexClass:[ClassName] --target-org [alias]`

### Modify Existing Agent (version-safe path)

For agents already in the org (e.g., SDO/IDO pre-installed agents). Uses Agent Script — retrieve the existing agent, comprehend it, modify, publish as a new version.

**Before deploying, fire notification and ask:**
```bash
osascript -e 'display notification "About to modify existing agent: [AgentName] (currently v[N]) — [plain English description]" with title "SF Demo Scout — Input Needed"'
```
> "⚠️ About to modify existing agent [AgentName] (currently v[N]). This agent may be part of pre-installed demo scenarios. Changes will publish as v[N+1]. Rollback: `sf agent activate --api-name [AgentName] --version-number [N]`. Proceed? (yes/no)"

Wait for confirmation. If yes, proceed autonomously:
1. Load `developing-agentforce` skill — follow its "Modify an Existing Agent" workflow
2. Note the current active version number before any changes (rollback target)
3. Comprehend existing agent structure, update Agent Spec
4. Validate and preview before publishing
5. Publish (creates new version), then activate
6. Rollback: `sf agent deactivate --json --api-name [AgentName]` then `sf agent activate --json --api-name [AgentName] --version-number [N]`

### Always SE Manual Checklist
- Multi-agent orchestration
- Custom model/LLM config
- Channel assignment and configuration
- Production-scale test suites