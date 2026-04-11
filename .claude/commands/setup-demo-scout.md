---
description: Connect your demo org and run the first audit. Run once after install.sh.
allowed-tools: Bash, Read, Write, Edit
---

# SF Demo Scout — Org Setup

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
```

If a default org is already set, run:

```bash
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
- `id` (this is the Org ID)
- `instanceUrl`

## Step 4: Update CLAUDE.md

Open `CLAUDE.md` and replace the three placeholder values in the `## Org` block:
- `[YOUR ORG USERNAME]` → the username from Step 3
- `[YOUR ORG ID]` → the org ID from Step 3
- `[YOUR ORG INSTANCE URL]` → the instance URL from Step 3

Do not change anything else in CLAUDE.md.

Confirm the update by reading back the `## Org` section to the SE.

## Step 5: Run the First Org Audit

Tell the SE:
> "Running your first org audit — this verifies MCP is working and gives Demo Scout a baseline to work from."

Using MCP `retrieve_metadata`, audit the org and save the result to `org-audit-[TODAY'S DATE].md`.

Include:
- Custom objects (API name, label)
- Existing flows (name, type, active/inactive)
- Existing custom permission sets
- Existing LWC components (if any)

If MCP is unavailable or returns empty results, tell the SE:
> "MCP isn't connecting. Check that `.mcp.json` is in the project root (not a subfolder) and restart VSCode. Then run `/setup-demo-scout` again."

Do not proceed if the audit is empty — MCP must be working for Demo Scout to function correctly.

## Step 6: Show Setup Summary

Print this summary to the terminal:

```
✅ SF Demo Scout — Setup Complete
====================================
Project:    [current directory]
Org:        demo-org ([username])
Audit:      org-audit-[date].md

Three commands to remember:
  /demo-scout     – start customer sparring
  /switch-org     – change demo orgs
  /model opusplan – Opus thinks, Sonnet builds

Ready to go! Close this session, reopen VSCode in this folder,
and type /demo-scout to start your first sparring session.
```
