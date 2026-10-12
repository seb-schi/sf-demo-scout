# Report repair CLI fixtures

Captured 2026-10-08 from a user-authorized demo org using sf 2.150.6,
SDR 13.1.1. Read-only calls only. No deploy start or restore was run.

`live-*` files are sanitized real JSON responses:

- org display: identity allowlist only; auth/token fields were discarded before saving.
- organization query: `SELECT Id FROM Organization`.
- retrieve success: existing report plus ReportFolder; observed source path suffix
  `.reportFolder-meta.xml`. `fileProperties.fileName` uses Metadata API names,
  whereas `files.filePath` uses the source-format names the helper must read.
- retrieve missing: exit 0 / `Succeeded`, but a missing-member warning and no report.
- deploy report success: exact existing job ID from this org's local cache, then
  `sf project deploy report --job-id ... --target-org ...`. Eight FlowTest components,
  nine success rows including package.xml, `numberComponentsTotal: 8`.

Org/user/component identifiers and paths are anonymized. Personal names, credentials
and incidental stack/context fields are omitted. No customer record data was queried.
This receipt establishes the general envelope/count convention, not a live one-report
deployment acceptance result.

`synthetic-*` are explicitly authored fixtures, NOT live captures. The single-report
success and queued/failed variants use the observed envelope. The async start fixture
uses the installed CLI's async result format. SourceConflictError is a pre-deploy
source-tracking rejection in installed `source-tracking/lib/shared/conflicts.js` and
its pre-deploy event handlers. `NothingToDeploy` is raised before launch in installed
`plugin-deploy-retrieve/lib/utils/deploy.js`. Only these checked classes establish
no-launch evidence; generic error envelopes and partial stdout do not.

`sf_fixture.py` is an independent fake executable with hard-coded SDR source paths.
It imports no implementation code. `cli_harness.py` only confines the global deploy
cache lookup to the fixture tree; it runs the real CLI parser/main and subprocess
adapter. Tests use Python `-S` to establish independence from site packages.

Still needed before live repair support: actual one-report async start and terminal
receipt, write/read-back, source normalization, conflict handling and verified restore
on a specifically authorized disposable report. Queued/failed live receipts are not
claimed by these fixtures.
