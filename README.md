# SF Demo Scout

**A Claude Code pipeline for Salesforce SEs.** Audits your demo org, spars with you on the scenario, and deploys the configuration via Headless 360 — so you ship CLI-driven demos this week instead of next quarter.

## Why Scout exists

The SE role is shifting. SEs are increasingly asked to do post-sales activation work — configuring real Salesforce orgs through CLI-native tools that didn't exist eighteen months ago. Most SEs come from a business background, not engineering. The gap between what the platform now expects and what we trained for is real.

The tooling landscape isn't helping. Five MCP servers, twenty community skill repos, half a dozen ways to stand up Claude Code, and no clear path through any of it. The cost of starting is high, and the cost of starting wrong is higher.

Scout is the on-ramp. It does three things:

1. **Audits the org you're connected to** — a complete snapshot of what already exists, so you build into reality instead of around it.
2. **Spars with you on the scenario** — guided discovery from customer notes through to a structured deployment spec.
3. **Builds the configuration** — Opus orchestrates Sonnet sub-agents that deploy via Headless 360, with a change log and rollback commands.

It works because the official Salesforce AgentForce skills are baked in. Scout doesn't improvise Apex, Flow XML, or agent metadata from training data — it loads the same authoring rules and validation patterns the platform team publishes. You're not vibe-coding the platform layer; you're driving it.

## What Scout builds

Scout-building deploys the demo your spec describes — custom objects and fields, permission sets, page layout field additions, business processes, paths, flows, Apex, LWC, Agentforce agents with smoke tests, data seeding. The output is a working demo, not a sketch. Every change log carries an SE Manual Checklist for the things Scout deliberately doesn't touch: visual layout in App Builder, complex multi-screen flows, OmniStudio, channel assignment, customer-specific narrative tuning. Those belong with SE judgment, and the checklist makes sure none of them are forgotten.

The point isn't to replace SE expertise. It's to make sure you don't deploy the kind of broken metadata that wastes a demo — and to take care of the well-understood scaffolding so your time goes to the parts that need you. Scout is the on-ramp, not the autopilot.

**Showtime is different.** It's the bounded format for live customer engagement: a deliberately small slice that deploys live within the hour, with the customer in the room. Five hard envelopes, no stacking beyond two narrow combinations — so the live deploy is a guarantee, not a hope. See the Showtime section below.

---

## What You Need

| Ingredient | Description |
|------------|-----|
| macOS | Apple Silicon or Intel. |
| Claude Code via LLMGW | Opus thinks. Sonnet builds. Install Claude Code first using the **Installing Claude Code for Solutions** canvas (one command, one Google sign-in). |
| A Salesforce demo org | SDO, IDO, sandbox, or personal dev org. |

---

## Install

In your macOS Terminal, run:

```rm -rf ~/claude-projects/sf-demo-scout
bash -c "$(curl -fsSL https://raw.githubusercontent.com/seb-schi/sf-demo-scout/main/bootstrap.sh)"
```

One command. Bootstrap clones the repo to `~/claude-projects/sf-demo-scout`, runs the full installer (Homebrew, Node.js, Python, Salesforce CLI, Slack MCP registration, 16 community skills, CLI self-updates), and drops you straight into a Claude Code session running `/setup-demo-scout`. Idempotent — safe to re-run. If the repo already exists, bootstrap routes to `update.sh` instead.

Prerequisites: `git` (via `xcode-select --install`) and Claude Code (via the *Installing Claude Code for Solutions* canvas — one Google sign-in). Bootstrap tells you if either is missing.

For the full setup walkthrough — screenshots, VS Code extensions, Slack OAuth, troubleshooting — see the **Salesforce Demo Scout** canvas in Slack.

## Updating

```bash
bash ~/claude-projects/sf-demo-scout/update.sh
```

Or re-run the bootstrap one-liner — it routes to `update.sh` automatically when the repo already exists. Scout backs up your org data (audits, specs, change logs), nukes the install, re-clones fresh, restores your data, and lands you back in a Claude Code session running `/setup-demo-scout`. Clean slate. ~30 seconds.

> Running from VS Code? `update.sh` opens Terminal.app for you if you launch it from VS Code's integrated terminal. Close VS Code, let it run, reopen after.

---

## How It Works

Two commands.

| Step | Command | What happens |
|------|---------|--------------|
| **Spar** | `/scout-sparring` | You share customer context. Opus audits the org, researches platform capabilities, asks clarifying questions, and produces a structured demo spec. |
| **Build** | `/scout-building` | Opus reads the spec, orchestrates Sonnet sub-agents across three phases (org config → flows/apex/LWC → Agentforce), and writes a change log. |

Always spar first, build second.

### Showtime — live customer engagement

For the format where the customer is in the room and you want to ship something real before they leave: `/scout-sparring` → Showtime. Paste a 15-minute discovery transcript, get a holistic build plan plus a tightly-scoped slice that deploys live within the hour. Showtime is bounded by five hard envelopes (single object + layout, single before-save flow, single Apex class, single Agentforce agent with standard actions only, idempotent data seeding) so the live deploy is a guarantee, not a hope.

### Supporting commands

| Command | When to use it |
|---------|---------------|
| `/setup-demo-scout` | First time connecting an org |
| `/switch-org` | Switching to a different demo org |

---

## What Scout Handles, and Where SE Judgment Takes Over

### Fully autonomous
Custom objects, fields, picklist values, record types, queues, permission sets, page layout field additions, Lightning apps and tabs, demo data seeding.

### One-time SE confirmation per category
Record-triggered Flows, simple screen flows (≤3 linear screens, up to 5 with justification), simple Apex, simple LWC, and Agentforce agents (with smoke testing). Confirm once per category, Scout handles the rest.

### Where SE judgment takes over
Complex screen flows (branching, subflows, File Upload, Data Table, custom LWC screen components), scheduled flows, multi-object flows, complex Apex/LWC, multi-agent orchestration, page layout visual arrangement, reports, dashboards, OmniStudio, customer-specific data refinement, narrative tuning. These were always SE territory — Scout doesn't half-do them, it leaves them. The change log surfaces every one of them in an SE Manual Checklist so nothing is forgotten.

---

## What You Get Back

After every run, Scout saves artifacts in `orgs/[alias]-[customer]/`:

| File | What's inside |
|------|---------------|
| `audit-*.md` | Org snapshot — objects, flows, agents, layouts, gaps |
| `demo-spec-*.md` | The deployment spec — your source of truth |
| `changes-*.md` | What got deployed, what to verify, what's on you |

These survive updates. They're your data — Scout just writes them.

---

## The Salesforce Connection

Scout talks to your org through three MCP servers:

**Salesforce DX MCP** — metadata deployment, SOQL queries, permission sets, code analysis, LWC scaffolding. The primary connection.

**Salesforce Docs MCP** — semantic search across official Salesforce docs. Scout checks release notes and dev guides during sparring and on unfamiliar deploy errors. Optional — degrades gracefully if unavailable.

**Slack MCP** — optional. Lets Scout skim a setup canvas or channel you name during sparring, and write the post-deployment handover brief to a canvas in your personal Slack. Registered user-scope by `install.sh`; `/setup-demo-scout` probes the macOS Keychain on first run and walks you through `/mcp-auth` if you're not yet signed in. Skip it and Scout carries on without Slack.

Scout falls back to the `sf` CLI when MCP is unavailable.

---

## Skills & Smarts

Scout's intelligence lives in **skills** — domain-specific instruction sets loaded on demand. They're why Scout knows Flow XML needs `<start><filters>` and not `processMetadataValues`, why it never sets `TabVisibility: DefaultOn`, and why it checks `EntityDefinition` flags before suggesting a trigger.

**Ships with the repo** (3 demo skills):
- `demo-deployment-rules` — the rulebook for deploying Flows, Apex, LWC, Agentforce
- `demo-org-audit` — how to audit an org properly
- `demo-docs-consultation` — when to consult docs vs. proceed from existing knowledge

**Downloaded at install** (16 community skills):
- 10 from [forcedotcom/sf-skills (Jaganpro branch)](https://github.com/forcedotcom/sf-skills/tree/Jaganpro/sf-skills) — SOQL, Apex, Flows, Permissions, Deploy, Data, Debug, LWC, Testing, Flex Estimator
- 6 from [forcedotcom/sf-skills](https://github.com/forcedotcom/sf-skills) — Custom Fields, Objects, Permission Sets, Agentforce dev/test/observe

These are the official Salesforce Agentforce Vibes skills plus the most-used community sets. Skills are managed declaratively via `.claude/skills-manifest.yaml`. Sync runs automatically during `install.sh` and `update.sh`; to re-sync mid-session without a full reinstall, run `.claude/scripts/sync-skills.sh`.

---

## What's In The Box

```
CLAUDE.md                       ← Root instructions
install.sh                      ← Full setup (idempotent)
update.sh                       ← Nuke-and-reinstall updater
.claude/
  commands/                     ← 6 slash commands (SE-facing + internal pipeline ops)
  skills/                       ← 3 demo skills (+ 16 community skills after install)
  prompts/                      ← Sub-agent templates, lessons, reference docs
  scripts/                      ← sync-skills.sh
  hooks/                        ← session-startup.sh (org check on every launch)
  settings.json                 ← Permissions and hooks config
  skills-manifest.yaml          ← Which community skills to sync from where
```

Generated at runtime (gitignored, yours to keep):
```
orgs/                           ← Your audits, specs, and change logs
.sf/                            ← Salesforce CLI local config
force-app/                      ← SFDX project (for metadata operations)
.mcp.json                       ← MCP server config (generated by setup)
```

---

## FAQ

**Can I use this with a sandbox?**
Yes — any org that `sf org login web` can authenticate. SDO, IDO, sandbox, dev org. Scout is built for demo orgs, not customer orgs: it deploys metadata freely and assumes nothing irreplaceable is at stake. Don't point it at production.

**Is Scout meant to replace the SE expert build?**
No. Scout-building deploys the demo your spec describes; it doesn't half-do the things it leaves to SE judgment (visual layout, complex multi-screen flows, OmniStudio, channel assignment, narrative tuning) — those go in the SE Manual Checklist instead. Scout's job is to keep you from deploying broken metadata and to handle the well-understood scaffolding, so your time goes to the parts that need you. It's the on-ramp, not the autopilot.

**What if I mess up my org?**
Every change log includes rollback commands.

**What model does it use?**
Opus for thinking (sparring, orchestration), Sonnet for doing (metadata generation, deployment). Both via LLMGW. Thinking summaries are on by default — you'll see Scout's reasoning as it works, which helps on slow operations where the output would otherwise look frozen. Configured via `CLAUDE_CODE_EXTRA_BODY` in `.claude/settings.json` (committed to the repo, no per-SE config).

**Can I use it without Agentforce?**
Yes. Agentforce is Phase 3 — if your spec doesn't include agents, that phase doesn't run.

---

## Maintainer

Sebastian Schickhoff — Munich SE. Scout is in active use across SE teams across the globe on customer demo orgs and pre-production sandboxes. Questions, feedback, or something broken: drop it in #sf-demo-scout on Slack, or open an issue on the repo.
