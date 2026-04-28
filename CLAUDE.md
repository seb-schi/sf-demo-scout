# SF Demo Prep — Claude Code Instructions

## Org
> Org identity is read from `sf config get target-org` at runtime.
> Session startup displays the active org, username, and connection status.
> No manual configuration needed — run /switch-org to connect or change an org. Do NOT use /setup-demo-scout for org switching.

- Type: Personal demo org — destructive operations permitted with prior explanation

## MCP Tools
Salesforce DX MCP Server configured in .mcp.json. Prefer MCP over CLI:
- `retrieve_metadata` — inspect org state
- `deploy_metadata` — push changes
- `run_soql_query` — data verification
- `assign_permission_set` — assign permission sets
- `list_all_orgs` — verify org connections
- `run_code_analyzer` — quality gate for Apex/LWC
- LWC expert tools — scaffolding, SLDS, validation (complemented by the `sf-lwc` skill for PICKLES methodology and 165-point scoring)

Salesforce Docs MCP Server (also in .mcp.json) for official documentation lookup:
- `salesforce_docs_search` — semantic search across Salesforce doc collections; returns ranked excerpts with source URLs
- `salesforce_docs_fetch` — retrieve a full doc page by `documentPath`
Use during sparring to verify release-gated features before speccing, and during deployment to diagnose unfamiliar error messages. Optional — if the endpoint is unavailable, Scout degrades gracefully.

Slack MCP Server (user-scope, registered by install.sh) for SE-named canvas/channel lookups during sparring and handover-canvas writes after deployment:
- `slack_search_public_and_private`, `slack_search_channels` — resolve canvas titles and channel names the SE mentions
- `slack_read_canvas`, `slack_read_channel` — pull content for scenario context
- `slack_create_canvas` — write the demo handover brief to the SE's personal Slack (scout-building Step 8c)
Used in scout-sparring Stage 4 (inline ask, New/Reuse-org only) and scout-building Step 8c (y/n handover canvas offer). Hard-degrades to "not available" if not authenticated. OAuth token lives in macOS Keychain (`Claude Code-credentials`); MCP registration in `~/.claude.json` — both survive `update.sh`.

Fall back to `sf` CLI if MCP is unavailable.

## Build Boundaries

### Autonomous (no SE input needed)
- Custom objects, fields, record types
- Permission sets and assignment
- Lightning apps, custom tabs
- Queues with object routing
- Business Processes (stage / status subsets for Opportunity, Lead, Case, Solution — one `BusinessProcess` Metadata API type covers all four)
- Paths (PathAssistant — active flag, driving picklist, key fields + guidance per step)
- Page layout field additions (active layout only — query ProfileLayout first)
- Data seeding — single object always; cross-object (junctions, FK chains) when backed by an idempotent script with `--pilot-only` self-test per `demo-deployment-rules` §Script Deliverable Rules
- Picklist value additions to existing fields

### Gated (SE confirms once per category, then autonomous)
- Simple record-triggered flows (single-object only)
- Simple screen flows (≤3 linear screens by default; up to 5 when SE justifies during sparring; whitelisted components; single terminal DML; optional QuickAction wiring)
- Simple Apex (single-trigger, single-object)
- Simple LWC (demo-specific UI)
- Agentforce agents via Agent Script (topics, actions, backing Apex, publish, activate, smoke test)

### Always Manual (SE Manual Checklist)
- Complex screen flows (branching across screens, subflows, reactive across screens with formula dependencies, custom LWC screen components, File Upload, Repeater, Data Table, Kanban Board)
- Scheduled, multi-object flows, subflows
- Complex Apex/LWC
- Multi-agent orchestration, channel assignment, production-scale agent testing
- Page layout visual arrangement (field positioning, sections in App Builder)
- Reports, dashboards, OmniStudio
- Screen-flow visual QA (one-time walkthrough in a record page after Scout deploys)

### NEVER Without Explicit SE Confirmation
- Delete existing metadata or records
- Modify existing profiles or permission sets
- Touch anything prefixed `sb_` or `managed__`

**Deployment rules** for Flows, Apex, LWC, Agentforce, and Page Layouts live in `.claude/skills/demo-deployment-rules/SKILL.md` — phase sub-agents load it on-demand.

## Working Pattern
1. Announce before every tool call or parallel batch — one line, what and why.
   Opus 4.7 hides thinking from the SE; silence reads as stuck. This rule
   supersedes default brevity — a short status beats a mystery pause.
   For multi-step loops (audits, deploys), announce the shape upfront
   ("8 counts, then 10 layouts, then 3 deploys") so the SE can track progress.
2. Retrieve current state before writing — prefer MCP retrieve_metadata
3. Deploy in small increments — never batch unrelated changes
4. After each deploy: confirm success via deploy status or MCP feedback
5. On failure: explain error in plain English, fix only the failing element, redeploy
6. After every deployment: run the Companion Permission Set (see below)
7. If context is getting long, save progress to the change log and tell the SE to start a fresh session

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
- Per-org history: `orgs/[alias]-[customer]/` (audits, change logs, specs)
- Sparring lessons: `orgs/sparring-lessons.md`
- Building lessons: `orgs/building-lessons.md`
- Deployment rules: `.claude/skills/demo-deployment-rules/SKILL.md`
- Org audit format: `.claude/skills/demo-org-audit/SKILL.md`
- Spec template: `.claude/prompts/spec-template.md`
- Change log template: `.claude/prompts/change-log-template.md`