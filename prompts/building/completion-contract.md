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
`acceptance.flow_validation`. Its `flow_api_name` and optional
`flow_test_api_name` are authoritative identities. Its mode is immutable:

- `flow_test_required` requires a terminal current test for that exact Flow/test,
  independent `FlowTestResult` proof of the tested positive version, and active
  read-back of the same Flow ID and version before VERIFIED. Pending, failed,
  unavailable, missing, old-version, or ambiguous evidence remains AWAITING_QA or
  INCOMPLETE. A worker's VERIFIED claim is never evidence.
- `unsupported` has a null test name and a concrete frozen reason. Report the
  deployed Flow Draft and AWAITING_QA with `flow_test_outcome=NOT_SUPPORTED`.
  Do not switch a required item to unsupported because an org query or association
  is unavailable.

An already-satisfied Flow does not require a new version. It needs pre-dispatch and
current exact active identity plus a current targeted test/version result for that
same identity. After an activation attempt, failed or unavailable active read-back
is unresolved and the state is failed/unknown; do not report Draft unless a current
read-back proves Draft.

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
