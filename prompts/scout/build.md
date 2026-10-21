# /scout build: complex plans

The router (`skills/scout/SKILL.md` and `prompts/scout/router-build.md`) routes complex plans here and still governs targeting, confirmation, dispositions and history. It needs `story` with beats on the open-ended path or when the task records one; complete briefs invent none.

## The plan, in the proposal
Show beats, then items, then write order; each item shows type, category, `depends_on` and the claims it backs. For each beat, list the UI surfaces it touches (form, list view, record page, app navigation, report, agent); each is an item or `already_satisfied` with its query, so a new object whose beat shows its form needs its layout. Confirm gated categories once, inside the bundled confirmation. Flow items first follow `${CLAUDE_PLUGIN_ROOT}/prompts/scout/hosted-flow.md` §"Inspection"; its lines join that confirmation. Classify Docs-gated items first: UI-only goes on the SE's checklist with a fetched citation naming the exact operation; authorable with no build-time signal is flagged for visual QA; fuzzy matching rules are authorable. No envelope, item cap or one-spec rule applies; platform facts stay Docs-gated dispositions. Tell the SE the items, gated categories and rough duration, then one line per item, never waiting. Record each live flip's expected ID in the block before executing it.

## Author in parallel, write in series
Run `python3 [PLUGIN_ROOT_ABS]/scripts/scout_history.py plan --task [T]`: it prints the write order (a topological order of `depends_on`; a cycle exits 3, so fix the plan with the SE), the authoring layers, `open_jobs` and `ready`, the items writable now.

Dispatch at most four authoring workers at once, one item each, in a fresh `prepare-workspace` project, with `prompts/scout/router-build.md`'s worker rules, the item's criterion, its contract row and the grounding duty in `${CLAUDE_PLUGIN_ROOT}/prompts/scout/router-build.md` §"Ground design and claims". Workers may make read-only org calls through the bound username after `check`, but never write to the org, run pilots or runtime tests, or open mutation-bearing previews. They return a delta against their baseline, grounding entries, issues and "authored; live validation pending". Draft a dependent from its predecessor's authored interface; reconcile it with the live schema once landed, or defer it.

Only the orchestrator writes to the org, the task record and the log. For each item, in write order:
1. Re-read the amendment log; an item withdrawn before its write becomes `omitted`.
2. Proceed only when every prerequisite is `applied` or `already_satisfied`. Otherwise the item is `blocked`, naming the prerequisite, unless an approved amendment replaces the dependency.
3. Run `check --write`, also before any retry.
4. Re-retrieve every touched component and apply the delta to current source, merging shared-file types (SharingRules, permission sets) with incumbents; keep the draft.
5. Stage the result in a fresh writer project; record the attempt in flight.
6. Execute with the type's own mechanism (terminal statuses in parentheses): Metadata API deploys polled with `sf project deploy report --job-id` (`Succeeded|SucceededPartial|Failed|Canceled|FinalizingDeployFailed`), synchronous data writes or Bulk jobs (`JobComplete|Failed|Aborted`), Email-to-Case's two-phase apply script (`Completed|Failed`), Agentforce's publish lifecycle (`Active|Inactive|NeedsUICommit|Failed`). Pilots and runtime tests run here.
7. While any job isn't terminal, the write slot stays occupied: no org mutation of any kind. Its checkpoint's `job:` line (an ID, else the executor) records `launched:` and `settled:`; only a terminal `status:` settles it. A timed-out job stays `unverified` with its job ID and launch receipt; recover a lost ID as `${CLAUDE_PLUGIN_ROOT}/prompts/building/scout-2-repair.md` §"Scout 2.0 existing-report repair" step 7 does. A read-back never settles a job that may still land.
8. Read back yourself; record the attempt's outcome and the item's disposition.

Write the companion permission set after the items it grants settle, extending it as later ones settle; omit failed items' grants, drop those items from the set's `depends_on` and name them in the log. A Service Agent's backing-action grants precede its validation probe. A failed, blocked or unverified item blocks its dependents; independent items and beats carry on. Never retry automatically: a retry is a new attempt after the error rule in `${CLAUDE_PLUGIN_ROOT}/prompts/scout/router-build.md` §"Ground design and claims", recording the covering lesson or the Docs search of the verbatim error as a grounding entry `{"attempt":"<retry-ID>","source":"lesson|docs","ref":"<lesson-ID|Docs-URL>",…}`. With Docs unavailable, record the Docs-unavailable entry instead: `ungrounded`, empty ref, verdict starting `Docs unavailable`.

## Per-type contracts
Take each source's technical rules; ignore its envelopes, ledgers, output formats, phase topology and model choices.

Type family | Procedure | Completion signal
---|---|---
Object, field, record type | `salesforce-development:platform-custom-object-generate`, `salesforce-development:platform-custom-field-generate`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Picklist Value Additions" | read-back
Permission set | `salesforce-development:platform-permission-set-generate`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Companion Permission Set — MANDATORY" | grants and assignment
App, tab | Docs: Metadata API `CustomApplication`, `CustomTab` | read-back
Queue, business process, path | `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Queue Rules", §"Business Process Rules", §"Path Rules" | read-back
Layout | `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Page Layout Rules" | placement read-back
Record page field section | `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Lightning Record Page — Field Section Add Rules" | read-back, then visual QA
Validation rule | `salesforce-development:platform-validation-rule-generate`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Validation Rule Rules" | read-back
List view | `salesforce-development:platform-list-view-generate`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"List View Rules" | read-back and results
Sharing rules | `salesforce-development:platform-sharing-rules-generate`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Sharing Rule Rules" | merged read-back
Report, report type | `salesforce-development:platform-report-generate`, `salesforce-development:platform-custom-report-type-generate`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Report Rules", §"Custom Report Type Rules" | read-back and a run
Existing report filter | `${CLAUDE_PLUGIN_ROOT}/prompts/building/scout-2-repair.md` §"Scout 2.0 existing-report repair" | the helper's read-back
Custom setting, metadata type | `salesforce-development:platform-custom-setting-generate`, `salesforce-development:platform-custom-metadata-type-generate`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Custom Setting Rules", §"Custom Metadata Type Rules" | read-back
Data | `salesforce-development:platform-data-manage`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Salesforce Data Seeding Quirks" | each claim's read-back
Email-to-Case | `service-engagement:service-email-to-case-configure`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Email-to-Case Rules" | the script's verification
Flow | `${CLAUDE_PLUGIN_ROOT}/prompts/scout/hosted-flow.md`, else `sf-flow`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase2.md` §"Flow Rules"; `${CLAUDE_PLUGIN_ROOT}/prompts/building/sub-agent-validation.md` §"Phase-2 Flow Evidence" | exact-version tests and activation
Apex | `salesforce-development:platform-apex-generate`, `salesforce-development:platform-apex-test-generate`, `salesforce-development:platform-apex-test-run`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase2.md` §"Apex Rules" | passing tests, bounded fix loop
LWC | `experience-lwc:experience-lwc-generate`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase2.md` §"LWC Rules" | read-back, then visual QA
Agentforce | `agentforce-adlc:agentforce-generate`, `agentforce-adlc:agentforce-test`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase3.md` §"New Agent (Agent Script path)", §"Modify Existing Agent (version-safe path)", §"Smoke Test + Validation Gate (after activate — both paths)"; `${CLAUDE_PLUGIN_ROOT}/prompts/building/agentforce-validation-gate.md` §"Validation Gate — REQUIRED before reporting an agent working" | smoke test and gate; preview gaps to visual QA
Anything else | `${CLAUDE_PLUGIN_ROOT}/AGENTS.md` §"Docs-Gated: attempt metadata-authorable work" | its Docs-cited disposition

A Flow item records its frozen validation mode and every required test. An Agentforce item references the evaluator's evidence file, with one obligation per required action and assertion, each with its own inputs. An `unavailable` test or invocation is visual QA, never a pass.

Block additions: `"complex":true`; a beat may hold `"flips":["FL1"]` and `"verification":{"verdict":"…","evidence":"…"}`; a claim holds `"result"` and, when optional, `"required":false`; an item seeding date-relative claims holds `"valid_until":"YYYY-MM-DD"`; the top level holds `"rehearsals":[{"flip":"FL1","record_id":"…","before":{…},"result":"passed|failed|not_rehearsable","evidence":"…"}]`. A Flow item holds `"flow_validation":{"flow_api_name":"…","mode":"flow_test_required|unsupported","required_tests":[…],"unsupported_reason":"…","version":N,"active_version":N}`; an Agentforce item holds `"obligations":[{"id":"…","agent_runtime":{…}}]` and `"agent_version":"<active-version-ID>"`. Both hold `"evidence_ref"`, a folder-relative JSON file: `flow_tests` rows `{test,flow_api_name,version,org_id,"outcome":"Pass|unavailable",reason}`, or `agent_contexts` plus `agent_runtime` keyed by obligation ID.

## Verify each beat
Run every claim's read-back yourself; record `claims[].result` as `passed`, `failed` or `dropped` (drop only claims marked `"required":false`). Match each on-screen noun to the record's shape (subtype, record type, the component the beat names): a "logged call" is a Task with `TaskSubtype = Call`.

Rehearse a live flip only in anonymous Apex inside an always-rolled-back savepoint, after a passing `check --write`, when Docs show every effect is undone. A flip that publishes a Publish Immediately event, makes a callout or starts async work goes to visual QA. Record each rehearsal in `rehearsals[]` against its flip ID, record ID and before-values, and read back that nothing remains. A required flip with no result is `unverified`.

Record `story.beats[].verification`: `verified` when every item is `applied` or `already_satisfied` with no visual QA pending, every claim passed and every flip passed; `visual_qa` when the only gaps are visual QA or a flip that can't be rehearsed safely; `unverified` when evidence is missing; `failed` when a claim or rehearsal failed. A `failed` or `unverified` beat makes Overall `UNRESOLVED`; a `visual_qa` beat makes it `FINISHED_WITH_EXCEPTIONS`. The Demo Story labels each beat accordingly.

## Records at scale and resume
Keep one consolidated change log per task, with per-type sections only under the template's conditions, not final dispositions (Agent Not Live whenever an attempted agent isn't live; Existing Agent Before-State for a modified incumbent; Execution Order Check whenever a flow is attempted). Map decisions: new-versus-existing forks, cuts, Docs-driven changes, presales-lens choices. The block is the state: on resume, settle any non-terminal job first, then run `plan` for the unsettled items.
