<!-- Parent: sf-flow/SKILL.md -->
# Multi-Skill Orchestration: sf-flow Perspective

This document details how sf-flow fits into the multi-skill workflow for Salesforce development.

---

## Standard Orchestration Order

1. Confirm referenced objects and fields. For missing, approved dependencies use `platform-custom-object-generate` and `platform-custom-field-generate`.
2. Author the Flow and eligible FlowTests with `sf-flow`.
3. Use `platform-metadata-deploy` for the authorized deployment; preserve the caller's exact-version test and activation gate.
4. Use `platform-data-manage` only for separately in-scope data setup or bulk verification.

Existing schema does not need to be recreated. An unavailable or unapproved dependency is a gap to report, not permission to add it.


---

## Confirm Schema Dependencies

| sf-flow Uses | Schema prerequisite | What Fails Without It |
|--------------|------------------|----------------------|
| Object references | Custom Objects | `Invalid reference: Quote__c` |
| Field references | Custom Fields | `Field does not exist: Status__c` |
| Picklist values | Picklist Fields | Flow decision uses non-existent value |
| Record Types | Record Type metadata | `Invalid record type: Inquiry` |

**Rule**: Verify referenced schema first. Create only missing dependencies within the approved scope, using the object or field skill as appropriate.

---

## sf-flow's Role in the Triangle Architecture

Flow acts as the **orchestrator** in the Flow-LWC-Apex triangle:

```
                    ┌─────────────────────┐
                    │       FLOW          │◀── YOU ARE HERE
                    │  (Orchestrator)     │
                    └──────────┬──────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
         ▼                     ▼                     │
┌─────────────────┐   ┌─────────────────┐           │
│   LWC Screen    │   │  Apex Invocable │           │
│   Component     │   │     Action      │           │
└────────┬────────┘   └────────┬────────┘           │
         │    @AuraEnabled     │                     │
         └──────────┬──────────┘                     │
                    ▼                                │
         ┌─────────────────────┐                     │
         │   Apex Controller   │─────────────────────┘
         └─────────────────────┘   Results back to Flow
```

See `references/triangle-pattern.md` for detailed Flow XML patterns.

---

## Integration + Agentforce Extended Order

When building agents with Flow actions:

Use `platform-apex-generate` for approved invocable actions, `sf-flow` for the Flow wrapper, `platform-metadata-deploy` for deployment, and `agentforce-generate` for Agent Script authoring and lifecycle guidance. Deploy dependencies before their consumers; the caller controls publication and activation.

External authentication, Named Credentials, and External Services require their own confirmed supported route and approved scope. This skill does not depend on absent `sf-connected-apps` or `sf-integration` skills.


---

## Flows for Agentforce: Critical Requirements

When creating Flows that will be called by Agentforce agents:

### 1. Variable Name Matching

Agent Script input/output names MUST match Flow variable API names exactly:

```xml
<!-- Flow variable -->
<variables>
    <name>inp_AccountId</name>
    <dataType>String</dataType>
    <isInput>true</isInput>
</variables>
```

```yaml
# Agent Script action - names must match!
actions:
  - name: GetAccountDetails
    target: flow://Get_Account_Details
    inputs:
      - name: inp_AccountId  # Must match Flow variable name
        source: slot
```

### 2. Flow Requirements for Agents

| Requirement | Why |
|-------------|-----|
| Autolaunched or Screen Flow | Record-triggered flows cannot be called directly |
| `isInput: true` for inputs | Agent needs to pass values |
| `isOutput: true` for outputs | Agent needs to read results |
| Descriptive variable names | Agent uses these in responses |

### 3. Common Integration Errors

| Error | Cause | Fix |
|-------|-------|-----|
| "Internal Error" on publish | Variable name mismatch | Match Flow var names exactly |
| "Flow not found" | Flow not deployed | platform-metadata-deploy before agentforce-generate |
| Agent can't read output | Missing `isOutput: true` | Add output flag to Flow variable |

---

## Cross-Skill Integration Table

| From Skill | To sf-flow | When |
|------------|------------|------|
| agentforce-generate | → sf-flow | "Create Autolaunched Flow for agent action" |
| platform-apex-generate | → sf-flow | "Create Flow wrapper for Apex logic" |
| Approved integration work | → sf-flow | Create an HTTP Callout Flow after its dependencies are confirmed |

| From sf-flow | To Skill | When |
|--------------|----------|------|
| sf-flow | → platform-custom-object-generate / platform-custom-field-generate | verify Invoice__c fields using an approved describe tool |
| sf-flow | → platform-metadata-deploy | "Deploy flow with --dry-run" |
| sf-flow | → platform-data-manage | "Create 200 test Accounts" (after deploy) |

---

## Deployment Order for Flow Dependencies

When deploying Flows that reference Apex or LWC:

```
1. APEX CLASSES        (if @InvocableMethod called)
   └── Deploy first

2. LWC COMPONENTS      (if used in Screen Flow)
   └── Deploy second

3. FLOWS               ◀── Deploy LAST
   └── References deployed Apex/LWC
```

---

## Best Practices

1. **Always verify objects exist** before creating Flow references
2. **Use the approved object/field describe tool** to confirm field API names
3. **Deploy as Draft first** for complex flows
4. **Test with 251 records** for bulk safety
5. **Match variable names exactly** when creating for Agentforce

---

## Related Documentation

| Topic | Location |
|-------|----------|
| Triangle pattern (Flow perspective) | `sf-flow/references/triangle-pattern.md` |
| LWC integration | `sf-flow/references/lwc-integration-guide.md` |
| Apex action template | `sf-flow/assets/apex-action-template.xml` |
| agentforce-generate | `agentforce-generate/SKILL.md` |
