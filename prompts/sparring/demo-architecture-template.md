# Demo Architecture — Output Format & Reconciliation Rules

One living doc per org: `[ORG_FOLDER]/demo-architecture.md` (no timestamp — it is the single cumulative record, rewritten in place, NOT a per-session snapshot). This is the counterpart to the timestamped `demo-spec-*.md` files: a spec is a point-in-time build order; this doc is the demo as it stands now.

**Authored by sparring only.** `/scout-building` never writes it. It captures the synthesis ACROSS specs and change logs — it does NOT duplicate the per-session spec's build instructions, and it does NOT duplicate the change logs' build ledger (what objects/fields/flows were deployed). If you are tempted to list deployed metadata here, stop — point at the change log instead.

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
The end-to-end story as it stands NOW — the scenes/beats in order, what the customer sees. This is the "overall flow" a fresh session needs to understand the demo without reading five specs. Rewrite to reflect the current state each reconciliation; this section is present-tense, not append-only.
1. **[Beat name]** — [what happens, what the audience sees, which KP it proves]
2. …

## Decision Log
Append-only. Newest at top. Every entry is a decision + its rationale, so it is never re-litigated. INCLUDE superseded / rejected ideas (mark them) — the point is that a future session sees "we already considered X and dropped it because Y."
- **[YYYY-MM-DD]** — [decision]. **Why:** [rationale]. [If it supersedes an earlier entry: "Supersedes [date] — [what changed]."]
- **[YYYY-MM-DD]** — [REJECTED] [idea]. **Why not:** [rationale].

## Pointers (not duplicated here)
- **Build ledger:** see change logs `changes-*.md` in this folder — what was actually deployed, per session.
- **Latest build order:** see most recent `demo-spec-*.md`.
- **Outstanding SE-manual work:** see the most recent change log's "SE Must Do" / handover brief.
```

## Create Rules (Stage 6 — new / reuse-org sessions)

Write the doc for the FIRST time when a new or reuse-org session produces a spec and no `demo-architecture.md` exists yet. Populate:
- **Customer Context & Value Spine** — from the spec's Customer Context + Value Spine (already gathered this session).
- **Demo Flow / Narrative Arc** — draft from the scenario's business story + the demo beats discussed this session.
- **Decision Log** — seed with this session's material decisions (see "Auto-draft decision entries" below).
- Stamp `Last reconciled: [now]`, `Reconciled through: none — created from discovery`.

## Reconcile Rules (Stage 3i — iteration sessions)

This runs at iteration bootstrap, BEFORE the Stage 3i questions. Two cases:

**Case A — arch doc exists.** Reconcile it to current reality:
1. Read `demo-architecture.md`. Note its `Last reconciled` timestamp and `Reconciled through` filename.
2. List `changes-*.md` in the folder. Identify every change log NEWER than `Reconciled through` (by the filename's date-time stamp). Read only those (not the whole history — the doc already reflects the rest). Extract: what was deployed/changed, any `REGRESSED` / `Open Questions` / live-Builder-work notes, decisions implied.
3. **Opportunistic audit diff (only if `AUDIT_MODE = background-fresh` this session):** when a fresh audit ran, compare its ★ surface (agents, custom objects, key fields) against what the arch doc's flow/decisions reference. Surface anything in the org the doc does not mention as a recognition prompt ("the org has [X] I have no record of — what happened?"). If no fresh audit ran this session, SKIP this step silently — do NOT trigger an audit for reconciliation.
4. Draft the updated doc: refresh the Narrative Arc to current state, append new Decision Log entries, carry the Value Spine forward (edit only if genuinely changed).
5. Present the drafted reconciliation to the SE as ONE message and wait:
   > "Here's the [Customer] demo as I have it recorded:
   > **Flow:** [current narrative arc, condensed to beats]
   > **Key decisions:** [last 2-3 decision-log entries]
   >
   > Since I last reconciled ([date]), I folded in [N] change log(s): [1-line each]. [If audit diff ran and found deltas: "The fresh audit also shows [X] I didn't have recorded."]
   >
   > **Anything change in the org since [date] that isn't in a change log?** (a live tweak, a fix, seed edits — only if it's not already above). Then confirm this picture or correct it."
6. On SE confirm/correct: write the reconciled doc, stamp `Last reconciled: [now]` and `Reconciled through: [newest change log folded in]`. THEN proceed to the Stage 3i questions — which now build on a confirmed shared picture instead of a cold interview.

**Case B — no arch doc, but prior specs/change logs exist (backfill an in-flight demo).** Synthesize one:
1. Read the most recent `demo-spec-*.md` (for Customer Context + Value Spine + scenario) and ALL `changes-*.md` (for what's been built + decisions + open items). Do NOT read every historical spec — the latest spec plus the change-log sequence is enough; older specs are superseded snapshots.
2. Draft a full `demo-architecture.md` from that history. Infer the Narrative Arc from the latest spec's scenario + the change logs' deployed features. Seed the Decision Log from material forks visible in the change logs (e.g. "net-new agent vs upgrade," regressions, dropped features).
3. Present it for confirm/edit with the same message shape as Case A step 5 (adjust the lead-in: "I don't have a living architecture doc for [Customer] yet, so I synthesized one from your [N] specs and [M] change logs — confirm or correct, and it becomes the running record.").
4. On confirm: write the doc, stamp `Last reconciled: [now]`, `Reconciled through: [newest change log]`. Proceed to Stage 3i questions.

## Auto-draft decision entries (Stage 6, all authoring paths — SE-gated)

When (re)writing the doc at Stage 6, draft new Decision Log entries from THIS session's material decisions, then show them to the SE for confirm/edit before writing (never silent auto-write). Draw from:
- The Stage 5 cut-gate answer (what the SE would cut / what's load-bearing → a decision about scope).
- Scenario forks (net-new vs modify-existing agent; existing-first vs new object).
- Features proposed and dropped (→ a [REJECTED] entry so they're not re-proposed).
Keep each entry to the template's one-line + **Why:** shape. If nothing material was decided this session, add no entry — do not manufacture one.
