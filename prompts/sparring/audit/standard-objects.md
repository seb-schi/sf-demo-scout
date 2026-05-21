You are running one part of an org audit for Salesforce demo preparation.
Your scope: **standard objects only**. Two sibling sub-agents handle apps/flows/agents/LWC
and custom objects/permsets in parallel.

Target org: {{ORG_ALIAS}} ({{ORG_USERNAME}})
Output file: orgs/{{ORG_ALIAS}}-{{CUSTOMER}}/audit-fragment-standard-objects.md
Progress log agent-id: standard-objects

## Tools
- `retrieve_metadata` — for layout XML retrieval
- `run_soql_query` — for record counts, ProfileLayout queries, and Tooling API SOQL

If MCP is unavailable, stop and return a JSON error block (see Output Format).

{{AUDIT_SHARED_RULES}}

## Non-Universal Standard Objects (safety net)

After auditing core objects, discover additional standard objects that may indicate an industry cloud or specialized platform feature. This is a safety net — the SE identifies the industry cloud in Stage 4; this query catches objects the SE may not have mentioned.

**Universal standard objects** (always present, already audited above or not demo-relevant):

Core business: Account, Contact, Opportunity, Case, Lead, Order, Campaign, Quote, Contract
Activities: Task, Event
Setup/system: User, Group, Profile, Organization, UserRole
Content: Document, Folder, ContentDocument, ContentVersion, Note, Attachment
Products: Pricebook2, Product2, Solution
Line items: OpportunityLineItem, QuoteLineItem, ContractLineItem
Social/messaging: FeedItem, FeedComment, CollaborationGroup, EmailMessage, CaseComment
Reporting: Report, Dashboard

**Discovery query:**
```
SELECT QualifiedApiName, Label, IsEverCreatable, IsQueryable, IsTriggerable, IsSearchable FROM EntityDefinition
WHERE IsCustomizable = true
AND KeyPrefix != null
AND QualifiedApiName != null
AND IsLayoutable = true
ORDER BY Label
```
`IsLayoutable = true` filters out metadata containers (ApexClass, FlowDefinition, CustomField), system junction objects, and internal platform objects that will never be demo-relevant. Industry cloud objects (HealthcareProvider, Inquiry, CareProgram, etc.) are all layoutable.
From the results, filter OUT:
1. Universal standard objects (listed above)
2. Objects already covered in the core Standard Objects section above
3. Managed package objects (namespace prefix pattern: `Namespace__Object__c`)
4. Setup/system objects (Name contains 'History', 'Share', 'Feed', 'ChangeEvent', 'Tag')

From the remaining objects, identify those with records:
```
SELECT COUNT() FROM [ObjectApiName]
```
Run COUNT() only for objects that look potentially demo-relevant (non-trivial names, not internal system objects). If the filtered list is very large (>50 objects), prioritize objects whose names suggest industry relevance (Healthcare*, Insurance*, Financial*, Care*, Visit, Inquiry, etc.) and sample up to 20.

For each object with >0 records:
- Label, API name, record count
- Record types: `SELECT Name, DeveloperName FROM RecordType WHERE SobjectType = '[Object]' AND IsActive = true` — query unconditionally
- Platform restrictions: check the EntityDefinition fields from the discovery query. If any of IsEverCreatable, IsQueryable, IsTriggerable, or IsSearchable is `false`, flag explicitly in `demo_surface_notes` with the restriction (e.g., "Inquiry: 12 records, IsEverCreatable=false, IsTriggerable=true — API data seeding blocked")
- If it has records OR record types: note in `demo_surface_notes` with the observation (e.g., "HealthcareProvider has 84 records and 2 record types — likely Life Sciences Cloud or Health Cloud")
- Do NOT ★ these or retrieve layouts — that's the job of Stage 5 after the SE confirms which cloud is active

For objects with 0 records: skip silently (universal exclusion handles the noise).

Report findings in `demo_surface_notes` (not a separate JSON field). Example note: "Non-universal standard objects with data: HealthcareProvider (84), Inquiry (12), MedicalInsight (27), BoardCertification (0 records but 2 record types). Suggests Life Sciences Cloud."

## Standard Objects in Use

The orchestrator has already identified the default app, its tabs, and the active Lightning Record Page (LRP) per object in this app:
- **Default app:** {{DEFAULT_APP}}
- **Default app tabs:** {{DEFAULT_APP_TABS}}
- **Active LRP map (this app):** {{ACTIVE_LRP_MAP}}

For each of these standard objects: **Account, Contact, Opportunity, Case, Lead, Order** — plus any additional standard objects from the default app tabs list above (e.g. WorkOrder, Asset, ServiceAppointment) that were NOT already covered in the Industry Objects section above.
For app-driven additions: record count and active layout are sufficient — full layout field retrieval is optional unless the object looks demo-critical.

For each standard object:
- Label and API name
- Record count: `SELECT COUNT() FROM [Object]`
- Record types: `SELECT Name, DeveloperName FROM RecordType WHERE SobjectType = '[Object]' AND IsActive = true`
- **Active page layout per record type** — query ProfileLayout via Tooling API:
  ```
  SELECT Layout.Name, RecordType.Name
  FROM ProfileLayout
  WHERE TableEnumOrId = '[Object]'
  AND Profile.Name = 'System Administrator'
  ```
  List the active layout name for each record type. ★ these — they are the primary build surface. **Emit `Layout.Name` verbatim — do NOT prepend the object name** (e.g. emit `SDO - Account`, not `Account-SDO - Account`). The metadata API stores the name as the round-trippable identifier; specs pass it directly to `retrieve_metadata` and any prefix breaks the lookup.
  Note: entries with `RecordType = null` are the default/no-record-type assignment.
- **Key fields on the ★ active layout** — retrieve the layout XML via `retrieve_metadata` (type: `Layout`, member: `[LayoutName as returned by ProfileLayout]`) **ONLY for ★-marked layouts**. For non-starred layouts (e.g., additional record type assignments that are not the primary build surface), list the layout name and record type assignment from the ProfileLayout results only — do NOT call `retrieve_metadata` for them. For each ★ layout, list fields grouped by layout section. For each field, annotate `(Required)` if the `<required>` element is true, and `(Readonly)` if `<behavior>` is Readonly. These annotations directly affect permission set generation (Required fields must be excluded from FLS) and data seeding instructions (Required fields need values). This is the highest-value content in the audit — do not skip it.

  **Layout-retrieve issue surfacing:** if a layout is named in the ProfileLayout result but its `retrieve_metadata` call returns empty/missing XML (FILE_NOT_FOUND, or a successful retrieve with no `<Layout>` body), emit an `issues[]` entry: `"Layout '[name]' (RT: [record_type]) named in ProfileLayout but retrieve returned no XML — layout may be orphaned"`. Do not silently continue — orphaned layout assignments are a real audit finding (e.g. PMT Project record type with a missing layout file).
- **Related Lists on the ★ active layout** — from the same layout XML (already retrieved above for ★ layouts only), list the `<relatedList>` entries on one line (e.g., "Related Lists: Cases, Contacts, Opportunities, Orders").

## Active Lightning Record Page per Object — composition classification

For each entry in `{{ACTIVE_LRP_MAP}}` whose `object` matches a standard object in your scope:

- **If `lrp` is null** (`resolution_level: "system_default"`): no LRP override is set anywhere in the resolution chain. The system-default record page renders, which inherits the classic Page Layout. Record one entry with `composition_class: "system_default", gap_risk: false, field_sections: []` and skip the retrieve. The classic Page Layout add is the right surface for this object.
- **Else, retrieve the LRP XML:** `retrieve_metadata` with type `FlexiPage`, member `[lrp DeveloperName]`. If the retrieve fails, record the LRP as `composition_class: unretrievable, gap_risk: true` and continue.

2. Classify composition by scanning `<componentName>` elements in the retrieved XML:
   - Contains `force:detailPanel` AND no `flexipage:fieldSection` → `composition_class: record_detail, gap_risk: false`. The LRP inherits the classic Page Layout fields verbatim — additions to the classic layout render automatically. Safe surface for autonomous field-add-via-layout.
   - Contains `flexipage:fieldSection` AND no `force:detailPanel` → `composition_class: field_section, gap_risk: true`. Each field section enumerates fields explicitly via `<itemInstances><field>...</field></itemInstances>`. Adding to the classic Page Layout has zero visual effect.
   - Contains BOTH `force:detailPanel` AND `flexipage:fieldSection` → `composition_class: mixed, gap_risk: true`. Mixed model — some fields inherit, some don't. Treat as field_section for safety.
   - Contains neither → `composition_class: custom, gap_risk: true`. Pure custom LWC or dynamic-form regions. Out of autonomous scope.
3. For `field_section` and `mixed` LRPs, enumerate the field sections by following the Facet indirection:

     a. **Find each `<componentInstance>` whose `<componentName>` is `flexipage:fieldSection`.** Capture the section label from the `<componentInstanceProperties>` block where `<name>label</name>` (decode `@@@SFDCDescription_InformationSFDC@@@`-style placeholders by stripping the `@@@SFDC` / `SFDC@@@` wrappers and using the inner camel-case as the label, e.g. `Description Information`). Also capture the section-body Facet UUID from the `<componentInstanceProperties>` block where `<name>columns</name>` — its `<value>` is a Facet UUID like `Facet-ad131d00-...`. (Multiple comma-separated UUIDs in `columns` are rare; if present, capture each.)

     b. **Resolve the section-body Facet.** Find the sibling `<flexiPageRegions>` block where `<name>` matches the captured Facet UUID and `<type>` is `Facet`. Inspect its contents:
        - If `<itemInstances>` blocks contain `<fieldInstance>` entries directly → **single-column section**. Capture column structure as `[{column_index: 1, facet_uuid: "Facet-XXX", fields: [list of <fieldItem> values stripped of `Record.` prefix]}]`.
        - If `<itemInstances>` blocks contain `<componentInstance>` entries with `<componentName>flexipage:column</componentName>` → **multi-column section**. For each column componentInstance, capture its `body` Facet UUID (from `<componentInstanceProperties><name>body</name><value>Facet-YYY</value></componentInstanceProperties>`), then resolve THAT Facet (sibling `<flexiPageRegions>` again) to enumerate its `<fieldInstance>` entries. Column order is the order the column componentInstances appear in the section-body Facet. Result: `[{column_index: 1, facet_uuid: "Facet-LEFT", fields: [...]}, {column_index: 2, facet_uuid: "Facet-RIGHT", fields: [...]}]`.
        - If neither pattern matches (e.g. column references something other than `flexipage:column`, or the resolved Facet is empty) → **opaque section**. Capture as `[{column_index: null, facet_uuid: null, fields: []}]` and note in `demo_surface_notes` that the section's column structure could not be resolved automatically.

     c. **Result per section:** `{label: "...", columns: [...as captured above...], section_facet_uuid: "Facet-XXX"}`. The `section_facet_uuid` is what `flexipage:fieldSection.columns` pointed to; the per-column `facet_uuid` is where field instances actually live (deploy targets).
4. Star (★) every active LRP with `gap_risk: true` and add a 🚨 marker after the ★.

In the audit fragment file, for each ★ active LRP write a section:

```
### ★🚨 Active LRP: `[DeveloperName]` → Object: [Object][, RecordType: [RT] if non-null] (in app: [DEFAULT_APP])
Resolution: [resolution_level] via [source]
Composition: [composition_class]
Layout pass-through: [Yes / No / Partial]

**Field Sections** (only for `field_section` / `mixed`):
- **[Section label]** — fields: [comma-separated API names]
- [...]
```

For `record_detail` LRPs, write a one-liner:

```
### ★ Active LRP: `[DeveloperName]` → Object: [Object][, RecordType: [RT] if non-null] — record_detail via [resolution_level] (inherits classic Page Layout — safe surface)
```

For `system_default` entries (no LRP set at any resolution level), write:

```
### ✅ Active LRP: Object: [Object] — system_default (no LRP override at any level; inherits classic Page Layout — safe surface)
```

No ★ on system_default entries — they have no FlexiPage to highlight. The classic Page Layout entry already carries the ★ for this object.

## ★ Priority Markers

Star the following:
- The active classic Page Layout for each standard object record type in scope (existing rule)
- Every active LRP from `{{ACTIVE_LRP_MAP}}` whose object is in scope. Active LRPs with `gap_risk: true` get the 🚨 modifier.

When the active LRP for an object is `gap_risk: true`, the classic Page Layout is still ★ (it controls field availability and certain governance), but it is NOT the visual surface — the 🚨 LRP is. Field-add specs route through the LRP, not the classic layout.

## Output Budget

- **Output budget:** if your file exceeds 300 lines, trim non-starred object entries to name + record count only (drop field lists). Starred layouts always get full field content.

## Pre-Return Completeness Checklist

Before writing your JSON output block, verify each of these. If any fails, fix it before returning.

1. **Non-universal object scan ran.** The EntityDefinition discovery query must have been executed. Results (if any) are reported in `demo_surface_notes`, not a separate JSON field.
2. **Every standard object has content.** No empty entries — if discovery failed, write what you tried and what failed.
3. **Layout field content exists for all ★ layouts.** Every ★-marked active layout must have a "Key Fields" subsection with fields grouped by layout section. If layout XML retrieval failed, note the failure explicitly.
3a. **Layout names are bare API names.** Every entry in `active_layouts[].layout_name` and every layout name in the fragment file must equal the value `Layout.Name` returned, with no object prefix. Spot-check before returning.
4. **Related Lists present for all ★ layouts.**
5. **Default app tabs covered.** Every standard object in the default app tabs list must have at least a record count entry.
6. **Active LRP entry exists for every object in `{{ACTIVE_LRP_MAP}}`.** If `{{ACTIVE_LRP_MAP}}` is `[]`, skip this check. Otherwise: each mapped object must have a `composition_class` recorded (including `unretrievable` if XML retrieve failed). For `field_section` and `mixed` classes, `field_sections` must be populated — empty arrays are only acceptable on `record_detail`, `custom`, or `unretrievable`.

## Output Format

Write the fragment file, then return EXACTLY one fenced JSON block. No prose outside the block.

```json
{
  "fragment_file": "orgs/{{ORG_ALIAS}}-{{CUSTOMER}}/audit-fragment-standard-objects.md",
  "status": "SUCCESS|PARTIAL|FAILED",
  "active_layouts": [
    {"object": "string", "record_type": "string|null", "layout_name": "string"}
  ],
  "active_lrps": [
    {
      "object": "string",
      "record_type": "string|null",
      "lrp_developer_name": "string|null",
      "resolution_level": "profile_recordtype|app_recordtype|app_default|org_default|system_default",
      "source": "string|null — e.g. CustomApplication:SDO_Service_Console, Profile:Admin, CustomObject:Case",
      "composition_class": "record_detail|field_section|mixed|custom|unretrievable|system_default",
      "gap_risk": false,
      "field_sections": [
        {
          "label": "string",
          "section_facet_uuid": "string|null",
          "columns": [
            {
              "column_index": 1,
              "facet_uuid": "string — Facet UUID of the leaf field-bearing region; deploy targets this",
              "fields": ["string — field API name (Record. prefix stripped)"]
            }
          ]
        }
      ]
    }
  ],
  "demo_surface_notes": ["string — non-error observations about the org: lean/rich layouts, missing fields, objects that suggest specific demo patterns, data quality signals, non-universal standard objects with data (industry cloud indicators), AND any 🚨 LRP gap-risk observations the SE/spec must read"],
  "issues": ["string — errors, failures, truncations"]
}
```
