## Re-author From Planner (UI-built agent migration path)

**This section is ACTIVE only if the line above reads `RE-AUTHOR MODE: ON`.** If it reads
`RE-AUTHOR MODE: OFF` (or this section was substituted to an inert marker), skip it entirely
and follow the normal New-Agent / Modify-Existing paths.

The orchestrator routed you here because: the spec targets a UI-built agent (planner-only,
no editable source), the change is STRUCTURAL (adds/moves a topic or action), AND the SE has
confirmed they flipped the in-place Builder upgrade — which makes the agent's
`GenAiPlannerBundle` retrievable via Metadata API. Your job is NOT to hand-patch that planner.
Your job is to read it, reconstruct its topics/actions as fresh Agent Script, publish a clean
editable agent under a NEW side-by-side API name, and add the spec's new capability on top.

**Why re-author, not retrieve-and-edit:** an `AiAuthoringBundle` retrieved AFTER a publish is
`<target>`-locked and read-only — editing it deploys as a misleading no-op (see
`developing-agentforce` reference agent-metadata-and-lifecycle.md, "Version-suffixed
AiAuthoringBundle"). So you reconstruct from the planner into NEW source, never edit the
retrieved bundle in place.

### Step R1 — Retrieve the upgraded agent's planner (confirm readability)
The orchestrator's pre-flight already confirmed the planner retrieves. Re-retrieve it into the
project root for parsing:
```bash
# {{ORG_ALIAS}} substituted by orchestrator; directory pinned per the Retrieve output location rule
```
Use `retrieve_metadata` for `GenAiPlannerBundle:[LegacyAgentName]` with
`directory` = `$HOME/claude-projects/sf-demo-scout`. If the retrieve FAILS here (the SE did not
actually complete the upgrade, or it is org-specific), **STOP** and record the phase **BLOCKED**
in `issues` with reason "re-author requested but GenAiPlannerBundle:[LegacyAgentName] did not
retrieve — upgrade not confirmed on the org; do not ship a partial build." Report the agent NOT
shipped. Do NOT fall through to any hand-patch.

### Step R2 — Extract the inventory from the planner XML
Parse the retrieved planner. Build a structured inventory of:
- Each topic (`<genAiPlugin>` of `pluginType=Topic`): its label, scope/description, and the
  `<functionName>` action references it carries.
- Each action's backing-logic reference (standard action name, or the Apex invocable / flow
  `flow://` reference named in the planner or its `plannerActions`/`localActions` subtree).
- Planner-level standard actions (e.g. `AnswerQuestionsWithKnowledge`) — reproduce as standard
  actions, do NOT attempt to re-create knowledge grounding from scratch unless the spec calls for it.
Record the extracted inventory in `discovery_notes` so the SE can diff it against the legacy agent.

### Step R3 — Re-author as fresh Agent Script under a NEW api name
Invoke `developing-agentforce` and follow its New-Agent (create-from-scratch) workflow — NOT the
modify workflow. Build a brand-new authoring bundle whose api-name is the legacy name with a
`_Scout` suffix (e.g. `Field_Service_Agent_Scout`). Reproduce every extracted topic/action as
Agent Script subagents + actions. Wire backing logic to the SAME flows/Apex the legacy agent
used (those already exist in the org and have real source — do not re-deploy them unless the
spec adds new backing logic). Then ADD the spec's new topic/action/capability on top — this is
the whole point of the migration.

Publish via `sf agent publish authoring-bundle --api-name [LegacyAgentName]_Scout` and activate.
The legacy agent is UNTOUCHED and stays Active — the SE retires it manually once satisfied.

### Step R4 — Mandatory validation (reuses the standard gate)
Run the Smoke Test + Validation Gate below against `[LegacyAgentName]_Scout`. The
action-invocation probe is mandatory — a re-authored agent that has not had at least one
action confirmed firing is reported **deployed but NOT validated**, never "Active/working."

### Step R5 — Report honestly
In `issues`, record the n=0 caveat verbatim: "Re-authored [LegacyAgentName]_Scout from the
upgraded planner's inventory. Side-by-side with the untouched legacy [LegacyAgentName]. Topic/action
fidelity is NOT machine-verified beyond the smoke test — SE MUST diff re-authored behavior against
the legacy agent (or its known demo script) before demo day, then retire the legacy agent." Carry
this into the change log and handover brief.
