# What's New in Demo Scout

Check your last `update.sh` date against the headers below to see what you missed.

## 2026-04-29

- **Scout now thinks visibly.** Opus 4.7 hides its reasoning by default, which made slow operations feel like Scout had frozen — a first-impression killer. Adaptive thinking summaries now ship via the repo's `.claude/settings.json`, so every SE who clones gets visible thinking on Opus and Sonnet runs without touching their personal config.
- **Pipeline updates post to `#sf-demo-scout` automatically.** After every `/project-sparring` session, Scout drafts a short release note for the channel plus a CHANGELOG mirror for the pinned canvas — you review both in one message, approve, Scout posts. Degrades cleanly if Slack MCP isn't authenticated.
- **Fewer Slack permission prompts.** The wildcard in `.claude/settings.json` finally matches the way it was always supposed to (`mcp__slack__*`, not `mcp__slack__slack_*`). Turns out the `*` needs to eat the whole tool-name segment, not just the tail.

## 2026-04-28

- **Sales, Lead, Support, and Solution Processes now deploy autonomously.** The Metadata API exposes all four as one type (`BusinessProcess`) — the four labels you see in Setup are UI groupings, not separate types. Scout now ships the XML and binds it to the right Record Type for any of the four objects.
- **Paths now autonomous.** Scout deploys PathAssistant metadata — active flag, driving picklist, key fields plus rich-text guidance per step — for Opportunity, Lead, Case, and custom objects. You still drag the component onto the record page in App Builder; that's a one-time click Scout refuses to pretend it can automate.
- **LWC mock data rule.** When a component has no backing data source (no Apex, no wire target, no Data Cloud), Scout hardcodes realistic mock data in the JS file. A spinning wheel with no data breaks a demo worse than obviously-fake values.
- **Install and update scripts now point you at `/setup-demo-scout`.** Previously, a silent gap after `update.sh` left Slack auth unconfigured until you noticed it missing mid-session.
- **Agentforce skills now pull from the official `forcedotcom/afv-library`.** Same content, newer versions, one fewer upstream repo for Scout to track. The Jaganpro skills will follow once their migration lands — Scout's not repointing speculatively.
- **"Topics" → "subagents" across Scout.** Agent Script v2 renamed the keyword in `.agent` files; Scout's spec template, orchestrator messages, and audit language now match what the skill actually emits. No change to deployed output.
- **Fixed before any field use: the BusinessProcess XML root was wrong in yesterday's build** (would have failed deploy on all four objects). Scout now retrieves an existing BusinessProcess from your org as a reference before writing new XML — if the org already emits a shape, mirror it.

## 2026-04-27

- **Industry-cloud and managed-package default apps now audit correctly.** Life Sciences Commercial, Health Cloud, Q Branch and friends were silently falling back to core-6 because `retrieve_metadata` was called without the package namespace. One live probe exposed what a week of inferred rules had missed; the fix is a namespace-aware app-name construction.
- **Smarter data-seeding deployments.** `/scout-sparring` now runs `sf sobject describe` on every Data Seeding target object before writing the spec, so field-name, RecordType, and picklist-vs-text mismatches surface during sparring — not halfway through a deploy when you've stopped paying attention.
- **Reusable seed scripts by default.** For cross-object data seeding, `/scout-building` now produces an idempotent script with a `--pilot-only` rehearsal flag. The sub-agent runs it against your live org before returning, and the exact pilot + bulk commands land in the change log and handover brief so you can safely re-run after a re-spin or hand off to a colleague.
- **Cross-object data seeding is now autonomous** when backed by a self-tested idempotent script. Previously: single-object only. The gate moved from "how many objects?" to "does the pilot pass?"
- **Shared lessons now carry the fix, not just the failure.** When the lesson is a debugging one, Scout captures the verbatim error and the working fix as sub-bullets — and stamps each lesson with the Scout git SHA that produced it. Field reports from colleague laptops are useless without knowing which Scout build they came from.
- Fixed: the `/scout-sparring` default-app override query no longer dies on the Salesforce API's refusal to do disjunctions. Two sequential queries (DeveloperName first, Label fallback) replace the single one that kept getting rejected.
- Fixed: `unpackaged/` directory left behind by audits. Now gitignored and auto-swept after each audit.

## 2026-04-26

- **Phase 3 gets smarter about actions.** `/scout-building` now tries standard Agentforce actions (Get/Update Record, Knowledge grounding) before reaching for Apex — and requires evidence of the standard-action failure in the change log before accepting an Apex fallback. The pre-deploy gate enumerates backing actions verbatim from the spec, discloses the auto-created Einstein Agent User, and warns loudly if the spec said "no Apex" but an Apex action is being proposed anyway.
- **More honest Phase 3 reporting.** Actions that couldn't be verified in `sf agent preview` (stateless-preview gaps, Knowledge grounding waiting on a Data Library) now surface as their own category in deployment logs — distinct from smoke-test failures. The handover brief adds a 30-second citation check for any Knowledge-grounded agent so you're not the one finding out post-demo that grounding never worked.
- **Self-healing schema validation.** When a sub-agent mangles its JSON envelope but the deployment actually succeeded, Scout probes the org directly (BotDefinition for agents, SOQL for objects/fields, `retrieve_metadata` for flows/Apex/LWC) before forcing a retry. Cosmetic output drift no longer risks re-publishing an active agent.
- **Friendlier setup.** `/setup-demo-scout` asks for your org alias instead of silently grabbing `demo-org` (which may already belong to something else), probes the macOS Keychain for Slack auth, and walks you through `/mcp-auth` if you're not connected. No more discovering Slack's broken three stages into a sparring session.
- **Sparring default-app resolution is no longer fragile.** `/scout-sparring` surfaces the detected app and asks you to confirm before the audit spawns — skipping the cascade through unsupported fallbacks that used to burn queries when your active app was Q Branch, Demo Wizard, or a setup-only app. Customer folder names follow a deterministic slug algorithm and match against existing folders before creating new ones.
- **Pre-launch UX hardening.** Pre-deployment check is a straight yes/no (no mysterious third option), handover brief drops the "paste into ChatGPT" suggestion (the Slack canvas handles it), and shared lessons point at `#sf-demo-scout` instead of a hardcoded personal handle that shipped to every SE.
- **Safer by default.** A narrow deny list blocks destructive operations on your `orgs/` folder, `~/.sf/` auth cache, and force-pushes to main. Normal Scout flow is unchanged — the deny list only fires on things you'd regret.
- **`/sync-skills` retired as a manual command.** Skill updates happen automatically during `update.sh` now; the sync engine itself is unchanged, just no longer a button you have to remember to press.
- **README refreshed for launch** — reflects retired commands, the Slack OAuth flow via `/setup-demo-scout`, and corrected skill/command counts.
- **Cleaner `.zshrc`.** Scout stops leaving "superseded by managed block" comments for its own fixed-value keys (model IDs, token limits) — the redacted lines always matched what the managed block wrote, so the comments carried no information and accumulated forever. Existing legacy comments get swept on next install.
- Fixed: screen-flow smoke tests now invoke the correct `[FlowApiName]_Test` class — the previous command was two authoring passes out of sync with itself.
- Fixed: audit orchestrator no longer references an undefined user Id in a stage it never captured one.
- Fixed: post-deployment checks now cover objects that already had active flows before the deploy — header claimed this; procedure didn't.

## 2026-04-25

- **Audit progress is visible while it runs.** The Stage 4 fresh-audit used to be a 10-minute black box — three parallel sub-agents working silently while you sat wondering if Claude Code had hung. Each sub-agent now drops one-line heartbeats into `.audit-progress.log` at section boundaries, and Scout surfaces a clickable link to the log in the sparring message so you can watch progress without Opus having to read the file (and pay for it).
- **README caught up for the US launch** — skill count corrected (16, not 13), `sf-lwc`/`sf-testing`/`sf-flex-estimator` listed, Slack MCP documented with its first-session OAuth step, simple screen flows moved from "manual" to "confirm-once" to match what Scout actually does.

## 2026-04-24

- **Slack integration simplified to an in-session ask.** Gone: the sources files you were supposed to curate per customer. Instead, Scout asks inline during sparring which canvases (and optionally one channel) to reference, and offers a handover-canvas y/n prompt after deploy. Turned out SEs renamed canvases every session anyway, so the "curated state" premise never survived first contact with a real customer.
- **Opus stops truncating on long reasoning.** Thinking budget raised from 1024 to 4096 tokens — the Opus sparring/review step was silently hitting the cap, which manifested as responses that mysteriously stopped making sense.
- **Your `.zshrc` is now managed by Scout.** A `# BEGIN SF-DEMO-SCOUT` / `# END SF-DEMO-SCOUT` block rewrites canonical values for model IDs and token limits on every install — so new Scout versions actually propagate instead of being silently skipped by the old per-key append-if-missing logic. Conflicting old exports get commented out with a dated note. PATH and non-Scout vars are untouched.
- Cleaner install output — fixed a section-numbering gap (`8 → 10` used to skip `9`) and removed a dead shell-reload call that did nothing useful.
- Fixed a broken Slack canvas-search tool name, pruned dead Slack tool grants from sparring permissions, and synced CLAUDE.md's Slack section to match the current integration.

## 2026-04-23

- **Screen flows now autonomous.** Scout builds simple screen flows end-to-end — up to 3 screens by default, 5 if you make the case during sparring. Scout also writes a Flow Test, runs it with `sf flow run test`, and only activates the flow on pass. You still walk through it once in the UI to sanity-check the look and feel — automation draws the line at "does it run," not "does it look good." This is the first of three deferred capability expansions (screen flows → OmniStudio → Data Cloud).
- **LWC generation follows PICKLES, Apex tests self-heal, and Agentforce scenarios get cost estimates.** Three new community skills landed: `sf-lwc` (Salesforce's official PICKLES methodology + SLDS 2 + 165-point scoring; required before any LWC generation in Phase 2), `sf-testing` (agentic Apex fix loops up to 3 iterations on first-attempt failure — Scout's two-attempt rule still applies above), and `sf-flex-estimator` (public-list Flex Credit cost projection for Agentforce actions and Data Cloud meters; surfaces in sparring platform research when relevant).
- **Scout now runs on LLMGW — the company-wide Claude gateway.** No more `aws sso login` at session start; the gateway speaks Bedrock protocol but authenticates with a long-lived LLMGW token from Google OAuth. Default repo location moved to `~/claude-projects`. If you're setting up fresh, use the official Solutions installer first, then clone Scout.
- **Update notices now surface inside `/scout-sparring`.** A flag file (`.claude/.update-available`) gets written when you're behind `origin/main` and surfaced as part of Stage 1's model gate — commits-behind count plus the first three CHANGELOG bullets. Harder to miss than the old banner, easier to act on without leaving the session.
- **Leaner everything.** Audit sub-agents share a single rule block instead of three near-identical copies, Phase 2's "CRITICAL —" warnings got downgraded so the one that matters actually stands out, and the sparring/building commands load less into memory at session start. More room for the actual demo work.
- **Smarter Phase 2 deployments.** Conditional section markers (`<!-- IF:FLOWS/APEX/LWC -->`) in the phase prompt let the orchestrator strip irrelevant blocks before spawning the sub-agent — roughly 200 lines saved on single-category deployments.
- Fixed: the audit page-layout query was silently returning no results for custom objects in three places. The Tooling API stores the entity key ID for custom objects, not the string name — Scout now uses a `Name LIKE` pattern instead.
- Fixed: Agentforce rollback command in the change log template pointed at the wrong metadata type (should have been `AiAuthoringBundle`, not the bot + planner pair).
- Minor: `/scout-building` no longer fires macOS notifications during active deployments — the chat prompt is already prominent.

## 2026-04-22

- **Demo Handover Brief.** After every deployment, Scout now writes a business-language summary of what was built, a three-beat demo story outline, your SE to-do list (visual QA, App Builder placements, any final-mile checks), and the exact file locations with a one-click Finder shortcut. Designed for the handoff moment, not the deploy moment.
- **Faster sparring and deployments.** End-of-flow procedures (handover brief, post-deployment checks) now load on demand instead of at session start, and Phase 1 sub-agents stop receiving rules for queues, layouts, or permission sets when your spec doesn't need them. Roughly 700 tokens saved on data-only specs — small per-session, meaningful across a day.
- **`/switch-org` now offers to connect a new org directly** — type `new` to start the SSO flow instead of having to remember which command does that.
- **Sparring responses are more concise.** Same depth of judgment, fewer words — a 4-6 sentence rule unless you ask for more or the stage requires structured output. Token cost compounds across turns; brevity pays.
- Fixed: post-deployment verification no longer queries a non-existent `DeveloperName` field on `FlowDefinitionView` (the correct field is `ApiName`).

## 2026-04-21

- **Reuse-org mode.** A third sparring intent alongside "new scenario" and "iterate on existing" — reuse an org from a prior customer without wasted discovery steps. The route table in Stage 3 now classifies all three intents up front and skips the stages that don't apply.
- **Iteration-only stages now load on demand.** Stages 4i and 6i (the iteration-specific discovery shortcuts) extracted to `sparring-iteration.md`, loaded only when the intent matches. Scout-sparring drops from 294 to 254 lines of always-loaded context.
- **Audit is cheaper on large orgs.** Standard-objects sub-agent now retrieves layout XML only for ★-marked layouts (not every layout for every record type), tightens EntityDefinition queries with `IsLayoutable = true`, and counts flows client-side instead of via an unsupported `GROUP BY`.
- Fixed: flow audit no longer wastes a query on a `GROUP BY` that the `FlowDefinitionView` Tooling API entity quietly rejects.

## 2026-04-20

- **Platform restrictions surface during sparring, not during deploy.** Scout now captures `EntityDefinition` flags (`IsCreateable`, `IsQueryable`, `IsTriggerable`) at audit time and interprets them via Docs MCP during platform research — so the spec's Platform Constraints section warns you about managed-package objects that default to dynamic SOQL, Health Cloud objects that reject static references, and similar gotchas before you commit to a scenario.
- **Data shape validation before spec write.** Stage 7b now samples records, checks lookup population, and confirms field filterability for every object the scenario depends on — catching "great idea, empty org" before it becomes a deployment surprise.
- **`update.sh` replaces incremental `git pull`.** Nuke-and-reinstall: backs up `orgs/` and `.sf/config.json`, deletes the repo, re-clones, runs `install.sh`, restores. Your personal lessons, org config, and demo history survive — incremental update machinery (drift checks, changed-file detection) doesn't, because it broke every time the project structure evolved.
- **Lessons now live in `orgs/` instead of `.claude/prompts/`** — so they persist across `update.sh` runs. First-time `/setup-demo-scout` creates empty lesson files; you accumulate them organically.
- **Shared lessons-maintenance fragment** nudges you to trim your lessons file when it exceeds 25 lines, with a one-click Slack share to `#sf-demo-scout`.
- Fixed: MCP tools actually load on first launch now. `install.sh` pre-caches the `@salesforce/mcp` package via `npx --help` — without this, first-time users hit a silent timeout because npx downloads the full dependency tree during the first Claude Code session.
- Fixed: stale `sf` CLI versions no longer break MCP connections. `install.sh` now runs `sf update` when the CLI is already installed.

## 2026-04-19

- **Audit split into three parallel workers.** The monolithic audit hit the 8K output cap after ~100 tool calls on SDO-scale orgs. Scout now spawns three Sonnet sub-agents in parallel — standard objects, apps/flows/agents, custom objects/permsets — each writing to disk and returning a compact JSON summary. Opus stitches the Notable Gaps narrative from the summaries without ever reading the raw payloads.
- **Queues and picklist value additions now autonomous.** Added to Phase 1 without an SE gate — cheap, stable metadata with no visual-editor round-trip.
- **Agentforce smoke test after deployment.** Scout runs three utterances through `sf agent preview` and records the responses in the change log — catches obviously-broken agents before you demo them.
- **Industry-cloud detection during audit.** `EntityDefinition` queries now detect Health Cloud, FSC, Life Sciences, Manufacturing, and Insurance objects automatically, reporting them in the audit's Demo Surface Notes for Opus to factor into scenario design.
- **Platform research moves before scenario proposal.** Stage 6 now consults Docs MCP and reasons about the org's data model before you commit to a scenario — so "great idea, impossible on this org" surfaces while you're still shaping the demo.
- Fixed: session startup no longer falsely reports "no default org" on systems where `sf` emits pretty-printed JSON with whitespace around colons. Six grep patterns now tolerate the spaces.
- Fixed: audit no longer silently misses flows or agents. Flow enumeration uses `GROUP BY TriggerObjectOrEventLabel` instead of a hardcoded 6-object list; agent detection adds `GenAiPlannerBundle` retrieval as a fallback when `BotDefinition` filters are too narrow.

## 2026-04-18

- **Salesforce Docs MCP integrated.** Scout can now search and fetch official Salesforce documentation via a remote HTTP MCP server — closes the Bedrock no-web-access gap. Sparring gets a dedicated Feasibility Pass (Stage 7) that consults docs before spec generation; deployment sub-agents consult docs on unfamiliar errors before retrying.
- **Docs consultation is targeted, not ambient.** A decision tree lives in the `demo-docs-consultation` skill: release-gated features, industry cloud data models, novel metadata types, unfamiliar deploy errors, architectural research — yes. Things Opus already knows cold — no.
- **Spec and change log now cite which docs were consulted** — citation format standardised across sparring and deployment.
- **Scout-building becomes an Opus orchestrator with Sonnet sub-agents.** Phase 1 (org config), Phase 2 (flows/apex/lwc), Phase 3 (agentforce) each run as Sonnet sub-agents with their own prompt templates. Opus handles judgment, prompt construction, failure interpretation; Sonnet handles speed, instruction-following, XML generation. Sub-agents return fenced JSON blocks instead of unstructured text — finally robust parsing.

## 2026-04-17

- **`/sync-skills` command** — one command to pull the latest versions of all community skills (pre-retirement, before skill sync moved into `install.sh` itself on 2026-04-26). Driven by a declarative `.claude/skills-manifest.yaml` that replaces hardcoded bash loops.
- Fixed: switching orgs now actually sticks. `/switch-org` writes to local scope (`.sf/config.json` in the project) instead of `--global`, which MCP was correctly reading even when you thought you'd switched.

## 2026-04-16

- **Metadata generation routed through specialist skills.** Custom fields, custom objects, and permission sets now generate via the `generating-*` skills from Salesforce's `forcedotcom/afv-library` — with proper handling of Master-Detail constraints, Roll-up Summary formats, required-field FLS exclusion, and the dozen other things Salesforce quietly rejects if you get the XML wrong.
- **Structured deployment error recovery.** Sub-agents now run a fail-twice-then-skip loop inside a single invocation, with docs consultation between attempts on unfamiliar errors — instead of the orchestrator firing cryptic retries from outside the loop.

## 2026-04-15

- **`install.sh` now installs Claude Code itself** — truly one-script setup. Paired with PATH handling, skill sync, MCP registration, and shell profile updates.
- Skill folders lost their ugly underscore prefixes (`_demo-*` → `demo-*`).

## 2026-04-14

- **No more manual org config in CLAUDE.md.** Scout reads your active org from `sf config get target-org` at runtime and surfaces it via session-startup — alias, username, connection status. Run `/switch-org` to change; no editable values in project files.
- **Agentforce is a first-class sparring citizen,** not an afterthought bolted onto the end of scenario design.
- **Iteration mode.** Make targeted changes to existing demos without running full rediscovery every time — Stage 1.5 classifies intent and routes to a lighter discovery path.
- **Faster session startup.** Heavy skill contents load on demand at point of use instead of via eager `@`-injection in CLAUDE.md — roughly 20 KB of tokens saved per session.
- Fixed: various stale command references, hardcoded customer names, and broken lessons.md paths cleaned out of the pipeline.
- Removed: manual org editing in CLAUDE.md, and the short-lived WebFetch/WebSearch experiment (Bedrock's Haiku sub-processor blocks both — remote HTTP MCPs became the workaround instead).
