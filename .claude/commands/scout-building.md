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

## Step 1: Confirm Active Org

Run:
```
sf config get target-org --json
sf org display --json
```

Extract alias, username, org ID (first 6 chars).

Tell the SE:
> "Active org: [alias] ([username]). Deploying here. Type 'switch' to change org, or confirm to continue."

Wait for confirmation. If they say switch, tell them to run `/switch-org` first.

---

## Step 2: Load Spec

Find all spec files in the project root:
```
ls -lt demo-spec-*.md
```

**If no spec files exist:**
> "No spec file found. Run /scout-sparring first to generate a deployment spec."
Stop.

**If exactly one spec exists:** load it automatically and tell the SE which file you're using.

**If multiple specs exist:** list them with dates and ask the SE which one to deploy:
> "Multiple specs found — which should I deploy?
> 1. demo-spec-[CUSTOMER-A]-[DATE].md
> 2. demo-spec-[CUSTOMER-B]-[DATE].md"

Wait for selection before continuing.

---

## Step 3: Load Org Audit

Org folder path: `orgs/[alias]-[ORG_ID_SHORT]/`

Find the most recent audit:
```
ls -lt orgs/[alias]-[ORG_ID_SHORT]/audit-*.md | head -1
```

Check which audit the spec was generated against (see `Org Audit Used:` field in spec header).

**If the spec audit and the most recent audit match:** load and proceed.

**If they differ** (spec used an older audit):
> "The spec was generated against [spec-audit-date] but the most recent audit is [latest-audit-date]. There may be org changes not reflected in the spec. Recommend running a fresh audit via /scout-sparring before deploying. Continue anyway? (yes/no)"

Wait for SE decision.

**If no audit exists for this org at all:**
> "No org audit found for [alias]. Run /scout-sparring first to audit the org and generate a spec."
Stop.

---

## Step 4: Pre-Deployment Conflict Check

Read the full spec and the full audit. Cross-check:

- Any object in the spec that already exists in the org → flag with ⚠️
- Any field API name collision → flag with ⚠️
- Any flow in the spec that conflicts with existing active flows → flag with ⚠️
- Any LWC component name collision → flag with ⚠️
- Any ⚠️ items already marked in the spec (Apex, LWC) → surface these explicitly

Present all flags to the SE before touching the org:

> "Pre-deployment check complete. Found [N] items to review:
> ⚠️ [issue] — [plain-English explanation of risk]
> Proceed with deployment? (yes / yes, skip flagged items / no)"

Wait for explicit go-ahead.

---

## Step 5: Deploy

Follow the Working Pattern from CLAUDE.md exactly:

1. State what you will do and why before every operation
2. Deploy in small increments — never batch unrelated changes
3. After each deploy: confirm success via deploy status or MCP feedback
4. On failure: explain error in plain English, fix only the failing element, redeploy
5. After every deployment that creates objects, fields, record types, tabs, or apps:
   deploy the Companion Permission Set (see CLAUDE.md) in the same operation
6. NEVER deploy Flow XML under any circumstance
7. Apex and LWC require explicit SE confirmation before deployment — stop and ask

If context is getting long mid-deployment, save progress to
`orgs/[alias]-[ORG_ID_SHORT]/changes-[YYYY-MM-DD]-[CUSTOMER]-partial.md`
and tell the SE to start a fresh session referencing that file.

---

## Step 6: Write Change Log

After all deployments complete (or if stopping early), write a change log to:
`orgs/[alias]-[ORG_ID_SHORT]/changes-[YYYY-MM-DD]-[CUSTOMER].md`

Use this format:

```markdown
# Change Log — [Customer] — [Date]
Org: [alias] ([username])
Spec: demo-spec-[CUSTOMER]-[DATE].md
Audit used: audit-[YYYY-MM-DD].md

## What Was Deployed
[Every component created or modified, grouped by type]
[Include API names, not just labels]

## What Was Skipped
[Items not deployed and why — conflicts, SE decision, second-attempt failure]

## Companion Permission Set
[Name, what it covers, assignment status]

## Apex Deployed (if any)
[Class/trigger names, plain-English description]
Rollback:
  sf project delete source --metadata ApexClass:[ClassName] --target-org [alias]
  sf project delete source --metadata ApexTrigger:[TriggerName] --target-org [alias]

## LWC Deployed (if any)
[Component names, plain-English description]
Rollback:
  sf project delete source --metadata LightningComponentBundle:[ComponentName] --target-org [alias]

## Issues Encountered
[Errors, workarounds, anything that needed a second attempt]

## SE Must Do Next (in order)
1. [Prioritised manual steps — flows first, then layout arrangement, then data refinement]
2. [Be specific: "Open App Builder > Patient Record Page > drag Status field to top-right panel"]

## How to Verify
[Step-by-step test sequence: navigate here, click this, expect that]

## Open Questions for Next Session
[Unresolved items, suggested follow-up, anything to feed back into sparring]
```

After saving, output the full change log to the terminal and tell the SE:

> "Change log saved to orgs/[alias]-[ORG_ID_SHORT]/changes-[DATE]-[CUSTOMER].md. Review the 'SE Must Do Next' section above — flows and layout arrangement need to be done before the demo."