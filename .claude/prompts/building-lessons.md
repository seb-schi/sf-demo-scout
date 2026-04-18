# Building Lessons

Accumulated lessons from scout-building sessions. Add new lessons at the end with today's date.

- 2026-04-13: Required fields must be excluded from FLS in permission sets — the API rejects them and the deployment fails silently.
- 2026-04-13: Flow XML deployment is brittle via Metadata API. Simple record-triggered flows only. Screen flows, scheduled flows, and subflows go to SE Manual Checklist — no exceptions.
- 2026-04-13: Cross-object data seeding is unreliable. Seed one object at a time. If records need relationships, seed the parent first, query for its ID, then seed the child.
- 2026-04-13: After switching orgs, VS Code must be fully quit (CMD+Q) and reopened — reload window is not enough for MCP to pick up the new org.
- 2026-04-13: If a deployment fails twice, stop trying and add it to SE Manual Checklist. Wrestling with a broken deploy wastes context and rarely succeeds on attempt three.
- 2026-04-14: Custom fields are invisible to SOQL until FLS is granted — a field that appears in `FieldDefinition` queries will return "No such column" in SOQL until the permission set with Read FLS is deployed. Deploy the permission set first, then test SOQL access.
- 2026-04-14: Order Status picklist values vary by org and record type — don't assume "Activated" is available. This org's MedTech Order record type uses "Shipped". Always check status values against an existing order record before speccing Order data seeding.
- 2026-04-14: Agentforce Agent Script deployment via `developing-agentforce` works reliably for new agents — generate bundle, write .agent, validate, deploy backing Apex, preview, publish, activate. Every publish creates a permanent version; existing agents can be safely modified because `sf agent activate --version-number N` rolls back instantly. Deploy Agentforce last in any session — the ADLC skills consume significant context.
