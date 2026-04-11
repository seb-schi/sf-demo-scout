---
description: Connect your demo org and run the first audit. Run once after cloning the repo.
allowed-tools: Bash, Read, Write, Edit, mcp__Salesforce_DX__retrieve_metadata, mcp__Salesforce_DX__run_soql_query, mcp__Salesforce_DX__list_all_orgs
---

# SF Demo Prep — Org Setup

You are completing the one-time org setup for a Salesforce Solutions Engineer.
The project files are already in place from the GitHub clone. Your job is to:
connect the demo org, fill in CLAUDE.md with real org details, and run the first audit.

Do not create or overwrite any existing config files. They are already correct.

## Step 1: Check AWS SSO

```bash
aws sts get-caller-identity --profile claude
```

If this fails, stop and tell the SE:

> "Your AWS SSO session isn't active. Open Terminal and run:
> `aws sso login --profile claude`
> Then come back and type `/setup-demo-scout` again."

Do not proceed until AWS is confirmed active.

## Step 2: Check for Existing Org Connection

```bash
sf config get target-org --json
sf org display --json
```

If the org is authenticated and healthy, skip to Step 4 — tell the SE:
> "Found an existing org connection: [alias] ([username]). Skipping login and going straight to the audit."

If no org is set, or auth has expired, proceed to Step 3.

## Step 3: Connect the Demo Org

Tell the SE:
> "I'll open a browser now — log in with your **demo org credentials** (not your Salesforce SSO / Okta login). This is the org you want to demo from."

Then run:

```bash
sf org login web --alias demo-org --set-default
```

Wait for the browser login to complete. Then retrieve org details:

```bash
sf org display --target-org demo-org --json
```

Extract and store:
- `username`
- `id` (this is the Org ID — use the full 18-char value)
- `instanceUrl`

## Step 4: Update CLAUDE.md

Open `CLAUDE.md` and replace the placeholder values in the `## Org` block:
- `[YOUR ORG USERNAME]` → the username from Step 3
- `[YOUR ORG ID]` → the org ID from Step 3
- `[YOUR ORG INSTANCE URL]` → the instance URL from Step 3

Do not change anything else in CLAUDE.md.

Confirm the update by reading back the `## Org` section to the SE.

Note: the CLAUDE.md Org section is documentation only — all slash commands read
org identity from `sf config get target-org` at runtime. CLAUDE.md is not used
as a config source.

## Step 5: Run the First Org Audit

Tell the SE:
> "Running your first org audit — this verifies MCP is working and gives the pipeline a baseline to work from."

Determine the org folder key:
- Alias: from Step 3
- Org ID short: first 6 characters of the 18-char org ID from Step 3
- Folder: `orgs/[alias]-[ORG_ID_SHORT]/`

Create the folder:
```bash
mkdir -p orgs/[alias]-[ORG_ID_SHORT]/
```

Using MCP `retrieve_metadata`, audit the org and save the result to:
`orgs/[alias]-[ORG_ID_SHORT]/audit-[YYYY-MM-DD].md`

The audit must include:
- Custom objects (API name, label, record count via run_soql_query where feasible)
- Key fields and relationships per object
- Existing flows (name, type, active/inactive, trigger object, brief logic summary)
- Existing LWC components (name, purpose if inferrable from source)
- Existing custom permission sets (custom only, not standard)
- Notable gaps or risks relative to standard HLS demo scenarios

If MCP is unavailable or returns empty results, tell the SE:
> "MCP isn't connecting. Check that `.mcp.json` is in the project root (not a subfolder) and restart VS Code. Then run `/setup-demo-scout` again."

Do not proceed if the audit is empty — MCP must be working for the pipeline to function correctly.

## Step 6: Show Setup Summary

Print this summary to the terminal:

```
✅ SF Demo Prep — Setup Complete
====================================
Project:    [current directory]
Org:        [alias] ([username])
Org folder: orgs/[alias]-[ORG_ID_SHORT]/
Audit:      audit-[YYYY-MM-DD].md

Three commands to remember:
  /scout-sparring  – Opus 4.6 discovery sparring + spec generation
  /scout-building  – Sonnet 4.6 org deployment from completed spec
  /switch-org      – change active demo org

Ready to go! Close this session, reopen VS Code in this folder,
and type /scout-sparring to start your first sparring session.
```