# What's New in Demo Scout

Check your last `update.sh` date against the headers below to see what you missed.

## 2026-04-26

- Smarter Phase 3 deployments — `/scout-building` now tries standard Agentforce actions before falling back to Apex (with evidence required in the change log), discloses the auto-created Einstein Agent User in the pre-deploy gate, and enumerates backing actions verbatim from the spec so Apex additions are visible at confirmation time
- More honest Phase 3 reporting — deployment logs now surface actions that couldn't be verified in preview (stateless-preview gaps, Knowledge grounding pending Data Library creation) as a distinct category, and the handover brief adds a 30-second citation check for Knowledge-grounded agents
- Self-healing schema validation — when a sub-agent mangles its JSON envelope but the deployment actually completed, Scout probes the org (BotDefinition for agents, SOQL for objects/fields, retrieve_metadata for flows/Apex/LWC) to confirm before forcing a retry, so cosmetic output drift no longer risks re-publishing an active agent
- Friendlier setup — `/setup-demo-scout` asks for your org alias (no more overwriting an existing `demo-org`) and checks Slack is connected, walking you through the fix if not
- Smarter sparring — `/scout-sparring` confirms the default app before auditing (no more getting stuck on Q Branch or other SE home-bases that aren't your demo surface), uses consistent customer folder names across sessions, and checks for existing matches before creating new ones
- Tidier customer folders — spec filenames now sort chronologically (date-time first), and the live audit progress log is removed automatically once the audit completes
- Deterministic seed counts — spec template requires a single integer (`5`, not `3-5`) so building doesn't have to guess
- Cleaner prompts — `/scout-building` pre-deployment check is a straight yes/no, handover brief no longer suggests pasting into ChatGPT/Gemini (the Slack canvas handles it), and the lessons-share message points at `#sf-demo-scout` instead of a personal handle
- `/sync-skills` retired — skill updates happen automatically during `update.sh` now
- Safer by default — a narrow deny list blocks destructive operations on your `orgs/` folder, `~/.sf/` auth, and force-pushes. Normal Scout flow unchanged
- Cleaner `.zshrc` — no more stale "superseded by managed block" comments piling up; existing ones get swept on next install
- Fixed: screen-flow smoke tests invoke the correct `_Test` class, audit orchestrator no longer references an undefined user Id, and post-deployment checks now cover objects that already had active flows before the deploy

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
