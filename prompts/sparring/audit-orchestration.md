# Audit Orchestration Procedure

Execute this procedure to run a fresh 3-agent parallel audit.

**This audit runs in the BACKGROUND.** The orchestrator does sync setup (Phase A), launches the prelude sub-agent with `Agent(run_in_background: true)`, and RETURNS control to the caller so the SE can answer discovery questions while the audit runs. Background sub-agent completions push a notification that wakes the orchestrator even while an SE answer is pending — so the orchestrator must be able to react to a completion at any point: collect it, do the next background step, log to the progress file, and emit NO new SE-facing chat message (an SE discovery ask may be in flight — a second simultaneous ask is the confusion the 2026-05-11 ask-while-async lesson warns against). The caller pulls the consolidated result at the join point (Phase C) once the SE has finished the audit-independent discovery questions.

**Three phases:**
- **Phase A — Sync setup + launch prelude (blocking, fast).** Pre-Spawn steps 0–5a, then launch the prelude in the background and return control to the caller. The caller proceeds to ask Stage 3 discovery questions.
- **Phase B — Prelude completion (push-triggered, log-only).** On the prelude's background-completion notification: collect + parse it, slice ACTIVE_LRP_MAP, launch the 3 parallel sub-agents in the background, append a progress-log line. NO chat message. If a discovery ask is pending, the SE keeps answering — the parallel agents run silently.
- **Phase C — AUDIT-READY barrier (foreground join).** Invoked by the caller once the SE has answered the audit-independent discovery questions. If the prelude is still running, finish its bounded Phase B handling and launch the 3 workers first. Then collect the workers (await their completions if needed), apply the existing bounded structural retry, run the spot-check, consolidate, write and validate the audit, and return a ready/not-ready outcome. This is the single audit-dependent boundary; callers own their route-specific star/question UI.

## Pre-Spawn Setup (orchestrator runs directly)

0. **Resolve the absolute plugin root (MUST — before any sub-agent envelope is built).** `${CLAUDE_PLUGIN_ROOT}` resolves in this orchestrator context but is **empty inside Agent-tool sub-agents** — if you pass the literal `${CLAUDE_PLUGIN_ROOT}/prompts/...` into a sub-agent envelope, the sub-agent cannot expand it and wastes ~10 tool calls hunting for its prompt file via `find`, with a real risk of reading a stale cached plugin version (13 versions sit side by side in the cache). Resolve the active install path once here and reuse it in every envelope below as `PLUGIN_ROOT_ABS`:
   ```bash
   python3 -c "
   import json, os
   d = json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')))
   entries = d['plugins']['sf-demo-scout@scout']
   e = next((x for x in entries if x.get('scope') == 'user'), entries[0])
   print(e['installPath'])
   "
   ```
   - The value is an absolute path like `/Users/<user>/.claude/plugins/cache/scout/sf-demo-scout/<active-version>`. Record it as `PLUGIN_ROOT_ABS`.
   - **Why `installed_plugins.json` and not `find ... | sort -V | tail -1`:** Scout ships multiple same-date versions whose topic suffix breaks version-sort (`2026.06.07-deploy-error-extract-and-cli-guard` sorts after `2026.06.07-audit-field-dump-cut`, so `tail -1` would pick the PRIOR version). `installed_plugins.json` names the actually-installed path regardless of version-string shape. The per-plugin value is a LIST of install records (one per scope) — prefer the `scope=="user"` entry, fall back to the first.
   - **On failure** (file missing, key absent, empty output): fall back to `${CLAUDE_PLUGIN_ROOT}` literal in the envelopes (current behaviour — sub-agents will hunt, but the audit still completes) and log to `audit-progress.log`: `⚠️ plugin-root resolution failed — sub-agents will self-locate prompts (slower; verify they read the active version)`. Do NOT abort the audit over this.

1. Read `[PLUGIN_ROOT_ABS]/prompts/operation-safety.md` and follow it. Resolve
   `WORKSPACE_ROOT` from bootstrap and absolute `CUSTOMER_DIR` from the selected
   customer; set `ASSET_HELPER` to `[PLUGIN_ROOT_ABS]/scripts/build-assets.py`.
   Prepare and verify a unique coordinator project with `WRITER=audit-coordinator`.
   Retain its returned project root as `AUDIT_RUN_DIR`; use it for this audit's
   progress log, fragments and candidate. Never remove or reuse old audit files.
   Prepare a separate verified project for each prelude/parallel metadata writer
   immediately before dispatch. Pass its own `PROJECT_ROOT` and `SCOUT_TMPDIR`
   (the same absolute project root), the common `AUDIT_RUN_DIR`, and the unchanged
   selected `ORG_FOLDER` to each envelope. A replacement worker gets fresh staging.
   Set each worker's `ASSET_HELPER` to that injected absolute helper path; the
   projects are already prepared, so workers verify/use them without re-preparing.
   Retain all receipts/paths; failure blocks the affected writer without a shared
   source fallback. The coordinator and workers never sweep source or audit files.
2. Initialize progress log — truncate the file and write a header so the SE-facing link opens to a non-empty file. The log now carries only coarse orchestrator phase markers + sub-agent `⚠️` failure lines (routine sub-agent heartbeats were removed — they rendered as chat-card noise during background discovery):
   ```
   printf "=== Audit started %s for %s ===\nSub-agents: standard-objects, apps-flows-agents, custom-objects\nThis log shows phase milestones + failures only.\n\n[%s] [orchestrator] Phase A — sync setup + prelude launch\n" "$(date '+%Y-%m-%d %H:%M:%S')" "[ORG_FOLDER]" "$(date '+%H:%M:%S')" > [AUDIT_RUN_DIR]/.audit-progress.log
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

   **The link MUST be a workspace-relative path**, not an absolute `file://` URI. The VSCode native CC extension renders markdown links relative to the SE's VSCode workspace root (which is reliably `~/claude-projects/sf-demo-scout` for Scout SEs) and does not open `file://` URIs as in-editor file opens. Emit exactly this message as the next assistant turn — single message, verbatim:

   > Audit running in the background. Status → [audit progress]([AUDIT_RUN_DIR]/.audit-progress.log) — click to open; it logs phase milestones and any failures (not every step). Typical runtime 5-10 min on SDO-scale orgs. No need to watch it — I'll fold the results in once it lands.

   Substitute `[AUDIT_RUN_DIR]` with this run's actual workspace-relative path before emitting.

   The heartbeat exists because SE-facing silence is expensive — minutes of sub-agent runtime with no signal reads as "is Scout stuck?" Do not skip it. Do not paraphrase it. Do not bundle it into a later message. **If you find yourself about to call a tool here, stop — the heartbeat goes first.**

6. **Dispatch the audit-prelude sub-agent** to retrieve and parse the heavy metadata. This keeps CustomApplication/CustomObject/Profile XML out of Opus context.

   Construct the dispatch envelope (do NOT read the prompt body — the sub-agent reads it itself). The envelope is the only string passed to `Agent()`. **Substitute the absolute `PLUGIN_ROOT_ABS` resolved in Pre-Spawn step 0 for `[PLUGIN_ROOT_ABS]` below — do NOT emit the literal `${CLAUDE_PLUGIN_ROOT}`, which the sub-agent cannot expand:**

   ```
   Read your prompt file at `[PLUGIN_ROOT_ABS]/prompts/sparring/audit/prelude.md`. Also read `[PLUGIN_ROOT_ABS]/prompts/operation-safety.md` as `{{OPERATION_SAFETY}}` and `[PLUGIN_ROOT_ABS]/prompts/sparring/audit/shared.md` — its content substitutes for `{{AUDIT_SHARED_RULES}}`. Apply these placeholder substitutions verbatim before executing:

   {{ORG_ALIAS}} = [raw alias — for --target-org; NOT slugified]
   {{ORG_USERNAME}} = [username]
   {{ORG_FOLDER}} = [resolved ORG_FOLDER path, e.g. orgs/metro-cpq-metro]
   {{CANDIDATE_APP_FULL_NAME}} = [computed value]
   {{CANDIDATE_APP}} = [label]
   {{CANDIDATE_APP_DEVELOPER_NAME}} = [developer name]
   {{CURRENT_USER_ID}} = [user id]
   {{ASSET_HELPER}} = [PLUGIN_ROOT_ABS]/scripts/build-assets.py
   {{SCOUT_TMPDIR}} = [this writer's helper-returned absolute project_root]
   {{PROJECT_ROOT}} = [this writer's helper-returned absolute project_root]
   {{AUDIT_RUN_DIR}} = [coordinator's unique absolute project_root]

   Execute the prompt and return the JSON block per its Output Format section.
   ```

   Spawn in the BACKGROUND (this ends Phase A — return control to the caller immediately after this spawn; do NOT block):
   - `Agent(description="Org audit: prelude (LRP resolution)", model="sonnet", prompt=[envelope above], run_in_background=true)`

   **End of Phase A.** Return to the caller (scout-sparring.md Stage 3 / showtime.md S1b) so the SE can begin answering discovery questions. The steps below (parse prelude, slice, launch parallel) execute as **Phase B** when the prelude's background completion notification arrives — which may be while an SE discovery answer is still pending. Do NOT wait synchronously here.

   **Phase B begins on the prelude background-completion notification.** Apply the same structural fenced-JSON check as Post-Return Processing below. If the block is absent or malformed, redispatch the prelude envelope with a fresh owned project **once** and log `auto-retry 1/1`; only a second absent/malformed return falls through to the core-6 degradation. Parse a present block.
   - `status: SUCCESS` or `status: PARTIAL` → use the returned `default_app_tabs` and `active_lrp_map`. If `PARTIAL`, retain every `degradations` entry in `PRELUDE_LIMITATIONS` and log each one to `audit-progress.log` so the SE can see which level was lost. These limitations make the final barrier result `ready-partial` even when every worker succeeds.
   - `status: FAILED`, or missing/malformed JSON after the one retry → degrade the audit: set `DEFAULT_APP_TABS` to core-6, set `ACTIVE_LRP_MAP` to `[]`, record a partial-result reason, and flag the SE: "Audit prelude failed — proceeding with core-6 fallback only. Retry in a fresh window if you need full LRP resolution."

   Record: `DEFAULT_APP` = `CANDIDATE_APP`, `DEFAULT_APP_DEVELOPER_NAME` = `CANDIDATE_APP_DEVELOPER_NAME`. For `SUCCESS`/`PARTIAL`, record validated `DEFAULT_APP_TABS` and `ACTIVE_LRP_MAP` from the prelude JSON. For the failed/missing/malformed branch, retain the fallback values already assigned (`DEFAULT_APP_TABS` = core-6 and `ACTIVE_LRP_MAP` = `[]`); do not overwrite them from the invalid return.

   Then **slice `ACTIVE_LRP_MAP` into two per-sub-agent views** so each Sonnet only sees entries it owns:
   - `ACTIVE_LRP_MAP_STANDARD` = entries where `object` does NOT end in `__c` (standard objects — Account, Contact, Opportunity, Case, Lead, Order, MessagingSession, ServiceResource, etc.). Goes to the standard-objects sub-agent.
   - `ACTIVE_LRP_MAP_CUSTOM` = entries where `object` ends in `__c` (unmanaged custom objects). Goes to the custom-objects sub-agent.

   Managed-package objects (namespace prefix in the `object` field, e.g. `lsc4ce__SomeObject__c`) are excluded from both — Scout does not classify managed-package LRPs.

   This is the structural defense against schema drift: each sub-agent only ever sees its own scope — drift becomes structurally impossible, not just discouraged.

## Sub-Agent Dispatch

Do NOT read the sub-agent prompt bodies. Each sub-agent reads `[PLUGIN_ROOT_ABS]/prompts/operation-safety.md` as `{{OPERATION_SAFETY}}`, its own prompt file and `[PLUGIN_ROOT_ABS]/prompts/sparring/audit/shared.md` (the absolute path resolved in Pre-Spawn step 0). The orchestrator's job is to construct each envelope with the right placeholder values and dispatch. **Every `[PLUGIN_ROOT_ABS]` and `[PROMPT_PATH]` below must be the resolved absolute path — never the literal `${CLAUDE_PLUGIN_ROOT}`, which is empty in sub-agent context.**

Build a per-sub-agent envelope. Common placeholder values (computed by the orchestrator from earlier steps): `{{ORG_ALIAS}}` (raw — `--target-org` only), `{{ORG_FOLDER}}` (resolved folder path — every file path uses this), `{{ORG_USERNAME}}`, `{{CUSTOMER}}` (raw — object name-matching only), `{{YYYY-MM-DD}}`, `{{HHMM}}`, `{{DEFAULT_APP}}`, `{{DEFAULT_APP_TABS}}`, `{{SCOUT_TMPDIR}}`, `{{PROJECT_ROOT}}`, `{{AUDIT_RUN_DIR}}`, `{{ASSET_HELPER}}`. The two LRP-aware sub-agents receive a sliced `{{ACTIVE_LRP_MAP}}`:
  - standard-objects: `ACTIVE_LRP_MAP_STANDARD`
  - custom-objects: `ACTIVE_LRP_MAP_CUSTOM`
  - apps-flows-agents: omit the placeholder (its prompt does not reference it).

Envelope template (substitute the prompt path and the placeholder block). `[PROMPT_PATH]` = `[PLUGIN_ROOT_ABS]/prompts/sparring/audit/<sub-agent>.md`:

```
Read your prompt file at `[PROMPT_PATH]`. Also read `[PLUGIN_ROOT_ABS]/prompts/operation-safety.md` as `{{OPERATION_SAFETY}}` and `[PLUGIN_ROOT_ABS]/prompts/sparring/audit/shared.md` — its content substitutes for `{{AUDIT_SHARED_RULES}}`. Apply these placeholder substitutions verbatim before executing:

{{ORG_ALIAS}} = [raw alias — for --target-org; NOT slugified]
{{ORG_USERNAME}} = [username]
{{ORG_FOLDER}} = [resolved ORG_FOLDER path, e.g. orgs/metro-cpq-metro]
{{CUSTOMER}} = [raw customer name — for object name-matching only, NOT paths]
{{YYYY-MM-DD}} = [date]
{{HHMM}} = [time]
{{DEFAULT_APP}} = [label]
{{DEFAULT_APP_TABS}} = [tabs JSON]
{{ACTIVE_LRP_MAP}} = [sliced map JSON — omit this line for apps-flows-agents]
{{ASSET_HELPER}} = [PLUGIN_ROOT_ABS]/scripts/build-assets.py
   {{SCOUT_TMPDIR}} = [this writer's helper-returned absolute project_root]
   {{PROJECT_ROOT}} = [this writer's helper-returned absolute project_root]
   {{AUDIT_RUN_DIR}} = [coordinator's unique absolute project_root]

Execute the prompt and return the JSON block per its Output Format section.
```

Each entry in the sliced map carries `record_type`, `resolution_level`, and `source`. The sub-agent treats each entry as an independent LRP retrieval target — multiple record types on the same object mean multiple retrievals.

Spawn all 3 in the BACKGROUND (`[PLUGIN_ROOT_ABS]` = the absolute path from Pre-Spawn step 0):
- `Agent(description="Org audit: standard objects", model="sonnet", prompt=[envelope with PROMPT_PATH=[PLUGIN_ROOT_ABS]/prompts/sparring/audit/standard-objects.md], run_in_background=true)`
- `Agent(description="Org audit: apps/flows/agents", model="sonnet", prompt=[envelope with PROMPT_PATH=[PLUGIN_ROOT_ABS]/prompts/sparring/audit/apps-flows-agents.md], run_in_background=true)`
- `Agent(description="Org audit: custom objects", model="sonnet", prompt=[envelope with PROMPT_PATH=[PLUGIN_ROOT_ABS]/prompts/sparring/audit/custom-objects.md], run_in_background=true)`

After spawning, append ONE progress-log line (`echo "[$(date +%H:%M:%S)] [orchestrator] prelude done — 3 parallel audit agents launched" >> [AUDIT_RUN_DIR]/.audit-progress.log`) and emit **NO chat message** — a discovery ask may be pending. The live-status heartbeat was already emitted in step 5a. **This ends Phase B.** Do not block waiting for the 3 agents here; their completions will push notifications. As each arrives, you MAY collect it eagerly (hold the parsed JSON), but do NOT begin consolidation until Phase C is invoked by the caller — consolidation emits the SE-facing star summary, which must not compete with a pending discovery ask.

<a id="phase-c-audit-ready-barrier"></a>
## Phase C — AUDIT-READY barrier

Invoke this barrier only after the caller's audit-independent question is answered. If Phase B has not launched the three workers yet, await the prelude, apply Phase B's one-retry/fallback handling, and launch them. Then ensure all 3 parallel sub-agents have completed (await any whose background completion has not yet arrived). Append one coarse marker — `echo "[$(date +%H:%M:%S)] [orchestrator] Phase C — all sub-agents in, consolidating" >> [AUDIT_RUN_DIR]/.audit-progress.log` — then (do not read the progress log back — it is SE-facing only) run Post-Return Processing, Spot-Check, Consolidation, Notable Gaps, and Cleanup below.

Do not return to an audit consumer until Cleanup & Validation assigns an outcome:

- `ready-complete` — all required sections returned and the written audit passed star validation.
- `ready-partial` — the prelude degraded or one worker section failed, every degradation/failure is surfaced, and the written audit still passed star validation. A partial result is usable evidence with named limits, never a full-audit claim.
- `not-ready` — two or more workers failed, consolidation/write failed, or star validation failed. Stop at the existing retry-or-explicit-skip decision. A caller must not consume this run as an audit. An explicit skip changes `AUDIT_MODE` to `skipped`; it does not turn this result into `ready-partial`.

Return the outcome, consolidated summary, and audit-file path. Do not emit a caller-specific star block, Q5, reconciliation, or proposal from this fragment.

## Post-Return Processing

As each sub-agent returns, **first** apply structural partial-return detection — do not eyeball the response:

1. **Regex-check the agent's return string for a fenced JSON block:** `^```json` (start of line, anywhere in the response), then parse it. A missing block or parse/schema failure is a structural failure; preserve the raw return. A present fence by itself is not success.
2. **On structural failure:** auto-redispatch the envelope with a fresh owned project **once** (max 1 retry — a second retry usually hits the same wall and doubles worst-case latency). Before redispatching, log to `audit-progress.log`: `⚠️ [agent-id]: absent or malformed fenced JSON — auto-retry 1/1`. Use the same `Agent(...)` call shape as the original spawn.
3. **On structural failure after retry:** flag that sub-agent's section as failed and surface both raw returns to the SE: "[agent-id] failed structural validation twice. Retry in a fresh window or skip this section."
4. **On structurally valid JSON:** `status: SUCCESS` or `status: PARTIAL` → collect the JSON. `status: FAILED` → flag that sub-agent's section as failed and surface its stated reason.
5. If 2+ sub-agents fail (after retry where applicable) → set the barrier outcome to `not-ready`, show the raw outputs, and ask the SE to retry in a fresh window or explicitly skip the audit. **Stop.** Do not run consolidation or return data to an audit consumer unless a retry later crosses the barrier; a skip sets `AUDIT_MODE = skipped`.
6. If exactly one sub-agent fails, require the other two successful/partial fragment files, then write a short fragment at the failed section's expected path containing only its section heading, `Section unavailable`, and the surfaced failure reason. Do not infer findings or star items. If either successful fragment is missing or the placeholder write fails, set `not-ready` and stop. This explicit placeholder is what permits a structurally complete `ready-partial` audit.

The same structural check applies to the prelude sub-agent's return in the Pre-Spawn Setup step — absent or malformed fenced JSON triggers the same max-1 retry before falling through to the core-6 degraded audit.

Check the standard-objects sub-agent's `demo_surface_notes` for non-universal standard objects with data — these hint at which industry cloud the org uses. Record for Stage 3.

## Spot-Check Pass (2 targeted queries — always run)

Run these SOQL queries in parallel:
- `SELECT COUNT() FROM BotDefinition` — agent count
- `SELECT COUNT() FROM FlowDefinitionView WHERE IsActive = true` — active flow count

Compare each against the sub-agent JSON fields:
- **Flow count:** compare against apps/flows/agents sub-agent's `active_flow_count`. A mismatch is a discrepancy; retain both raw values and do not infer which query failed without further evidence.
- **Agent count:** compare against apps/flows/agents sub-agent's `agents_found` array length. If spot-check finds >0 but sub-agent reported 0, query `SELECT DeveloperName, MasterLabel, Type FROM BotDefinition` and include the results in the consolidated summary.
- For any mismatch >20% or zero-vs-nonzero: flag to the SE: "Sub-agent reported [X] but spot-check found [Y]. The [section] may be incomplete." If the discrepancy remains unresolved, add both raw values to `SPOT_CHECK_LIMITATIONS`; that makes the final result `ready-partial` if validation otherwise succeeds.
- If either spot-check query fails, is unavailable, or returns an unparseable result, record that value as `unknown`, retain the worker's reported value only as unverified context, and add the exact failure to `SPOT_CHECK_LIMITATIONS`. Do not coerce failure to zero or call it ground truth. Any `SPOT_CHECK_LIMITATIONS` entry makes the final result `ready-partial` if validation otherwise succeeds.

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
- `active_flow_count`: from a successful spot-check (ground truth); otherwise `unknown`, with the worker-reported value retained as unverified context and the spot-check limitation named
- `notable_gaps`: collect `issues` arrays from all 3 sub-agents
- `demo_surface_notes`: collect `demo_surface_notes` arrays from all 3 sub-agents

## Notable Gaps Narrative

Using the consolidated JSON summary — especially `demo_surface_notes` from all 3 sub-agents — write a "Notable Gaps and Risks" section. This is cross-cutting synthesis: what the org's metadata means for the demo scenario.

After verifying all three expected paths exist (including an explicit failed-section placeholder when exactly one worker failed), concatenate into a bounded candidate path rather than the published audit path:
```
cat [AUDIT_RUN_DIR]/audit-fragment-standard-objects.md \
    [AUDIT_RUN_DIR]/audit-fragment-apps-flows-agents.md \
    [AUDIT_RUN_DIR]/audit-fragment-custom-objects.md \
    > [AUDIT_RUN_DIR]/audit-candidate-[YYYY-MM-DD]-[HHMM].md
```

If any required fragment is missing or concatenation/write fails, set the barrier outcome to `not-ready`, retain the available fragments and progress log for diagnosis, and stop for retry-or-explicit-skip. Never publish or return the candidate as a valid audit.

Append the Notable Gaps section (written by Opus from the JSON summaries) to the candidate file. Include `PRELUDE_LIMITATIONS`, failed-section details, worker `degradations`, `SPOT_CHECK_LIMITATIONS`, and count mismatches as applicable.

## Cleanup & Validation

1. **Star marker validation:** Grep the candidate audit file for `★`. If 0 matches, set the barrier outcome to `not-ready`, flag to the SE: "The audit candidate has no ★ markers — build surface identification may have failed. Retry in a fresh window or explicitly skip this audit." Keep the candidate, source fragments, and progress log in place, then **stop** — do not publish or return the candidate to an audit consumer.
2. After star validation succeeds, publish the candidate to a new customer audit
   path `[ORG_FOLDER]/audit-[YYYY-MM-DD]-[HHMM]-[unique coordinator directory name].md`.
   Require the destination to be absent; use an exclusive-create copy and verify
   its complete bytes against the candidate. Never overwrite an existing audit.
   On copy/verification failure set `not-ready`, retain the candidate/fragments/log,
   report the exact failure (including any partial destination), and stop.
3. Retain the progress log, fragments, candidate, and all writer projects with their
   ownership receipts. There is no automatic cleanup. Return the exact published
   file path; consumers must not derive a timestamp-only path or pick another run.
4. Preservation and file-write failures remain visible. Do not suppress errors,
   infer absence from failed enumeration, or reroute a refused operation.
5. **Return the barrier result.** Return `ready-partial` if the prelude returned `PARTIAL` or used core-6 fallback, any collected worker reported `PARTIAL`, exactly one worker section failed, or any spot-check is unknown; include every named limitation. Otherwise return `ready-complete`. Return the consolidated summary and validated published audit-file path with either ready outcome. Never return ready after a `not-ready` condition above.
