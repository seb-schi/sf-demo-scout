# Audit Orchestration Procedure

Execute this procedure to run a fresh 3-agent parallel audit.

## Pre-Spawn Setup (orchestrator runs directly)

1. Clean ALL stale orchestrator artifacts before any work begins. End-of-success cleanup (Cleanup & Validation steps 3–4) does not fire when a prior run crashes, hangs, or is SE-interrupted — the next run then inherits corrupt state and typically hangs at the parse step that consumes it, with no causal link visible to the SE. Run all sweeps unconditionally:
   ```
   rm -f orgs/[alias]-[customer]/audit-fragment-*.md 2>/dev/null || true
   rm -f orgs/[alias]-[customer]/.audit-* 2>/dev/null || true
   rm -f orgs/[alias]-[customer]/retrieve-*.xml 2>/dev/null || true
   rm -f orgs/[alias]-[customer]/*.tmp 2>/dev/null || true
   rm -rf unpackaged/ 2>/dev/null || true
   find . -maxdepth 1 -name 'manifest-*.xml' -delete 2>/dev/null || true
   find . -maxdepth 1 -name 'temp-*.xml' -delete 2>/dev/null || true
   ```
   Notes:
   - The `2>/dev/null || true` wrappers keep zsh's `NO_MATCH` from erroring on empty globs (lesson 68); without them the bundled cleanup step fails silently and step 2 (`printf` to init the progress log) never runs.
   - The `.audit-*` sweep is intentionally a wildcard, not a fixed list — it catches `.audit-progress.log` from a crashed prior run AND any ad-hoc files the model may have invented during a hang (e.g. `.audit-manifest-app.xml`).
   - `retrieve-*.xml` and `*.tmp` per-customer sweeps catch model-invented working files inside the customer folder (e.g. `retrieve-layouts-custom.xml` left by an ad-hoc retrieve workaround). Pattern-prefixed, not blanket `*.xml` — audit outputs are `.md`, but a future feature may legitimately store customer-owned XML in this folder, so we sweep only model-known prefixes.
   - `find . -maxdepth 1 -name 'manifest-*.xml' -delete` and the parallel `temp-*.xml` sweep are the zsh-safe shapes for repo-root sweeps — `rm -f manifest-*.xml` errors at glob expansion time on zsh before the redirection takes effect, so the `2>/dev/null` doesn't help. `find -delete` does its own argv handling and returns 0 on no matches.
   - `unpackaged/` is the directory `retrieve_metadata` drops at the repo root; `manifest-*.xml` and `temp-*.xml` are repo-root files the model sometimes writes during ad-hoc retrieve workarounds. All are gitignored — their presence carries no SE-meaningful state.
   - The sweep list grows as model-invented patterns surface in the field. When a new orphan appears in repo-root or a customer folder, add a pattern-prefixed sweep here rather than relying on the existing wildcards to catch it.
2. Initialize progress log — truncate the file and write a header so the SE-facing link opens to a non-empty file:
   ```
   printf "=== Audit started %s for %s ===\nSub-agents: standard-objects, apps-flows-agents, custom-objects\n\n" "$(date '+%Y-%m-%d %H:%M:%S')" "[alias]-[customer]" > orgs/[alias]-[customer]/.audit-progress.log
   ```
3. Resolve the current user Id: `run_soql_query` with `SELECT Id FROM User WHERE Username = '[username from Stage 1]' LIMIT 1`. Record as `CURRENT_USER_ID`.
4. Resolve the candidate default app — 2 SOQL queries:
   - `SELECT AppDefinitionId FROM UserAppInfo WHERE UserId = '[CURRENT_USER_ID]'`
   - `SELECT DurableId, Label, DeveloperName, NamespacePrefix FROM AppDefinition WHERE DurableId = '[AppDefinitionId]'`
   Record the Label as `CANDIDATE_APP` and the DeveloperName as `CANDIDATE_APP_DEVELOPER_NAME`.
   Compute `CANDIDATE_APP_FULL_NAME`:
   - If `NamespacePrefix` is non-null (managed-package app): `[NamespacePrefix]__[DeveloperName]` (e.g. `lsc4ce__lifeSciencesCommercial`, `qbranch__Q_Branch_Lightning`).
   - If `NamespacePrefix` is null (unmanaged app): just `[DeveloperName]` (e.g. `Service`, `LightningSales`).
   The Metadata API requires the namespaced full name for installed apps — an unnamespaced member will return "Entity cannot be found" even though the app exists.

5. **Confirm with the SE before retrieve.** The user's currently-open app is not always the right audit surface — common offenders are SE home-bases like Q Branch, Demo Wizard, and setup apps that exist in most demo orgs but are out of scope for customer demos. Emit exactly this message, then wait for the SE's reply:

   > "Detected default app: **[CANDIDATE_APP]**. Audit into this app, or is a different app the demo surface? Reply `yes` to proceed, or name the app to audit instead (e.g. `Service Console`, `Sales`)."

   - If the SE replies `yes` (or equivalent): keep `CANDIDATE_APP` / `CANDIDATE_APP_DEVELOPER_NAME`.
   - If the SE names a different app: re-query in two steps — `AppDefinition` does not support SOQL disjunctions (`OR` across columns), so a single `WHERE Label = 'X' OR DeveloperName = 'Y'` query rejects with "Disjunctions not supported".
     1. First try DeveloperName: `SELECT DurableId, Label, DeveloperName, NamespacePrefix FROM AppDefinition WHERE DeveloperName = '[SE's input]' LIMIT 1`.
     2. If that returns 0 rows, fall through to Label: `SELECT DurableId, Label, DeveloperName, NamespacePrefix FROM AppDefinition WHERE Label = '[SE's input]' LIMIT 1`.
     3. If both return 0 rows, tell the SE "No app matching `[input]` — reply with a different name or `skip` to audit core objects only" and loop.
     On a match: replace `CANDIDATE_APP` / `CANDIDATE_APP_DEVELOPER_NAME` with the result and recompute `CANDIDATE_APP_FULL_NAME` (same rule as step 4: `[NamespacePrefix]__[DeveloperName]` if namespaced, else `[DeveloperName]`).
   - If the SE replies `skip`: set `DEFAULT_APP` to "UNKNOWN", `DEFAULT_APP_TABS` to the 6 core objects only, and `ACTIVE_LRP_MAP` to `[]`. Skip step 6.

5a. **Emit the live-status heartbeat (MUST, before any sub-agent dispatch).** Async sub-agent work begins at step 6 (prelude) and continues through the parallel sub-agent dispatch — total async window is 5-10 min on SDO-scale orgs, all of it invisible to the SE in chat. The progress log is the only signal.

   **The link MUST be an absolute `file://` URI** — relative `orgs/...` paths don't open in VS Code when CC was launched from outside the Scout workspace (which is the default since Scout went global as a plugin). Pre-compute the absolute path with one Bash call, then substitute it into the message template:

   ```bash
   echo "file://$HOME/claude-projects/sf-demo-scout/orgs/[alias]-[customer]/.audit-progress.log"
   ```

   Capture the printed string as `[ABS_LOG_URI]`. Then emit exactly this message as the next assistant turn — single message, verbatim, with `[ABS_LOG_URI]` replaced by the captured value:

   > Audit running. Live status → [.audit-progress.log]([ABS_LOG_URI]) — click to open, VS Code auto-updates as the prelude and the 3 parallel sub-agents append. Typical runtime 5-10 min on SDO-scale orgs.

   The heartbeat exists because SE-facing silence is expensive — minutes of sub-agent runtime with no signal reads as "is Scout stuck?" Do not skip it. Do not paraphrase it. Do not bundle it into a later message. **If you find yourself about to call a tool here, stop — the heartbeat goes first** (the Bash pre-compute above is the one allowed exception).

6. **Dispatch the audit-prelude sub-agent** to retrieve and parse the heavy metadata. This keeps CustomApplication/CustomObject/Profile XML out of Opus context.

   Construct the dispatch envelope (do NOT read the prompt body — the sub-agent reads it itself). The envelope is the only string passed to `Agent()`:

   ```
   Read your prompt file at `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/audit/prelude.md`. Also read `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/audit/shared.md` — its content substitutes for `{{AUDIT_SHARED_RULES}}`. Apply these placeholder substitutions verbatim before executing:

   {{ORG_ALIAS}} = [alias]
   {{ORG_USERNAME}} = [username]
   {{CANDIDATE_APP_FULL_NAME}} = [computed value]
   {{CANDIDATE_APP}} = [label]
   {{CANDIDATE_APP_DEVELOPER_NAME}} = [developer name]
   {{CURRENT_USER_ID}} = [user id]

   Execute the prompt and return the JSON block per its Output Format section.
   ```

   Spawn:
   - `Agent(description="Org audit: prelude (LRP resolution)", model="sonnet", prompt=[envelope above])`

   Wait for the sub-agent to return. Extract the fenced JSON block. Parse it.
   - `status: SUCCESS` or `status: PARTIAL` → use the returned `default_app_tabs` and `active_lrp_map`. If `PARTIAL`, log each `degradations` entry to `audit-progress.log` so the SE can see which level was lost.
   - `status: FAILED` or missing/malformed JSON → degrade the audit: set `DEFAULT_APP_TABS` to core-6, set `ACTIVE_LRP_MAP` to `[]`, and flag the SE: "Audit prelude failed — proceeding with core-6 fallback only. Retry in a fresh window if you need full LRP resolution."

   Record: `DEFAULT_APP` = `CANDIDATE_APP`, `DEFAULT_APP_DEVELOPER_NAME` = `CANDIDATE_APP_DEVELOPER_NAME`, `DEFAULT_APP_TABS` = from prelude JSON, `ACTIVE_LRP_MAP` = from prelude JSON.

   Then **slice `ACTIVE_LRP_MAP` into two per-sub-agent views** so each Sonnet only sees entries it owns:
   - `ACTIVE_LRP_MAP_STANDARD` = entries where `object` does NOT end in `__c` (standard objects — Account, Contact, Opportunity, Case, Lead, Order, MessagingSession, ServiceResource, etc.). Goes to the standard-objects sub-agent.
   - `ACTIVE_LRP_MAP_CUSTOM` = entries where `object` ends in `__c` (unmanaged custom objects). Goes to the custom-objects sub-agent.

   Managed-package objects (namespace prefix in the `object` field, e.g. `lsc4ce__SomeObject__c`) are excluded from both — Scout does not classify managed-package LRPs.

   This is the structural defense against schema drift: each sub-agent only ever sees its own scope — drift becomes structurally impossible, not just discouraged.

## Sub-Agent Dispatch

Do NOT read the sub-agent prompt bodies. Each sub-agent reads its own prompt file and `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/audit/shared.md`. The orchestrator's job is to construct each envelope with the right placeholder values and dispatch.

Build a per-sub-agent envelope. Common placeholder values (computed by the orchestrator from earlier steps): `{{ORG_ALIAS}}`, `{{ORG_USERNAME}}`, `{{CUSTOMER}}`, `{{YYYY-MM-DD}}`, `{{HHMM}}`, `{{DEFAULT_APP}}`, `{{DEFAULT_APP_TABS}}`. The two LRP-aware sub-agents receive a sliced `{{ACTIVE_LRP_MAP}}`:
  - standard-objects: `ACTIVE_LRP_MAP_STANDARD`
  - custom-objects: `ACTIVE_LRP_MAP_CUSTOM`
  - apps-flows-agents: omit the placeholder (its prompt does not reference it).

Envelope template (substitute the prompt path and the placeholder block):

```
Read your prompt file at `[PROMPT_PATH]`. Also read `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/audit/shared.md` — its content substitutes for `{{AUDIT_SHARED_RULES}}`. Apply these placeholder substitutions verbatim before executing:

{{ORG_ALIAS}} = [alias]
{{ORG_USERNAME}} = [username]
{{CUSTOMER}} = [customer]
{{YYYY-MM-DD}} = [date]
{{HHMM}} = [time]
{{DEFAULT_APP}} = [label]
{{DEFAULT_APP_TABS}} = [tabs JSON]
{{ACTIVE_LRP_MAP}} = [sliced map JSON — omit this line for apps-flows-agents]

Execute the prompt and return the JSON block per its Output Format section.
```

Each entry in the sliced map carries `record_type`, `resolution_level`, and `source`. The sub-agent treats each entry as an independent LRP retrieval target — multiple record types on the same object mean multiple retrievals.

Spawn all 3 in parallel:
- `Agent(description="Org audit: standard objects", model="sonnet", prompt=[envelope with PROMPT_PATH=${CLAUDE_PLUGIN_ROOT}/prompts/sparring/audit/standard-objects.md])`
- `Agent(description="Org audit: apps/flows/agents", model="sonnet", prompt=[envelope with PROMPT_PATH=${CLAUDE_PLUGIN_ROOT}/prompts/sparring/audit/apps-flows-agents.md])`
- `Agent(description="Org audit: custom objects", model="sonnet", prompt=[envelope with PROMPT_PATH=${CLAUDE_PLUGIN_ROOT}/prompts/sparring/audit/custom-objects.md])`

The live-status heartbeat was already emitted in step 5a — do not re-emit it here. Wait for all 3 to return. Do not read the progress log — it is SE-facing only.

## Post-Return Processing

As each sub-agent returns, **first** apply structural partial-return detection — do not eyeball the response:

1. **Regex-check the agent's return string for a fenced JSON block:** `^```json` (start of line, anywhere in the response). If present, proceed to parse. If absent, the sub-agent returned mid-narration (typically a budget/timeout wall — the harness surfaces last-assistant-text as "result" without flagging the truncation).
2. **On absent JSON:** auto-redispatch the same envelope **once** (max 1 retry — a second retry usually hits the same wall and doubles worst-case latency). Before redispatching, log to `audit-progress.log`: `⚠️ [agent-id]: returned without fenced JSON — auto-retry 1/1`. Use the same `Agent(...)` call shape as the original spawn.
3. **On absent JSON after retry:** flag that sub-agent's section as failed and surface the raw return string to the SE: "[agent-id] failed twice — returned mid-narration both times. Likely tool-budget exhaustion. Retry in a fresh window or skip this section."
4. **On present JSON:** parse it. `status: SUCCESS` or `status: PARTIAL` → collect the JSON. `status: FAILED` → flag that sub-agent's section as failed.
5. If 2+ sub-agents fail (after retry where applicable) → show the raw outputs, ask the SE to retry in a fresh window or skip the audit entirely.

The same regex-check applies to the prelude sub-agent's return in the Pre-Spawn Setup step — absent fenced JSON triggers the same max-1 retry before falling through to the core-6 degraded audit.

Check the standard-objects sub-agent's `demo_surface_notes` for non-universal standard objects with data — these hint at which industry cloud the org uses. Record for Stage 3.

## Spot-Check Pass (2 targeted queries — always run)

Run these SOQL queries in parallel:
- `SELECT COUNT() FROM BotDefinition` — agent count
- `SELECT COUNT() FROM FlowDefinitionView WHERE IsActive = true` — active flow count

Compare each against the sub-agent JSON fields:
- **Flow count:** compare against apps/flows/agents sub-agent's `active_flow_count`. Mismatch means the sub-agent's count query failed — flag it.
- **Agent count:** compare against apps/flows/agents sub-agent's `agents_found` array length. If spot-check finds >0 but sub-agent reported 0, query `SELECT DeveloperName, MasterLabel, Type FROM BotDefinition` and include the results in the consolidated summary.
- For any mismatch >20% or zero-vs-nonzero: flag to the SE: "Sub-agent reported [X] but spot-check found [Y]. The [section] may be incomplete."

Default app is not spot-checked here — the orchestrator confirmed it with the SE in pre-spawn setup.

## Consolidation (no raw markdown reading)

Merge the 3 JSON summaries + spot-check corrections into one consolidated summary:
- `default_app`: from orchestrator pre-spawn (ground truth)
- `default_app_tabs`: from orchestrator pre-spawn (ground truth)
- `active_lrp_map`: from prelude sub-agent (ground truth — same `ACTIVE_LRP_MAP` injected into the parallel sub-agents)
- `active_layouts`: union of standard objects + custom objects sub-agent arrays (classic Page Layouts)
- `active_lrps`: union of standard objects + custom objects sub-agent `active_lrps` arrays — each entry carries `{object, lrp_developer_name, composition_class, gap_risk, field_sections}`. `composition_class` ∈ {`record_detail` (uses `force:detailPanel`, layout-pass-through, safe), `field_section` (uses `flexipage:fieldSection`, custom-composed, layout adds invisible), `mixed` (both), `custom` (neither — pure LWC or dynamic-form regions), `unretrievable` (LRP retrieve failed)}. `gap_risk` is `false` for `record_detail`, `true` for `field_section` / `mixed` / `custom` / `unretrievable`.
- `relevant_custom_objects`: from custom objects sub-agent
- `agents_found`: from apps/flows/agents sub-agent (corrected by spot-check if needed)
- `active_flow_count`: from spot-check (ground truth)
- `notable_gaps`: collect `issues` arrays from all 3 sub-agents
- `demo_surface_notes`: collect `demo_surface_notes` arrays from all 3 sub-agents

## Notable Gaps Narrative

Using the consolidated JSON summary — especially `demo_surface_notes` from all 3 sub-agents — write a "Notable Gaps and Risks" section. This is cross-cutting synthesis: what the org's metadata means for the demo scenario.

Concatenate fragment files:
```
cat orgs/[alias]-[customer]/audit-fragment-standard-objects.md \
    orgs/[alias]-[customer]/audit-fragment-apps-flows-agents.md \
    orgs/[alias]-[customer]/audit-fragment-custom-objects.md \
    > orgs/[alias]-[customer]/audit-[YYYY-MM-DD]-[HHMM].md
```

Append the Notable Gaps section (written by Opus from the JSON summaries) to the end of that file.

## Cleanup & Validation

1. Delete the 3 fragment files after successful concatenation.
2. **Star marker validation:** Grep the consolidated audit file for `★`. If 0 matches, flag to the SE: "The audit file has no ★ markers — build surface identification may have failed." Keep the progress log in place — SE may need the heartbeat history to debug which sub-agent failed to star-flag.
3. Delete the progress log — `rm -f orgs/[alias]-[customer]/.audit-progress.log`. Run this only after star-marker validation passes; on validation failure, leave the log so the SE can inspect sub-agent heartbeats.
4. **Symmetric workspace sweep.** Run the same orphan-file sweeps the Pre-Spawn Setup runs at start-of-run, so clean successful audits don't leave model-invented working files in the SE workspace:
   ```
   rm -rf unpackaged/ 2>/dev/null || true
   find . -maxdepth 1 -name 'manifest-*.xml' -delete 2>/dev/null || true
   find . -maxdepth 1 -name 'temp-*.xml' -delete 2>/dev/null || true
   rm -f orgs/[alias]-[customer]/retrieve-*.xml 2>/dev/null || true
   rm -f orgs/[alias]-[customer]/*.tmp 2>/dev/null || true
   ```
   These mirror the Pre-Spawn sweep exactly. Start-of-run cleanup remains the safety net for crashed / interrupted / SE-cancelled prior runs (the corrupt-state hang it prevents is documented in `pipeline-lessons/sub-agent-architecture.md`); end-of-success cleanup is hygiene for the clean-success path, so a successful audit doesn't leave manifest/temp orphans visible in the SE's `ls` or VS Code file tree. The two layers are complementary, not redundant: end-of-success doesn't fire when a run crashes; start-of-run doesn't fire until the *next* audit kicks off — without symmetry, orphans linger between successful runs. The SE workspace at `~/claude-projects/sf-demo-scout/` is not a git repo and has no `.gitignore`, so these files are visible until swept.
