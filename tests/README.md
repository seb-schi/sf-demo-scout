# Maintained offline verification

Run the complete repository suite from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -v
```

This is the single clean-checkout offline command. It uses only local fixtures:
no network, npm registry, Salesforce org, real CLI installation, customer data,
or user-home mutation. The test processes retain the caller's real `HOME`;
fixture locations are passed through the shipped seams. CLI tests replace
`PATH` with a temporary directory plus fixed system utility directories, and
provide isolated `npm`, `sf`, and `claude` stubs so missing stubs cannot fall
through to a user's installation. Parent and child Python processes disable
bytecode writes.

Batch 8a ownership fixtures create complete temporary npm package metadata,
declared executable bins, and active symlinks. Negative cases cover native or
shadowed executables, missing tools, failed/timed-out/ambiguous roots, malformed
metadata, unsafe bin paths, non-executable targets, invalid text, and shell
function shadowing. MCP fixtures execute the shipped status helper against a
local Claude or Codex CLI stub and cover explicit host selection, conflicting
host signals, managed-policy versus user disablement, invalid server names,
enabled registrations without runtime readiness, current-project inheritance,
aliases, exact known signatures, list
failure/timeout, malformed or nonmatching output, ambiguity, documented
transport states, spoof resistance, invalid text, and secret-free output. They
do not read configuration or credentials, contact providers, authenticate, or
create/remove connections.

Host compatibility fixtures also cover Codex startup ignoring Claude's cached
MCP state and credential settings, disabled Slack not triggering authentication,
Codex workspace setup preserving Claude files, and a Claude-only guard on prefix
repairs. Packaging checks reject nonportable MCP identifiers and operational
prompts that reintroduce Claude-only CLI availability gates. These tests do not
replace fresh-session startup, actual tool discovery, or an authorized DX read
in each host after installing a release.

Batch 8b bootstrap fixtures run the shipped Bash boundary with an isolated
`PATH` and local tool/installer stubs. They cover valid existing tools without
installer calls; broken, malformed, unreadable, old, and wrong-major existing
tools without replacement; successful missing-tool installs with a fresh
selected-executable probe; installer failure after a partial change; exit-zero
installs followed by missing, old, malformed, or failing probes; missing brew or
npm; invalid selectors; and distinct missing-npx versus failed-cache outcomes.
No fixture runs Homebrew, npm, npx, a registry request, or a real host runtime.

Prerequisites are Python 3, PyYAML, Git, `/bin/bash`, standard POSIX/macOS shell
utilities, and a real `/bin/zsh`. The shell-repair tests execute `zsh -f -n`
against both original and staged temporary files. Missing Git, zsh, or PyYAML
fails clearly; no prerequisite is reported as a skipped pass.

## Vendoring verification and recovery limits

`tests/test_vendor.py` runs the shipped `scripts/vendor-skills.sh` entrypoint in
temporary plugin fixtures. Its Git executable copies a local synthetic upstream,
so the suite never fetches the real repository or changes the working tree's
skills. Failure injectors act outside the production script and exercise clone,
staged-copy, publication, rollback, post-publication backup cleanup, symlink,
and lock failures. One offline test uses real Git with isolated config to prove a
full pinned SHA wins after the local upstream branch advances. Tests also require
hidden/nested-file copying, obsolete-file removal, the full policy roster, and
truthful partial-result counts.

The vendoring command handles SIGINT, SIGTERM, and SIGHUP during ordinary
operation and restores the previous tree when publication fails. If restoration
also fails, it leaves the old backup in place and prints its exact recovery path.
If cleanup fails after a replacement is installed, `BACKUP_PATH` identifies any
remaining old-backup material; cleanup may already have removed part of it, so
that path is diagnostic and is not claimed as a complete recovery tree.
SIGKILL, process-host failure, and power loss cannot be trapped; they may leave a
private stage, backup, or `.vendor-skills.lock`. The command never guesses that a
lock is stale or deletes it automatically. A maintainer must inspect those paths
and recover or remove them manually before rerunning.

## Historical assertion map

The historical assertion count is separate from unittest's method count.
Subcases retain the original semantic assertions without creating one method per
assertion:

| Historical group | Maintained location | Assertions | Coverage |
|---|---|---:|---|
| B2 shell repair | `tests/test_setup.py::ZshrcScriptTests` | 65 | Missing-file creation; existing pair, unrelated text, backup and idempotency; lone, padded, reversed, duplicate and nested markers; ordinary marker words; multiline result rejection; original syntax and validator failures; successful/rejected/dangling symlinks; injected staging and final-replace failures; mode, exact backup and staging cleanup. |
| B3 CLI reporting | `tests/test_setup.py::CliRefreshScriptTests` and `tests/test_packaging.py::test_done_summary_keeps_three_truthful_failure_assertions` | 27 | Twelve outcomes for each of `sf` and `claude`, including policy-held, installer/probe failures, malformed or embedded version text, no-op and mismatch; three truthful done-summary assertions. |
| B4 slug/hook | `tests/test_slug.py` | 27 | Nine literal transliterations, empty/glob inputs, six literal truncation boundaries, and ten real startup-hook customer-folder assertions using F6's cache/settings/config/workspace seams and complete synthetic CLI envelopes. |

B1 remains a static instruction contract in
`tests/test_packaging.py::test_source_login_instructions_preserve_default_org_contract`.
It checks the two source-login commands do not set the default, the two deliberate
switch commands do, source authentication stays inline, delegation text is gone,
the sandbox endpoint and failed/cancelled stop rule remain, and the reciprocal
cross-reference stays present. These checks validate shipped instructions; they
do not claim runtime model compliance.

The baseline contained 128 unittest methods. Batch 6 added 23 focused methods,
Batch 7 added 14 vendoring methods, Batch 8a added 12 setup ownership/status
methods, and Batch 8b adds 9 bootstrap methods, for 186 total while preserving
all 177 pre-Batch-8b methods. Batch 9 adds 30 methods (20 workspace, 2 CLI
probe, 5 preservation, and 3 completion methods), for 216 total while retaining
all 186 baseline methods. The 119
historical assertions above remain executed inside the maintained methods and
subcases, including all 24 CLI outcome meanings.

Batch 9 runs the workspace helper against explicit temporary paths and a local
`sf` stub. It covers failed/malformed scaffold results, missing artifacts,
partial reruns, incumbent-file preservation, live/dangling symlink blockers,
staged-link rejection, genuine copy failure and
atomic config-write failure. CLI fixtures cover failed, ambiguous and malformed
pre-update probes and mismatched npm transitions without allowing installation.
Recovery fixtures exercise complete selected pre-edit bundles, failed copies,
immutable retries and cleanup verification. Completion checks reject supplied
failed or malformed snapshot evidence. Static caller checks verify prompt wiring;
the parent still determines whether an edit requires a snapshot and independently
verifies its receipt. These fixtures do not prove model compliance or live recovery.

Batch 10 adds 24 settings methods for 240 total, retaining all 216 prior methods.
It runs the shipped settings helper against explicit temporary files.
It covers the exact JSONC property boundary, comments and unrelated bytes,
malformed/ambiguous input, live and missing hook targets, supported interpreter
wrappers, compound commands, unsupported hook types, and inaccessible targets.
Filesystem fixtures cover no-op identity, exact backups, modes, symlink and
backup-collision refusal, copy/stage/replace failures, and distinct reporting
after a completed replacement fails verification. The suite does not modify
real user settings or exercise live client loading; launchctl behavior is unchanged.

Batch 11 adds 14 Flow/completion and 5 audit-route methods for 259 total, preserving
all 240 baseline methods. It exercises Flow validation through the existing read-only completion
reconciler. Fixtures distinguish the deployed draft from an older active version,
require the exact selected test and terminal run/queue result, check activation
identity, and retain unsupported, failed or unavailable evidence as unresolved
work. The fixture payloads are normalized assertions with saved-source references;
the helper does not contact Salesforce or authenticate those assertions. Static
audit checks resolve the shared Markdown barrier and check consumer order across
new, iteration and Showtime routes, including mutations that remove or move the
barrier. They do not simulate worker scheduling or prove model compliance.
Live FlowTest/version-association, activation, retrieval and background-audit
acceptance remain separate checks in an appropriate org/client environment.

Batch 12 adds 12 focused methods for 271 total while preserving all 259 baseline
methods. Four executable asset fixtures exercise exact report/Flow files, complete
Apex companions and LWC bundles through immutable pre-edit snapshots, cleanup,
selected restore staging, copy failure, symlink rejection, and tampered incomplete
receipts. Eight static contract methods check only the direct-repair entry route,
materialized shared pre-mutation ordering, fail-closed folder/Flow restoration,
authorized-skip and no-mutation exemptions, ledger-derived parent review, and
cleanup/handover consumers. They do not prove model
behavior, live Salesforce read-back, Flow activation, or destructive rollback.

Batch 13 adds 9 focused static contract methods for 280 total while preserving all
271 baseline methods. They cover Scout-owned vendor precedence and dependency
boundaries, Flow handoffs, analyzer fallback prerequisites, report and formula
corrections, supported FlexiPage scope, mode-specific Agentforce readiness, all-phase
injection, direct-repair entry, and caller-derived selected-section materialization.
The materialization fixture reads the shipped selection table, resolves a synthetic
installed path, and checks a report-only Phase 1 block excludes unrelated sections.
These checks do not execute a model, vendor skill, CLI, MCP tool, or Salesforce org.

## September 22 local hardening verification

The same offline command also runs the owned-workspace, required-Flow-test,
FlowTest-template, and materialized-caller regressions. Owned-workspace fixtures
exercise concurrent audit/build/repair writers, interrupted and unknown source
retention, absolute path/config/ownership checks, failed preparation/preservation,
and immutable Layout/SharingRules/FlexiPage originals across separate edits.
Caller fixtures execute shipped prepare/preserve/stage commands with temporary
projects, including the existing-agent parent-to-worker handoff, and feed the
shipped unsupported-Flow JSON into the actual reconciler.

Required-test fixtures cover complete sets and legacy singleton compatibility,
missing/duplicate/failing/skipped/pending companions, diagnostic substitution,
stale/wrong-org/mixed-version identities and sync/async result correlations.
XML fixtures parse/materialize the canonical maintained `sf-flow` templates,
reject entity declarations and exercise their business assertions against values.
Static instruction checks protect delivery only. A separately recorded local
model canary is not native-client enforcement or Salesforce acceptance evidence.
No automatic staging cleanup exists; retained source is intentional. Live MCP
directory behavior, exact-version execution and exclusion semantics require the
separately scoped disposable-target experiment. Normalized evidence still does
not authenticate Salesforce truth. The other 25 upstream-derived skills remain
protected; `sf-flow` is deliberately maintained without changing its frozen policy.

## Release-only validation

The 16 cartridge-selection methods in `test_knowledge_cartridges.py` exercise
the shipped helper and its materialized Stage 4 command. Fixtures cover selected
older versions beside newer cache leftovers, disabled and absent plugins, full
provider identities, ambiguous scopes, literal paths, contract containment,
malformed inventories, unavailable CLI results, and the native session directory.
They use local inventory fixtures and a read-only CLI stub. They do not claim
native model compliance, loaded-session byte identity, or Claude/Codex parity.

Run installed `claude plugin validate` separately against the release candidate.
It invokes a real installed client and is therefore a release gate, not part of
the hermetic offline suite.
