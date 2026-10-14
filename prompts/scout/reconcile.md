# Settle another task's open job

`pending` lists a job under `open_jobs` when a checkpoint records it and no record settles it. Before any write, read each one's status yourself, through the bound username:
- a deploy: `sf project deploy report --job-id <ID> --target-org [BOUND_USERNAME] --json`
- a Bulk job: its job record, `GET /services/data/v<API>/jobs/ingest/<ID>` through `sf api request rest`
- an agent publish: the agent version's status

Then add one line per job under `## Reconciled Jobs`, above the final `## Checkpoints` in this task's change log:

`- reconciled: job <ID>; status: <the answer>; read-back: <what the job changed, as you read it now>`

Name a submission without an ID as `<its log's filename> · attempt <ID> · <its job label>` instead of `job <ID>`.
- A terminal word for the job's type settles it.
- `not found` settles a job Salesforce answers it doesn't have, such as the CLI's `InvalidDeployIdError`. A deploy that's still running stays reportable, so it can't be one.
- `unavailable` settles a submission with no status to read, such as Email-to-Case's apply script, once its session has ended.
- Those two need the read-back. Any other answer, an error included, settles nothing: stop and tell the SE.

Never edit the other task's records. `pending` then lists the job under `reconciled_jobs`, and later tasks don't read it again.
