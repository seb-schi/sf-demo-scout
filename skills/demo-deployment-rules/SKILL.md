---
name: demo-deployment-rules
description: >
  Scout's deployment reference: known deploy-error patterns, script deliverable rules, rollback and per-type deployment rules. /scout and its workers read it by path; it is not invoked on its own.
disable-model-invocation: true
---

# Deployment Rules — Canonical Reference

One home per category:
- **Phase 1** (Queues, Picklists, Page Layouts, Lightning Record Page edits, Business Processes, Paths) — rules live inlined under IF markers in `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md`. This skill file does NOT duplicate them. If a Phase 1 sub-agent needs a rule, it reads its own prompt.
- **Phase 2 and Phase 3** (Flows, Apex, LWC, Agentforce) — phase prompts delegate to external skills (`sf-flow`, `salesforce-development:platform-apex-generate`, `experience-lwc:experience-lwc-generate`, `agentforce-adlc:agentforce-generate`). This skill file carries the rollback commands, the attempt-rule meta-rule, unfamiliar-error escalation, and Script Deliverable Rules that the phase prompts reference but do not inline. The Known Deploy-Error Patterns catalog lives in `references/deploy-error-patterns.md` (loaded on demand on a deploy failure).
- **Cross-phase** — Script Deliverable Rules (below) apply to any sub-agent producing a reusable shell / language script, regardless of phase.

**Attempt rule (pattern-gated, ten attempts, then a check-in):** every retry must carry a *new* fix —
never redeploy unchanged metadata, it fails identically.
- **Attempt 1** — deploy. On failure, check the error against the **Known
  Deploy-Error Patterns** section below.
- **Each next attempt** — if the error **matched a pattern**, apply the
  documented fix and redeploy. If **no pattern matched**, follow the
  Unfamiliar-errors path, then redeploy. Keep going while each attempt surfaces
  a *different* error that carries a new fix: a matched pattern, a Docs insight,
  or the cause read from the org, its logs or the deploy's component failures.
- **STOP** when an attempt fails with an error you already tried to fix, when no
  new fix is available, or when the fix needs something outside the approved scope.
  When the last attempt failed conclusively, record the item
  as `failed` with the error message, the pattern IDs tried, the state left and
  whether rollback occurred, and continue with the remaining items. A write whose
  outcome isn't settled stays `unverified` with its pending evidence; never resend it.
- **At attempt 10, and every ten after it**, check in with the builder: say what you tried
  and what's left, and continue under this same rule only on their yes, for ten more
  attempts; the count runs across generation, deployments and tests for the item.
  Without a yes, stop as above.
  A worker that can't ask returns both to its orchestrator, which asks. This rule
  never raises an official skill's own cap on an org-wide or permanent step, such as
  a sharing-default deploy or the Email-to-Case apply script.

**Unfamiliar errors:** if the error message is not self-evident, not already
in a loaded `orgs/lessons/` topic, and not matched by a Known Deploy-Error Pattern, read
`${CLAUDE_PLUGIN_ROOT}/skills/demo-docs-consultation/SKILL.md` before the next attempt. Record the
consultation in `docs_consulted`.

---

## Known Deploy-Error Patterns

The full catalog of deterministic fixes for recurring Salesforce metadata
deploy errors lives in
[`references/deploy-error-patterns.md`](references/deploy-error-patterns.md).
**On a deploy failure, read that file**, match the error, and apply the
documented fix — the attempt rule above counts a match as the next attempt.
These are org-agnostic parse errors (distinct from `orgs/lessons/`, which
holds org-specific gotchas); a rule-based fix is preferred over improvising.

The catalog currently covers FlexiPage (Pattern A — duplicate
componentInstance; Pattern B — design-time component not found), PermissionSet
(Pattern C — FLS on a required / master-detail field), and LWC (Pattern D —
literal in template expression / apiVersion-66). Pattern B drops a component the
org can't resolve, never re-guessing it, and hands it over for App Builder; a second
one stops the page edit (the record page convergence rule below). To extend
the catalog, propose a new pattern to Scout's maintainers; org-*specific*
gotchas still go to `orgs/lessons/` (topic-clustered).

---

## Script Deliverable Rules (cross-phase)

Applies whenever a sub-agent produces a reusable shell or language script as part of its deliverable — data-seeding scripts, Apex test-data factories, agent smoke-test harnesses, cleanup scripts. The script is a builder-runnable artifact that outlives the session.

**Default execution pattern (Pattern B — idempotent script):**
1. The script MUST be idempotent — safe to re-run after partial success. Upserts or existence-check-then-insert over blind inserts; external-Id lookups over hardcoded Ids.
2. The script MUST expose a `--pilot-only` flag that exercises **every distinct command/object path the bulk run uses** — one real guarded write per (CLI verb × target object) combination, against one target record each (or the minimum viable slice) — before the bulk path runs. A pilot that touches only one path while the bulk run uses several is structurally unable to catch a bug in the untested paths. Exit code 0 with expected counts on every exercised path = pass; anything else = fail.
3. The orchestrator runs the script within the current session after the builder's confirmation (immediate verified state). The same script is the builder's re-run path for future re-spins or handoffs.
4. If the script cannot be idempotent for a legitimate reason (single-shot schema migration, destructive cleanup), Pattern A applies: a resumable sub-agent invoked via SendMessage. Document the reason in `discovery_notes`. Pattern B is the default; Pattern A is the exception. If creating a new worker for Pattern A, prepend this block with the resolved absolute plugin root; a resumed worker keeps its original envelope:

   > Scout is installed. Before any Salesforce org change, including a quick fix outside a Scout command, read "[PLUGIN_ROOT_ABS]/AGENTS.md" and follow it.
   > Get the builder's explicit confirmation before:
   > - Delete existing metadata or records
   > - Modify existing profiles or permission sets
   > - Touch anything prefixed `sb_` or `managed__`


**Mandatory self-test before returning the deliverable:**
1. `bash -n [script]` — syntax check. Cheap insurance against later edits; will NOT catch runtime bugs (subshell exports, `declare -A` under Bash 3.2, JSON envelope unwrap, while-loop counter scope). Run it anyway.
2. `bash [script] --pilot-only` against the live target org — the mandatory step that exercises every distinct command/object path at low cost. If the bulk run does `import bulk` on three objects plus an `update record` on a fourth, the pilot MUST exercise all four (verb × object) combinations, not just the cheapest one — a pilot that validates a single path while the real run uses several will certify a script whose untested paths are broken. Confirm exit 0 AND expected record counts (e.g., 1 pilot record per exercised path) BEFORE returning the sub-agent's output. This is what actually catches the Bash 3.2 / declare -A class of failure AND a wrong CLI verb on a path the pilot would otherwise skip.
3. If the self-test fails, fix the script and re-run `--pilot-only` until it passes. Every bug caught during self-test goes in the `issues` array verbatim (with the error or symptom). Do NOT hide them behind a successful final run — the orchestrator and the builder need to know what was fragile. The sub-agent MUST be honest about the state of its deliverable.
4. If a bug reflects a runtime-environment design constraint that future sub-agents should know about (e.g., "target Mac runs Bash 3.2 — avoid `declare -A`, use temp-file JSON for Python↔bash state handoff"), record it in `discovery_notes` as well — it carries forward; `issues` is this session only.

**Builder-runnable standalone contract:**
- Same flags, same exit codes, same idempotency whether the orchestrator or the builder runs it.
- No hardcoded session paths, temp-file assumptions, or parent-shell state. The script self-contains everything it needs.
- Script lives at `orgs/[alias]-[customer]/[script-name].sh` (or language-appropriate extension). Change log records its path and the `--pilot-only` + bulk invocation commands. Handover brief surfaces both commands under Your Files.

**Target environment defaults (the builder's macOS laptop):**
- Assume Bash 3.2 (Apple ships this as `/bin/bash`). No `declare -A`, no `${var^^}`, no `&>`. If associative arrays are genuinely needed, use temp-file JSON parsed via `python3` / `jq`.
- Assume `python3` and `jq` available (both in a standard install). `sf` CLI and MCP available in-session only — the builder's re-run path uses `sf` CLI.

**Salesforce CLI data-write command reference (pin these — do not invent verbs):**

At demo-seed scale (handfuls to low hundreds of records — every Scout seed) use the **single-record** commands. They return clean JSON and need no CSV:
- Create one record: `sf data create record --sobject <Object> --values "Field1=val Field2=val" --target-org <alias> --json`
- Update one record: `sf data update record --sobject <Object> --record-id <Id> --values "Field=val" --target-org <alias> --json`
- Query: `sf data query --query "<SOQL>" --target-org <alias> --json`

**Bulk API 2.0** is for thousands of records and is rarely warranted in a demo seed. If genuinely needed, the verbs are (Bulk API 2.0, `sf` v2):
- Create / insert: `sf data import bulk` (paired with `sf data import resume`). **There is NO `sf data create bulk`** — that verb does not exist; `import bulk` IS the insert path.
- Upsert: `sf data upsert bulk` (paired with `sf data upsert resume`) — requires an external-Id field.
- Update: `sf data update bulk`. Delete: `sf data delete bulk`. Export: `sf data export bulk`.
- Bulk commands take **CSV input only (not JSON)** and one object per call. They run async: the `bulk` verb submits a job and returns a `jobId`; the success/failed record counts and the `*-success-records.csv` / `*-failed-records.csv` files come from `sf data bulk results --job-id <id>` (or the paired `resume` command) — NOT from the submitting command's immediate output.
- Bulk-write success-check therefore reads the job result's failed-record count, NOT the submit command's exit code — a submitted job can exit 0 yet have per-record failures.

---

## Lightning Record Page Edits — scope, convergence & rollback (Phase 1)

Full procedure lives under `<!-- IF:LRP -->` in `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Lightning Record Page — Edit Rules". This summary is for orchestrator-level decisions and rollback.

**Scope (Gated, confirmed once):** additive edits to an existing record page: a new tab in an existing tabset, a component in an existing region or tab, a new field section, fields in an existing section, the Path component, or an LWC built in the same task. The confirmation names the page, the region, tab or section, and each component.

**Needs its own yes:** moving, changing or removing an existing component, or converting the page to Dynamic Forms. Pages prefixed `sb_` or `managed__` keep the confirmation tier.

**Stays on the manual checklist (App Builder):** a new page from scratch, a page that belongs to a managed package, the page's activation or assignment, and whatever the convergence rule drops.

**Route, in order:** (1) `salesforce-development:platform-flexipage-generate`, with `salesforce-development:platform-metadata-api-context-get` for the schema and the overrides in `${CLAUDE_PLUGIN_ROOT}/prompts/building/official-skill-overrides.md` §"FlexiPage scope"; (2) Scout's field-section append, when that skill can't run here and the change is fields only; (3) App Builder by hand, last.

**Convergence rule:** nothing ungrounded is written. Every component and property comes from a page in this org that uses it, the skill's references, an LWC's own source (one this task built, or retrieved from the org) or a fetched Docs page. A component the org rejects in a dry run is dropped, never re-guessed, and handed over with its App Builder step (Pattern B). A second such rejection on the same page stops the edit: drop that component too and dry-run what's left once more, so component errors cost at most three dry runs. Other errors, such as structural XML ones (Pattern A), follow the skill's XML rules and the attempt rule.

**Incumbents:** before the first dry run on the edited file, and after the deploy on the page read back, run `scripts/scout_page_check.py` against the first verified `component-preedit` snapshot: every existing identifier, facet and region is still there, under the same parent and in the same order, with its properties and visibility rule unchanged. A missing, moved or changed incumbent is a failure that rolls back. A `record_detail` page (built on `force:detailPanel`) shows the classic Page Layout's fields, so fields for it go to the layout; the audit's composition classes are leads, never a gate.

**Rollback:**
- The pre-edit FlexiPage XML is preserved with `preserve --kind component-preedit` before any edit. Restore the first verified original and redeploy:
  `sf project deploy start --metadata FlexiPage:[Name] --target-org [alias]`
- There is no `sf project delete source --metadata FlexiPage:[Name]` rollback path because deletion would remove the page entirely (catastrophic for a live demo surface). Always restore-and-redeploy.

## Flow Rules (Phase 2)

Gated flow scope matches `sf-flow`'s full trigger spectrum: record-triggered (before-save / after-save / before-delete; any object; cross-object DML allowed), screen flows, autolaunched flows, subflows, scheduled flows, platform-event-triggered flows, and docs-confirmed orchestration metadata. Screen-flow logic (branching, cross-screen reactivity, formula dependencies) is in scope, with any number of screens and any screen component. `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase2.md` §"Flow Rules" decides each Flow's validation: the required FlowTests where Salesforce supports one for that shape, otherwise Draft and visual QA, as for every screen flow. A live orchestration run creates work items, so it runs only on the builder's yes. Never activate a Flow that failed its own test.

### All Flow Types
1. Author in the order of `${CLAUDE_PLUGIN_ROOT}/prompts/building/official-skill-overrides.md` §"Flow scope": Salesforce's hosted generator for a new Flow, then the official skills, and the `sf-flow` skill last (its 110-point checklist, templates and references).
2. Before deploying hand-written XML, skim `${CLAUDE_PLUGIN_ROOT}/skills/sf-flow/references/xml-gotchas.md` — root-level alphabetical ordering, fault-connector self-reference, relationship-field traps in recordLookups, `storeOutputAutomatically` data-leak risk. Deployment blockers.
3. On the `sf-flow` route, validate the XML against its checklist. Flag failures in `issues`.
4. Deploy as Draft first (`<status>Draft</status>`). Confirm success.
5. Where the validation mode is `flow_test_required`, author each FlowTest from the `sf-flow` skill's guide and templates and run it (`sf flow run test --class-names [FlowApiName]_Test --target-org [alias] --json`). Repair a failure as `building/phase2.md` Flow Rules step 4 says: classify it, make a new fix each time within the attempt rule, and stop on a repeat. Activate only the tested version, after every required test passes; record a failure in `issues`. An `unsupported` Flow stays Draft for visual QA.
6. Check for existing flows on the same object and trigger (retrieve them) — flag execution order conflicts in `discovery_notes`.
7. Rollback (record in `rollback_commands`):
   `sf project delete source --metadata Flow:[FlowApiName] --target-org [alias]`
   Plus `QuickAction:[Name]` if deployed, `FlowTest:[FlowApiName]_Test` if deployed.

### Record-Triggered Flow
- Templates: `record-triggered-before-save.xml`, `record-triggered-after-save.xml`, `record-triggered-before-delete.xml`.
- Before-delete: `<recordTriggerType>Delete</recordTriggerType>` + `<triggerType>RecordBeforeDelete</triggerType>`. No after-delete flavor exists.
- Cross-object DML (trigger on Object A, create/update Object B) is in scope.

### Screen Flow
- Templates: `screen-flow-template.xml`, and `screen-flow-with-lwc.xml` for a custom LWC screen component.
- Any screen component (Repeater, Data Table, File Upload, Kanban Board and custom LWC screens included) and any number of screens. Confirm an unfamiliar component in Docs first (`demo-docs-consultation` trigger 3).
- Record lookups name `<queriedFields>`; never `<storeOutputAutomatically>` in screen flows (per xml-gotchas).
- Multi-screen: collect input across screens first (variables), then write after the last input screen, unless the story needs a save between screens. Each screen breaks the transaction boundary.
- Custom input validation allowed: Boolean formula + custom error message per input.
- QuickAction wiring (when the request asks for it): deploy `QuickAction` (actionType=Flow), retrieve active layout, add under `<quickActionListItems>`, redeploy.

### Autolaunched Flow
- Template: `autolaunched-flow-template.xml`.
- No UI, no trigger. Invoked from Apex (`Flow.Interview`), subflow, process, or REST. FlowTest exercises via `<parameters>` block providing input variables.

### Subflow
- Stored and deployed as an autolaunched flow; the "subflow" distinction is invocation-pattern only.
- Deploy subflows **before** their parent in the same phase — parent's static reference fails deploy if the subflow is missing.
- Parent flow exercises the subflow transitively; a dedicated FlowTest on the subflow is still required per the All Flow Types rule.
- Reusable patterns: `${CLAUDE_PLUGIN_ROOT}/skills/sf-flow/assets/subflows/` (bulk-updater, dml-rollback, email-alert, error-logger, query-with-retry, record-validator).

### Scheduled Flow (Gated)
- Template: `scheduled-flow-template.xml`. Built on autolaunched skeleton with a `<schedule>` block in `<start>`.
- Schedule: the bundled confirmation proposes `<startDate>` (YYYY-MM-DD: the demo date the builder gave, else the next day; not before it unless recurring), `<startTime>` (HH:MM:SS, before the demo) and `<frequency>` (Once, Daily or Weekly, what a schedule-triggered flow offers; another cadence only when the Docs ground it for this flow type) to fit the story. Build with them, or with the builder's changes, on their go.
- Optional object filter: `<object>` + `<filters>` for batch-record runs (max 250K interviews/day).
- Runs as Default Workflow User. `SCHEDULED_FLOW_DETAIL` debug log event confirms record count per run.
- No FlowTest covers a scheduled flow (`phase2.md` marks it `unsupported`): read back the deployed `<schedule>` block, and leave the run itself to visual QA.

### Platform-Event-Triggered Flow (Gated)
- Template: `platform-event-flow-template.xml`.
- `<start><object>` = platform event API name (`CustomEvent__e` or standard — AIPredictionEvent, BatchApexErrorEvent, FlowExecutionErrorEvent, etc.).
- Pre-flight: check that the event object exists in the org (retrieve or describe it). If this build creates the event, deploy it before the flow. Ask the builder only when it's absent and not planned.
- Event references can't directly populate a record variable — create a flow variable per field the flow uses and map in the caller (per Salesforce docs, Paused Flow Interview Considerations).
- No FlowTest: platform-event-triggered flows deploy as Draft for visual QA, as phase 2's Flow Rules say.

---

## Apex Rules (Phase 2)

Scope: triggers, classes, and invocable actions — multi-class and cross-object
are in scope. No "complexity" cutoff; the gate is the test signal + the bounded
fix-loop (`salesforce-development:platform-apex-test-run` → `salesforce-development:platform-apex-logs-debug`), not a size label.
Author a test class for every class/trigger; a failing / low-coverage test is
recorded in `issues` and NEVER blocks the deploy (the build ships test-unvalidated
for the builder to finish in this session).
Tests that insert records of a new record type create their own user and grant the
record type through a permission set, outside `System.runAs`; they insert those
records as that user, inside it. From API 67.0, a test that inserts them on the
deploying admin's own access fails with `INVALID_CROSS_REFERENCE_KEY`, "this ID value
isn't valid for the user": grant the record type first, to the test's user or to the admin.

1. Invoke `salesforce-development:platform-apex-generate` skill for generation rules.
2. Run Code Analyzer before deploying through
   `salesforce-code-quality:dx-code-analyzer-run`, once its own prerequisite
   checks succeed. Record any high-severity findings in `issues`.
3. Rollback commands:
   - `sf project delete source --metadata ApexClass:[ClassName] --target-org [alias]`
   - `sf project delete source --metadata ApexTrigger:[TriggerName] --target-org [alias]`

---

## LWC Rules (Phase 2)

Scope: demo-specific UI — Customer 360 Cards, custom record views, branded
components — one component or several, under one rule; no size or complexity
label decides anything.

1. Invoke `experience-lwc:experience-lwc-generate` before generating any
   component file (scaffolding, SLDS, validation).
2. Run Code Analyzer before deploying through
   `salesforce-code-quality:dx-code-analyzer-run`, once its own prerequisite
   checks succeed. Record high-severity findings in `issues`.
3. Signals: Code Analyzer, a dry run, read-back of the bundle, and the skill's
   Jest tests where the project already runs Jest (nothing is installed for them
   without the builder's yes). The rendered result has no build-time signal:
   report it deployed — needs visual QA.
4. Rollback command:
   `sf project delete source --metadata LightningComponentBundle:[ComponentName] --target-org [alias]`

---

## Agentforce Rules (Phase 3)

Two paths depending on whether the agent is new or already exists in the
org. Both use the ADLC skill suite (`agentforce-adlc:agentforce-generate`,
`agentforce-adlc:agentforce-test`, `agentforce-adlc:agentforce-observe`).

### New Agent (Agent Script path)

Scope: single agent, topic-based routing with Apex or Flow backing actions.

1. Invoke `agentforce-adlc:agentforce-generate` skill — follow its "Create an Agent"
   workflow.
2. Check for existing agents (retrieve them) — flag conflicts
   in `issues`.
3. Run Code Analyzer on Apex backing actions through
   `salesforce-code-quality:dx-code-analyzer-run`, once its own prerequisite
   checks succeed.
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

1. Invoke `agentforce-adlc:agentforce-generate` skill — follow its "Modify an Existing
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

After the agent is activated, run the official agent test suite using the `agentforce-adlc:agentforce-test` skill. Prefer Mode B (Testing Center) — build the `test-spec.yaml` from the spec's Agent test cases and run it:

1. Build `test-spec.yaml` in the official format (delegate the schema to `agentforce-adlc:agentforce-test`: `basic-test-spec.yaml` + `guardrail-test-spec.yaml` are authoritative). Map each spec test-case row to `utterance` / `expectedTopic` / `expectedActions` (Level-2 invocation names) / `expectedOutcome`. Include at least one guardrail/off-topic row. **Never attach the `instruction_following` / `conciseness` / `completeness` metrics** (UI crash / score-0 / routing penalty) — rely on `expectedOutcome` (LLM-as-judge).
2. Create: `sf agent test create --json --spec test-spec.yaml --api-name [Suite] -o [alias]`
3. Run: `sf agent test run --json --api-name [Suite] --wait 10 --result-format json -o [alias]`
4. Results: `sf agent test results --json --job-id [runId] -o [alias]` (use `--job-id` from the run output, NEVER `--use-most-recent`). Filter the guardrail false-negative: a `topic_assertion` FAILURE on a row with empty `expectedTopic` is spurious.
5. If `sf agent test` is unavailable, fall back to a Mode A `sf agent preview` conversational check (`start`/`send`/`end --authoring-bundle`) and record the fallback in `discovery_notes`.
6. Record results in the `smoke_test` object of your JSON output.

A failed test suite does NOT block deployment — the agent is already active. Record failures in `issues` and flag for the builder. The event-log Action-Invocation Probe (`building/sub-agent-validation.md`) remains the deterministic gate for hero-action invocation; the suite runs alongside it.

### Docs-confirmed UI-only (hard decline — skip with the doc citation)

A different model for an agent or a subagent is not on this list: it's Agent Script's `model_config` block, authored with the rest of the `.agent` source. Only the org's model provider setup in Setup stays manual.

These Agentforce surfaces have no Metadata API / Agent Script path (docs-confirmed); skip with reason "UI-only — Your Manual Checklist [cite]". They are NOT complexity declines — everything else in a spec is attempted (see Scout's `AGENTS.md` §Build Boundaries → Docs-Gated):
- Multi-agent orchestration **connection wiring** (Beta, UI-only) — but Scout DOES author the sub-agent + the parent's `connected_subagent` metadata; only the live connection is UI. See `prompts/building/agentforce-advanced-capabilities.md`.
- Channel assignment and configuration
- Production-scale test suites (Testing Center batch regression — Mode B) — a scope choice, not a capability limit; functional regression via `sf agent test` IS automated in Phase 3.
