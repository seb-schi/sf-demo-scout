# Audit Orchestration Procedure

Execute this procedure to run a fresh 3-agent parallel audit.

**This audit runs in the BACKGROUND.** The orchestrator does sync setup (Phase A), launches the prelude sub-agent with `Agent(run_in_background: true)`, and RETURNS control to the caller so the SE can answer discovery questions while the audit runs. Background sub-agent completions push a notification that wakes the orchestrator even while an SE answer is pending — so the orchestrator must be able to react to a completion at any point: collect it, do the next background step, log to the progress file, and emit NO new SE-facing chat message (an SE discovery ask may be in flight — a second simultaneous ask is the confusion the 2026-05-11 ask-while-async lesson warns against). The caller pulls the consolidated result at the join point (Phase C) once the SE has finished the audit-independent discovery questions.

**Three phases:**
- **Phase A — Sync setup + launch prelude (blocking, fast).** Pre-Spawn steps 0–5a, then launch the prelude in the background and return control to the caller. The caller proceeds to ask Stage 3 discovery questions.
- **Phase B — Prelude completion (push-triggered, log-only).** On the prelude's background-completion notification: collect + parse it, slice ACTIVE_LRP_MAP, launch the 3 parallel sub-agents in the background, append a progress-log line. NO chat message. If a discovery ask is pending, the SE keeps answering — the parallel agents run silently.
- **Phase C — Consolidation (foreground join).** Invoked by the caller once the SE has answered the audit-independent discovery questions. Collect the 3 parallel sub-agents (await their completions if not all arrived), run the spot-check, consolidate, write the Notable Gaps narrative, clean up, and surface the star summary. This is the audit-dependent join — the star summary and the anchor-app discovery question surface here.

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

1. Clean stale orchestrator artifacts and prepare a bounded scratch dir for this run. End-of-success cleanup (Cleanup & Validation steps 3–4) does not fire when a prior run crashes, hangs, or is SE-interrupted — the next run then inherits corrupt state and typically hangs at the parse step that consumes it, with no causal link visible to the SE. Run unconditionally:
   ```
   rm -f [ORG_FOLDER]/audit-fragment-*.md 2>/dev/null || true
   rm -f [ORG_FOLDER]/.audit-* 2>/dev/null || true
   find [ORG_FOLDER]/.scout-tmp -mindepth 0 -delete 2>/dev/null || true
   mkdir -p [ORG_FOLDER]/.scout-tmp/
   rm -rf unpackaged/ 2>/dev/null || true
   find . -maxdepth 1 -name 'package-*.xml' -delete 2>/dev/null || true
   ```
   Notes:
   - **Bounded scratch dir.** `[ORG_FOLDER]/.scout-tmp/` is the only location sub-agents write transient working files (manifests for ad-hoc `retrieve_metadata` calls, intermediate XML, anything that isn't an audit fragment or the progress log). Sub-agents see the absolute path via the `{{SCOUT_TMPDIR}}` envelope placeholder in Sub-Agent Dispatch and are instructed in `prompts/sparring/audit/shared.md` to write only inside it. The whole directory is wiped on entry (above, via `find … -delete`) and on successful exit (Cleanup & Validation step 4), so any new working-file pattern the model invents lands inside the disposable boundary automatically — no need to widen a per-pattern sweep list.
   - The `.audit-*` sweep stays as a wildcard — it catches `.audit-progress.log` from a crashed prior run AND any ad-hoc files the model may have invented at the customer-folder root (where the SE looks first). Hidden-file convention; the model knows to write hidden state files there.
   - `audit-fragment-*.md` stays as an explicit sweep — these are first-class audit outputs the consolidation step concatenates, not transient scratch, so they live at the customer folder root, not inside `.scout-tmp/`.
   - The `2>/dev/null || true` wrappers keep zsh's `NO_MATCH` from erroring on empty globs (see `pipeline-lessons/mcp-platform-constraints.md`); without them the bundled cleanup step fails silently and step 2 (`printf` to init the progress log) never runs.
   - **Why two repo-root sweeps survive.** `unpackaged/` is the directory the MCP `retrieve_metadata` server drops at the repo root when no manifest argument is supplied — it is SFDX-controlled, not redirectable through the `manifest` argument. `package-*.xml` at the repo root is an MCP-side sibling artifact (e.g. `package-prelude-app.xml` from prelude retrieves). Both are model-uncontrollable, so they get explicit sweeps. The model-controllable equivalents (`manifest-*.xml`, `retrieve-*.xml`, `temp-*.xml`, `*.tmp`, model-written `package-*.xml`) are now structurally impossible — sub-agents only write inside `.scout-tmp/`.
   - **If a new MCP-side orphan pattern appears at the repo root** (unrelated to model writes — i.e. the SE sees an unfamiliar repo-root file after a clean audit), add a pattern-prefixed sweep here. Inside `.scout-tmp/` no sweep additions are ever needed.
   - `find . -maxdepth 1 -name 'package-*.xml' -delete` is the zsh-safe shape — `rm -f package-*.xml` errors at glob expansion time on zsh before the redirection takes effect, so the `2>/dev/null` doesn't help. `find -delete` does its own argv handling and returns 0 on no matches.
   - **Why `.scout-tmp` is cleared with `find … -mindepth 0 -delete`, NOT `rm -rf`.** The SE workspace `.claude/settings.json` ships a catastrophic-deletion deny rule `Bash(rm -rf orgs*)`. Claude Code denies the ENTIRE compound command if any segment matches a deny glob, and a prefix-glob cannot distinguish `rm -rf orgs/<customer>/.scout-tmp` from `rm -rf orgs/<customer>` — so an `rm -rf orgs/...` scratch sweep gets the whole Pre-Spawn block hard-denied and the audit can't start. `find <dir> -mindepth 0 -delete` removes the directory and its contents (depth-first, dir last — same net effect as `rm -rf <dir>/`) but matches no deny rule. `-mindepth 0` includes the top dir itself in the delete set; `2>/dev/null || true` swallows the "No such file or directory" when the dir is absent (first run). Do NOT change this back to `rm -rf orgs/...` — it will re-trip the deny rule. (2026-06-07)
2. Initialize progress log — truncate the file and write a header so the SE-facing link opens to a non-empty file. The log now carries only coarse orchestrator phase markers + sub-agent `⚠️` failure lines (routine sub-agent heartbeats were removed — they rendered as chat-card noise during background discovery):
   ```
   printf "=== Audit started %s for %s ===\nSub-agents: standard-objects, apps-flows-agents, custom-objects\nThis log shows phase milestones + failures only.\n\n[%s] [orchestrator] Phase A — sync setup + prelude launch\n" "$(date '+%Y-%m-%d %H:%M:%S')" "[ORG_FOLDER]" "$(date '+%H:%M:%S')" > [ORG_FOLDER]/.audit-progress.log
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

   > Audit running in the background. Status → [.audit-progress.log]([ORG_FOLDER]/.audit-progress.log) — click to open; it logs phase milestones and any failures (not every step). Typical runtime 5-10 min on SDO-scale orgs. No need to watch it — I'll fold the results in once it lands.

   Substitute `[ORG_FOLDER]` with the actual resolved folder path before emitting (e.g. `orgs/voice-wt-26-wsa/.audit-progress.log`).

   The heartbeat exists because SE-facing silence is expensive — minutes of sub-agent runtime with no signal reads as "is Scout stuck?" Do not skip it. Do not paraphrase it. Do not bundle it into a later message. **If you find yourself about to call a tool here, stop — the heartbeat goes first.**

6. **Dispatch the audit-prelude sub-agent** to retrieve and parse the heavy metadata. This keeps CustomApplication/CustomObject/Profile XML out of Opus context.

   Construct the dispatch envelope (do NOT read the prompt body — the sub-agent reads it itself). The envelope is the only string passed to `Agent()`. **Substitute the absolute `PLUGIN_ROOT_ABS` resolved in Pre-Spawn step 0 for `[PLUGIN_ROOT_ABS]` below — do NOT emit the literal `${CLAUDE_PLUGIN_ROOT}`, which the sub-agent cannot expand:**

   ```
   Read your prompt file at `[PLUGIN_ROOT_ABS]/prompts/sparring/audit/prelude.md`. Also read `[PLUGIN_ROOT_ABS]/prompts/sparring/audit/shared.md` — its content substitutes for `{{AUDIT_SHARED_RULES}}`. Apply these placeholder substitutions verbatim before executing:

   {{ORG_ALIAS}} = [raw alias — for --target-org; NOT slugified]
   {{ORG_USERNAME}} = [username]
   {{ORG_FOLDER}} = [resolved ORG_FOLDER path, e.g. orgs/metro-cpq-metro]
   {{CANDIDATE_APP_FULL_NAME}} = [computed value]
   {{CANDIDATE_APP}} = [label]
   {{CANDIDATE_APP_DEVELOPER_NAME}} = [developer name]
   {{CURRENT_USER_ID}} = [user id]
   {{SCOUT_TMPDIR}} = [absolute path to [ORG_FOLDER]/.scout-tmp/]

   Execute the prompt and return the JSON block per its Output Format section.
   ```

   Spawn in the BACKGROUND (this ends Phase A — return control to the caller immediately after this spawn; do NOT block):
   - `Agent(description="Org audit: prelude (LRP resolution)", model="sonnet", prompt=[envelope above], run_in_background=true)`

   **End of Phase A.** Return to the caller (scout-sparring.md Stage 3 / showtime.md S1b) so the SE can begin answering discovery questions. The steps below (parse prelude, slice, launch parallel) execute as **Phase B** when the prelude's background completion notification arrives — which may be while an SE discovery answer is still pending. Do NOT wait synchronously here.

   **Phase B begins on the prelude background-completion notification.** Extract the fenced JSON block. Parse it.
   - `status: SUCCESS` or `status: PARTIAL` → use the returned `default_app_tabs` and `active_lrp_map`. If `PARTIAL`, log each `degradations` entry to `audit-progress.log` so the SE can see which level was lost.
   - `status: FAILED` or missing/malformed JSON → degrade the audit: set `DEFAULT_APP_TABS` to core-6, set `ACTIVE_LRP_MAP` to `[]`, and flag the SE: "Audit prelude failed — proceeding with core-6 fallback only. Retry in a fresh window if you need full LRP resolution."

   Record: `DEFAULT_APP` = `CANDIDATE_APP`, `DEFAULT_APP_DEVELOPER_NAME` = `CANDIDATE_APP_DEVELOPER_NAME`, `DEFAULT_APP_TABS` = from prelude JSON, `ACTIVE_LRP_MAP` = from prelude JSON.

   Then **slice `ACTIVE_LRP_MAP` into two per-sub-agent views** so each Sonnet only sees entries it owns:
   - `ACTIVE_LRP_MAP_STANDARD` = entries where `object` does NOT end in `__c` (standard objects — Account, Contact, Opportunity, Case, Lead, Order, MessagingSession, ServiceResource, etc.). Goes to the standard-objects sub-agent.
   - `ACTIVE_LRP_MAP_CUSTOM` = entries where `object` ends in `__c` (unmanaged custom objects). Goes to the custom-objects sub-agent.

   Managed-package objects (namespace prefix in the `object` field, e.g. `lsc4ce__SomeObject__c`) are excluded from both — Scout does not classify managed-package LRPs.

   This is the structural defense against schema drift: each sub-agent only ever sees its own scope — drift becomes structurally impossible, not just discouraged.

## Sub-Agent Dispatch

Do NOT read the sub-agent prompt bodies. Each sub-agent reads its own prompt file and `[PLUGIN_ROOT_ABS]/prompts/sparring/audit/shared.md` (the absolute path resolved in Pre-Spawn step 0). The orchestrator's job is to construct each envelope with the right placeholder values and dispatch. **Every `[PLUGIN_ROOT_ABS]` and `[PROMPT_PATH]` below must be the resolved absolute path — never the literal `${CLAUDE_PLUGIN_ROOT}`, which is empty in sub-agent context.**

Build a per-sub-agent envelope. Common placeholder values (computed by the orchestrator from earlier steps): `{{ORG_ALIAS}}` (raw — `--target-org` only), `{{ORG_FOLDER}}` (resolved folder path — every file path uses this), `{{ORG_USERNAME}}`, `{{CUSTOMER}}` (raw — object name-matching only), `{{YYYY-MM-DD}}`, `{{HHMM}}`, `{{DEFAULT_APP}}`, `{{DEFAULT_APP_TABS}}`, `{{SCOUT_TMPDIR}}`. The two LRP-aware sub-agents receive a sliced `{{ACTIVE_LRP_MAP}}`:
  - standard-objects: `ACTIVE_LRP_MAP_STANDARD`
  - custom-objects: `ACTIVE_LRP_MAP_CUSTOM`
  - apps-flows-agents: omit the placeholder (its prompt does not reference it).

Envelope template (substitute the prompt path and the placeholder block). `[PROMPT_PATH]` = `[PLUGIN_ROOT_ABS]/prompts/sparring/audit/<sub-agent>.md`:

```
Read your prompt file at `[PROMPT_PATH]`. Also read `[PLUGIN_ROOT_ABS]/prompts/sparring/audit/shared.md` — its content substitutes for `{{AUDIT_SHARED_RULES}}`. Apply these placeholder substitutions verbatim before executing:

{{ORG_ALIAS}} = [raw alias — for --target-org; NOT slugified]
{{ORG_USERNAME}} = [username]
{{ORG_FOLDER}} = [resolved ORG_FOLDER path, e.g. orgs/metro-cpq-metro]
{{CUSTOMER}} = [raw customer name — for object name-matching only, NOT paths]
{{YYYY-MM-DD}} = [date]
{{HHMM}} = [time]
{{DEFAULT_APP}} = [label]
{{DEFAULT_APP_TABS}} = [tabs JSON]
{{ACTIVE_LRP_MAP}} = [sliced map JSON — omit this line for apps-flows-agents]
{{SCOUT_TMPDIR}} = [absolute path to [ORG_FOLDER]/.scout-tmp/]

Execute the prompt and return the JSON block per its Output Format section.
```

Each entry in the sliced map carries `record_type`, `resolution_level`, and `source`. The sub-agent treats each entry as an independent LRP retrieval target — multiple record types on the same object mean multiple retrievals.

Spawn all 3 in the BACKGROUND (`[PLUGIN_ROOT_ABS]` = the absolute path from Pre-Spawn step 0):
- `Agent(description="Org audit: standard objects", model="sonnet", prompt=[envelope with PROMPT_PATH=[PLUGIN_ROOT_ABS]/prompts/sparring/audit/standard-objects.md], run_in_background=true)`
- `Agent(description="Org audit: apps/flows/agents", model="sonnet", prompt=[envelope with PROMPT_PATH=[PLUGIN_ROOT_ABS]/prompts/sparring/audit/apps-flows-agents.md], run_in_background=true)`
- `Agent(description="Org audit: custom objects", model="sonnet", prompt=[envelope with PROMPT_PATH=[PLUGIN_ROOT_ABS]/prompts/sparring/audit/custom-objects.md], run_in_background=true)`

After spawning, append ONE progress-log line (`echo "[$(date +%H:%M:%S)] [orchestrator] prelude done — 3 parallel audit agents launched" >> [ORG_FOLDER]/.audit-progress.log`) and emit **NO chat message** — a discovery ask may be pending. The live-status heartbeat was already emitted in step 5a. **This ends Phase B.** Do not block waiting for the 3 agents here; their completions will push notifications. As each arrives, you MAY collect it eagerly (hold the parsed JSON), but do NOT begin consolidation until Phase C is invoked by the caller — consolidation emits the SE-facing star summary, which must not compete with a pending discovery ask.

**Phase C — Consolidation join (invoked by the caller after the SE answers the audit-independent discovery questions).** Ensure all 3 parallel sub-agents have completed (await any whose background completion has not yet arrived). Append one coarse marker — `echo "[$(date +%H:%M:%S)] [orchestrator] Phase C — all sub-agents in, consolidating" >> [ORG_FOLDER]/.audit-progress.log` — then (do not read the progress log back — it is SE-facing only) run Post-Return Processing, Spot-Check, Consolidation, Notable Gaps, and Cleanup below, and return the consolidated summary to the caller for the star-summary emission.

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
cat [ORG_FOLDER]/audit-fragment-standard-objects.md \
    [ORG_FOLDER]/audit-fragment-apps-flows-agents.md \
    [ORG_FOLDER]/audit-fragment-custom-objects.md \
    > [ORG_FOLDER]/audit-[YYYY-MM-DD]-[HHMM].md
```

Append the Notable Gaps section (written by Opus from the JSON summaries) to the end of that file.

## Cleanup & Validation

1. Delete the 3 fragment files after successful concatenation.
2. **Star marker validation:** Grep the consolidated audit file for `★`. If 0 matches, flag to the SE: "The audit file has no ★ markers — build surface identification may have failed." Keep the progress log in place — SE may need the heartbeat history to debug which sub-agent failed to star-flag.
3. Delete the progress log — `rm -f [ORG_FOLDER]/.audit-progress.log`. Run this only after star-marker validation passes; on validation failure, leave the log so the SE can inspect sub-agent heartbeats.
4. **Symmetric workspace sweep.** Mirror the Pre-Spawn sweep exactly so a clean successful audit doesn't leave orphans in the SE workspace:
   ```
   find [ORG_FOLDER]/.scout-tmp -mindepth 0 -delete 2>/dev/null || true
   rm -rf unpackaged/ 2>/dev/null || true
   find . -maxdepth 1 -name 'package-*.xml' -delete 2>/dev/null || true
   ```
   Start-of-run cleanup is the safety net for crashed / interrupted / SE-cancelled prior runs (see `pipeline-lessons/sub-agent-architecture.md`); end-of-success cleanup is clean-path hygiene — neither fires in the other's case, so both are needed. The SE workspace at `~/claude-projects/sf-demo-scout/` is not a git repo and has no `.gitignore`, so these files are visible until swept. The bounded `.scout-tmp/` directory keeps the sweep list fixed (one `find … -delete` for the model surface, two for the MCP-server-controlled surface) as new model-invented patterns surface.
