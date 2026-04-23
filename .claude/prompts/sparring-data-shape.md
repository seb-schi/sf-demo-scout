# Data Shape Validation — Stage 6b

Loaded on demand by scout-sparring when the scenario has Apex, Flows, or Agentforce actions (i.e., objects queried or written to programmatically). Runs inline — no sub-agent needed.

## Scope

For every object the scenario's Apex, Flow, or Agentforce action will **query or write to** — not objects that only receive new fields or layouts.

## Procedure per object

1. **Sample real records** — `SELECT [key fields from scenario] FROM [Object] LIMIT 5`. If a field errors (e.g., "No such column"), that itself is a finding.
2. **Check lookup population** — for any lookup field the scenario depends on (e.g., `VisitId`, `AccountId`): `SELECT COUNT(Id) FROM [Object] WHERE [LookupField] != null`. If 0% populated, the scenario's join path is broken.
3. **Check field filterability** — for any field the scenario uses in a WHERE clause or GROUP BY: `SELECT QualifiedApiName, DataType FROM FieldDefinition WHERE EntityDefinition.QualifiedApiName = '[Object]' AND QualifiedApiName = '[Field]'`. Long Text Area and rich text fields are not filterable — if the scenario depends on filtering them, flag it.

**Budget:** 3-6 SOQL queries per action-relevant object. Most scenarios touch 1-3 objects. Queries are fast and sequential (each informs the next).

## Surface findings to the SE

> "Data shape validation for [objects]:
> - [Object]: [field] populated on [X]% of records, [field] is [DataType] (not filterable in WHERE) ...
> - [Object]: sample records look healthy, all assumed fields present and populated.
>
> [If problems found:] This affects [scenario element]. Options: [workaround A] or [adjust scenario to B]. Which way?"

**Wait for SE response** if any problems require a design change. If all objects check out cleanly, proceed to Stage 7 without stopping.
