# Agent Go-Live via Builder UI — SFAP-publish-404 recovery runbook

**When to use this.** Scout's headless publish (`sf agent publish authoring-bundle`)
failed with an empty-body HTTP 404 (`AgentApiNotFound`) on
`POST /einstein/ai-agent/v1.1/authoring/agents` (and `/…/agents/{id}/versions`),
on all three hosts (`api.` / `test.api.` / `dev.api.salesforce.com`), *after*
`sf agent validate` and `sf agent preview` succeeded. That signature is a
**per-instance SFAP provisioning gap** — the publish resource is not routed on this
org instance — NOT a client, CLI, permission, or bundle-validity problem. Confirmed
facts behind this runbook:

- Compile (`/authoring/scripts`) succeeds on the same instance → the bundle is valid.
- `sf project deploy start` lands the `.agent`/`AiAuthoringBundle` **source** in the
  org but does NOT compile it to a runnable planner (source-only — verified by an
  unchanged `GenAiPlannerBundle` after deploy+activate).
- The Agentforce **Builder UI** (New Draft → wire → Commit → Activate) is the ONLY
  verified path to a live agent on a 404 instance. A committed agent DOES round-trip
  to editable `AiAuthoringBundle` source — so this is recoverable, not a dead end.
- The instance-level fix is a **Salesforce Support case citing the org instance ID**
  (cross-post evidence to #agentforce-dx). Until then, use this UI path.

**This is not one-click.** The preserved `.agent` is a *blueprint*; commit compiles
routing (topics) but validates every action's I/O against the live Flow/Apex backend
and will reject mismatches. Expect an iterative reconcile. Budget accordingly.

---

## Prerequisites — verify against the org FIRST

The commit compiler validates every action against its live backend. If a backing
component is missing or inactive, commit fails. Before authoring, confirm each
backing component the agent references exists and is active — e.g.:

```bash
# Apex backing class active?
sf data query -o <ORG_ALIAS> -t -q "SELECT Name, Status FROM ApexClass WHERE Name='<ClassName>'"
# Flow has an active version?
sf data query -o <ORG_ALIAS> -t -q "SELECT DeveloperName, ActiveVersionId FROM FlowDefinition WHERE DeveloperName='<FlowName>'"
# Knowledge online (only if the agent grounds on Knowledge)?
sf data query -o <ORG_ALIAS> -q "SELECT COUNT(Id) FROM Knowledge__kav WHERE PublishStatus='Online'"
```

## Reconcile action I/O against live schemas BEFORE authoring

The commit compiler checks each action's declared inputs/outputs against the REAL
flow/apex interface — a name or type mismatch fails commit with a message that names
the exact fix, but you save a round-trip by matching up front:

```bash
sf project retrieve start -o <ORG_ALIAS> -m Flow:<FlowName>       # read <variables> name / isInput / isOutput / dataType
sf project retrieve start -o <ORG_ALIAS> -m ApexClass:<ClassName> # read @InvocableVariable names / types
```

Two recurring mismatch classes:
- **Input name:** Flow inputs often carry a prefix (e.g. `inp_<Name>`); the action
  input + arg binding must match that exact name, not a guessed camelCase.
- **Currency/complex output type:** a Flow Currency output must be declared `object`
  with `complex_data_type_name: "lightning__currencyType"`, not `number`. Only
  `object`/`list[object]` inputs/outputs carry `complex_data_type_name`; primitives
  (`string`/`boolean`/`number`) do NOT — a `complex_data_type_name` on a primitive
  is a cosmetic Warning to remove for a clean save.

## The happy path (step by step)

1. **Open the agent in Agentforce Builder.**
   `sf org open -o <ORG_ALIAS> --path "/lightning/setup/EinsteinCopilot/home"` then
   open the agent.
2. **A committed version is READ-ONLY — by design, not a bug.** Salesforce docs
   (*Commit an Agent Version*): once committed you can no longer change that version;
   create a new draft. If Canvas AND Script both show read-only, the version is
   committed — do NOT mistake this for the 404 or a permission problem. Click **New Draft**.
3. **New Draft → fully editable clone.** Creates the next version (e.g. v3) as an
   editable draft; clones all assets (subagents, actions, variables). Both Canvas and
   Script views become editable.
4. **Get the real `.agent` source to edit — don't hand-type.** A committed agent
   exposes editable source: `sf project retrieve start -o <ORG_ALIAS> -m "AiAuthoringBundle:<ApiName>"`.
   ⚠️ A default-template Service Agent commit produces a **stock `SvcCopilotTmpl` shell**
   (ServiceCustomerVerification, OrderInquiries, ReservationManagement, DeliveryIssues,
   AccountManagement, CaseManagement, GeneralFAQ…) — NOT your real topics. This is why
   "committed" ≠ "your agent is live": you must replace the topic set.
5. **Build the target-state script — MERGE, don't wholesale-replace.** Keep the
   template's required scaffolding or Save fails:
   - `config: agent_template: "SvcCopilotTmpl__AgentforceServiceAgent"`
   - the 5 `linked` MessagingSession variables (EndUserId / RoutableId / ContactId /
     EndUserLanguage / ChannelType) — the linter flags them "unused" but also says
     *"required by Agentforce; removing can cause issues"* → KEEP them (Info, not error).
   - `model_config` on the router, the `knowledge:` block (if grounded), `access: default_agent_user`.
   Swap in your real topics from the Scout-preserved blueprint (see step below).
6. **Paste into Script view → Save → read the Console.**
   - **Info** (unused-but-required scaffolding vars): expected, ignore.
   - **Warning** (`complex_data_type_name` on a primitive input): cosmetic; remove for
     a clean save.
   - You can commit with warnings, NOT with errors.
7. **Commit Version — expect action-schema rejections.** The compiler checks each
   action's declared I/O against the real flow/apex interface. Each error names the
   exact fix (input rename, type→`object`+`complex_data_type_name`). Apply and re-commit
   until a clean Save (Info-only, 0 warnings, 0 errors) → **Commit Version** succeeds.
   (Reconciling up front per the section above minimizes these.)
8. **Verify the commit compiled the REAL topics — org-side, not on the UI's word:**
   ```bash
   sf project retrieve start -o <ORG_ALIAS> -m "GenAiPlannerBundle:<ApiName>_v<N>" --target-metadata-dir /tmp/planner-vN
   unzip -oq /tmp/planner-vN/unpackaged.zip -d /tmp/planner-vN/unz
   rg -l "<your_real_topic_or_action_tokens>" /tmp/planner-vN/unz      # expect hits
   rg -l "OrderInquiries|ReservationManagement|SvcCopilotTmpl__CreateCaseEnhancedData" /tmp/planner-vN/unz  # expect ZERO
   ```
   Real topics present + template topics gone = airtight proof the UI path compiled
   your content.
9. **Activate (headless activate works — different endpoint than the dead publish):**
   ```bash
   sf agent activate --api-name <ApiName> --version <N> -o <ORG_ALIAS> --json
   # --version is REQUIRED non-interactively, else the CLI prompts and a headless run force-closes.
   sf data query -o <ORG_ALIAS> -q "SELECT VersionNumber, Status FROM BotVersion WHERE BotDefinition.DeveloperName='<ApiName>' ORDER BY VersionNumber"
   ```

## After go-live — commit compiles ROUTING, not action correctness

The agent will route to your real topics and can still fail to fire actions. A
coherent reply is NOT validation — confirm action side-effects in a **live Messaging
Session**, never on the preview reply text:
- Knowledge/FAQ grounding needs the **Data Library** wired (Setup → Agentforce Studio
  → Data Libraries); without it grounded topics return empty.
- For each backing action, confirm the side-effect actually occurred (record created,
  flow result returned) and that the agent's running user has the FLS/permset to run it.

## Escalation

This is a backend per-instance gap no client change fixes. File a Salesforce Support
case citing the org **instance ID**, and cross-post the captured endpoint/status
evidence to #agentforce-dx (strengthens the existing "not org-wide, not auth" thread).
