---
name: _scout-lessons
description: >
  Accumulated lessons from sparring and building sessions.
  Loaded by /scout-sparring and /scout-building to prevent repeated mistakes.
  Add new lessons at the end of the relevant section.
  Pipeline lessons live separately in pipeline-lessons/SKILL.md.
---

# Lessons Learned

## Sparring Lessons
- 2026-04-13: SDO/IDO orgs are not blank slates — always check existing objects, apps, and layouts before proposing new metadata. The default is to extend, not create.
- 2026-04-13: SEs tend to agree with gate questions reflexively. If the answer doesn't reference a specific customer statement or pain point, push back — the question hasn't done its job.
- 2026-04-13: New custom objects are rarely necessary in SDO orgs. Standard objects like Account, Contact, and Case cover most HLS scenarios. Require explicit justification before proposing anything net-new.
- 2026-04-13: The first layout returned by metadata retrieval is almost never the active one. Always query ProfileLayout before touching any layout.
- 2026-04-14: Always audit what the org already covers before proposing new builds — especially for booth/conference demos with multiple target motions. SEs often don't know what's already in their demo orgs. Check existing data and apps against each target motion first; iterations should build on what exists, not duplicate it.

## Building Lessons
- 2026-04-13: Required fields must be excluded from FLS in permission sets — the API rejects them and the deployment fails silently.
- 2026-04-13: Flow XML deployment is brittle via Metadata API. Simple record-triggered flows only. Screen flows, scheduled flows, and subflows go to SE Manual Checklist — no exceptions.
- 2026-04-13: Cross-object data seeding is unreliable. Seed one object at a time. If records need relationships, seed the parent first, query for its ID, then seed the child.
- 2026-04-13: After switching orgs, VS Code must be fully quit (CMD+Q) and reopened — reload window is not enough for MCP to pick up the new org.
- 2026-04-13: If a deployment fails twice, stop trying and add it to SE Manual Checklist. Wrestling with a broken deploy wastes context and rarely succeeds on attempt three.
- 2026-04-14: Custom fields are invisible to SOQL until FLS is granted — a field that appears in `FieldDefinition` queries will return "No such column" in SOQL until the permission set with Read FLS is deployed. Deploy the permission set first, then test SOQL access.
- 2026-04-14: Order Status picklist values vary by org and record type — don't assume "Activated" is available. This org's MedTech Order record type uses "Shipped". Always check status values against an existing order record before speccing Order data seeding.
- 2026-04-14: Agentforce Agent Script deployment via `developing-agentforce` works reliably for new agents — generate bundle, write .agent, validate, deploy backing Apex, preview, publish, activate. Every publish creates a permanent version; existing agents can be safely modified because `sf agent activate --version-number N` rolls back instantly. Deploy Agentforce last in any session — the ADLC skills consume significant context.