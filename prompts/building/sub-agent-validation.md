# Sub-Agent Output Validation

Loaded on demand by scout-building.md Step 5. The worker report and independent
orchestrator observations are separate inputs to the read-only completion helper.
Neither one can change the frozen expected-work ledger.

## Procedure

1. Preserve the raw worker response. Extract its one fenced JSON block and save the
   parsed object as the worker-result JSON. If parsing fails, do not synthesize a
   successful envelope: treat the worker report as missing and retain the parse
   error for the change log. Required phase detail keys remain:
   - Phase 1: `deployed`, `skipped`, `permission_set`, `data_seeded`,
     `script_deliverables`, `discovery_notes`, `docs_consulted`, `issues`.
   - Phase 2: `deployed`, `skipped`, `rollback_commands`, `discovery_notes`,
     `docs_consulted`, `issues`.
   - Phase 3: `deployed`, `smoke_test`, `actions_unverified_in_preview`, `skipped`,
     `rollback_commands`, `discovery_notes`, `docs_consulted`, `issues`.
   All phases also require `schema_version`, `build_id`, `spec_sha256`, `phase`, and
   `completion`. A missing/malformed report remains INCOMPLETE even if probes find
   exact state. Request a corrected report; do not redeploy or republish to fix JSON.

2. Collect current independent observations for every non-authorized-skipped ledger
   item. Use targeted metadata read-back, describe, SOQL, tests, or saved tool output
   that checks the requested properties. Presence-only queries and a deployment
   receipt alone are diagnostic, not verification. Save the actual tool result in
   the build record and reference it from `source`/`details`.

3. Attribute state honestly:
   - `applied` requires both a current change source (`change_source`: deployment
     receipt or saved before/after evidence) and targeted current-state evidence.
   - `already_satisfied` requires exact targeted current state plus
     `baseline_source` that proves the same state before dispatch. A post-read-back
     alone cannot establish that the build did not make the change.
   - Failed operations remain FAILED; prerequisites/refusals/manual obligations are
     BLOCKED; deployed items with required test/visual/runtime work outstanding are
     AWAITING_QA. None of these are success or an authorized skip.

   Derive every selected Phase 1 metadata target (including Layout, SharingRules,
   FlexiPage and Report/ReportType), plus Flow, Apex class/trigger, and LWC
   mutation targets from the frozen ledger plus selected approved phase work, even when
   a detailed worker row is absent or malformed. Exclude a frozen authorized skip when
   dispatch/tool evidence proves no mutation was attempted; it requires no worker row,
   checkpoint, or receipt. Any worker, tool, or current evidence of unexpected mutation
   keeps it as an out-of-scope preservation failure. An
   `already_satisfied` item is receipt-exempt only when saved independent baseline and
   current evidence prove the exact requested state and that no mutation was attempted.
   A worker label alone is insufficient, and any attempted mutation removes the
   exemption. For each remaining target, independently check `preedit_snapshot` and
   require the saved baseline classification source. An `existing` target with an
   attempted mutation requires `status: verified`, the first
   immutable artifact/source/member paths, and a successful `ASSET_HELPER verify`
   result of kind `component-preedit` beneath this org's rollback directory. `new`
   requires positive saved absence evidence and `not_needed`; `unknown` is BLOCKED.
   Never recreate a missing receipt from current or edited source. For a Flow, also
   require the original active/inactive evidence; active needs exact ID/version and
   inactive must remain distinct from unknown. Preservation failure overrides an
   otherwise successful detailed row. In the existing independent observation, set
   `result` to `unavailable`, put the preservation failure and source in `details`,
   and rerun the reconciler. Keep the preservation issue/checkpoint BLOCKED while
   retaining the reconciler's true unresolved result (normally INCOMPLETE for
   unavailable evidence); do not invent a state mismatch or replace it with prose.

4. **Probe every non-authorized-skipped seed ledger item**, even when worker JSON is
   absent/malformed or `data_seeded[]` is absent/empty:
   - CREATE: query only the ledger's exact stable keys, record `matched_count`, and
     check the requested values. Require `matched_count >= count`; paired rows may
     make the actual count larger. Observed zero or short results are FAILED; an
     unavailable probe is INCOMPLETE. Never accept a worker count as evidence.
   - UPDATE: query every named stable target and requested field. Literal values
     must equal the spec exactly. Only fields explicitly marked `⚠️ SE refines
     prose` use a nonblank check. Ignore row count for acceptance.
   - Record a calibration directive, its reference query result, computed value,
     and fallback honestly. Never infer an operation/count/target/value or widen a
     stable key. An ambiguous old/hand-edited spec leaves that seed item BLOCKED for
     clarification.

5. Save one evidence JSON object. First run the helper with just `--spec` and
   `--ledger` if you need its canonical `ledger_sha256`. The evidence shape is:

   ```json
   {
     "schema_version": 1,
     "build_id": "same build id",
     "spec_sha256": "same spec digest",
     "ledger_sha256": "canonical digest reported by the helper",
     "phase": 1,
     "orchestrator_provenance": "saved build log / tool-result index",
     "observations": [
       {
         "item_id": "p1.field.case-risk",
         "verification": "targeted_state|presence|deployment_receipt|seed_probe",
         "result": "match|mismatch|unavailable",
         "attribution": "applied|already_satisfied|unknown",
         "change_source": "required for applied",
         "baseline_source": "required for already_satisfied",
         "source": "saved tool result reference",
         "details": "properties checked and observed values",
         "actual_state": {"same property keys as ledger expected_state": "typed observed value"}
       }
     ]
   }
   ```

   A CREATE `seed_probe` contains `operation`, `object`, the exact `stable_keys` and
   `required_values`, `matched_count`, and `values_match`. An UPDATE `seed_probe`
   contains `operation`, `object`, and `targets[]`, each with the exact `stable_key`
   and an `actual_values` object. When the ledger item has settled calibration, the
   probe also carries `calibration_source` equal to the ledger's saved
   `acceptance.calibration.reference_source`.

6. Run the executable reconciler (omit `--worker-result` or `--evidence` only when
   that input truly does not exist):

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build-completion.py" \
     --spec "[actual approved spec path]" \
     --ledger "[frozen phase ledger JSON path]" \
     --worker-result "[parsed worker JSON path]" \
     --evidence "[orchestrator evidence JSON path]"
   ```

   The helper is stdlib/read-only: it makes no Salesforce calls and no deployment
   decisions. It checks the actual spec digest and exact source anchors, all
   build/spec/phase/ledger identities, required phase-detail key types,
   duplicate/missing/unexpected IDs, contradictions between completion rows and
   detailed deploy/permission/Draft/recovery outcomes, worker and evidence
   semantics, seed report pairing, and independent seed acceptance.

7. Preserve the helper's full item array. `FULLY_VERIFIED` means every item is
   VERIFIED. `FINISHED_WITH_EXCEPTIONS` contains only accounted-for SKIPPED and/or
   AWAITING_QA alongside verified work; never call it blanket success. `UNRESOLVED`
   contains FAILED, BLOCKED, or INCOMPLETE work. Every disposition has
   `automatic_retry: false`: select the next action item by item. A malformed report
   gets a corrected-envelope request; a positive probe prevents blind redeploy or
   reseed; a true defect needs concrete new fix evidence before any retry; an
   authorized skip is never auto-retried.

The helper verifies anchors and reconciliation, not semantic exhaustiveness or live
Salesforce truth. The orchestrator remains responsible for reading every populated
spec section and for grounding each evidence assertion in saved tool output.

## Phase-2 Flow Evidence

Every Flow ledger item carries authoritative `acceptance.flow_validation` with an
exact Flow API name, an immutable `flow_test_required|unsupported` mode, and either
the complete `required_tests_all_must_pass` list (or explicit legacy singleton)
or a concrete unsupported reason. Collect this evidence even
when the worker omits or renames its deployed Flow row. Missing independent Flow
evidence leaves only that item INCOMPLETE; malformed identities or contradictions
invalidate the report.

For an applied Flow, positively attribute the new draft before testing it: save the
pre-deploy Flow version set, the one-Flow deployment receipt and returned file
identity, and the post-deploy set. Accept only one new matching Draft row, then
preserve its exact Flow ID and positive version. A latest-row query alone is not
attribution. For `already_satisfied`, save the exact pre-dispatch active Flow ID and
version plus a current read-back; do not create a new version merely to fill the
evidence shape.

Also save the original activation state before dispatch as `active` with exact Flow
ID/version, `inactive` with null identity plus successful evidence, or `unknown` after
failed/ambiguous evidence. Do not substitute the post-deploy active identity. The
rollback path may reactivate only the saved original active version. For an originally
inactive Flow, preserved source must be restored while current read-back continues to
prove inactivity. If the Flow is active and no supported deactivation operation with
read-back has been established, rollback remains BLOCKED for manual deactivation;
never select a fallback version or claim completed rollback.

Add `flow_validation` to that item's ordinary observation using the canonical
schema in `completion-contract.md`. Use `tests[]` for the complete required set and
worker `flow_tests[]` for matching exact named results; flat `test`/worker fields are
only the explicit singleton compatibility path. Select the current execution
receipts independently, before normalizing the results; preserve all earlier attempts
and any diagnostic results separately. Never choose a stale Pass to displace the
current failure. State which later receipt supersedes which earlier summary.

Before activation, independently check every required test against the deployed
Flow ID/version and current target/build. Do not demand FULLY_VERIFIED yet: that
final disposition also requires the subsequent active-version read-back. A required
Fail, missing/skipped/pending companion, mixed version or unresolved attribution
keeps the gate unsatisfied. After an allowed activation, collect fresh active
identity and run final reconciliation; actual state and policy deviations remain
separate facts. After any activation attempt, unknown activation read-back cannot be labelled Draft.

Save a runtime Tooling describe for the selected result projection and relationships.
For synchronous execution, correlate the returned method result through its actual
`ApexTestResultId` to exactly one `FlowTestResult`; null queue/run identities are
valid for this path and must remain null. For asynchronous execution, correlate the
actual queue ID and terminal result. Require exact Flow and test names, org, version,
current build and outcome in the contract's `version_result`; timestamps alone and
name-only queries are not correlation. `FlowVersionNumber` availability remains
version-sensitive: a missing/unsupported describe or failed query leaves evidence
unavailable, never a guessed field. Raw receipts and normalized assertions remain
separate; the helper validates supplied consistency, not Salesforce authenticity.

For `unsupported`, preserve the exact frozen reason and incumbent read-back with
`activation.attempted: false`; the authored Draft remains AWAITING_QA. A required
route that becomes unavailable keeps its required mode and unresolved tests.

## Agentforce Current-Test Evidence (Phase 3)

Read the installed `prompts/building/agentforce-validation-gate.md` and follow it as
the canonical policy. Compute its SHA-256 from that fixed installed path. The
reconciler independently reads the same sibling file; do not load a worker-selected
policy or accept a digest copied from evidence without checking the file.

Run this process from every ledger item that carries `acceptance.agent_runtime`,
even if the Phase 3 worker report is absent or malformed. The worker smoke boolean
is summary only. It cannot pass or fail the independent check.

1. Independently read back the published agent/version and save the result. Then
   open one explicitly selected current test and save its start/identity result.
   Do not infer either identity from a passing observation.
2. Collect current live invocation, behavior and source-specific structural facts
   under the canonical gate. Preserve earlier attempt references. A fixed retest
   supersedes a failed attempt only with an explicit selection and saved fix source.
3. Add one `agent_contexts[]` row per tested ledger obligation:

   ```json
   {
     "item_id": "p3.agent.flag-case",
     "agent_api_name": "Demo_Agent",
     "deployed_version_id": "independently read-back version id",
     "deployment_source": "saved deploy/version read-back",
     "source_kind": "agent_script|compiled_planner|unknown",
     "gate_sha256": "digest of installed canonical gate",
     "test": {
       "attempt_id": "selected attempt id",
       "mode": "session_turn|job_case",
       "session_id": "required with session_turn",
       "turn_id": "required with session_turn",
       "job_id": "required with job_case",
       "case_id": "required with job_case",
       "identity_source": "saved current test start/identity result",
       "history": [{"attempt_id": "prior", "outcome": "failed|passed|unavailable", "source": "saved result"}],
       "supersedes_attempt_id": "optional prior failed attempt",
       "fix_source": "required when superseding"
     }
   }
   ```

4. Put normalized `agent_runtime` in that item's ordinary observation. It uses Scout
   keys, not raw Salesforce field names: exact agent/version/gate/test identity;
   evidence channel; invocation status/action/live/simulated/evidence kind/source;
   exact mutation target+before+after or read-only output+side-effect N/A; and the
   source-specific structural result. For event logs also save REST Describe and
   field-map sources, verified session mapping, correlation result, and the
   lower-inclusive/upper-exclusive UTC fence. Never fabricate behavior placeholders
   when invocation evidence is unavailable or a complete trace proves no call.

   This is a complete mutating, Agent Script, live-preview example. Replace the
   placeholders with values and saved-source references from the independently
   selected current test; do not copy identities from the trace itself.

   <!-- agent-runtime-example:start -->
   ```json
   {
     "agent_api_name": "Demo_Agent",
     "deployed_version_id": "0Xx-version-7",
     "gate_sha256": "<installed gate sha256>",
     "test_identity": {
       "attempt_id": "attempt-1",
       "mode": "session_turn",
       "session_id": "session-current",
       "turn_id": "turn-current"
     },
     "evidence_channel": "live_preview",
     "invocation": {
       "status": "succeeded",
       "action": "Flag_Case",
       "live_actions": true,
       "simulated": false,
       "evidence_kind": "live_trace",
       "source": "saved current preview trace / invocation 4"
     },
     "behavior": {
       "target": {"Case.Id": "500xx"},
       "before": {"Case.Flagged__c": false},
       "after": {"Case.Flagged__c": true},
       "source": "saved before and after SOQL 5"
     },
     "structure": {
       "method": "agent_script_validation",
       "result": "pass",
       "source": "saved validate authoring bundle result 2"
     }
   }
   ```
   <!-- agent-runtime-example:end -->

   The exact enums and variants are:

   - `test_identity.mode`: `session_turn` with `session_id` + `turn_id`, or
     `job_case` with `job_id` + `case_id`.
   - `evidence_channel`: `live_preview`, `event_log`, or `test_job`.
   - `invocation.status`: `succeeded`, `failed`, `not_invoked`, or `unavailable`.
     `invocation.evidence_kind` is `live_trace`, `complete_trace`,
     `expected_action_declaration`, `transcript_only`, `authoring_preview`, or
     `test_metrics`; only a current `live_trace` or `complete_trace` is eligible.
     `not_invoked` is FAIL only with a `complete_trace`; unavailable/incomplete
     evidence may omit `action` and `behavior`.
   - For read-only work, replace `behavior` with
     `{"output": {"answer_contains": "approved dosage"},
     "side_effect": "not_applicable", "source": "saved current output 5"}` and
     use the exact same output assertion in ledger criteria.
   - `structure.method` is `agent_script_validation` for Agent Script or
     `compiled_schema_join` for realized compiled planner source. Its `result` is
     `pass`, `fail`, or `unavailable`. Unknown source stays unavailable.
   - For `evidence_channel: "event_log"`, also add:

     ```json
     {
       "retrieval": {
         "describe_source": "saved REST Describe response 6",
         "field_map": {
           "session": "described session field",
           "turn": "described turn field",
           "version": "described version field",
           "timestamp": "described timestamp field"
         },
         "session_mapping_source": "saved session + turn + version mapping 7",
         "correlation": "verified",
         "lower_inclusive": "2026-09-17T10:00:00Z",
         "upper_exclusive": "2026-09-17T10:00:02Z",
         "event_timestamp": "2026-09-17T10:00:01Z"
       }
     }
     ```

     Merge this `retrieval` member into the runtime object. Described field labels
     are normalized references only; they do not assert portable Salesforce API
     field names.
5. Run `scripts/build-completion.py`; it invokes
   `scripts/agentforce_evidence.py` with the actual installed gate content. Preserve
   each item's runtime assessment and its ordinary completion disposition.

PASS affects only its exact ledger item. Current FAIL or BLOCKED stays explicit even
without a worker report and cannot be hidden by an authorized non-execution row.
UNAVAILABLE is distinct from an observed failure. Missing worker output still makes
completion INCOMPLETE even when runtime PASS is exposed. A passing hero check never
clears another required action, guardrail or QA obligation.
