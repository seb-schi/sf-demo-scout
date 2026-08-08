# Agentforce Advanced Capabilities — Authoring + Handoff

Scout-owned reference (NOT a vendored skill — safe to edit). Loaded by
`phase3.md` when the spec's Agentforce section flags an advanced capability,
and mirrored by the spec-template's advanced-capabilities block.

These three capabilities share a shape: the **deployable metadata is
build-time-authorable** (Scout authors + deploys it), but the **UI wiring and
go-live verification are runtime-only** — no FlowTest / event-log signal can
assert them, so they render/route correctly only in a live Enhanced Web Chat
session. Scout authors what it can prove at build time, then hands the runtime
wiring to the SE with the exact steps below. This mirrors the `NeedsUICommit`
pattern — author + validate, then a UI handoff.

Source: Boehringer CareConnect4Me build (2026-08-04 → 08-07), docs-verified.

---

## 1. Multi-agent orchestration (one agent delegating to a connected sub-agent)

**Status: Beta, UI-only connection wiring.** (Docs: Salesforce Help
`ai.agent_orchestrate_remove.htm` — Beta, requires "Manage AI Agents".)

### Scout authors (build-time)
- The **sub-agent as a standalone agent** — its own `.agent` file / authoring
  bundle, published independently (all the normal New-Agent rules apply).
- In the **parent** agent script, the connection declaration + the invocation:
  ```
  connected_subagent <name>:
    target: "agentforce://<api_name>"      # MUST be agentforce:// — NOT agent://
    # map inputs/outputs here
  ```
  Then reference it as an action inside a **regular (non-router) sub-agent**:
  ```
  <action_name>: @connected_subagent.<name>
  ```
- For a **silent handoff** (no patient-facing prompt), mark passed inputs
  `is_user_input: False`.

### Gotchas (verbatim rejections from the build)
- `connected-agent-no-transition`: a connected sub-agent CANNOT be invoked via
  `@utils.transition to @connected_subagent.X` — that syntax is for local
  `@subagent.*` transitions only.
- `hyperclassifier-non-transition`: a router using
  `model: "model://sfdc_ai__DefaultEinsteinHyperClassifier"` can ONLY use
  `@utils.transition` actions — it cannot reference a connected sub-agent
  directly. The connected call must live in a downstream regular sub-agent, not
  at router level.
- `connected-agent-unsupported-scheme`: the URI scheme must be `agentforce://`,
  not `agent://`.

### SE handoff (runtime — UI-only)
- Wire the actual connection in **Agent Builder** (Beta, unversioned — no
  Metadata API / Agent Script path for the connection itself).
- Verify the handoff passes silent inputs correctly in a **live messaging
  session** — not observable at build time.

---

## 2. Enhanced Chat v2 activation (a.k.a. "v2 chat")

**Why it matters:** Custom Lightning Types (§3) do NOT render without an
Enhanced Chat v2 connection. (Docs: Salesforce Help
`ai.agent_enhanced_chat_v2_custom_lightning_types.htm`.)

### Scout authors (build-time)
- The agent-script **connection block** for the web client, including
  escalation routing when the spec calls for it:
  ```
  connection customer_web_client:
    escalation_message: "One moment while I connect you..."
    outbound_route_type: "OmniChannelFlow"
    outbound_route_name: "flow://<Escalation_Route_Flow>"    # flow:// prefix required
  ```

### SE handoff (runtime — UI-only)
- In Agentforce Builder, add the **Enhanced Chat v2 connection tile** (Explorer
  panel).
- **Republish the Embedded Service Deployment** after ANY agent version change —
  it is NOT automatic and can take up to ~10 min.
- Create the **Enhanced Chat Channel** via Builder.
- Test via **"Test Enhanced Web Chat"** (Embedded Service Deployments settings) —
  NOT Builder Preview, which has no MessagingSession context and cannot test
  escalation or form rendering.
- Escalation needs TWO config layers beyond the agent script, or `routeWork`
  fails with "queue isn't valid for this object type": (1) a
  `QueueRoutingConfigId` on the target queue; (2) a `QueueSobject` junction
  record for the `MessagingSession` sObject type.

---

## 3. Lightning types (forms) in chat

Render a custom form (Lightning Type) inline in the agent conversation, backed
by an Apex class. Requires Enhanced Chat v2 (§2).

### Scout authors (build-time)
- **LWC** targeting `lightning__AgentforceInput` (SLDS 2). It MUST implement the
  framework contract `@api value` and sync that object on every field change
  (`onchange` → `syncValue()`) — Enhanced Chat v2 reads `@api value` at submit.
  Do NOT build a custom submit button dispatching a `CustomEvent`: the framework
  ignores it and uses its own Submit control (a custom button produces a
  dead-button / double-button bug).
- **LightningTypeBundle** with:
  - `lightningTypes/<name>/schema.json` → `@apexClassType` binding to the Apex
    class. **Bind the OUTER class, not an inner `.Request` class** — inner-class
    references fail resolution silently (undetected at deploy time).
  - `lightningTypes/<name>/enhancedWebChat/editor.json` → references the LWC as
    `c/<componentName>`.
- In the **agent script**, declare the action input as
  `type: object` + `complex_data_type_name: "c__<ApexClass>"`, and drive
  slot-fill via `with X = ...` (no variable reference). Using
  `with X = @variables.Y` compiles to `boundInputs` reading unpopulated state
  vars and REMOVES them from `llmInputs` (the `boundInput`-vs-`llmInput` trap).
- **Currency outputs** from a backing Flow/Apex: declare `type: object` +
  `complex_data_type_name: "lightning__currencyType"` (NOT `number`); a Flow
  Currency variable also requires an explicit `<scale>` element or the deploy
  fails. (Empirically required per compiler errors — not found in published
  docs; treat as a build gotcha, re-verify if the compiler stops requiring it.)

### Gotchas
- Standard "Create Record" (Case) action failed `sf agent validate` with
  "Failed to find source action" — fall back to an Apex invocable.
- Testing/previewing custom Lightning Types for a Service agent is **not
  supported in Agentforce Builder** — test only in "Test Enhanced Web Chat".

### SE handoff (runtime)
- Confirm the form renders inline and `@api value` submits correctly in a live
  Enhanced Web Chat session (no build-time signal).
