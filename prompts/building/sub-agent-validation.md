# Sub-Agent Output Validation

Loaded on-demand by scout-building.md Step 5 between every sub-agent return and the next phase. Procedure for validating JSON output AND empirically probing the org when validation fails.

## Procedure

After EVERY sub-agent returns, validate its output before proceeding:

1. Extract the fenced `json` block from the sub-agent's response.
2. Parse it. If parsing succeeds and the top-level keys match the phase schema, schema validation passes. **For Phase 1, schema validity is necessary but not sufficient when `data_seeded[]` is non-empty — also run the Data Seeding Integrity Probe (below) before declaring the phase passed.** Required top-level keys:
   - Phase 1: `deployed`, `skipped`, `issues`
   - Phase 2: `deployed`, `skipped`, `discovery_notes`, `issues`
   - Phase 3: `deployed`, `smoke_test`, `actions_unverified_in_preview`, `skipped`, `discovery_notes`, `issues`
3. **If parsing fails or required keys are missing, probe the org before declaring failure.** Sub-agent may have completed the deployment and only mangled the output envelope. Use the empirical probe queries below per phase.
4. Only if the empirical probe shows the deployment did NOT complete: treat the phase as FAILED. Show the raw output to the SE:
   > "Sub-agent returned unexpected output for Phase [N], and the [org probe] shows the deployment did not complete. Raw output below. Retry with a fresh sub-agent, or skip this phase?"
5. If retry also produces invalid output AND the org probe still shows incomplete: record as FAILED in the change log and tell the SE to start a fresh session for this phase.

## Empirical Probe Queries

### Phase 1 (Org Config)

Run these SOQL queries via `run_soql_query` against the target org. Substitute `[ApiNames]` with the comma-quoted API names the spec requested.

- **Custom objects present:**
  ```
  SELECT QualifiedApiName FROM EntityDefinition WHERE QualifiedApiName IN ('Custom_Object_1__c','Custom_Object_2__c')
  ```
- **Custom fields present:**
  ```
  SELECT QualifiedApiName FROM FieldDefinition WHERE EntityDefinition.QualifiedApiName='Case' AND QualifiedApiName IN ('Field_1__c','Field_2__c')
  ```
- **Record types present:**
  ```
  SELECT DeveloperName, SobjectType FROM RecordType WHERE SobjectType='Case' AND DeveloperName IN ('RT_1','RT_2')
  ```
- **Custom tabs present:**
  ```
  SELECT DeveloperName FROM TabDefinition WHERE DeveloperName IN ('Tab_1','Tab_2')
  ```
- **Permission set present:**
  ```
  SELECT Id, Name FROM PermissionSet WHERE Name='[PermSetApiName]'
  ```

Rule: every component the spec requested must return a row. If every component exists → treat as SUCCESS with `schema_validation_failed: true`, harvest what you can from the raw sub-agent output, preserve the rest verbatim in the change log's Issues Encountered section. If components are missing → treat as partial FAILED; show raw output to the SE and ask retry-or-skip.

### Phase 2 (Flows / Apex / LWC)

- **Flow active:**
  ```
  SELECT ApiName, ActiveVersionId FROM FlowDefinitionView WHERE ApiName IN ('Flow_1','Flow_2')
  ```
  (`ActiveVersionId != null` means the flow is active; null means Draft only.)
- **Apex classes present:**
  ```
  SELECT Name, Status FROM ApexClass WHERE Name IN ('Class_1','Class_2')
  ```
- **Apex triggers present:**
  ```
  SELECT Name, Status FROM ApexTrigger WHERE Name IN ('Trigger_1','Trigger_2')
  ```
- **LWC bundles present:**
  ```
  SELECT DeveloperName FROM LightningComponentBundle WHERE DeveloperName IN ('lwc_1','lwc_2')
  ```
  (If Tooling-API SOQL for `LightningComponentBundle` is unavailable in the active MCP config, fall back to `retrieve_metadata` with `LightningComponentBundle:[Name]` for each bundle — presence of the returned XML confirms deployment.)

Same SUCCESS / partial-FAILED rule as Phase 1.

### Phase 3 (Agentforce)

- **Agent active:**
  ```
  SELECT DeveloperName, Status FROM BotDefinition WHERE DeveloperName='[AgentName]'
  ```

If the agent exists and `Status='Active'` → treat as SUCCESS with `schema_validation_failed: true`. Do NOT retry — re-publishing an active agent risks state corruption and bumps the version number. Preserve the raw sub-agent output verbatim in the change log's Issues Encountered section under a `⚠️ SUB-AGENT OUTPUT SCHEMA VALIDATION FAILED` heading. Flag the sub-agent output as a lessons candidate — the schema the sub-agent emitted may reveal a drift vector worth patching.

## Data Seeding Integrity Probe (Phase 1 — runs unconditionally when `data_seeded[]` is non-empty)

A schema-valid envelope can still report a seeding failure as success — e.g. `{"object": "EmailMessage", "records": 0, "status": "SUCCESS"}`. The probes above only fire on parse/key failure, so a well-formed contradiction slips through. This probe runs **regardless of schema validity**, whenever Phase 1's `data_seeded[]` array has one or more rows. It removes the sub-agent from the trust path: expected counts come from the SPEC, actual counts come from the ORG.

**Step 1 — Cheap contradiction catch (always, before any query).** Scan every `data_seeded[]` row. Any row with `status: "SUCCESS"` AND `records: 0` is an immediate hard FAIL — a success cannot have seeded zero rows. Flag that object for re-seed.

**Step 2 — Parse expected counts from the SPEC, not the sub-agent.** In the spec's Data Seeding section, each object line carries a structured token: `Object: **<Name>**, Records: <N> (<VERB> ...` where `<VERB>` is CREATE or UPDATE. Regex each object's `<N>` and `<VERB>` directly from the spec. Do NOT use any count the sub-agent reported — the sub-agent is the component that may have lied.

**Step 3 — Probe the org, branching on VERB:**

- **CREATE** → count rows matching the spec's stable keys for that object; FAIL if `matched_count < N`. Use `>=`, never `==` — Salesforce auto-inserts paired rows the spec never counted (e.g. an outbound `EmailMessage` auto-creates a paired `Email:`-prefixed `Task`, so Task may legitimately exceed its spec count). Match on the spec's stable identifying keys, for example:
  ```
  SELECT COUNT() FROM EmailMessage WHERE ParentId='[CaseId]' AND Incoming=true
  SELECT COUNT() FROM Task WHERE WhatId='[CaseId]' AND Subject LIKE 'Pharmacovigilance%'
  SELECT COUNT() FROM CaseComment WHERE ParentId='[CaseId]' AND IsPublished=false
  ```
- **UPDATE** → ignore row count (the record already existed). Probe that the named target fields on the identified record are populated as the spec requires:
  - Fields the spec gives a **literal value** (e.g. `Regulatory_Market__c → EU`, `Market_Response_Path__c → On-label scientific exchange`, a Product Id) → exact-match: FAIL if the org value ≠ the spec value.
  - Fields the spec marks **⚠️ SE refines prose** (freeform `Scientific_Question__c`, `MSL_Response__c`) → presence-check only: FAIL if null/blank, PASS if non-empty (freeform prose can't be equality-checked).
  ```
  SELECT Regulatory_Market__c, Market_Response_Path__c, Product__c, Scientific_Question__c, MSL_Response__c FROM Case WHERE Id='[CaseId]'
  ```

**Step 4 — Degrade loud, never silent.** If an object appears in `data_seeded[]` but the spec has no parseable `Records: N` token for it (hand-edited or older spec with counts buried in prose), do NOT pass it implicitly. Probe `SELECT COUNT() ... ` for presence and surface the ambiguity to the SE:
> "Phase 1 seeded `[object]` but I couldn't parse an expected record count from the spec. The org shows [N] rows present. Confirm this is correct, or tell me the expected count."

An unparseable count must never become an implicit PASS — that reintroduces the original gap one level up.

**Step 5 — On FAIL.** Re-run the seed script's bulk path for the failed object(s) (or re-invoke the seeding step), then re-probe. This is a hard gate: do not report Phase 1 complete with a failed seeding probe. If re-seed fails twice, record the object as FAILED in the change log's Issues Encountered section with the probe's expected-vs-actual, and surface to the SE.

## Action-Invocation Probe (Phase 3 — runs unconditionally when an Agentforce agent was deployed Active)

Mirror of the Data Seeding Integrity Probe, one phase over: a sub-agent can report an agent `Active` with a coherent smoke-test transcript while the hero action never fired (the agent narrates "I'll flag it" and invokes nothing; or a hand-patched topic references an action with no resolvable I/O schema, so it can never be selected). The sub-agent's `smoke_test.action_invocation_confirmed` self-report and its CLI-preview transcript are NOT trusted here — the sub-agent is the component that may be wrong (it has cited `sf agent preview` interfaces that don't exist in the installed CLI). This probe runs **regardless of what the sub-agent reported**, whenever `deployed.agent.status == "Active"`. Expected behaviour comes from the SPEC's hero action; actual comes from the ORG.

The probe runs as a LADDER in this order — structural first (deterministic, no live turn), then runtime confirmation, then corroboration. Do NOT lead with the record-write check: its negative is ambiguous and an affirmative live write mutates demo data the SE must then reset.

**Step 1 — Identify the hero action + its expected effect from the SPEC.** From the spec's Agentforce section, read the primary ("hero") action and what firing it does — its API name (for the event-log check) and, if any, the object + field(s) it writes (for corroboration).

**Step 2 — PRIMARY: localActions structural gate (deterministic, on-disk, no live turn).** This is the real catch — it isolates the structural defect itself, not a downstream symptom, and on a modify-existing build it has already run pre-deploy in phase3.md. Re-confirm it here against the deployed bundle on disk using the SAME `<fullName>`-based structural join phase3.md uses (parse each Topic plugin's `<fullName>` from the bundle XML; require `localActions/<fullName>/` to exist with one non-empty `input/schema.json` + `output/schema.json` per `<functionName>`; exclude the parallel `plannerActions/` subtree). A topic referenced in the planner graph with NO `localActions/<fullName>/` folder is a dead topic regardless of what the transcript said — hard FAIL. Do NOT match on topic/action names — the folders carry unknowable 18-char metadata-Id suffixes; the topic's `<fullName>` IS the folder name, and a hand-patched dead topic has no folder at all.

**Step 3 — Runtime confirmation: event-log FunctionStep (post-activate).** Enabling the log is step 0, not optional — if "Keep a record of conversations with enhanced event logs" is OFF, the query returns zero rows and you'd misread "no rows" as "action didn't fire" when it's really "logging was off."
   a. Enable enhanced event logs on the agent (Edit Agent Details → "Keep a record of conversations with enhanced event logs") if not already on.
   b. Send ONE test turn through any working channel that should fire the hero action.
   c. Query:
   ```sql
   SELECT StepType, Action, EventTarget, IsSuccessful, ConversationTurn FROM ConversationDefinitionEventLog WHERE CreatedDate = TODAY ORDER BY CreatedDate DESC
   ```
   A `FunctionStep` row naming the hero action with `IsSuccessful = true` = confirmed invocation = PASS. Turn rows that are only `Message`/`CancelDialog`/`Transfer` with ZERO `FunctionStep` = the action never fired = FAIL. (The object is `ConversationDefinitionEventLog` — there is no `GenAiInteraction`.)

**Step 4 — Corroboration only: record-write SOQL (NOT a lead signal).** If the hero action writes a record, SOQL the target for the expected change to corroborate a Step-3 PASS:
   ```sql
   SELECT [field(s) the action sets] FROM [Object] WHERE [stable key from the test turn] ORDER BY LastModifiedDate DESC LIMIT 1
   ```
   A changed field is strong positive proof. An unchanged/null field proves NOTHING on its own — no turn may have attempted a write — so never use this as the discriminator; use it to confirm a FunctionStep row, not to lead.

**Step 5 — On FAIL.** Do NOT report the agent "Active/working." Override the sub-agent's report: set the agent's status to **"deployed but NOT validated — hero action invocation not confirmed in org"** for the change log and handover brief, record the probe's expected-vs-actual (verbatim org result) in the change log's Issues Encountered section, and surface to the SE. This is NOT a hard stop on the deployment (the agent may still demo for routing/conversation) — it is an honesty gate: the SE must see "deployed but unvalidated" rather than a false green. If Step 2 found a missing `localActions/<fullName>/` folder, flag it as the root cause and recommend re-adding the action via the Builder wizard (which regenerates the schema with its proper Id).

**Step 6 — Degrade loud, never silent.** If the spec has no parseable hero action, or the org can't be probed (event logs unavailable AND no observable write), do NOT pass implicitly. Surface to the SE:
> "Phase 3 deployed agent `[name]` Active, but I couldn't independently confirm its hero action fired (no observable write and event logs unavailable). Reporting it deployed-but-unvalidated. Confirm in a live Messaging Session, or tell me the expected record effect so I can probe."
