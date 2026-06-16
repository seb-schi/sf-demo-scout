# Data Shape Validation — Stage 5b

Loaded on demand by scout-sparring when the scenario has Apex, Flows, or Agentforce actions (i.e., objects queried or written to programmatically). Runs inline — no sub-agent needed.

## Scope

For every object the scenario's Apex, Flow, or Agentforce action will **query or write to** — not objects that only receive new fields or layouts.

**Reconcile every `[UNVERIFIED — pending 5b]` decision from the Stage 5 cut-gate FIRST.** The cut-gate may have provisionally chosen a write target or status on an unprobed assumption (e.g. "write to `Order.EffectiveDate` instead of a custom field"). Before validating anything else, probe each tagged decision against the org by testing the field in the EXACT record STATE the scenario uses — not an arbitrary record. Two traps the worked example below teaches:

- **Key on StatusCategory, not the status label.** `Order.EffectiveDate` (Order Start Date) is editable while the order's `StatusCategory = Draft` and locked once `StatusCategory = Activated`. Status *values* are org-defined and each maps to one of those two categories — a custom "Delivered" status can map to the Draft category and accept the write, while a custom activated-category status not literally named "Activated" is locked. A probe keyed on `Status = 'Activated'` (the literal string) gives false confidence in any org with custom activated-category statuses. Probe against a real **priced + `StatusCategory = Activated`** order (an empty order can't activate — "must have at least one product"), and check the `Status → StatusCategory` mapping rather than the label.
- **Capture the `errorCode`, not just the symptom.** This particular lock is the standard platform activation field-lock (`FIELD_INTEGRITY_EXCEPTION` / platform), NOT a custom validation rule (`FIELD_CUSTOM_VALIDATION_EXCEPTION`, which carries the VR's own text) and distinct from Salesforce Billing's own field locks (which target a different financial/relationship field set with package-style errors). It is also modulated — the "Edit Activated Orders" user permission unlocks a subset of post-activation fields (EffectiveDate is NOT in that subset) and the "Enhanced Commerce Orders" org setting tightens it further. Capturing the `errorCode` is the meta-skill: it tells the SE which mechanism they're fighting (platform lock vs VR vs package) instead of just observing that the write failed.

If a tagged assumption fails, the cut reverses — surface it to the SE as a design change (per the Surface-findings step below) and clear the tag only once the decision holds against real data in the scenario's actual record state.

## Procedure per object

1. **Sample real records** — `SELECT [key fields from scenario] FROM [Object] LIMIT 5`. If a field errors (e.g., "No such column"), that itself is a finding. **When testing whether a write is feasible, reason upfront about the ONE meaningful test rather than iterating.** A write-feasibility question has a specific blocking state (e.g. "is `EffectiveDate` writable on a priced order whose `StatusCategory = Activated`?" — keyed on StatusCategory, not the status label). Construct that exact record state and test it once — don't probe a Delivered record (may map to Draft category → inconclusive), then an empty record (can't activate → fails for the wrong reason), then the real chain. One designed test against the scenario's actual state beats three exploratory writes. **Capture the write's `errorCode` on failure** (`FIELD_INTEGRITY_EXCEPTION`/platform lock vs `FIELD_CUSTOM_VALIDATION_EXCEPTION`/validation rule) — the code identifies the mechanism the SE is fighting, not just that it failed.
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

**Wait for SE response** if any problems require a design change. If all objects check out cleanly, proceed to Stage 6 without stopping.
