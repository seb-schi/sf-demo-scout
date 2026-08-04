## Validation Gate — REQUIRED before reporting the agent working

A coherent conversation is NOT proof an agent works. An agent may be reported `Active` (it deployed
and published) but it must NOT be reported `validated` / `working` unless at least one of its actions
has been **confirmed to fire with a real side-effect**. "Confirmed to fire" requires an
**org-verified side-effect delta against a pre-state you set yourself** — the strongest, and the only
fully reliable, proof:
- SET a known pre-state (create the target record with a sentinel field value, or note "0 Cases for
  this contact"), drive the hero utterance, then RE-QUERY and confirm the delta (row-count increased,
  or the field mutated from your sentinel to the expected value). A record that merely *exists* is
  NOT proof — it may predate the turn.
- An event-log `FunctionStep` row in `ConversationDefinitionEventLog` proves the action was *invoked*,
  but NOT that it *succeeded* — a backing action can fire and then fail downstream on a RecordType, a
  dependency read, or a license wall (layers 3/4/5 in phase3's Running-User Backing-Action Access
  section) and still leave a row. Treat the event-log row as necessary-but-not-sufficient whenever the
  action has a side effect: pair it with the delta check. (An event-log row alone is acceptance ONLY
  for a read-only / answer action that has no side effect.)

A green conversation where the agent SAYS it will act, with no verified delta, is explicitly NOT
acceptance. This is the exact failure that shipped here twice: first the agent narrated "I'll flag it"
on every channel and never invoked the action; later it invoked the action but silently failed
downstream and still replied fluently.

### Fallback ladder (try in order; stop at the first that yields a confirmed invocation)
1. **CLI preview + traces** — `sf agent preview start --use-live-actions` then send an utterance that
   should fire the hero action; inspect the session trace for the action invocation.
2. **Enhanced event logs** — if preview is blocked (e.g. "Invalid user ID provided on start session"
   — see agent-type note below; this is common in SDO/IDO orgs), enable
   "Keep a record of conversations with enhanced event logs" on the agent (Edit Agent Details),
   send ONE test turn through any working channel, then query:
   ```sql
   SELECT StepType, Action, EventTarget, IsSuccessful, ConversationTurn, EventDetails
   FROM ConversationDefinitionEventLog WHERE CreatedDate = TODAY ORDER BY CreatedDate DESC
   ```
   A `FunctionStep` row for the hero action = confirmed invocation. (Note: the object is
   `ConversationDefinitionEventLog` — there is no `GenAiInteraction`.)
3. **Agent API headless** — drive a turn from an external app via the Agent API. Employee Agents
   run as the logged-in/Run-As user; use `bypassUser: false` on the `/sessions` call (NOT `true` —
   public docs say `true` for client-credentials, but that assumes a Service Agent with an assigned
   agent-user; an Employee Agent has `BotUserId=null` and `true` throws "Invalid user ID").

### Why a Service-Agent action didn't fire — read the trace, don't infer
When an `AgentforceServiceAgent` (dedicated running user) replies coherently but the delta check above
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
error is the `bypassUser` interaction (ladder step 3), NOT a license/permset problem. Route
validation to the event-log path (step 2) rather than chasing a permset.

### Schema presence check (cheap — do it PRE-DEPLOY, do not rely on a post-deploy re-retrieve)
The load-bearing structural check is the **on-disk `localActions` folder presence gate** in phase3.md's
Modify path: for every Topic plugin in the bundle XML that has actions, a `localActions/<topic-fullName>/`
directory must exist with one non-empty `input/schema.json` + `output/schema.json` per action,
verified BEFORE deploy via the topic's `<fullName>` (the folder name verbatim — do not guess at the
Salesforce-assigned Id suffixes). Do this on disk — do NOT defer it to a post-deploy `retrieve_metadata`
GenAiPlannerBundle re-retrieve, which can fail with UNKNOWN_EXCEPTION and silently skip the one check
that catches a missing schema. An action with no input schema gives the LLM no slots to fill, so it can
never be invoked. If a schema folder is absent, block the deploy and record it in `issues`; re-adding the
action via the Builder wizard regenerates the schema. Independent of this, the orchestrator runs an
Action-Invocation Probe after Phase 3 (sub-agent-validation.md) that confirms the hero action actually
fired in the org — that probe, not this sub-agent's self-report, decides validated status.

### Required identity fields (confirm before reporting done)
Confirm the deployed agent has a NON-EMPTY **Role** and **Company** (description) field — both are
mandatory agent-identity fields. An agent can deploy and activate with these blank (it still appears
in Setup), but it ships incomplete and the SE must hand-fill them. If either is blank post-deploy,
record it in `issues` and surface it in the change log's SE checklist — do not silently report the
agent complete.

### Reporting
Set `smoke_test.action_invocation_confirmed = true` ONLY when the ladder yielded a confirmed
side-effect delta per the acceptance definition above (an invocation with no verified delta is NOT
enough for an action that has a side effect; an event-log row alone suffices only for a read-only
action). If no rung confirmed the required proof, set it `false`,
record which rungs were tried (with the verbatim error) in `discovery_notes`, and report the agent
as NOT validated — NOT "Active/working." A `false` value does not block the deployment from
completing; it ensures the SE sees an honest "deployed but unvalidated — hero action never confirmed
to fire" status instead of a false green.
