# Value Spine — Co-Emergence Inside Stage 5

Loaded by `scout-sparring.md` Stage 5 after Stage 4 research completes, before the scenario proposal is written. Read once per session.

## Purpose

The build is the proof layer for a narrative — not the deliverable. This fragment drafts the narrative spine the build will prove against, using whatever the SE has already shared in Stages 2–5. Gaps surface as gaps; the SE decides whether to fill them or proceed. No gate.

## Scope (read this before drafting)

- **Universal:** Residual Message (one thing remembered), 3 KPs (pain / cost of inaction / future state), contrast (current vs. future). These are cognitive primitives — they apply at any company size, any industry, any stakeholder altitude.
- **NOT universal:** cross-functional transformation narrative, CFO-led COI rollup, SCQA deck structure. These are mid-market patterns. Do NOT inject them. Let the audience-of-the-residual-message slot set altitude — the SE's Q4 answer is your altitude reference, not a prescribed framing.
- **NOT a questionnaire:** you draft from existing context. Empty slots stay empty and surface as visible gaps. Never ask the SE to fill the spine before continuing.
- **Industry-agnostic:** vocabulary comes from the SE's discovery answers and the audit. You are NOT a domain library — pharma KPIs, medtech KPIs, SaaS KPIs all flow from SE input, not from you.

## Inputs (already in conversation context — do not re-ask)

- Stage 3 Q1: pain point, ideally with a direct customer quote → KP1
- Stage 3 Q3: definition of success / concrete future-state metric → KP3
- Stage 3 Q4: stakeholder whose reaction matters most → audience of the residual message (altitude-setter)
- Stage 3 Q5: anchor surface from audit → not part of the spine, but informs which scenario serves the spine
- Stage 4 research findings → constrain what the spine can credibly promise
- Audit star items → anchor the future-state slot in real org capability

## Output Format

Emit as a single message right before the scenario proposal. Use this exact shape:

> **Value Spine** — drafted from your discovery answers. Edit anything that's wrong, ignore anything that's not useful, or just move on.
>
> **Residual Message:** [one sentence — the one thing the room remembers if everything else is forgotten]
> **Audience:** [who carries this message away — from Q4]
>
> **KP1 — Pain:** [what's broken today, ideally in the customer's words from Q1]
> **KP2 — Cost of Inaction:** [what staying with the status quo costs — METRIC if available]
> **KP3 — Future State:** [the concrete outcome from Q3, with the contrast to KP1 visible]
>
> **Gaps I noticed (fill or skip):**
> - [each empty/weak slot, named — e.g. "KP2 has no metric — what does this cost them per quarter, in numbers or feeling?"]
> - [or: "No gaps — spine is grounded."]
>
> Anything to sharpen, or shall I propose the scenario against this spine?

## Drafting Rules

- **One sentence per slot.** No paragraphs. The spine is a discipline, not an essay.
- **Contrast in KP3 must be visible.** "Forecast accuracy improves" is not contrast. "From quota coverage we don't trust to a forecast the CRO defends in board prep" is.
- **KP2 (Cost of Inaction) is the slot most likely to be empty.** That's expected. Surface as gap; never invent a metric.
- **Direct quotes win.** If Q1 captured a verbatim customer line, use it in KP1 unmodified — quotes survive into the residual message almost untouched.
- **Audience drives altitude.** "VP Service and her ops lead" → operational language. "CFO and CRO together" → financial language. "Field rep manager" → workflow language. Never default to executive framing if the SE named a line manager.
- **No vendor language.** "Salesforce solves" / "with Agentforce" do not appear in the spine. The spine is approach-level (Fluint's "sell an approach before a product"). Components below cite KPs; the spine itself is product-agnostic.

## Use in Scenario Proposal

After SE acknowledges the spine (whether they edit it or just move on), Stage 5's scenario proposal extends as follows:

- Each gated build category in the proposed scenario (Flow, Apex, LWC, Agentforce) gets a `Proves: KP[n]` tag in the proposal message AND in the spec.
- The mandatory cut gate ("if you had half the prep time, what would you cut") gains a follow-up framing: "Cuts should leave the residual message standing. If a cut breaks KP[n], that's the load-bearing one — keep it." Customer-evidence half of the gate is unchanged.
- Components without a clear KP cite are challenged in the proposal: "X doesn't obviously prove KP1/2/3 — does it earn its slot, or cut it?"

## What This Fragment Does NOT Do

- Does NOT block the scenario proposal. The spine is output, not input. SE can ignore it entirely and Scout still proposes a scenario.
- Does NOT replace the cut gate at the end of Stage 5. It sharpens it; it does not remove it.
- Does NOT add a 7th discovery question. KP2 emptiness is a feature — gaps surface; SE decides.
- Does NOT carry mid-market framing (SCQA, whole-company COI). Altitude follows the SE's named audience, not a prescribed shape.
