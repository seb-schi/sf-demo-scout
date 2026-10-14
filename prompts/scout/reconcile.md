# Settle another task's open job

`pending` lists a job under `open_jobs` when a checkpoint records it and no record settles it, with the exact name for its receipt under `receipt_keys`. Before any write, read each one's status yourself, through the bound username:
- a deploy: `sf project deploy report --job-id <ID> --target-org [BOUND_USERNAME] --json`
- a Bulk job: `sf data bulk results --job-id <ID> --target-org [BOUND_USERNAME] --json`
- an agent publish: the agent version's status

Make sure this task's change log names the bound org in its header, as the template's `Org:` line does. Then add one line per job under `## Reconciled Jobs`, above the final `## Checkpoints`:

`- reconciled: <its receipt key>; status: <the answer>; read-back: <what the job changed, as you read it now>`

- A terminal word for the job's type settles it.
- `not found` settles a job Salesforce answers it doesn't have, such as the CLI's `InvalidDeployIdError`, but only past Salesforce's retention: more than 31 days since a deploy's `launched:` time (else its checkpoint heading's time), or 8 since a Bulk job's. Inside that window, or with neither time recorded, Salesforce may still have the job, so the answer means the read was wrong: stop and tell the SE.
- `unavailable` settles a submission with no status to read, such as Email-to-Case's apply script, once its session has ended and no process of it still runs (`pgrep -f <script>` finds none). An agent publish always has a status to read.
- Those two need the read-back. Any other answer, an error included, settles nothing: stop and tell the SE.

Then rerun `pending`, and write only once every entry shows under `reconciled_jobs`; fix any line that doesn't. Never edit the other task's records.
