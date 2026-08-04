# SF Demo Scout — Claude Code Instructions

## Org
> Org identity is read from `sf config get target-org` at runtime.
> Session startup displays the active org, username, and connection status.
> No manual configuration needed — run /scout-switch-org to connect or change an org. Do NOT use /scout-setup for org switching.

- Type: Personal demo org — destructive operations permitted with prior explanation

## MCP Tools
Four MCP servers may be configured: Salesforce DX + Salesforce Docs (declared in the plugin's `plugin.json`), Slack, and Google Workspace (both user-scope, registered separately; both optional and degrade gracefully when absent). Prefer MCP over `sf` CLI; fall back to CLI if MCP is unavailable.

- **Salesforce DX** — metadata retrieve/deploy, SOQL, permset assignment, org listing, `run_code_analyzer`, and LWC expert tools (complement the `experience-lwc-generate` skill's PICKLES methodology + 165-point scoring).
- **Salesforce Docs** — `salesforce_docs_search` + `salesforce_docs_fetch` for release-gated features and unfamiliar deploy errors. Decision tree in `demo-docs-consultation`. Degrades gracefully if unavailable.
- **Slack** — canvas + channel lookups during sparring (Stage 3, opt-in) and handover canvas writes after deployment (scout-building 6c). Hard-degrades when unauthenticated.
- **Google Workspace** — read Docs/Sheets during sparring (Stage 3, opt-in) — e.g. an RfP, capability map, or account plan as discovery context. Bridged via the DevBar `mcp-adaptor` binary (T&P-gated); degrades gracefully when absent or unauthenticated. The connection is read-write (the gateway binds the read-write OAuth provider), but the discovery lookup calls read tools only.

## Build Boundaries

### Autonomous (no SE input needed)
- Custom objects, fields, record types
- Permission sets and assignment
- Lightning apps, custom tabs
- Queues with object routing
- Business Processes (stage / status subsets for Opportunity, Lead, Case, Solution — one `BusinessProcess` Metadata API type covers all four)
- Paths (PathAssistant — active flag, driving picklist, key fields + guidance per step)
- Page layout field additions (active classic Page Layout — query ProfileLayout first)
- Lightning Record Page field additions to existing `flexipage:fieldSection` components (gated: SE confirms target FlexiPage + section name; only when audit classifies the LRP composition as `field_section`. `record_detail` LRPs inherit classic Page Layout — no separate LRP step needed. `mixed` / `custom` / `unretrievable` route to SE Manual.)
- Data seeding — single object always; cross-object (junctions, FK chains) when backed by an idempotent script with `--pilot-only` self-test per `demo-deployment-rules` §Script Deliverable Rules
- Picklist value additions to existing fields
- Validation Rules (declarative `ValidationRule` formulas on any object — `platform-validation-rule-generate` skill carries formula gotchas + CDATA rule)
- List Views (`ListView` metadata — `platform-list-view-generate` skill)
- Sharing Rules (record-level `sharingCriteriaRules` / `sharingOwnerRules` / `sharingGuestRules` — `platform-sharing-rules-generate` skill; autonomous for the rule metadata. ⚠️ Standard-object OWD is an SE manual prerequisite — Scout never changes org-wide defaults, because a standard-object `CustomObject` deploy redeploys the whole object and triggers sharing recalculation)
- Simple Lightning Record Page authoring (new `RecordPage` FlexiPage: header + one/two-column field section + standard components — `platform-flexipage-generate` skill; complex authoring stays SE Manual)
- Lightning Reports (`Report` metadata — Tabular / Summary / Matrix / Joined; columns, groupings, filters, charts, folder + `<folderShares>` — `platform-report-generate` skill; runs on a standard report type or a deployed Custom Report Type. Dashboards stay SE Manual)

### Gated (SE confirms once per category, then autonomous)
- Record-triggered flows (before-save, after-save, before-delete; any trigger object; cross-object DML allowed)
- Screen flows (≤3 linear screens by default; up to 5 when SE justifies during sparring; whitelisted components; single terminal DML; optional QuickAction wiring)
- Autolaunched flows (no UI, no trigger — invoked from Apex / Flow / REST / Process)
- Subflows (autolaunched flows invoked by a parent — deploy before the parent in the same phase)
- Scheduled flows (SE names `<startDate>`, `<startTime>`, and `<frequency>` during sparring — demo-day precision)
- Platform-event-triggered flows (SE confirms the `<eventType>` object exists in the audit or ships in the same deploy)
- Apex (triggers, classes, invocable actions; multi-class and cross-object allowed). Autonomous within a bounded test-fix loop: Scout authors a test, runs it, and self-fixes via `platform-apex-test-run` (up to 3 iterations) → `platform-apex-logs-debug` on exhaustion. A failing / low-coverage test NEVER blocks the deploy — the class ships and is reported test-unvalidated for the SE to finish in Sonnet. No "complexity" cutoff: the gate is the test signal + the loop, not an undefined size label.
- Simple LWC (demo-specific UI — complex/multi-component LWC stays SE Manual pending a dedicated signal-gated pass; LWC's visual half has no build-time loop)
- Agentforce agents via Agent Script (subagents, actions, backing Apex, publish, activate, smoke test)

### Always Manual (SE Manual Checklist)
- Screen flows using components OUTSIDE the autonomous whitelist (custom LWC screen components, File Upload/Preview, Repeater, Data Table, Kanban Board) — these have no build-time success signal a FlowTest can assert, so they stay manual. NOTE: branching, cross-screen reactivity, and formula-dependency logic are NOT manual — those are now Gated/autonomous (they deploy Draft-first and are gated by a happy-path FlowTest; the flow stays Draft if the test fails twice, so it never ships live-and-broken).
- Orchestration flows (parent-child, sequential, conditional — multi-day lifecycles with assignees, not demo-day-viable as autonomous)
- Complex LWC (multi-component, heavy client-state, or visually-intensive UI) — pending a dedicated signal-gated pass. (Complex Apex is now Gated/autonomous via the test-fix loop — see the Gated list above.)
- Multi-agent orchestration, channel assignment, production-scale load/volume agent testing (functional regression via Testing Center — `sf agent test` — is automated in Phase 3, not manual)
- Classic Page Layout visual arrangement (field positioning, sections in App Builder / Page Layout editor)
- Lightning Record Page authoring beyond simple new-page creation (repositioning sections on an existing page, custom LWC placement, tabsets, dynamic-form regions, conditional visibility — App Builder. Simple new RecordPage authoring is now Autonomous via `platform-flexipage-generate`.)
- Lightning Record Page field-add when composition is `mixed`, `custom`, or `unretrievable` (drop into App Builder for visual confirmation)
- Dashboards, OmniStudio (Lightning Reports are now Autonomous via `platform-report-generate` — see Autonomous list above)
- Screen-flow visual QA (one-time walkthrough in a record page after Scout deploys) — deliberately manual: a screen flow's rendered UX (label wording, button order, help-text readability) has no metadata read-back or FlowTest signal, so this is the one screen-flow step that cannot be looped and is handed to the SE (see the "Built — validate in Sonnet" surface in the handover brief).

### NEVER Without Explicit SE Confirmation
- Delete existing metadata or records
- Modify existing profiles or permission sets
- Touch anything prefixed `sb_` or `managed__`

**Deployment rules** for Flows, Apex, LWC, Agentforce, Page Layouts, and Lightning Record Pages live in `${CLAUDE_PLUGIN_ROOT}/skills/demo-deployment-rules/SKILL.md` — phase sub-agents load it on-demand.

## Working Pattern
1. Before your first tool call, say in one sentence what you're about to do.
   For multi-step loops (audits, deploys), announce the shape upfront
   ("8 counts, then 10 layouts, then 3 deploys") so the SE can track progress.
   While working, give a brief update when you find something important or
   change direction — a demo-day SE reads silence as stuck.
2. Retrieve current state before writing — prefer MCP retrieve_metadata
3. Deploy in small increments — never batch unrelated changes
4. After every deployment: run the Companion Permission Set (see below)
5. If context is getting long, save progress to the change log and tell the SE to start a fresh session

## Companion Permission Set — MANDATORY
After every deployment creating objects, fields, record types, tabs, or apps:

- Object CRUD for all new custom objects
- Field Read + Edit FLS for all new fields (EXCLUDE Required fields — API rejects FLS)
- RecordTypeVisibility: visible=true for new record types
- TabVisibility: Visible for new custom tabs (not DefaultOn — DefaultOn is Profile-only)
- AppVisibility: visible=true for new Lightning apps

Assign via MCP `assign_permission_set`. If unavailable, read alias from `sf config get target-org`:
```
sf data query --target-org [ALIAS] --query "SELECT Id FROM PermissionSet WHERE Name='[NAME]'"
sf data query --target-org [ALIAS] --query "SELECT Id FROM User WHERE Username='[USERNAME]'"
sf data create record --sobject PermissionSetAssignment --values "PermissionSetId=[PS_ID] AssigneeId=[USER_ID]" --target-org [ALIAS]
```

## File Locations
- Per-org history: `orgs/[alias]-[customer]/` (audits, change logs, specs) — in the SE workspace at `~/claude-projects/sf-demo-scout/`
- Lessons: `orgs/lessons/` (topic-clustered; loaded via `${CLAUDE_PLUGIN_ROOT}/prompts/lessons-bootstrap.md`, see `INDEX.md`)
- Deployment rules: `${CLAUDE_PLUGIN_ROOT}/skills/demo-deployment-rules/SKILL.md`
- Org audit format: `${CLAUDE_PLUGIN_ROOT}/skills/demo-org-audit/SKILL.md`
- Spec template: `${CLAUDE_PLUGIN_ROOT}/prompts/spec-template.md`
- Change log template: `${CLAUDE_PLUGIN_ROOT}/prompts/building/change-log-template.md`
