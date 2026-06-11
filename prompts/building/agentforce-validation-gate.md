## Validation Gate — REQUIRED before reporting the agent working

A coherent conversation is NOT proof an agent works. An agent may be reported `Active` (it deployed
and published) but it must NOT be reported `validated` / `working` unless at least one of its actions
has been **confirmed to fire**. "Confirmed to fire" means ONE of:
- the real record write the action performs is observed in the org (SOQL the target record), OR
- an event-log row shows the action executed (a `FunctionStep` in `ConversationDefinitionEventLog`).

A green conversation where the agent SAYS it will act, with no record change and no event-log row,
is explicitly NOT acceptance. This is the exact failure that shipped here once: the agent narrated
"I'll flag it" on every channel and never invoked the action.

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

### Agent-type note (do not mis-diagnose a missing permset as the blocker)
Before treating a runtime/preview error as an access problem, check the deployed agent TYPE.
For `AgentforceEmployeeAgent`: `BotUserId=null` is BY DESIGN (it runs as the logged-in user) and it
needs NO agent-user runtime permset — do not block or await one. The CLI-preview "Invalid user ID"
error is the `bypassUser` interaction (ladder step 3), NOT a license/permset problem. Route
validation to the event-log path (step 2) rather than chasing a permset.

### Post-deploy schema check (cheap, do it before the gate)
After publish/activate, confirm each agent action has a NON-EMPTY Input/Output schema and that the
planner bundle re-retrieves cleanly (`retrieve_metadata` GenAiPlannerBundle:[AgentName] succeeds).
Actions added programmatically can land with an empty/unresolved I/O schema — an action with no input
schema gives the LLM no slots to fill, so it can't meaningfully invoke it. If a schema is empty or
the planner won't re-retrieve, record it in `issues` and treat the gate as NOT passed; re-adding the
action via the Builder wizard regenerates the schema.

### Required identity fields (confirm before reporting done)
Confirm the deployed agent has a NON-EMPTY **Role** and **Company** (description) field — both are
mandatory agent-identity fields. An agent can deploy and activate with these blank (it still appears
in Setup), but it ships incomplete and the SE must hand-fill them. If either is blank post-deploy,
record it in `issues` and surface it in the change log's SE checklist — do not silently report the
agent complete.

### Reporting
Set `smoke_test.action_invocation_confirmed = true` ONLY when the ladder yielded a confirmed
invocation per the acceptance definition above. If no rung confirmed an invocation, set it `false`,
record which rungs were tried (with the verbatim error) in `discovery_notes`, and report the agent
as NOT validated — NOT "Active/working." A `false` value does not block the deployment from
completing; it ensures the SE sees an honest "deployed but unvalidated — hero action never confirmed
to fire" status instead of a false green.
