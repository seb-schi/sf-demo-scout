# Demo Spec — Output Format

Save to: `[ORG_FOLDER]/demo-spec-[YYYY-MM-DD]-[HHmm]-[CUSTOMER].md` (the resolved ORG_FOLDER from customer-normalization)

HHmm = local time at spec creation (e.g. 0930, 1445). Prevents silent overwrites when sparring runs multiple times in a day for the same customer. Date-first ordering keeps the customer folder sorted chronologically in `ls`.

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
- **Demo stakeholders:**
- **Competitive context:**

### Value Spine
Drafted in Stage 5, refined with SE. The narrative the build proves against. Empty slots are honest gaps — leaving them visible is intentional, not an error.
- **Residual Message:** [one sentence — the one thing the room remembers]
- **Audience:** [who carries this message away — altitude-setter]
- **KP1 — Pain:** [what's broken today, ideally a direct customer quote]
- **KP2 — Cost of Inaction:** [what staying with the status quo costs — metric if available, or "gap — SE to fill"]
- **KP3 — Future State:** [the concrete outcome with visible contrast to KP1]

## Release Notes & Citations
Docs consulted during sparring (Platform & Data Model Research — Stage 4, plus any residual checks in Stage 6). Empty if scenario uses only established patterns.
- **Question:** [one line]
  - **URL:** [doc URL]
  - **Verdict:** [what the doc confirmed, contradicted, or left ambiguous]

### Slack References
Context only — Slack content is medium-confidence and attributed to source messages. Docs and SE knowledge take precedence in the spec body. List each canvas or channel the SE named during sparring, with a 1-line synthesis of what it surfaced.
- [Canvas title or #channel-name] — [1-line synthesis of what it surfaced, not what is asserted as true]
- (or: "None — no Slack references pulled this session.")

### Google Workspace References
Context only. A customer's stated requirements (e.g. RfP questions, capability rows) are high-signal; any solution-fit claim in the doc is the SE's hypothesis, validated against docs + audit, not asserted. List each Doc/Sheet the SE named during sparring, with a 1-line synthesis.
- [Doc/Sheet title (+ tab if a Sheet)] — [1-line synthesis of the requirements/context it surfaced, not asserted fit]
- (or: "None — no Google Workspace references pulled this session.")

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
- RecordTypeVisibility: visible=true, TabVisibility: Visible (not DefaultOn — DefaultOn is Profile-only), AppVisibility: visible=true
- Assign to running user
- **If this spec has an Agentforce section:** Phase 3 auto-detects and assigns the standard Agentforce runtime permset (`AgentforceEmployeeAgentUser` / `AgentforceServiceAgentUser` / `AgentforceUser`, whichever exists in the org) to the running user. The Companion permset above covers custom metadata only — those three are standard permsets, assigned separately by Phase 3.

### Platform Constraints (from pre-flight — if any managed/industry objects in scope)
- [Object]: IsEverCreatable=[true/false], IsQueryable=[true/false], queueable=[yes/no], namespace=[if managed]
- Impact: [how this constrains the spec — e.g. "no API data seeding", "no queue routing", "Apex must use dynamic SOQL"]
- ⚠️ Managed-package objects (non-null namespace) default to "dynamic SOQL recommended" — static SOQL only if deploy-time evidence confirms it
- ⚠️ Agentforce + managed object: may fail at runtime even with dynamic SOQL — SE confirm before speccing

### Data Shape (from validation — if Apex/Flow/Agent queries objects)
- [Object]: [field] populated [X]%, [field] is [DataType] (filterable: yes/no)
- Design impact: [how this shapes the query pattern — e.g. "join via AccountId not VisitId", "use SOSL not SOQL WHERE for text search"]

### Queues (if applicable)
- Queue: [ApiName], Label: [Label]
- Objects: [Case, Lead, etc. — which objects this queue receives]
- Members: assign to running user

### Business Processes (if applicable)
One `BusinessProcess` Metadata API type covers Sales / Lead / Support / Solution Processes — the Setup UI groups them by object, but the metadata is unified.
- Process: [ApiName], Label: [Label]
- Object: [Opportunity | Lead | Case | Solution]
- Driving picklist: [StageName for Opportunity; Status for Lead / Case / Solution]
- Values (in order, subset of the standard picklist): [value 1, value 2, ...]
- Record Type binding: [RecordType DeveloperName] (the record type that uses this process)

### Paths (if applicable)
- Path: [ApiName], Label: [Label]
- Object: [SObject API], Record Type: [RecordType DeveloperName]
- Picklist field: [field API — the field driving the path, e.g. `StageName`]
- Active: yes/no (default yes)
- Steps (one per picklist value, in order):
  - **[Picklist value]** — key fields: [field1, field2, field3 (max 5)] — guidance: `[1-3 sentences of rich text shown in the Path component]`

### Validation Rules (if applicable)
- Rule: [ApiName] on [Object], Label: [Label]
- Error condition formula: `[formula — Scout wraps in CDATA if it contains <, >, &]`
- Error message: `[≤255 chars shown to the user on save]`
- Error location: [field API name | top of page]
- Active: yes/no (default yes)

### List Views (if applicable)
- List View: [ApiName] on [Object], Label: [Label]
- Filter scope: [Everything | Mine | Queue]
- Columns (field API names, in order): [field1, field2, ...]
- Filters (if any): [field operation value, e.g. `StageName equals "Closed Won"`]

### Sharing Rules (if applicable)
Scope: record-level access via `sharingCriteriaRules`, `sharingOwnerRules`, or `sharingGuestRules` (the `platform-sharing-rules-generate` skill). A sharing rule is **inert unless the object's org-wide default (OWD) is restrictive** (`Private` or `Public Read Only`) — capture the OWD prerequisite per object below.
- Object: [SObject API — standard or custom]
- OWD prerequisite:
  - **Custom object (in this spec):** Scout sets `<sharingModel>` to [`Private` | `ReadWrite` if M-D → `ControlledByParent`] in the object metadata — autonomous, deployed in the same phase. Sharing rule is meaningful only if `Private`.
  - **Standard object (Account, Case, Opportunity, …):** ⚠️ OWD *is* API-settable (`<sharingModel>` on `CustomObject`, API 30.0+) — but Scout does NOT change it, because a `CustomObject:Account` deploy **cannot update a single element**: it redeploys the whole object (every custom field, list view, record type), and a restrictive OWD change also triggers org-wide sharing recalculation. Blast radius, not impossibility. **SE Manual prerequisite:** the SE must set the OWD to Private/Read in Setup → Sharing Settings BEFORE the rule has effect. Scout deploys the rule and flags it inert-until-OWD-set in the change log.
- Rule type: [criteria | owner | guest]
- Rule: [PascalCase fullName], Label: [Title Case label]
- Access level: [Read | Edit] (default Read)
- Shared to: [`<role>`RoleName | `<roleAndSubordinates>`RoleName | `<group>`GroupName | `<guestUser>`CommunityNickname (guest only) | `<portalRole>` …]
- For criteria rules — criteria (ANDed unless booleanFilter given): [Field operation value, e.g. `Region__c equals "West"`]; `includeRecordsOwnedByAll`: [true | false] (default true)
- For owner rules — shared from: [`<role>` | `<group>` source]
- For guest rules — `includeHVUOwnedRecords`: [true | false] (default false); guest user CommunityNickname resolved via org query
- ⚠️ If object is **Account**: rule MUST include `<accountSettings>` (case/contact/opportunity access — default all `None`)

### Custom Report Type (if applicable)
Scope: a report type exposing one primary object + up to 3 related objects (4 total in the join chain) to the report builder (the `platform-custom-report-type-generate` skill). Each object contributes its own field section; join semantics decide whether related records are required (inner) or optional (outer).
- Report Type: [DeveloperName], Label: [masterLabel]
- Category: [Accounts & Contacts | Opportunities | Customer Support Reports | Activities | ... | Other Reports] (valid category value — the skill's `references/category-values.md` is authoritative)
- Description: [one line shown in the report-type chooser]
- Deployed: [Deployed (visible in builder) | In Development (hidden)] (default Deployed)
- Primary object: [SObject API]
- Join chain (in order, max 3 related objects — omit if primary-only):
  - [Related SObject API] via [child relationship name — `__r` for custom]; join: [inner | outer] (inner = primary rows require a related record; outer = primary rows appear with or without one)
  - [next related object] via [relationship]; join: [inner | outer]
  - ⚠️ Once a join is outer, every join after it must also be outer (Salesforce rejects inner-after-outer).
- Field sections (one per object in the chain, primary first):
  - [Object]: section label "[masterLabel]", fields (API name → checked-by-default? → optional display label):
    - [Field__c] → checked / unchecked → ["Override label" if the builder should show a custom name]
    - [Field2__c] → checked / unchecked
  - [Related Object]: section label "[masterLabel]", fields:
    - [Field__c] → checked / unchecked

### Reports (if applicable)
Scope: a Lightning Report (`.report-meta.xml`) in a folder (the `platform-report-generate` skill). Reports run on a standard report type (e.g. `Opportunity`, `CaseList`, `LeadList`, `AccountList`) or a deployed Custom Report Type from the section above. Columns use platform report column names, NOT raw API field names.
- Report: [Report Name (max 40 chars)], API/DeveloperName: [DeveloperName]
- Folder: [FolderName] — [new (Scout creates it + AllInternalUsers share) | existing (Scout deploys the report only, does not touch the folder)]
- Report type: [Opportunity | CaseList | LeadList | AccountList | ... standard | deployed Custom Report Type DeveloperName]
- Format: [Tabular | Summary | Matrix | Joined]
- Columns (platform column names — see the skill's `references/column-names.md`; e.g. `STAGE_NAME`, `AMOUNT`, `CLOSE_DATE`):
  - [COLUMN_NAME] → optional aggregate: [Sum | Average | Max | Min] (aggregates need Summary/Matrix)
- Groupings (Summary/Matrix only; a grouping field must NOT also be a column):
  - Down: [COLUMN_NAME] → [date granularity if a date] → [Asc | Desc]
  - Across (Matrix only): [COLUMN_NAME]
- Filters (optional): [COLUMN_NAME] [operator: equals/notEqual/contains/...] [value — comma-separate for multi-value picklist in ONE item]
- Time frame (optional): [dateColumn] over [interval — e.g. INTERVAL_CURRENT (this quarter), INTERVAL_CURY (this year), INTERVAL_LAST30]
- Chart (optional, Summary/Matrix only): [chart type — see the skill's `references/chart-types.md`]

### Lightning Record Page — Authoring (Autonomous, simple pages only)
Scope: a NEW simple `RecordPage` FlexiPage — header + one/two-column field section + standard components. Complex authoring (dynamic forms, custom LWC placement, tabsets, conditional visibility) stays SE Manual below.
- FlexiPage DeveloperName: [ApiName]
- Object: [SObject API]
- Field section(s): [section label → columns → field API names]
- Standard components: [Highlights Panel | Activity | Related Lists | ... from the platform-flexipage-generate catalog]
- Activation: [org default | leave inactive for SE | app/profile name] (if not org-default, SE assigns in App Builder)

### Data Seeding
- Object: [name], Records: [count]
- Key values: [field]: [value] — (reason)
- ⚠️ Review and customize seed data for customer-specific values (names, product SKUs, dates) before demo
- **Record counts must be single integers, not ranges.** `Records: 5` — not `Records: 3-5`. Building needs a deterministic count; if genuinely unsure, pick the upper bound of what the demo story needs.
- **Cross-object seeding (junctions, FK chains):** if this seed touches 2+ objects with lookup population, building will produce an idempotent reusable script per `demo-deployment-rules` §Script Deliverable Rules. Spec lists target objects and key field mappings; the script path + `--pilot-only` + bulk commands land in the change log and handover brief.
- **Field names are describe-confirmed.** Sparring Stage 5b runs `sf sobject describe` on every Data Seeding target object before writing this spec. Field names, RecordType DeveloperNames, and picklist-vs-string distinctions in this section are empirically verified, not inferred.
- **Calibration directives (when seed values depend on live org data):** if a seed value must be computed against live aggregates (e.g. "quota set to 70-80% of running user's open pipeline" so the "at risk" narrative reads), write it as a `Calibration:` line under the relevant seed bullet. Format: `Calibration: <target ratio/range in plain English> — reference query: <one-line SOQL>`. Phase 1 runs the query, computes the seed value, and auto-applies — overriding any literal number in this section. The calibration and the computed value land in the change log. If the reference query errors or returns no data, Phase 1 falls back to the literal and records the fallback in `issues`.

### Page Layouts (Classic — field additions only)
Scope: adding fields to a classic Page Layout. **Use this section ONLY when the audit's active LRP for the object is `composition_class: record_detail`** (the LRP uses `force:detailPanel`, so classic Page Layout adds pass through automatically). For `field_section` / `mixed` / `custom` / `unretrievable` LRPs, use one of the LRP sections below — touching just the classic layout will not change what the demo audience sees.
- [Object] — [RecordType] — Active layout: [classic layout name from audit ★]
- Fields to add: [list]
- LRP composition (from audit): record_detail — confirms layout pass-through is the visual surface
- ⚠️ Visual arrangement: SE Manual Checklist

### Lightning Record Page — Field Section additions (Autonomous, Gated)
Scope: appending existing fields into the field-bearing leaf Facet of an existing `flexipage:fieldSection` on the active LRP. Use this section when the audit's active LRP for the object is `composition_class: field_section` or `mixed` AND the spec names exactly which field section + column receives the field. Scout edits the FlexiPage XML, deploys, and verifies via post-deploy retrieve grep.
- [Object] — Active LRP: [LRP DeveloperName from audit ★🚨]
- LRP composition (from audit): [field_section | mixed]
- Target field section: [exact section label from audit's enumerated field_sections list — must match audit verbatim]
- Target column: [`1` for single-column sections (audit reports one column entry); `1` / `2` / `N` for multi-column sections — column_index from audit. REQUIRED — Scout cannot guess column placement when there are multiple columns]
- Fields to add: [list of field API names]
- Section position: append (Scout adds new fields at the end of the named column's leaf Facet; in-section reordering is SE Manual)
- ⚠️ Repositioning fields within the column, creating new sections / columns, or moving fields between sections / columns is SE Manual
- ⚠️ If the audit's `columns` array for the named section contains a column with `facet_uuid: null` (opaque structure), this section is NOT eligible for autonomous deploy — route to the LRP SE Manual section below.

### Lightning Record Page — SE Manual (App Builder)
Scope: anything beyond appending into an existing field section. Use when audit reports `composition_class: mixed` AND the field belongs in something other than a field section, OR `custom` / `unretrievable`, OR the spec needs new sections, repositioning, components, tabset edits, or dynamic-form regions. Scout deploys the underlying metadata (LWC bundles, Path components, QuickActions); the SE drags and drops in App Builder.
- [Object] — [LRP name] — Composition: [field_section | mixed | custom | unretrievable] — Why SE Manual: [section creation / reposition / new component / dynamic-form region / unretrievable composition]
- Components / fields to add: [list]

### Lightning App / Tabs
- Existing app: [name] — modifications: [list]
- New tabs (if any): [list]

### Flows (if applicable)
- ⚠️ SE CONFIRMATION REQUIRED (single upfront gate — Scout will notify you)
- **Proves:** KP[1|2|3] — [one line: how this flow makes a KP land in the demo]
- Plain English: [description]
- Flow name: [ApiName]
- Flow type: one of **record-triggered** (before-save / after-save / before-delete) | **autolaunched** | **subflow** | **scheduled** | **platform-event-triggered**
  - Orchestration and complex screen flows route to the SE Manual Checklist — do not list them here.
- Type-specific fields:
  - **Record-triggered:** Trigger object: [API name], Trigger type: [before-save | after-save | before-delete], Entry conditions: [filter formula or "none"], Logic: [steps, including any cross-object DML]
  - **Autolaunched:** Invoked from: [Apex class / parent flow / REST / process], Input variables: [name + type per var], Logic: [steps]
  - **Subflow:** Parent flow: [ApiName of caller — must also be in this spec or already in org], Input variables: [name + type per var], Output variables (if any): [name + type per var], Logic: [steps]
  - **Scheduled:** Start date: [YYYY-MM-DD], Start time: [HH:MM:SS], Frequency: [Once | Daily | Weekly | Monthly | Yearly | Hourly | Weekdays], Object filter (optional): [SObject + filter conditions for batch runs], Logic: [steps]
  - **Platform-event-triggered:** Event object: [API name — e.g. `OrderCreated__e` or standard like `AIPredictionEvent`], Event fields referenced: [list], Logic: [steps]

### Screen Flows (if applicable)
- ⚠️ SE CONFIRMATION REQUIRED (single upfront gate — Scout will notify you)
- **Proves:** KP[1|2|3] — [one line: how this screen flow makes a KP land in the demo]
- Plain English: [what the user sees and accomplishes]
- Flow name: [ApiName], Type: Screen Flow
- Screen count: [SE names the count — no hard cap; more screens = a longer one-time visual-QA walkthrough, already a named SE step]
- Logic: [branching, cross-screen reactivity, and formula dependencies are all in scope — describe the flow's decision logic here]
- Target object: [object for terminal DML, or "none" for display-only]
- Screens (in order):
  - Screen 1: [label]
    - Fields: [name] ([type: Text/Number/Email/Date/Picklist/RadioButtons/Checkbox/CheckboxGroup/MultiSelectPicklist/DisplayText/Section], required: yes/no, help text: [optional], default: [optional])
    - Validation (optional): formula `[Boolean expression]` — error: `[message]`
  - Screen 2: ...
  - Screen N: ...
- Terminal DML: [Create | Update | Get | None]
  - If Create/Update: target object field assignments: [field: source]
  - If Get: queriedFields: [explicit list — never storeOutputAutomatically]
- QuickAction wiring: [yes (label: [button label], layout: [active layout name from audit]) | no — SE will wire manually]
- Smoke test: Scout auto-generates happy-path FlowTest; SE does a one-time visual walkthrough in the Lightning UI
- Components outside the autonomous whitelist (Repeater, Data Table, Kanban Board, File Upload/Preview, custom LWC screen component) → move to SE Manual Checklist. This is a *no-build-time-signal* gate, not a complexity gate: these components have nothing a happy-path FlowTest can assert. Branching, cross-screen reactivity, and formula dependencies are NOT in this list — they are in scope (gated by the FlowTest; the flow stays Draft if it fails).

### Apex (if applicable)
- ⚠️ SE CONFIRMATION REQUIRED (single upfront gate — Scout will notify you)
- **Proves:** KP[1|2|3] — [one line: how this Apex makes a KP land in the demo]
- Plain English: [description]
- Name: [name], Object(s): [single or multiple — cross-object is in scope], Logic: [steps]
- Note: Scout authors a test and self-fixes via a bounded loop; if the test can't be made to pass, the class ships test-unvalidated and is handed to the SE for a Sonnet iteration (see the handover brief). No "too complex" refusal.

### LWC Components (if applicable)
- ⚠️ SE CONFIRMATION REQUIRED (single upfront gate — Scout will notify you)
- **Proves:** KP[1|2|3] — [one line: how this LWC makes a KP land in the demo]
- Plain English: [behaviour]
- Name: [name], Location: [page], Data: [objects/fields], SLDS: [pattern]

### External Skills (if any — SE-approved, non-bundled)
> Only present if the SE approved a non-bundled skill during sparring. Each entry is a skill installed by the SE that is NOT part of Scout's bundled set. /scout-building makes these available to phase sub-agents by name; it does NOT validate their output.
- Skill: [verbatim skill name as it appears in the menu, e.g. `rlm-pricing`]
- Applies to: [which build areas — e.g. "Quote/Order pricing config", "RLM custom objects"]
- ⚠️ OUTSIDE SCOUT VALIDATION — output from this skill is NOT covered by Scout's phase checks (data-seed integrity probe, action-invocation probe). SE verifies the result against the org before demo. This caveat is per-skill and non-removable.

### Agentforce (if applicable)
- ⚠️ SE CONFIRMATION REQUIRED (single upfront gate — Scout will notify you)
- ⚠️ Deploys last — ADLC skills are large; org config completes first
- **Proves:** KP[1|2|3] — [one line: how this agent makes a KP land in the demo]
- Path: New Agent / Modify Existing Agent (specify which)
- Plain English: [what agent does, why it strengthens demo]
- Agent: [name], Type: AgentforceEmployeeAgent / AgentforceServiceAgent
- Role: [one line — who the agent is / who it helps; REQUIRED identity field]
- Company: [one line — the customer org description; REQUIRED identity field]
- Agent Script file: [developer_name].agent
- Subagents: [name] — [description] — backing action: [apex://ClassName or flow://FlowName]
- Backing Apex classes: [name] — [InvocableMethod description]
- Existing agents in org: (from audit — note conflicts)
- If modifying existing: current version v[N], rollback: `sf agent activate --version-number [N]`
- Agent test cases: table below — 4-8 rows that become the official `sf agent test` spec (Testing Center). Columns map 1:1 to the `agentforce-test` skill's YAML fields. **MUST include at least one guardrail/off-topic row** (leave `expectedTopic` empty, describe the decline in `expectedOutcome`) — mirror the skill's `guardrail-test-spec.yaml`.

  | # | Utterance | expectedTopic | expectedActions | expectedOutcome |
  |---|-----------|---------------|-----------------|-----------------|
  | 1 | [primary-path user message] | [topic / subagent name] | [Level-2 invocation action name] | [what a correct response does] |
  | 2 | [action-exercising message] | [topic] | [action] | [observable effect described] |
  | 3 | [off-topic / guardrail message] | (leave empty) | (none) | [declines gracefully, stays on-domain, no hallucination] |

  Notes: `expectedActions` uses **Level-2 invocation names** (from `reasoning: actions:`), NOT Level-1 definition names; it is a flat list and assertion is superset-match. Always fill `expectedOutcome` — LLM-as-judge is the most reliable assertion. For guardrail rows leave `expectedTopic` empty and rely on `expectedOutcome`. The `agentforce-test` skill's `basic-test-spec.yaml` + `guardrail-test-spec.yaml` are the authoritative templates — do not hand-invent field names.
- **Running-user access (Service Agents only):** if Type is `AgentforceServiceAgent`, the agent
  executes as a dedicated running user (not the logged-in admin), so every backing action is gated by
  that user's access. Phase 3 auto-grants the running user access to the backing Apex/Flow, the
  RecordTypes the backing code inserts, and the dependency objects the backing code reads (derived from
  the backing actions above — no spec enumeration needed). Employee Agents run as the logged-in user
  and need none of this.
- **⚠️ Layer-5 license wall (Service Agent + restricted-license running user):** if any backing action
  touches a managed/industry object (Life Sciences: Inquiry, CareProgramEnrollee, ProgramEnrollment,
  etc.) AND the running user is on a restricted license (e.g. Einstein Agent), a permset CANNOT grant
  access — it is a base-license wall. Pick the bypass at spec time and record it as a manual pre-demo
  step: (1) blocking query lives in an asset WE own (unmanaged flow/apex) → set that flow to System
  Mode / the apex to `without sharing` + system-context DML (one line, in our control); (2) blocking
  query lives in MANAGED code (e.g. an `lsc4ce` trigger) → disable the *specific* handler via the
  managed Admin Console → Trigger Handler Administration (SE-manual, org-wide toggle — pin the exact
  handler first, disable ONE not all). The paid Agentforce-for-Life-Sciences add-on is the only
  license-level fix and is not demo-viable.
- ⚠️ Channel assignment: SE Manual Checklist
- **Advanced capabilities (if any — flag here so Phase 3 authors the metadata + hands off UI wiring):**
  - Multi-agent orchestration: [sub-agent api_name(s) the parent delegates to] — Beta, connection wiring is UI-only
  - Enhanced Chat v2: [yes/no] — REQUIRED if any Lightning types/forms in chat; SE republishes Embedded Service Deployment + creates the chat channel
  - Lightning types (forms) in chat: [form name(s) + backing Apex class] — Scout authors LightningTypeBundle + LWC (`@api value` contract); SE verifies live render in Test Enhanced Web Chat
  - (Details + gotchas: Phase 3 reads `prompts/building/agentforce-advanced-capabilities.md`)

## SE Manual Checklist

> Only **docs-confirmed UI-only** items belong here (disposition 3 — no Metadata API path; cite the doc). Do NOT list an artifact as manual on "complexity" or "visual" grounds: if it is metadata-authorable, Scout ATTEMPTS + deploys it (see CLAUDE.md §Build Boundaries → Docs-Gated). Artifacts Scout deployed but that carry no build-time signal (a rendered page, a layout arrangement, a UX) are **attempt-with-QA** — they surface in the handover brief's *Built — Validate in Sonnet* section, NOT in this checklist.

### Complex Flows
- Name, Type, Trigger, Conflicts, Steps, Activate when

### Agentforce Manual Steps
- [ ] **Layer-5 license bypass (Service Agent + restricted-license running user only):** if specced,
      apply the chosen bypass — System Mode on an asset WE own, OR disable the specific managed trigger
      handler via Admin Console → Trigger Handler Administration (org-wide toggle; pin the exact handler
      first)
- [ ] Assign agent to channels (Messaging, Experience Cloud, etc.)
- [ ] Production-scale test suite via Testing Center (batch regression — Mode B)
- [ ] Multi-agent orchestration (if applicable)

### Must Do Before Demo
- [ ] Build orchestration flows (multi-day lifecycles) and any screen flow using a non-whitelisted component (Repeater, Data Table, Kanban Board, File Upload/Preview, custom LWC screen component) — these have no build-time signal. (Branching / cross-screen reactivity / formula-dep screen flows and multi-class/cross-object Apex are now built autonomously and appear under "Built — validate in Sonnet" in the handover brief, NOT here.)
- [ ] Screen-flow visual QA: walk through each autonomous screen flow once in the Lightning UI (labels, button order, help text read sensibly)
- [ ] For scheduled flows: verify the Scheduled Jobs page (Setup → Scheduled Jobs) shows the next run time matching the spec
- [ ] Complete Agentforce manual steps (channel assignment, production testing)
- [ ] Arrange field positions and sections in App Builder
- [ ] Place LWC on Lightning pages
- [ ] Add the Path component to the Lightning record page (App Builder) — Scout deploys the Path metadata; the visual placement on the record page is manual
- [ ] Review and customize seed data for customer-specific values
- [ ] Review all ⚠️ items
- [ ] Test full demo end-to-end

### Known Limitations
- [Build boundaries, managed packages, UNVERIFIED items]

### Open Questions for Next Session
- [Unresolved, feedback, improvements]
```
