You are running the **pre-spawn metadata pass** of a Salesforce demo org audit. Your scope is bounded: retrieve three metadata types, parse `<actionOverrides>` blocks out of each, and build the resolved `ACTIVE_LRP_MAP`. You do NOT do object/flow/agent discovery — that's the 3 parallel sub-agents that follow.

Target org: {{ORG_ALIAS}} ({{ORG_USERNAME}})
Progress log agent-id: prelude

Inputs (passed in by orchestrator):
- `CANDIDATE_APP_FULL_NAME` = {{CANDIDATE_APP_FULL_NAME}}
- `CANDIDATE_APP` = {{CANDIDATE_APP}}
- `CANDIDATE_APP_DEVELOPER_NAME` = {{CANDIDATE_APP_DEVELOPER_NAME}}
- `CURRENT_USER_ID` = {{CURRENT_USER_ID}}

## Tools
- `retrieve_metadata` — for CustomApplication, CustomObject, Profile XML
- `run_soql_query` — for the profile name lookup in step 2

If MCP is unavailable, stop and return a JSON error block (see Output Format).

{{AUDIT_SHARED_RULES}}

## Step 1: Retrieve confirmed app's tabs + action overrides

`retrieve_metadata` with type `CustomApplication`, member `{{CANDIDATE_APP_FULL_NAME}}`. From the retrieved XML extract two things in one parse:
- `<tabs>` elements → `DEFAULT_APP_TABS` (list of tab API names).
- `<actionOverrides>` elements where `<actionName>View</actionName>` AND `<type>Flexipage</type>` AND `<formFactor>Large</formFactor>` → for each, capture `<pageOrSobjectType>` (the object), `<content>` (the LRP DeveloperName), and `<recordType>` if present (e.g. `Account.VIP`; null if absent). Hold these as `APP_OVERRIDES`.

**On CustomApplication retrieve failure, short-circuit to core-6 immediately.** Set `DEFAULT_APP_TABS` to the 6 core objects only (`Account, Contact, Opportunity, Case, Lead, Order`), set `APP_OVERRIDES` to `[]`, and skip steps 2 and 3. Do NOT attempt AppTabDefinition, AppMenuItem, or other Tooling API fallbacks — they are unreliable for custom/managed apps. The orchestrator already confirmed the app name and computed the namespaced full name; a retrieve failure here is a genuine access boundary (unpackaged managed content, org-specific permission) and core-6 is the correct answer. Heartbeat: `⚠️ CustomApplication:{{CANDIDATE_APP_FULL_NAME}} retrieve failed — short-circuit to core-6`.

## Step 2: Retrieve org-default LRP overrides on standard objects (level 4)

`retrieve_metadata` with type `CustomObject`, members = `[Account, Contact, Opportunity, Case, Lead, Order]` plus any non-universal standard object that appears in `DEFAULT_APP_TABS`. From each retrieved object XML, parse `<actionOverrides>` elements where `<actionName>View</actionName>` AND `<type>Flexipage</type>` AND `<formFactor>Large</formFactor>` → capture `<content>` (LRP DeveloperName) and `<recordType>` (if present). Hold as `OBJECT_OVERRIDES` keyed by object.

On CustomObject retrieve failure for an individual object: log to `audit-progress.log` (`⚠️ CustomObject:[Object] retrieve failed — org-default LRP undetected`), set that object's `OBJECT_OVERRIDES` entry to empty, continue. A failure here means level-4 detection is degraded for that object only; levels 1–3 still apply.

## Step 3: Retrieve the running user's profile (levels 1–2 contribution)

Get the Profile DeveloperName from a SOQL query:
```
SELECT Profile.Name FROM User WHERE Id = '{{CURRENT_USER_ID}}' LIMIT 1
```

Profile metadata API name is the DeveloperName of the profile, not the Label — for stock profiles, `System Administrator` retrieves as `Admin`, `Standard User` as `Standard`, etc. If the SOQL returns `Profile.Name` matching one of the system labels, map it: `System Administrator → Admin`, `Standard User → Standard`, `Read Only → ReadOnly`, `Marketing User → MarketingProfile`, `Contract Manager → ContractManager`, `Solution Manager → SolutionManager`, `Standard Platform User → StandardAul`. For all other (custom) profiles, the Profile.Name is already the metadata API name — use it directly.

Then `retrieve_metadata` with type `Profile`, member `[mapped DeveloperName]`. From the retrieved XML, parse `<profileActionOverrides>` where `<actionName>View</actionName>` AND `<type>Flexipage</type>` AND `<formFactor>Large</formFactor>` → capture `<content>` (LRP), `<pageOrSobjectType>` (object), `<recordType>` (e.g. `Case.SDO_Service_Case`). Hold as `PROFILE_OVERRIDES`.

**Profile XML overflow on SDO-scale orgs is expected** — every FLS row + layoutAssignment + objectPermission lives in there. If the retrieve writes to an overflow temp file, parse it via `python3` / `jq` per `{{AUDIT_SHARED_RULES}}` Overflow File Handling — extract only `<profileActionOverrides>` blocks, ignore the rest. If the retrieve fails outright (error, not overflow), log to `audit-progress.log` (`⚠️ Profile:[Name] retrieve failed — profile-scoped LRP detection degraded`), set `PROFILE_OVERRIDES` to `[]`, continue. A failure here means level-1 detection is degraded; levels 2–4 still apply.

## Step 4: Build ACTIVE_LRP_MAP via resolution order

For each object in scope (`DEFAULT_APP_TABS` ∪ core-6), the active LRP is determined by the most-specific override present:

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

`resolution_level` values: `profile_recordtype` (level 1), `app_recordtype` (level 2), `app_default` (level 3), `org_default` (level 4), `system_default` (no override).

## Output Format

Return a single fenced JSON block — nothing else, no prose. The orchestrator parses this directly.

```json
{
  "status": "SUCCESS",
  "default_app_tabs": ["standard-Account", "standard-Contact", "..."],
  "active_lrp_map": [ /* full array per Step 4 */ ],
  "degradations": []
}
```

`status` values:
- `SUCCESS` — all 3 retrieves succeeded (or Profile overflow handled cleanly).
- `PARTIAL` — at least one retrieve failed and was handled per the inline rules (CustomApplication short-circuit to core-6, individual CustomObject failure, or Profile failure). Populate `degradations` with one entry per failure: `{"step": "1|2|3", "target": "metadata API name", "impact": "core-6 fallback | level-4 missing for [object] | level-1 disabled"}`.
- `FAILED` — unrecoverable error before Step 4 could complete. Return `default_app_tabs: []`, `active_lrp_map: []`, and a `degradations` entry describing the failure. Orchestrator will fall through to a degraded audit.

Heartbeats: emit one at start (`starting`), after each step (`step 1 done — N tabs, M app overrides`, etc.), before writing JSON (`writing JSON`), and immediately before returning (`done`). On any failure: `⚠️ <step>: <one-line reason>`.

Do NOT write a fragment file. Your output is the JSON block only — the orchestrator carries it forward.
