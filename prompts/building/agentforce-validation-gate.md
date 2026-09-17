## Validation Gate — REQUIRED before reporting an agent working

This file is the single Agentforce acceptance policy. The orchestrator hashes the
installed file and records that digest in the independent current-test context.
Worker `smoke_test` fields and transcripts are summary only. They never decide
acceptance.

Create one expected ledger item per required action, guardrail, answer assertion,
or other test obligation. An action-bearing item names the exact agent, action,
behavior type, source kind, and typed criteria and carries `agent_runtime`. A
no-action guardrail or non-action assertion remains a separate ordinary ledger/test
obligation; it does not require a hero invocation to prove an intended decline. A
passing hero-action item resolves only that item and never clears another required
action or guardrail.

Keep three facts separate:

1. the independently read-back deployed agent and published version;
2. the explicitly selected current test identity; and
3. the invocation and behavior proven for that exact current test.

A coherent response, an expected-action declaration, test metrics, a prose
transcript, simulated actions, or an authoring preview before publication cannot
prove the deployed version worked. An older successful turn cannot replace a
current failure. A later fixed retest may supersede a failed attempt only when the
orchestrator selects it explicitly, preserves the failed attempt reference, and
records the concrete fix source.

### Current-test evidence ladder

Use the first channel that yields a saved, current, live trace:

1. **Live CLI preview trace.** Start preview with live actions, record the CLI
   session ID, send the selected turn, and save the trace. Do not assume the CLI
   session ID is an event-log parent.
2. **Enhanced event logs.** Enable logging before the turn. Call read-only REST Describe
   for `ConversationDefinitionEventLog`, save the response, and construct
   projections only from fields actually exposed there. Field labels in docs do not
   establish API names. Establish and save a verified session + turn + deployed version
   mapping before treating any row as current-test evidence.
3. **Exact test job/case or direct live trace.** A saved result for the selected job
   and case can prove invocation when it exposes actual live action execution. Its
   expected-action declaration and aggregate metrics cannot prove a write.
4. **Agent API headless.** Drive one selected live turn and retain its exact
   session/turn/version identities. Employee Agents run as the logged-in/Run-As
   user; use `bypassUser: false`. A Service Agent may use its assigned agent user.

For event-log retrieval, capture a UTC lower bound rounded down to the second before
the turn and an upper bound after the completed turn and bounded polling interval.
Use unquoted ISO-8601 literals with `>=` lower-inclusive and `<` upper-exclusive.
Never use an Apex-style `:sentAt` bind. A timestamp window narrows candidates; it
does not correlate them. Missing, delayed, denied, or uncorrelatable logs are
UNAVAILABLE. Only a matching complete current trace can prove the expected
invocation did not occur and therefore FAIL.

### Why a Service-Agent action didn't fire — read the trace, don't infer
When an `AgentforceServiceAgent` (dedicated running user) replies coherently but the behavior assessment
shows NO side-effect, the cause is almost always the running-user access stack, and the preview trace
tells you which layer — read it before re-authoring anything:
- **`EnabledToolsStep.runtime_withheld_actions`** — if the hero action appears here with
  `NO_USER_ACCESS`, it was never offered to the LLM (layer 1): the running user lacks
  `SetupEntityAccess` on the backing Apex/Flow. Fix in phase3's Running-User Backing-Action Access
  grant, NOT by editing the agent.
- **The action's passed inputs in the trace** — if the action fired with an input empty/null that
  should have been slot-filled, it was wired as a `boundInput` (`with X = @variables.Y`) that nothing
  populated, instead of an `llmInput` (`with X = ...`). This is an authoring fix in the `.agent`, not
  an access grant.
Record which layer the trace implicated in `discovery_notes`. A missing side-effect with a clean
`runtime_withheld_actions` AND populated inputs points downstream (layers 3/4/5 — RecordType,
dependency read, or license wall).

### Agent-type note (do not mis-diagnose a missing permset as the blocker)
Before treating a runtime/preview error as an access problem, check the deployed agent TYPE.
For `AgentforceEmployeeAgent`: `BotUserId=null` is BY DESIGN (it runs as the logged-in user) and it
needs NO agent-user runtime permset — do not block or await one. The CLI-preview "Invalid user ID"
error is the `bypassUser` interaction (ladder step 4), NOT a license/permset problem. Route
validation to the event-log path (step 2) rather than chasing a permset.

### Source-specific structural evidence

- **Agent Script / AiAuthoringBundle:** run the authoring validation appropriate to
  the `.agent` source and preserve its result. Agent Script source does not require `localActions`;
  absence of a compiled tree is not a structural failure.
- **Realized compiled GenAiPlannerBundle:** when changing existing topic actions,
  join each topic `<fullName>` to `localActions/<fullName>/`, require one action
  directory per `<functionName>`, and require nonempty `input/schema.json` and
  `output/schema.json`. Exclude `plannerActions`. Missing schemas are BLOCKED.
- **Unknown source kind:** report structural evidence UNAVAILABLE and do not infer
  which validation applies.

Never hand-patch a compiled planner to add or move topics/actions. Re-author from
Agent Script or use Builder so Salesforce creates the matching schemas.

### Behavior acceptance

- **Mutating action:** require a successful current live invocation and the exact
  approved target, discriminating pre-state sentinel, and requested post-state. A
  no-op is FAILED. If the desired value already existed before the turn and there
  is no discriminating pre-state, proof is UNAVAILABLE.
- **Read-only action:** require a successful current live invocation and exact typed
  answer/output assertions from the spec. Record `side_effect: not_applicable`.
- A current failed invocation, wrong target, wrong output, or complete trace proving
  no invocation is FAILED. Missing or uncorrelatable evidence is UNAVAILABLE.

### Required identity fields (confirm before reporting done)
Confirm the deployed agent has a NON-EMPTY **Role** and **Company** (description) field — both are
mandatory agent-identity fields. An agent can deploy and activate with these blank (it still appears
in Setup), but it ships incomplete and the SE must hand-fill them. If either is blank post-deploy,
record it in `issues` and surface it in the change log's SE checklist — do not silently report the
agent complete.

### Reporting
The worker records `smoke_test.action_invocation_confirmed` honestly, but it is
summary only. The orchestrator independently records the deployed version, current
test identity and sources, canonical gate digest, normalized invocation, behavior,
and structural evidence. It passes those facts to `scripts/build-completion.py`,
which uses the narrow `scripts/agentforce_evidence.py` evaluator.

Report PASS only for the exact ledger obligation assessed. FAIL and BLOCKED remain
explicit. UNAVAILABLE is deployed but unvalidated and remains AWAITING_QA when the
deployment/read-back is otherwise proven. A missing or malformed worker report
still leaves completion INCOMPLETE even when the independent runtime assessment
passes. Preserve prior attempt references and every remaining Agentforce test
obligation in the change log and handover.
