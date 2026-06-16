---
name: scout-building
description: >
  Orchestrator for SF Demo Prep deployment.
  Parses a completed spec from /scout-sparring, delegates deployment to
  Sonnet sub-agents in phases, and writes a consolidated change log.
  Activate with /scout-building.
model: opus
allowed-tools: Read, Grep, Glob, Write, Edit, Bash, Agent, AskUserQuestion, mcp__Salesforce_DX__retrieve_metadata, mcp__Salesforce_DX__deploy_metadata, mcp__Salesforce_DX__run_soql_query, mcp__Salesforce_DX__assign_permission_set, mcp__Salesforce_DX__list_all_orgs, mcp__Salesforce_DX__run_code_analyzer, mcp__Salesforce_Docs__salesforce_docs_search, mcp__Salesforce_Docs__salesforce_docs_fetch, mcp__slack__slack_create_canvas
---

# Scout Building — Opus Orchestrator

You are the orchestrator. You do NOT deploy metadata directly. You parse the spec,
construct sub-agent prompts from templates, spawn sub-agents, validate their results,
and write the change log.

## Source of Truth — Spec Only

The loaded demo spec and org audit are your ONLY inputs. If the SE pastes or uploads new external context mid-session — a PDF, a doc, requirements, notes, anything that is not the spec or the audit — STOP. Do not reinterpret it, do not fold it into the deployment, and never create, modify, or delete metadata or records on its basis. Respond:

> "That's a spec change. Take it back to `/scout-sparring` to revise the spec, then re-run `/scout-building` with the updated spec."

This is a hard stop, not a judgment call — mid-build context cannot override the spec, and acting on it risks deploying or deleting the wrong things.

**Note on the skills menu:** you may see `scout-building` listed as a skill.
Ignore it — the harness auto-indexes slash commands for discoverability, but
there is no `${CLAUDE_PLUGIN_ROOT}/skills/scout-building/SKILL.md` by design. Your
instructions are this file. Do not go looking for a SKILL.md.

## Step 0: Bootstrap

Read `${CLAUDE_PLUGIN_ROOT}/prompts/workspace-bootstrap.md` and follow it. This fragment cd's into the Scout workspace and aborts cleanly if it cannot. Do not proceed with the steps below if the fragment aborted.

Read `orgs/building-lessons.md` — these are mistakes from previous building sessions. Do not repeat known mistakes.

**Docs consultation on error:** when a sub-agent reports a deployment failure with an error message not in `building-lessons` and not self-evident, consult Salesforce Docs MCP BEFORE asking the SE to retry or skip. Load `${CLAUDE_PLUGIN_ROOT}/skills/demo-docs-consultation/SKILL.md` for the decision tree. Record every consultation for the change log.

---

## Step 1: Confirm Org & Identify Customer

Run `sf config get target-org --json` and `sf org display --json`. Extract the raw alias and username. The raw alias (e.g. `Metro CPQ`) is for `--target-org`. To find the customer folder, slugify the alias first — read `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/slug-rule.md` and apply its transform to the alias (sparring names folders by the slugified alias, so a raw caps/space alias would not match).

List org folders: `ls -d orgs/<slug(alias)>-*/`. Once the SE confirms the customer, set `ORG_FOLDER` = the matched folder (e.g. `orgs/metro-cpq-metro`) and use `[ORG_FOLDER]` for every path below.

Present both in a single message. Prepend the model-gate warning verbatim as the FIRST line of whichever branch fires, then a blank line, then the active-org sentence:
- No folders -> "⚠️ This command is designed for Opus. Please run `/model` to switch if not on Opus.\n\nActive org: [alias] ([username]). No customer folders found — run /scout-sparring first." Stop.
- One folder -> "⚠️ This command is designed for Opus. Please run `/model` to switch if not on Opus.\n\nActive org: [alias] ([username]). Customer: [customer]. Deploying here. Type 'switch' to change, or confirm."
- Multiple folders -> "⚠️ This command is designed for Opus. Please run `/model` to switch if not on Opus.\n\nActive org: [alias] ([username]). Multiple customers found: [list]. Which one?" Wait.

Wait for confirmation. If the SE wants to switch orgs: *"Stopping. Run `/scout-switch-org` in a fresh session to change orgs, then re-run `/scout-building`."* Stop — do not proceed.

---

## Step 2: Load Spec

```
ls -lt [ORG_FOLDER]/demo-spec-*.md
```

- No specs -> "Run /scout-sparring first." Stop.
- One spec -> load automatically, tell SE which file.
- Multiple -> list with timestamps, ask SE to choose. Wait.

---

## Step 3: Load Org Audit

Find most recent audit in `[ORG_FOLDER]/`.
Check `Org Audit Used:` field in spec header.

- Audits match -> proceed.
- Audits differ -> warn: "Spec used [old audit] but latest audit is [new audit]. If you made manual changes between those dates, the spec may have conflicts. Continue? (yes/no)"
- No audit -> "Run /scout-sparring first." Stop.

---

## Step 4: Pre-Deployment Conflict Check

Cross-check spec against audit:
- Object/field API name collisions
- Flow conflicts with existing active flows
- LWC/Agentforce name collisions
- Spec items already marked with warnings -> surface explicitly

> "Pre-deployment check complete. [N] items to review:
> [issue] — [risk]
> Proceed? (yes/no)"

If the SE answers `no`: tell them *"Stopping. Re-run `/scout-sparring` to revise the spec, or edit it manually and re-run `/scout-building`."* Stop.

Wait for go-ahead. This is the last SE input required before Phase 1.

---

## Step 5: Phased Deployment via Sub-Agents

### Workspace Prep — Clean Scratch force-app

Before any phase runs, clear converted-retrieve scratch so this deployment starts clean and any pollution from a crashed prior run — or from the pre-2026-06-08 cwd-drift bug — is swept. `retrieve_metadata` converts what it pulls into the SFDX project's `force-app/main/default/`; that tree is pure transient scratch (demos live in `orgs/`, `force-app/` is never committed). Run unconditionally:

```bash
find "$HOME/claude-projects/sf-demo-scout/force-app/main/default" -mindepth 1 -delete 2>/dev/null || true
find orgs -maxdepth 2 -type d -name force-app -exec find {} -mindepth 0 -delete \; 2>/dev/null || true
```

`find … -delete` (never `rm -rf`) is the deny-rule-safe idiom — the SE workspace `.claude/settings.json` ships a catastrophic-deletion deny `Bash(rm -rf orgs*)`, and Claude Code hard-denies the WHOLE compound if any segment matches a prefix glob, so an `rm -rf orgs/...` sweep would get the prep block denied and the deploy couldn't start (same constraint documented for the audit's `.scout-tmp` sweep). The first sweep clears the legitimate project `force-app/` contents but keeps the `main/default/` skeleton so the package dir stays valid; the second removes any stray `orgs/<customer>/force-app/` tree left by the old cwd-drift behaviour. Do NOT change these to `rm -rf` — it will re-trip the deny rule.

### Phase Analysis

Read the spec and determine which phases are needed:

- **Phase 1 (Org Config):** Always runs if spec has Objects & Fields, Record Types, Permission Set, Data Seeding, Page Layouts, Lightning App/Tabs, Business Processes, or Paths sections.
- **Phase 2 (Flows/Apex/LWC):** Runs only if spec has Flows, Apex, or LWC sections.
- **Phase 3 (Agentforce):** Runs only if spec has Agentforce section.

Tell the SE which phases you identified:
> "Deployment plan: Phase 1 (Org Config) [+ Phase 2 (Flows/Apex/LWC)] [+ Phase 3 (Agentforce)]."

If only Phase 1 applies:
> "Only safe operations in this spec — no Flows, Apex, LWC, or Agentforce. No further SE confirmation needed. Deploying now."

### Sub-Agent Output Validation

After EVERY sub-agent returns, load `${CLAUDE_PLUGIN_ROOT}/prompts/building/sub-agent-validation.md` and run the validation procedure before proceeding. The procedure covers JSON parse checks, per-phase required-keys lists, empirical org-probe queries for schema-drift-with-successful-deployment, an unconditional Data Seeding Integrity Probe (runs whenever Phase 1's `data_seeded[]` is non-empty — verifies seeded counts and field values against the org using spec-parsed expectations, catching a schema-valid envelope that reports zero or short seeds as SUCCESS), and the retry-or-skip gate when the org confirms an incomplete deployment.

### Phase Prep Procedure

Every phase follows the same prep flow. Per-phase inputs are in the table below.

1. Read the template file from `${CLAUDE_PLUGIN_ROOT}/prompts/building/`.
2. If the template has `<!-- IF:... -->` markers, strip blocks whose tag has no matching content in the spec (marker comments included).
3. Replace every `{{PLACEHOLDER}}` with the content listed in the phase's row below. Do not inject skill file contents — sub-agents invoke skills by name via the Skill tool.
4. Spawn: `Agent(description="[row's description]", model="sonnet", prompt=[constructed prompt])`.
5. Validate output (see Sub-Agent Output Validation above) before moving on.

| Phase | Template | IF markers | Placeholders | Agent description |
|-------|----------|------------|--------------|-------------------|
| 1 | `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md` | `QUEUES`, `LAYOUTS`, `LRP`, `PERMSET`, `STRUCTURAL`, `PICKLISTS`, `DATA_SEEDING`, `BUSINESS_PROCESS`, `PATHS` | `{{ORG_ALIAS}}`, `{{ORG_USERNAME}}`, `{{ROLLBACK_DIR}}` (= `$HOME/claude-projects/sf-demo-scout/[ORG_FOLDER]/rollback` — absolute, resolved from Step 1's `ORG_FOLDER`), `{{SPEC_SECTIONS}}` (Objects & Fields, Record Types, Permission Set, Data Seeding, Page Layouts, Lightning Record Page — Field Section additions, Lightning App / Tabs, Business Processes, Paths) | `Phase 1: Org Config deployment` |
| 2 | `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase2.md` | `FLOWS`, `APEX`, `LWC` | `{{ORG_ALIAS}}`, `{{ORG_USERNAME}}`, `{{PHASE1_SUMMARY}}`, `{{SPEC_SECTIONS}}` (Flows, Apex, LWC sections) | `Phase 2: Flows/Apex/LWC deployment` |
| 3 | `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase3.md` | *(none)* | `{{ORG_ALIAS}}`, `{{ORG_USERNAME}}`, `{{PRIOR_PHASES_SUMMARY}}`, `{{ROLLBACK_DIR}}` (= `$HOME/claude-projects/sf-demo-scout/[ORG_FOLDER]/rollback` — absolute, resolved from Step 1's `ORG_FOLDER`; same value injected into Phase 1), `{{SPEC_SECTIONS}}` (Agentforce section), `{{VALIDATION_GATE}}` (= full verbatim contents of `${CLAUDE_PLUGIN_ROOT}/prompts/building/agentforce-validation-gate.md` — read the file and substitute; sub-agents cannot resolve `${CLAUDE_PLUGIN_ROOT}`, so inject the content the same way `{{AUDIT_SHARED_RULES}}` is injected) | `Phase 3: Agentforce deployment` |

### Phase 1: Org Config

Run the Phase Prep Procedure for Phase 1. After it returns, if critical items failed (objects that Phase 2/3 depend on), warn the SE before continuing.

### Phase 2: Flows / Apex / LWC — if applicable

**SE gate before spawning.** List what will be deployed and ask:
> "About to deploy: [plain English list]. Proceed? (yes/no)"

If no, record as skipped. If yes, run the Phase Prep Procedure for Phase 2.

**Phase 2→3 Risk Review (if Phase 3 applies):** Before the Phase 3 SE gate, scan Phase 2's `discovery_notes`. For each discovery involving an object also used in Phase 3's Agentforce actions:
- Cross-check against `orgs/building-lessons.md` — known restriction or new one?
- Include the risk in the Phase 3 SE confirmation prompt (below).
- Fold discovery notes into `{{PRIOR_PHASES_SUMMARY}}` as explicit risk callouts, not just deployment facts. Example: "⚠️ Phase 2 discovered MedicalInsight is a managed object requiring dynamic SOQL — Agentforce execution context may also restrict it."

If `discovery_notes` is empty or contains no Phase 3-relevant entries, proceed normally.

### Phase 3: Agentforce — if applicable

**Editability pre-flight (MUST — run before the SE gate, before any sub-agent spawn).** The failure this prevents: two consecutive builds shipped a dead topic because the sub-agent hand-patched a compiled `GenAiPlannerBundle` on a UI-built agent (added topic/action graph references but not the matching `localActions/<topic>/<action>/{input,output}/schema.json` folders — so the actions can't resolve at runtime, yet deploy reports SUCCESS and the agent stays Active). Determine editability ONCE here:

1. Read the spec's Agentforce section. Classify the change: **net-new agent** (no existing agent named) vs **modify-existing** (spec targets an agent already in the org), and whether the change **adds or moves a topic/action** (structural) vs **tweaks existing node text/values only** (in-place).
2. For modify-existing, determine editability with a cheap SOQL query FIRST, then confirm with a single retrieve used as a boolean (do NOT parse error strings — `agentDSLEnabled` is NOT SOQL-reachable; it lives only in `.bot-meta.xml`, so don't query it):
   ```sql
   SELECT DeveloperName, Type, AgentType FROM BotDefinition WHERE DeveloperName = '[AgentName]'
   ```
   **Risk-class flag:** `AgentType = 'EinsteinServiceAgent'` (or a legacy `Type = 'Bot'` / `Type = 'ExternalCopilot'`) is the UI-built, planner-only, hand-patch-risk class (the WSA/Qiagen class). `AgentType` values like `AgentforceEmployeeAgent` / `Employee` / `ServicePlanner` are the other classes. **The enum is an empirical SDO/IDO mapping, not a guarantee** — a newer Agent-Script-authored service agent could also report `EinsteinServiceAgent` yet have editable source. So treat the SOQL result as the risk flag, then confirm with ONE retrieve used purely as a boolean:
   ```bash
   sf project retrieve start --json --metadata "AiAuthoringBundle:[AgentName]" --target-org {{ORG_ALIAS}} 2>&1 | head -40
   ```
   Retrieve **succeeds** (a `.agent`/AiAuthoringBundle lands on disk) → **editable source exists** (safe edit). Retrieve **fails** → **confirmed sourceless / UI-built** (route structural edits to Builder). Use success-vs-failure as the boolean — do NOT pattern-match the exact error code (the surface evolves monthly).
3. **Routing decision:**
   - **Net-new agent** → Agent Script path (sub-agent builds the `.agent` bundle from scratch). Proceed normally.
   - **Modify-existing WITH editable source** → version-safe Modify path. Proceed normally.
   - **Modify-existing, UI-built (no source), IN-PLACE tweak only** → planner XML edit is the legitimate path. Proceed to the Modify path.
   - **Modify-existing, UI-built (no source), STRUCTURAL add/move of topic or action** → **DO NOT hand-patch the planner.** Re-scope Phase 3: Scout deploys the backing flows/Apex only (the parts that have real source); the topic + action **wiring** is routed to the SE Manual Checklist ("Add topic '[X]' + action '[Y]' in Agent Builder — the agent is UI-built, so structural wiring must be done in the Builder wizard, which regenerates the action I/O schemas"). Record this split in `skipped` with reason "SE Manual Checklist — UI-built agent, structural wiring not source-editable." Surface it in the SE gate below so the SE sees the accurate partial scope.

Record the editability verdict in `discovery_notes` verbatim (e.g. `"Agentforce_Service_Agent: AiAuthoringBundle retrieve failed (AABNotFound) — UI-built, structural wiring routed to SE Manual."`).

**SE gate before spawning.** Enumerate from the spec verbatim — do not paraphrase action types. Pull `Backing Apex classes:` / `Backing actions:` / `Knowledge grounding:` fields from the spec's Agentforce section exactly as written. The SE must be able to see at decision time whether the plan is "no Apex" or "Apex fallback allowed."

> "About to deploy:
> - **Agent:** [agent api_name] ([subagent count] subagents: [list])
> - **Backing actions (from spec):** [enumerate verbatim — e.g. 'standard Get Records, standard Update Record, Knowledge grounding via Data Libraries; NO Apex in v1' OR 'Apex invocable LGInverterGetWarranty + standard Update Record']
> - **New Einstein Agent User:** `[expected username pattern]@[orgid].ext` will be created by `sf agent` CLI during publish (standard Agentforce procedure)
>
> Proceed? (yes/no)"

If the spec carries an explicit "no Apex" directive, add one extra line:
> "⚠️ Spec forbids Apex backing actions. If the sub-agent hits a standard-action failure during validate/preview, it will fall back to Apex and record the triggering error in `issues`. You'll see the deviation in the change log."

If no, record as skipped. If yes, run the Phase Prep Procedure for Phase 3. After it returns:
1. Check `smoke_test` in the output for pass/fail. **Check `smoke_test.action_invocation_confirmed`** — if `false` (or absent), the agent's hero action was NEVER confirmed to fire; report the agent to the SE as **"deployed but NOT validated — no action invocation confirmed"**, NOT as "Active/working," and carry that status into the change log and handover brief. A coherent conversation is not validation.
2. Surface `actions_unverified_in_preview` to the SE explicitly — these are the actions the sub-agent deployed but could not exercise in stateless preview. They are NOT smoke-test failures; they are verification gaps the SE must close manually in a live Messaging Session. If the list is non-empty, include it in the change log's Issues Encountered section and in the handover brief's SE checklist.
3. Cross-check `deployed.backing_actions` types against the spec. If the spec said "no Apex" and `backing_actions` contains any `type: ApexClass`, the sub-agent invoked the fallback path — verify `discovery_notes` or `issues` carries the triggering standard-action error. If it doesn't, flag as a deviation in the change log (the sub-agent skipped the evidence rule).

---

## Step 5b: Post-Deployment Execution Order Check

Read `${CLAUDE_PLUGIN_ROOT}/prompts/building/post-deployment-check.md` and execute the procedure. Flag findings in the change log.

---

## Step 6: Change Log, Lessons, and Done

### 6a: Write Change Log

Consolidate results from all phases into a single change log.
Use the template in `${CLAUDE_PLUGIN_ROOT}/prompts/building/change-log-template.md` (read it when writing the log).

The change log must include:
- Everything from all sub-agent reports (deployed, skipped, permission set, data, issues)
- Rollback commands from Phase 2 and Phase 3
- Which phases ran and which were skipped
- Any phases that FAILED validation (raw output preserved)
- **Docs Consulted** section — aggregate `docs_consulted` arrays from every sub-agent's JSON output, plus any orchestrator-level error-recovery consultations. If nothing was consulted, write "None — no unfamiliar errors encountered."

**Workspace cleanup (after the change log is written).** The change log is now the durable record of this deployment; the converted-retrieve scratch in `force-app/` has served its purpose. Sweep it clean (deny-rule-safe `find … -delete`, never `rm -rf` — see Step 5 Workspace Prep):

```bash
find "$HOME/claude-projects/sf-demo-scout/force-app/main/default" -mindepth 1 -delete 2>/dev/null || true
```

The `main/default/` skeleton is kept so the package dir stays valid. This is the clean-success-path hygiene that complements the start-of-run sweep (which is the safety net for crashed / interrupted prior runs).

### 6b: Propose Lessons

Read `${CLAUDE_PLUGIN_ROOT}/prompts/lessons-maintenance.md` and execute the "Propose Lessons (building)" section.

### 6c: Demo Handover Brief

**Do NOT output the brief until 6a and 6b are complete.**

Read `${CLAUDE_PLUGIN_ROOT}/prompts/building/handover-brief.md` for the format, then synthesize the brief. Output it to the terminal as plain text (no file written).

**Then offer the Slack handover canvas:**

1. Probe Slack MCP availability: bash `claude mcp list 2>/dev/null | grep -qE '^slack:.*✓ Connected' && echo OK || echo MISSING`.
   - On `MISSING`: skip silently to the notification (no prompt — nothing to offer).
   - On `OK`: proceed to step 2.
2. Ask the SE inline:
   > "Write the handover brief to a Slack canvas in your personal Slack? (y/n)"
   Wait for the reply. On `n` or silence: skip to the notification.
3. On `y`: call `mcp__slack__slack_create_canvas` with:
   - `title`: `Demo Handover — [Customer] — [YYYY-MM-DD]`
   - `content`: the same markdown brief you output to the terminal, reformatted for Canvas-flavored Markdown (plain headers, lists, links — no Slack-message syntax). The canvas lands in the SE's personal Slack; no channel targeting needed.
4. Capture the returned canvas link. Append one line to the terminal output AFTER the brief:
   ```
   📋 Slack canvas: [canvas URL] — refine before sharing with customer.
   ```
5. On any canvas-create error, surface one line: *"Canvas write failed: [reason]. Brief is still above."* Do not retry.

Then fire the notification:

```bash
osascript -e 'display notification "Deployment complete — check the handover brief." with title "SF Demo Scout — Done"'
```
