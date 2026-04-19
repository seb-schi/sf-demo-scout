# Sparring Lessons

Accumulated lessons from scout-sparring sessions. Add new lessons at the end with today's date.

- 2026-04-13: SDO/IDO orgs are not blank slates — always check existing objects, apps, and layouts before proposing new metadata. The default is to extend, not create.
- 2026-04-13: SEs tend to agree with gate questions reflexively. If the answer doesn't reference a specific customer statement or pain point, push back — the question hasn't done its job.
- 2026-04-13: New custom objects are rarely necessary in SDO orgs. Standard objects like Account, Contact, and Case cover most HLS scenarios. Require explicit justification before proposing anything net-new.
- 2026-04-13: The first layout returned by metadata retrieval is almost never the active one. Always query ProfileLayout before touching any layout.
- 2026-04-14: Always audit what the org already covers before proposing new builds — especially for booth/conference demos with multiple target motions. SEs often don't know what's already in their demo orgs. Check existing data and apps against each target motion first; iterations should build on what exists, not duplicate it.
- 2026-04-16: Booth demos are not World Tours — shape build scope to the event format. If visitors won't know Salesforce's product positioning, they need talk-track-first with a few strong screens, not polished end-to-end flows. Don't over-engineer.
- 2026-04-16: Before building, check what other SEs already have. One team session surfaced three ready-made demo assets that eliminated most of the build backlog. Sparring should always ask: "who else on the team has something close to this?"
- 2026-04-16: Industry POV sessions and internal strategy transcripts are gold for demo scenario design. Feed them into sparring to extract use cases and validate demo relevance against what the field team is actually hearing from customers.
- 2026-04-19: Life Sciences Cloud has dedicated standard objects for most pharma commercial concepts — HealthcareProvider (not Contact) for HCPs/KOLs, Inquiry (not Case) for medical inquiries and adverse events, BoardCertification for provider credentials, MedicalInsight for visit-level intelligence. Always consult LSC docs and check EntityDefinition before proposing custom fields on generic objects.
- 2026-04-19: The Inquiry standard object has an LSDO_Adverse_Event record type in LSDO orgs — this is the commercial pharmacovigilance intake path. The clinical trials Adverse Event objects (AdverseEventEntry, etc.) are a separate module and may not be enabled. Check which module is active before choosing the data model.
- 2026-04-19: When designing stress test scenarios, prioritize deployment complexity over metadata complexity. SEs can deploy custom objects and seed data themselves — they need help most with Flows, Apex, LWC, and Agentforce. Order stress tests foundation-first, but real demo priority should be complex categories first.
