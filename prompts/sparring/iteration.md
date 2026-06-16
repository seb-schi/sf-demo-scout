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
- **UI-built Agentforce agent — net-new-vs-upgrade fork (hard gate).** If the change adds or moves a topic/action on an Agentforce agent that the audit ★-flagged as UI-built (planner did not retrieve via Metadata API), do NOT default to "upgrade." That agent can't be safely edited as metadata, and upgrading it is a remediation project, not a quick step. Present the SE the real fork BEFORE speccing, keyed on whether the change reuses the agent's existing wiring, and stop for the answer:
  > "The audit flags **[agent]** as a UI-built agent — its planner can't be retrieved via Metadata API, so Scout can't edit it safely as metadata. There are two real paths, and which is cheaper turns on one question: **does your change build on this agent's existing topics, voice, or knowledge — or is it largely self-contained?**
  > - **Self-contained scenario →** I'd build a **net-new Agent-Script agent** for it. That's Scout's strong lane — clean, editable source from day one — and we leave the legacy agent untouched.
  > - **Builds on the existing agent's wiring** (its other topics, voice config, knowledge/Data Library you'd otherwise rebuild) **→** then we **upgrade it to the new Agentforce Builder** first. Be honest with yourself that this is a **remediation project, not a quick step**: expect the first commit of the upgraded version to fail several times (blank required descriptions on legacy actions, missing standalone action records, stale knowledge-grounding IDs), and expect to de-conflict legacy SDO template topics that compete with your new topic for routing (which I can only check after the upgrade makes the planner readable). It's reversible — the old version stays Active until you activate the upgraded one — but on a managed, packaged, or template-derived agent confirm reversibility (or test in a sandbox) first. Plan a dedicated session for the upgrade itself.
  >
  > Which fits — self-contained (net-new), or builds-on-existing (upgrade-and-remediate)?"

  Carry the SE's choice into the spec. If text-only (no new/moved topic or action), this gate does not apply — building's editability pre-flight is the authoritative backstop.

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
