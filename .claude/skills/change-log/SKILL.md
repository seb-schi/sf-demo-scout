---
name: change-log
description: >
  Template for the mandatory change log after every deployment.
  Used by /scout-building.
---

# Change Log — Template

Save to: `orgs/[alias]-[ORG_ID_SHORT]/changes-[YYYY-MM-DD]-[CUSTOMER].md`
Also output the full change log to the terminal.

```markdown
# Change Log — [Customer] — [Date]
Org: [alias] ([username])
Spec: demo-spec-[CUSTOMER]-[DATE].md
Audit used: audit-[YYYY-MM-DD].md

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
Rollback: sf project delete source --metadata GenAiPlanner:[Name] / BotDefinition:[Name] --target-org [alias]

## Issues Encountered
[Errors, workarounds, second attempts]

## SE Must Do Next (in order)
1. [Specific steps with UI paths]

## How to Verify
[Step-by-step test sequence]

## Open Questions for Next Session
[Unresolved items, follow-up]
```

After saving, tell the SE:
> "Change log saved. Review 'SE Must Do Next' — complete those before the demo."