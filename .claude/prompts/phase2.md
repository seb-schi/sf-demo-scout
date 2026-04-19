You are deploying Flows, Apex, and/or LWC to org {{ORG_ALIAS}} ({{ORG_USERNAME}}).
The SE has already confirmed this deployment. Work autonomously — do not ask for further confirmation.
Use MCP tools (deploy_metadata, retrieve_metadata, run_soql_query, run_code_analyzer) for all operations.
Salesforce Docs MCP (`salesforce_docs_search`, `salesforce_docs_fetch`) is available for unfamiliar-error recovery — not for pre-flight checks.

## Skills Available
Invoke these skills via the Skill tool when you need detailed rules:
- `sf-flow` — flow design and 110-point validation checklist (invoke before generating Flow XML)
- `sf-apex` — Apex generation rules and 150-point scoring (invoke only if Apex is in scope)
- `demo-docs-consultation` — decision tree for when to consult Salesforce Docs MCP (load on unfamiliar deploy errors)

## Deployment Rules

**Two-attempt rule:** if a deployment fails twice, STOP that item, record it as SKIPPED in your JSON output with the error message, and continue with remaining items.

**Unfamiliar errors:** if the error message is not self-evident, invoke the `demo-docs-consultation` skill before the second attempt. Record the consultation in `docs_consulted`.

Deploy in small increments. One component per deploy call.

### Flow Rules
Scope: single-object, record-triggered only. If a complex flow (screen, scheduled, subflow) reaches you, skip it: "out of scope for autonomous deploy."

1. Invoke `sf-flow` skill before generating Flow XML.
2. Deploy as Draft first (`<status>Draft</status>`), confirm success, then activate.
3. Check for existing flows on the same object via `retrieve_metadata` — flag execution order conflicts.
4. Rollback: `sf project delete source --metadata Flow:[FlowApiName] --target-org [alias]`

**CRITICAL — Flow XML pattern.** Do NOT use `processMetadataValues`. Use this record-triggered after-save template:
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
- Entry conditions go in `<start><filters>`, not in `processMetadataValues`
- For RecordType filters, use a Decision element with `$Record.RecordType.DeveloperName` — do NOT put RecordType in start filters (schema validation issues)
- `<triggerOrder>500</triggerOrder>` is safe default for no-conflict scenarios

### Apex Rules
Scope: single-trigger, single-object. No test classes (demo org context).
1. Invoke `sf-apex` skill for generation rules.
2. Run `run_code_analyzer` before deploying (if MCP available). Record high-severity findings in `issues`.
3. Rollback: `sf project delete source --metadata ApexClass:[ClassName] --target-org [alias]`

### LWC Rules
Scope: demo-specific UI — Customer 360 Cards, custom record views, branded components.
1. Use MCP LWC expert tools when available (scaffolding, SLDS, validation).
2. Run `run_code_analyzer` before deploying (if MCP available). Record high-severity findings in `issues`.
3. Rollback: `sf project delete source --metadata LightningComponentBundle:[ComponentName] --target-org [alias]`

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
  "docs_consulted": [
    {"question": "string", "url": "string", "verdict": "string"}
  ],
  "issues": ["string"]
}
```
