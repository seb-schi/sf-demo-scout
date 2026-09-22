# Working source and operation failures

## One project per metadata writer

The parent resolves `WORKSPACE_ROOT` from the successful workspace bootstrap and
`CUSTOMER_DIR` from the selected customer, as absolute paths. The customer must be
an existing direct child of that workspace's `orgs/`. Never derive either by taking
a parent of cwd or concatenating an already absolute ORG_FOLDER. Before any metadata
retrieve, authoring, staging or repair, prepare a separate project for each writer
(including each audit worker and parent editability probe):

```bash
python3 "$ASSET_HELPER" prepare-workspace \
  --workspace-root "$WORKSPACE_ROOT" --customer-dir "$CUSTOMER_DIR" \
  --writer "$WRITER"
```

Require exit 0 and retain the JSON receipt. Carry its `project_root`, `source_root`,
`customer_dir`, `rollback_dir` and `ownership_receipt` unchanged. Verify with
`python3 "$ASSET_HELPER" verify-workspace --project-root "[returned project_root]"`
before use. A failed preparation or verification blocks that writer. Preparation
does not establish an incumbent before-state: preserve and verify exact originals
through the existing asset/rollback contract before editing them.

Only that writer uses that project. Dispatch its absolute `PROJECT_ROOT`; use it as
the working directory of each CLI call and as `retrieve_metadata.directory`, and
use its exact source paths for scoped deployments. Pass the selected target org
explicitly; do not copy credentials or set defaults in the project. If an installed
tool cannot direct conversion into this project, preserve the technical failure
and use an already-authorized supported explicit-directory route, or block the
affected operation. Never fall back to shared source. A retry by the same writer
may reuse its verified project and first originals; a replacement/overlapping
writer gets a new project and explicitly selected immutable inputs.

Retain working projects and record their paths in the existing log. Do not sweep
shared `force-app`, another customer's source, old audit files, unknown owners,
or these retained projects. No automatic cleanup runs at startup or finish.
Preservation failure retains original source and blocks the affected mutation;
do not recreate an original from edited source. Later user-requested cleanup must
identify exact ownership and recovery needs first; a failed removal stays a reported
failure, never a suppressed success or a reason to change command spelling.

## Classify a failure before choosing the next action

- An **explicit permission or policy rejection** stops that operation. Retain the
  rejected tool, operation, target, time and reason. Do not retry the same mutation
  via another tool, endpoint, shell spelling, changed working directory, worker,
  credentials or reduced validation. Prior scope approval does not override a new
  host denial. Return BLOCKED with the actual reason and the exact action needing
  resolution by the user/host; workers return this to the parent instead of rerouting.
- A schema, transport, unsupported-command or authentication error is technical
  evidence, not approval. If no refusal occurred, an already-authorized alternative
  may proceed only with the same target, scope and acceptance obligations and a
  concrete reason it addresses that error. Do not extract credentials, install
  tools, change settings or widen scope to make it work. An ambiguous failure stays
  unresolved until classified; do not assume it is a transport error.
- Routine actions already authorized by the current request need no repeated
  approval. Keep category gates and genuinely new targets/actions separate. A
  worker must not interpret "pre-granted" as permission to bypass host refusal.

These instructions govern parent and worker decisions. They do not implement or
replace the client's security boundary.
