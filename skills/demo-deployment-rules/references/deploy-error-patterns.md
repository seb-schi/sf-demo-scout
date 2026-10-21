# Known Deploy-Error Patterns

Loaded on demand by `demo-deployment-rules` (its `## Known Deploy-Error
Patterns` section points here). Read this file on a deploy failure to match
the error and apply the documented fix. Per the skill's attempt rule, a match
here counts as the next attempt — apply the fix and redeploy.

Deterministic fixes for recurring Salesforce metadata deploy errors. These are
org-agnostic parse errors (distinct from `orgs/lessons/`, which holds
org-specific gotchas). A rule-based fix is preferred over improvising — the
patch shape is exact.

Scope: covers the component types Scout's build phases deploy (FlexiPage,
PermissionSet, LWC). Integration/site metadata (NamedCredential,
ExternalCredential, CSP, Experience Cloud) is out of Scout's deploy scope and
not covered here.

## Pattern A — FlexiPage: duplicate componentInstance (Phase 1)
- **Signature:** `Element componentInstance is duplicated at this location in type ItemInstance`
- **File:** `flexipages/<Name>.flexipage-meta.xml`
- **Cause:** each `<itemInstances>` may contain exactly ONE `<componentInstance>`.
- **Fix:** split each extra `<componentInstance>` into its own `<itemInstances>`
  block inside the same `<flexiPageRegions>`. Structural reshape — no component
  is lost. Redeploy.
- **Handoff:** none — nothing dropped. Note the reshape in `discovery_notes`.

## Pattern B — FlexiPage: design-time component not found (Phase 1)
- **Signature:** `We couldn't retrieve the design time component information for component <name>` (e.g. `flexipage:recordDetails`, `c:record_detail`, `force:recordDetail`), or a missing required property on a component the edit added
- **File:** `flexipages/<Name>.flexipage-meta.xml`
- **Cause:** the component isn't available to this page in this org: a wrong or guessed API name (the standard Record Detail component's varies by org), one this page type or org doesn't offer, or a required property left out.
- **Fix:** remove the `<itemInstances>` block this edit added for that component and dry-run again. Never re-guess its name. If the error names a component that was already on the page, change nothing there: stop the edit and hand it over.
- **Convergence:** this is the record page convergence rule (`prompts/building/phase1.md` §"Lightning Record Page — Edit Rules"): a second such rejection on the same page stops the edit — drop that component too and dry-run what's left once more, so component errors cost at most three dry runs.
- **Handoff:** **Your Manual Checklist** — the page name, each dropped component and where it goes, for App Builder, in the Manual Checklist AND `issues`. The deployed edit stays AWAITING_QA for visual QA.

## Pattern C — PermissionSet: FLS on a required or master-detail field (Phase 1)
- **Signature:** `You cannot deploy to a required field: <Object>.<Field>`
- **File:** `permissionsets/<Name>.permissionset-meta.xml`
- **Cause:** required fields are implicitly read/write for anyone with
  object-level access; master-detail fields inherit access from the parent —
  neither can carry their own FLS entry.
- **Fix:** delete the `<fieldPermissions>` block for the offending field.
  Redeploy. To pre-empt: grep the object's field metadata for
  `<required>true</required>` / `<type>MasterDetail</type>` before deploying the
  permission set.
- **Handoff:** none — the field stays implicitly accessible; nothing for the builder
  to redo. Note the removed block in `issues`.

## Pattern D — LWC: literal in template expression (Phase 2)
- **Signature:** `LWC1210: Template expression doesn't allow Literal. The current component API version (62) is insufficient and must be increased to at least 66`
- **Files:** `lwc/<component>/<component>.html` (the literal) and
  `lwc/<component>/<component>.js-meta.xml` (the apiVersion).
- **Cause:** template literals like `multiple={false}` require LWC API v66+.
  NOTE: this error blames the template but the real cause is the API version —
  the most misleading error class in this library.
- **Fix (pick one):** (A) remove the literal — e.g. drop `multiple={false}` (the
  default is single), or for truthy literals use a JS-backed getter; OR (B) bump
  `<apiVersion>` in `.js-meta.xml` to `66.0`. Prefer A unless the component needs
  newer LWC features. Redeploy.
- **Handoff:** none — lossless. Note the fix choice in `discovery_notes`.

## Extending this library
When a Scout deploy hits a recurring org-agnostic parse error not covered here,
propose a new pattern (signature / file / cause / fix / handoff) to Scout's
maintainers. Org-*specific* gotchas still go to `orgs/lessons/` (topic-clustered).
