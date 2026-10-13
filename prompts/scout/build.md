# /scout build: complex plans

Read this before the first write when the plan has several items, or any gated or Docs-gated item; `commands/scout.md` still governs targeting, confirmation, dispositions and history. Such a task needs `story` with beats, even on the complete-brief path.

## The plan, in the proposal
Show beats, then items, then write order; each item shows type, category, `depends_on` and the claims it backs. For each beat, list the UI surfaces it touches (form, list view, record page, app navigation, report, agent); each is an item or `already_satisfied` with its query, so a new object whose beat shows its form needs its layout. Confirm each gated category once, inside the bundled confirmation. Classify Docs-gated items first: UI-only goes on the SE's checklist with a fetched citation naming the exact operation; authorable with no build-time signal is flagged for visual QA up front; fuzzy matching rules are authorable. No envelope, item cap or one-spec rule applies; platform facts stay Docs-gated dispositions. Tell the SE the items, gated categories and a rough duration; then report one line per item, never waiting for acknowledgement. Record each live flip's expected ID in the block before executing it.

## Author in parallel, write in series
Run `python3 [PLUGIN_ROOT_ABS]/scripts/scout_history.py plan --task [T]`: it prints the write order (a topological order of `depends_on`; a cycle exits 3, so fix the plan with the SE) and the authoring layers.

Dispatch at most four authoring workers at once, one item each, each in a fresh `prepare-workspace` project, with `commands/scout.md`'s worker rules, the item's criterion, its contract row and K7's grounding duty. Workers may make read-only org calls through the bound username after `check`, but never write to the org, run pilots or runtime tests, or open mutation-bearing previews. They return a delta against their baseline, grounding entries, issues and "authored; live validation pending". Draft a dependent from its predecessor's authored interface; reconcile it with the live schema once the predecessor lands, or defer it.

Only the orchestrator writes to the org, the task record and the log. For each item, in write order:
1. Re-read the amendment log; an item withdrawn before its write becomes `omitted`.
2. Proceed only when every prerequisite is `applied` or `already_satisfied`. Otherwise the item is `blocked`, naming the prerequisite, unless an approved amendment replaces the dependency.
3. Run `check`, also before any retry.
4. Re-retrieve every touched component and apply the delta to current source, merging shared-file types such as SharingRules and permission sets with incumbents; keep the draft.
5. Stage the result in a fresh writer project and record the attempt in flight.
6. Execute with the type's own mechanism: Metadata API deploys polled with `sf project deploy report --job-id`, synchronous data writes or Bulk jobs, Email-to-Case's two-phase apply script, Agentforce's publish lifecycle. Pilots and runtime tests run here.
7. While any job isn't terminal, the write slot stays occupied: no org mutation of any kind. A timed-out job stays `unverified` with its job ID and launch receipt; recover a lost ID as `${CLAUDE_PLUGIN_ROOT}/prompts/building/scout-2-repair.md` §"Scout 2.0 existing-report repair" step 7 does. A read-back never settles a job that may still land.
8. Read back yourself, then record the attempt's outcome and the item's disposition.

Write the companion permission set after the items it grants settle, extending it as later ones settle; omit failed items' grants and name them in the log. A Service Agent's backing-action grants precede its validation probe. A failed, blocked or unverified item blocks its dependents; independent items and beats carry on. Never retry automatically: a retry is a new attempt after K7's error rule, recording the covering lesson or the Docs search of the verbatim error.

## Per-type contracts
Take each source's technical rules; ignore its envelopes, ledgers, output formats, phase topology and model choices.

| Type | Procedure | Completion signal |
|---|---|---|
| Object, field, record type | `platform-custom-object-generate`, `platform-custom-field-generate`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Picklist Value Additions" | read-back |
| Permission set | `platform-permission-set-generate`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Companion Permission Set — MANDATORY" | grants and assignment |
| App, tab | Docs: Metadata API `CustomApplication`, `CustomTab` | read-back |
| Queue, business process, path | `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Queue Rules", §"Business Process Rules", §"Path Rules" | read-back |
| Layout | `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Page Layout Rules" | placement read-back |
| Record page field section | `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Lightning Record Page — Field Section Add Rules" | read-back, then visual QA |
| Validation rule | `platform-validation-rule-generate`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Validation Rule Rules" | read-back |
| List view | `platform-list-view-generate`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"List View Rules" | read-back and results |
| Sharing rules | `platform-sharing-rules-generate`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Sharing Rule Rules" | merged read-back |
| Report, report type | `platform-report-generate`, `platform-custom-report-type-generate`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Report Rules", §"Custom Report Type Rules" | read-back and a run |
| Existing report filter | `${CLAUDE_PLUGIN_ROOT}/prompts/building/scout-2-repair.md` §"Scout 2.0 existing-report repair" | the helper's read-back |
| Custom setting, metadata type | `platform-custom-setting-generate`, `platform-custom-metadata-type-generate`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Custom Setting Rules", §"Custom Metadata Type Rules" | read-back |
| Data | `platform-data-manage`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Salesforce Data Seeding Quirks" | each claim's read-back |
| Email-to-Case | `service-email-to-case-configure`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Email-to-Case Rules" | the script's verification |
| Flow | `sf-flow`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase2.md` §"Flow Rules"; `${CLAUDE_PLUGIN_ROOT}/prompts/building/sub-agent-validation.md` §"Phase-2 Flow Evidence" | exact-version tests and activation |
| Apex | `platform-apex-generate`, `platform-apex-test-generate`, `platform-apex-test-run`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase2.md` §"Apex Rules" | passing tests, bounded fix loop |
| LWC | `experience-lwc-generate`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase2.md` §"LWC Rules" | read-back, then visual QA |
| Agentforce | `agentforce-generate`, `agentforce-test`; `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase3.md` §"New Agent (Agent Script path)", §"Modify Existing Agent (version-safe path)", §"Smoke Test + Validation Gate (after activate — both paths)"; `${CLAUDE_PLUGIN_ROOT}/prompts/building/agentforce-validation-gate.md` §"Validation Gate — REQUIRED before reporting an agent working" | smoke test and gate; preview gaps to visual QA |
| Anything else | `${CLAUDE_PLUGIN_ROOT}/CLAUDE.md` §"Docs-Gated — attempt everything metadata-authorable (there is no capability ceiling)" | its Docs-cited disposition |

A Flow item records its frozen validation mode and every required test. An Agentforce item references the evaluator's evidence file, with one obligation per required action and assertion, each with its own inputs.

## Verify each beat
Run every claim's read-back yourself; record `claims[].result` as `passed`, `failed` or `dropped` (never drop a required proof-moment claim). Match each on-screen noun to the record's shape (subtype, record type, the component the beat names): a "logged call" is a Task with `TaskSubtype = Call`.

Rehearse a live flip only in anonymous Apex inside an always-rolled-back savepoint, after a passing `check`, when Docs show every effect is undone. A flip that publishes a Publish Immediately event, makes a callout or starts async work goes to visual QA. Record each rehearsal in `rehearsals[]` against its flip ID, and read back that nothing remains. A required flip with no result is `unverified`. Agents use `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase3.md` §"Smoke Test + Validation Gate (after activate — both paths)".

Record `story.beats[].verification`: `verified` when every item is `applied` or `already_satisfied` with no visual QA pending, every claim passed and every flip passed; `visual_qa` when the only gaps are visual QA or a flip that can't be rehearsed safely; `unverified` when evidence is missing; `failed` when a claim or rehearsal failed. A `failed` or `unverified` beat makes Overall `UNRESOLVED`; a `visual_qa` beat makes it `FINISHED_WITH_EXCEPTIONS`. The Demo Story labels each beat accordingly.

## Records at scale and resume
Keep one consolidated change log per task, with per-type sections only under the template's conditions (Agent Not Live only when an agent isn't live; Execution Order Check whenever a flow deploys). Map decisions come from new-versus-existing forks, cuts, Docs-driven changes and K8 choices; a complex scenario usually rewrites the arc. The block is the state: on resume, settle any non-terminal job first, then run `plan` for the unsettled items.
