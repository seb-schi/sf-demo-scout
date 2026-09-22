# Common Completion Contract

The orchestrator froze the expected-work ledger below from the approved spec before
dispatch. It is authoritative for coverage; your report cannot add, remove, rename,
or skip ledger items. Keep every existing detailed output array because the change
log still consumes it. Return one `completion[]` row for every expected item except
an independently authorized omission. An authorized omission may have no completion
row, but it must appear in `skipped[]` with the exact ledger reason.

For non-seed work, each ledger item's `acceptance.expected_state` is the normalized
literal requested state. Your report does not prove it; the orchestrator supplies a
separate `actual_state` with the same exact keys and typed values from targeted
read-back. Do not substitute a presence claim or deployment receipt.

When a supported Report/ReportType, Flow, Apex class/trigger, or LWC target is
modified, its detailed row also carries the shared component rollback evidence. An
`existing` target requires the verified first `component-preedit` artifact/source and
exact receipt paths; `new` requires saved positive absence evidence; `unknown` is
BLOCKED. This preservation evidence protects rollback but never proves completion.
For a Flow, report the original active/inactive state separately, including the exact
active ID/version when active. Missing preservation makes the item BLOCKED even when
current read-back or runtime testing passes.

Each completion row has exactly this meaning:

```json
{"item_id":"stable ledger id","status":"applied|already_satisfied|failed|blocked|awaiting_qa","summary":"concrete result, cause, or remaining QA"}
```

- `applied`: this run changed the item. The orchestrator still requires a current
  change source plus targeted read-back; your statement alone is not evidence.
- `already_satisfied`: exact requested state existed before dispatch. Do not use it
  for a mere presence check; the orchestrator requires saved baseline provenance.
- `failed`: an attempted operation failed. `blocked`: a prerequisite, safety gate,
  unsupported surface, or outstanding manual action prevents completion.
- `awaiting_qa`: deployment/read-back succeeded but required visual, test, or live
  runtime confirmation remains. It is never success and never belongs in `skipped`.
- There is no worker-authorized `skipped` status. Only the orchestrator's frozen
  `authorized_skips[]` can produce SKIPPED, based on an explicit SE non-execution
  decision or explicit approved-spec exclusion. Runtime refusals and manual
  handoffs are BLOCKED; deployed items awaiting confirmation are AWAITING_QA.

`skipped[]` is reserved for those authorized omissions. Do not put an exhausted
failure, safety refusal, unsupported runtime condition, Draft item, or manual handoff
there. Report it as FAILED, BLOCKED, or AWAITING_QA in `completion[]`. This common
outcome contract overrides older vendored skill wording that says to "skip" after a
failure or manual gate; keep following those skills for their technical procedures.

Every detailed row that corresponds to an expected item must carry its
`ledger_item_id`. A seed row must also report the explicit `operation`:

```json
{"ledger_item_id":"p1.seed.case","object":"Case","operation":"CREATE|UPDATE","records":2,"status":"SUCCESS|FAILED"}
```

`data_seeded.records` is reporting only; it never replaces the independent probe.
For CREATE, zero or fewer than the approved count contradicts SUCCESS. Extra rows
can be legitimate (for example Salesforce-created paired activity rows). UPDATE is
accepted only from exact target/field observations, not from its reported count.

Reconcile the common rows with the detailed arrays before returning. A detailed
failure, Draft/unvalidated state, failed agent recovery, unauthorized skipped/manual
handoff, or unresolved issue cannot be paired with `applied` success. Choose the
more conservative status and name the contradiction in `summary`/`issues`. Never
redeploy or reseed merely to repair a missing or malformed report; return a
corrected envelope describing what happened.

For every phase-2 Flow item, the frozen ledger also contains
`acceptance.flow_validation`. Its `flow_api_name` and required test declarations
are authoritative identities. Its mode is immutable:

- `flow_test_required` requires every name in `required_tests_all_must_pass` to
  have a terminal current Pass, independent `FlowTestResult` proof of the tested
  positive version, and active read-back of the same Flow ID and version before
  VERIFIED. The array must be nonempty, unique, and contain only API names. A
  legacy declaration with only `flow_test_api_name` explicitly requires that one
  test. When both fields exist, the single name must belong to the array; it is a
  selector, never permission to omit companions. Malformed/conflicting declarations
  are invalid input. Pending, failed,
  unavailable, missing, old-version, or ambiguous evidence remains AWAITING_QA or
  INCOMPLETE. A diagnostic cannot replace or join the required set. A worker's
  VERIFIED claim is never evidence.
- `unsupported` has a null test name, no required-test array, and a concrete frozen reason. Report the
  deployed Flow Draft and AWAITING_QA with `flow_test_outcome=NOT_SUPPORTED`.
  Do not switch a required item to unsupported because an org query or association
  is unavailable.

An already-satisfied Flow does not require a new version. It needs pre-dispatch and
  current exact active identity plus a current targeted test/version result for that
  same identity. After an activation attempt, failed or unavailable active read-back
  is unresolved and the state is failed/unknown; do not report Draft unless a current
read-back proves Draft.

For a required-test array, return `deployed[].flow_tests[]`, exactly one row for
each required name. The orchestrator separately supplies
`observations[].flow_validation.tests[]` with the same exact set. Do not mix these
collections with independent `test` or the old worker `flow_test_*`/
`tested_flow_version_number` singleton fields. Existing singleton declarations may
still use that legacy async report/evidence form; new sync evidence, including a
single test, uses the collection form below. A required array cannot silently fall
back to the singleton path. Explicit `execution_mode` or frozen `target_org_id`
also requires collection evidence so those new constraints cannot be ignored by
the legacy path.

The collection's independent `flow_validation.target_org_id` comes from the
orchestrator's selected target observation. New ledgers should freeze the same
`acceptance.flow_validation.target_org_id`; when present it must match. Older
immutable ledgers can use the independently captured target context. Both
`deployment` and `activation` carry that `target_org_id` and the current `build_id`.
Each test and its `version_result` must match those identities and the exact Flow.
These additions do not change the existing deployment/active read-back fields.

Each worker `flow_tests[]` row contains these normalized fields (illustrative
identities below are placeholders, never values to manufacture):

```json
{
  "test_api_name": "Required_Test",
  "flow_api_name": "Requested_Flow",
  "flow_id": "exact deployed Flow ID",
  "execution_mode": "synchronous",
  "build_id": "injected current build id",
  "target_org_id": "independently selected org ID",
  "run_id": null,
  "queue_item_id": null,
  "apex_test_result_id": "observed ApexTestResultId",
  "status": "terminal",
  "outcome": "Pass",
  "tested_version": 1
}
```

Here `apex_test_result_id` normalizes the unified runner's per-method `id` only
after its relationship is established. It does not imply that the response has a
property literally named `ApexTestResultId`. The relationships below were observed
on an API-66 Tooling projection; the public FlowTestResult Object Reference does
not list them, and Tooling documentation marks that object reserved for internal
use. Follow the sf-flow reference: retain a fresh target/API describe with the
version-query evidence and prove the exact relationship before normalizing it.
Missing support leaves required validation incomplete; do not substitute a
name/timestamp join or change the frozen validation mode to `unsupported`.

The independent `tests[]` row repeats those fields and adds `launch_source`,
`terminal_source`, and `version_source`: separate saved raw request, response, and
version-query references. It also adds `version_result`, the independently
correlated durable FlowTestResult observation. That object carries `id` (the
FlowTestResult record ID) and repeats `test_api_name`, `flow_api_name`, `flow_id`,
`build_id`, `target_org_id`, `outcome`, `tested_version`, `queue_item_id`, and
`apex_test_result_id`. Those are normalized fields derived from the saved result,
its related records and the current invocation context, not a claim that all are
literal Salesforce fields. Result/method IDs cannot be reused across required names.
If the execution response supplies `numTestsRun`, retain it as `num_tests_run` in
the independent test row; a terminal result requires a positive integer. Never
discard a zero-test response and replace it with historical result records.

- **Synchronous:** `execution_mode=synchronous`, `run_id=null`, and
  `queue_item_id=null`. A populated observed `apex_test_result_id` must match the
  independent FlowTestResult's `ApexTestResultId` relationship. A returned method
  result is not a run ID. Null queue identity is legitimate for this path.
- **Asynchronous:** `execution_mode=asynchronous`; a terminal or pending result
  requires the observed `queue_item_id`. Terminal evidence must match the
  FlowTestResult's `ApexTestQueueItemId` relationship. `run_id` may remain null;
  if an actual run ID is reported, independent evidence also needs `run_source`
  and `version_result.run_id` proving the queue/run relationship. Do not copy a
  method result ID into a run field.
- **Unfinished:** `status=pending|unavailable`, with null `outcome`,
  `tested_version`, `apex_test_result_id`, `terminal_source`, `version_source`,
  and `version_result`. Retain the attempted request/error under `launch_source`.
  Pending is only supported for async execution with a queue identity. A terminal
  `Fail|Error|Skip` remains unfulfilled and cannot authorize activation.

The helper reconciles local normalized assertions. It does not query Salesforce,
authenticate source references, or prove a caller's build/org attribution true.
The orchestrator must independently preserve and correlate current raw receipts;
timestamps alone, historic records relabeled as current, and a matching local hash
do not establish that a required test ran for this invocation. Correcting an
evidence envelope is not authorization to rerun tests, activate, or waive a gate.

The required common top-level fields are:

```json
{
  "schema_version": 1,
  "build_id": "injected build id",
  "spec_sha256": "injected approved-spec sha256",
  "phase": 1,
  "completion": []
}
```

Use the phase number injected below. Return these fields alongside, not instead of,
the phase's existing detailed arrays.
