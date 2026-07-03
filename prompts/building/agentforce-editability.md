# Agentforce Editability Pre-Flight

Read + executed by `scout-building.md` Step 5 Phase 3 (orchestrator context, NOT a sub-agent) — **only when the spec modifies an existing agent.** Net-new-agent builds never read this file: the caller has already classified net-new vs modify-existing inline and takes the Agent-Script path directly.

**Run this BEFORE the Phase 3 SE gate, before any sub-agent spawn.** The failure this prevents: two consecutive builds shipped a dead topic because the sub-agent hand-patched a compiled `GenAiPlannerBundle` on a UI-built agent (added topic/action graph references but not the matching `localActions/<topic>/<action>/{input,output}/schema.json` folders — so the actions can't resolve at runtime, yet deploy reports SUCCESS and the agent stays Active). Determine editability ONCE here.

The caller has already classified whether the change **adds or moves a topic/action** (structural) vs **tweaks existing node text/values only** (in-place). Use that classification in the routing decision below.

## Step 1 — Determine editability

Determine editability with a cheap SOQL query FIRST, then confirm with a single retrieve used as a boolean (do NOT parse error strings — `agentDSLEnabled` is NOT SOQL-reachable; it lives only in `.bot-meta.xml`, so don't query it):
```sql
SELECT DeveloperName, Type, AgentType FROM BotDefinition WHERE DeveloperName = '[AgentName]'
```
**Risk-class flag:** `AgentType = 'EinsteinServiceAgent'` (or a legacy `Type = 'Bot'` / `Type = 'ExternalCopilot'`) is the UI-built, planner-only, hand-patch-risk class (the WSA/Qiagen class). `AgentType` values like `AgentforceEmployeeAgent` / `Employee` / `ServicePlanner` are the other classes. **The enum is an empirical SDO/IDO mapping, not a guarantee** — a newer Agent-Script-authored service agent could also report `EinsteinServiceAgent` yet have editable source. So treat the SOQL result as the risk flag, then confirm with ONE retrieve used purely as a boolean:
```bash
sf project retrieve start --json --metadata "AiAuthoringBundle:[AgentName]" --target-org {{ORG_ALIAS}} 2>&1 | head -40
```
Retrieve **succeeds** (a `.agent`/AiAuthoringBundle lands on disk) → **editable source exists** (safe edit). Retrieve **fails** → **confirmed sourceless / UI-built** (route structural edits to Builder). Use success-vs-failure as the boolean — do NOT pattern-match the exact error code (the surface evolves monthly).

## Step 2 — Routing decision

- **Modify-existing WITH editable source** → version-safe Modify path. Proceed normally.
- **Modify-existing, UI-built (no source), IN-PLACE tweak only** → planner XML edit is the legitimate path. Proceed to the Modify path.
- **Modify-existing, UI-built (no source), STRUCTURAL add/move of topic or action** → **DO NOT hand-patch the planner.** This is the re-author path. The painful "remediate the legacy agent in place" route is retired — instead, make the agent editable by re-authoring it from scratch, side-by-side. Present the SE this gate and STOP for the answer:
  > "**[AgentName]** is a UI-built agent — its planner can't be safely edited as metadata, so I can't add a topic/action to it directly. The low-friction path: **flip the in-place upgrade in Agent Builder** (Setup → Agentforce Studio → open the agent → upgrade to the new Builder). It's **reversible** — the old version stays Active until you activate the new one, so nothing breaks. Once upgraded, the agent's definition becomes machine-readable and I'll **re-author it as clean, editable Agent Script under a new side-by-side name (`[AgentName]_Scout`)**, then add your new [topic/action] on top. The original [AgentName] stays untouched so you can compare them. **On a managed, packaged, or template-derived agent, confirm the upgrade is reversible (or test in a sandbox) first.** Have you completed the upgrade? (yes / no — or 'manual' to wire it yourself in Builder instead)"

    - **SE answers yes (upgraded)** → confirm the planner now retrieves with ONE boolean probe:
      ```bash
      sf project retrieve start --json --metadata "GenAiPlannerBundle:[AgentName]" --target-org {{ORG_ALIAS}} 2>&1 | head -40
      ```
      Retrieve **succeeds** → route to Phase 3 in **re-author mode**: set `{{REAUTHOR_FROM_PLANNER}}` to the live directive (see the substitution note on the Phase 3 table row). Record in `discovery_notes`: `"[AgentName]: UI-built, SE upgraded in Builder, planner now retrievable — re-authoring as [AgentName]_Scout side-by-side."` Retrieve **still fails** → the upgrade did not take; do NOT spawn Phase 3 for this agent. Tell the SE the upgrade isn't visible to the Metadata API yet (it can lag a few minutes, or the upgrade didn't complete), record the agent as skipped with that reason, and offer to retry or route to the manual path.
    - **SE answers no / manual** → fall back to the SE Manual Checklist: Scout deploys the backing flows/Apex only (the parts with real source); the topic + action **wiring** is routed to the SE Manual Checklist ("Add topic '[X]' + action '[Y]' in Agent Builder — the agent is UI-built, so structural wiring must be done in the Builder wizard, which regenerates the action I/O schemas"). Record this split in `skipped` with reason "SE Manual Checklist — UI-built agent, SE declined upgrade, structural wiring not source-editable." Surface it in the SE gate below.

Record the editability verdict in `discovery_notes` verbatim (e.g. `"Agentforce_Service_Agent: AiAuthoringBundle retrieve failed (AABNotFound) — UI-built, structural wiring routed to SE Manual."`).

Then return to `scout-building.md` Phase 3 for the SE gate.
