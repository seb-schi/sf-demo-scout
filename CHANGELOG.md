# What's New in Demo Scout

Check your last `update.sh` date against the headers below to see what you missed.

## 2026-05-23

- **Scout is now a Claude Code plugin.** The whole install model has changed. Scout is no longer a repo you clone and `update.sh` — it's an official extension you install from a plugin marketplace, the same way Claude Code itself gets its other extensions. Existing SEs upgrade by running `bash update.sh` one last time; it hands you off to the plugin install and migrates your workspace in place (orgs, lessons, change logs all preserved). After today, you never run `update.sh` again. Closes a six-week migration arc.
- **One command for everything install-related: `/scout-setup`.** First-time install, post-update refresh, "something feels broken — please reset" — same command, every time. Replaces the old `/setup-demo-scout` plus a handful of separate manual steps. Run it any time you suspect Scout is out of sync; it figures out what state you're in and only does the work that's actually needed.
- **Updates are now (almost) fully automatic.** Whenever we publish a new Scout version, Claude Code pulls it down in the background — typically within a few minutes of starting your next session. When an update is downloaded but not yet finished installing, you'll see a one-line banner at the top of your session: "Scout update downloaded — run /scout-setup to finish installation." One command, you're current. No more "am I on the latest version?" anxiety.
- **`/scout-sparring` is lighter on the way in.** The old separate update-acknowledgement step is gone — folded into the regular sparring flow. Same safety, one less round-trip before you're sparring.
- **Skills sync stays current automatically.** The 16 specialist skills (Apex, LWC, Flow, Agentforce, etc.) refresh from Salesforce's official source whenever Scout updates or you run `/scout-setup`. No more wondering whether your skill versions match what Scout's pipeline expects.
- **Migration UX polished through real test cycles.** Slash commands in the install walkthrough are now copy-paste-friendly inside the Claude Code terminal (the previous code-block formatting was getting flattened and lost its copy button). Step-by-step install instructions, plain-language phrasing, fewer "wait, what's that?" moments.
- **Plugin README** ships with real install / first-run / update / uninstall instructions, replacing the placeholder copy.
- Fixed: the "you're on the wrong model" warning at the start of sparring is now a single line instead of a stop-and-switch interruption.
- Fixed: your shell config no longer accumulates a mysterious blank line every time Scout updates (one of those "huh, that's weird" things — it was a long-standing bug in the old install path, and it's gone now).
- Fixed: leftover references to the temporary plugin repo URL purged from install scripts and READMEs after the single-repo cutover.

## 2026-05-20

- **Scout sessions stay on Opus by default — no more "did you switch the model?" dance.** Project default is now `opus` in `.claude/settings.json`, so sparring and building both run on Opus from message one. The `/switch-org` and other Sonnet-by-design commands keep their explicit override. The model gate in scout-sparring still fires as a safety belt, but it should now be a one-line "yes" instead of a stop-and-switch step.
- **`/compact` suggestion after fresh audits.** Audits load 30-50K of pre-spawn metadata XML on SDO-scale orgs; Scout now nudges you to compact before Stage 4 if context is tight. Reuse-branch audits skip the suggestion (nothing heavy was loaded).
- **`/project-sparring` carries less weight per session.** Deployment-guide format spec moved to an on-demand prompt fragment, loaded only when actually writing the guide. ~35 lines off the always-resident command body.
- **Audit sub-agent regressions from the 2026-05-20 meta-test fixed.** Two prompt regressions surfaced when comparing a fresh audit against the prior run on the same org: the custom-objects sub-agent had over-narrowed its enumeration to objects in the active-page map (silently dropping AI_Agent and other helpers), and the standard-objects sub-agent had started prefixing layout names with the object (`Account-SDO - Account`), breaking the round-trip into `retrieve_metadata`. Both fixed in the prompts; enumeration and classification are now independent axes, and layout names ship as the bare metadata API name.
- **Audit dispatch slimmed further — Opus no longer carries sub-agent prompt bodies.** The orchestrator now passes each sub-agent its prompt *path* plus a placeholder map; the sub-agent reads its own prompt and substitutes. Saves ~580 lines of prompt body per audit on Opus. The placeholder values themselves (notably the active-page map serialized as JSON) still pass through Opus — the win is the prompt bodies, not 100% of every dispatch.
- **Audit sub-agent tool budget extended via bulk-fetch.** The custom-objects sub-agent used to do per-object ProfileLayout queries + per-object layout retrieves with fallback retries — on customer SDOs with 17+ relevant custom objects, this could exhaust the sub-agent's tool budget mid-flight (silently — the harness surfaces the agent's last sentence as "result"). Custom-objects discovery now bulk-fetches: one SOQL with `WHERE TableEnumOrId IN (...)` for ProfileLayout, one manifest retrieve listing all layouts upfront. Missing layouts surface as parse-side soft outcomes instead of retry loops.
- **Orchestrator detects partial sub-agent returns structurally.** When a sub-agent hits a budget or timeout wall, the harness returns mid-narration text (`"Reading the remaining XMLs in parallel..."`) — not a JSON envelope. The orchestrator now regex-checks for a fenced JSON block before parsing; absent → automatic re-dispatch (max 1 retry) before falling through to the SE-prompt. Same defense at the prelude-return step.
- **Live-status link emits earlier and covers the full audit window.** The "Audit running — live status →" link used to fire only after the 3 parallel sub-agents were spawned, leaving the prelude phase (~30-60s of metadata retrieves) silent. The link now emits right after the SE confirms the default app, so it covers prelude + parallel work as one continuous async window. Same MUST framing — Scout shouldn't go silent for minutes without a status signal.
- **Audit synthesis can't invent classification labels.** New pipeline rule: the Notable Gaps narrative may summarize and connect sub-agent findings, but every classification label that appears in prose (`unretrievable`, `mixed`, `gap_risk`) must appear verbatim in the sub-agent's structured output. If a thing wasn't retrieved, say it wasn't retrieved — don't promote that absence to a status label.
- **Audit cleanup sweeps catch more model-invented orphans.** Sub-agents occasionally write ad-hoc working files (`temp-*.xml` at the repo root, `retrieve-*.xml` inside the customer folder) during retrieve workarounds. The start-of-run cleanup now sweeps these prefixes too — pattern-prefixed, not blanket, so future customer-owned XML in the audit folder isn't at risk.

## 2026-05-18

- **Skill sources repointed to Salesforce's renamed `forcedotcom/sf-skills` repo.** No content change today (the old `afv-library` URL was a byte-identical mirror), but Scout now pulls from the canonical name so future updates land cleanly.
- **Audits don't trip over leftovers from the previous session anymore.** A crashed or interrupted prior audit used to leave stale working files in the customer folder and at the repo root; the next `/scout-sparring` would inherit them and silently hang at the parse step. Cleanup now runs at the *start* of every audit, sweeps everything (per-customer artifacts + repo-root drops), and uses zsh-safe shapes so an empty target never errors. Surfaced when a Sivantos audit hung after a clean LSDO session left files behind.

## 2026-05-11

- **FlexiPage audit pipeline tightened after early field runs.** Two fixes surfaced from real Showtime deploys: the audit cleanup step is now zsh-safe (an empty-glob error was silently skipping audit init on fresh customer folders on macOS), and the standard-vs-custom-object split in the active-page map is now enforced at the orchestrator level so the custom-objects sub-agent can't emit a degraded entry for a standard-object page. Drift becomes structurally impossible, not just discouraged.
- **Showtime stacking framing is more honest.** When the customer's wish was already inside the envelope cap, Scout now says "nothing was cut" instead of claiming a reduction. Reductions are only named when something actually got cut.
- **Showtime is calmer to run live.** No more "is Scout waiting on me or working in the background?" — the transcript prompt now appears only after the audit finishes. Use the audit window for your opening discovery questions, exactly as designed.
- **Showtime customer-facing canvas redesigned for skim-first reading.** Same content, lighter shape: capability summary table at the top, per-capability sections with one emoji header each, "Powered by:" inline, ✅ checklist for what's about to deploy, em-dash framing on follow-ups. Tone stays clean and confident — light emojis on section headers, no jokes in body copy. Customer pull-quotes only when the transcript actually surfaced one. Help-article links preserved verbatim.
- **Scout no longer trips over modern Salesforce record pages.** First Showtime run almost shipped a silent fail: Scout added two fields to the Case page layout correctly, but the *actual* page the customer would have seen was a custom-built Lightning page that doesn't auto-show layout fields. The audience would have seen nothing. Audit now figures out which Lightning page is really showing up — checking every assignment path Salesforce supports (by app, by record type, by profile, org default) and resolving them in the right order — reads the page's structure, and ★🚨-flags the cases where a layout-only deploy won't show up visibly. Each flagged page comes with a breadcrumb (`assigned via app default in Service Console`, `assigned via profile combo for System Administrator`, etc.) so a misassigned page is traceable in one read.
- **Scout can now add fields directly to Lightning pages, when it's safe to.** When the audit confirms the page accepts field-section adds, and the spec says exactly which section and column the field belongs in, Scout edits the Lightning page itself, deploys, and re-reads the page to verify the field landed in the right place. Multi-column sections need an explicit column number in the spec; if the page's structure is anything more exotic (custom components, dynamic forms, opaque layouts), Scout drops it into App Builder for you. The spec template now asks the routing question up front: classic page layout, Lightning page field section, or App Builder by hand?
- **Build Boundaries spell out the dual-system reality.** "Page layout field additions" now explicitly says "active classic Page Layout" and lives next to a separate gated entry for "Lightning Record Page field additions to existing field-section components." SE Manual covers everything else on the Lightning page side — new sections, repositioning, components, anything custom-composed. The line is no longer ambiguous.

## 2026-05-08

- **Iteration sparring now handles "fix this broken thing" intent.** Paste the error text and reproduction step; Scout researches it against Salesforce docs and proposes a remediation spec. Driven by SE feedback after a post-deploy Agentforce preview error that didn't pattern-match the additive iteration path.
- **Showtime is now a continuous engagement format with a customer-facing Slack canvas.** Fire it up when the customer sits down: audit runs in parallel with your opening discovery (~5–10min) → transcript paste → one-pass proposal with one feedback round → spec written → customer-facing Slack canvas written (while you narrate Headless 360 + Docs MCP to the customer) → `/scout-building` deploys the PoC slice while you walk the customer through the broader canvas → review the working slice together when build completes. The canvas — "What we heard / What we'd build / What we're proving today / What's next," in customer language with Salesforce doc citations — is the takeaway artifact that acknowledges everything they asked for.
- **Showtime spec captures the customer's full ask, deploys a bounded slice.** Scenario section = holistic build plan across Salesforce + Agentforce + Headless 360 + Data Cloud + Flows + Apex + LWC. New Showtime PoC section names the envelope, lists what's in the build today, lists what's deferred and why. `/scout-building` deploys only the PoC slice; deferred items are ready for `/scout-sparring → Iteration` after the demo.
- **Showtime envelopes replace the happy-path shortlist.** Five tightly-scoped envelopes — fields+layout (E1), single before-save flow (E2), single Apex (E3), single Agentforce agent with **standard actions only** (E4), data seeding (E5) — with two narrow stacking exceptions (E1+E2, E1+E5) that auto-reduce scope. E2 dropped after-save / screen / scheduled / platform-event flows; E4 dropped backing custom Apex and flows. Both cuts driven by field evidence: open-ended smoke-test surfaces don't fit a Showtime timebox.
- **Showtime always runs a fresh audit.** No more ≤24h reuse window. Pre-demo deploys must run against verified-fresh state.

## 2026-05-07

- **Sparring now has three explicit paths.** Stage 2 presents `A new demo scenario` / `Iterating on an existing demo` / `Showtime` as a menu instead of an open "what brings you in today?" — discoverable, equal-altitude, no hidden classifier logic.
- **Showtime: live customer conversation sparring.** Paste a 15-minute customer transcript, get 2 scenarios proposed against a pre-vetted happy-path shortlist, sharpen one in a single round, get a spec. No multi-stage discovery, no spine-acknowledgement gate, no cut gate. The value spine survives — auto-drafted from your transcript, emitted inline with each scenario card. Designed for the 90-minute "build alongside the customer" engagement format. Pilot at World Tour Frankfurt.
- **Happy-path shortlist as the moat.** Showtime can only propose patterns Scout has run end-to-end ≥3× cleanly — currently 3 Tier 1 (record-triggered flow + email draft, Account hierarchy + KOL fields, cross-cloud activity timeline) and 1 Tier 2 (single Agentforce agent, no Data Cloud dependency). Off-list edits route the SE to full sparring. The list grows via /project-sparring as more deployment data accumulates.
- **Spring cleaning after Showtime.** Tightened the always-loaded instructions and removed some duplicated boilerplate across commands. No behaviour change — Scout just carries less weight per session.
- **FlowTests work on the first attempt for record-triggered flows.** The template Scout writes now uses the right shape — Start node as the entry test point, parameters seeding the trigger record directly, no `apiVersion`. Yesterday's Phase 2 failure (which cost a flow's activation) becomes the inline. The recipe was learned, now it ships.
- **Agentforce deploys handle both bundle formats automatically.** When `sf agent publish authoring-bundle` fails because the org doesn't support Agent Script v2 (any flavour of "bundle not present / not supported"), Scout falls back to the legacy `GenAiPlannerBundle` retrieve+edit+deploy path — no SE intervention, no second attempt burned. Loose detection on purpose: the Agentforce surface ships features monthly and error codes drift.
- **Smarter Agentforce permset assignment when licenses fight back.** Scout now reads the running user's license, attempts the preferred runtime permset, and on a license-mismatch failure (e.g. Salesforce-licensed admin × `AgentforceServiceAgentUser`) falls through the preference order automatically — recording each attempt as carry-forward design constraint, not session noise.
- **Spec template draws a clearer line between deployable layouts and App Builder work.** `### Page Layouts` split into two siblings: `### Page Layouts (Classic — field additions only)` for the deployable path, `### Lightning Record Pages (SE Manual — App Builder)` as reference for components you'll drag in App Builder. The heading does the enforcement; the orchestrator was already skipping correctly, the spec just needed to read more clearly at a glance.

## 2026-05-06

- **Sparring now drafts a value spine before the scenario proposal.** Scout reads what you've shared in discovery and emits a one-screen draft — residual message, three key points (pain / cost of inaction / future state), and the audience whose reaction matters. Empty slots show as visible gaps, not as questions you have to answer. Edit, sharpen, or just say "move on" — the spine is guidance, never a gate.
- **Scenario proposals now cite which key point each component proves.** Flow, Apex, LWC, and Agentforce sections each carry a one-line `Proves: KP[n]` tag. The cut gate uses it: cuts should leave the residual message standing; if a cut breaks a key point, that's the load-bearing one.
- **Discovery questions sharpened, not added.** Q1 asks for the customer's direct quote on the pain point (quotes survive into the residual message almost untouched). Q3 asks for a concrete 12-month outcome or metric, not a fuzzy definition of success. Question count stays at 6.
- **Install fixed: Opus 4.7 thinking is hidden again.** Anthropic removed `adaptive` thinking display in 4.7, which left the `CLAUDE_CODE_EXTRA_BODY` env var in `.claude/settings.json` crashing Claude on any version below 4.6 — including breaking fresh installs. Hotfix removed the env var. Tradeoff: the 2026-04-29 "Scout now thinks visibly" feature is rolled back; Opus 4.7 will run with hidden thinking until Anthropic restores a working display mode. Slow operations may once again read as "is it hung?" — emit a status line before any slow op (this was always the underlying defense; the env var was the convenience layer).

## 2026-05-04

- **Install is now one Terminal command.** `curl -fsSL https://raw.githubusercontent.com/seb-schi/sf-demo-scout/main/bootstrap.sh | bash` clones, installs, and drops you into a Claude Code session with `/setup-demo-scout` already running. No more Terminal → VS Code → extension → slash-command dance. VS Code becomes a preference, not a step.
- **Updates land you back in Claude Code automatically.** `update.sh` (or re-running the one-liner) now `exec`s `claude "/setup-demo-scout"` after the reinstall, so Slack + org re-verification happens without you having to remember to launch it.
- **Claude Code CLI self-updates on every install.** `install.sh` now runs `claude update` alongside `sf update`, so you're never stuck on a stale CLI. Graceful fallback if the update path is unavailable.
- **Scout now calibrates seed data against your live org.** Tell the spec "quota = 70-80% of running user's open pipeline" instead of a literal number, and Phase 1 runs the reference SOQL before seeding and computes the right count. Stops the 881%-quota-coverage class of miss when a seed script meets a real org's actual numbers.
- **Agentforce permset auto-assigns after activate.** Scout probes for the standard runtime permset (`AgentforceEmployeeAgentUser` / `AgentforceServiceAgentUser` / `AgentforceUser`, by agent type and org edition) and assigns it to your demo user. One less manual step between publish and a working agent in the UI.
- **Handover brief reorganized.** Three buckets now: what Scout did (change-log mirror), what's yours (UI-only steps like page layout arrangement), and how to iterate (reminder that `/scout-sparring` works on existing demos too). Reads less like a launch gate, more like an ongoing collaboration.
- Sparring starts cleaner — model gate no longer mid-message rewrites itself when a Scout update is pending.

## 2026-04-30

- **Scout now builds flows of every stripe.** Record-triggered (create, update, *and* delete), screen, autolaunched, subflows, scheduled, and platform-event-triggered — all now under autonomous build with the usual single SE confirmation. The flows Scout used to push to your manual checklist as "too complex" are now fair game for a spec. Only the genuinely visual or multi-day ones (orchestration, screen flows with reactive branching or custom components) stay on your plate.
- **More Salesforce-maintained content behind the hood.** The underlying skills Scout leans on for Apex, LWC, Flow, and the rest now ship with the full library of templates, reference guides, and subflow patterns — not just the instruction file. Practically: Scout has more worked examples to copy from, so generated metadata is closer to Salesforce-preferred patterns out of the gate.

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
