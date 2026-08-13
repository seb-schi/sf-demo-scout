# Demo Architecture — Output Format & Reconciliation Rules

One living doc per org: `[ORG_FOLDER]/demo-architecture.md` (no timestamp — it is the single cumulative record, rewritten in place, NOT a per-session snapshot). This is the counterpart to the timestamped `demo-spec-*.md` files: a spec is a point-in-time build order; this doc is the demo as it stands now.

**Authored by sparring only.** `/scout-building` never writes it. It captures the synthesis ACROSS specs and change logs — it does NOT duplicate the per-session spec's build instructions, and it does NOT duplicate the change logs' build ledger (what objects/fields/flows were deployed). If you are tempted to list deployed metadata here, stop — point at the change log instead.

## This doc is a MAP, not a LOG — size discipline is the whole point

A map that costs as much to read as the territory has failed. This doc exists so a fresh sparring session skips a cold re-interview WITHOUT reading every spec and change log — so it MUST stay small. Hard rules, enforced on every write:

- **Whole-doc budget: ~350 lines / ~5k tokens.** If a reconcile pushes it past that, you are logging, not mapping — compact harder (fold resolved decisions into the Narrative Arc, drop them from the log). A doc over budget is a bug to fix that session, not a state to accept.
- **Every Decision Log entry is ONE line.** Decision + one-clause Why + date + change-log citation. If you are writing a second line, that detail belongs in the change log, not here — cite it, don't copy it.
- **No running-narrative banner.** The header is exactly the three fixed lines in the template. Current state lives ONLY in the present-tense Narrative Arc (rewritten each reconcile). Never accrete a prose "here's where we are" blob in the header or above the sections — that is duplication of the arc + the log, and it is what ballooned the Boehringer doc.
- **The change logs ARE the deep archive.** Do not create a separate archive file and do not preserve full history here. Compaction drops detail *because* the change logs still hold it — that is the trade, by design.

## Template

```markdown
# Demo Architecture — [Customer Name]
Last reconciled: [YYYY-MM-DD HHmm] by /scout-sparring
Target Org: [alias] ([username])
Reconciled through: [most-recent change-log filename folded in, or "none — created from discovery"]

## Customer Context & Value Spine
The stable frame — carried forward so sparring never re-asks it cold. Update only when a session genuinely changes it (new stakeholder, sharpened pain point); otherwise carry verbatim.
- **Company:**
- **Industry vertical / cloud:**
- **Key pain point:** [customer's words if quoted]
- **Demo stakeholders:**
- **Competitive context:**
- **Residual Message:** [the one thing the room remembers]
- **KP1 — Pain:** …
- **KP2 — Cost of Inaction:** …
- **KP3 — Future State:** …

## Demo Flow / Narrative Arc
The end-to-end story as it stands NOW — the scenes/beats in order, what the customer sees. This is the "overall flow" a fresh session needs to understand the demo without reading five specs. Present-tense, rewritten each reconciliation to reflect the current state — NOT append-only. This section ABSORBS resolved decisions: once a decision's outcome is visible in a beat, the beat is the record and the decision drops out of the log below.
1. **[Beat name]** — [what happens, what the audience sees, which KP it proves]
2. …

## Decision Log
ROLLING, not append-only. Newest at top. Two tiers, both one line each:
- **Live accepted decisions — keep only the last ~10.** Each is a decision + its rationale so it is not re-litigated. On reconcile, if an older accepted decision's outcome is now reflected in the Narrative Arc, FOLD it into the arc and DROP it here (the arc is its record). Beyond ~10, compact the oldest the same way. Do not let this tier grow unbounded.
- **Rejected / superseded — keep FOREVER, one line each.** These are the anti-re-propose memory: a future session must see "we already considered X and dropped it because Y." They are cheap at one line and never expire.

- **[YYYY-MM-DD]** — [decision]. **Why:** [rationale]. (see `changes-[stamp].md`)
- **[YYYY-MM-DD]** — [REJECTED] [idea]. **Why not:** [rationale].
- **[YYYY-MM-DD]** — [SUPERSEDED by YYYY-MM-DD] [old decision]. **What changed:** [one clause].

## Pointers (not duplicated here)
- **Build ledger:** see change logs `changes-*.md` in this folder — what was actually deployed, per session.
- **Latest build order:** see most recent `demo-spec-*.md`.
- **Outstanding SE-manual work:** see the most recent change log's "SE Must Do" / handover brief.
- **Deep history:** the change logs are the archive — older decisions compacted out of the log above are recoverable there.
```

## Create Rules (Stage 6 — new / reuse-org sessions)

Write the doc for the FIRST time when a new or reuse-org session produces a spec and no `demo-architecture.md` exists yet. Populate:
- **Customer Context & Value Spine** — from the spec's Customer Context + Value Spine (already gathered this session).
- **Demo Flow / Narrative Arc** — draft from the scenario's business story + the demo beats discussed this session.
- **Decision Log** — seed with this session's material decisions (see "Auto-draft decision entries" below).
- Stamp `Last reconciled: [now]`, `Reconciled through: none — created from discovery`.

## Reconcile Rules (Stage 3i — iteration sessions)

This runs at iteration bootstrap, BEFORE the Stage 3i questions. Two cases.

**Read cap (applies to BOTH cases — the balloon backstop):** change logs are read newest-first and CAPPED. Read at most the **5 most recent** relevant change logs in FULL. For any older change log still in scope, read ONLY its handover-brief / "SE Must Do" tail (the last section), not the whole ledger — the doc already reflects the rest, and full bodies are what front-loaded context on large demos. If you truncate, note it to the SE ("folded in the last 5 change logs in full; older ones by their handover tails"). NEVER read "all" change logs in full.

**Case A — arch doc exists.** Reconcile it to current reality:
1. Read `demo-architecture.md`. Note its `Last reconciled` timestamp and `Reconciled through` filename.
2. List `changes-*.md` in the folder. Identify every change log NEWER than `Reconciled through` (by the filename's date-time stamp), newest-first. Apply the read cap above: last 5 in full, older-but-in-scope by handover tail only. Extract: what was deployed/changed, any `REGRESSED` / `Open Questions` / live-Builder-work notes, decisions implied.
3. **Opportunistic audit diff (only if `AUDIT_MODE = background-fresh` this session):** when a fresh audit ran, compare its ★ surface (agents, custom objects, key fields) against what the arch doc's flow/decisions reference. Surface anything in the org the doc does not mention as a recognition prompt ("the org has [X] I have no record of — what happened?"). If no fresh audit ran this session, SKIP this step silently — do NOT trigger an audit for reconciliation.
4. Draft the updated doc, COMPACTING as you go (this is the balloon fix, not optional):
   - Rewrite the Narrative Arc to current state — folding in the outcomes of resolved decisions so the arc, not the log, carries them.
   - Decision Log: add this session's new accepted decisions at top; then DROP any older accepted entry whose outcome now lives in the arc, and trim the accepted tier to ~10. Keep ALL rejected/superseded one-liners.
   - Carry the Value Spine forward (edit only if genuinely changed).
   - Do NOT create or grow a header narrative banner. If the prior doc has one (legacy), delete it — its content belongs in the arc.
   - Check the whole-doc budget (~350 lines / ~5k tokens). If over, compact harder before presenting.
5. Present the drafted reconciliation to the SE as ONE message and wait:
   > "Here's the [Customer] demo as I have it recorded:
   > **Flow:** [current narrative arc, condensed to beats]
   > **Key decisions:** [last 2-3 decision-log entries]
   >
   > Since I last reconciled ([date]), I folded in [N] change log(s): [1-line each]. [If capped: "(last 5 in full, [M] older by handover tail.)"] [If audit diff ran and found deltas: "The fresh audit also shows [X] I didn't have recorded."]
   >
   > **Anything change in the org since [date] that isn't in a change log?** (a live tweak, a fix, seed edits — only if it's not already above). Then confirm this picture or correct it."
6. On SE confirm/correct: write the reconciled (compacted) doc, stamp `Last reconciled: [now]` and `Reconciled through: [newest change log folded in]`. THEN proceed to the Stage 3i questions — which now build on a confirmed shared picture instead of a cold interview.

**Case B — no arch doc, but prior specs/change logs exist (backfill an in-flight demo).** Synthesize one:
1. Read the most recent `demo-spec-*.md` (for Customer Context + Value Spine + scenario). For change logs, apply the read cap: the last 5 `changes-*.md` in full + the handover tails of any older ones — NOT every historical change log, and NOT every historical spec (older specs are superseded snapshots).
2. Draft a full `demo-architecture.md` from that history, ALREADY COMPACTED to the budget: infer the Narrative Arc from the latest spec's scenario + the change logs' deployed features; seed the Decision Log from material forks visible in the change logs (net-new vs upgrade, regressions, dropped features) — accepted tier ≤10, all rejected/superseded as one-liners. Do not reproduce change-log detail; cite it.
3. Present it for confirm/edit with the same message shape as Case A step 5 (adjust the lead-in: "I don't have a living architecture doc for [Customer] yet, so I synthesized one from your latest spec and [M] change logs — confirm or correct, and it becomes the running record.").
4. On confirm: write the doc, stamp `Last reconciled: [now]`, `Reconciled through: [newest change log]`. Proceed to Stage 3i questions.

## Auto-draft decision entries (Stage 6, all authoring paths — SE-gated)

When (re)writing the doc at Stage 6, draft new Decision Log entries from THIS session's material decisions, then show them to the SE for confirm/edit before writing (never silent auto-write). Draw from:
- The Stage 5 cut-gate answer (what the SE would cut / what's load-bearing → a decision about scope).
- Scenario forks (net-new vs modify-existing agent; existing-first vs new object).
- Features proposed and dropped (→ a [REJECTED] entry so they're not re-proposed).
Keep each entry to the template's ONE-line + **Why:** shape (a second line means it belongs in the change log). If nothing material was decided this session, add no entry — do not manufacture one.
