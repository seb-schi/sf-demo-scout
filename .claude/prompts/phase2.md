You are deploying Flows, Apex, and/or LWC to org {{ORG_ALIAS}} ({{ORG_USERNAME}}).
The SE has already confirmed this deployment. Work autonomously — do not ask for further confirmation.
Use MCP tools (deploy_metadata, retrieve_metadata, run_soql_query, run_code_analyzer) for all operations.
Salesforce Docs MCP (`salesforce_docs_search`, `salesforce_docs_fetch`) is available for unfamiliar-error recovery — not for pre-flight checks.

**Platform Constraints:** if the spec includes a `### Platform Constraints` section, read it BEFORE generating any Apex or data-related code. Objects flagged with restrictions (IsEverCreatable=false, managed namespace, not queueable) require specific patterns — see the Dynamic SOQL template below. Do not generate static type references for restricted objects. Note: Platform Constraints are initial assessments from sparring's EntityDefinition queries — they may be incomplete. If a deployment fails in a way that contradicts these constraints, trust the deploy-time error over the spec's assessment. Record the contradiction in `discovery_notes`.

## Skills Available
Invoke these skills via the Skill tool when you need detailed rules:
- `sf-flow` — flow design and 110-point validation checklist (invoke before generating Flow XML)
- `sf-apex` — Apex generation rules and 150-point scoring (invoke only if Apex is in scope)
- `sf-lwc` — LWC scaffolding with PICKLES methodology and 165-point scoring (invoke before generating any LWC bundle — SLDS 2, accessibility, wire patterns)
- `sf-testing` — Apex test execution and agentic test-fix loops (invoke when Apex deployment tests fail — up to 3 automated fix iterations before skipping)
- `demo-docs-consultation` — decision tree for when to consult Salesforce Docs MCP (load on unfamiliar deploy errors)

## Deployment Rules

**Two-attempt rule:** if a deployment fails twice, STOP that item, record it as SKIPPED in your JSON output with the error message, and continue with remaining items.

**Unfamiliar errors:** if the error message is not self-evident, invoke the `demo-docs-consultation` skill before the second attempt. Record the consultation in `docs_consulted`.

Deploy in small increments. One component per deploy call.

<!-- IF:FLOWS -->
### Flow Rules
Autonomous-with-SE-gate scope covers the full trigger spectrum the `sf-flow` skill owns — record-triggered (before-save, after-save, before-delete; any object; cross-object DML allowed), screen flows (whitelist below), autolaunched flows, subflows, scheduled flows, and platform-event-triggered flows. Orchestration flows (parent-child / sequential / conditional) and complex screen flows → skip with reason "out of scope for autonomous deploy — SE Manual Checklist."

Screen-flow component whitelist: DisplayText, Section, InputField (Text / LargeTextArea / Number / Email / Date / DateTime / Password), Picklist, RadioButtons, Checkbox, CheckboxGroup, MultiSelectPicklist. Anything else (Repeater, Data Table, Kanban Board, File Upload/Preview, custom LWC screen component) → skip.

**Template sources.** The `sf-flow` skill ships canonical XML templates under `.claude/skills/sf-flow/assets/`:
- `record-triggered-before-save.xml`, `record-triggered-after-save.xml`, `record-triggered-before-delete.xml`
- `screen-flow-template.xml`, `screen-flow-with-lwc.xml` (LWC variant out of autonomous scope)
- `autolaunched-flow-template.xml`
- `scheduled-flow-template.xml`
- `platform-event-flow-template.xml`
- `subflows/` — reusable subflow patterns (bulk-updater, dml-rollback, email-alert, error-logger, query-with-retry, record-validator)
- `elements/` — get-records, loop, record-delete, transform element patterns

Reference guides: skim `.claude/skills/sf-flow/references/xml-gotchas.md` before any XML work (root-level alphabetical ordering, fault-connector self-reference, relationship-field trap, storeOutputAutomatically data leak). Per-category references (`flow-best-practices.md`, `testing-guide.md`, `wait-patterns.md`, `subflow-library.md`, `transform-vs-loop-guide.md`) as needed.

**Deployment order within Phase 2.** Deploy subflows before their parent flows (same-phase dependency). Platform-event-triggered flows require the `<eventType>` object — if the spec ships a new platform event in this deploy, the event object deploys before the flow. Scheduled flows have no in-phase dependencies.

1. Invoke `sf-flow` skill before generating Flow XML.
2. Use the matching template from the asset list above as the starting point. Record-triggered-after-save is inlined below because it carries the `processMetadataValues` deployment-blocker rule and the Record Update pattern — both load-bearing beyond what the asset file covers.
3. Deploy as Draft first (`<status>Draft</status>`), confirm success.
4. **Validation — happy-path FlowTest is mandatory for every autonomous flow type.** Generate a happy-path FlowTest XML (template below — save as `[FlowApiName]_Test.flowTest-meta.xml`), deploy it alongside the flow, then run `sf flow run test --class-names [FlowApiName]_Test --target-org [alias] --json`. Pass → activate. Fail twice → skip activation, record in `issues`. FlowTest supports every flow type via MDAPI even though Flow Builder's auto-test UI is limited to record-triggered + data-cloud-triggered (Salesforce docs, 2026-04-30). Type-specific test adaptations:
   - **Record-triggered:** `<parameters>` supplies `$Record` via `triggeringRecordInitialValues`.
   - **Before-delete:** test asserts the pre-delete state; delete is the triggering event, assertion checks flow ran without fault.
   - **Screen flow:** one `<parameters>` block per required input variable.
   - **Autolaunched / subflow:** `<parameters>` supplies invocation inputs via flow variables.
   - **Scheduled:** test exercises the flow body on-demand, ignoring the schedule trigger. Schedule itself is a config read-back (`retrieve_metadata` on the deployed flow confirms `<schedule>` fields match the spec).
   - **Platform-event-triggered:** `<parameters>` supplies a mock event payload (one `<parameters>` block per event field referenced by the flow).
5. **Screen flows with QuickAction wiring** (spec requests it): deploy a `QuickAction` (actionType=Flow) pointing at the flow's API name; retrieve the target object's active Layout, add the QuickAction under `<quickActionListItems>`, redeploy the layout.
6. **Scheduled flow pre-flight:** confirm the spec's Scheduled Flow section names `<startDate>`, `<startTime>`, and `<frequency>` (Once / Daily / Weekly / Monthly / Yearly / Hourly / Weekdays — per FlowSchedule subtype, Salesforce docs API v66.0+). If missing, skip with reason "scheduled flow missing schedule fields — SE must add to spec."
7. **Platform-event flow pre-flight:** confirm the `<eventType>` object exists via `retrieve_metadata` (CustomObject with `__e` suffix, or standard event like `AIPredictionEvent`). If missing and not in-scope for this deploy, skip with reason "platform event object not in org — SE must create or import first."
8. Check for existing flows on the same object/trigger via `retrieve_metadata` — flag execution order conflicts in `discovery_notes`.
9. Rollback: `sf project delete source --metadata Flow:[FlowApiName] --target-org [alias]` (plus `QuickAction:[Name]` if deployed, plus `FlowTest:[FlowApiName]_Test` if deployed).

**CRITICAL — Flow XML must not use `processMetadataValues`.** Use this record-triggered after-save template:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Flow xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>62.0</apiVersion>
    <status>Draft</status>
    <label>Flow Label Here</label>
    <description>Brief description</description>
    <interviewLabel>Flow_Label_Here-{!$Flow.CurrentDateTime}</interviewLabel>
    <environments>Default</environments>
    <triggerOrder>500</triggerOrder>

    <!-- Start element: defines trigger object, type, and entry conditions -->
    <start>
        <locationX>50</locationX>
        <locationY>0</locationY>
        <connector>
            <targetReference>first_action_or_decision</targetReference>
        </connector>
        <filterLogic>and</filterLogic>
        <filters>
            <field>FieldApiName__c</field>
            <operator>EqualTo</operator>
            <value>
                <stringValue>SomeValue</stringValue>
            </value>
        </filters>
        <object>ObjectApiName</object>
        <recordTriggerType>CreateAndUpdate</recordTriggerType>
        <triggerType>RecordAfterSave</triggerType>
    </start>

    <!-- Decision element (conditional branching) -->
    <decisions>
        <name>check_condition</name>
        <label>Check Condition</label>
        <locationX>176</locationX>
        <locationY>200</locationY>
        <defaultConnector>
            <targetReference>end_element_or_other</targetReference>
        </defaultConnector>
        <defaultConnectorLabel>Default</defaultConnectorLabel>
        <rules>
            <name>condition_met</name>
            <conditionLogic>and</conditionLogic>
            <conditions>
                <leftValueReference>$Record.FieldApiName__c</leftValueReference>
                <operator>EqualTo</operator>
                <rightValue>
                    <stringValue>TargetValue</stringValue>
                </rightValue>
            </conditions>
            <connector>
                <targetReference>create_record_action</targetReference>
            </connector>
            <label>Condition Met</label>
        </rules>
    </decisions>

    <!-- Create Records action -->
    <recordCreates>
        <name>create_record_action</name>
        <label>Create Record</label>
        <locationX>264</locationX>
        <locationY>400</locationY>
        <inputAssignments>
            <field>Subject</field>
            <value>
                <stringValue>Auto-created record</stringValue>
            </value>
        </inputAssignments>
        <inputAssignments>
            <field>Priority</field>
            <value>
                <stringValue>High</stringValue>
            </value>
        </inputAssignments>
        <object>Task</object>
    </recordCreates>
</Flow>
```
Adapt this template for your spec. Key rules:
- Use `<triggerType>RecordAfterSave</triggerType>` (not RecordBeforeSave) for any flow that creates/updates related records
- Entry conditions go in `<start><filters>`
- For RecordType filters, use a Decision element with `$Record.RecordType.DeveloperName` — do NOT put RecordType in start filters (schema validation issues)
- `<triggerOrder>500</triggerOrder>` is safe default for no-conflict scenarios

**Common Flow variable references:**
- Current user: `{!$User.Id}` — do NOT use `$Flow.CurrentUserID` (does not exist)
- Current record: `{!$Record.FieldName}` in formulas, `$Record` as inputReference
- Current date/time: `{!$Flow.CurrentDateTime}`, `{!$Flow.CurrentDate}`

**Record Update (triggering record) pattern — after-save flows:**
```xml
<recordUpdates>
    <name>update_triggering_record</name>
    <label>Update Triggering Record</label>
    <locationX>176</locationX>
    <locationY>400</locationY>
    <inputReference>$Record</inputReference>
    <inputAssignments>
        <field>FieldApiName__c</field>
        <value>
            <stringValue>NewValue</stringValue>
        </value>
    </inputAssignments>
</recordUpdates>
```
Key rules for updating the triggering record:
- Use `<inputReference>$Record</inputReference>` — NOT filters
- Field assignments go in `<inputAssignments>`, not `<filters>`
- This pattern works for after-save triggers — before-save triggers use `$Record` assignments directly in the start element

Screen flow template lives at `.claude/skills/sf-flow/assets/screen-flow-template.xml` (full clone guarantees presence). For screen flows, two rules from the asset that tend to get lost: root-level elements must stay in strict alphabetical order (apiVersion → description → environments → interviewLabel → label → processType → recordCreates → screens → start → status → variables), and in `recordLookups` always specify `<queriedFields>` explicitly — never `<storeOutputAutomatically>true</storeOutputAutomatically>` on screen flows (data-leak risk, especially on Experience Cloud).

**FlowTest template** (applies to every autonomous flow type — type-specific adaptations in step 4 above). Save as `[FlowApiName]_Test.flowTest-meta.xml`, deploy alongside the flow, then run `sf flow run test --class-names [FlowApiName]_Test --target-org [alias] --json`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<FlowTest xmlns="http://soap.sforce.com/2006/04/metadata">
    <description>Happy-path smoke test for [FlowApiName]</description>
    <flowApiName>[FlowApiName]</flowApiName>
    <label>[FlowApiName] Happy Path</label>
    <testPoints>
        <assertions>
            <conditionLogic>and</conditionLogic>
            <conditions>
                <leftValueReference>$Flow.FaultMessage</leftValueReference>
                <operator>IsNull</operator>
                <rightValue><booleanValue>true</booleanValue></rightValue>
            </conditions>
            <errorMessage>Flow produced a fault on the happy path</errorMessage>
        </assertions>
        <elementApiName>Create_Record</elementApiName>
        <parameters>
            <leftValueReference>var_RecordName</leftValueReference>
            <type>Input</type>
            <value><stringValue>Test Record</stringValue></value>
        </parameters>
        <testPointName>AfterCreate</testPointName>
        <type>FinalOutput</type>
    </testPoints>
</FlowTest>
```
Adapt: `flowApiName` is the flow under test. One `<parameters>` block per required input variable, with a value that satisfies all validation rules. Assertion checks `$Flow.FaultMessage IS NULL` — passes if the flow runs to completion without a fault. For recordCreates/recordUpdates, add a second assertion on the created record's key field if the test should also validate DML outcome.
<!-- /IF:FLOWS -->

<!-- IF:APEX -->
### Apex Rules
Scope: single-trigger, single-object. No test classes (demo org context).
1. Invoke `sf-apex` skill for generation rules.
2. Run `run_code_analyzer` before deploying (if MCP available). Record high-severity findings in `issues`.
3. If the spec's Platform Constraints section flags any object with restrictions, follow the dynamic SOQL pattern below for that object.
4. If compile or runtime tests fail on the first deploy attempt, invoke `sf-testing` before the second attempt — it runs an agentic fix loop that diagnoses the failure and patches the code. Record the loop outcome in `discovery_notes` (iterations run, whether loop succeeded). The two-attempt rule still applies: one sf-testing loop counts as one attempt.
5. Rollback: `sf project delete source --metadata ApexClass:[ClassName] --target-org [alias]`

**InvocableMethod pattern (for Agentforce backing actions).** Use this template:
```java
public with sharing class ActionNameHere {
    @InvocableMethod(label='Action Label' description='What the action does — Agentforce LLM reads this')
    public static List<OutputParameters> execute(List<InputParameters> inputs) {
        List<OutputParameters> outputs = new List<OutputParameters>();
        for (InputParameters input : inputs) {
            OutputParameters output = new OutputParameters();
            // action logic here
            output.result = 'value';
            outputs.add(output);
        }
        return outputs;
    }

    public class InputParameters {
        @InvocableVariable(required=true label='Input Label' description='What this input is — agent uses this to map values')
        public String inputField;
    }

    public class OutputParameters {
        @InvocableVariable(label='Output Label' description='What this output contains')
        public String result;
    }
}
```
Key rules:
- `with sharing` — Agentforce executes in user context
- `description` on BOTH `@InvocableMethod` and every `@InvocableVariable` — the agent LLM uses these to discover and invoke the action. Missing descriptions = agent can't find/use the action.
- Inner classes for Input/Output (not top-level classes)
- `List<>` wrapping on method params AND return type (bulkification contract)
- Loop over inputs — do not use `inputs[0]` shortcut

**Dynamic SOQL pattern (for managed/industry objects).** When the spec's Platform Constraints flag an object (IsEverCreatable=false, managed namespace, etc.), use dynamic SOQL with bind variables — never static type references:
```java
// Static type reference — FAILS for managed/industry objects at compile time
Inquiry inq = [SELECT Id, Subject FROM Inquiry WHERE Id = :recordId];

// Dynamic SOQL with bind variable — CORRECT for restricted objects
String objectName = 'Inquiry';
String query = 'SELECT Id, Subject FROM ' + objectName + ' WHERE Id = :recordId';
SObject record = Database.query(query);
String subject = (String) record.get('Subject');
```
Key rules:
- Use bind variables (`:recordId`) for Id/String values — NOT string concatenation with escapeSingleQuotes
- Use `.get('FieldName')` for all field access on the generic SObject — no casting to a typed object
- Only the object name and field names are dynamic strings; values always use bind variables
- This pattern is required whenever Platform Constraints mention a managed or industry object
<!-- /IF:APEX -->

<!-- IF:LWC -->
### LWC Rules
Scope: demo-specific UI — Customer 360 Cards, custom record views, branded components.
1. Invoke `sf-lwc` skill BEFORE generating any component file. The skill enforces PICKLES methodology, SLDS 2 compliance, dark mode support, accessibility (WCAG/ARIA), and Jest test patterns across a 165-point rubric.

**Mock data when no backing data source exists.** If the spec describes UI with no objects/fields/Apex class supplying data (no wire target, no Apex `@AuraEnabled` method referenced, no Data Cloud or external source), hardcode realistic mock data directly in the component's JS file and skip the wire service. Demo orgs often have no seeded data for new objects at LWC deploy time — a component that renders a spinning wheel breaks the demo worse than hardcoded values. Use industry-appropriate terminology (medtech device names, pharma product SKUs, etc. per the Customer Context in the spec). When the spec DOES name a backing data source, follow `sf-lwc` wire patterns normally.

2. Use MCP LWC expert tools when available (scaffolding, SLDS, validation) — these complement sf-lwc's guidance.
3. Run `run_code_analyzer` before deploying (if MCP available). Record high-severity findings in `issues`.
4. Rollback: `sf project delete source --metadata LightningComponentBundle:[ComponentName] --target-org [alias]`

**LWC meta XML template.** Every component needs a `componentName.js-meta.xml`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<LightningComponentBundle xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>62.0</apiVersion>
    <isExposed>true</isExposed>
    <masterLabel>Component Display Name</masterLabel>
    <description>Brief component description</description>
    <targets>
        <target>lightning__RecordPage</target>
    </targets>
    <targetConfigs>
        <targetConfig targets="lightning__RecordPage">
            <objects>
                <object>Account</object>
            </objects>
        </targetConfig>
    </targetConfigs>
</LightningComponentBundle>
```
Key rules:
- `apiVersion` is MANDATORY (Spring '25+) — always include it
- `isExposed` must be `true` for any component placed on pages or used in builders
- Valid demo targets: `lightning__RecordPage` (record pages), `lightning__AppPage` (app pages), `lightning__HomePage` (home page), `lightning__FlowScreen` (flow screens)
- For Agentforce action UIs: use `lightning__AgentforceInput` (user input) or `lightning__AgentforceOutput` (display data)
- Object filtering goes in `targetConfigs` > `targetConfig` > `objects` — limits which record pages show the component
- `masterLabel` and `description` are optional but recommended for discoverability in App Builder
<!-- /IF:LWC -->

## What Phase 1 Already Deployed
{{PHASE1_SUMMARY}}

## Your Spec
{{SPEC_SECTIONS}}

## Output Format
Return EXACTLY one fenced JSON block matching this schema. Do not include any prose outside the block.

```json
{
  "phase": 2,
  "deployed": [
    {"type": "Flow|ApexClass|ApexTrigger|LightningComponentBundle", "api_name": "string", "status": "SUCCESS|FAILED", "flow_status": "Active|Draft|null"}
  ],
  "skipped": [
    {"type": "string", "api_name": "string", "reason": "string"}
  ],
  "rollback_commands": ["string"],
  "discovery_notes": [
    "string — things that worked differently than the spec assumed, OR design constraints on deliverable artifacts (script portability, runtime-environment observations, library availability) if this phase produced a reusable script. Include raw error messages verbatim. Examples: 'MedicalInsight: spec assumed static SOQL safe, but compiler returned [Error: sObject type MedicalInsight is not supported] — switched to dynamic SOQL', 'target SE Mac runs Bash 3.2 — avoided declare -A in the data-factory script, used temp-file JSON for state handoff'. Canonical discovery_notes-vs-issues split: see `demo-deployment-rules` §Script Deliverable Rules."
  ],
  "docs_consulted": [
    {"question": "string", "url": "string", "verdict": "string"}
  ],
  "issues": ["string"]
}
```
