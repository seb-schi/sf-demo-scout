---
name: scout-building
description: >
  Sonnet 4.6 deployment mode for SF Demo Prep.
  Loads a completed spec from /scout-sparring, cross-checks it against
  the org audit, flags conflicts, and deploys to the active Salesforce org.
  Activate with /scout-building.
model: us.anthropic.claude-sonnet-4-6
context: fork
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Write, Edit, Bash, mcp__Salesforce_DX__retrieve_metadata, mcp__Salesforce_DX__deploy_metadata, mcp__Salesforce_DX__run_soql_query, mcp__Salesforce_DX__assign_permission_set, mcp__Salesforce_DX__list_all_orgs, mcp__Salesforce_DX__run_code_analyzer
---

# Scout Building — Sonnet 4.6 Org Deployment

Before deploying any Flows, Apex, LWC, or Agentforce: read @.claude/skills/deployment-rules/SKILL.md

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

## Step 1: Confirm Active Org

Run `sf config get target-org --json` and `sf org display --json`.
Extract alias and username.

> "Active org: [alias] ([username]). Deploying here. Type 'switch' to change, or confirm."

Wait for confirmation. Switch → tell SE to run `/switch-org` first.

---

## Step 2: Identify Customer Folder

List org folders:
```
ls -d orgs/[alias]-*/
```

- No folders → "Run /scout-sparring first." Stop.
- One folder → use it, tell SE which customer.
- Multiple → list them, ask SE to choose. Wait.

---

## Step 3: Load Spec

```
ls -lt orgs/[alias]-[customer]/demo-spec-*.md
```

- No specs → "Run /scout-sparring first." Stop.
- One spec → load automatically, tell SE which file.
- Multiple → list with timestamps, ask SE to choose. Wait.

---

## Step 4: Load Org Audit

Find most recent audit in `orgs/[alias]-[customer]/`.
Check `Org Audit Used:` field in spec header.

- Audits match → proceed.
- Audits differ → warn: "Spec used [old audit] but latest audit is [new audit]. If you made manual changes between those dates, the spec may have conflicts. Continue? (yes/no)"
- No audit → "Run /scout-sparring first." Stop.

---

## Step 5: Pre-Deployment Conflict Check

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

## Step 6: Deploy

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

Follow @.claude/skills/deployment-rules/SKILL.md for all gated operations.

If context is getting long, save partial progress to
`orgs/[alias]-[customer]/changes-[YYYY-MM-DD]-[HHmm]-[CUSTOMER]-partial.md`
and tell the SE to start a fresh session.

---

## Step 7: Write Change Log

Use the template in @.claude/skills/change-log/SKILL.md

Fire a final notification when complete:
```bash
osascript -e 'display notification "Deployment complete. Review the change log." with title "SF Demo Scout — Done"'
```