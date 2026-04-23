# What's New in Demo Scout

Check your last `update.sh` date against the headers below to see what you missed.

## 2026-04-23

- **Skill adoption wave** — three new community skills adopted: `sf-lwc` (PICKLES methodology + 165-point scoring, required before any LWC component generation), `sf-testing` (agentic Apex test-fix loops, up to 3 automated fix iterations before skipping), `sf-flex-estimator` (Flex Credit cost projections when scenario includes Agentforce or Data Cloud). Run `/sync-skills` to pull the new SKILL.md files.
- **LLMGW Migration** — Scout now uses LLMGW (the company-wide Claude gateway) instead of Embark/AWS SSO. No more `aws sso login` on session start. Install script no longer installs Claude Code itself — use the official Solutions installer first. Default repo location changed from `~/Projects` to `~/claude-projects` to match official install guide.
- Command cleanup — `/scout-building` Phase 2 / Phase 3 SE gates no longer fire macOS notifications during active deployments — the blockquote prompt in chat is sufficient, matching the pattern already applied to model gates.

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
