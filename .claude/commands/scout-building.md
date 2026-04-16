---
name: scout-building
description: >
  Opus orchestrator for SF Demo Prep deployment.
  Parses a completed spec from /scout-sparring, delegates deployment to
  Sonnet sub-agents in phases, and writes a consolidated change log.
  Activate with /scout-building.
model: opus
context: fork
allowed-tools: Read, Grep, Glob, Write, Edit, Bash, Agent, AskUserQuestion, mcp__Salesforce_DX__retrieve_metadata, mcp__Salesforce_DX__deploy_metadata, mcp__Salesforce_DX__run_soql_query, mcp__Salesforce_DX__assign_permission_set, mcp__Salesforce_DX__list_all_orgs, mcp__Salesforce_DX__run_code_analyzer
---

# Scout Building — Opus Orchestrator

You are the orchestrator. You do NOT deploy metadata directly. You parse the spec,
construct sub-agent prompts from templates, spawn sub-agents, validate their results,
and write the change log.

Read @.claude/skills/demo-lessons/SKILL.md — focus on the **Building Lessons** section. Do not repeat known mistakes.

---

## Deployment Philosophy

The SE approved the scope during sparring. Your job is autonomous execution via sub-agents.
Each sub-agent gets a complete brief — spec section + relevant skills + deployment rules — and
works independently. You track results and handle failures.

**Safe operations — fully autonomous (no SE input required):**
- Custom fields on standard or custom objects
- Record types
- Page layout field additions (active layout only — always query ProfileLayout first)
- Lightning app modifications and custom tabs
- Permission sets and assignment
- Data seeding (single object)

**Gated operations — one upfront confirmation per category, then autonomous:**
- Flows, Apex, LWC, Agentforce

For each gated category: fire a macOS notification to alert the SE, present the single
confirmation question, wait for yes/no. Only spawn the sub-agent after receiving yes.

```bash
osascript -e 'display notification "[what you are about to deploy]" with title "SF Demo Scout — Input Needed"'
```

---

## Step 1: MCP Probe

Run a single MCP probe to confirm connectivity:
- Call `run_soql_query` with: `SELECT Id FROM Organization LIMIT 1`
- If it returns a result -> MCP is active, proceed
- If it fails or times out -> warn the SE:
  > "MCP is not responding. Quit VS Code fully (CMD+Q), reopen, and run /scout-building again.
  > If this persists, check that .mcp.json exists in the project root."
  Stop. Do not proceed without MCP.

---

## Step 2: Model Gate

Fire a macOS notification:
```bash
osascript -e 'display notification "Scout Building requires Opus 4.6 — switch model now if needed." with title "SF Demo Scout — Model Check"'
```

> "**Run `/model opus` now if you haven't already.** Confirm you're on Opus. (yes)"

**Wait for the SE's confirmation before proceeding.**

---

## Step 3: Confirm Org & Identify Customer

Run `sf config get target-org --json` and `sf org display --json`. Extract alias and username.

List org folders: `ls -d orgs/[alias]-*/`

Present both in a single message:
- No folders -> "Active org: [alias] ([username]). No customer folders found — run /scout-sparring first." Stop.
- One folder -> "Active org: [alias] ([username]). Customer: [customer]. Deploying here. Type 'switch' to change, or confirm."
- Multiple folders -> "Active org: [alias] ([username]). Multiple customers found: [list]. Which one?" Wait.

Wait for confirmation. Switch -> tell SE to run `/switch-org` first.

---

## Step 4: Load Spec

```
ls -lt orgs/[alias]-[customer]/demo-spec-*.md
```

- No specs -> "Run /scout-sparring first." Stop.
- One spec -> load automatically, tell SE which file.
- Multiple -> list with timestamps, ask SE to choose. Wait.

---

## Step 5: Load Org Audit

Find most recent audit in `orgs/[alias]-[customer]/`.
Check `Org Audit Used:` field in spec header.

- Audits match -> proceed.
- Audits differ -> warn: "Spec used [old audit] but latest audit is [new audit]. If you made manual changes between those dates, the spec may have conflicts. Continue? (yes/no)"
- No audit -> "Run /scout-sparring first." Stop.

---

## Step 6: Pre-Deployment Conflict Check

Cross-check spec against audit:
- Object/field API name collisions
- Flow conflicts with existing active flows
- LWC/Agentforce name collisions
- Spec items already marked with warnings -> surface explicitly

> "Pre-deployment check complete. [N] items to review:
> [issue] — [risk]
> Proceed? (yes / yes, skip flagged / no)"

Wait for go-ahead. This is the last SE input required before Phase 1.

---

## Step 7: Phased Deployment via Sub-Agents

### Phase Analysis

Read the spec and determine which phases are needed:

- **Phase 1 (Org Config):** Always runs if spec has Objects & Fields, Record Types, Permission Set, Data Seeding, Page Layouts, or Lightning App/Tabs sections.
- **Phase 2 (Flows/Apex/LWC):** Runs only if spec has Flows, Apex, or LWC sections.
- **Phase 3 (Agentforce):** Runs only if spec has Agentforce section.

Tell the SE which phases you identified:
> "Deployment plan: Phase 1 (Org Config) [+ Phase 2 (Flows/Apex/LWC)] [+ Phase 3 (Agentforce)]."

If only Phase 1 applies:
> "Only safe operations in this spec — no Flows, Apex, LWC, or Agentforce. No further SE confirmation needed. Deploying now."

### Sub-Agent Output Validation

After EVERY sub-agent returns, validate its output before proceeding:
1. Check that the output contains the expected sections (DEPLOYED, SKIPPED, PERMISSION SET/ROLLBACK COMMANDS, ISSUES).
2. If the output is missing expected sections, is truncated, or is incoherent: treat the phase as FAILED. Show the raw output to the SE:
   > "Sub-agent returned unexpected output for Phase [N]. Raw output below. Retry with a fresh sub-agent, or skip this phase?"
3. If retry also produces invalid output: record as FAILED in the change log and tell the SE to start a fresh session for this phase.

### Template Usage

When constructing sub-agent prompts from template files:
- The frontmatter (YAML between `---` markers) and the meta-description paragraph are for you — do not include them in the sub-agent prompt.
- Use only the content below the second `---` separator as the prompt body.
- Replace all `{{PLACEHOLDER}}` strings with actual content.
- If a reference section is not needed (e.g., Apex skill when no Apex is in scope), remove the entire section header and placeholder from the prompt.

### Phase 1: Org Config (Sonnet sub-agent)

**Prepare the sub-agent prompt:**
1. Read `.claude/skills/demo-building-phase1-prompt/SKILL.md` — this is the prompt template.
2. Read the AFV skill files and inject their content into the template placeholders:
   - `.claude/skills/generating-custom-object/SKILL.md` -> `{{GENERATING_CUSTOM_OBJECT_SKILL}}`
   - `.claude/skills/generating-custom-field/SKILL.md` -> `{{GENERATING_CUSTOM_FIELD_SKILL}}`
   - `.claude/skills/generating-permission-set/SKILL.md` -> `{{GENERATING_PERMISSION_SET_SKILL}}`
3. Fill remaining placeholders:
   - `{{ORG_ALIAS}}` and `{{ORG_USERNAME}}` from Step 3
   - `{{SPEC_SECTIONS}}` — paste the relevant spec sections (Objects & Fields, Record Types, Permission Set, Data Seeding, Page Layouts, Lightning App / Tabs)

Spawn: `Agent(description="Phase 1: Org Config deployment", model="sonnet", prompt=[constructed prompt])`

**After Phase 1 returns:** Validate output (see Sub-Agent Output Validation above). Parse deployed items, failures, and skipped items. If critical items failed (objects that Phase 2/3 depend on), warn the SE before continuing.

### Phase 2: Flows / Apex / LWC (Sonnet sub-agent) — if applicable

**Before spawning:** Fire the SE confirmation gate.

```bash
osascript -e 'display notification "About to deploy Flows/Apex/LWC — review the list and confirm." with title "SF Demo Scout — Input Needed"'
```

List what will be deployed from the spec and ask:
> "About to deploy: [plain English list]. Proceed? (yes/no)"

Wait for confirmation. If no, record as skipped. If yes:

**Prepare the sub-agent prompt:**
1. Read `.claude/skills/demo-building-phase2-prompt/SKILL.md` — this is the prompt template.
2. Read skill files and inject into placeholders:
   - `.claude/skills/sf-flow/SKILL.md` -> `{{SF_FLOW_SKILL}}`
   - `.claude/skills/sf-apex/SKILL.md` -> `{{SF_APEX_SKILL}}` (only if Apex is in scope — if not, remove the entire "Reference: Apex Generation Rules" section from the prompt)
   - Read `.claude/skills/demo-deployment-rules/SKILL.md`, extract the Flow Rules, Apex Rules, and LWC Rules sections -> `{{DEPLOYMENT_RULES_GATED}}`
3. Fill remaining placeholders:
   - `{{ORG_ALIAS}}` and `{{ORG_USERNAME}}`
   - `{{PHASE1_SUMMARY}}` — summary from Phase 1 (objects, fields, permission set deployed)
   - `{{SPEC_SECTIONS}}` — paste the Flows, Apex, and LWC spec sections

Spawn: `Agent(description="Phase 2: Flows/Apex/LWC deployment", model="sonnet", prompt=[constructed prompt])`

**After Phase 2 returns:** Validate output. Parse results.

### Phase 3: Agentforce (Sonnet sub-agent) — if applicable

**Before spawning:** Fire the SE confirmation gate.

```bash
osascript -e 'display notification "About to deploy Agentforce agent — review and confirm." with title "SF Demo Scout — Input Needed"'
```

Present the agent details from the spec and ask:
> "About to deploy: [agent name, topics, actions]. Proceed? (yes/no)"

Wait for confirmation. If no, record as skipped. If yes:

**Prepare the sub-agent prompt:**
1. Read `.claude/skills/demo-building-phase3-prompt/SKILL.md` — this is the prompt template.
2. Read `.claude/skills/developing-agentforce/SKILL.md` -> `{{DEVELOPING_AGENTFORCE_SKILL}}`
3. Fill remaining placeholders:
   - `{{ORG_ALIAS}}` and `{{ORG_USERNAME}}`
   - `{{PRIOR_PHASES_SUMMARY}}` — summary from Phase 1 and Phase 2
   - `{{SPEC_SECTIONS}}` — paste the Agentforce spec section

Spawn: `Agent(description="Phase 3: Agentforce deployment", model="sonnet", prompt=[constructed prompt])`

**After Phase 3 returns:** Validate output. Parse results.

---

## Step 8: Change Log, Lessons, and Done

### 8a: Write Change Log

Consolidate results from all phases into a single change log.
Use the template in @.claude/skills/demo-change-log/SKILL.md

The change log must include:
- Everything from all sub-agent reports (deployed, skipped, permission set, data, issues)
- Rollback commands from Phase 2 and Phase 3
- Which phases ran and which were skipped
- Any phases that FAILED validation (raw output preserved)

### 8b: Propose Lessons

Review the session for:
- Two-attempt failures reported by sub-agents (what failed and why)
- Sub-agent output validation failures (what went wrong)
- Unexpected conflict check findings from Step 6
- SE corrections during gated confirmations
- Permission set or layout issues reported by sub-agents

If any occurred, propose 1-3 candidate lessons:

> "A few things worth remembering for next time:
> 1. [lesson]
> 2. [lesson]
> Add these to lessons? (yes / edit / skip)"

If approved, append to the **Building Lessons** section of `.claude/skills/demo-lessons/SKILL.md` with today's date. If the deployment was clean, skip silently.

### 8c: Done

**Do NOT fire the completion notification until 8a and 8b are complete.**

```bash
osascript -e 'display notification "Deployment complete. Review the change log." with title "SF Demo Scout — Done"'
```
