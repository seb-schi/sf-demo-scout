# Scout 2.0 existing-report repair

Opt-in preview; shared helper `[PLUGIN_ROOT]/scripts/scout-repair.py`. It uses
Python 3.9+ and its standard library, plus an existing authenticated Salesforce CLI.
No package installation is needed. Missing authentication, CLI or permission is a
reported limitation; never change managed routing or switch tools to evade refusal.
Read-only CLI integration has been exercised; live repair/restore is not validated.

1. Resolve the user's org selector and existing customer directory in a verified
   Scout workspace. Review affected unresolved tasks/change logs and relevant report
   rules (`platform-report-generate`, `building/vendor-compatibility.md`). Resolve
   affected legacy PENDING work before starting another mutation. Read the original
   request clause by clause; a metadata result cannot discharge requested UI/runtime
   behavior. Coverage/history notes are optional, not a substitute for this review.
2. This route supports one existing report in one ordinary top-level folder, one
   unique top-level criterion selected by column/operator, and a scalar value change.
   Empty values are supported. API names must start with a letter and contain only
   letters, digits and underscores. Nested folders, `unfiled$public`, other names,
   joined reports, multiple matching predicates and filter-logic edits are outside
   this preview. It never creates a report/folder or changes sharing/defaults.
3. Save the exact instruction to `[ABS_CUSTOMER]/repair-request-[UNIQUE].md` using
   the canonical absolute customer path, not `/tmp` or a symlink. Supply its source
   reference. Select the existing conventional change log with `--change-log` when
   known; otherwise the helper uses the latest `changes-*.md`, or creates the standard
   local-time `changes-[YYYY-MM-DD]-[HHmm]-[CUSTOMER].md` when none exists.
4. Run each helper operation with a **600000 ms Bash timeout** and shell-safe
   argument arrays or properly quoted literals. Do not wrap a write in an automatic
   retry. If the host cannot grant that timeout, report the execution limitation.

   ```text
   python3 [PLUGIN_ROOT]/scripts/scout-repair.py inspect-report
     --workspace-root [ABS_WORKSPACE] --customer-dir [ABS_CUSTOMER]
     --target-org [SELECTOR] --report [Folder/Report]
     --column [EXISTING_COLUMN] --operator [EXISTING_OPERATOR]
     --before [EXPECTED_OLD_VALUE] --after [REQUESTED_VALUE]
     --request-file [ABS_REQUEST] --request-reference [SOURCE_REFERENCE]
   ```

   Inspection binds the alias once to username plus authenticated org ID, retrieves
   into a fresh owned project, checks actual files and seals the contract. Use the
   returned task path/digest. Failed retrieval or absent files mean unknown state.
5. `apply-report --task-dir [TASK] --contract-digest [DIGEST]` rereads report/folder
   state once, preserves the original, changes only the selected value's bytes,
   rechecks authenticated identity and launches one report deployment. Every org
   operation uses the bound username. Alias/default changes do not redirect it.
   `already_satisfied` makes no write. A launch is still unverified.
6. `verify-report` or `reconcile-report` with the same task/digest reads the tracked
   job and current source. Mutation, acceptance and recovery are separate fields.
   A terminal successful exact-member receipt plus matching metadata permits
   `applied`. Missing evidence or normalization/concurrent drift stays `unverified`.
   A failed job, or a proven preflight rejection, plus unchanged baseline permits
   `not_applied` and releases the local component guard. Generic errors alone never
   prove that a write did not launch. Comments/formatting are ignored in metadata
   acceptance; candidate generation preserves every byte outside the chosen value.
7. After timeout/interruption, reconcile before doing anything else. The CLI writes
   its launch response directly to `deploy-start.json`; reconciliation can recover
   its job ID even when the caller never recorded it. If no ID survived, leave the
   attempt unknown until an operator identifies the exact job from deployment
   history. Record that attribution with `reconcile-report --job-id [ID]
   --job-evidence [ABS_EVIDENCE_FILE]` and the same task/digest. The evidence must
   establish the link to this attempt; the helper checks job time, membership,
   terminal result and current state, but cannot prove a human attribution. Never
   invent an ID, select a recent unrelated job, edit result.json or delete a lock
   pointer to resume. Poll nonterminal jobs with bounded waits; never redeploy.
   If deployment history shows no job for this attempt after `launch.started_at`,
   or the read-back difference has been reviewed, the operator may release a still
   unverified attempt with `reconcile-report --task-dir [TASK]
   --contract-digest [DIGEST] --release-evidence [ABS_EVIDENCE_FILE]`. Save that
   review in a non-empty bounded regular file. The helper reconciles first, then
   copies the evidence once to `release-evidence.md` and releases the component
   guard only if the result is still unverified. Changed evidence is rejected.
   The result is `released_unverified`, reported as unverified, never as applied
   or not applied; retain its original, receipts and read-back. A new task may
   now inspect the current state. Other outcomes have nothing to release.
   Resolved tasks refuse further verify/reconcile; start a new task instead.
8. Report the result, task/log paths and recovery status. The helper updates one
   marked checkpoint in the conventional log, including source, preservation,
   receipt and read-back pointers. A pending operation remains PENDING. Preserve
   all scratch and evidence; log failure blocks launch and reports the actual path.

`status --task-dir [TASK]` is local and needs no CLI. Scope changes use a new task
with `--previous-task [OLD_TASK]`; finish/reconcile the old operation first. There
is no amendment engine. Originals belong to their task and remain available across
linked tasks. Earlier schema-1 preview tasks need manual evidence reconciliation;
never relabel their edited source as an original.

Recovery remains deliberate: verify the pinned component-preedit artifact, confirm
current target/state and exact scope, then use the existing component-rollback
procedure to stage only the report in a new owned project. A successful mutation
with `recovery=blocked` does not establish safe restore. No automatic cleanup or
rollback occurs. Local locks coordinate this workspace only; prewrite reads are
not a Salesforce compare-and-swap guarantee.
