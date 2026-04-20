---
name: demo-deployment-rules
description: >
  Canonical deployment rules for Flows, Apex, LWC, Agentforce, Page Layouts,
  Queues, and Picklists in SF Demo Prep. Two-attempt rule, rollback commands,
  and per-category deployment procedures.
  TRIGGER when: a phase sub-agent needs deployment rules outside its inlined
  scope, or needs to verify rollback command syntax.
  DO NOT TRIGGER when: deploying metadata (phase prompts inline the relevant
  rules), during sparring, or for permission set generation.
---

# Deployment Rules — Canonical Reference

Phase sub-agent templates inline the rules relevant to their phase. This
file is the canonical source of truth — if a template's inlined rules
diverge from this file, this file wins. Sub-agents may still invoke this
skill for rules outside their normal phase scope (e.g., a Phase 2 agent
that needs Queue rules for a dependency check).

**Two-attempt rule:** if a deployment fails twice, STOP that item, record it
as SKIPPED in your JSON output with the error message, and continue with
remaining items. Do not wrestle with a broken deploy.

**Unfamiliar errors:** if the error message is not self-evident and not
already in `building-lessons`, invoke the `demo-docs-consultation` skill
before the second attempt. Record the consultation in `docs_consulted`.

---

## Queue Rules (Phase 1)

Scope: queues needed for case/lead/custom object routing in the demo scenario.

1. Deploy Queue metadata via `deploy_metadata`. The XML structure:
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <Queue xmlns="http://soap.sforce.com/2006/04/metadata">
       <fullName>Queue_Api_Name</fullName>
       <name>Queue Label</name>
       <queueSobject>
           <sobjectType>Case</sobjectType>
       </queueSobject>
   </Queue>
   ```
   Multiple `<queueSobject>` elements for queues that receive multiple object types.
2. After deploying, verify via SOQL: `SELECT Id, Name FROM Group WHERE Type = 'Queue' AND DeveloperName = '[ApiName]'`
3. If the spec asks to add the running user as a queue member, use:
   `sf data create record --sobject GroupMember --values "GroupId=[QueueId] UserOrGroupId=[UserId]" --target-org [alias]`

---

## Picklist Value Additions (Phase 1)

When the spec asks to add values to an existing picklist field (standard or custom):

1. Retrieve the current field metadata via `retrieve_metadata`.
2. Add new `<value>` elements to the existing `<valueSet>` — do NOT remove existing values.
3. For standard value sets (e.g., Case.Type uses `CaseType` StandardValueSet), retrieve and modify the StandardValueSet, not the field directly.
4. Deploy the updated metadata. Verify by querying: `SELECT ApiName, Value FROM StandardValueSet WHERE ...` or by checking the field describe.

---

## Page Layout Rules (Phase 1)

Before modifying any page layout, identify which layout is actually active
for the demo user. Never retrieve "whichever layout comes first" — SDO orgs
have many layouts per object and the first one is rarely the active one.

1. Query `ProfileLayout` via Tooling API to find the layout assigned to
   System Administrator for the target object and record type:
   ```
   SELECT Layout.Name, RecordType.DeveloperName
   FROM ProfileLayout
   WHERE SobjectType = '[Object]'
   AND Profile.Name = 'System Administrator'
   ```
2. Retrieve only the layout(s) returned by that query — not all layouts for
   the object.
3. Modify and redeploy only the active layout.
4. If multiple record types are in scope, run the query per record type and
   retrieve each assigned layout separately.

---

## Flow Rules (Phase 2)

Scope: single-object, record-triggered only. No screen flows, scheduled
flows, or subflows. (The orchestrator filters the spec; if a complex flow
reaches you, skip it and note "out of scope for autonomous deploy.")

1. Invoke the `sf-flow` skill before generating any Flow XML — it holds the
   110-point validation checklist.
2. Validate generated XML against that checklist — work through it mentally,
   flag failures in the `issues` array of your JSON output.
3. Deploy as Draft first (`<status>Draft</status>`), confirm success, then
   activate.
4. Check for existing flows on the same object via MCP `retrieve_metadata` —
   flag execution order conflicts in `issues`.
5. Rollback command (record in `rollback_commands` array):
   `sf project delete source --metadata Flow:[FlowApiName] --target-org [alias]`

---

## Apex Rules (Phase 2)

Scope: single-trigger, single-object. No cross-object Apex. No test classes
(demo org context).

1. Invoke `sf-apex` skill for generation rules.
2. Run `run_code_analyzer` before deploying (if MCP available). Record any
   high-severity findings in `issues`.
3. Rollback commands:
   - `sf project delete source --metadata ApexClass:[ClassName] --target-org [alias]`
   - `sf project delete source --metadata ApexTrigger:[TriggerName] --target-org [alias]`

---

## LWC Rules (Phase 2)

Scope: demo-specific UI — Customer 360 Cards, custom record views, branded
components.

1. Use MCP LWC expert tools when available (scaffolding, SLDS, validation).
2. Run `run_code_analyzer` before deploying (if MCP available). Record
   high-severity findings in `issues`.
3. Rollback command:
   `sf project delete source --metadata LightningComponentBundle:[ComponentName] --target-org [alias]`

---

## Agentforce Rules (Phase 3)

Two paths depending on whether the agent is new or already exists in the
org. Both use the ADLC skill suite (`developing-agentforce`,
`testing-agentforce`, `observing-agentforce`).

### New Agent (Agent Script path)

Scope: single agent, topic-based routing with Apex or Flow backing actions.

1. Invoke `developing-agentforce` skill — follow its "Create an Agent"
   workflow.
2. Check for existing agents via MCP `retrieve_metadata` — flag conflicts
   in `issues`.
3. Run `run_code_analyzer` on Apex backing actions (if MCP available).
4. Validate via `sf agent validate authoring-bundle` before publishing.
5. Preview with `sf agent preview` before publishing.
6. Publish, then activate.
7. Rollback commands:
   - `sf project delete source --metadata AiAuthoringBundle:[AgentName] --target-org [alias]`
   - `sf project delete source --metadata ApexClass:[ClassName] --target-org [alias]` (backing Apex)

### Modify Existing Agent (version-safe path)

For agents already in the org (e.g., SDO/IDO pre-installed agents). Every
publish creates a new version; previous versions remain activatable, so
rollback is instant via `sf agent activate --version-number N`.

1. Invoke `developing-agentforce` skill — follow its "Modify an Existing
   Agent" workflow.
2. Note the current active version number before any changes (rollback
   target).
3. Comprehend existing agent structure, update Agent Spec.
4. Validate and preview before publishing.
5. Publish (creates new version), then activate.
6. Rollback commands:
   - `sf agent deactivate --json --api-name [AgentName] --target-org [alias]`
   - `sf agent activate --json --api-name [AgentName] --version-number [N] --target-org [alias]`

### Smoke Test (after activate — both paths)

After the agent is activated, run an ad-hoc smoke test using `testing-agentforce` skill (Mode A):

1. Read the spec's "Smoke test utterances" list. If no utterances are specified, generate 3 based on the agent's topic descriptions.
2. Start a preview session: `sf agent preview start --json --authoring-bundle [AgentName] -o [alias]`
3. Send each utterance: `sf agent preview send --json --session-id [ID] --utterance "[message]" --authoring-bundle [AgentName] -o [alias]`
4. End the session: `sf agent preview end --json --session-id [ID] --authoring-bundle [AgentName] -o [alias]`
5. Evaluate each response: did the agent select the correct topic? Did it invoke the expected backing action? Was the response coherent?
6. Record results in the `smoke_test` object of your JSON output.

A failed smoke test does NOT block deployment — the agent is already active. Record failures in `issues` and flag for the SE.

### Always Out of Scope (skip with reason)

If the spec asks for any of the following, skip with reason
"out of scope for autonomous deploy — SE Manual Checklist":
- Multi-agent orchestration
- Custom model/LLM config
- Channel assignment and configuration
- Production-scale test suites (Testing Center batch regression — Mode B)
