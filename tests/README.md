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

Prerequisites are Python 3, `/bin/bash`, standard POSIX/macOS shell utilities,
and a real `/bin/zsh`. The shell-repair tests execute `zsh -f -n` against both
original and staged temporary files. A missing zsh prerequisite fails clearly;
it is never reported as a skipped pass.

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

The baseline contained 128 unittest methods. Batch 6 adds 23 focused methods for
151 total while preserving those 128; the 119 historical assertions above are
executed inside the new methods and subcases.

## Release-only validation

Run installed `claude plugin validate` separately against the release candidate.
It invokes a real installed client and is therefore a release gate, not part of
the hermetic offline suite.
