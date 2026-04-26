# What's New in Demo Scout

Check your last `update.sh` date against the headers below to see what you missed.

## 2026-04-26

- `/setup-demo-scout` now prompts for an alias instead of defaulting to `demo-org` — no more silent overwrites when you already have a `demo-org` alias
- `/scout-sparring` now follows a deterministic rule for customer folder names — same customer lands in the same folder every time, even with punctuation, diacritics, or ampersands in the name
- `/scout-sparring` checks for existing folders before creating a new one — if Scout finds a similar match, it asks before splitting the customer across two folders
- `/scout-building` pre-deployment check is cleaner — `yes/no` instead of an undefined third "skip flagged" option that did different things in different sessions
- `/sync-skills` retired — skill updates now happen automatically as part of `update.sh`, no separate command to remember
- Safer by default — a narrow deny list now blocks Claude from recursively deleting your `orgs/` folder, nuking `~/.sf/` auth, force-pushing, or issuing destructive `sf org` operations. Normal Scout flow is unchanged
- Internal: launch-followup backlog captured for post-launch week 1 (sub-agent timeout path, orchestrator-level Companion PS check, audit-mismatch resilience)

## 2026-04-25

- README caught up for the US launch — skill count corrected (16, not 13), sf-lwc/sf-testing/sf-flex-estimator listed, Slack MCP documented with first-session OAuth step, simple screen flows moved from "manual" to "confirm-once" to match actual behavior

## 2026-04-24

- Slack integration simplified — no more sources files to curate. During sparring Scout asks inline which canvases (and optionally one channel) to reference; handover canvas is a y/n prompt after deploy
- Slack integration drift cleanup — CLAUDE.md Slack section now matches the current integration (inline Stage 4 ask + handover canvas), broken canvas-search tool name fixed, dead tool grants pruned from sparring permissions
- Opus sessions no longer truncate on long reasoning — thinking budget raised
- `.zshrc` config managed by Scout — model IDs and token limits update automatically on install/update; conflicting old lines get commented out with a dated note
- Cleaner install output — fixed a section-numbering gap, removed a no-op shell-reload step

## 2026-04-23

- Leaner prompts — Scout's audit sub-agents share a single rule block instead of three copies, and the Phase 2 template drops over-eager "CRITICAL" warnings so the one that matters stands out
- Leaner sparring and deployment commands — Scout loads less into memory at the start of a session, leaving more room for the actual demo work
- Update notices now surface inside `/scout-sparring` when you start a session — harder to miss, easier to act on
- Screen flows now autonomous — Scout can build simple screen flows end-to-end (up to 3 screens by default, 5 if you justify during sparring). Scout also writes a quick test and runs it automatically; you just walk through once in the UI to sanity-check the look and feel
- LWC, Apex testing, and Flex Credit estimation added — Scout now follows Salesforce's PICKLES guidelines when building Lightning Web Components, auto-fixes failing Apex tests up to 3 times before giving up, and gives you a public-price cost estimate when your scenario uses Agentforce or Data Cloud
- Scout now uses LLMGW (the company-wide Claude gateway) — no more `aws sso login` at session start. If you're setting up fresh, use the official Solutions installer first. Default repo location moved to `~/claude-projects`
- Smarter Phase 2 deployments — Scout no longer sends Flow, Apex, or LWC rules to the sub-agent when your spec doesn't need them
- Fixed: audit page-layout query was silently returning no results for custom objects in three places — layouts are now detected correctly
- Fixed: Agentforce rollback command in the change log template had the wrong metadata type
- Minor cleanup: `/scout-building` no longer fires macOS notifications during active deployments (the chat prompt is enough)

## 2026-04-22

- Faster deployments — Scout's deployment command now loads end-of-flow procedures (handover brief, post-deployment checks) on demand instead of at session start
- Demo Handover Brief — after deployment, Scout summarizes what was built in business terms, outlines a demo story, lists your to-dos, and shows where your files live (with a Finder shortcut)
- Smarter deployments for simple specs — Scout no longer sends irrelevant rules to sub-agents (queues, layouts, permission sets) when the spec doesn't need them
- `/switch-org` now offers to connect a new org directly — no need to guess
- Sparring responses are more concise — same depth of judgment, fewer words
- Fixed: deployment verification no longer fails on a non-existent FlowDefinitionView field

## 2026-04-21

- Reuse-org mode — reuse an org from a prior customer without wasted research steps
- Audit is cheaper on large orgs (skips layout retrieval for non-starred layouts, tighter object queries)
- Fixed: flow audit no longer wastes a query on an unsupported GROUP BY

## 2026-04-20

- Scout now warns you about platform restrictions before you commit to a scenario
- Validates that your org's data actually supports the demo story before writing a spec
- Gently nudges you to trim your lessons file when it gets long
- Update mechanism is now a simple `update.sh` script — just run it and you're current
- Your personal lessons now survive updates (no more losing hard-won wisdom)
- Fixed: MCP tools actually load on first launch now (no more mysterious silence)
- Fixed: stale CLI versions no longer break MCP connections

## 2026-04-19

- Audit handles large orgs without choking (split into parallel workers)
- Scout can now deploy queues and picklist values without asking — fewer interruptions
- Agentforce agents get a smoke test after deployment (talks to itself to verify)
- Auto-detects industry clouds (Health Cloud, FSC, etc.) during audit
- Platform research happens before scenario proposal — no more "great idea, impossible org"
- Fixed: session startup no longer fails to detect your org on certain systems
- Fixed: audit no longer silently misses flows or agents

## 2026-04-18

- Salesforce Docs integration — Scout reads official docs to verify features and diagnose errors
- New orchestrator architecture — smarter planning, faster execution
- Spec and change log now cite which docs were consulted

## 2026-04-17

- `/sync-skills` command — one command to pull the latest skill updates
- Fixed: switching orgs now sticks (MCP was reading the wrong org)

## 2026-04-16

- Better metadata generation (fields, objects, permission sets) via specialist skills
- Deployment errors now get structured recovery instead of cryptic retries

## 2026-04-15

- `install.sh` now installs Claude Code itself — truly one-script setup
- Cleaner skill naming (no more ugly underscores)

## 2026-04-14

- No more manual org config — Scout reads your active org automatically
- Agentforce is a first-class citizen in sparring (not an afterthought)
- Iteration mode — make targeted changes to existing demos without full rediscovery
- Faster session startup (heavy files load only when needed)
- Fixed: various stale references and hardcoded values cleaned out
- Removed: manual org editing, broken web tools
