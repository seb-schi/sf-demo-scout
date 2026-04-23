# Change Log — Template

Save to: `orgs/[alias]-[customer]/changes-[YYYY-MM-DD]-[HHmm]-[CUSTOMER].md`
Also output the full change log to the terminal.

HHmm = local time at change log creation (e.g. 0930, 1445).

```markdown
# Change Log — [Customer] — [Date] [HHmm]
Org: [alias] ([username])
Spec: demo-spec-[CUSTOMER]-[DATE]-[HHmm].md
Audit used: audit-[YYYY-MM-DD]-[HHmm].md

## What Was Deployed
[Every component, grouped by type — include API names]

## What Was Skipped
[Items not deployed and why]

## Companion Permission Set
[Name, coverage, assignment status]

## Flows Deployed (if any)
[API names, description, active/draft status]
Rollback: sf project delete source --metadata Flow:[FlowApiName] --target-org [alias]

## Apex Deployed (if any)
[Names, description]
Rollback: sf project delete source --metadata ApexClass:[Name] / ApexTrigger:[Name] --target-org [alias]

## LWC Deployed (if any)
[Names, description]
Rollback: sf project delete source --metadata LightningComponentBundle:[Name] --target-org [alias]

## Agentforce Deployed (if any)
[Names, description]
Rollback: sf project delete source --metadata AiAuthoringBundle:[AgentName] --target-org [alias]
(plus `ApexClass:[ClassName]` for each backing action. For existing-agent modifications, rollback is `sf agent activate --version-number [N]` — see phase 3 sub-agent output.)

## Agentforce Smoke Test Results (if any)
[Utterances sent, pass/fail per utterance, issues observed]

## Execution Order Check
[Per-object list of active flows after deployment. Flag objects with multiple after-save record-triggered flows and note execution order risks.]

## Issues Encountered
[Errors, workarounds, second attempts]

## Docs Consulted
Aggregated from sub-agent `docs_consulted` arrays + any orchestrator-level error-recovery consultations.
- **Phase:** [1|2|3|orchestrator] — **Question:** [one line]
  - **URL:** [doc URL]
  - **Verdict:** [what the doc confirmed/contradicted/left ambiguous]

## SE Must Do Next (in order)
1. [Specific steps with UI paths]

## How to Verify
[Step-by-step test sequence]

## Open Questions for Next Session
[Unresolved items, follow-up]
```

After saving, tell the SE:
> "Change log saved. Review 'SE Must Do Next' — complete those before the demo."
