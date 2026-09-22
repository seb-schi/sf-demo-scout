You are deploying an Agentforce agent to org {{ORG_ALIAS}} ({{ORG_USERNAME}}).
The SE has already confirmed this deployment. Work autonomously.

**Scope approval is PRE-GRANTED; host refusals still stop the operation.** The `agentforce-generate` skill contains hard
human-in-the-loop STOP gates ("STOP for user approval of Agent Spec"; a pre-publish "User explicitly
approves deployment" CHECKPOINT). You run as a sub-agent with NO way to ask the SE and resume (no
SendMessage in this harness), and a stop there dies mid-task with nothing created. Treat every such
approval gate as ALREADY SATISFIED — the SE approved upfront at the orchestrator's Phase-3 gate — and
proceed straight through Spec approval and the pre-publish checkpoint. The skill's *other* CHECKPOINT
conditions (validate passes, preview tested) still apply; only the user-approval condition is
pre-satisfied.
Use MCP tools for metadata operations (deploy, retrieve, query). Use `sf agent` CLI for agent lifecycle commands (validate, preview, publish, activate).

{{OPERATION_SAFETY}}

**Writer-owned project:** `{{PROJECT_ROOT}}`. The parent has prepared it. Verify
its ownership receipt before use. Set each CLI call's working directory and
`retrieve_metadata.directory` to this exact project; all relative `force-app/`
paths below are inside it. Use its source paths for deployment; retain the project.
Salesforce Docs MCP (`salesforce_docs_search`, `salesforce_docs_fetch`) is available. Agent Script ships features monthly — proactively consult docs for any non-trivial Agent Script element (subagents, before_reasoning hooks, filtered visibility, action chaining) before writing the bundle. Also consult on unfamiliar deploy errors before retry.

{{REAUTHOR_FROM_PLANNER}}

**Target-org integrity.** The orchestrator has already confirmed the target org is authenticated and `connectedStatus: Connected` — that is authoritative. Ignore MCP `get_username` / auth-status probes and do NOT bail out before any deploy/query/agent-CLI call based on them; MCP DX tools can hold a stale target-org binding while `sf` CLI is fine. Only for a technical target-binding error, after ruling out a permission/policy rejection and confirming the intended target, fall back to `sf` CLI with `--target-org {{ORG_ALIAS}}` for that call and record the fallback in `discovery_notes`. Otherwise keep using MCP — it is faster and richer when it works.

## Binding Build Scope

{{BUILD_SCOPE}}

This block is binding during authoring, deployment, retries, and return reporting.
Explicit no-Apex is binding in every mode. Showtime E4 permits standard actions only
and never permits backing Apex fallback. Showtime E3 permits its named Apex only in
Phase 2; E3 never selects Phase 3 or authorizes an agent backing action. Out-of-scope
or excluded work remains BLOCKED.

{{VENDOR_COMPATIBILITY}}

## Skills Available
Invoke these skills via the Skill tool:
- `agentforce-generate` — agent spec, validation, preview, publish, activate
- `agentforce-test` — official agent testing after activate: builds + runs a Testing Center suite (Mode B: `sf agent test create/run/results`) from the spec's Agent test cases, with Mode A `sf agent preview` as fallback. Authoritative for the test-spec YAML schema + Testing Center metric landmines.
- `demo-docs-consultation` — decision tree for when to consult Salesforce Docs MCP
{{EXTERNAL_SKILLS}}

{{IMPORTED_ASSETS}}

## Deployment Rules

**Attempt rule (max 3, pattern-gated):** every retry must carry a *new* fix — never redeploy unchanged metadata. On a deploy failure, check the error against the **Known Deploy-Error Patterns** in the `demo-deployment-rules` skill before retrying. (Agentforce deploys none of the covered component types, so in practice no pattern matches here and this stays a two-attempt path via the Unfamiliar-errors route — the wording is shared for consistency.) STOP and record FAILED (with error + any pattern id tried) when an attempt fails with no new fix, or after attempt 3.

**Unfamiliar errors:** if the error message is not self-evident and not matched by a Known Deploy-Error Pattern, invoke the `demo-docs-consultation` skill before the next attempt. Record the consultation in `docs_consulted`.

**Standard action and bounded fallback:** attempt every spec-named standard action
first, then validate and preview an exercising utterance. Explicit no-Apex and
Showtime E4 forbid backing Apex even after failure. Showtime E3 never selects this
phase and cannot authorize an agent backing action. For an Ordinary build, fallback
is allowed only when BUILD_SCOPE
names it, the approved spec names the exact Apex class/action and target semantics,
and the frozen expected-work ledger already contains matching artifact/action
obligations and acceptance. Generic permission is insufficient. Record exact
failure evidence from `sf agent validate` or `sf agent preview`; do not change the
hero-action identity or expected state. If these conditions are absent, report the
attempted standard action FAILED with exact failure evidence, and any unattempted
forbidden/prerequisite fallback work BLOCKED for spec revision. Do not author Apex
or change the frozen expected-work ledger.

**Email-to-Case agent handoff:** consume the probe evidence and prerequisite status
in the **What Earlier Phases Deployed** section below; do not presume conversation context. The orchestrator
has already run the absolute `check-agent-email-capability.sh` probe for each
approved email-agent requirement. Act only on an exit-0 requirement with an exact
`routingName` → Agent API name link and VERIFIED base Email-to-Case prerequisite.
Exit 3 (not entitled), other nonzero probe errors, and missing/ambiguous links are
BLOCKED for this obligation; they never block independently verified base
Email-to-Case settings. For an email agent, omit the Service Customer Verification
topic and include an Escalation subagent so a case can reach a human. Agent creation
does not complete channel integration. Report manual channel assignment as BLOCKED
unless the injected External Skills block contains the exact installed and
explicitly approved channel skill for this obligation; never install or infer one.

### New Agent (Agent Script path)
Scope: single agent, subagent-based routing with approved standard, Apex, or Flow backing actions.
**Required identity fields — non-negotiable.** Before publish, the agent's config MUST set a non-empty
**Role** and **Company** (description), in addition to Name and top-level Description. These are
mandatory agent-identity fields; an agent can deploy and activate WITHOUT them and still appear in
Setup, but it ships incomplete and the SE has to hand-fill them (this happened on an early customer build —
Role and Company were both blank on the shipped agent). Pull `Role:` and `Company:` from the spec's
Agentforce section; if the spec omits either, derive a sensible value (Role from the agent's purpose,
Company from the customer name + audit context) rather than leaving it blank. Confirm both are present
in the `.agent` config before `sf agent publish`.
1. Invoke `agentforce-generate` skill — follow its "Create an Agent" workflow. **If the spec's Agentforce section flags an advanced capability (multi-agent orchestration, Enhanced Chat v2, or Lightning types / forms in chat), read `${CLAUDE_PLUGIN_ROOT}/prompts/building/agentforce-advanced-capabilities.md` first** — it splits the build-time metadata Scout authors (connected_subagent blocks, connection blocks, LightningTypeBundle + LWC with the `@api value` contract, `complex_data_type_name` declarations) from the UI-wiring + live-verification the SE handles, with the verbatim compiler-rejection gotchas. **Before declaring any action's inputs/outputs, retrieve the live backing interfaces so authored I/O matches the real schema** — `sf project retrieve start -m Flow:<name>` (read `<variables>` name / isInput / isOutput / dataType) and `sf project retrieve start -m ApexClass:<name>` (read `@InvocableVariable` names / types). Two recurring mismatches the publish/commit compiler rejects: (1) a Flow input often carries a prefix (e.g. `inp_<Name>`) — bind the exact name, not a guessed camelCase; (2) a Flow **Currency** output must be declared `object` with `complex_data_type_name: "lightning__currencyType"`, not `number`. Matching up front de-risks both headless publish and (on a 404 instance) the Builder UI commit (see step 6b).
2. Check for existing agents via `retrieve_metadata` — flag conflicts in `issues`.
3. Run `run_code_analyzer` on Apex backing actions (if MCP available).
4. Validate via `sf agent validate authoring-bundle` before publishing.
5. Preview with `sf agent preview` before publishing.
6. Publish via `sf agent publish authoring-bundle --api-name [AgentName] --target-org [alias] --skip-retrieve`. **The `--skip-retrieve` flag is mandatory, not optional** (documented: `agent-dx-nga-publish.html`). Publish runs 5 steps: validate compile → commit the new version server-side (Bot/BotVersion/GenAiPlannerDefinition) → **retrieve the new metadata back to the DX project** → populate the bundle `<target>` → deploy the AiAuthoringBundle member. The retrieve-back step has a known CLI crash (`TypeError: Cannot read properties of undefined (reading 'map')` at `scriptAgentPublisher.js:187`) that fires AFTER the version is committed but BEFORE the bundle member deploys — leaving an **orphaned version**: a `GenAiPlannerDefinition` with no matching AiAuthoringBundle member, invisible in Builder's version dropdown and NOT deletable via Tooling API (`DELETE_FAILED: setup object in use`). `--skip-retrieve` skips the crash-prone step entirely; retrieve the bundle separately (below) if you need the updated `<target>`. **Orphan detection (before + after publish):** compare the two lists — `sf data query -q "SELECT DeveloperName, VersionNumber FROM GenAiPlannerDefinition WHERE BotId IN (SELECT Id FROM Bot WHERE DeveloperName='[AgentName]') ORDER BY VersionNumber" --target-org [alias]` vs `sf org list metadata --metadata-type AiAuthoringBundle --target-org [alias]` (AiAuthoringBundle is Metadata-API-only, NOT a queryable sObject). Any planner version with no `[AgentName]_N` bundle member is an orphan — record it in `discovery_notes` (verbatim version numbers), do NOT attempt Tooling-API cleanup (not fixable that way; the only reliable route is nuke-and-rebuild, out of scope for demo prep). If a publish crashes at retrieve-back, re-run with `--skip-retrieve` to land the missing bundle member; do NOT retry without the flag. **If publish fails with any error indicating the authoring bundle is not present / not supported / not found** (e.g. `AABNotFound`, "authoring bundle not found", "AiAuthoringBundle is not supported in this org" — do not pattern-match the exact code, the Agentforce surface evolves monthly): **the GenAiPlannerBundle fallback below is ONLY for modifying an EXISTING agent that already has a published planner.** For this New-Agent path the agent is NET-NEW — there is no existing planner to edit, and deploying a hand-built `GenAiPlannerBundle` ships a compiled, SOURCELESS legacy-builder agent (no editable `.agent`/`AiAuthoringBundle`, so all future edits become base64 hand-patching). Do NOT do that. Instead: STOP and record the phase **BLOCKED** in `issues` with the verbatim publish error, and report the agent NOT shipped. Recovering editable authoring-bundle source (re-run `sf agent generate authoring-bundle`, re-validate, re-publish) is the correct next step — surface it to the SE rather than silently shipping a legacy planner. (The GenAiPlannerBundle metadata path — retrieve `GenAiPlannerBundle:[AgentName]`, edit XML, `sf project deploy start --metadata GenAiPlannerBundle:[AgentName]` — remains the legitimate path ONLY under "Modify Existing Agent" below, where a published planner already exists.) Record the publish error in `discovery_notes` verbatim so future deploys learn the current trigger surface.
6b. **SFAP publish-route 404 (per-instance provisioning gap) — DISTINCT from step 6's `AABNotFound` branch.** If publish fails specifically with an **empty-body HTTP 404 / `AgentApiNotFound` on the `/einstein/ai-agent/v1.1/authoring/agents` (or `/…/agents/{botId}/versions`) resource** — AFTER `sf agent validate` and `sf agent preview` succeeded (i.e. compile `/authoring/scripts` works, so the bundle IS valid) — this is NOT the `AABNotFound` "bundle not supported" case above and the re-generate-source remedy does NOT apply (re-generating loops forever against an unrouted resource). It is a per-instance SFAP provisioning gap on this org instance; UI Commit works, `sf project deploy` lands source but does NOT compile, and the fix is a Support case citing the instance ID. Do NOT loop re-generate, do NOT ship a sourceless `GenAiPlannerBundle`, do NOT `sf project deploy` the bundle as a publish substitute (source-only — proven not to compile). Instead: (a) preserve the COMPLETE validated authoring bundle using the mandatory durable-recovery procedure below; (b) record in `discovery_notes` VERBATIM the failing endpoint, the empty-body 404 status, and the org **instance ID** (from `sf org display` / the org's `instanceName`) — this is the escalation evidence; (c) set `deployed.agent.status` to `NeedsUICommit` (see Output Format) and report the agent **authored + validated, NOT live**; (d) point the SE to the go-live runbook: `${CLAUDE_PLUGIN_ROOT}/prompts/building/agent-ui-commit-runbook.md` (Builder UI New Draft → merge real topics into the template shell → reconcile action I/O → Commit → activate). Frame this as a known per-instance platform gap (ref #agentforce-dx), NOT a Scout failure.

**Durable recovery for step 6b (before returning).** Copy the whole
`aiAuthoringBundles/[AgentName]/` directory, including the `.agent`, bundle
metadata, and nested schemas/local actions. A compiled planner is not a substitute
and is not expected for this unpublished agent. Run with the injected absolute
helper and rollback paths:

```bash
python3 "{{ASSET_HELPER}}" preserve \
  --source-root "{{PROJECT_ROOT}}/force-app/main/default" \
  --rollback-dir "{{ROLLBACK_DIR}}" --kind agent-recovery \
  --path "aiAuthoringBundles/[AgentName]"
```

Require exit 0. The helper uses a unique directory and verifies complete paths
and content, so separate attempts never overwrite prior recovery bundles. Set
`deployed.agent.recovery` to `status: verified`, the returned absolute `artifact`,
`bundle_path: <artifact>/source/aiAuthoringBundles/[AgentName]`, and the absolute
`original_path` in scratch; `error: null`. Include the real durable bundle path
in `discovery_notes` and the runbook handover. Keep the preserved copy immutable.
On ANY copy/verification/helper error, STOP this phase's work, keep the original,
set recovery `status: failed` with the original path + error (`artifact` and
`bundle_path` null), and record **BLOCKED — recovery preservation; DO NOT CLEAN
SCRATCH** in `issues`. Keep agent status `NeedsUICommit` (not live); never claim
its blueprint is preserved until verification succeeds. The orchestrator must
independently verify before cleanup.

7. Activate. (Skip if step 6b set `NeedsUICommit` — there is no headless-published version to activate; activation happens in the runbook after UI Commit.)
8. Rollback:
   - If published via authoring bundle: `sf project delete source --metadata AiAuthoringBundle:[AgentName] --target-org [alias]`
   - If published via planner bundle: `sf project delete source --metadata GenAiPlannerBundle:[AgentName] --target-org [alias]`
   - Plus: `sf project delete source --metadata ApexClass:[ClassName] --target-org [alias]`

### Modify Existing Agent (version-safe path)
For agents already in the org. Every publish creates a new version; rollback via `sf agent activate --version N`. Use `--version` with an explicit API name and target org in this Scout path, even if a loaded reference uses the legacy `--version-number` spelling. The [current CLI contract](https://developer.salesforce.com/docs/platform/salesforce-cli-reference/guide/cli_reference_agent_activate.html) requires explicit version selection for a deterministic rollback.

The parent's preflight used a separate project. `PRIOR_PHASES_SUMMARY` supplies its
verified transfer artifact, exact members and successful staging paths in this
worker's project. Require that handoff and complete source before step 1; never
look in shared scratch or edit the parent's retrieval/immutable artifact.

**Editability is already decided by the orchestrator.** The orchestrator ran an editability pre-flight and routed you here only if EITHER (a) the agent has editable AiAuthoringBundle source, OR (b) the change is an IN-PLACE tweak to existing planner nodes (text/value edits, no new topic/action). **You must NOT add or move a topic or action by hand-patching a compiled `GenAiPlannerBundle`.** If you find yourself about to add a new topic/action graph reference to planner XML, STOP and record the phase **BLOCKED** in `issues` with reason "structural planner hand-patch attempted on UI-built agent — orchestrator should have routed to SE Manual; escalate." Adding graph references without the matching `localActions/<topic>/<action>/{input,output}/schema.json` folders ships a dead topic that deploys SUCCESS but never fires — this is the exact failure that shipped twice.

1. **Pre-edit snapshot (ordered step 1 — MANDATORY).** Before invoking the modify workflow or editing any source, preserve the exact retrieved bundle directories selected by the orchestrator's pre-flight. Use the actual retrieved names, including version/Id suffixes; never select the whole type folder or guess a missing bundle. For editable source preserve its `aiAuthoringBundles/<member>`; for an in-place planner edit preserve its `genAiPlannerBundles/<member>`. If both families will be edited, include both exact members in the same command with repeated `--path` arguments. An unused absent family needs no invented placeholder, but a missing required source BLOCKS the edit.
   ```bash
   python3 "{{ASSET_HELPER}}" preserve \
     --source-root "{{PROJECT_ROOT}}/force-app/main/default" \
     --rollback-dir "{{ROLLBACK_DIR}}" --kind agent-preedit \
     --path "[exact retrieved bundle-type/member selected for this edit]"
   ```
   Require exit 0, then run `python3 "{{ASSET_HELPER}}" verify --artifact "[returned artifact]"` and require exit 0. The helper creates a unique immutable snapshot with a verified path/hash manifest. Record `deployed.agent.preedit_snapshot` with `status: verified` and the actual returned `artifact`, `source`, and `paths`; `error: null`. Keep the first verified pre-edit snapshot for this build: a deployment retry must reuse and reverify it, never replace it with already-edited source. On missing source, copy or verification failure, STOP before mutation; record `status: failed`, the exact selectors/error and **BLOCKED — pre-edit preservation; DO NOT CLEAN SCRATCH**. Never suppress a failed copy or report a snapshot based on directory existence.

   Do NOT emit `git checkout` / `git restore` — the SE workspace is not a git repo. The primary org rollback remains the recorded active-version reactivation below. Any file-level restore must first verify the recorded artifact, copy its exact member to a disposable restore project without changing the snapshot, and redeploy that member only. Record the actual source/member path, never a `*.preedit` wildcard.
2. Record the current active version number before invoking any modify workflow (rollback target). If it cannot be established, stop and report the missing rollback target before mutation.
3. Invoke `agentforce-generate` skill — follow its "Modify an Existing Agent" workflow using the already verified snapshot and recorded rollback target.
4. Comprehend existing agent structure, update Agent Spec.
5. **Pre-deploy source-specific validation (MUST).** For Agent Script / AiAuthoringBundle source, run the Agent Script authoring validation; absence of a compiled `localActions` tree is not a failure. Only when the source is an already realized compiled `GenAiPlannerBundle` and the in-place change touches existing topic actions, run the STRUCTURAL JOIN below between planner XML and `localActions/`. **Do NOT try to match on topic/action display names** — compiled folders carry Salesforce-assigned metadata-Id suffixes. A hand-patched dead compiled topic has no matching `localActions` folder. The compiled-only gate:
   ```
   For each topic in the bundle XML — each <genAiPluginName>/<genAiPlugin> of pluginType=Topic
     that has one or more child <functionName> entries (i.e. the topic has actions):
       read the topic's <fullName> (e.g. "Order_Management_16jKB000000oUsk")
       require a directory localActions/<fullName>/ to EXIST on disk
       require one child dir per <functionName>, each containing input/schema.json AND output/schema.json
       require each schema.json to be NON-EMPTY (a 0-byte schema is the "deployed Active with empty I/O schema" failure seen on an early customer build — also a fail)
   → topic referenced in XML but localActions/<fullName>/ absent, OR present but missing an action child, OR any schema.json empty → BLOCK.
   ```
   The topic's `<fullName>` string is the folder name verbatim — no name-guessing, suffix-and-all. **Exclude the parallel `plannerActions/<action>_<suffix>/` subtree** — it is planner-level/standard actions (e.g. `AnswerQuestionsWithKnowledge`), one level shallower with no topic dir; folding it into the topic-action check produces false results. On a BLOCK, record the phase BLOCKED in `issues` with the missing path(s). (This gate is cheap, deterministic, runs entirely on disk, and does NOT depend on a post-deploy re-retrieve — which can fail with UNKNOWN_EXCEPTION and silently skip the only check that catches this.)
6. Validate and preview before publishing.
7. Publish with `sf agent publish authoring-bundle --api-name [AgentName] --target-org [alias] --skip-retrieve` (creates a new version), then activate. **`--skip-retrieve` is mandatory** — it avoids the retrieve-back CLI crash that orphans a version (a committed `GenAiPlannerDefinition` with no AiAuthoringBundle member; see New-Agent step 6 for the detection probe and why Tooling-API cleanup does not work). Run the before/after orphan probe from step 6 here too.
8. Rollback:
   - `sf agent deactivate --json --api-name [AgentName] --target-org [alias]`
   - `sf agent activate --json --api-name [AgentName] --version [N] --target-org [alias]`
   - If a source restore is needed, verify `preedit_snapshot.artifact`, then restore/redeploy the exact recorded `preedit_snapshot.source` + member path. Redeployment is not proof that the new published version was deleted; report version disposition separately.

### Smoke Test + Validation Gate (after activate — both paths)

**Service Agent prerequisite (ordering).** If the deployed agent is an `AgentforceServiceAgent`,
complete BOTH the "Standard Agentforce Runtime Permset" AND the "Running-User Backing-Action Access"
sections below BEFORE trusting any smoke-test or independent current-test result — a Service Agent runs
as a dedicated running user with NO access to your backing actions until those grants land, so a
validation run first is a guaranteed false red (`NO_USER_ACCESS`, no side-effect). Employee Agents
(logged-in user) need neither grant and this ordering does not apply.

**Primary validation is the orchestrator's independent current-test assessment, not this CLI smoke test.** After Phase 3, the orchestrator applies the canonical validation gate from expected ledger obligations (see sub-agent-validation.md), binds evidence to the independently read-back deployed version and selected session+turn or job+case, and checks exact behavior. It may use a saved live preview trace, exact job/case trace, or described and correlated event logs. CLI-preview smoke testing below is a SECONDARY conversational check — useful for routing/coherence, but it is NOT acceptance and its exact `sf agent preview` interface changes monthly (do not over-trust the flag spelling). If a preview subcommand errors as unrecognized, record the verbatim error in `discovery_notes`; never replace the independent assessment with the worker boolean.

1. **Build the official test suite from the spec.** Read the spec's "Agent test cases" table and write a `test-spec.yaml` in the official `sf agent test` format — delegate the exact schema to the `agentforce-test` skill (its `basic-test-spec.yaml` + `guardrail-test-spec.yaml` assets are authoritative; do NOT hand-invent field names). Map each row: `utterance` / `expectedTopic` / `expectedActions` (Level-2 invocation names, flat list, superset match) / `expectedOutcome`. If the spec has no table (older spec) or no rows, derive 3 cases from subagent descriptions and treat them as happy-path. **Metric landmines — do NOT ignore:** never attach `instruction_following` (crashes Testing Center UI), `conciseness` (returns score 0), or `completeness` (penalizes routing/deflection agents); rely on `expectedOutcome` (LLM-as-judge) for correctness and guardrail rows.
2. **Run the suite (Mode B — Testing Center).** `sf agent test create --json --spec test-spec.yaml --api-name [Suite] -o [alias]`, then `sf agent test run --json --api-name [Suite] --wait 10 --result-format json -o [alias]`, then fetch results with `sf agent test results --json --job-id [runId] -o [alias]` (use `--job-id` from the run output, NEVER `--use-most-recent`). Consult `agentforce-test` for the current flag spelling — the CLI surface changes monthly. If `sf agent test` is unavailable or errors, record the verbatim error in `discovery_notes`, fall back to a Mode A `sf agent preview` conversational check, and note the fallback.
3. **Judge against the official assertions, not an inferred outcome.** A case PASSES when its `expectedTopic`/`expectedActions`/`expectedOutcome` assertions pass in the run results. For guardrail/off-topic rows (empty `expectedTopic`), pass = the `expectedOutcome` LLM-judge confirms the agent declined/deflected; a confident off-domain answer is a FAILURE. Filter the known false-negative: a `topic_assertion` FAILURE on a guardrail row with empty `expectedTopic` is spurious (empty assertion XML) — do not count it.
4. Record per-case results in `smoke_test.utterances` (carry `expectedTopic`/`expectedActions`/`expectedOutcome`/`passed`/`mode`). A green suite is NOT full acceptance on its own. The orchestrator's independently correlated current-test assessment decides each action-bearing ledger item; Mode B runs alongside it and never replaces it.
**Minimum coverage (if preview is drivable):** send at least 3 utterances (or all, if fewer than 3 in the spec). If utterance #1 fails, send at least 2 more to determine whether the failure is routing-specific or universal. Different utterances test different routing paths — only skip remaining utterances if 3+ consecutive failures produce the identical error message.

**Validation gate — follow this verbatim:**
{{VALIDATION_GATE}}

A failed smoke test does not block deployment from completing. Record conversational failures in `issues` and set `smoke_test.action_invocation_confirmed` honestly as worker summary. Final validated/deployed-but-unvalidated reporting comes only from the orchestrator's per-item reconciled current-test assessment under the gate above.

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

### Running-User Backing-Action Access — Service Agent only (after activate, before the validation probe)
This section is a **NO-OP** for `AgentforceEmployeeAgent` (runs as the logged-in user, which already
holds this access — skip entirely) and for any agent whose backing actions are all standard / @utils
(no custom Apex/Flow, no custom RecordType). Run it ONLY when the deployed agent type is
`AgentforceServiceAgent`, which executes as the dedicated Einstein Agent running user — that user
starts with NO access to your backing code, so every custom action is withheld from the LLM until
granted. This is layers 1/3/4 of the running-user stack; the Standard Agentforce Runtime Permset above
is separate (Agentforce runtime access, not backing-action access).

Grant to the agent/Companion permset (retrieve-augment-redeploy — never blank-author over the existing
permset), derived from the backing actions in your spec. Do NOT hand-enumerate a fixed list — read
your own backing actions:
1. **Layer 1 — action reachable at all.** For every backing ApexClass and every backing Flow, add a
   `SetupEntityAccess`. `SetupEntityType` = `ApexClass` (SetupEntityId = the ApexClass Id) or
   `FlowDefinition` (SetupEntityId = the Flow's `FlowDefinitionView.DurableId` — NOT the Flow Id).
   Without this the planner withholds the action with `NO_USER_ACCESS` and the LLM never sees it.
2. **Layer 3 — RecordType visible.** For every RecordType the backing code inserts, add a
   `recordTypeVisibility` (visible=true).
3. **Layer 4 — dependency objects readable.** For every object a backing flow/apex READS for
   config/lookup (helper/config objects are easy to miss — trace the backing code, not just the target
   object), add an `objectPermission` read.
Deploy the augmented permset and confirm it is assigned to the running user.

**Prove layer 1 cleared (do not infer).** Run `sf agent preview` for one hero utterance and read the
trace `EnabledToolsStep.runtime_withheld_actions` — it must NOT list the hero action with
`NO_USER_ACCESS`. If it does, a grant is missing or the FlowDefinition Id was wrong
(`FlowDefinitionView.DurableId` vs the Flow Id); fix and re-deploy before proceeding. Record the
withheld-actions read in `discovery_notes`.

**Layer 5 — base-license wall (record, do not fight).** If a grant DEPLOY is *rejected* with
`The user license doesn't allow the permission: Read <Object>` (typically a managed/industry object —
Life Sciences: Inquiry, CareProgramEnrollee, ProgramEnrollment — under an Einstein Agent license), STOP
granting that object: a permset cannot cross a base-license wall. Record it in `issues` and surface the
spec's Layer-5 bypass as a mandatory SE-manual step (System Mode on an asset WE own, or disable the
specific managed trigger handler via Admin Console → Trigger Handler Administration). Do NOT loop
retries on a license-rejected grant, and do NOT report the agent validated if the hero action is
blocked by a wall — report deployed-but-NOT-validated with the wall named.

### Advanced capabilities — author metadata, hand off UI wiring
For multi-agent orchestration, Enhanced Chat v2, and Lightning types (forms) in chat, Scout AUTHORS + DEPLOYS the build-time-knowable metadata (per `${CLAUDE_PLUGIN_ROOT}/prompts/building/agentforce-advanced-capabilities.md`) and then hands the UI wiring + live verification to the SE — these have no build-time success signal (they render/route only in a live Enhanced Web Chat session), so do NOT report them "working." Report deployed metadata as `awaiting_qa`; report the separate outstanding UI-only obligation as `blocked` until the SE completes it. Do not put either in `skipped`. Note the connection wiring for multi-agent orchestration is Beta + UI-only (no Metadata API path).

### Always Out of Scope for Worker Automation
- Custom model/LLM config
- Production-scale test suites (Testing Center batch regression — Mode B)

Report these as BLOCKED manual obligations unless the injected ledger already has an
independently authorized explicit spec exclusion or SE non-execution decision. The
worker never puts them in `skipped` on its own.

## What Earlier Phases Deployed
{{PRIOR_PHASES_SUMMARY}}

{{COMPLETION_CONTRACT}}

## Expected Completion Ledger — Phase 3
{{EXPECTED_COMPLETION_LEDGER}}

## Your Spec
{{SPEC_SECTIONS}}

## Output Format
Return EXACTLY one fenced JSON block matching this schema. Do not include any prose outside the block. Every top-level key is REQUIRED even if empty.

```json
{
  "schema_version": 1,
  "build_id": "string — injected build id",
  "spec_sha256": "string — injected approved-spec sha256",
  "phase": 3,
  "completion": [
    {"item_id": "string — exact ledger item id", "status": "applied|already_satisfied|failed|blocked|awaiting_qa", "summary": "string"}
  ],
  "deployed": {
    "agent": {
      "ledger_item_id": "string", "api_name": "string", "version": 0, "status": "Active|Inactive|NeedsUICommit",
      "recovery": {"status": "not_needed|verified|failed", "artifact": "string|null", "bundle_path": "string|null", "original_path": "string|null", "error": "string|null"},
      "preedit_snapshot": {"status": "not_needed|verified|failed", "artifact": "string|null", "source": "string|null", "paths": ["string — exact relative bundle member"], "error": "string|null"}
    },
    "backing_actions": [{"ledger_item_id": "string", "type": "ApexClass|Flow|StandardAction", "api_name": "string", "status": "SUCCESS|FAILED"}],
    "agent_user": {"ledger_item_id": "string", "username": "string", "created_by_cli": true},
    "standard_permset_assignment": {"ledger_item_id": "string", "name": "string|null", "assigned_to": "string|null", "status": "SUCCESS|FAILED|NOT_FOUND"}
  },
  "smoke_test": {
    "ledger_item_id": "string",
    "ran": true,
    "action_invocation_confirmed": false,
    "utterances": [
      {"utterance": "string", "expectedTopic": "string|null", "expectedActions": ["string"], "expectedOutcome": "string", "passed": true, "mode": "B|A-fallback", "notes": "string"}
    ]
  },
  "actions_unverified_in_preview": [
    {"ledger_item_id": "string", "action": "string", "reason": "string — see Schema notes below for full definition and required wording for Knowledge grounding"}
  ],
  "skipped": [
    {"ledger_item_id": "string", "component": "string", "reason": "string — authorized omission only; must exactly mirror the frozen ledger authorization"}
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
- `deployed.agent.preedit_snapshot` — required. For net-new/re-author-side-by-side agents use `not_needed`, null path/error fields and empty `paths`. For any modified incumbent, `verified` requires the before-edit helper receipt and exact selected members; a failed/missing snapshot blocks mutation and cleanup. This is separate from new-agent `recovery` and never certifies runtime behavior.
- `smoke_test` is worker summary only. Its boolean never proves the deployed version
  worked and never overrides the orchestrator's independent current-test runtime
  assessment. Keep separate `ledger_item_id` values for the hero action, every
  other required action, and every guardrail/test obligation; one passing action
  must not clear another obligation's QA.
- `deployed.agent.recovery` — required. Use `not_needed` with all path/error fields null when step 6b did not fire. For `NeedsUICommit`, use `verified` only after the helper succeeds, otherwise `failed` with the original scratch path and error. All non-null paths must be actual absolute paths, never placeholders. A `verified` record certifies durable source, not a live agent.
- `deployed.agent.status = NeedsUICommit` — set ONLY by step 6b (SFAP publish-route 404 on this instance). Means the agent was authored + validated but could NOT be published headless; it is NOT live. `version` will typically be `0` (no published version). The orchestrator surfaces this to the SE as "authored + validated, NOT live — requires UI Commit" and routes to the go-live runbook. Do NOT report a `NeedsUICommit` agent as Active/working.
- `deployed.agent_user` — record the Einstein Agent User the `sf agent` CLI auto-creates during publish. The orchestrator surfaces this to the SE post-deploy.
- `deployed.backing_actions[].type = StandardAction` — use this when a standard action (Get Records, Update Record, Knowledge grounding) is wired in the Agent Spec without an Apex class.
- `actions_unverified_in_preview` — distinct from `smoke_test` failures. Populate when an action is deployed and syntactically correct but `sf agent preview` can't exercise it (stateless preview, missing session context, Knowledge grounding requiring a Data Library the SE must create). Include every Knowledge-grounded subagent here with the reason "Knowledge grounding unverified — Data Library must be created manually" until Data Library auto-provisioning is available.
- `discovery_notes` — covers the full deploy→validate→publish→activate lifecycle. If the sub-agent applied an inline fix at any stage, it belongs here. Publish-time fixes are not optional prose — they are required structured output. Canonical discovery_notes-vs-issues split: see `demo-deployment-rules` §Script Deliverable Rules.
