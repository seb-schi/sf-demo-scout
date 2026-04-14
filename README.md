# SF Demo Scout

Claude Code pipeline for configuring Salesforce demo orgs from customer discovery notes. Two loops: a **demo loop** (sparring → building) that prepares customer demos, and a **pipeline loop** (architect → deployment) that evolves the tooling itself.

## Prerequisites

- macOS (Apple Silicon or Intel)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) with AWS Bedrock access
- A Salesforce demo org (SDO, IDO, or personal developer org)

## Install

```bash
git clone https://github.com/seb-schi/sf-demo-scout ~/Projects/sf-demo-scout
cd ~/Projects/sf-demo-scout && bash install.sh
```

The install script sets up Homebrew, Node.js, Python, Salesforce CLI, the SFDX project structure, community Salesforce skills, Agentforce ADLC skills, and shell environment variables for Claude Code model routing.

After install, open the project in VS Code, start Claude Code, and run `/setup-demo-scout` to connect your first demo org and run an initial audit.

## Demo Loop

Prepare a customer demo in two steps:

| Command | Model | What it does |
|---|---|---|
| `/scout-sparring` | Opus 4.6 | Discovery sparring — takes customer context, audits the org, produces a structured demo spec |
| `/scout-building` | Sonnet 4.6 | Deploys the spec to the org autonomously, writes a change log with rollback instructions |

Supporting commands:

| Command | What it does |
|---|---|
| `/setup-demo-scout` | One-time setup: connects org, updates CLAUDE.md, runs first audit |
| `/switch-org` | Switch active demo org (re-authenticates, updates config) |

### What it deploys

Safe operations run autonomously: custom objects, fields, record types, permission sets, page layout changes, Lightning app/tab config, and demo data seeding.

Gated operations require a single SE confirmation before the category deploys: Flows (record-triggered only), Apex, LWC, and Agentforce agents. Complex flows, screen flows, and multi-agent orchestration are always deferred to an SE Manual Checklist.

### Artifacts

All artifacts are saved per-org in `orgs/[alias]-[customer]/`:
- `audit-[DATE]-[HHmm].md` — org state snapshot
- `demo-spec-[CUSTOMER]-[DATE]-[HHmm].md` — generated spec
- `changes-[DATE]-[HHmm]-[CUSTOMER].md` — deployment change log

## Pipeline Loop

Evolve the pipeline itself:

| Command | Model | What it does |
|---|---|---|
| `/project-architect` | Opus 4.6 | Architectural sparring — diagnoses issues, proposes changes, writes a deployment guide |
| `/project-deployment` | Sonnet 4.6 | Applies the deployment guide mechanically, appends verification log |

Pipeline change history lives in `pipeline-changes/`:
- `pipeline-state.md` — current state, maintained by `/project-architect`
- `[YYYY-MM-DD]/[HHmm]-[topic]-PLAN.md` — individual change plans with LOG sections

## Skills

Skills are domain-specific instruction sets loaded on demand by commands. They keep `CLAUDE.md` lean (under 100 lines) while giving each command deep context.

**Scout skills** (demo loop):
- `scout-lessons` — accumulated sparring/building lessons
- `scout-deployment-rules` — gates for Flows, Apex, LWC, Agentforce
- `scout-org-audit` — audit format and procedure
- `scout-change-log` — change log template
- `scout-spec-format` — spec output format

**Pipeline skills:**
- `pipeline-lessons` — pipeline architecture lessons

**Community skills** (installed by `install.sh`):
- `sf-flow`, `sf-metadata`, `sf-permissions`, `sf-deploy`, `sf-apex`, `sf-soql`, `sf-data`, `sf-debug`, `sf-ai-agentforce` — from [Jaganpro/sf-skills](https://github.com/Jaganpro/sf-skills)
- `developing-agentforce`, `testing-agentforce`, `observing-agentforce` — from [SalesforceAIResearch/agentforce-adlc](https://github.com/SalesforceAIResearch/agentforce-adlc)

## How it connects to Salesforce

The pipeline uses the [Salesforce DX MCP Server](https://github.com/salesforce/salesforce-mcp) (configured in `.mcp.json`) for metadata retrieval, deployment, SOQL queries, permission set assignment, and code analysis. Falls back to `sf` CLI when MCP is unavailable.

## Project structure

```
CLAUDE.md                     ← root instructions (under 100 lines)
.mcp.json                     ← Salesforce DX MCP server config
.claude/
  commands/                   ← slash commands
  skills/                     ← domain-specific instruction sets
  settings.json               ← permission allow rules, session hooks
  hooks/                      ← session startup checks
orgs/                         ← per-org artifacts (audits, specs, change logs)
pipeline-changes/             ← pipeline evolution history
force-app/                    ← SFDX project (for metadata operations)
install.sh                    ← one-time setup script
```

## Questions

Reach out to @Sebastian Schickhoff.
