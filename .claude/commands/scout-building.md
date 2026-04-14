---
name: scout-building
description: >
  Sonnet 4.6 deployment mode for SF Demo Prep.
  Loads a completed spec from /scout-sparring, cross-checks it against
  the org audit, flags conflicts, and deploys to the active Salesforce org.
  Activate with /scout-building.
model: sonnet
context: fork
allowed-tools: Read, Grep, Glob, Write, Edit, Bash, mcp__Salesforce_DX__retrieve_metadata, mcp__Salesforce_DX__deploy_metadata, mcp__Salesforce_DX__run_soql_query, mcp__Salesforce_DX__assign_permission_set, mcp__Salesforce_DX__list_all_orgs, mcp__Salesforce_DX__run_code_analyzer
---

# Scout Building — Sonnet 4.6 Org Deployment

Before deploying any Flows, Apex, LWC, or Agentforce: read @.claude/skills/_demo-deployment-rules/SKILL.md
Read @.claude/skills/_demo-lessons/SKILL.md — focus on the **Building Lessons** section. Do not repeat known mistakes.

## Deployment Philosophy

Once the spec is confirmed, deploy autonomously. Do not ask for confirmation on individual MCP calls, file writes, or metadata pushes. The SE has already approved the scope during sparring — execution is your job.

**Safe operations — fully autonomous (no SE input required):**
- Custom fields on standard or custom objects
- Record types
- Page layout field additions (active layout only — always query ProfileLayout first)
- Lightning app modifications and custom tabs
- Permission sets and assignment
- Data seeding (single object)

**Gated operations — one upfront confirmation per category, then autonomous:**
- Flows, Apex, LWC, Agentforce

For each gated category: fire a macOS notification to alert the SE, present the single confirmation question, wait for yes/no, then proceed without further interruption.

```bash
osascript -e 'display notification "[what you are about to deploy]" with title "SF Demo Scout — Input Needed"'
```

---

## Step 1: MCP Probe

Run a single MCP probe to confirm connectivity:
- Call `run_soql_query` with: `SELECT Id FROM Organization LIMIT 1`
- If it returns a result → MCP is active, proceed
- If it fails or times out → warn the SE:
  > "⚠️ MCP is not responding. Quit VS Code fully (CMD+Q), reopen, and run /scout-building again.
  > If this persists, check that .mcp.json exists in the project root."
  Stop. Do not proceed without MCP — deployment depends on it.

---

## Step 2: Confirm Active Org

Run `sf config get target-org --json` and `sf org display --json`.
Extract alias and username.

> "Active org: [alias] ([username]). Deploying here. Type 'switch' to change, or confirm."

Wait for confirmation. Switch → tell SE to run `/switch-org` first.

---

## Step 3: Identify Customer Folder

List org folders:
```
ls -d orgs/[alias]-*/
```

- No folders → "Run /scout-sparring first." Stop.
- One folder → use it, tell SE which customer.
- Multiple → list them, ask SE to choose. Wait.

---

## Step 4: Load Spec

```
ls -lt orgs/[alias]-[customer]/demo-spec-*.md
```

- No specs → "Run /scout-sparring first." Stop.
- One spec → load automatically, tell SE which file.
- Multiple → list with timestamps, ask SE to choose. Wait.

---

## Step 5: Load Org Audit

Find most recent audit in `orgs/[alias]-[customer]/`.
Check `Org Audit Used:` field in spec header.

- Audits match → proceed.
- Audits differ → warn: "Spec used [old audit] but latest audit is [new audit]. If you made manual changes between those dates, the spec may have conflicts. Continue? (yes/no)"
- No audit → "Run /scout-sparring first." Stop.

---

## Step 6: Pre-Deployment Conflict Check

Cross-check spec against audit:
- Object/field API name collisions → ⚠️
- Flow conflicts with existing active flows → ⚠️
- LWC/Agentforce name collisions → ⚠️
- Spec items already marked ⚠️ → surface explicitly

> "Pre-deployment check complete. [N] items to review:
> ⚠️ [issue] — [risk]
> Proceed? (yes / yes, skip flagged / no)"

Wait for go-ahead. This is the last SE input required for safe operations.

---

## Step 7: Deploy

Log intent before every operation (written to terminal, not a pause for SE input).
Deploy in small increments — never batch unrelated changes.
Confirm success after each deploy via MCP feedback or deploy status.
On failure: plain-English explanation in terminal, fix only the failing element, redeploy. Two-attempt rule: if anything fails twice, add to SE Manual Checklist and continue with remaining items.

**Page layouts:** always query ProfileLayout first, retrieve and modify only the active assigned layout. Never assume which layout is active.

**Companion Permission Set:** run after every deployment creating objects, fields, record types, tabs, or apps. Do not wait for SE input — this is mandatory and automatic.

**Gated operations (Flows, Apex, LWC, Agentforce):**
Before deploying each category, fire the notification and ask the single confirmation:

```bash
osascript -e 'display notification "[plain English description of what will be deployed]" with title "SF Demo Scout — Input Needed"'
```

> "About to deploy: [plain English]. Proceed? (yes/no)"

Wait for answer. If yes, deploy the full category autonomously — no further confirmations within that category. If no, add to SE Manual Checklist and continue.

**Agentforce deploys last.** The ADLC skills (`developing-agentforce`, `testing-agentforce`) are large and consume significant context. Always complete all org config (fields, layouts, data, flows, permissions) before starting any Agentforce deployment. If context is already heavy after org config, write a partial change log and tell the SE to start a fresh session for the agent work.

Follow the deployment rules loaded above for all gated operations.

If context is getting long, save partial progress to
`orgs/[alias]-[customer]/changes-[YYYY-MM-DD]-[HHmm]-[CUSTOMER]-partial.md`
and tell the SE to start a fresh session.

---

## Step 8: Change Log, Lessons, and Done

### 8a: Write Change Log

Use the template in @.claude/skills/_demo-change-log/SKILL.md

### 8b: Propose Lessons

Review the session for:
- Two-attempt failures (what failed and why)
- Unexpected conflict check findings
- SE corrections during gated confirmations
- Permission set or layout issues that required workarounds

If any occurred, propose 1-3 candidate lessons:

> "A few things worth remembering for next time:
> 1. [lesson]
> 2. [lesson]
> Add these to lessons? (yes / edit / skip)"

If approved, append to the **Building Lessons** section of `.claude/skills/_demo-lessons/SKILL.md` with today's date. If the deployment was clean, skip silently.

### 8c: Done

**Do NOT fire the completion notification until 8a and 8b are complete.**

```bash
osascript -e 'display notification "Deployment complete. Review the change log." with title "SF Demo Scout — Done"'
```