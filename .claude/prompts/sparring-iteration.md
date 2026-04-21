# Iteration Path — Discovery & Definition

Loaded on demand when intent = iteration. Returns to the main command for Stage 5+.

## Stage 4i: Iteration Discovery

Review the most recent audit, prior specs, and change logs for this org. Understand what's already built before asking anything.

Ask these three questions in a single message:
1. **What are you adding or changing?** Be specific — "add an Agentforce agent for case triage," not "improve the demo."
2. **Why now?** Customer feedback, new stakeholder, demo gap, competitive pressure — what's driving this?
3. **Which part of the existing demo does this connect to?** Where in the demo flow does this appear?

**Stop and wait for answers.**

If the SE's answers are vague ("just add an agent" / "because I want one" / "it's standalone"), push back: "Which customer moment does this serve? If you can't name the moment, it'll feel bolted-on in the demo."

### Delta Conflict Check

After the SE answers, review the existing audit and any prior specs/change logs against the proposed change:
- **Conflicts:** existing flows on the same object, field name collisions, layout crowding, permission set overlaps
- **Quality evaluation:** does the existing setup make sense as a foundation? If not, say so:
  > "Before we add [proposed change] — I reviewed the current org state. [Problem]. Adding this on top will [consequence]. Want to address that first, or proceed anyway?"

Only surface genuine concerns — don't re-litigate prior decisions that are working fine.

Then proceed to Stage 5 (Platform & Data Model Research).

---

## Stage 6i: Iteration Definition

Propose the change: what gets built, what exists, what conflicts, what the SE does manually.

Apply the same **existing-first evaluation** as Stage 6 — even a single new component should prefer extending existing metadata. Ground data model choices in Stage 5 research.

**ONE GATE — send as a standalone message, then stop:**

> "Walk me through the demo moment where this appears. What happens right before, and what does the customer see right after?"

This forces integration thinking. If the SE can't place the change in a demo flow: "If you can't describe what comes before and after, this change doesn't have a home in the demo yet. Let's figure out where it fits first."

Once the gate is cleared, proceed to Stage 6b.
