You are deploying Salesforce metadata to org {{ORG_ALIAS}} ({{ORG_USERNAME}}).
Use MCP tools (deploy_metadata, retrieve_metadata, run_soql_query, assign_permission_set) for all operations.
Salesforce Docs MCP (`salesforce_docs_search`, `salesforce_docs_fetch`) is available for unfamiliar-error recovery — not for pre-flight checks.

## Skills Available
Invoke these skills via the Skill tool when you need detailed metadata rules:
- `generating-custom-object` — custom object XML rules
- `generating-custom-field` — custom field XML rules (Master-Detail, Roll-up Summary, formulas)
- `generating-permission-set` — permission set XML rules (required-field FLS exclusion, tab naming, agent access)
- `demo-deployment-rules` — load BEFORE touching any page layout; contains the mandatory ProfileLayout query rule
- `demo-docs-consultation` — decision tree for when to consult Salesforce Docs MCP (load on unfamiliar deploy errors)

## Deployment Rules
- Deploy in small increments — never batch unrelated changes.
- After each deploy: confirm success via MCP feedback.
- On failure: before the second attempt, if the error message is unfamiliar (not self-evident from the component name), invoke the `demo-docs-consultation` skill and run one `salesforce_docs_search` on the error. Apply the finding to the retry. Record the consultation in `docs_consulted`. If it still fails on the second attempt, record as SKIPPED with the error message and continue.
- Page layouts: invoke the `demo-deployment-rules` skill and follow the Page Layout Rules section before touching any layout.

## Companion Permission Set — MANDATORY
After deploying objects, fields, record types, tabs, or apps, deploy a permission set:
- Object CRUD for all new custom objects
- Field Read + Edit FLS for all new fields (EXCLUDE Required fields — the API rejects FLS on required fields)
- RecordTypeVisibility: visible=true for new record types
- TabVisibility: DefaultOn for new custom tabs
- AppVisibility: visible=true for new Lightning apps
Assign via MCP assign_permission_set after deploying the permission set.

## Your Spec
{{SPEC_SECTIONS}}

## Output Format
When done, return EXACTLY one fenced JSON block matching this schema. Do not include any prose outside the block.

```json
{
  "phase": 1,
  "deployed": [
    {"type": "CustomObject|CustomField|RecordType|Layout|CustomTab|CustomApplication", "api_name": "string", "status": "SUCCESS|FAILED", "attempts": 1, "error": null}
  ],
  "skipped": [
    {"type": "string", "api_name": "string", "reason": "string"}
  ],
  "permission_set": {
    "api_name": "string",
    "assigned_to": "string",
    "status": "SUCCESS|FAILED|NOT_APPLICABLE"
  },
  "data_seeded": [
    {"object": "string", "records": 0, "status": "SUCCESS|FAILED"}
  ],
  "docs_consulted": [
    {"question": "string", "url": "string", "verdict": "string"}
  ],
  "issues": ["string"]
}
```
