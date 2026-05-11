# Showtime Scope Envelopes

Hard scope limits for what Scout deploys during a Showtime session. Loaded by `sparring/showtime.md` Step S4. Maintained by hand via /project-sparring sessions.

The Showtime spec captures the customer's **full** wish list (holistic build plan in the Scenario section). The envelope below bounds only what /scout-building actually deploys today — the proof-of-concept slice. Everything else lives in the spec's Showtime PoC section as deferred-to-follow-up items, ready for `/scout-sparring → Iteration` to pick up later.

## How to Read This File

Each envelope is a hard scope ceiling, not a template. The SE's transcript and the org's audit determine the specific objects, fields, automations, and customer language. The envelope guarantees: "Scout can deploy this shape inside a Showtime timebox without unbounded smoke testing."

A Showtime PoC fits **one** envelope, with two narrow stacking exceptions (see Stacking Rules below). Anything outside the envelope is logged in the spec's Showtime PoC → Deferred list, not deployed.

---

## E1 — Fields + Layout

- **Build:** 1–5 custom fields on ONE audit-confirmed object + add to active layout + Companion permset
- **Forbidden:** flows, Apex, LWC, agents, object creation, profile or existing-permset modification
- **Why it's safe:** zero runtime code path; FLS is the only failure mode and the permset rules cover it

## E2 — Single Before-Save Record-Triggered Flow

- **Build:** ONE before-save record-triggered flow on ONE audit-confirmed object + FlowTest happy-path + permset
- **Forbidden:** after-save flows, screen flows, scheduled flows, platform-event flows, before-delete flows, subflows, Apex, multi-object, cross-object DML
- **Why this slice and not other flow types:** before-save runs inside the trigger transaction with no DML side effects, and FlowTest gives a pass/fail in seconds. Other flow types either need future-time triggers (scheduled), specific event objects (platform-event), DML risk (after-save), or visual QA (screen) — all of which break the Showtime timebox.

## E3 — Single Apex

- **Build:** ONE Apex trigger + ONE single-object service class + 1 smoke test method (≥75% coverage on the trigger handler) + permset
- **Forbidden:** flows, LWC, agents, multi-object DML, batch/queueable/schedulable, dynamic SOQL beyond a single bounded query

## E4 — Single Agentforce Agent (Standard Actions Only)

- **Build:** 1 agent (.agent file) + standard actions only + Companion permset + standard Agentforce runtime permset (auto-assigned by Phase 3) + 1–2 smoke utterances
- **Standard actions allowed:** Search Knowledge, Identify Record by Name, Get Record Details, Find Object by Name, Send Email, Create Record, Update Record (and other shipped Agent Script standard actions — no custom)
- **Forbidden:** no backing Apex actions, no backing autolaunched flows, no backing prompt templates, no Data Cloud grounding, no Knowledge grounding via Data Library, no multi-agent orchestration, no custom topics with custom actions
- **SE pre-stage required:**
  - Agent user license type matches intended agent type (Service Agent = Agentforce User license; Employee Agent = standard Salesforce license)
  - Channel assignment for the agent (Messaging / Experience Cloud / Embedded)
  - Knowledge article published if scenario references knowledge lookup
  - Agent user renamed for credibility ("Aria" / "Marcus" — not "Einstein Agent User")
- **Why standard actions only:** the Showtime "wow" comes from natural-language → action wiring, not from custom code behind it. Custom backing flows / Apex multiply the smoke-test surface from 1–2 utterances to 3–5 and turn deploy time into open-ended debugging.

## E5 — Data Shape Only

- **Build:** seed data via idempotent `--pilot-only` script for objects the audit confirms populated (or empty-but-existing) + permset only if new objects are touched (none should be in E5)
- **Forbidden:** any metadata creation (no fields, no flows, no Apex, no agents)

---

## Stacking Rules

A Showtime PoC fits **one envelope by default**. Two stacking exceptions are allowed when the customer's wish maps to two LOW-complexity moments and a single-envelope cut would feel arbitrary:

- **E1 + E2** (fields + before-save flow on the same object)
- **E1 + E5** (fields + data seeding into the new fields)

E3 and E4 are always single-envelope.

When stacking: Scout caps each envelope at the lower end of its range and **names the cut honestly to the SE in the iteration round.** If the customer's wish was already small (e.g., 2 existing fields to surface, 3 records to seed), say so explicitly — *"E1+E5 stack at minimum scope; nothing was cut because the wish was already inside the cap."* Don't claim a reduction that didn't happen. If the wish was maximalist, name what got cut: *"E1+E2 stack: cut from 4 fields to 2; cut the second flow action."* Examples of typical caps: E1+E2 → up to 2 fields, 1 flow with up to 2 actions; E1+E5 → up to 2 fields, seed only the records that exercise the new fields.

If the SE pushes for a third envelope or a stack that includes E3/E4, refuse: "That pushes us past the Showtime envelope. I'll log the full ask in the spec's Future Build list — re-open with `/scout-sparring → Iteration` after the demo to deploy it."

---

## Hard Rules Across All Envelopes

- Build only on objects, apps, and layouts the audit star-flagged. No object creation. No tab creation unless covered by a single object's Companion permset.
- No profile modification. No modification of existing permsets. New Companion permset is the only permission surface Scout writes.
- The existing Disqualified list (below) applies regardless of envelope choice.

---

## Disqualified — Never Proposed in Showtime

- **Multi-flow + multi-agent + Prompt Template scenarios** — too many moving parts for a Showtime timebox.
- **Matching Rules + Duplicate Rules via Metadata API** — platform limitation: no programmatic enum for fuzzy matching methods. UI-only, breaking Scout's end-to-end deploy guarantee.
- **Agentforce + Data Cloud vector indexing + Data Library setup** — requires tenant provisioning Scout cannot execute.
- **Anything requiring Setup-UI navigation as load-bearing demo step** — Showtime sells "Scout deployed it"; if the demo moment depends on a step Scout couldn't deploy, the format breaks.
- **Custom Agentforce actions (Apex / Flow / Prompt Template backed)** — covered by E4's "standard actions only" constraint; reiterated here for clarity.

---

## Refinement Triggers

Update this file when:
- A Showtime deploy fails inside an envelope's stated scope → tighten the envelope.
- A Showtime deploy succeeds with an item the envelope forbade → consider promoting after ≥2 confirming sessions across ≥2 SEs.
- A platform change broadens or narrows what's safe to deploy in a Showtime timebox.

Removing or relaxing an envelope requires a /project-sparring session — envelopes earn their place; loosening them is a deliberate decision.
