# Post-Deployment Execution Order Check

Run after all phases complete (or after Phase 1 if Phases 2/3 were skipped).

## Flow execution order

For each object that received new flows in Phase 2, AND for each object the audit reported as already carrying active flows, query active flows:

```
SELECT ApiName, TriggerType, ProcessType FROM FlowDefinitionView WHERE IsActive = true AND TriggerObjectOrEventLabel = '[Object]'
```

If multiple after-save record-triggered flows exist on the same object, flag in the change log:

> "⚠️ [Object] has [N] active after-save flows: [names]. Check execution order in Setup > Process Automation > Flow Trigger Explorer."

This check also runs for objects that already had active flows in the audit — the goal is to catch conflicts introduced by this deployment.

## Trigger count report for data-seeded objects

For each object that received bulk data inserts in Phase 1 (`data_seeded[].object` from Phase 1 JSON) AND that has active Apex triggers, emit a read-only report. Bulk inserts fire triggers — if a managed-package or SE-authored trigger is active on the target, ordering issues can silently corrupt demo data.

1. For each data-seeded object, query active triggers:
   ```
   SELECT Name, TableEnumOrId, Status FROM ApexTrigger WHERE TableEnumOrId = '[Object]' AND Status = 'Active'
   ```
2. If any triggers exist, flag in the change log under a new **Trigger Context for Data Seeding** section:
   > "ℹ️ [Object] has [N] active triggers: [names]. Bulk insert during this deployment fired them. Check Setup > Object Manager > [Object] > Triggers if you see unexpected data state."
3. If no triggers, skip silently — the section only appears when there's something to report.

This is informational, not a failure signal. The goal is to give the SE a handhold for post-mortem if the demo reveals unexpected data.
