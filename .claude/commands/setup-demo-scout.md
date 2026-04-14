---
name: setup-demo-scout
description: >
  Connect your demo org. Run once after cloning the repo.
allowed-tools: Bash, Read, Write, mcp__Salesforce_DX__list_all_orgs
---

# SF Demo Prep — Org Setup

You are completing the one-time org setup for a Salesforce Solutions Engineer.
The project files are already in place from the GitHub clone. Your job is to:
connect the demo org and verify the connection.

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
> "Found an existing org connection: [alias] ([username]). Skipping login."

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

## Step 4: Show Setup Summary

Print this summary to the terminal:

```
✅ SF Demo Prep — Setup Complete
====================================
Project:    [current directory]
Org:        [alias] ([username])

Three commands to remember:
  /scout-sparring  – Opus 4.6 discovery sparring + spec generation
  /scout-building  – Sonnet 4.6 org deployment from completed spec
  /switch-org      – change active demo org

Ready to go! Restart VS Code (CMD+Q), then type /scout-sparring to begin.
Opus will audit the org and create the customer folder as part of the sparring session.
```