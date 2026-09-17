# Existing and New Component Rollback

Use this contract for every supported component that this run may mutate. It does
not authorize a new operation, widen `BUILD_SCOPE`, relax the NEVER tier, or replace
a component skill's authoring and validation rules.

## Before any mutation

1. Freeze the target org, exact metadata identity, requested delta, expected state,
   and exclusions from the current approved instruction. Do not retrieve yet.
2. Append a durable `PENDING — component repair` checkpoint to this org's existing
   change log before any retrieve can overwrite retained scratch, before editing, and
   before cleanup. If no change log exists, create a conventional
   `changes-[YYYY-MM-DD]-[HHmm]-[CUSTOMER].md` in the resolved org folder first.
   Record an attempt ID, target org and component identity, expected delta and
   exclusions, with classification/evidence and artifact fields pending. If this
   checkpoint cannot be saved, stop BLOCKED.
3. Retrieve and read back that exact target. Classify it as `existing` only from
   successful current evidence, `new` only from positive absence evidence, otherwise
   `unknown`. Empty, failed, or ambiguous retrieval is `unknown`, not absence.
   Classify a Report and its ReportFolder separately. For a Flow, separately record
   whether the original was active or inactive and the exact active Flow ID/version
   when active; failed or ambiguous active-state evidence is `unknown`. Update the
   pending checkpoint with this evidence before continuing.
4. If saved independent baseline and current read-back both prove an `existing` target
   already has the exact requested state, and tool evidence proves no mutation was
   attempted, finalize it as `already_satisfied`; no pre-edit snapshot or receipt is
   required. A label without both observations is insufficient, and any attempted
   mutation removes this exemption. Otherwise, for `existing`, use the complete selected
   source from that successful retrieval and run the caller's absolute `ASSET_HELPER`
   path with `preserve --kind component-preedit`, the exact component selector, and the caller's absolute
   `ROLLBACK_DIR`. A class or trigger
   selector includes its metadata companion; LWC/Aura and other supported bundles
   require the whole member directory. Never select a metadata-type folder. Verify
   the returned artifact immediately, then append its absolute artifact/source paths,
   exact receipt members, and verification result to the pending checkpoint. Preserve
   the first verified before-state on retries. Never reconstruct it after mutation.
   A `new` component records the positive absence source and uses
   `preedit_snapshot.status: not_needed`. `unknown` is BLOCKED and must not be written.
   Never edit or deploy from the durable snapshot; edit only disposable working source.

## Validate and report

Read back the requested state and relevant incumbent content after the operation. For
Reports, compare filter values, filter logic, format/grouping, and unrelated existing
content. For Flows, the exact-version testing and activation rules in Phase 2 remain
binding. A green deploy with wrong requested state is FAILED. Missing or unavailable
read-back is AWAITING_QA/unresolved. `already_satisfied` is valid only when saved
pre-mutation evidence already contained the requested state; a no-change result after
an attempted mutation is not enough.

Append the final outcome to the same checkpoint for `applied`, `already_satisfied`,
`failed`, `blocked`, or `unverified`, including receipts, read-back sources, and exact
remaining action. Do this even when the operation fails or was already satisfied.

## Roll back

- Existing non-Flow component: verify the first `component-preedit` artifact again,
  stage only its receipt-selected component into a disposable project with the same
  absolute `ASSET_HELPER`, validate current org identity/state, deploy only that exact
  component, and read it back. Never use git checkout, a wildcard, or a fresh retrieve
  as original-state evidence.
- Existing Flow: verify the first artifact again and stage the preserved original definition
  into a disposable restore project. When the Flow was originally active,
  deploy the preserved definition as needed, reactivate only the recorded original
  Flow ID/version through the supported exact `FlowDefinition` route, and read back
  both original source and runtime identity. When it was originally inactive and the
  current read-back proves inactive, deploy the preserved definition as an
  exactly attributed Draft and read back both its original contents and the absence
  of an active version. If current state is unknown, stop unresolved without deploying
  or claiming rollback. If current
  state is active, proceed only with a documented supported deactivation operation and
  successful read-back, then follow the inactive branch; when none is established,
  stop `BLOCKED — manual Flow deactivation`.
  Retain the staged restore project and evidence and do not claim rollback completed.
  Never delete the incumbent or select or activate a fallback version. Missing
  identity/state or source evidence also blocks rollback.
  Record that Salesforce retains old and new version history; a completed rollback
  restores selected source/runtime state, not version erasure.
- Proven-new component: after the normal explicit destructive-action explanation,
  delete only its exact created identity and read back absence. Delete a new report
  folder only when the folder was separately proven new and is currently empty; later
  added or unknown contents require retaining the folder and handing off cleanup.

Record rollback read-back and remaining uncertainty in the change log. Startup and
final cleanup must stop while a pending checkpoint lacks a final outcome, an existing
component with an attempted mutation lacks its verified first receipt/path, or any
artifact/staging verification failed. A finalized `already_satisfied` target needs no
receipt only when saved independent baseline and current evidence prove the requested
state and no mutation was attempted. A frozen authorized skip needs no checkpoint or
receipt when no mutation occurred; an unexpected mutation is not exempt. Retain scratch
paths in the checkpoint so recovery remains discoverable.
