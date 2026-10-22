# Scout: inspection, build and handover

`skills/scout/SKILL.md` sends you here once the org is bound and the scope is confirmed. Its rules on targeting, confirmation and the CLI still apply.

## Inspection and durable task

First follow `${CLAUDE_PLUGIN_ROOT}/prompts/building/official-skill-overrides.md` §"Readiness", before inspection, delegation, proposals or writes. Use `${CLAUDE_PLUGIN_ROOT}/skills/demo-org-audit/SKILL.md` for scoped inspection; read only needed sections under `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/audit/`, including LRP composition when relevant. A full audit at most seven days old may inform the plan; retrieve every touched component again before writing. Keep scoped findings in the task record, never in `audit-*.md`; a full audit runs only on request. Run `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/platform-research.md` §"Step 0 — Object Capability Pre-Flight" for touched managed/industry objects and §"Step 0b — Docs Follow-Up for Restricted Objects" for restrictions. In folders with history, compare the request with the map's `[REJECTED]` and superseded entries; raise any match in the bundled confirmation. Use `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/iteration.md` §"Delta Conflict Check", including §"Agent source evidence gate"; fix symptoms use §"Symptom Follow-up (fix intent only)".

Read `demo-architecture.md` first; run `python3 [PLUGIN_ROOT_ABS]/scripts/scout_history.py reconcile-plan --folder [ORG_FOLDER]` and fold in the listed logs as leads. Read the newest `demo-spec-*.md` only when continuing work. Re-offer only the chosen folder's proposals. Answer re-offers in confirmation; record the answer in the new task, write with the history block.

Run `python3 [PLUGIN_ROOT_ABS]/scripts/scout_history.py pending --orgs-dir [WORKSPACE]/orgs --org-id [BOUND_ORG_ID] --username [BOUND_USERNAME]`. Scan records across `orgs/*/` by the bound org ID, including prior folders. An `unresolved` checkpoint blocks dependent items; read every `unclear` checkpoint and record your interpretation. Settle every `open_jobs` entry `pending` reports with a status read before writing, recorded per `${CLAUDE_PLUGIN_ROOT}/prompts/scout/reconcile.md`, or stop and tell the builder. Legacy checkpoints with outcome mentions are unclear; without them, unresolved. On nonzero exit from `pending` or `reconcile-plan`, read the history yourself and record that before any dependent write. Keep recovery-preservation and cleanup-withheld blockers. Preserve other tasks' records without resolving, cleaning or relabelling them.

On a joined string telephone, follow `${CLAUDE_PLUGIN_ROOT}/prompts/scout/string-telephone.md` §"Before the first write: the brief" now, and its §"Claiming" at confirmation.

Stamp records from `date`, never an estimate. Before the first write, create `[ORG_FOLDER]/task-[YYYY-MM-DD]-[HHmm]-[slug].md` with a unique name. Keep request verbatim, bound selector/alias/username/org ID, categorized items, criteria, inspection findings, timestamped amendments and dispositions/evidence. Record in-flight writes before dispatch, including every checkpoint marker and attempt ID in the task record. Withdrawn unattempted items become `omitted`; withdrawal after launch stops further work but still needs read-back and an honest outcome for what landed. A new item gets its own inspection, criterion and authorization check. Preserve earlier outcomes when amending.

Include exactly one fenced `scout-items` JSON block (schema 1); update it with every disposition. Use this shape; replace placeholders, keep arrays even when empty:

```scout-items
{"schema":1,"path":"complete-brief","change_log":"changes-YYYY-MM-DD-HHmm-customer.md",
 "story":null,
 "items":[{"id":"I1","what":"","type":"CustomField","beat":"-","category":"autonomous",
 "criterion":"","readback":"","proves":"-","depends_on":[],"components":[],"attempts":[],
 "grounding":[{"assumption":"","source":"skill","ref":"","verdict":""}],
 "disposition":null,"evidence":"","visual_qa":false,"reason":"","seed_asset":""}],
 "history":{"decisions":"none","proposed_entries":[],"lessons":"none","architecture":"unchanged"}}
```

Every item needs type, depends_on, grounding and proves; components records known identities without enabling parallel writes. Sources: `docs|skill|org|lesson|ungrounded`; Docs needs URL/verdict. Ungrounded uses empty ref and reason in verdict; `Docs unavailable` warns instead of failing the Docs floor. Failed reason: `State left: …; rollback: …`.

Create the block’s new per-task change log before the first checkpoint, with `Task record: [task filename]` in its header. Every owned checkpoint, including seeds, uses `### PENDING — component repair · attempt <ID> · <YYYY-MM-DD HH:MM>` under final `## Checkpoints`. Add `- why: <criterion>`, `- via: <skill or command>` and `- **Outcome: <disposition>.** <evidence>` per attempt, plus `- job:<ID>;status:<terminal>;launched:<YYYY-MM-DDTHH:MM:SS>;settled:<…>` per job (a non-terminal status in backticks). Resolved headings use that attempt’s outcome; missing/conflicting outcomes stay PENDING. Never copy an item's final outcome onto earlier attempts.

To resume a record, check its recorded target first. Continue items without dispositions. For an interrupted/in-flight write or an `unverified` item, reconcile only the checkpoint markers and attempt IDs recorded in this task, then read back before deciding its outcome; do not replay it. Terminal items need a new amendment or task to change scope.

## Ground design and claims

Every item records grounding: assumption, source and reference. `skill` means only what the skill's NO list makes authoritative; `org` means observed state, with its query. Gated/Docs-gated types (flows, Apex, LWC, Agentforce, Email-to-Case, dashboards and unknown types) require Docs. Claim mechanisms require Docs unless plain field values. Read `${CLAUDE_PLUGIN_ROOT}/skills/demo-docs-consultation/SKILL.md` §"When to Consult — YES", §"When to Consult — NO", §"How to Cite", §"Degraded Mode"; this floor overrides silent degradation. Fetch before deciding; snippets aren't evidence. Before proposals: industry model when the org has one or the request names one; gated approaches, release availability and capability classifications. Name design-changing Docs findings in the proposal. While building: consult Docs before first writes for new metadata types and ungrounded assumptions; Agentforce always. After an error no loaded lesson covers, search the verbatim error before retry or `failed`. Workers return grounding; fetch disposition-deciding pages yourself. If unavailable, ask once on open-ended work whether to proceed ungrounded; record `Docs unavailable` entries and handover risks, never fake URLs.

Before seeding, describe every object using `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/data-shape.md` §"Describe-before-spec — Data Seeding objects only" (required fields, picklists, record-type DeveloperNames); for claim-dependent existing data, §"Procedure per object". Capture `errorCode` on failure. Use dates relative to seed day; state the validity window. Include tension: at-risk/stale/overdue records. Dress each hero record with contacts and relative-dated activities. Stage live flips in before-state with a reset. Deliver an idempotent, re-runnable script that never deletes, with `--pilot-only` against the bound org, following `${CLAUDE_PLUGIN_ROOT}/skills/demo-deployment-rules/SKILL.md` §"Script Deliverable Rules (cross-phase)". Every on-screen claim is an acceptance criterion with an exact `readback` query: verify it yourself, including the proof moment. Drop unbacked claims from Demo Story. A missed post-write claim is `failed`, naming state left and rollback.

## Execution and delegation

Work solo by default. Run items in `depends_on` order. Follow steps 2–7 of `${CLAUDE_PLUGIN_ROOT}/prompts/building/direct-repair.md`; this task replaces step 1. Read `${CLAUDE_PLUGIN_ROOT}/prompts/operation-safety.md` and create a fresh writer-owned `prepare-workspace` project with `WRITER=scout` for each item. Retain its ownership receipt, source and original rollback evidence. Read other customers' folders only for the history and conflict checks named here; copy their source, records, seed data or wording only on the builder's yes to an offer naming its folder, then scan copies for that customer's content.

Legacy prompts supply technical procedures: category gates, `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` §"Companion Permission Set — MANDATORY", append-only record page edits and incumbent preservation. Ignore their envelopes, placeholders, report formats, acknowledgements, phase topology and model choices. Keep skill, rollback, targeted read-back, data-repair and log requirements; no new write capability.

Pass this task’s log explicitly as `--change-log` to the report helper. Wrap its attempt in the owned checkpoint form, keeping the helper’s marked receipt block fenced and its evidence unchanged. Existing-report filter changes use `${CLAUDE_PLUGIN_ROOT}/prompts/building/scout-2-repair.md` with the bound username as selector. Retain this route’s original binding check and the helper’s receipts/operator-evidence requirements.

Delegate read-only research/inspection when useful. With three or more items or any gated or Docs-gated item, read `${CLAUDE_PLUGIN_ROOT}/prompts/scout/build.md` before proposing or writing; authoring may run in parallel, org writes stay serial. Give each worker its own prepared project, resolved absolute root, active host, bound selector/username/org ID with its class and write status, exact approved scope and criteria, relevant technical rules, the three qualified confirmation bullets in `skills/scout/SKILL.md`, and this unconditional CLI-only rule copied verbatim into every worker brief: “Never call MCP org tools, even when the bound org is the default. Wherever a file says MCP, the active or default org, `sf config get target-org`, or to omit `--target-org`, use `sf … --target-org [BOUND_USERNAME]`.” Every worker must check identity before writes/read-back and retain pending evidence on interruption or refusal.

On Claude, every Agent call—research, inspection or write—passes `model` set to the alias of the orchestrator's own model family; if that family is unknown, omit the argument. An explicit `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` wins.

Every disposition rests on a read-back you ran yourself, after a passing `check`. Audits and worker reports are leads, not evidence. Read back every delegated write yourself after checking the binding, and establish `already_satisfied` from your own fresh pre-write read-back. Missing read-back means `blocked` before attempt, `unverified` after; never infer completion. Inspect landed state after a timeout or malformed worker report before any retry. Preserve policy refusals and return the blocker rather than changing tools or command spelling.

## Verification and handover

Assign exactly one disposition per item:

Disposition | Meaning
---|---
`applied` | Written in this task, and post-write read-back meets the criterion.
`already_satisfied` | Pre-write read-back met the criterion; nothing was written.
`failed` | Attempted and rejected, or read-back misses the criterion; name remaining state and whether rollback occurred.
`blocked` | Not attempted; name the gate or precondition.
`unverified` | A write happened or may have happened, and no read-back settles it.
`omitted` | Deliberately not done: withdrawn, out of scope, or docs-confirmed UI-only with citation and manual-checklist entry.

Map report-repair `not_applied` to `failed`, and both `unverified` and `released_unverified` to `unverified`; other outcomes retain their names. Green deploy alone is not read-back. For authorable no-signal artifacts, `applied` covers metadata read-back only: list them under “needs visual QA”, never call them working. A new record page stays manual; page edits write nothing ungrounded, and a second rejection stops the edit.

After the last disposition, read `${CLAUDE_PLUGIN_ROOT}/prompts/scout/history.md` unless this session read it since its last compaction. Consolidate this task’s log using `render`, run `resolve`, then `check`. Send the handover only after exit 0, or start it with “History incomplete: [reason]” when history.md's fix rounds end without a pass; history.md gives the handover's form and the rounds.
