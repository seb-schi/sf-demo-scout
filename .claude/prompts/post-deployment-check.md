# Post-Deployment Execution Order Check

Run after all phases complete (or after Phase 1 if Phases 2/3 were skipped).

For each object that received new flows in Phase 2, AND for each object the audit reported as already carrying active flows, query active flows:

```
SELECT ApiName, TriggerType, ProcessType FROM FlowDefinitionView WHERE IsActive = true AND TriggerObjectOrEventLabel = '[Object]'
```

If multiple after-save record-triggered flows exist on the same object, flag in the change log:

> "⚠️ [Object] has [N] active after-save flows: [names]. Check execution order in Setup > Process Automation > Flow Trigger Explorer."

This check also runs for objects that already had active flows in the audit — the goal is to catch conflicts introduced by this deployment.
