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

After install, open the project in VS Code, start Claude Code, and run `/setup-demo-scout` to connect your first demo org.

## Demo Loop

Prepare a customer demo in two steps:

| Command | Model | What it does |
|---|---|---|
| `/scout-sparring` | Opus | Discovery sparring — takes customer context, audits the org, produces a structured demo spec |
| `/scout-building` | Opus | Orchestrates spec deployment via Sonnet sub-agents (org config → flows/apex/lwc → agentforce), writes a consolidated change log |

Supporting commands:

| Command | What it does |
|---|---|
| `/setup-demo-scout` | One-time setup: connects demo org |
| `/switch-org` | Switch active demo org (re-authenticates, updates project-local config) |
| `/sync-skills` | Pull latest external skills per `.claude/skills-manifest.yaml` (adds, updates, prunes orphans) |

### What it deploys

Safe operations run autonomously: custom objects, fields (including picklist value additions), record types, queues, permission sets, page layout changes, Lightning app/tab config, and demo data seeding.

Gated operations require a single SE confirmation before the category deploys: Flows (record-triggered only), Apex, LWC, and Agentforce agents (with post-activation smoke testing). Complex flows, screen flows, multi-agent orchestration, and Agentforce channel assignment are always deferred to an SE Manual Checklist.

### Artifacts

All artifacts are saved per-org in `orgs/[alias]-[customer]/`:
- `audit-[DATE]-[HHmm].md` — org state snapshot
- `demo-spec-[CUSTOMER]-[DATE]-[HHmm].md` — generated spec
- `changes-[DATE]-[HHmm]-[CUSTOMER].md` — deployment change log

## Pipeline Loop

Evolve the pipeline itself:

| Command | Model | What it does |
|---|---|---|
| `/project-sparring` | Opus | Architectural sparring — diagnoses issues, proposes changes, writes a deployment guide |
| `/project-building` | Sonnet | Applies the deployment guide mechanically, appends verification log |

Pipeline change history lives in `pipeline-changes/`:
- `pipeline-state.md` — current state, maintained by `/project-sparring`
- `[YYYY-MM-DD]/[HHmm]-[topic]-PLAN.md` — individual change plans with LOG sections

## Skills

Skills are domain-specific instruction sets loaded on demand by commands. They keep `CLAUDE.md` lean (under 100 lines) while giving each command deep context.

**Demo reference skills** (internal — loaded by commands, not user-invocable):
- `demo-deployment-rules` — gates for Flows, Apex, LWC, Agentforce
- `demo-org-audit` — audit format and procedure
- `demo-docs-consultation` — decision tree for Salesforce Docs MCP consultation

**Demo prompt fragments** (internal — eager-loaded or read at specific steps):
- `.claude/prompts/sparring-lessons.md`, `.claude/prompts/building-lessons.md` — mistakes to avoid
- `.claude/prompts/spec-template.md` — sparring spec output format
- `.claude/prompts/change-log-template.md` — building change log format
- `.claude/prompts/phase1.md`, `phase2.md`, `phase3.md` — sub-agent prompt templates

**Pipeline reference skills** (internal):
- `pipeline-lessons` — pipeline architecture lessons

**Community skills** — declared in `.claude/skills-manifest.yaml`, synced by `install.sh` and `/sync-skills`:
- `sf-flow`, `sf-permissions`, `sf-deploy`, `sf-apex`, `sf-soql`, `sf-data`, `sf-debug` — from [Jaganpro/sf-skills](https://github.com/Jaganpro/sf-skills)
- `generating-custom-field`, `generating-custom-object`, `generating-permission-set` — from [forcedotcom/afv-library](https://github.com/forcedotcom/afv-library)
- `developing-agentforce`, `testing-agentforce`, `observing-agentforce` — from [SalesforceAIResearch/agentforce-adlc](https://github.com/SalesforceAIResearch/agentforce-adlc)

The manifest is the single source of truth. To add, remove, or pin a version, edit the YAML and run `/sync-skills`. Session startup detects drift (orphans on disk, missing folders, upstream changes) and prompts you to re-sync.

## How it connects to Salesforce

The pipeline uses the [Salesforce DX MCP Server](https://github.com/salesforce/salesforce-mcp) (configured in `.mcp.json`) for metadata retrieval, deployment, SOQL queries, permission set assignment, and code analysis. Falls back to `sf` CLI when MCP is unavailable.

## Project structure

```
CLAUDE.md                     ← root instructions (under 100 lines)
.mcp.json                     ← Salesforce DX MCP server config
.claude/
  commands/                   ← slash commands
  skills/                     ← domain-specific instruction sets
  prompts/                    ← sub-agent prompt templates (phase1/2/3)
  scripts/                    ← shared scripts (sync-skills.sh)
  hooks/                      ← session startup checks
  skills-manifest.yaml        ← declarative source of truth for external skills
  settings.json               ← permission allow rules, session hooks
orgs/                         ← per-org artifacts (audits, specs, change logs)
pipeline-changes/             ← pipeline evolution history
force-app/                    ← SFDX project (for metadata operations)
install.sh                    ← one-time setup script
```

## Questions

Reach out to @Sebastian Schickhoff.
