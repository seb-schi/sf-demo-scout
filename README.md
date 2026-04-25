# SF Demo Scout 🦮

**Your AI-powered demo prep sidekick** – because nobody became an SE to manually configure permission sets.

SF Demo Scout is a Claude Code pipeline that *spars* with you about customer scenarios, then configures your Salesforce demo org to match. You bring the context, Scout brings the questions – and then handles the clicks. Think of it as a very eager junior admin who never fat-fingers a field API name.

---

## What You Need

| Ingredient | Why |
|------------|-----|
| macOS | Apple Silicon or Intel. Sorry, Windows friends. 🍎 |
| Claude Code via LLMGW | Opus thinks. Sonnet builds. Install Claude Code first using the **Installing Claude Code for Solutions** canvas (one command, one Google sign-in). |
| A Salesforce demo org | SDO, IDO, personal dev org – we're not picky. The messier, the more fun. |

---

## Install (One Time, We Promise)

```bash
git clone https://github.com/seb-schi/sf-demo-scout ~/claude-projects/sf-demo-scout
cd ~/claude-projects/sf-demo-scout && bash install.sh
```

Go grab a coffee. ☕ The script installs Homebrew, Node.js, Python, Salesforce CLI, sets up the SFDX project, registers the Slack MCP server, and pulls 16 community skills from three open-source repos. It's idempotent – safe to re-run if something went sideways the first time.

Then: **VS Code → Open Folder → `~/claude-projects/sf-demo-scout` → Open Terminal → `claude` → `/setup-demo-scout`**

That's it. You're in.

## Updating

```bash
bash update.sh
```

No `git pull` drama here. Scout nukes the install, re-clones fresh, and restores your org data (audits, specs, change logs). Clean slate. Zero drift. ~30 seconds. Like a metadata refresh, but for your tooling.

> 💡 Running from VS Code? It'll pop open Terminal.app for you. Close VS Code, let it cook, reopen after.

---

## How It Works

Two commands. That's the whole workflow.

| Step | Command | What happens |
|------|---------|--------------|
| **Spar** | `/scout-sparring` | You share customer context. Opus audits the org, researches platform capabilities, asks smart questions, and produces a structured demo spec. |
| **Build** | `/scout-building` | Opus reads the spec, orchestrates Sonnet sub-agents across three phases (org config → flows/apex/LWC → Agentforce), and writes a change log. |

Always spar first. Always build second. It's like discovery → demo, but for configuring the demo itself. Very meta. 🤯

### Supporting Cast

| Command | When to use it |
|---------|---------------|
| `/setup-demo-scout` | First time connecting an org |
| `/switch-org` | Switching to a different demo org |
| `/sync-skills` | Pulling latest community skills (install does this too) |

---

## What Scout Can Do

### Fully autonomous (no approvals needed)
Custom objects, fields, picklist values, record types, queues, permission sets, page layout field additions, Lightning apps & tabs, and demo data seeding. Scout does these in its sleep. If it had sleep.

### One-time SE confirmation per category
Record-triggered Flows, simple screen flows (≤3 linear screens, up to 5 with justification), simple Apex, simple LWC, and Agentforce agents (with smoke testing!). Confirm once, Scout handles the rest.

### Still on your plate (for now 😉)
Complex screen flows (branching, subflows, File Upload, Data Table, custom LWC screen components), scheduled flows, multi-object flows, complex Apex/LWC, multi-agent orchestration, page layout visual arrangement, reports, dashboards, OmniStudio. Scout adds these to a Manual Checklist so you don't forget.

---

## What You Get Back

After every run, Scout saves artifacts in `orgs/[alias]-[customer]/`:

| File | What's inside |
|------|---------------|
| `audit-*.md` | Org snapshot – objects, flows, agents, layouts, gaps |
| `demo-spec-*.md` | The deployment spec (your source of truth) |
| `changes-*.md` | What got deployed, what to verify, what's on you |

These survive updates. They're *your* data – Scout just writes them.

---

## The Salesforce Connection

Scout talks to your org through three MCP servers:

🔧 **Salesforce DX MCP** – metadata deployment, SOQL queries, permission sets, code analysis, LWC scaffolding. The workhorse.

📚 **Salesforce Docs MCP** – semantic search across official Salesforce docs. Scout checks release notes and dev guides so you don't have to. Optional – degrades gracefully if unavailable.

💬 **Slack MCP** – optional. Lets Scout skim a setup canvas or channel you name during sparring, and write the post-deployment handover brief to a canvas in your personal Slack. Registered user-scope by `install.sh`; after the first install, run `/mcp` in Claude Code, select `slack`, and complete the OAuth flow in your browser. Skip OAuth and Scout silently carries on without it.

Falls back to `sf` CLI when MCP acts up. Belt and suspenders.

---

## Skills & Smarts

Scout's intelligence lives in **skills** – domain-specific instruction sets loaded on demand. They're why Scout knows Flow XML needs `<start><filters>` and not `processMetadataValues`, why it never sets `TabVisibility: DefaultOn`, and why it checks `EntityDefinition` flags before suggesting a trigger.

**Ships with the repo** (3 demo skills):
- `demo-deployment-rules` – the rulebook for deploying Flows, Apex, LWC, Agentforce
- `demo-org-audit` – how to audit an org properly
- `demo-docs-consultation` – when to look things up vs. wing it

**Downloaded at install** (16 community skills):
- 10 from [Jaganpro/sf-skills](https://github.com/Jaganpro/sf-skills) – SOQL, Apex, Flows, Permissions, Deploy, Data, Debug, LWC, Testing, Flex Estimator
- 3 from [forcedotcom/afv-library](https://github.com/forcedotcom/afv-library) – Custom Fields, Objects, Permission Sets
- 3 from [SalesforceAIResearch/agentforce-adlc](https://github.com/SalesforceAIResearch/agentforce-adlc) – Agentforce dev, test, observe

Manage skills declaratively: edit `.claude/skills-manifest.yaml` → run `/sync-skills`. Done.

---

## What's In The Box

```
CLAUDE.md                       ← Root instructions (under 100 lines – we counted)
install.sh                      ← Full setup (idempotent, run it twice if you want)
update.sh                       ← Nuke-and-reinstall updater
.claude/
  commands/                     ← 5 slash commands (the ones you actually type)
  skills/                       ← 3 demo skills (+ 16 community skills after install)
  prompts/                      ← 12 sub-agent templates, lessons & reference docs
  scripts/                      ← sync-skills.sh
  hooks/                        ← session-startup.sh (org check on every launch)
  settings.json                 ← Permissions & hooks config
  skills-manifest.yaml          ← Which community skills to sync from where
```

**Generated at runtime** (gitignored, yours to keep):
```
orgs/                           ← Your audits, specs, and change logs
.sf/                            ← Salesforce CLI local config
force-app/                      ← SFDX project (for metadata operations)
.mcp.json                       ← MCP server config (generated by setup)
```

---

## FAQ (Frequently Anticipated Questions)

**Q: Can I use this with a sandbox?**
A: Yes! Any org that `sf org login web` can authenticate. SDO, IDO, sandbox, dev org – Scout doesn't judge. **But:** this is built for demo orgs, not customer orgs. Scout deploys metadata freely and assumes it won't break anything irreplaceable. Don't point it at production. Yet. 😏

**Q: What if I mess up my org?**
A: Every change log includes rollback commands. Scout's like a responsible designated driver – it notes the way back.

**Q: What model does it use?**
A: Opus for thinking (sparring, orchestration), Sonnet for doing (metadata generation, deployment). Both via LLMGW.

**Q: Can I use it without Agentforce?**
A: Absolutely. Agentforce is Phase 3 – if your spec doesn't include agents, that phase simply doesn't run.

---

## Questions?

Reach out to @Sebastian Schickhoff – preferably with a wild demo idea and a freshly-provisioned org. 🚀
