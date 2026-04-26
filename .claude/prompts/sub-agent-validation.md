# Sub-Agent Output Validation

Loaded on-demand by scout-building.md Step 7 between every sub-agent return and the next phase. Procedure for validating JSON output AND empirically probing the org when validation fails.

## Procedure

After EVERY sub-agent returns, validate its output before proceeding:

1. Extract the fenced `json` block from the sub-agent's response.
2. Parse it. If parsing succeeds and the top-level keys match the phase schema, validation passes. Required top-level keys:
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
