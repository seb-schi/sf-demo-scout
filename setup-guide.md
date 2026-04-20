# 🚀 SF Demo Scout – Setup & Usage Guide

*A Claude Code pipeline that sparrs with you about customer scenarios, then configures your Salesforce demo org to match. Less clicking through Setup. More time on what actually matters: the customer conversation.*

> ⚠️ **Data classification reminder:** Embark accounts are rated for internal data only. Do not use real customer data in this pipeline. Fake it till you make it — Scout won't tell anyone.

---

## 📦 What You'll End Up With

- ✅ Claude Code running in VS Code via AWS Bedrock
- ✅ A Salesforce demo org connected and ready to configure
- ✅ The Demo Scout pipeline installed and ready to run
- ✅ A working end-to-end flow: discovery notes → guided sparring → configured org

**Total setup time:** ~15 minutes (coffee run included ☕)

---

## 🎭 How the Pipeline Works

```
Your discovery notes + org context
            ↓
/scout-sparring  (Opus)
Guided sparring → org audit → platform research → 1 focused scenario → structured spec
            ↓
/scout-building  (Opus orchestrator → Sonnet sub-agents)
Reads spec → deploys in 3 phases (org config → flows/apex/LWC → Agentforce) → produces change log
            ↓
You
Build complex flows, arrange layouts, replace data → demo ready
```

**What Scout handles automatically:**
- Custom objects & fields
- Picklist value additions
- Record types
- Permission sets (including companion perm sets — no more invisible fields!)
- Lightning apps & tabs
- Queues with object routing
- Page layout field additions
- Data seeding (single object)
- Simple record-triggered flows (with your confirmation)
- Simple Apex (with your confirmation)
- Simple LWC components (with your confirmation)
- Agentforce agents — new or modifying existing, with post-activation smoke testing (with your confirmation)

**What you still handle manually:**
- Screen Flows, Scheduled Flows, Multi-object Flows
- Page layout visual arrangement (Scout adds fields, you arrange them)
- Reports & dashboards
- OmniStudio / managed packages
- Agentforce channel assignment & multi-agent orchestration
- Realistic demo data (Scout seeds placeholders — you make them believable)

**Five commands to remember:**

| Command | What it does |
|---------|-------------|
| `/scout-sparring` | Guided sparring + spec generation (switches to Opus automatically) |
| `/scout-building` | Org deployment from a completed spec (Opus orchestrates Sonnet sub-agents) |
| `/switch-org` | Switch between demo orgs |
| `/setup-demo-scout` | First-time org connection |
| `/sync-skills` | Pull latest community skills from upstream repos |

---

## 🐻 Before You Start

This guide picks up where the [Embark + AWS Bedrock setup guide](https://salesforce.enterprise.slack.com/docs/T01G0063H29/F0ADG6ASE81) leaves off. Before continuing, you should be able to type `claude` in macOS Terminal and get a response. If you can't, complete that guide first.

---

# Part 1: VS Code Setup

*Already have VS Code with Claude Code, Salesforce, and XML working? Skip to Part 2.*

## Step 1: Install VS Code 💻

Download and install VS Code from [code.visualstudio.com](https://code.visualstudio.com) if you don't have it. Open it once to confirm it launches, then continue.

## Step 2: Install the Required Extensions 🧩

Open VS Code. In the left sidebar, click the four-squares Extensions icon (or press ⌘+Shift+X). Search for and install these three extensions:

- **Salesforce Extension Pack** (by Salesforce) – gives you Apex, SOQL, and metadata tools directly in VS Code. Also required for the sf-flow skill's XML validation to work correctly.
- **XML** (by Red Hat) – handles metadata file validation so you don't get mysterious red squiggles on Flow XML and other metadata files.
- **Claude Code** (by Anthropic) – your AI co-pilot. When it prompts you to sign in, close the prompt. Do not sign in with your personal Claude account. Your Bedrock credentials from the Embark setup work automatically.

> 💡 The **"API Usage Billing"** label on the Claude Code welcome screen is a known cosmetic bug. Don't panic – you're not paying out of pocket. Type `/cost` in Claude Code; if it shows $0.00, you're correctly on Bedrock.

## Step 3: Open the Integrated Terminal 🖥

Here's something that trips people up: Claude Code lives in two places in VS Code – the sidebar panel and the integrated terminal. **For this pipeline, you'll use the sidebar panel.** The sidebar is where the pipeline runs best – it gives you the full chat experience with tool approvals and formatted output.

Open it by clicking the Claude icon in the left sidebar, or use ⌘+Shift+P and type "Claude Code: Open Chat".

> 💡 You *can* also use the integrated terminal (⌘+J → type `claude`), but the sidebar panel is the recommended experience for Demo Scout.

## Step 4: Verify Claude Code Works ✅

In the Claude Code sidebar (or integrated terminal), type:

```
/cost
```

If it shows $0.00, you're on Bedrock and everything is wired up correctly. If Claude Code doesn't start at all, run `source ~/.zshrc` in a terminal first, then restart VS Code (⌘+Q and reopen).

> ⚠️ **Opus availability:** Opus is not enabled by default in all Embark accounts. `/scout-sparring` uses Opus automatically – but if your account doesn't have it provisioned, it will fall back or error. To check: run `aws bedrock list-foundation-models --region us-west-2 --profile claude | grep opus` in the terminal. The pipeline works on Sonnet too – sparring is just slightly less... opinionated.

---

# Part 2: Demo Scout Setup

*This is the good part. Three steps and you're done.*

## Step 1: Clone the Repository 📁

In a macOS Terminal window (or VS Code's integrated terminal via ⌘+J), paste this and hit Enter:

```bash
git clone https://github.com/seb-schi/sf-demo-scout ~/Projects/sf-demo-scout
```

This downloads the entire Demo Scout project to your Mac – all the config files, pipeline instructions, and hooks that make everything work. You'll see some text scroll by; that's normal. Once you see a `$` prompt again, continue.

## Step 2: Run the Install Script ⚙️

Paste this and hit Enter:

```bash
cd ~/Projects/sf-demo-scout && bash install.sh
```

This runs a setup script that checks your environment and gets everything ready. Here's what it actually does:

- **Checks Homebrew and Node.js** – installs them if missing. Node.js is required for the Salesforce CLI.
- **Checks Claude Code** – installs it if missing. Yes, Claude Code installs itself. Very meta.
- **Checks Python 3.9+** – installs it if missing. Required for the Agentforce development skills.
- **Checks the Salesforce CLI** – installs it if missing. This is what Claude Code uses to talk to your org.
- **Initialises the SFDX project structure** – sets up the folder layout Salesforce expects for metadata deployments.
- **Installs 13 community Salesforce skills** from three open-source repos:
  - 7 core skills from [Jaganpro/sf-skills](https://github.com/Jaganpro/sf-skills) (sf-flow, sf-permissions, sf-deploy, sf-apex, sf-soql, sf-data, sf-debug)
  - 3 metadata generation skills from [forcedotcom/afv-library](https://github.com/forcedotcom/afv-library) (generating-custom-field, generating-custom-object, generating-permission-set)
  - 3 Agentforce ADLC skills from [SalesforceAIResearch/agentforce-adlc](https://github.com/SalesforceAIResearch/agentforce-adlc) (developing-agentforce, testing-agentforce, observing-agentforce)

  These are knowledge packs that teach Claude Code Salesforce best practices: how to generate valid Flow XML, deploy metadata in the right order, construct permission sets correctly, and build Agentforce agents end-to-end. This is what makes Flow and Agent deployment reliable.
- **Sets shell environment variables** – including bumping the output token limit to 8,192 (prevents truncated deployments on complex scenarios), setting the right model strings for Opus and Sonnet via Bedrock, and configuring model aliases so `/model opus` and `/model sonnet` just work.
- **Makes scripts executable** – the session startup hook and skill sync engine.

The whole thing takes a minute or two. You'll see a running log. When it finishes, you'll see:

```
✅ Install complete!
```

If any skill install fails, the script will tell you which one. Skills are optional for the core pipeline – but sf-flow is required if you want Claude Code to deploy Flows, and the Agentforce ADLC skills are required for agent deployment. You can always re-sync later with `/sync-skills`.

## Step 3: Open the Project Folder in VS Code 📂

**This step matters.** Claude Code reads its instructions from whichever folder VS Code has open – so you need to point it at `sf-demo-scout`, not your home folder or Downloads or wherever.

In VS Code:

**File → Open Folder** → navigate to your home folder → open **Projects** → select **sf-demo-scout** → click **Open**.

Check the title bar at the very top of VS Code. It should say **sf-demo-scout**. If it says anything else, repeat this step.

## Step 4: Run the Org Setup Command 🐾

Open the Claude Code chat by clicking the Claude icon **in the VS Code sidebar**.

Type:

```
/setup-demo-scout
```

Then sit back. 🛋️ Claude Code takes it from here. It may ask you for confirmation every now and then; confirm any edits it requests.

**What happens during setup:**
1. **Pre-flight checks** – verifies your AWS SSO session is active
2. **Connects your demo org** – opens a browser for you to log in (use your demo org credentials, not Salesforce SSO / Okta)
3. **Shows a setup summary** with your connected org and next steps

**What you'll see at the end:**

```
✅ SF Demo Prep — Setup Complete
====================================
Project:    ~/Projects/sf-demo-scout/
Org:        demo-org (admin@yourorg.demo)

/scout-sparring  – Opus discovery sparring + spec generation
/scout-building  – Opus orchestrator for org deployment
/switch-org      – change active demo org

Ready to go! Restart VS Code (CMD+Q), then type /scout-sparring to begin.
```

> 💡 The org audit runs automatically as part of `/scout-sparring`. This ensures the audit is always fresh when you actually need it.

---

🚀 *Setup complete. Everything below is your day-to-day guide.*

---

# Part 3: Preparing a Demo (Every Session)

Always start by opening VS Code with the **sf-demo-scout** folder – not a parent folder. The title bar should say **sf-demo-scout**.

## Phase 1: Gather Your Inputs 📋

Before starting Demo Scout, make sure you have:

- **Discovery call transcript** or notes
- Any additional context: RFP docs, stakeholder map, competitive notes, etc.

Don't overthink this — Scout will ask you clarifying questions. Raw notes are fine. Polished briefs are also fine. Scout doesn't judge your note-taking style.

## Phase 2: Demo Scout Sparring 🧠

Launch Claude Code. The startup hook runs automatically and shows you a status dashboard – green checkmarks mean you're good to go. Then type:

```
/scout-sparring
```

Scout will check that Opus is the active model and prompt you to switch if needed.

> 💡 **Starting up `/scout-sparring` may take some time.** This is normal! Scout loads context, checks your org connection, and prepares the sparring session. It should be ready after about 1–2 minutes at most.

### Stage 1 – Org Connection Check

Scout verifies it can talk to your org via MCP. If something's off, it'll tell you before wasting your time.

### Stage 2 – Org Audit

Scout runs a detailed audit of your connected demo org using **3 parallel sub-agents** (standard objects, apps/flows/agents, custom objects). This creates a baseline to plan and deploy against. The audit is saved to `orgs/[alias]-[customer]/` and reused by `/scout-building` later.

> ⚠️ **MCP connectivity when switching orgs:** Due to limitations with VS Code and MCP servers, you must **completely restart VS Code** (⌘+Q) when switching to a new demo org for the audit (and subsequent deployment) to work correctly.
>
> The MCP server starts up when you launch VS Code using the credentials of the last demo org used. Therefore, when you switch orgs, the MCP server remains connected to the previous org until you restart VS Code (`/switch-org` will detect this and notify you).

### Stage 3 – Discovery Analysis

Paste your discovery transcript and any supporting notes. Scout reads the org audit, analyses everything, and asks up to 5 targeted clarifying questions. Answer them honestly – this shapes the whole scenario.

### Stage 4 – Platform & Data Model Research

Scout consults the **Salesforce Docs MCP** to research platform capabilities relevant to your scenario — checking release-gated features, industry cloud data models, and object restrictions. This happens automatically before scenario proposal, so the spec is grounded in what the platform actually supports.

### Stage 5 – Scenario Definition

Scout proposes exactly **1 scenario** and asks two mandatory challenge questions:

- *"If you had half the prep time, what would you cut from this scenario?"*
- *"Does this scenario address what the customer actually said matters, or what we think should matter?"*

Take these seriously. Scout will push back if you agree without engaging. It can also query the org live via MCP during this stage to verify metadata exists before putting it in the spec.

### Stage 6 – Spec Generation

Scout generates the full spec with two parts:

- **Claude Code Instructions** – the automated configuration work
- **SE Manual Checklist** – complex flows, layout, data, channel assignment, anything requiring UI interaction

The spec is saved automatically to `orgs/[alias]-[customer]/demo-spec-[CUSTOMER]-[topic]-[DATE]-[HHmm].md`. Scout will tell you the filename and prompt you to review before executing.

> ⚠️ If Scout marks anything **[UNVERIFIED]**, check it yourself before proceeding. Unverified capabilities must not appear in Claude Code Instructions.

## Phase 3: Claude Code Deployment 🔧

Once you've reviewed the spec, **open a fresh Claude Code window** (this keeps the sparring context separate — trust us, it matters). Then type:

```
/scout-building
```

Scout will check the active model and prompt you to switch to Opus if needed. Yes, Opus — scout-building is now an **Opus orchestrator** that spawns Sonnet sub-agents for the heavy lifting. Best of both worlds: Opus judgment + Sonnet speed.

**What happens:**
1. Confirms which org is active and asks for your go-ahead
2. Loads the spec (if multiple exist, it'll ask which one)
3. Cross-checks the spec against the org audit and flags any conflicts
4. Asks for explicit confirmation before touching anything

**Then it deploys in three phases:**

| Phase | What | Confirmation needed? |
|-------|------|---------------------|
| **Phase 1: Org Config** | Objects, fields, picklists, queues, record types, permission sets, layouts, tabs, apps, data | No — runs autonomously |
| **Phase 2: Flows/Apex/LWC** | Record-triggered flows, Apex classes/triggers, LWC components | Yes — one-time confirmation |
| **Phase 3: Agentforce** | Agent topics, actions, backing Apex, publish, activate, smoke test | Yes — one-time confirmation |

**Scout will:**
- ✅ Explain each operation before doing it
- ✅ Retrieve current org state via MCP before writing anything
- ✅ Deploy in small increments and confirm success after each step
- ✅ Deploy a companion permission set automatically — so all fields, tabs, and apps are actually visible
- ✅ Deploy Flows as Draft first, then activate after confirmation
- ✅ Run Agentforce smoke tests after agent activation
- ✅ Save a change log to `orgs/[alias]-[customer]/changes-[DATE]-[HHmm]-[CUSTOMER]-[topic].md`

**If something goes wrong:**
- Scout explains errors in plain English and attempts a fix
- It consults Salesforce documentation on unfamiliar errors before retrying
- If it fails twice on the same item, it adds it to the manual checklist and moves on
- Type **stop** at any time to halt immediately
- If context gets long, Scout saves progress to a partial change log and asks you to start a fresh session

## Phase 4: SE Manual Work 🛠

Open the change log from `orgs/[alias]-[customer]/` in VS Code. Work through **"SE Must Do Next"** in order:

1. **Build complex flows** – screen flows, scheduled flows, and multi-object flows are in the SE Manual Checklist. Do these first – they take the longest and any bug here breaks the demo narrative.
2. **Arrange page layouts** – Open App Builder. Scout adds fields but doesn't arrange them visually. Make them pretty.
3. **Complete Agentforce manual steps** – Channel assignment, production-scale testing, and any multi-agent orchestration are always manual.
4. **Replace seed data** – Scout seeds placeholder records. Replace with realistic values for your customer. Nobody's impressed by "Test Account 1."
5. **Test end-to-end** – Walk the complete demo narrative from start to finish. Test each flow individually first.

> ⚠️ If **Apex** was deployed and something isn't working, the change log includes delete commands. Run them to roll back, then build the logic as a Flow instead.

## Phase 5: Iterate If Needed 🔄

After testing, if changes are needed:

1. Note what needs to change.
2. Start `/scout-sparring` and paste the change log with your notes.
3. Scout recognises this is an iteration — it runs a lighter discovery focused on the changes, not a full re-audit.
4. Scout produces a refined spec – hand only the changed items to `/scout-building`.

For small tweaks, skip sparring and talk directly to Claude Code – e.g.:

```
Add picklist value "Completed" to Status__c on Patient_Visit__c
```

---

# Part 4: Switching Demo Orgs 🔄

Type `/switch-org` inside a Claude Code session. Scout lists all authenticated orgs, asks which you want, updates the config, and confirms the switch.

Scout also verifies whether the MCP server has picked up the new org. If it hasn't (which happens when you switch without restarting), you'll see a clear warning:

> ⚠️ MCP is still connected to the previous org. Restart VS Code now (⌘+Q).

**Always restart VS Code after switching orgs**, then re-run `/scout-sparring`. Scout's conflict detection depends on an accurate snapshot of the target org. The sparring session will check audit freshness and prompt you if a refresh is needed.

---

# Part 5: Updating Demo Scout 🔄

When Scout detects a newer version on GitHub during session startup, it'll let you know. To update:

```bash
bash update.sh
```

No `git pull` here — Scout uses a **nuke-and-reinstall** model. The script backs up your org data (audits, specs, change logs) and Salesforce config, deletes the installation, re-clones fresh, restores your data, and re-runs `install.sh`. Clean slate. Zero drift. ~30 seconds.

> 💡 Running from VS Code? It'll pop open Terminal.app automatically. Close VS Code while it does its thing, then reopen after.

---

# Part 6: File Reference 📁

| File | Description |
|------|-------------|
| `CLAUDE.md` | Master rules for Claude Code. Do not edit. |
| `.claude/settings.json` | Permission rules and session hooks. Do not edit. |
| `.claude/hooks/session-startup.sh` | Session health check on every launch. Do not edit. |
| `.claude/commands/scout-sparring.md` | Defines `/scout-sparring`. Do not edit. |
| `.claude/commands/scout-building.md` | Defines `/scout-building`. Do not edit. |
| `.claude/commands/switch-org.md` | Defines `/switch-org`. Do not edit. |
| `.claude/commands/setup-demo-scout.md` | Defines `/setup-demo-scout`. Do not edit. |
| `.claude/commands/sync-skills.md` | Defines `/sync-skills`. Do not edit. |
| `.claude/skills-manifest.yaml` | Which community skills to sync. Do not edit (unless adding skills). |
| `install.sh` | Full setup script. Idempotent — safe to re-run. |
| `update.sh` | Nuke-and-reinstall updater. |
| `orgs/[alias]-[customer]/audit-*.md` | Org snapshot, input for sparring. Auto-generated. |
| `orgs/[alias]-[customer]/demo-spec-*.md` | Spec from sparring, input for building. Edit only to correct verified items. |
| `orgs/[alias]-[customer]/changes-*.md` | What was built + manual checklist. Auto-generated. |

**Community skills** (installed by `install.sh`, synced by `/sync-skills`):

| Skill | Source | Purpose |
|-------|--------|---------|
| `sf-flow` | Jaganpro/sf-skills | Flow XML generation & validation |
| `sf-permissions` | Jaganpro/sf-skills | Permission set best practices |
| `sf-deploy` | Jaganpro/sf-skills | Deployment order and safety rules |
| `sf-apex` | Jaganpro/sf-skills | Apex best practices |
| `sf-soql` | Jaganpro/sf-skills | SOQL query generation |
| `sf-data` | Jaganpro/sf-skills | Data operations |
| `sf-debug` | Jaganpro/sf-skills | Debug log analysis |
| `generating-custom-field` | forcedotcom/afv-library | Custom field metadata generation |
| `generating-custom-object` | forcedotcom/afv-library | Custom object metadata generation |
| `generating-permission-set` | forcedotcom/afv-library | Permission set metadata generation |
| `developing-agentforce` | SalesforceAIResearch/agentforce-adlc | Agentforce agent development |
| `testing-agentforce` | SalesforceAIResearch/agentforce-adlc | Agentforce agent testing |
| `observing-agentforce` | SalesforceAIResearch/agentforce-adlc | Agentforce production observation |

Keep all generated files in `orgs/` – they're your audit trail and your starting point for adapting demos to similar customers.

---

# Part 7: Troubleshooting 🆘

### `sf: command` not found
Run `source ~/.zshrc` in the terminal, then try again. If that doesn't work, close and reopen VS Code.

### Claude Code hangs with no response
Your AWS SSO session expired. Open a new terminal tab (⌘+T) and run `aws sso login --profile claude`. Then relaunch Claude Code.

### `/scout-sparring` gives a model error
Your Embark account doesn't have Opus enabled. Check with your admin or try running `/scout-sparring` anyway – if it falls back to Sonnet the pipeline still works, sparring is just slightly less rigorous. To confirm Opus availability: `aws bedrock list-foundation-models --region us-west-2 --profile claude | grep opus`.

### Claude Code Welcome screen still shows an old model name
Run `/cost` – if it shows $0.00 you're on Bedrock and the label is cosmetic. If you're actually being billed, run `source ~/.zshrc` and relaunch.

### Fields, tabs, or the app aren't visible after deployment
The companion permission set didn't deploy or assign. Tell Claude Code:

```
"Deploy a companion permission set for everything you just created and assign it to me."
```

### MCP tools not working / org audit is empty
Check that `.mcp.json` is in the project root (not a subfolder). Restart VS Code after any changes. If the file is missing, run `/setup-demo-scout` again — it generates the MCP config.

### Claude Code isn't reading CLAUDE.md
Check the VS Code title bar – it must say **sf-demo-scout**. Claude Code reads CLAUDE.md from whichever folder VS Code has open. If it says anything else: File → Open Folder → sf-demo-scout.

### SSO session expired mid-session
Open a new terminal tab (⌘+T) and run `aws sso login --profile claude`. Return to your Claude Code session and retry.

### Apex deployed but something broke
The change log includes delete commands for any Apex. Run them to roll back, then build the logic as a Flow instead.

### A Flow deployed but it's not working correctly
Flow XML deployment is gated behind the sf-flow skill's validation and always deploys as Draft first. If the flow activated but behaves incorrectly, deactivate it in Setup → Flows and rebuild it manually using the instructions in the SE Manual Checklist section of the change log.

### A skill failed to install
Run `/sync-skills` — it'll retry all missing or outdated skills. If a specific skill keeps failing, the sync report will tell you which one and why.

If sf-flow isn't installed, Claude Code won't attempt Flow deployments – it will fall back to adding them to the SE Manual Checklist instead. Same principle for Agentforce ADLC skills.

### I want to add a new community skill
Edit `.claude/skills-manifest.yaml` — add the repo, path, and skill name — then run `/sync-skills`. That's it.

---

> 🐾 *SF Demo Scout was built by @Sebastian Schickhoff, your friendly Munich neighbourhood HLS SE.*
> *Questions? Ideas? Wild demo scenarios? You know where to find me.*
