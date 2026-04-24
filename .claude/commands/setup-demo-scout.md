---
name: setup-demo-scout
description: >
  Connect your demo org. Run once after cloning the repo.
model: sonnet
allowed-tools: Bash, Read, Write, mcp__Salesforce_DX__list_all_orgs
---

# SF Demo Prep — Org Setup

You are completing the one-time org setup for a Salesforce Solutions Engineer.
The project files are already in place from the GitHub clone. Your job is to:
connect the demo org and verify the connection.

Do not create or overwrite any existing config files. They are already correct.

## Step 1: Check for Existing Org Connection

```bash
sf config get target-org --json
sf org display --json
```

If the org is authenticated and healthy, skip to Step 3 — tell the SE:
> "Found an existing org connection: [alias] ([username]). Skipping login."

If no org is set, or auth has expired, proceed to Step 2.

## Step 2: Connect the Demo Org

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

## Step 2.5: Create Starter Files

If `orgs/sparring-lessons.md` does not exist, create it:

```markdown
# Sparring Lessons

Accumulated lessons from scout-sparring sessions. Add new lessons at the end with today's date.
```

If `orgs/building-lessons.md` does not exist, create it:

```markdown
# Building Lessons

Accumulated lessons from scout-building sessions. Add new lessons at the end with today's date.
```

If `orgs/slack-sources.md` does not exist, create it with this content:

```markdown
# Slack Sources — General

Channels and canvases useful across demo prep sessions in this account team's
Slack. Scout reads this file when pulling Slack context during /scout-sparring.

**Slack is background colour, not ground truth.** SE knowledge and Salesforce
documentation take precedence in specs and handovers. Slack content gets
attributed to source messages so you can trace where something came from —
it is not synthesised into assertive claims.

Handover Canvas: off  <!-- on / off — when on, /scout-building writes the demo handover to a new Slack canvas you own -->

## Channels

<!-- Add channels you find useful across customers. One per line. Format: - #channel-name — short note on why it helps -->

## Canvases

<!-- Add Slack canvas URLs you reference regularly. One per line. Format: - [Canvas title](full-canvas-url) — short note -->
```

If any of the three files already exist, leave them untouched.

## Step 3: Show Setup Summary

Print this summary to the terminal:

```
✅ SF Demo Prep — Setup Complete
====================================
Project:    [current directory]
Org:        [alias] ([username])

Three commands to remember:
  /scout-sparring  – Opus discovery sparring + spec generation
  /scout-building  – Opus orchestrator for org deployment (spawns Sonnet sub-agents)
  /switch-org      – change active demo org

Ready to go! Restart VS Code (CMD+Q), then type /scout-sparring to begin.
Opus will audit the org and create the customer folder as part of the sparring session.
```