# Data Shape Validation — Stage 6b

Loaded on demand by scout-sparring when the scenario has Apex, Flows, or Agentforce actions (i.e., objects queried or written to programmatically). Runs inline — no sub-agent needed.

## Scope

For every object the scenario's Apex, Flow, or Agentforce action will **query or write to** — not objects that only receive new fields or layouts.

## Procedure per object

1. **Sample real records** — `SELECT [key fields from scenario] FROM [Object] LIMIT 5`. If a field errors (e.g., "No such column"), that itself is a finding.
2. **Check lookup population** — for any lookup field the scenario depends on (e.g., `VisitId`, `AccountId`): `SELECT COUNT(Id) FROM [Object] WHERE [LookupField] != null`. If 0% populated, the scenario's join path is broken.
3. **Check field filterability** — for any field the scenario uses in a WHERE clause or GROUP BY: `SELECT QualifiedApiName, DataType FROM FieldDefinition WHERE EntityDefinition.QualifiedApiName = '[Object]' AND QualifiedApiName = '[Field]'`. Long Text Area and rich text fields are not filterable — if the scenario depends on filtering them, flag it.

**Budget:** 3-6 SOQL queries per action-relevant object. Most scenarios touch 1-3 objects. Queries are fast and sequential (each informs the next).

## Describe-before-spec — Data Seeding objects only

If the scenario includes a Data Seeding section with explicit field mappings (not just record counts), run `sf sobject describe` on EVERY target object BEFORE the spec is written. This is in addition to the three steps above — describe is cheaper and catches a different failure class (field-name assumptions, picklist-vs-string, record-type DeveloperName mismatches).

1. For each Data Seeding object: `sf sobject describe --sobject [Object] --target-org [alias] --json` (or use MCP retrieve when available).
2. Cross-check EVERY field name the seed plan references against the describe output. Common traps:
   - Junction/lookup fields whose API name differs from the related object (e.g., `SubjectAssignment.AssignmentId`, not `MedicalInsightId`).
   - RecordType `DeveloperName` ≠ label (e.g., `LSDO_Healthcare_Provider`, not `Healthcare Provider`). Query `SELECT DeveloperName FROM RecordType WHERE SobjectType='[Object]'` to confirm.
   - Picklist fields vs free-text fields with similar names (e.g., `Subject.UsageType` is a picklist, not a text field) — check `picklistValues` in the describe output.
3. If a field name or record-type name in the spec draft doesn't match the describe output, correct the spec before writing it to disk. These corrections are sparring-time findings, not building-time surprises.

**Budget:** ~20 seconds per object (one describe call). Scoped to Data Seeding sections only — objects touched purely by new fields or layouts don't need this.

## Surface findings to the SE

> "Data shape validation for [objects]:
> - [Object]: [field] populated on [X]% of records, [field] is [DataType] (not filterable in WHERE) ...
> - [Object]: sample records look healthy, all assumed fields present and populated.
>
> [If problems found:] This affects [scenario element]. Options: [workaround A] or [adjust scenario to B]. Which way?"

**Wait for SE response** if any problems require a design change. If all objects check out cleanly, proceed to Stage 7 without stopping.
