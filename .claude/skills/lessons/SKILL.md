---
name: lessons
description: >
  Accumulated lessons from sparring and building sessions.
  Loaded by /scout-sparring and /scout-building to prevent repeated mistakes.
  Add new lessons at the end of the relevant section.
---

# Lessons Learned

## Sparring Lessons
- 2026-04-13: SDO/IDO orgs are not blank slates — always check existing objects, apps, and layouts before proposing new metadata. The default is to extend, not create.
- 2026-04-13: SEs tend to agree with gate questions reflexively. If the answer doesn't reference a specific customer statement or pain point, push back — the question hasn't done its job.
- 2026-04-13: New custom objects are rarely necessary in SDO orgs. Standard objects like Account, Contact, and Case cover most HLS scenarios. Require explicit justification before proposing anything net-new.
- 2026-04-13: The first layout returned by metadata retrieval is almost never the active one. Always query ProfileLayout before touching any layout.

## Building Lessons
- 2026-04-13: Required fields must be excluded from FLS in permission sets — the API rejects them and the deployment fails silently.
- 2026-04-13: Flow XML deployment is brittle via Metadata API. Simple record-triggered flows only. Screen flows, scheduled flows, and subflows go to SE Manual Checklist — no exceptions.
- 2026-04-13: Cross-object data seeding is unreliable. Seed one object at a time. If records need relationships, seed the parent first, query for its ID, then seed the child.
- 2026-04-13: After switching orgs, VS Code must be fully quit (CMD+Q) and reopened — reload window is not enough for MCP to pick up the new org.
- 2026-04-13: If a deployment fails twice, stop trying and add it to SE Manual Checklist. Wrestling with a broken deploy wastes context and rarely succeeds on attempt three.