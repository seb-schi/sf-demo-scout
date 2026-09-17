# Build outcome summaries (opt-in)

A build outcome summary is an optional local appendix to Scout's existing saved
change log and the same terminal copy. Create and save it locally only when the
SE asks for it. Do not create another artifact, externally publish it, add a
standard prompt, rerun a probe, or send telemetry or data to a service.

The summary is a compact view of evidence already produced by the build. It does
not change the completion contract, calculate a new score, or turn incomplete
evidence into success.

## Evidence to reuse

Use only the approved scope and spec, the actual mode selected from that spec,
the Phase 1–3 completion-reconciler outputs, any actually recorded Phase 4
status, and the existing change log and handover. Include evidence paths so a
reader can inspect the source. Record the actual Scout version and model only
when known from the run; otherwise write `unknown`.

Treat each reconciler output as bound to its own `build_id`, `spec_sha256`,
`ledger_sha256`, and phase. Invalid, missing, mixed, or stale identities are
unusable evidence. Mark that phase and its values `unknown` or `unusable`; never
merge them into a successful count.

Keep disposition counts separate for every phase: `VERIFIED`, `SKIPPED`,
`AWAITING_QA`, `FAILED`, `BLOCKED`, and `INCOMPLETE`. Phase 1–3 coverage does not
prove the whole build and says nothing about Phase 4. If Phase 4 has no recorded
status and evidence reference, report it as `unknown`. A phase is `not
applicable` only when the approved scope shows that the phase was not expected;
cite that scope source. An expected phase with missing or unusable evidence is
`unknown`, never `not applicable`.

Derive run type from the actual selected mode and approved spec: `new`,
`iteration`, `repair`, or `Showtime`. The selected mode may exist only in the
transient build-scope context rather than the final reconciler; if that original
context is unavailable, write `unknown`. Do not infer run type from the desired
comparison or relabel a run after the fact.

Elapsed time is reportable only when trustworthy start and end timestamps cover
the same stated scope. Name that scope. If either timestamp or scope is missing,
write `unknown`; never substitute zero. For retry reporting, count only recorded
attempts of the same operation and define retries as attempts beyond the first.
List report-repair attempts and verification probes separately because neither
is an operation retry. Missing attempt records are `unknown`, not zero.
The reconciler's `automatic_retry: false` means no automatic retry is scheduled;
it is not evidence that an operation had zero retries.

List manual follow-ups and QA follow-ups separately, with the reconciler item or
change-log evidence that requires each action. Manual work comes from unresolved
manual ledger items and the handover's setup obligations. Do not count an
authorized `SKIPPED` item as manual work unless separate evidence records a
remaining obligation. Do not copy customer identifiers,
credentials, URLs containing secrets, raw arguments, or unrelated error payloads
merely to make the summary look complete.

## Pasteable appendix

Copy this section into the end of the existing change log and replace only values
supported by the current run's evidence.

```markdown
## Build Outcome Summary (opt-in)

### Run
- Run type: [new | iteration | repair | Showtime | unknown]
- Run-type source: [mode/spec evidence path | unknown]
- Approved scope: [short scope description | unknown]
- Scope source: [approved spec/ledger path | unknown]
- Scout version: [actual version | unknown]
- Model: [actual model | unknown]
- Time interval: [start → end, timezone | unknown]
- Elapsed: [duration and covered scope | unknown]

### Evidence identity
- Change log: [path]
- Handover: [path or terminal output reference | unknown]
- Phase 1 reconciler: [path; current build/spec/ledger identity status | unknown]
- Phase 2 reconciler: [path; current build/spec/ledger identity status | unknown]
- Phase 3 reconciler: [path; current build/spec/ledger identity status | unknown]
- Phase 4 status: [actual status + evidence path | not applicable + approved-scope source | unknown]

### Phase dispositions
| Phase | VERIFIED | SKIPPED | AWAITING_QA | FAILED | BLOCKED | INCOMPLETE | Reconciler outcome |
|---|---:|---:|---:|---:|---:|---:|---|
| 1 | [unknown] | [unknown] | [unknown] | [unknown] | [unknown] | [unknown] | [unknown] |
| 2 | [unknown] | [unknown] | [unknown] | [unknown] | [unknown] | [unknown] | [unknown] |
| 3 | [unknown] | [unknown] | [unknown] | [unknown] | [unknown] | [unknown] | [unknown] |

Do not add a total row. State any invalid, missing, mixed, or stale phase identity
here: [none observed | phase + reason | unknown]. For a phase outside the
approved scope, replace that row's values with `not applicable` and cite the
approved-scope source; do not use `not applicable` for expected evidence that is
missing or unusable.

### Recorded attempts
- [operation + target]: [total recorded attempts | unknown]; retries beyond the first: [count | unknown]; evidence: [reference | unknown]
- Report-repair attempts: [count | unknown]; evidence: [reference | unknown]
- Verification probes: [count | unknown]; evidence: [reference | unknown]

### Follow-ups
Manual:
- [action | none evidenced | unknown] — evidence: [reconciler item/change-log reference | unknown]

QA:
- [confirmation | none evidenced | unknown] — evidence: [reconciler item/change-log reference | unknown]

### Scope-bound reading
[Describe only what the phase outcomes and Phase 4 status establish for the
approved scope. Do not generalize to the whole build, another run, or reliability.]
```

## Comparing representative runs

To compare behavior, collect actual opt-in summaries from separate representative
runs. A useful set is one `new` build, one `iteration`, and one `Showtime` build.
These are requested future measurements; this document does not claim they have
been run.

Keep each run's spec, approved scope, identities, evidence paths, and timing
interval intact. Compare like scopes, or state the normalization explicitly.
Never combine disposition counts across phases or runs into a general success
rate. Compare observed items such as phase-specific dispositions, scope-matched
elapsed intervals, recorded operation retries, report repairs, probes, and
manual/QA follow-ups. The result describes only those runs and scopes; it is not
a general reliability guarantee.
