# Iteration Path — Discovery & Definition

Loaded on demand when intent = iteration. Returns to the main command for Stage 4+.

## Stage 3i: Iteration Discovery

Review the most recent audit, prior specs, and change logs for this org. Understand what's already built before asking anything.

Ask these three questions in a single message:
1. **What are you changing — adding, refining, or fixing something that's broken?** Be specific — "add an Agentforce agent for case triage," "tighten the discovery flow's exit criteria," or "the agent's flow action errors on preview, fix it." Name the artifact and the change.
2. **Why now?** Customer feedback, new stakeholder, demo gap, competitive pressure, post-deploy bug — what's driving this?
3. **Which part of the existing demo does this connect to?** Where in the demo flow does this appear?

**Stop and wait for answers.**

If the SE's answers are vague ("just add an agent" / "because I want one" / "it's standalone"), push back: "Which customer moment does this serve? If you can't name the moment, it'll feel bolted-on in the demo."

### Symptom Follow-up (fix intent only)

If Q1 named a symptom — error message, broken preview, failed deployment, runtime exception — ask one targeted follow-up before the Delta Conflict Check:

> "To research the right way: paste the **exact error text** (copy from the UI / debug log), and tell me **when it fires** (preview, runtime, deploy, on a specific user action). If the error code is generic, the reproduction step is what makes it tractable."

Capture the verbatim error and trigger context. Carry both into Stage 4 — when platform-research runs, it MUST issue at least one Docs MCP search keyed on the verbatim error code or message text, in addition to the standard object/capability research.

No symptom in Q1 → skip the follow-up, proceed directly to Delta Conflict Check.

### Delta Conflict Check

After the SE answers, review the existing audit and any prior specs/change logs against the proposed change:
- **Conflicts:** existing flows on the same object, field name collisions, layout crowding, permission set overlaps
- **Quality evaluation:** does the existing setup make sense as a foundation? If not, say so:
  > "Before we add [proposed change] — I reviewed the current org state. [Problem]. Adding this on top will [consequence]. Want to address that first, or proceed anyway?"
- **UI-built Agentforce agent — net-new-vs-re-author fork (hard gate).** If the change adds or moves a topic/action on an Agentforce agent that the audit ★-flagged as UI-built (planner did not retrieve via Metadata API), do NOT plan to hand-edit it. That agent can't be safely edited as metadata. Both real paths end in clean, editable Agent Script — the question is only whether you're reusing the legacy agent's wiring. Present the SE the fork BEFORE speccing and stop for the answer:
  > "The audit flags **[agent]** as a UI-built agent — its planner can't be retrieved via Metadata API, so Scout can't edit it safely as metadata. Either way we end up with clean, editable Agent Script; the question is whether your change reuses this agent's existing topics/voice/knowledge — or is largely self-contained.
  > - **Self-contained scenario →** I'd build a **net-new Agent-Script agent**. Scout's strong lane — editable source from day one — and we leave the legacy agent untouched.
  > - **Builds on the existing agent's wiring →** then at build time you'll **flip the in-place upgrade in Agent Builder** (reversible — the old version stays Active until you activate the new one), which makes the agent machine-readable. Scout then **re-authors it as fresh Agent Script under a side-by-side name (`[agent]_Scout`)** — reproducing its topics/actions and adding your new capability on top. The original stays intact so you can compare them before retiring it. This replaces the old hand-remediation cascade — but note re-author fidelity isn't machine-proven yet, so plan to diff the re-authored agent against the legacy one (or its demo script) before demo day. On a managed, packaged, or template-derived agent, confirm the upgrade is reversible (or test in a sandbox) first.
  >
  > Which fits — self-contained (net-new), or builds-on-existing (upgrade-then-re-author)?"

  Carry the SE's choice into the spec. For builds-on-existing, note in the spec that the agent is UI-built and the re-author flow applies — building's editability pre-flight runs the SE upgrade gate and routes to re-author mode. If text-only (no new/moved topic or action), this gate does not apply — building's editability pre-flight is the authoritative backstop.

Only surface genuine concerns — don't re-litigate prior decisions that are working fine.

Then proceed to Stage 4 (Platform & Data Model Research).

---

## Stage 5i: Iteration Definition

Propose the change: what gets built, what exists, what conflicts, what the SE does manually.

Apply the same **existing-first evaluation** as Stage 5 — even a single new component should prefer extending existing metadata. Ground data model choices in Stage 4 research.

**ONE GATE — send as a standalone message, then stop:**

> "Walk me through the demo moment where this appears. What happens right before, and what does the customer see right after?"

This forces integration thinking. If the SE can't place the change in a demo flow: "If you can't describe what comes before and after, this change doesn't have a home in the demo yet. Let's figure out where it fits first."

Once the gate is cleared, proceed to Stage 5b.
