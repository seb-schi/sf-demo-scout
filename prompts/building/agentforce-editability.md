# Agentforce Editability Pre-Flight

Read + executed by `scout-building.md` Step 5 Phase 3 (orchestrator context, NOT a sub-agent) — **only when the spec modifies an existing agent.** Net-new-agent builds never read this file: the caller has already classified net-new vs modify-existing inline and takes the Agent-Script path directly.

**Run this BEFORE the Phase 3 SE gate, before any sub-agent spawn.** The failure this prevents: two consecutive builds shipped a dead topic because the sub-agent hand-patched a compiled `GenAiPlannerBundle` on a UI-built agent (added topic/action graph references but not the matching `localActions/<topic>/<action>/{input,output}/schema.json` folders — so the actions can't resolve at runtime, yet deploy reports SUCCESS and the agent stays Active). Determine editability ONCE here.

The caller has already classified whether the change **adds or moves a topic/action** (structural) vs **tweaks existing node text/values only** (in-place). Use that classification in the routing decision below.

## Step 1 — Determine editability

Determine editability with a cheap SOQL query FIRST, then obtain current retrieval evidence. `agentDSLEnabled` is NOT SOQL-reachable; it lives only in `.bot-meta.xml`, so don't query it. Validate the agent API identifier before substituting it in commands or SOQL, and require the exact intended org and one matching agent identity:
```sql
SELECT DeveloperName, Type, AgentType FROM BotDefinition WHERE DeveloperName = '[AgentName]'
```
**Risk-class flag:** `AgentType = 'EinsteinServiceAgent'` (or a legacy `Type = 'Bot'` / `Type = 'ExternalCopilot'`) has indicated UI-built, planner-only agents in observed SDO/IDO examples. The enum is empirical, not proof: an Agent-Script-authored service agent may have the same value. A failed or ambiguous identity query leaves editability unavailable.

Create a unique empty retrieve directory beneath the separately prepared parent-owned project's `force-app/main/default/` (for example with `mktemp -d` and a `.scout-agent-retrieve.XXXXXX` template), and substitute its actual absolute path for `[fresh retrieve directory]`. Do not reuse a previous directory. Capture the complete stdout JSON, separate stderr, and actual exit code; do not pipe through `head` or replace a failed command with a successful pipeline exit.

```bash
sf project retrieve start --json --metadata "AiAuthoringBundle:[AgentName]" --output-dir "[fresh retrieve directory]" --target-org {{ORG_ALIAS}}
```

**Positive retrieval proof:** require exit 0, top-level CLI `status = 0`, and a completed `result` with `done = true`, `success = true`, `status = "Succeeded"`. Require current-response `fileProperties` for the exact metadata type and fullName plus matching non-failed `files[]` rows (`type`, `fullName`, `filePath`, `state`). Resolve every selected path beneath that fresh directory and verify the expected regular files and complete bundle are present. A stale workspace file, empty result, partial retrieve, enqueue receipt, or success for another member is not proof. If the installed CLI returns a different/insufficient shape, report unavailable evidence rather than guessing.

Classify exactly one outcome:

- **Source confirmed:** the positive proof includes this agent's AiAuthoringBundle and editable `.agent` source. Record the raw result and exact source paths.
- **Source absence positively confirmed:** independent current evidence explicitly establishes that this exact agent has no editable Agent Script source (for example, an SE's current Builder inspection, or successful complete metadata discovery that establishes absence with access and identity confirmed). Save the evidence and its limitations. The risk enum, a retrieve error code/message, or an empty retrieve alone cannot establish this state.
- **Unavailable / unknown:** authentication, permission, network, timeout, malformed/incomplete result, missing member evidence, or otherwise ambiguous failure. Record the exact diagnostic and keep the affected agent BLOCKED pending a corrected probe or positive source evidence. Do not infer UI-built/sourceless status, prescribe an upgrade, or authorize planner editing from this outcome. Independent eligible work may proceed.

## Step 2 — Routing decision

- **Modify-existing WITH editable source** → version-safe Modify path. Proceed normally.
- **Modify-existing, source absence positively confirmed, IN-PLACE tweak only** → retrieve the exact GenAiPlannerBundle using the same fresh-directory and positive-proof rules before permitting the existing planner-text Modify path. Unavailable required planner source keeps the agent BLOCKED.
- **Modify-existing, source absence positively confirmed, STRUCTURAL add/move of topic or action** → **DO NOT hand-patch the planner.** This is the existing side-by-side re-author path. Present the SE this gate and STOP for the answer:
  > "**[AgentName]** is a UI-built agent — its planner can't be safely edited as metadata, so I can't add a topic/action to it directly. The low-friction path: **flip the in-place upgrade in Agent Builder** (Setup → Agentforce Studio → open the agent → upgrade to the new Builder). It's **reversible** — the old version stays Active until you activate the new one, so nothing breaks. Once upgraded, the agent's definition becomes machine-readable and I'll **re-author it as clean, editable Agent Script under a new side-by-side name (`[AgentName]_Scout`)**, then add your new [topic/action] on top. The original [AgentName] stays untouched so you can compare them. **On a managed, packaged, or template-derived agent, confirm the upgrade is reversible (or test in a sandbox) first.** Have you completed the upgrade? (yes / no — or 'manual' to wire it yourself in Builder instead)"

    - **SE answers yes (upgraded)** → retrieve the planner into another unique empty directory and apply the same complete positive-proof rules for `GenAiPlannerBundle`:
      ```bash
      sf project retrieve start --json --metadata "GenAiPlannerBundle:[AgentName]" --output-dir "[fresh retrieve directory]" --target-org {{ORG_ALIAS}}
      ```
      Positive proof → route to Phase 3 in **re-author mode**: set `{{REAUTHOR_FROM_PLANNER}}` to the live directive (see the substitution note on the Phase 3 table row). Record the SE's upgrade confirmation, retrieve result and actual planner path in `discovery_notes`. Otherwise do NOT spawn Phase 3 for this agent: report BLOCKED because current planner source could not be verified. A failed retrieve does not prove that the upgrade failed. Name the actual diagnostic and next probe/manual option.
    - **SE answers no / manual** → deploy only approved, independently eligible backing flows/Apex; hand off the structural topic/action wiring with the positive source-absence evidence. An outstanding manual obligation remains BLOCKED. Use `skipped[]` only if the SE explicitly declines that ledger obligation and the orchestrator records the authorized omission; declining the upgrade alone is not declining the requested work. Surface the split in the SE gate.

Record the editability verdict and evidence reference in `discovery_notes` (for example, `"Agentforce_Service_Agent: source unavailable — retrieve authentication failed; structural edit BLOCKED pending a successful probe"`). Do not include credentials in the diagnostic.

For an eligible route, stage only the positively retrieved complete members from
the fresh directory into their canonical parent-owned project source paths; record the source
and destination mapping. Retain the fresh retrieval and raw evidence until the
existing preservation/cleanup guards pass. Do not deploy from the retrieval
scratch directory or treat staging as permission to change the agent.

For a modify-existing route, record the exact retrieved bundle member paths that
will be edited (relative to `force-app/main/default`, including actual version/Id
suffixes). Carry this selection into Phase 3's mandatory pre-edit preservation and
the orchestrator's independent receipt check. Preserve only relevant complete
members; an unused absent family is not an error. A required source missing from
disk blocks the edit. Re-authoring under a new side-by-side name does not modify
the incumbent and follows the new-agent recovery contract instead.

For the modify-existing route, preserve the selected complete source for transfer
before returning. Set `SOURCE_ROOT` and `ROLLBACK_DIR` to the parent's helper-returned
paths, and `AGENT_PREFLIGHT_PATH` to the exact selected relative member. Repeat
`--path` when both families are selected:

```bash
python3 "$ASSET_HELPER" preserve --source-root "$SOURCE_ROOT" \
  --rollback-dir "$ROLLBACK_DIR" --kind component-preedit \
  --path "$AGENT_PREFLIGHT_PATH"
```

Require success and verify the returned artifact. Retain it as
`AGENT_PREFLIGHT_ARTIFACT`, with the exact member list and retrieval evidence.
This immutable transfer uses existing preservation machinery; it does not replace
Phase 3's required `agent-preedit` snapshot and original active-version record.
On failure, block the affected edit and retain all parent source. Then return to
`scout-building.md` Phase 3 for its SE gate and explicit source handoff.
