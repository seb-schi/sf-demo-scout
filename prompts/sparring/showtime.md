# Showtime — Live Customer Conversation Sparring

Loaded on demand by `scout-sparring.md` when the SE selects the Showtime path at Stage 1. Returns to the main command for spec generation.

## When This Runs

The SE is in a live customer conversation. Showtime is fired up when the customer sits down — the audit runs in parallel with the SE's opening discovery (~5–10min, the discovery should take at least as long). The SE has a transcript ready to paste shortly after the audit completes. Time budget from transcript paste to spec: ≤5 minutes of Scout work; the customer-facing Slack canvas write that follows takes another ~1–2 minutes during which the SE narrates the Headless 360 / Docs MCP angle to the customer.

The format is a continuous engaged experience: audit runs while SE does opening discovery → transcript paste → one-pass proposal → SE/customer feedback → spec finalised → customer-facing Slack canvas written → /scout-building deploys the PoC slice while SE walks the customer through the broader canvas → working slice reviewed together when build completes.

## Premise

- The transcript replaces the 6-question discovery round.
- The spec captures the customer's **full** ask as a holistic build plan in the Scenario section. The PoC slice that /scout-building actually deploys is bounded by `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/showtime-scope-envelopes.md`. Out-of-envelope items are logged in the spec's Showtime PoC → Deferred list, not deployed.
- The customer takeaway: "Salesforce + Agentforce can do all of this — and here's a working slice to prove it." Scout does not narrow the customer's ambition; it only narrows what gets deployed today.
- The value spine survives, but is auto-drafted silently and emitted inline with the proposal. No SE-acknowledgement round, no gaps-as-questions.
- One iteration round only. After SE confirms or sharpens, Scout writes the spec — no further loops.

## Step S1 — Run Fresh Audit

Showtime always runs a fresh audit. A stale audit risks customer-facing deploy failures, which is the worst possible outcome of this format. The SE was warned at Stage 1: ideal pattern is to fire up Showtime when the customer sits down, so the audit runs in parallel with the SE's opening discovery questions. Audit takes ~5–10min via 3 parallel Sonnet sub-agents; opening discovery should take at least that long.

Read `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/audit-orchestration.md` and execute **Phase A only** — sync setup through launching the prelude sub-agent in the background. Phase A returns control here; the audit then runs in the background (Phase B launches the 3 parallel sub-agents on the prelude's push completion) while the SE does opening discovery with the customer and prepares the transcript. Opus never reads raw metadata payloads. The audit-orchestration procedure already emitted the live-status note pointing at `.audit-progress.log` in its step 5a.

This is exactly the intended Showtime shape — the audit overlaps the SE's opening discovery instead of blocking it. Because the audit now runs silently in the background, you MAY prompt for the transcript right away (S2): one pending ask (transcript) + one silent background op (audit) is the resolvable case — not the two-simultaneous-asks confusion the 2026-05-11 rule guards against. The transcript paste is the join: when the SE says `go`, pull the audit to completion (Phase C) before extracting.

Proceed to S2.

## Step S2 — Transcript Paste

Emit this right after S1 returns from Phase A — the audit is running in the background; do not wait for it. Emit:

> "Audit running in the background — live status → [.audit-progress.log]([ORG_FOLDER]/.audit-progress.log). Do your opening discovery with the customer; it'll finish while you talk.
>
> When you're done with discovery, paste the customer transcript here. Multiple chunks fine — say `go` when done.
>
> Tip: if you don't have a transcript, paste your own notes from the conversation. Scout works on whatever signal you give it."

Wait. Concatenate chunks until SE says `go` (or equivalent: "done", "that's it", "ready"). Do not start extraction until the SE signals end.

**On `go` — the audit join.** Before extraction, invoke audit-orchestration **Phase C**: ensure all 3 parallel sub-agents have completed (await any still in flight; if the SE said `go` very fast and the audit is still mid-prelude, await the prelude, let Phase B fire, then await the parallel agents), then run Post-Return Processing, Spot-Check, Consolidation, Notable Gaps, and Cleanup to produce the consolidated summary + audit file. Extract star-flagged items (default app, active layouts, relevant custom objects). If the audit completed long before `go`, Phase C collection is instant. Then proceed to S3.

## Step S3 — Auto-Extract (silent)

From the transcript, extract — do NOT emit yet:

- **Pain (KP1):** the customer's most-loaded statement, ideally a direct quote
- **Cost of Inaction (KP2):** what staying with the status quo costs them — only if the transcript contains it; otherwise leave empty (gap)
- **Future State (KP3):** the concrete outcome the customer named, with visible contrast to KP1
- **Audience:** which stakeholder's reaction matters most — usually the one who spoke most or whose decision unblocks the others
- **Residual Message:** one sentence the room remembers

Read `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/value-story.md` Drafting Rules for the spine constraints (one sentence per slot, contrast in KP3 must be visible, no vendor language, audience drives altitude). Do NOT execute its Output Format — Showtime emits the spine inline with scenarios in S4, not as a standalone message.

## Step S3.5 — Knowledge cartridge consult (silent unless matched)

Read `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/knowledge-cartridge.md` and execute it against the fresh audit's detected industry signals (Demo Surface Notes namespaces/objects from S1). Showtime has no platform-research pass, so run the consult standalone here — its Step 4 docs cross-check is best-effort: only cross-check if a Docs MCP call is cheap, otherwise note the match is audit-signal-grounded and proceed (Showtime is time-boxed; do not open a research budget). On a match, fold the cartridge's traps/recipes/regulatory framing into the S4 Holistic Proposal and the PoC envelope reasoning. Silent on no match, exactly as in Stage 4.

## Step S4 — Holistic Proposal + PoC Envelope Choice

Read `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/showtime-scope-envelopes.md`. Then synthesize from transcript signal + audit star items:

1. **Holistic Scenario** — what would deploy the customer's full wish, end-to-end. Name Salesforce / Agentforce / Headless 360 / Data Cloud / Flows / Apex / LWC components where each is the right answer. This is the architecture proposal the SE walks the customer through narratively.
2. **Audit-grounded subset** — which parts of the holistic scenario map to objects/apps/layouts the audit star-flagged. Anything that requires creating new objects, modifying profiles, or touching managed metadata is automatically out-of-envelope.
3. **PoC envelope choice** — pick the single envelope (or stacked pair per Stacking Rules) from the audit-grounded subset that proves the most valuable moment from the spine. The envelope file's Forbidden lists are hard — do not propose anything they exclude.

Emit a single message:

> **Showtime — proposal for [Customer], grounded in your conversation.**
>
> **Spine** (drafted from your transcript):
> - **Residual Message:** [...]
> - **Audience:** [...]
> - **KP1 — Pain:** [direct quote if available]
> - **KP2 — Cost of Inaction:** [or "gap — not in transcript"]
> - **KP3 — Future State:** [contrast visible]
>
> ---
>
> **Holistic Scenario — [name]**
> [3–5 lines: what deploys the customer's full ask end-to-end across Salesforce + Agentforce + Headless 360 / Data Cloud / Flows / Apex / LWC as relevant. Be honest about ambition; the spec captures all of it.]
>
> ---
>
> **Showtime PoC — [envelope code(s)]**
> Proves: KP[n] (and optionally KP[n] if a stack)
> Build: [one-line — exactly what /scout-building deploys today]
> Audit fit: [which star-flagged items it builds onto]
> Est. deploy time: [4–18min depending on envelope]
> [If stacking E1+E2 or E1+E5: name the scope reduction applied to keep combined scope down — e.g. "1–2 fields instead of 5; 1 flow with 2 actions instead of 1 flow + QuickAction"]
>
> **Deferred to follow-up sparring** (logged in spec, not deployed today):
> - [holistic-scenario item] — [reason: out of envelope / requires Data Cloud / requires custom Apex / requires Setup-UI step / etc.]
> - [...]
>
> Confirm or sharpen — single message?

If the transcript signal points outside every envelope (e.g. customer wants only multi-agent orchestration, or only Data Cloud setup), refuse cleanly: "Nothing in your transcript maps to a Showtime PoC envelope. The full ask is solid for `/scout-sparring → New` after the demo, but I can't deploy a slice today that's worth showing." Do not invent a weak PoC just to have something to deploy.

## Step S5 — One Iteration Round

Wait for SE reply. Three valid replies:
- **Confirm** (no edits): proceed to S6 with the proposed Holistic Scenario + PoC envelope choice.
- **Sharpen** ("yes but use Account instead of Lead", "swap E2 for E1+E5", "move item X from Deferred into the PoC"): apply edits.
  - If the edit keeps the PoC inside the same envelope (or a valid stack), apply and proceed to S6.
  - If the edit pushes the PoC outside its envelope, refuse: "That pushes us past the Showtime envelope — it'd need [reason]. I'll keep the PoC on-envelope and add your edit to the spec's Deferred list. Re-open with `/scout-sparring → Iteration` after the demo to build it." Apply the rest of the edits and proceed to S6.
  - Holistic Scenario edits (changes to ambition, not to the PoC) are always accepted — that's the spec's job.
- **Reject the framing** ("propose something completely different"): refuse: "Showtime only proposes inside the scope envelopes. The proposal above is the closest fit to your transcript. If it doesn't work, switch to `/scout-sparring → New` for a full sparring flow."

Do NOT loop further. One iteration, then spec.

## Step S6 — Data Shape Validation (conditional)

If the chosen scenario includes Apex, Flow, or Agentforce that queries or writes objects: read `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/data-shape.md` and execute. If pure config (fields, layouts, custom labels, seed only): skip.

## Step S7 — Spec Generation

Read `${CLAUDE_PLUGIN_ROOT}/prompts/spec-template.md` and write the spec to `[ORG_FOLDER]/demo-spec-[YYYY-MM-DD]-[HHmm]-[CUSTOMER].md`.

Mark the spec header with `Sparring mode: Showtime` so /scout-building knows the provenance — useful for retros.

**Showtime-specific spec content** (insert in the order shown):

- **Scenario section** carries the **Holistic Scenario** as the Business story / Core capability / Pain point / Build required (Claude Code) / Build required (SE manual) / Demo risk fields. Be honest about ambition — name everything across Salesforce + Agentforce + Headless 360 + Data Cloud + Flows + Apex + LWC. This is what the SE walks the customer through narratively.
- **Insert a new `## Showtime PoC` section after the Scenario section** (Showtime-only — not in spec-template.md). Format:

  ```markdown
  ## Showtime PoC
  Envelope: [E1 / E2 / E3 / E4 / E5 / stack code]
  Proves from spine: KP[n] (+ optionally KP[n])

  ### In PoC (deploys today via /scout-building)
  - [item from Holistic Scenario]
  - [...]

  ### Deferred (logged here, not deployed today)
  - [item from Holistic Scenario] — out-of-envelope reason: [envelope cap / Data Cloud / custom Apex backing / multi-agent / Setup-UI step / etc.]
  - [...]

  To realize the full Holistic Scenario, re-open this spec with `/scout-sparring → Iteration` after the demo.
  ```

- **`## Claude Code Instructions` carries the PoC slice ONLY.** /scout-building deploys this section. The Holistic Scenario items not in the PoC must NOT appear in Claude Code Instructions — they live in the Showtime PoC → Deferred list above and nowhere else.

Skip the "Propose Lessons" step in main command Stage 6 — Showtime is too compressed for reliable lesson extraction. Lessons accumulate from regular sparring sessions.

## Step S7.5 — Customer-Facing Slack Canvas

This is the customer-facing artifact of Showtime. While Scout writes it (~1–2min), the SE narrates to the customer how Headless 360's Docs MCP integration lets Scout reason over the live Salesforce documentation surface to plan the build — turning the canvas write itself into a demo moment.

Probe Slack MCP availability first:

```bash
claude mcp list 2>/dev/null | grep -qE '^slack:.*Connected' && echo OK || echo MISSING
```

- On `MISSING`: skip silently to S8 with a one-line note in the Done message that Slack canvas was unavailable.
- On `OK`: proceed.

Emit a single line first so the SE has the cue: *"Writing the customer-facing canvas now — talk the customer through Headless 360 + Docs MCP while this lands."*

Call `mcp__slack__slack_create_canvas`:
- `title`: `Showtime Build Plan — [Customer] — [YYYY-MM-DD]`
- `content`: Canvas-flavored Markdown structured as below. The canvas is the customer's takeaway document — write it for the customer to read, not for the SE to refine.

Canvas content template (clean + confident, light emojis on section headers, capability summary table up top, compact Powered-by lines, ✅ checklist for the PoC):

```markdown
# 🎯 [Customer] — Showtime Build Plan
*Generated [YYYY-MM-DD] from your conversation with [list SE-side names from transcript or "the [Customer] team"].*

> **The connecting moment:** [one-sentence residual message from the spine — this is the line the room remembers]

## 👂 What we heard

[2–3 short paragraphs synthesizing the customer's full ask. Use direct quotes from the transcript where they're vivid — pull-quote them on their own line with `>`. This is the document acknowledging that Scout heard everything — so the customer reads it and recognizes their own conversation. Aim for punchy sentence rhythm, not a wall of text.]

## 🏗️ What we'd build (full plan)

| Area | What changes for you | Powered by |
|---|---|---|
| [Capability 1] | [one-line customer-language outcome] | [SF/Agentforce/etc. components, comma-separated, abbreviated] |
| [Capability 2] | [...] | [...] |
| [...] | [...] | [...] |

---

### [emoji] [Capability area 1 — e.g. "Service Vision — Voice agent with human handoff"]

**What it does for you:** [customer-language outcome — 2–3 sentences max, punchy]

**How Salesforce delivers it:** [Salesforce + Agentforce + Headless 360 + Data Cloud + Flows + Apex + LWC components, named where each is the right answer — single paragraph, not bullets]

**Docs:** [link 1] · [link 2] · [link 3]
*(use full Help URLs from Stage 4 Platform Research; separate with middle-dot, keep on one line per capability)*

### [emoji] [Capability area 2]

[same shape]

[...repeat for each major area of the holistic scenario...]

*Suggested emoji palette (pick what fits — keep it sparse, one per area):* 📞 voice/contact center · 🔧 service/repair · 📊 analytics · 🤝 partner/portal · 💬 messaging · 🧠 AI/agent · 🛒 commerce · 📈 sales · 🩺 healthcare · 🔐 identity/SSO

## ⚡ What we're proving today (Showtime PoC)

Scout will deploy this slice to your demo org in the next 5–15 minutes:

- ✅ [item from PoC envelope, in customer language — bold the noun the room remembers]
- ✅ [...]

> **Why this slice:** [one or two sentences on why this is the right proof — usually because it lands the spine's residual message in a contained build. Punchy.]

## 🚀 What's next

Everything above that's not in today's slice is captured for follow-up — Scout can deploy any of it in a follow-up session against this same org:

- **[Item name in customer language]** — [one-line follow-up framing: separate Iteration / separate engagement / specialist handoff, with the human-readable reason]
- **[...]** — [...]

---

*Generated by Headless 360 — Salesforce's CLI-and-MCP-native AI surface — reasoning over the live Salesforce documentation library and your demo org's current configuration. Today's deploy proves the round-trip: **discover → plan → deploy**, in one session.*
```

Authoring guidance for Opus when filling this template:
- The summary table is the skim layer — every capability gets exactly one row, "Powered by" stays comma-separated and short (e.g. "Agentforce Service Assistant, Service Cloud Voice, Knowledge"), no full URLs in the table.
- Per-capability sections are the read layer — "What it does for you" is the only place to be a bit punchy/quippy. "How Salesforce delivers it" stays factual.
- Pull-quotes (`> "..."`) for direct customer quotes only — don't fabricate them. If the transcript has none, drop the pull-quote line.
- Emoji discipline: one per capability section header, no emoji inside body copy. Section headers (`## What we heard` etc.) get the fixed emojis shown in the template; capability subsections get one chosen from the palette.
- "What's next" follow-ups are bolded at the front (the noun) so the customer can scan; the framing reason follows after an em dash.

Capture the canvas URL from the response. Hold it for emission in S8.

On any canvas-create error: surface one inline line *"Canvas write failed: [reason]. Spec is still on disk; SE can present from the spec directly."* Hold the absence of a canvas URL for S8.

## Step S8 — Done

Emit (substitute `[CANVAS_URL]` with the URL captured in S7.5; if canvas write was unavailable or failed, emit the alternate variant below):

**Canvas-available variant:**

> "Spec saved. Customer-facing canvas live: [CANVAS_URL]
>
> **Now: open a fresh Claude Code window** and run `/scout-building` to deploy the PoC slice. Hand over the spec at `[ORG_FOLDER]/demo-spec-[YYYY-MM-DD]-[HHmm]-[CUSTOMER].md`.
>
> While /scout-building deploys (~5–15min depending on envelope), walk the customer through the full Slack canvas — they're seeing the architecture for everything they asked for, not just what's about to land in the org. When the build completes, review the working slice together. The continuous experience is the format."

**Canvas-unavailable variant** (if S7.5 skipped or errored):

> "Spec saved at `[ORG_FOLDER]/demo-spec-[YYYY-MM-DD]-[HHmm]-[CUSTOMER].md`. Slack canvas unavailable — present from the spec directly.
>
> **Open a fresh Claude Code window** and run `/scout-building` to deploy the PoC slice. While it deploys, walk the customer through the spec's Holistic Scenario + Showtime PoC sections."

Return to main command (which exits cleanly since spec is on disk).

## What Showtime Does NOT Do

- Does NOT deploy outside the scope envelopes. Out-of-envelope items go in the Deferred list, not the build.
- Does NOT narrow the customer's ambition. The Holistic Scenario captures everything; the PoC is just the slice that deploys today.
- Does NOT run a value-spine acknowledgement gate (auto-drafted, emitted inline).
- Does NOT run the cut gate from Stage 5 (scope is already minimal by construction).
- Does NOT support iteration intent within Showtime (single-shot session — re-open with `/scout-sparring → Iteration` after the demo for follow-up).
- Does NOT do Slack lookup, broad doc research, or platform pre-flight beyond what the audit already captured. (Exception: the knowledge-cartridge consult runs proactively at S3.5 if a conforming cartridge matches — knowledge, not a build offer.)
- Does NOT propose a weak PoC just to have something to deploy. If the transcript signal points entirely outside the envelopes, refuse cleanly and route to `/scout-sparring → New` post-demo.
