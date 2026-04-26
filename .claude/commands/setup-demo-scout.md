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

## Step 0: Slack MCP Auth Check

The Slack MCP is registered at user scope by `install.sh` but OAuth must complete inside a Claude Code session. Detect auth state before anything else so the SE knows whether to run `/mcp-auth` now or proceed.

Run this probe:

```bash
security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null | \
  python3 -c "import json,sys; d=json.loads(sys.stdin.read()); oauth=d.get('mcpOAuth',{}); slack=[k for k in oauth if k.startswith('slack')]; tok=oauth[slack[0]].get('accessToken') if slack else None; print('authenticated' if tok else 'needs_auth')" 2>/dev/null || echo "needs_auth"
```

Interpret the single-word output:

- `authenticated` — Slack MCP is ready. Tell the SE:
  > "Slack MCP is authenticated. Proceeding to org setup."
  Continue to Step 1.

- `needs_auth` (or any other output) — tell the SE:
  > "Slack MCP needs authentication before we continue. It powers customer canvas lookups during sparring and the post-deployment handover canvas.
  >
  > **Run `/mcp-auth` in this session now.** A browser window will open for Salesforce SSO.
  >
  > For headless/SSH environments, use `/mcp-device-auth` instead.
  >
  > When you're back, type `continue` and I'll verify and proceed to org setup. If you'd rather skip Slack entirely for now, type `skip` — Slack features will stay dormant until you re-run `/setup-demo-scout`."

Wait for the SE's reply.

- If `continue`: re-run the probe. If `authenticated`, proceed to Step 1. If still `needs_auth`, tell the SE Slack auth didn't complete and ask whether to retry or skip.
- If `skip`: acknowledge and proceed to Step 1.

## Step 1: Check for Existing Org Connection

```bash
sf config get target-org --json
sf org display --json
```

If the org is authenticated and healthy, tell the SE:
> "Found an existing org connection: [alias] ([username]). Skipping login."

Then skip to Step 2.5 — starter files must always run (this command is re-invoked on every `update.sh`, and the starter files must exist before `/scout-sparring` can read them).

If no org is set, or auth has expired, proceed to Step 2.

## Step 2: Connect the Demo Org

Ask the SE for an alias first:
> "What alias should I use for this org? (short, lowercase, e.g. `lsdo-apr26`, `evident-sdo`, `karl-storz-service`)"

Wait for the reply. Then tell the SE:
> "I'll open a browser now — log in with your **demo org credentials** (not your Salesforce SSO / Okta login). This is the org you want to demo from."

Then run (substitute the alias the SE provided):

```bash
sf org login web --alias [alias] --set-default
```

Wait for the browser login to complete. Then retrieve org details:

```bash
sf org display --target-org [alias] --json
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

If either file already exists, leave it untouched.

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