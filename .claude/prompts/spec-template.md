# Demo Spec — Output Format

Save to: `orgs/[alias]-[customer]/demo-spec-[CUSTOMER]-[YYYY-MM-DD]-[HHmm].md`

HHmm = local time at spec creation (e.g. 0930, 1445). Prevents silent overwrites when sparring runs multiple times in a day for the same customer.

```markdown
# Demo Spec — [Customer Name]
Generated: [Date] [HHmm]
Salesforce Release: [cite or mark CONFIDENT]
Target Org: [alias] ([username])
Org Audit Used: audit-[YYYY-MM-DD]-[HHmm].md

## Customer Context
- **Company:**
- **Industry vertical:**
- **Key pain point:**
- **Value theme:**
- **Demo stakeholders:**
- **Competitive context:**

## Release Notes & Citations
Docs consulted during sparring (Feasibility Pass — Stage 7). Empty if scenario uses only established patterns.
- **Question:** [one line]
  - **URL:** [doc URL]
  - **Verdict:** [what the doc confirmed, contradicted, or left ambiguous]

## Scenario: [Name]
**Business story:**
**Core capability:**
**Pain point addressed:**
**Primary build surface:** (★-flagged app, objects, and layouts from audit — confirmed with SE)
**New metadata required:** (only what cannot be delivered by extending existing components — justify each)
**Org conflicts:** (what to check/avoid)
**Build required (Claude Code):**
**Build required (SE manual):**
**Demo risk:**

## Claude Code Instructions
> /scout-building executes this section autonomously after the pre-deployment conflict check.
> Flows, Apex, LWC, and Agentforce require a single SE confirmation before that category deploys.
> Review all ⚠️ flags before running /scout-building.

### Objects & Fields
- [Existing object API name, label] — extending existing
  - [Field API] ([Type], [length/values], Required: yes/no)
- [New custom object API name, label] — new (justified because: [reason])
  - [Field API] ([Type], [length/values], Required: yes/no)

### Record Types
- [Object]: [Name] — [description]

### Permission Set
- Name: [Feature]_Access
- Objects: [full CRUD]
- FLS: Read + Edit (EXCLUDE Required fields)
- RecordTypeVisibility, TabVisibility, AppVisibility
- Assign to running user

### Queues (if applicable)
- Queue: [ApiName], Label: [Label]
- Objects: [Case, Lead, etc. — which objects this queue receives]
- Members: assign to running user

### Data Seeding
- Object: [name], Records: [count]
- Key values: [field]: [value] — (reason)
- ⚠️ Review and customize seed data for customer-specific values (names, product SKUs, dates) before demo

### Page Layouts
- [Object] — [RecordType] — Active layout: [layout name from audit ★]
- Fields to add: [list]
- ⚠️ Visual arrangement: SE Manual Checklist

### Lightning App / Tabs
- Existing app: [name] — modifications: [list]
- New tabs (if any): [list]

### Flows (if applicable)
- ⚠️ SE CONFIRMATION REQUIRED (single upfront gate — Scout will notify you)
- Plain English: [description]
- Flow name: [ApiName], Type: Record-Triggered
- Object: [single], Trigger: [when], Logic: [steps]

### Apex (if applicable)
- ⚠️ SE CONFIRMATION REQUIRED (single upfront gate — Scout will notify you)
- Plain English: [description]
- Name: [name], Object: [single], Logic: [steps]

### LWC Components (if applicable)
- ⚠️ SE CONFIRMATION REQUIRED (single upfront gate — Scout will notify you)
- Plain English: [behaviour]
- Name: [name], Location: [page], Data: [objects/fields], SLDS: [pattern]

### Agentforce (if applicable)
- ⚠️ SE CONFIRMATION REQUIRED (single upfront gate — Scout will notify you)
- ⚠️ Deploys last — ADLC skills are large; org config completes first
- Path: New Agent / Modify Existing Agent (specify which)
- Plain English: [what agent does, why it strengthens demo]
- Agent: [name], Type: AgentforceEmployeeAgent / AgentforceServiceAgent
- Agent Script file: [developer_name].agent
- Topics: [name] — [description] — backing action: [apex://ClassName or flow://FlowName]
- Backing Apex classes: [name] — [InvocableMethod description]
- Existing agents in org: (from audit — note conflicts)
- If modifying existing: current version v[N], rollback: `sf agent activate --version-number [N]`
- Smoke test utterances: [3-5 test messages to validate agent after activation]
- ⚠️ Channel assignment: SE Manual Checklist

## SE Manual Checklist

### Complex Flows
- Name, Type, Trigger, Conflicts, Steps, Activate when

### Agentforce Manual Steps
- [ ] Assign agent to channels (Messaging, Experience Cloud, etc.)
- [ ] Production-scale test suite via Testing Center (batch regression — Mode B)
- [ ] Multi-agent orchestration (if applicable)

### Must Do Before Demo
- [ ] Build complex flows (screen, scheduled, multi-object, subflows)
- [ ] Complete Agentforce manual steps (channel assignment, production testing)
- [ ] Arrange field positions and sections in App Builder
- [ ] Place LWC on Lightning pages, configure Path component
- [ ] Review and customize seed data for customer-specific values
- [ ] Review all ⚠️ items
- [ ] Test full demo end-to-end

### Known Limitations
- [Build boundaries, managed packages, UNVERIFIED items]

### Open Questions for Next Session
- [Unresolved, feedback, improvements]
```
