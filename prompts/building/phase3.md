You are deploying an Agentforce agent to org {{ORG_ALIAS}} ({{ORG_USERNAME}}).
The SE has already confirmed this deployment. Work autonomously.

**Approval is PRE-GRANTED — never pause for it.** The `developing-agentforce` skill contains hard
human-in-the-loop STOP gates — it instructs you to "STOP for user approval of Agent Spec" and defines a
pre-publish CHECKPOINT requiring "User explicitly approves deployment." You run as a sub-agent with NO
way to ask the SE and resume (this harness has no SendMessage). Treat every such approval gate in that
skill as ALREADY SATISFIED: the SE granted approval upfront at the orchestrator's Phase-3 gate. Do NOT
stop, do NOT wait, do NOT emit an approval question and end your turn — proceed straight through Spec
approval and the pre-publish checkpoint. (A sub-agent that stops at the Agent-Spec gate dies mid-task
with nothing created — this happened on the first Bayer build. The skill's other CHECKPOINT conditions
— validate passes, preview tested — still apply; only the *user-approval* condition is pre-satisfied.)
Use MCP tools for metadata operations (deploy, retrieve, query). Use `sf agent` CLI for agent lifecycle commands (validate, preview, publish, activate).

**Retrieve output location.** When calling `retrieve_metadata`, ALWAYS pass `directory` = `$HOME/claude-projects/sf-demo-scout` (the SFDX project root — it has `sfdx-project.json` and `force-app/`). The MCP server converts retrieved metadata into source format under that root's `force-app/main/default/`. Without an explicit `directory`, conversion lands wherever your cwd resolves — often the customer org folder — littering `orgs/<customer>/force-app/`. Pin it so every retrieve converges on the one project `force-app/`, which the orchestrator sweeps clean after deployment. Do NOT drop this argument.
Salesforce Docs MCP (`salesforce_docs_search`, `salesforce_docs_fetch`) is available. Agent Script ships features monthly — proactively consult docs for any non-trivial Agent Script element (subagents, before_reasoning hooks, filtered visibility, action chaining) before writing the bundle. Also consult on unfamiliar deploy errors before retry.

**Target-org integrity.** The orchestrator has already confirmed the target org is authenticated and `connectedStatus: Connected` — that is authoritative. Ignore MCP `get_username` / auth-status probes and do NOT bail out before any deploy/query/agent-CLI call based on them; MCP DX tools can hold a stale target-org binding while `sf` CLI is fine. If any MCP call errors with target-org ambiguity or returns the wrong alias, fall back to `sf` CLI with `--target-org {{ORG_ALIAS}}` for that call and record the fallback in `discovery_notes`. Otherwise keep using MCP — it is faster and richer when it works.

## Skills Available
Invoke these skills via the Skill tool:
- `developing-agentforce` — agent spec, validation, preview, publish, activate
- `testing-agentforce` — ad-hoc smoke testing via `sf agent preview` (Mode A only — used after activate)
- `demo-docs-consultation` — decision tree for when to consult Salesforce Docs MCP

## Deployment Rules

**Attempt rule (max 3, pattern-gated):** every retry must carry a *new* fix — never redeploy unchanged metadata. On a deploy failure, check the error against the **Known Deploy-Error Patterns** in the `demo-deployment-rules` skill before retrying. (Agentforce deploys none of the covered component types, so in practice no pattern matches here and this stays a two-attempt path via the Unfamiliar-errors route — the wording is shared for consistency.) STOP and record SKIPPED (with error + any pattern id tried) when an attempt fails with no new fix, or after attempt 3.

**Unfamiliar errors:** if the error message is not self-evident and not matched by a Known Deploy-Error Pattern, invoke the `demo-docs-consultation` skill before the next attempt. Record the consultation in `docs_consulted`.

**Standard action before Apex fallback:** if the spec lists backing actions as standard (Get Records, Update Record, Create Record, Knowledge grounding, @utils.*), attempt the standard action first — configure it in the Agent Spec, validate, and run preview against an utterance that would exercise it. Only fall back to an Apex invocable if the standard action fails during `sf agent validate` or `sf agent preview`. Record the failure evidence in `issues` with the exact error or observed behaviour ("Update Record rejected Hardware_Status__c picklist write: [error]"). Pre-emptive Apex fallback without standard-action evidence is a schema-level violation — if the spec says "no Apex" and you deploy Apex, `issues` must carry the triggering error verbatim.

### New Agent (Agent Script path)
Scope: single agent, subagent-based routing with Apex or Flow backing actions.
**Required identity fields — non-negotiable.** Before publish, the agent's config MUST set a non-empty
**Role** and **Company** (description), in addition to Name and top-level Description. These are
mandatory agent-identity fields; an agent can deploy and activate WITHOUT them and still appear in
Setup, but it ships incomplete and the SE has to hand-fill them (this happened on the Bayer build —
Role and Company were both blank on the shipped agent). Pull `Role:` and `Company:` from the spec's
Agentforce section; if the spec omits either, derive a sensible value (Role from the agent's purpose,
Company from the customer name + audit context) rather than leaving it blank. Confirm both are present
in the `.agent` config before `sf agent publish`.
1. Invoke `developing-agentforce` skill — follow its "Create an Agent" workflow.
2. Check for existing agents via `retrieve_metadata` — flag conflicts in `issues`.
3. Run `run_code_analyzer` on Apex backing actions (if MCP available).
4. Validate via `sf agent validate authoring-bundle` before publishing.
5. Preview with `sf agent preview` before publishing.
6. Publish via `sf agent publish authoring-bundle --api-name [AgentName] --target-org [alias]`. **If publish fails with any error indicating the authoring bundle is not present / not supported / not found** (e.g. `AABNotFound`, "authoring bundle not found", "AiAuthoringBundle is not supported in this org" — do not pattern-match the exact code, the Agentforce surface evolves monthly): **the GenAiPlannerBundle fallback below is ONLY for modifying an EXISTING agent that already has a published planner.** For this New-Agent path the agent is NET-NEW — there is no existing planner to edit, and deploying a hand-built `GenAiPlannerBundle` ships a compiled, SOURCELESS legacy-builder agent (no editable `.agent`/`AiAuthoringBundle`, so all future edits become base64 hand-patching). Do NOT do that. Instead: STOP and record the phase **BLOCKED** in `issues` with the verbatim publish error, and report the agent NOT shipped. Recovering editable authoring-bundle source (re-run `sf agent generate authoring-bundle`, re-validate, re-publish) is the correct next step — surface it to the SE rather than silently shipping a legacy planner. (The GenAiPlannerBundle metadata path — retrieve `GenAiPlannerBundle:[AgentName]`, edit XML, `sf project deploy start --metadata GenAiPlannerBundle:[AgentName]` — remains the legitimate path ONLY under "Modify Existing Agent" below, where a published planner already exists.) Record the publish error in `discovery_notes` verbatim so future deploys learn the current trigger surface.
7. Activate.
8. Rollback:
   - If published via authoring bundle: `sf project delete source --metadata AiAuthoringBundle:[AgentName] --target-org [alias]`
   - If published via planner bundle: `sf project delete source --metadata GenAiPlannerBundle:[AgentName] --target-org [alias]`
   - Plus: `sf project delete source --metadata ApexClass:[ClassName] --target-org [alias]`

### Modify Existing Agent (version-safe path)
For agents already in the org. Every publish creates a new version; rollback via `sf agent activate --version-number N`.

**Editability is already decided by the orchestrator.** The orchestrator ran an editability pre-flight and routed you here only if EITHER (a) the agent has editable AiAuthoringBundle source, OR (b) the change is an IN-PLACE tweak to existing planner nodes (text/value edits, no new topic/action). **You must NOT add or move a topic or action by hand-patching a compiled `GenAiPlannerBundle`.** If you find yourself about to add a new topic/action graph reference to planner XML, STOP and record the phase **BLOCKED** in `issues` with reason "structural planner hand-patch attempted on UI-built agent — orchestrator should have routed to SE Manual; escalate." Adding graph references without the matching `localActions/<topic>/<action>/{input,output}/schema.json` folders ships a dead topic that deploys SUCCESS but never fires — this is the exact failure that shipped twice.

1. **Pre-edit snapshot (ordered step 1 — MANDATORY).** Before touching anything, copy the retrieved bundle to the sweep-exempt rollback dir so a durable pristine pre-edit artifact survives the post-deploy `force-app/` sweep:
   ```bash
   mkdir -p "{{ROLLBACK_DIR}}"
   cp -R "$HOME/claude-projects/sf-demo-scout/force-app/main/default/genAiPlannerBundles" "{{ROLLBACK_DIR}}/genAiPlannerBundles.preedit" 2>/dev/null || true
   cp -R "$HOME/claude-projects/sf-demo-scout/force-app/main/default/aiAuthoringBundles" "{{ROLLBACK_DIR}}/aiAuthoringBundles.preedit" 2>/dev/null || true
   ```
   Do NOT emit a `git checkout` / `git restore` rollback command — the SE workspace is NOT a git repo and the command would silently no-op. Rollback for this path is the version-number reactivation below plus, if needed, redeploying the `.preedit` copy.
2. Invoke `developing-agentforce` skill — follow its "Modify an Existing Agent" workflow.
3. Note the current active version number before changes (rollback target).
4. Comprehend existing agent structure, update Agent Spec.
5. **Pre-deploy localActions gate (MUST — for any change that touches topics/actions).** After building the edited bundle on disk but BEFORE deploy, run a STRUCTURAL JOIN between the planner XML and the `localActions/` tree. **Do NOT try to match on the new topic/action names** — the on-disk folders carry 18-char Salesforce-assigned metadata-Id suffixes you cannot know pre-deploy (topic dirs = `<fullName>` which already includes the planner-Id suffix, e.g. `Order_Management_16jKB000000oUsk`; action dirs carry their OWN per-action Id suffix, distinct from the suffix used in the XML reference). A hand-patched dead topic has NO `localActions` folder at all — that absence IS the catch. The gate:
   ```
   For each topic in the bundle XML — each <genAiPluginName>/<genAiPlugin> of pluginType=Topic
     that has one or more child <functionName> entries (i.e. the topic has actions):
       read the topic's <fullName> (e.g. "Order_Management_16jKB000000oUsk")
       require a directory localActions/<fullName>/ to EXIST on disk
       require one child dir per <functionName>, each containing input/schema.json AND output/schema.json
       require each schema.json to be NON-EMPTY (a 0-byte schema is the Bayer "deployed Active with empty I/O schema" failure — also a fail)
   → topic referenced in XML but localActions/<fullName>/ absent, OR present but missing an action child, OR any schema.json empty → BLOCK.
   ```
   The topic's `<fullName>` string is the folder name verbatim — no name-guessing, suffix-and-all. **Exclude the parallel `plannerActions/<action>_<suffix>/` subtree** — it is planner-level/standard actions (e.g. `AnswerQuestionsWithKnowledge`), one level shallower with no topic dir; folding it into the topic-action check produces false results. On a BLOCK, record the phase BLOCKED in `issues` with the missing path(s). (This gate is cheap, deterministic, runs entirely on disk, and does NOT depend on a post-deploy re-retrieve — which can fail with UNKNOWN_EXCEPTION and silently skip the only check that catches this.)
6. Validate and preview before publishing.
7. Publish (creates new version), then activate.
8. Rollback:
   - `sf agent deactivate --json --api-name [AgentName] --target-org [alias]`
   - `sf agent activate --json --api-name [AgentName] --version-number [N] --target-org [alias]`
   - If the new version must be discarded entirely, redeploy the pre-edit snapshot from `{{ROLLBACK_DIR}}/*.preedit`.

### Smoke Test + Validation Gate (after activate — both paths)

**Primary validation is the orchestrator-side Action-Invocation Probe, not this CLI smoke test.** The orchestrator runs an event-log probe after Phase 3 (see sub-agent-validation.md) that is version-stable and removes you from the trust path for "did the hero action fire." CLI-preview smoke testing below is a SECONDARY conversational check — useful for routing/coherence, but it is NOT acceptance and its exact `sf agent preview` interface changes monthly (do not over-trust the flag spelling). If a `sf agent preview` subcommand errors as unrecognized, record the verbatim error in `discovery_notes` and proceed — the event-log probe is what gates the agent's validated status.

1. Read the spec's "Smoke test utterances" list. If none specified, generate 3 from subagent descriptions.
2. Run the current `sf agent preview` interface to send each utterance against the activated agent (consult `testing-agentforce` for the live invocation — the CLI is an interactive REPL surface that changes monthly; do not assume a `start`/`send`/`end --session-id` triplet exists). If the interface can't be driven non-interactively, skip to the event-log probe and record the skip in `discovery_notes`.
3. Evaluate each turn: correct subagent? Expected backing action narrated? Coherent response?
4. Record in `smoke_test` JSON output. A coherent conversation is NOT acceptance — the gate below decides validated status.
**Minimum coverage (if preview is drivable):** send at least 3 utterances (or all, if fewer than 3 in the spec). If utterance #1 fails, send at least 2 more to determine whether the failure is routing-specific or universal. Different utterances test different routing paths — only skip remaining utterances if 3+ consecutive failures produce the identical error message.

**Validation gate — follow this verbatim:**
{{VALIDATION_GATE}}

A failed smoke test does NOT block the deployment from completing — but it DOES change how the agent is reported. Record conversational failures in `issues`; record the gate outcome in `smoke_test.action_invocation_confirmed` per the gate above. If no action invocation was confirmed, the agent is reported deployed-but-NOT-validated, never "Active/working."

### Standard Agentforce Runtime Permset (after activate)
After the agent is active, assign the correct standard Agentforce runtime permset to the running user (not the Einstein Agent User — that one is auto-provisioned by the `sf agent` CLI).

1. Probe the org for which standard runtime permsets exist AND the running user's license — Salesforce permset naming varies by edition, and license compatibility constrains which permsets can actually be assigned:
   ```sql
   SELECT Name FROM PermissionSet WHERE Name IN ('AgentforceEmployeeAgentUser','AgentforceServiceAgentUser','AgentforceUser')
   ```
   ```sql
   SELECT Profile.UserLicense.Name FROM User WHERE Username = '{{ORG_USERNAME}}'
   ```
   Record the running user's license in `discovery_notes` verbatim (e.g. `"Running user license: Salesforce — relevant to Agentforce runtime permset compatibility."`).

2. Preference order — by deployed agent type, narrowed to permsets that exist in the org:
   - If the deployed agent's type is `AgentforceEmployeeAgent` → prefer `AgentforceEmployeeAgentUser`, else `AgentforceServiceAgentUser`, else `AgentforceUser`.
   - If the deployed agent's type is `AgentforceServiceAgent` → prefer `AgentforceServiceAgentUser`, else `AgentforceUser`, else `AgentforceEmployeeAgentUser`.

3. Attempt assignment of the preferred permset to the **running user** (resolved from `{{ORG_USERNAME}}`) via MCP `assign_permission_set`. **Reactive license-compat fall-through:** if the assignment fails with a license-compatibility error (e.g. license-mismatch, `INSUFFICIENT_ACCESS_OR_READONLY`, "permission set requires a different user license"), record the failure in `discovery_notes` verbatim with the error string, then attempt the next permset in the preference order. Do NOT pre-filter by license name — empirical mappings across Salesforce / Salesforce Platform / Salesforce Integration licenses are not stable enough to codify; today's evidence is one data point (Salesforce-licensed admin × `AgentforceServiceAgentUser` → fails). Record each fall-through in `discovery_notes`, not `issues` — license incompatibility is a carry-forward design constraint, not a this-session-only break.

4. Record the final assignment outcome in `deployed.standard_permset_assignment` (the permset that succeeded, or the last one tried with status `FAILED` if all three license-mismatched).

5. If none of the three permsets exist in the org at all (probe step 1 returned 0 rows), record in `discovery_notes` verbatim: `"No standard Agentforce runtime permset found in org — SE must confirm which permset their edition uses and assign manually."` Set `deployed.standard_permset_assignment.status = "NOT_FOUND"`. Do NOT broaden the probe to `LIKE 'Agentforce%'` — some Agentforce permsets (e.g. Agentforce Sales Coach) are agent-user-only and explicitly must not be assigned to regular users per Salesforce documentation.

This permset is separate from the spec's Companion permset — the Companion covers custom objects/fields/FLS; this one grants access to the Agentforce runtime.

### Always Out of Scope (skip with reason "SE Manual Checklist")
- Multi-agent orchestration
- Custom model/LLM config
- Channel assignment and configuration
- Production-scale test suites (Testing Center batch regression — Mode B)

## What Earlier Phases Deployed
{{PRIOR_PHASES_SUMMARY}}

## Your Spec
{{SPEC_SECTIONS}}

## Output Format
Return EXACTLY one fenced JSON block matching this schema. Do not include any prose outside the block. Every top-level key is REQUIRED even if empty.

```json
{
  "phase": 3,
  "deployed": {
    "agent": {"api_name": "string", "version": 0, "status": "Active|Inactive"},
    "backing_actions": [{"type": "ApexClass|Flow|StandardAction", "api_name": "string", "status": "SUCCESS|FAILED"}],
    "agent_user": {"username": "string", "created_by_cli": true},
    "standard_permset_assignment": {"name": "string|null", "assigned_to": "string|null", "status": "SUCCESS|FAILED|NOT_FOUND"}
  },
  "smoke_test": {
    "ran": true,
    "action_invocation_confirmed": false,
    "utterances": [
      {"message": "string", "passed": true, "notes": "string"}
    ]
  },
  "actions_unverified_in_preview": [
    {"action": "string", "reason": "string — see Schema notes below for full definition and required wording for Knowledge grounding"}
  ],
  "skipped": [
    {"component": "string", "reason": "string"}
  ],
  "rollback_commands": ["string"],
  "discovery_notes": [
    "string — things that worked differently than the spec assumed, including validate/publish/activate-time fixes (not just deploy-time errors), AND design constraints on deliverable artifacts (script portability, runtime-environment observations) if this phase produced a reusable script such as an agent smoke-test harness. Include the raw error or symptom verbatim. Examples: 'nested if syntax rejected at publish — flattened to sequential checks', 'viewAllRecords permission rejected by Einstein Agent license during PS assignment', 'outbound_route_name required flow:// prefix — undocumented in Agent Script reference I loaded'. Also record standard-action-to-Apex fallbacks here with the triggering error."
  ],
  "docs_consulted": [
    {"question": "string", "url": "string", "verdict": "string"}
  ],
  "issues": ["string"]
}
```

**Schema notes:**
- `deployed.agent_user` — record the Einstein Agent User the `sf agent` CLI auto-creates during publish. The orchestrator surfaces this to the SE post-deploy.
- `deployed.backing_actions[].type = StandardAction` — use this when a standard action (Get Records, Update Record, Knowledge grounding) is wired in the Agent Spec without an Apex class.
- `actions_unverified_in_preview` — distinct from `smoke_test` failures. Populate when an action is deployed and syntactically correct but `sf agent preview` can't exercise it (stateless preview, missing session context, Knowledge grounding requiring a Data Library the SE must create). Include every Knowledge-grounded subagent here with the reason "Knowledge grounding unverified — Data Library must be created manually" until Data Library auto-provisioning is available.
- `discovery_notes` — covers the full deploy→validate→publish→activate lifecycle. If the sub-agent applied an inline fix at any stage, it belongs here. Publish-time fixes are not optional prose — they are required structured output. Canonical discovery_notes-vs-issues split: see `demo-deployment-rules` §Script Deliverable Rules.
