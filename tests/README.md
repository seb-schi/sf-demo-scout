# Maintained offline verification

Run the complete repository suite from the repository root:

```bash
scout_test_state=$(mktemp -d /tmp/scout-tests.XXXXXX)
mkdir -p "$scout_test_state/home" "$scout_test_state/claude"
env HOME="$scout_test_state/home" CLAUDE_CONFIG_DIR="$scout_test_state/claude" \
  TMPDIR="$scout_test_state" PYTHONDONTWRITEBYTECODE=1 \
  python3 -B -m unittest discover -s tests -v
```

This is the single clean-checkout offline command. It uses only local fixtures:
no network, npm registry, Salesforce org, real CLI installation, customer data,
or user-home mutation. The test processes retain the supplied `HOME`;
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
and Codex workspace setup preserving Claude files. Packaging checks reject
nonportable MCP identifiers and operational prompts that reintroduce Claude-only
CLI availability gates. These tests do not replace fresh-session startup, actual
tool discovery, or an authorized org read in each host after installing a release.

Batch 8b bootstrap fixtures run the shipped Bash boundary with an isolated
`PATH` and local tool/installer stubs. They cover valid existing tools without
installer calls; broken, malformed, unreadable, old, and wrong-major existing
tools without replacement; successful missing-tool installs with a fresh
selected-executable probe; installer failure after a partial change; exit-zero
installs followed by missing, old, malformed, or failing probes; missing brew or
npm; and invalid selectors. No fixture runs Homebrew, npm, npx, a registry
request, or a real host runtime.

Prerequisites are Python 3.9+, Git, `/bin/bash`, standard POSIX/macOS shell
utilities, and a real `/bin/zsh`. The setup-fence tests parse every shipped
bash fence with `zsh -f -n`, because the model's shell may be zsh. Missing Git or zsh
fails clearly; no prerequisite is reported as a skipped pass.

Install Python dependencies into a development virtual environment using
`python -m pip install -r tests/requirements.txt`, then run the command above
with that environment's Python. The report repair uses only the standard library,
with bounded Expat parsing that rejects DOCTYPE/entity declarations and external
references before resolution. Its CLI fixtures run with site packages disabled.

## Writer-project real-CLI conversion gate

W8 also requires this separate integration gate in a **network-denied sandbox**
with an already installed real `sf` CLI. Default discovery above deliberately
does not enter `tests/integration/` (it is not a Python package). Both commands
must pass for W8; the fixture suite alone does not prove source resolution.

```bash
scout_cli_state=$(mktemp -d /tmp/scout-cli-tests.XXXXXX)
mkdir -p "$scout_cli_state/home" "$scout_cli_state/claude"
env HOME="$scout_cli_state/home" CLAUDE_CONFIG_DIR="$scout_cli_state/claude" \
  TMPDIR="$scout_cli_state" PYTHONDONTWRITEBYTECODE=1 \
  SF_DISABLE_TELEMETRY=true SF_AUTOUPDATE_DISABLE=true \
  python3 -B tests/integration/test_forceignore_conversion.py
```

The gate creates fresh temporary HOME, Claude configuration and CLI state/cache
directories under `/tmp` for its subprocesses, passes an environment allowlist
without inherited authentication or org selectors, and disables telemetry and
updates. Network denial must be supplied by the execution sandbox; environment
flags alone do not enforce it. Missing CLI/SDR prerequisites or timeouts fail;
the gate never installs dependencies or reports a skipped pass. It prints
`sf --version`, the installed SDR version, commands, JSON results, manifest
members and converted file inventories. Retain that output with the review.

The fixture uses a writer project below hidden ancestors and spaces, plus an
outer `.forceignore` to reproduce the native trap. Relative and absolute source
paths must resolve the exact object and bundle. Removing only the writer's
`.forceignore` must yield an empty manifest; restoring it must recover both
components. Dotfiles, nested hidden directories, `.dup` files and package2
descriptor/manifest files remain excluded, including inside the bundle and
without an outer ignore file. There are no deploy, retrieve, auth or org calls.
Native verification of both routes remains Opus's W5 integration gate.

## Scout 2 preview verification

`test_report_repair.py` exercises the actual helper with a synthetic Salesforce
adapter and the existing workspace/snapshot subprocesses. Independently authored
final-state and operation-trace assertions cover exact targeting and scope,
folder/default preservation, ambiguous predicates, corrupt recovery, stale state,
unknown launches, no-op, linked tasks, task/component locking and cross-task replay
prevention. Adapter tests check explicit CLI selectors and authenticated identity
queries with credential-free persistence. An independent fake executable exercises
the real CLI adapter, durable launch stdout, exit codes and main's error JSON.
Sanitized read-only live CLI captures and clearly labeled synthetic fixtures live
in `fixtures/report-repair/`; test runs themselves make no live org calls.

Source coverage and reconciliation of legacy prose checkpoints remain caller
judgments, not properties proved by a note. Read-only org/report integration is
recorded separately from the fixtures. Actual report write/restore and one-report
terminal receipts remain a live acceptance gate.

## Official plugins (Scout 2.1)

Scout no longer copies Salesforce's skills; it drives the official plugins from
Salesforce's GitHub marketplace. `test_setup_official_plugins.py` runs the setup
script against a fake `claude` CLI: registration under any local name, auto-update,
the core set, first-need installs, duplicate copies, failures and other hosts.
`test_scout_official.py` checks the resolver against synthetic Claude config
folders (GitHub-only, every supported source form, switched-off and duplicate
copies, unreadable records, the Codex checkout and the trial source mode), skill
verification and the coexistence check with a fake `sf`. `test_official_overrides.py`
pins the driving contract. When `SCOUT_SF_SKILLS_CHECKOUT` names a local checkout of
Salesforce's sf-skills repository, it also checks every qualified name, capability-map
entry and cross-plugin handoff against it, and runs two official hooks from that
checkout with stubbed tools: the production gate (`sf-deploy-gate prod-check`, with a
fake `sf` classifying the org as production) and the LWC plugin's Write/Edit
validator (with a fake `npx`). Without the variable, those checks are skipped and
say so. None of these tests install a plugin, contact a marketplace or a Salesforce
org, or use the network.

## Historical assertion map

The historical assertion count is separate from unittest's method count.
Subcases retain the original semantic assertions without creating one method per
assertion:

| Historical group | Maintained location | Assertions | Coverage |
|---|---|---:|---|
| B2 shell repair (retired in 2.4) | none: setup no longer edits `~/.zshrc`, and these tests went with that step | 65 | Historical: missing-file creation; existing pair, unrelated text, backup and idempotency; lone, padded, reversed, duplicate and nested markers; ordinary marker words; multiline result rejection; original syntax and validator failures; successful/rejected/dangling symlinks; injected staging and final-replace failures; mode, exact backup and staging cleanup. |
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
all 186 baseline methods. The 54 B3 and B4
historical assertions above remain executed inside the maintained methods and
subcases, including all 24 CLI outcome meanings; B2's 65 retired with the
`.zshrc` step in 2.4.

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
In 2.4 the settings cleanup these methods drove (model pins, AI-tool hooks, retired
permission rules) was retired, and its tests with it. `tests/test_settings_parsers.py`
keeps the parser cases (strict JSON, JSONC, linked files) for the marketplace
auto-update step and the read-only model report, which still use those parsers.

## 2.4: checks for the public release

- `tests/test_public_hygiene.py::SlackWorkspaceTests` fails when anything shipped
  links one company's Slack workspace; Slack's public service hosts are fine. Names of
  internal services are checked by the maintainers' private release check, so no public
  file lists them.
- `tests/test_prompt_references.py` checks that every plugin path a prompt, command,
  skill or hook names exists, so a deleted file leaves no dangling pointer. It doesn't
  see prose references to step letters or procedures.
- `tests/test_uninstall.py` runs `scripts/scout_uninstall.py` against a temporary home:
  the plan before any removal, the workspace only on request and only when it's
  recognisably Scout's, links, absent folders and folders outside the home.
- `tests/test_setup_official_plugins.py` and `tests/test_shell_callers.py` check that
  setup fills in a missing marketplace `autoUpdate` and never overrides one the SE set.
- `tests/test_packaging.py` checks the per-host manifests: one version, Claude's hooks
  off the default path, and no hooks or commands for Codex.

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
