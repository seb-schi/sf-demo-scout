# Audit Orchestration Procedure

Execute this procedure to run a fresh 3-agent parallel audit.

## Pre-Spawn Setup (orchestrator runs directly)

1. Clean stale fragments: `rm -f orgs/[alias]-[customer]/audit-fragment-*.md`
2. Initialize progress log — truncate the file and write a header so the SE-facing link opens to a non-empty file:
   ```
   printf "=== Audit started %s for %s ===\nSub-agents: standard-objects, apps-flows-agents, custom-objects\n\n" "$(date '+%Y-%m-%d %H:%M:%S')" "[alias]-[customer]" > orgs/[alias]-[customer]/.audit-progress.log
   ```
3. Resolve the current user Id: `run_soql_query` with `SELECT Id FROM User WHERE Username = '[username from Stage 2]' LIMIT 1`. Record as `CURRENT_USER_ID`.
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
   - If the SE replies `skip`: set `DEFAULT_APP` to "UNKNOWN" and `DEFAULT_APP_TABS` to the 6 core objects only. Skip step 6.

6. Retrieve the confirmed app's tabs AND its action overrides: `retrieve_metadata` with type `CustomApplication`, member `[CANDIDATE_APP_FULL_NAME]`. From the retrieved XML extract two things in one parse:
   - `<tabs>` elements → `DEFAULT_APP_TABS` (list of tab API names).
   - `<actionOverrides>` elements where `<actionName>View</actionName>` AND `<type>Flexipage</type>` AND `<formFactor>Large</formFactor>` → for each, capture `<pageOrSobjectType>` (the object), `<content>` (the LRP DeveloperName), and `<recordType>` if present (e.g. `Account.VIP`; null if absent). Hold these as `APP_OVERRIDES` (working set, not yet `ACTIVE_LRP_MAP`).

   **On CustomApplication retrieve failure, short-circuit to core-6 immediately.** Set `DEFAULT_APP_TABS` to the 6 core objects only, set `APP_OVERRIDES` to `[]`, and skip steps 6a / 6b. Do NOT attempt AppTabDefinition, AppMenuItem, or other Tooling API fallbacks — they are unreliable for custom/managed apps and waste orchestrator budget. The SE already confirmed the app name and step 4 computed the namespaced full name; a retrieve failure at this point is a genuine access boundary (unpackaged managed content, org-specific permission) and core-6 is the correct answer.

6a. **Retrieve the org-default LRP overrides on standard objects (level 4).** `retrieve_metadata` with type `CustomObject`, members = `[Account, Contact, Opportunity, Case, Lead, Order]` plus any non-universal standard object that appears in `DEFAULT_APP_TABS`. From each retrieved object XML, parse `<actionOverrides>` elements where `<actionName>View</actionName>` AND `<type>Flexipage</type>` AND `<formFactor>Large</formFactor>` → capture `<content>` (LRP DeveloperName) and `<recordType>` (if present). Hold as `OBJECT_OVERRIDES` keyed by object.

On CustomObject retrieve failure for an individual object: log to `audit-progress.log` (`⚠️ CustomObject:[Object] retrieve failed — org-default LRP undetected`), set that object's `OBJECT_OVERRIDES` entry to empty, continue. A failure here means level-4 detection is degraded for that object only; levels 1–3 still apply.

6b. **Retrieve the running user's profile (levels 1–2 contribution depends on this).** Get the Profile DeveloperName from a SOQL query:
   ```
   SELECT Profile.Name FROM User WHERE Id = '[CURRENT_USER_ID]' LIMIT 1
   ```
   Profile metadata API name is the DeveloperName of the profile, not the Label — for stock profiles, `System Administrator` retrieves as `Admin`, `Standard User` as `Standard`, etc. If the SOQL returns `Profile.Name` matching one of the system labels, map it: `System Administrator → Admin`, `Standard User → Standard`, `Read Only → ReadOnly`, `Marketing User → MarketingProfile`, `Contract Manager → ContractManager`, `Solution Manager → SolutionManager`, `Standard Platform User → StandardAul`. For all other (custom) profiles, the Profile.Name is already the metadata API name — use it directly.

   Then `retrieve_metadata` with type `Profile`, member `[mapped DeveloperName]`. From the retrieved XML, parse `<profileActionOverrides>` where `<actionName>View</actionName>` AND `<type>Flexipage</type>` AND `<formFactor>Large</formFactor>` → capture `<content>` (LRP), `<pageOrSobjectType>` (object), `<recordType>` (e.g. `Case.SDO_Service_Case`). Hold as `PROFILE_OVERRIDES`.

   **Profile XML can overflow the MCP buffer on SDO-scale orgs** (every FLS row + layoutAssignment + objectPermission is in there). If the retrieve writes to an overflow temp file, parse it via `python3` / `jq` per `audit/shared.md` Overflow File Handling rules — extract only `<profileActionOverrides>` blocks, ignore the rest. If the retrieve fails outright (error, not overflow), log to `audit-progress.log` (`⚠️ Profile:[Name] retrieve failed — profile-scoped LRP detection degraded`), set `PROFILE_OVERRIDES` to `[]`, continue. A failure here means level-1 detection is degraded; levels 2–4 still apply.

6c. **Build `ACTIVE_LRP_MAP` by applying resolution order, per object.** For each object in scope (`DEFAULT_APP_TABS` ∪ core-6), the active LRP is determined by the most-specific override present:

   1. **Profile override with `<recordType>`** matching the object — level 1 hit. Use `PROFILE_OVERRIDES` entry. Multiple record types yield multiple `ACTIVE_LRP_MAP` entries for the same object (one per record type).
   2. **App override with `<recordType>`** matching the object — level 2 hit. Use `APP_OVERRIDES` entry where `recordType` is non-null and matches the object. Same multi-RT handling.
   3. **App override without `<recordType>`** — level 3 hit. Use `APP_OVERRIDES` entry where `recordType` is null.
   4. **Object org-default override** — level 4 hit. Use `OBJECT_OVERRIDES` entry. Same multi-RT handling.
   5. **No override anywhere** — system-default record page applies (`record_detail`-equivalent — inherits classic Page Layout). Emit an `ACTIVE_LRP_MAP` entry with `lrp: null, resolution_level: "system_default"` so the audit sub-agent doesn't bother retrieving anything but the spec author sees the surface is unconfigured.

   Output shape for `ACTIVE_LRP_MAP`:
   ```json
   [
     {"object": "Case", "record_type": null, "lrp": "Case_Record_Page_Zeiss", "resolution_level": "app_default", "source": "CustomApplication:SDO_Service_Console"},
     {"object": "Account", "record_type": "VIP", "lrp": "VIP_Account_Page", "resolution_level": "profile_recordtype", "source": "Profile:Admin"},
     {"object": "Lead", "record_type": null, "lrp": null, "resolution_level": "system_default", "source": null}
   ]
   ```

   `resolution_level` values: `profile_recordtype` (level 1), `app_recordtype` (level 2), `app_default` (level 3), `org_default` (level 4), `system_default` (no override). This is the breadcrumb the SE needs when an audit assignment looks wrong — they can trace which surface set the page.

   Record: `DEFAULT_APP` = `CANDIDATE_APP`, `DEFAULT_APP_DEVELOPER_NAME` = `CANDIDATE_APP_DEVELOPER_NAME`, `DEFAULT_APP_TABS` = list of tab API names, `ACTIVE_LRP_MAP` = the resolved JSON array above (or `[]` if all of 6 / 6a / 6b failed and there's nothing to resolve from).

## Sub-Agent Dispatch

Read these 3 prompt templates:
- `.claude/prompts/sparring/audit/standard-objects.md`
- `.claude/prompts/sparring/audit/apps-flows-agents.md`
- `.claude/prompts/sparring/audit/custom-objects.md`

Read `.claude/prompts/sparring/audit/shared.md` once — its content fills `{{AUDIT_SHARED_RULES}}` in all 3 sub-agent prompts.

Fill placeholders in each: `{{ORG_ALIAS}}`, `{{ORG_USERNAME}}`, `{{CUSTOMER}}`, `{{YYYY-MM-DD}}`, `{{HHMM}}`, `{{DEFAULT_APP}}`, `{{DEFAULT_APP_TABS}}`, `{{ACTIVE_LRP_MAP}}` (only the standard-objects and custom-objects sub-agents use this — apps-flows-agents may receive empty), `{{AUDIT_SHARED_RULES}}`.

Note: `{{ACTIVE_LRP_MAP}}` is the *resolved* map after applying steps 6 / 6a / 6b / 6c. Each entry now carries `record_type`, `resolution_level`, and `source`. The sub-agent treats each entry as an independent LRP retrieval target — multiple record types on the same object mean multiple retrievals.

Spawn all 3 in parallel:
- `Agent(description="Org audit: standard objects", model="sonnet", prompt=[standard objects prompt])`
- `Agent(description="Org audit: apps/flows/agents", model="sonnet", prompt=[apps/flows/agents prompt])`
- `Agent(description="Org audit: custom objects", model="sonnet", prompt=[custom objects prompt])`

**Immediately after spawning, emit this SE-facing note** (single message, exactly this format — fill in the real path):

> Audit sub-agents running in parallel. Live status → [.audit-progress.log](orgs/[alias]-[customer]/.audit-progress.log) — click to open, VS Code auto-updates as sub-agents append. Typical runtime 5-10 min on SDO-scale orgs.

Then wait for all 3 to return. Do not read the progress log — it is SE-facing only.

## Post-Return Processing

As each sub-agent returns, extract the fenced JSON block. Parse it.
- `status: SUCCESS` or `status: PARTIAL` -> collect the JSON.
- `status: FAILED` or missing/malformed JSON -> flag that sub-agent's section as failed.
- If 2+ sub-agents fail -> show the raw outputs, ask the SE to retry in a fresh window or skip the audit entirely.

Check the standard-objects sub-agent's `demo_surface_notes` for non-universal standard objects with data — these hint at which industry cloud the org uses. Record for Stage 4.

## Spot-Check Pass (2 targeted queries — always run)

Run these SOQL queries in parallel:
- `SELECT COUNT() FROM BotDefinition` — agent count
- `SELECT COUNT() FROM FlowDefinitionView WHERE IsActive = true` — active flow count

Compare each against the sub-agent JSON fields:
- **Flow count:** compare against apps/flows/agents sub-agent's `active_flow_count`. Mismatch means the sub-agent's count query failed — flag it.
- **Agent count:** compare against apps/flows/agents sub-agent's `agents_found` array length. If spot-check finds >0 but sub-agent reported 0, query `SELECT DeveloperName, MasterLabel, Type FROM BotDefinition` and include the results in the consolidated summary.
- For any mismatch >20% or zero-vs-nonzero: flag to the SE: "Sub-agent reported [X] but spot-check found [Y]. The [section] may be incomplete."

Default app is not spot-checked here — the orchestrator resolved it authoritatively in pre-spawn setup.

## Consolidation (no raw markdown reading)

Merge the 3 JSON summaries + spot-check corrections into one consolidated summary:
- `default_app`: from orchestrator pre-spawn (ground truth)
- `default_app_tabs`: from orchestrator pre-spawn (ground truth)
- `active_lrp_map`: from orchestrator pre-spawn (ground truth — same `ACTIVE_LRP_MAP` injected into sub-agents)
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
4. Remove the `unpackaged/` directory that `retrieve_metadata` drops at the repo root — `rm -rf unpackaged/`. The app XML was never needed as a working file (only the extracted `<tabs>` list matters), and leaving it accumulates stale content across sessions. Run this unconditionally — the directory is gitignored so its presence or absence carries no meaning for the SE.
