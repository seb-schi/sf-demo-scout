# Finish this task's history

Read after final disposition or resume. Run `python3 [PLUGIN_ROOT_ABS]/scripts/scout_history.py` with quoted absolute paths. Only `resolve` edits; no queries.

## Consolidate and check

Consolidate above final `## Checkpoints`; preserve checkpoints, before-state and evidence. Follow `${CLAUDE_PLUGIN_ROOT}/prompts/building/change-log-template.md`'s whole SE-facing shape: header, Achieved State, What Was Deployed, What Was Skipped, Completion Reconciliation (four subsections), Companion Permission Set, applicable before-state/type/script sections, Issues Encountered, Docs Consulted, SE Must Do Next, How to Verify and Open Questions. Replace Spec with `Task record: [task filename]`; omit Spec SHA-256 and Build ID. `Audit used:` names the full audit or `scoped (task record)`. Include every Docs URL/question/verdict, grouped by item. Give seed pilot, refresh and reset commands in How to Verify and Script Deliverables.

Run `render --task [T]`. Use `Grounding:` and reconciliation/skipped sections; counts are items with each source, so one item can count under several sources. Keep evidence after each `- I<n>`:

- `applied` → Verified — Applied This Build; visual QA instead → Accounted-for Exceptions as AWAITING_QA, with metadata evidence.
- `already_satisfied` → Verified — Already Satisfied Before This Build.
- `omitted` → What Was Skipped and Accounted-for Exceptions as SKIPPED, with decision source.
- `failed`, `blocked`, `unverified` → Unresolved Work as FAILED, BLOCKED, INCOMPLETE (unverified).

Overall: any unresolved item → UNRESOLVED; otherwise any exception → FINISHED_WITH_EXCEPTIONS; otherwise FULLY_VERIFIED. Visual QA never earns FULLY_VERIFIED.

Run `resolve --task [T]`, then `check --task [T]`. Applied/failed/unverified require attempts whose last outcome matches; `already_satisfied`/`blocked` allow attempts only when every outcome matches; omitted requires none. Record every checkpoint as an attempt. Resolve touches only owned attempt IDs in the named log whose header names T. Each settled attempt's heading comes from its own `- **Outcome: <disposition>.** <evidence>` line, never the item's eventual disposition. Missing/conflicting outcomes stay PENDING and are findings. Resolve replaces whole `outcome:` values; settle other pending fields yourself. Write business values containing the word pending in backticks. Only this task’s recorded report markers exempt delta JSON before/after strings; elsewhere, pending is a finding. Never fabricate evidence.

Exit 0 permits handover; warnings disclose Docs-unavailable grounding or SE sections causing map excess. Exit 2 means fix usage; exit 3 lists findings: fix and recheck up to twice. If still failing, or exit 4 (couldn't read), record why history is incomplete in the task and make the handover's first line **History incomplete: [reason]**. Never present incomplete history as complete.

## The map and one history question

Propose material decisions: amendments, confirmations, new/existing forks, gated choices, cuts as `[REJECTED]`, items kept without a moment, app and language choices. Change the arc only if flow changed. With neither change, leave the map untouched: “map unchanged”.

Create a map only when this task established a story: open-ended, or a brief/structured input naming audience and moment. In folders without a map and without a story, propose no entries and say “the map starts once there's a story.” Do not backfill a legacy demo without a map.

Read `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/demo-architecture-template.md` §"This doc is a MAP, not a LOG — size discipline is the whole point", §"Template", §"Create Rules (Stage 6 — new / reuse-org sessions)", §"Reconcile Rules (Stage 3i — iteration sessions)" (Case A steps 1, 2, 4, 6 only), and §"Auto-draft decision entries (Stage 6, all authoring paths — SE-gated)". Use `reconcile-plan --folder [F]`: newest five newer logs in full, older ones by last section. No fresh audit or separate stop.

After the outcome and Demo Story, show the log path, proposed entries and condensed arc (beats only), then proposed lessons and one **yes / edit / skip** question. Save proposed entries in the block before asking. Carry confirmation answers forward; write re-offers with the history block. Store them in this task’s `history.reoffers`: `[{"task":"prior filename","answer":"confirmed|edited|skipped"}]`. `pending` suppresses those answered proposals in this folder without editing older tasks. No answer means write nothing; decisions remain `proposed`, for `pending` to re-offer next run.

On yes/edit, write only the confirmed entries and arc; decisions become `confirmed`/`edited`. On skip, write the arc and stamps without new entries; record `skipped`. Stamp `Last reconciled: YYYY-MM-DD HHmm by /scout` and `Reconciled through: [this log]`. Set architecture `created`/`reconciled` and `history.arc_changed` (boolean), keeping beats at most 320 characters each and decisions in the dated template form, one line at most 320 characters. A created map is entirely this task’s; in a reconcile, every line citing this log is this task’s, including nested sections. Compact template sections only, keeping rejected/superseded decisions. Aim for 350 lines and 3,750 words; disclose remaining excess. Update the block, rerun `check`, then send one truthful receipt line.

## Lessons need the SE's yes

For a repeatable trap, propose 1–3 lessons in the history block using `${CLAUDE_PLUGIN_ROOT}/prompts/lessons-maintenance.md` §"Propose Lessons (building)": yes, edit or skip. Write only on yes or edit, following §"Append Format" and §"Routing — which topic file"; on excess length, run §"Per-Topic Review (replaces the old global 25-line trim)" with its separate approval for pruning. If absent, that yes also covers `${CLAUDE_PLUGIN_ROOT}/prompts/lessons-bootstrap.md` §"Step 1: Ensure the lessons directory + INDEX exist (idempotent)". Record lessons as `proposed`, `written` or `skipped`. Skip Slack Upstream and Legacy Drain offers.

## Precedence

- This per-task log rule overrides `${CLAUDE_PLUGIN_ROOT}/prompts/building/component-rollback.md`'s append-to-existing-log instruction.
- The outcome heading rule overrides that file's heading rule; only unresolved checkpoints keep PENDING.
- `/scout` is the architecture template's second author despite “Authored by sparring only.”
- Every SE-authored/non-template section stays byte-identical, in place; this overrides deleting legacy banners. Never move, prune, rename, re-index or rewrite other files.
