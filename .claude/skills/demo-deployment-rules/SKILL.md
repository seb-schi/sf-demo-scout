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

One home per category:
- **Phase 1** (Queues, Picklists, Page Layouts, Business Processes, Paths) — rules live inlined under IF markers in `.claude/prompts/phase1.md`. This skill file does NOT duplicate them. If a Phase 1 sub-agent needs a rule, it reads its own prompt.
- **Phase 2 and Phase 3** (Flows, Apex, LWC, Agentforce) — phase prompts delegate to external skills (`sf-flow`, `sf-apex`, `sf-lwc`, `developing-agentforce`). This skill file carries the rollback commands, two-attempt meta-rule, unfamiliar-error escalation, and Script Deliverable Rules that the phase prompts reference but do not inline.
- **Cross-phase** — Script Deliverable Rules (below) apply to any sub-agent producing a reusable shell / language script, regardless of phase.

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

## Flow Rules (Phase 2)

Autonomous-with-SE-gate flow scope matches `sf-flow`'s full trigger spectrum: record-triggered (before-save / after-save / before-delete; any object; cross-object DML allowed), screen flows (whitelist below), autolaunched flows, subflows, scheduled flows, and platform-event-triggered flows. Orchestration flows and complex screen flows route to SE Manual — if one reaches Phase 2, skip with reason "out of scope for autonomous deploy — SE Manual Checklist."

### All Flow Types
1. Invoke the `sf-flow` skill before generating any Flow XML — it holds the 110-point validation checklist, the full asset template set, and reference guides.
2. Before generating, skim `.claude/skills/sf-flow/references/xml-gotchas.md` — root-level alphabetical ordering, fault-connector self-reference, relationship-field traps in recordLookups, `storeOutputAutomatically` data-leak risk. Deployment blockers.
3. Validate generated XML against the sf-flow checklist. Flag failures in `issues`.
4. Deploy as Draft first (`<status>Draft</status>`). Confirm success.
5. Generate and deploy a happy-path FlowTest XML alongside the flow. Run `sf flow run test --class-names [FlowApiName]_Test --target-org [alias] --json`. Pass → activate. Fail twice → skip activation, record in `issues` — never activate a flow that failed its own smoke test. Per-type FlowTest adaptations live in `phase2.md` Flow Rules step 4.
6. Check for existing flows on the same object/trigger via `retrieve_metadata` — flag execution order conflicts in `discovery_notes`.
7. Rollback (record in `rollback_commands`):
   `sf project delete source --metadata Flow:[FlowApiName] --target-org [alias]`
   Plus `QuickAction:[Name]` if deployed, `FlowTest:[FlowApiName]_Test` if deployed.

### Record-Triggered Flow
- Templates: `record-triggered-before-save.xml`, `record-triggered-after-save.xml`, `record-triggered-before-delete.xml`.
- Before-delete: `<recordTriggerType>Delete</recordTriggerType>` + `<triggerType>RecordBeforeDelete</triggerType>`. No after-delete flavor exists.
- Cross-object DML (trigger on Object A, create/update Object B) is in scope.

### Screen Flow
- Template: `screen-flow-template.xml`. LWC-embedded variant (`screen-flow-with-lwc.xml`) is out of autonomous scope.
- Whitelisted components: DisplayText, Section, InputField (Text, LargeTextArea, Number, Email, Date, DateTime, Password), Picklist, RadioButtons, Checkbox, CheckboxGroup, MultiSelectPicklist. Any other component → skip with reason "component outside autonomous whitelist."
- Terminal DML: recordCreates, recordUpdates, or recordLookups (specify `<queriedFields>` — never `<storeOutputAutomatically>` in screen flows, per xml-gotchas).
- Multi-screen: collect all input across screens first (variables), DML after the final input screen. Each screen breaks the transaction boundary.
- Custom input validation allowed: Boolean formula + custom error message per input.
- QuickAction wiring (if spec requests it): deploy `QuickAction` (actionType=Flow), retrieve active layout, add under `<quickActionListItems>`, redeploy.

### Autolaunched Flow
- Template: `autolaunched-flow-template.xml`.
- No UI, no trigger. Invoked from Apex (`Flow.Interview`), subflow, process, or REST. FlowTest exercises via `<parameters>` block providing input variables.

### Subflow
- Stored and deployed as an autolaunched flow; the "subflow" distinction is invocation-pattern only.
- Deploy subflows **before** their parent in the same phase — parent's static reference fails deploy if the subflow is missing.
- Parent flow exercises the subflow transitively; a dedicated FlowTest on the subflow is still required per the All Flow Types rule.
- Reusable patterns: `.claude/skills/sf-flow/assets/subflows/` (bulk-updater, dml-rollback, email-alert, error-logger, query-with-retry, record-validator).

### Scheduled Flow (Gated)
- Template: `scheduled-flow-template.xml`. Built on autolaunched skeleton with a `<schedule>` block in `<start>`.
- Spec must provide: `<startDate>` (YYYY-MM-DD, ≥ demo date unless recurring), `<startTime>` (HH:MM:SS), `<frequency>` (Once / Daily / Weekly / Monthly / Yearly / Hourly / Weekdays — FlowSchedule subtype, API v66.0+). Pre-flight: if any field missing in spec, skip.
- Optional object filter: `<object>` + `<filters>` for batch-record runs (max 250K interviews/day).
- Runs as Default Workflow User. `SCHEDULED_FLOW_DETAIL` debug log event confirms record count per run.
- FlowTest runs the flow body on-demand; the schedule config is verified via `retrieve_metadata` read-back.

### Platform-Event-Triggered Flow (Gated)
- Template: `platform-event-flow-template.xml`.
- `<start><object>` = platform event API name (`CustomEvent__e` or standard — AIPredictionEvent, BatchApexErrorEvent, FlowExecutionErrorEvent, etc.).
- Pre-flight: confirm the event object exists via `retrieve_metadata`. If the spec deploys a new platform event in the same run, deploy the event before the flow.
- Event references can't directly populate a record variable — create a flow variable per field the flow uses and map in the caller (per Salesforce docs, Paused Flow Interview Considerations).
- FlowTest supplies a mock event payload via `<parameters>` blocks, one per referenced event field.

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
