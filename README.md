# SF Demo Scout

A plugin for Salesforce Solution Engineers that runs in Claude Code, Codex or
Cursor; one of them is enough. Run `/scout` and say what you need: Scout spars
with you on the demo story, builds it in your demo org, checks every piece there,
and preps you for delivery, all in one session. Scout 2.0 is built for Opus 5.5
and later; on Codex and Cursor, pick the strongest model you have.

## Why Scout exists

The SE role is shifting. We're increasingly asked to do post-sales
activation work — configuring real Salesforce orgs through CLI-native
tools that didn't exist 18 months ago — and the gap between what the
platform now expects and what most of us trained for is real. The tooling
landscape doesn't help: a dozen MCP servers, community skill repos, half a
dozen ways to stand up an AI coding tool. The cost of starting is high, and the
cost of starting wrong is higher.

Scout is the on-ramp. Setup stands up everything you need, and from there
`/scout` does four things:

1. **Works in the org you name.** It looks at exactly what your request
   touches (a full audit when you ask), so you build into reality instead of
   around it. If the org isn't connected yet, it opens Salesforce's login page
   for you. It never changes your existing logins, and changes your default org
   only on your yes, when Salesforce's deploy check needs one.
2. **Spars with you on the story.** From a one-liner or your discovery notes
   to a proposal with a clear "wow" moment, and pushback on anything that
   doesn't earn its place, because the real work is deciding what to leave out.
3. **Builds and checks the configuration.** In dependency order, one write at
   a time. It reads every item back in the org before calling it done, logs
   every change with rollback evidence, and asks before deleting or changing
   anything sensitive.
4. **Preps you for delivery.** The click path through your story, and a
   read-only readiness check before you present.

Scout works because it drives Salesforce's [official
skills](https://github.com/forcedotcom/sf-skills), straight from Salesforce's own
GitHub repository and kept current, with an orchestration layer for SEs on top. Rather than improvising Apex, Flow
XML, or agent metadata from training data, it uses the same authoring
rules and validation patterns the platform team publishes, the day they
publish them. You're not vibe-coding the platform layer — you're driving it.

## How it works

One session from idea to a checked demo. The 5.5 models carry the whole job;
Scout supplies the Salesforce playbook (Salesforce's official skills, deployment
rules, Salesforce Docs) and the SE rigour (org binding, confirmations, read-back,
per-customer history, and a log of what was done, with which skill, and why).

```mermaid
flowchart TD
    SE(["👤 Solution Engineer"])

    subgraph SCOUT["/scout · one session"]
        B["`Bind to your org
_and read its history_`"]
        S["`Spar on the story
**— and what to leave out**`"]
        Y{"`your yes`"}
        W["`Build in dependency order
_one write at a time_`"]
        R["`Read back every item
in the org`"]
        B --> S --> Y --> W --> R
    end

    OUT["`✅ Handover: verified · needs a look · left
+ change log + demo map`"]
    PREP["`🎬 Prep before the meeting
readiness check + click path`"]

    SE --> SCOUT
    R --> OUT --> PREP

    classDef scout fill:#e8eefc,stroke:#3b5ba5,color:#1a2a4a;
    class SCOUT scout;
```

## What Scout builds — and what it leaves to you

Building used to be the hard part. It isn't anymore. Scout will attempt
anything the Metadata API can express — objects, flows, Apex, agents — and
loop on its own until it's deployed. Today's models configure Salesforce more
reliably than most of us do by hand.

So the scarce discipline has moved. When everything is buildable, the
question that decides whether a demo lands is no longer *can we build
this* — it's *what's worth building, and what to leave out*. That judgment
doesn't automate, and it's the whole reason `/scout` spars first: the point
of sparring is to decide what **not** to build before a line is deployed.

Building, by contrast, is deliberately low-friction. Once you've approved
the proposal, Scout goes as far as the platform allows without stopping to
re-litigate the plan — the second-guessing already happened, with you, in
sparring. The one thing it never does is *pretend*: where it can check its
own work (a deploy read-back, a passing test, a fired agent action) it
reports a verified green; where it can't (a rendered layout, a visual UX)
it still builds and deploys, then hands you a short QA checklist rather
than claim a green it couldn't earn. And it never touches existing
metadata, or anything destructive, without your say-so.

| Scout builds and verifies | Scout builds it — you stay in the loop |
|---|---|
| Custom objects, fields, record types | Complex / multi-component LWC (deployed; visual QA) |
| Permission sets (incl. companion sets) | Existing Lightning-page field-section edits, page-layout arrangements, dashboards (deployed; visual QA) |
| Lightning apps, tabs, queues, reports | Screen flows using non-whitelisted components (deployed Draft; QA, then activate) |
| Flows — record-triggered, screen (branching, cross-screen), scheduled | Orchestration flows (deployed; you validate the lifecycle) |
| Apex — multi-class, cross-object (bounded test-fix loop) | Multi-agent wiring, channel assignment, OmniStudio (UI-only — Scout builds the metadata around them) |
| Agentforce agents (deploy, activate, smoke-test) | Anything destructive or on existing metadata — never without confirmation |

For Lightning Record Pages, additions to existing Dynamic Forms field sections
remain supported, and Scout still deploys underlying artifacts such as LWCs,
Paths, CompactLayouts, and ListViews. A full new `RecordPage` is composed
manually by the SE in App Builder, where the complete page can be arranged and
previewed safely.

## Install

### Claude Code

Inside Claude Code, run these four commands in order:

```
/plugin marketplace add https://github.com/seb-schi/sf-demo-scout.git
/plugin install sf-demo-scout@scout
/reload-plugins
/scout-setup
```

When prompted on the install step, select `Install for you (user scope)`.

### Codex (CLI and desktop app)

```bash
codex plugin marketplace add seb-schi/sf-demo-scout
```

```bash
codex plugin add sf-demo-scout@scout
```

Then restart Codex and run `$sf-demo-scout:scout-setup`; afterwards, start a demo
with `$sf-demo-scout:scout`, where these instructions say `/scout`. Codex's IDE
extension doesn't load plugins; use the CLI or the desktop app.

### Cursor

Managed Cursor installs often refuse third-party plugins, so Scout installs from
a folder of your choice. On macOS or Linux:

```bash
git clone https://github.com/seb-schi/sf-demo-scout.git ~/sf-demo-scout
```

```bash
python3 ~/sf-demo-scout/scripts/scout_install.py skills --host cursor --yes
```

On Windows, in PowerShell, clone to `$HOME\sf-demo-scout` the same way and run
`py -3 $HOME\sf-demo-scout\scripts\scout_install.py skills --host cursor --yes`.
Then open a new Cursor chat and run `/scout-setup`. Where your organisation's
Cursor allows third-party plugins, it can also add this repository as a plugin
marketplace instead.

### What setup does

`/scout-setup` handles the prerequisites: Node 22.20 or later, Python, the
Salesforce CLI and the SFDX scaffold (on macOS it installs them with Homebrew;
elsewhere it names the install commands). It sets up Salesforce's official skills
from Salesforce's own GitHub repository: on Claude Code and Codex as Salesforce's
plugins, kept current by auto-update, and on Cursor as a clone it reads in place.
It offers the public
[Agentforce Labs Salesforce Docs MCP](https://labs.agentforce.com/docs/salesforce-docs-mcp)
for docs grounding, and adds it only on your yes. It doesn't edit your shell
files or other tools' settings.

After setup, kick off your first demo with `/scout`.

**Demo orgs only.** Scout writes only to demo orgs: trials (an org with an expiry
date), sandboxes, scratch orgs and Developer Editions. In a production org, or one
it can't classify, Scout inspects, plans and preps, but never writes.

**Connected tools.** Scout can use whatever your coding tool has connected, such
as Slack or Google Drive. Check what's connected in your environment: when you
ask Scout to look something up, it may read from those tools. Scout itself
installs no connectors and never searches them unless you ask.

### Uninstall

To remove Scout's own files, ask Scout to uninstall itself before you remove the
plugin. It runs `scripts/scout_uninstall.py`, shows what it would remove, and
removes only Scout's configuration and cache on your yes. Your Scout workspace and
its org histories go only if you ask for that too (`--workspace`). Then remove the
plugin with `/plugin uninstall sf-demo-scout@scout` on Claude Code, or
`codex plugin remove sf-demo-scout@scout` on Codex. On Cursor, run
`scripts/scout_install.py uninstall --host cursor --yes` and delete the folder.

## The commands

| Command | What it does |
|---|---|
| `/scout` | Scout 2.0: spar, build, fix or prep a demo in one session, in the org you name. Built for Opus 5.5 and later. |
| `/scout-setup` | Setup, updates, and repairs. Scout also runs it itself when it finds its setup broken. |

`/scout-sparring` and `/scout-building` are the classic command names. They now open `/scout`; `/scout-building` hands it your spec as the brief.

## Building one demo org together

Tell Scout you're working with colleagues on an org ("/scout session: start a team on acme-sdo with Bob"). Each of
you builds in your own sandbox; the captain delivers the team's work into its common org.

- **Scout's own lane:** a private GitHub repository, a team board, and a guard in each teammate's Salesforce CLI.
- **On Salesforce's Lifecycle Center (beta):** the team's work items, reviews and promotions are Salesforce's own,
  and teammates can use Cursor, Agentforce Vibes or Scout. Scout offers Salesforce's Lifecycle Center plugin
  (`dx-devops`) the first time a team needs it. Scout checks each delivery before it merges, runs the
  stage's tests, and reads the common org back after it. The beta's known limits:
  - Lifecycle Center can't promote a new component whose files reach the work item in separate commits. Commit a new
    component's files together; when that didn't happen, Scout offers a full promotion, which deploys everything on
    `main` after checking it all against the common org.
  - DevOps Testing doesn't run on promotions from the command line, so Scout runs the stage's tests itself before
    the merge. Some orgs, trial demo orgs among them, run no tests during a deploy. There Scout asks first, then
    runs the stage's tests right after the promotion, and says verified only if they pass.
  - Required reviews on a protected `main` aren't tested yet, and Back Sync stays a manual step.

## Updates

- **Claude Code:** automatic. Setup turns on auto-update for Scout's marketplace,
  unless you've set it yourself. To update now, run `claude plugin marketplace update
  scout` and then `claude plugin update sf-demo-scout@scout` in a terminal, then
  `/reload-plugins` in Claude Code.
- **Codex:** Codex updates Scout when it starts, so restart it, then open a new
  chat. To update now: `codex plugin marketplace upgrade scout`.
- **Cursor:** Scout tells you when a new release is out, and updates its folder with
  `git pull` on your yes. Start a new chat afterwards.

**Staying on a release.** Each release has a tag, such as `scout-2.4.0`.
- **Claude Code:** `/plugin marketplace remove scout` (this removes Scout too; your
  workspace and its histories stay), then `/plugin marketplace add
  seb-schi/sf-demo-scout#scout-2.4.0` and `/plugin install sf-demo-scout@scout`.
- **Codex:** `codex plugin marketplace remove scout`, then add it again with
  `--ref scout-2.4.0`, and run `codex plugin add sf-demo-scout@scout`.
- **Cursor:** `git -C ~/sf-demo-scout checkout scout-2.4.0`.

To follow the latest again, do the same without the tag, or check out `main`.

**Going back to 2.3.2.** Version 2.3.2's own tag still installs from `main`, so use
the recovery branch made for this: on Claude Code, the steps above with
`#recovery-2.3.2` instead of the tag.

## Where Scout runs

| | macOS | Windows 11 | Linux |
|---|---|---|---|
| Claude Code (CLI, desktop app, VS Code) | yes | setup, builds, repairs and prep, once tested | best effort |
| Codex (CLI, desktop app) | yes | setup, builds, repairs and prep, once tested | best effort |
| Cursor (IDE, `cursor-agent`) | yes | setup, builds, repairs and prep, once tested | best effort |

Building one demo org together (team mode and Lifecycle Center mode) runs on macOS
for now. On Windows, Scout needs Git for Windows (its Git Bash), Python 3.9 or
later, Node 22.20 or later, the Salesforce CLI and `jq`; Salesforce's official
skills use the last two. A Windows host is marked tested once it has passed the
release's Windows checklist.

## Development checks

Run the [offline regression suite](tests/README.md) from a clean checkout with
`PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -v`.
The fixtures use temporary files and synthetic CLI responses; they do not test
a live Salesforce org or install CLI updates.

## Archive

The full clone-install history is preserved at branch
`archive/clone-install-final` and tag `v-clone-install-final`.

## Questions and problems

Open an issue on this repository. If your GitHub account can't open issues here,
for example a managed enterprise account, contact the maintainer through the
channel your organisation used to share Scout.

---

Built by **Sebastian Schickhoff** — Lead Solution Engineer, Applied AI &
Regulated Industries · [sebastian-schickhoff.com](https://sebastian-schickhoff.com)
