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

## Step 1: Confirm Active Org

Run `sf config get target-org --json` and `sf org display --json`.
Extract alias, username, org ID (first 6 chars).

> "Active org: [alias] ([username]). Deploying here. Type 'switch' to change, or confirm."

Wait for confirmation. Switch → tell SE to run `/switch-org` first.

---

## Step 2: Load Spec

```
ls -lt demo-spec-*.md
```

- No specs → "Run /scout-sparring first." Stop.
- One spec → load automatically, tell SE which file.
- Multiple → list with dates, ask SE to choose. Wait.

---

## Step 3: Load Org Audit

Find most recent audit in `orgs/[alias]-[ORG_ID_SHORT]/`.
Check `Org Audit Used:` field in spec header.

- Audits match → proceed.
- Audits differ → warn: "Spec used [old-date] but latest audit is [new-date]. If you made manual changes between those dates, the spec may have conflicts. Continue? (yes/no)"
- No audit → "Run /scout-sparring first." Stop.

---

## Step 4: Pre-Deployment Conflict Check

Cross-check spec against audit:
- Object/field API name collisions → ⚠️
- Flow conflicts with existing active flows → ⚠️
- LWC/Agentforce name collisions → ⚠️
- Spec items already marked ⚠️ → surface explicitly

> "Pre-deployment check: [N] items to review:
> ⚠️ [issue] — [risk]
> Proceed? (yes / yes, skip flagged / no)"

Wait for go-ahead.

---

## Step 5: Deploy

Follow Working Pattern from CLAUDE.md:
1. State intent before every operation
2. Small increments — never batch unrelated changes
3. Confirm success after each deploy
4. On failure: plain-English explanation, fix, redeploy
5. Companion Permission Set after every deployment creating objects/fields/record types/tabs/apps
6. Flows, Apex, LWC, Agentforce: SE confirmation required — follow @.claude/skills/deployment-rules/SKILL.md

If context is getting long, save partial progress to
`orgs/[alias]-[ORG_ID_SHORT]/changes-[YYYY-MM-DD]-[CUSTOMER]-partial.md`
and tell the SE to start a fresh session.

---

## Step 6: Write Change Log

Use the template in @.claude/skills/change-log/SKILL.md