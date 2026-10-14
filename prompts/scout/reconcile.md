# Settle another task's open job

`pending` lists a job under `open_jobs` when a checkpoint records it and no record settles it, with the exact name for its receipt under `receipt_keys`. Before any write, read each one's status yourself, through the bound username:
- a deploy: `sf project deploy report --job-id <ID> --target-org [BOUND_USERNAME] --json`
- a Bulk job: `sf data bulk results --job-id <ID> --target-org [BOUND_USERNAME] --json`, run from a fresh scratch folder (`cd "$(mktemp -d)"`), since it writes the job's records out
- an agent publish: the agent version's status

Make sure this task's change log names the bound org in its header, as the template's `Org:` line does. Then add one line per job under `## Reconciled Jobs`, above the final `## Checkpoints`:

`- reconciled: <its receipt key>; status: <the answer>; read-back: <what the job changed, as you read it now>`

- A terminal word for the job's type settles it.
- `not found` records Salesforce's answer that it has no such job, such as the CLI's `InvalidDeployIdError`. `pending` accepts it once Salesforce can no longer report the job: more than 31 days after a deploy's launch or 8 after a Bulk job's, counted to this log's own time, or at once when the job's own log names another org ID (a refreshed sandbox).
- `unavailable` records a submission with no status to read: Email-to-Case's apply script, or an agent publish when no version of that agent exists. Use it once the submitting session has ended and no process of it still runs (`pgrep -f <script>` finds none).
- Those two need the read-back. Any other answer, an error included, settles nothing: stop and tell the SE.

Then rerun `pending`, and write only once every entry shows under `reconciled_jobs`. An entry still under `open_jobs` didn't settle: fix its line, or, for a `not found` that `pending` doesn't accept yet, stop and tell the SE the read may be wrong or the job too recent. Never edit the other task's records.
