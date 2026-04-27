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

## Script Deliverable Rules (cross-phase)

Applies whenever a sub-agent produces a reusable shell or language script as part of its deliverable — data-seeding scripts, Apex test-data factories, agent smoke-test harnesses, cleanup scripts. The script is an SE-runnable artifact that outlives the session.

**Default execution pattern (Pattern B — idempotent script):**
1. The script MUST be idempotent — safe to re-run after partial success. Upserts or existence-check-then-insert over blind inserts; external-Id lookups over hardcoded Ids.
2. The script MUST expose a `--pilot-only` flag that exercises every code path against one target record (or the minimum viable slice) before the bulk path runs. Exit code 0 with expected counts = pass; anything else = fail.
3. The orchestrator runs the script within the current session after SE confirmation (immediate verified state). The same script is the SE's re-run path for future re-spins or handoffs.
4. If the script cannot be idempotent for a legitimate reason (single-shot schema migration, destructive cleanup), Pattern A applies: a resumable sub-agent invoked via SendMessage. Document the reason in `discovery_notes`. Pattern B is the default; Pattern A is the exception.

**Mandatory self-test before returning the deliverable:**
1. `bash -n [script]` — syntax check. Cheap insurance against later edits; will NOT catch runtime bugs (subshell exports, `declare -A` under Bash 3.2, JSON envelope unwrap, while-loop counter scope). Run it anyway.
2. `bash [script] --pilot-only` against the live target org — the mandatory step that exercises every code path at low cost. Confirm exit 0 AND expected record counts (e.g., 1 pilot record inserted) BEFORE returning the sub-agent's output. This is what actually catches the Bash 3.2 / declare -A class of failure.
3. If the self-test fails, fix the script and re-run `--pilot-only` until it passes. Every bug caught during self-test goes in the `issues` array verbatim (with the error or symptom). Do NOT hide them behind a successful final run — the orchestrator and the SE need to know what was fragile. The sub-agent MUST be honest about the state of its deliverable.
4. If a bug reflects a runtime-environment design constraint that future sub-agents should know about (e.g., "target SE Mac runs Bash 3.2 — avoid `declare -A`, use temp-file JSON for Python↔bash state handoff"), record it in `discovery_notes` as well — it carries forward; `issues` is this session only.

**SE-runnable standalone contract:**
- Same flags, same exit codes, same idempotency whether the orchestrator or the SE runs it.
- No hardcoded session paths, temp-file assumptions, or parent-shell state. The script self-contains everything it needs.
- Script lives at `orgs/[alias]-[customer]/[script-name].sh` (or language-appropriate extension). Change log records its path and the `--pilot-only` + bulk invocation commands. Handover brief surfaces both commands under Your Files.

**Target environment defaults (macOS SE laptop):**
- Assume Bash 3.2 (Apple ships this as `/bin/bash`). No `declare -A`, no `${var^^}`, no `&>`. If associative arrays are genuinely needed, use temp-file JSON parsed via `python3` / `jq`.
- Assume `python3` and `jq` available (both in standard SE install). `sf` CLI and MCP available in-session only — the SE re-run path uses `sf` CLI.

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
   SELECT Layout.Name, RecordType.Name
   FROM ProfileLayout
   WHERE TableEnumOrId = '[Object]'
   AND Profile.Name = 'System Administrator'
   ```
2. Retrieve only the layout(s) returned by that query — not all layouts for
   the object.
3. Modify and redeploy only the active layout.
4. If multiple record types are in scope, run the query per record type and
   retrieve each assigned layout separately.

---

## Flow Rules (Phase 2)

Two autonomous flow types: **record-triggered** (single-object) and **screen flows**
(≤3 linear screens by default, ≤5 when the spec's Screen Flow section carries SE
justification). Scheduled flows, subflows, and multi-object flows still route to the
SE Manual Checklist — if one reaches you, skip it and note "out of scope for
autonomous deploy."

### Both Types
1. Invoke the `sf-flow` skill before generating any Flow XML — it holds the
   110-point validation checklist and the reference assets.
2. Before generating, skim `.claude/skills/sf-flow/references/xml-gotchas.md`
   if present — it covers root-level alphabetical ordering, fault-connector
   self-reference, relationship-field traps in recordLookups, and the
   `storeOutputAutomatically` data-leak risk. These are deployment blockers.
3. Validate generated XML against the sf-flow checklist. Flag failures in the
   `issues` array of your JSON output.
4. Deploy as Draft first (`<status>Draft</status>`). Confirm success.
5. Check for existing flows on the same object via MCP `retrieve_metadata` —
   flag execution order conflicts in `issues`.
6. Rollback command (record in `rollback_commands` array):
   `sf project delete source --metadata Flow:[FlowApiName] --target-org [alias]`

### Record-Triggered Flow
- Source template: `.claude/skills/sf-flow/assets/record-triggered-after-save.xml`
  (after-save) or `record-triggered-before-save.xml` (before-save). Fall back to
  the inline template in `phase2.md` if the asset is missing.
- Activate after Draft deploys cleanly.

### Screen Flow
- Source template: `.claude/skills/sf-flow/assets/screen-flow-template.xml`.
- Whitelisted screen components: DisplayText, Section, InputField (Text,
  LargeTextArea, Number, Email, Date, DateTime, Password), Picklist,
  RadioButtons, Checkbox, CheckboxGroup, MultiSelectPicklist. Any other
  component in the spec → skip with reason "component outside autonomous
  whitelist."
- Terminal DML is one of: recordCreates, recordUpdates, recordLookups
  (specify `<queriedFields>` — never `<storeOutputAutomatically>` in screen
  flows, per xml-gotchas).
- Multi-screen flows: collect ALL input across screens first (variables),
  perform DML after the final input screen. Each screen breaks the transaction
  boundary — premature DML cannot be rolled back by later navigation.
- Custom input validation allowed: Boolean formula + custom error message per
  input (per Salesforce docs — "Improve Data Quality by Validating User Input").
- **Deployment validation (autonomous):** after Draft deploys, generate a
  happy-path FlowTest XML (inputs populated to satisfy validation, assertion on
  the terminal DML outcome) and run `sf flow run test --class-names [FlowApiName]
  --target-org [alias] --json`. If the test passes, activate. If it fails twice,
  skip activation and record the failure in `issues` — do not activate a flow
  that failed its own smoke test. See `.claude/skills/sf-flow/references/testing-guide.md`
  section 5 for FlowTest XML patterns.
- **QuickAction wiring (if the spec's Screen Flow section requests it):** deploy
  a `QuickAction` metadata file alongside the flow, set to action type `Flow`
  with the flow's API name. Add the QuickAction to the object's active page
  layout (`retrieve_metadata` → add under `<quickActionListItems>` → redeploy).
  This is what makes the flow reachable from the UI; spec-level buttons are
  meaningless without it.

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
