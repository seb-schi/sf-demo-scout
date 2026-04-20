# Platform & Data Model Research Procedure

Execute this procedure before proposing any scenario. Grounds the design in current platform capabilities. Runs for EVERY session — industry clouds and standard orgs alike.

Read `.claude/skills/demo-docs-consultation/SKILL.md` for the NO list (items that don't need docs lookup).

## Inputs

Gather from prior stages — they drive search topic inference:
- **Audit findings:** star-flagged build surface, non-universal standard objects from `demo_surface_notes` (Stage 4), existing agents, active flows, custom objects
- **SE discovery answers:** pain points (Stage 5/5i), industry cloud named by SE (question 2), feature requests (question 6), build surface confirmation
- **Intent:** new scenario vs. iteration (determines search depth)

## Step 0 — Object Capability Pre-Flight

For every managed or industry-cloud standard object the scenario will touch, run:

Build the IN clause from: (a) non-universal standard objects with data, reported in the audit's `demo_surface_notes`, plus (b) any managed/industry objects the SE named during Stage 5 discovery.

```sql
SELECT QualifiedApiName, IsQueryable, IsCreateable, IsCustomizable
FROM EntityDefinition WHERE QualifiedApiName IN ('<object1>', '<object2>', ...)
```

Then check queue eligibility for any object the spec might route to a queue:

```sql
SELECT SobjectType FROM QueueSobject GROUP BY SobjectType
```

Record the results as explicit constraints for the spec's `### Platform Constraints` block:

```
### Platform Constraints (from pre-flight)
- Inquiry: IsCreateable=false (managed RT), not queueable
- HealthcareProvider: IsCreateable=true, not queueable
```

Any object where `IsCreateable = false` or `IsQueryable = false` or is not queueable (when the scenario needs queuing) must have its spec items adjusted BEFORE proposing the scenario. Do not defer these constraints to building — they reshape the spec.

## Step 0b — Docs Follow-Up for Restricted Objects

For each object with at least one restriction (IsCreateable/IsQueryable/IsTriggerable = false, or not queueable), run ONE `salesforce_docs_search` query: `"[ObjectName] API limitations"` or `"[ObjectName] platform restrictions developer"`. Record:
- The practical workaround (e.g., "use Database.query() with .get() for field access", "records must be created via UI", "no Apex triggers — use Flow instead")
- Whether the restriction is absolute or has conditions (e.g., "IsCreateable=false only when using managed record types — standard RT may work")

Write the workaround into the Platform Constraints block as the `Impact` line:
```
- Inquiry: IsCreateable=false (managed RT), not queueable. Impact: no API data seeding (SE manual), Apex must use Database.query() + .get() pattern, no queue routing available
```

Budget: 1 docs call per restricted object (typically 1-3 objects per scenario).

**Skip this step for standard unmanaged objects** (Account, Contact, Case, Lead, Opportunity) — their capabilities are stable and well-known.

## Step 1 — Infer Search Topics

Based on audit + discovery, infer 3-7 doc search topics. Categories:

1. **Industry data model** (if SE named an industry cloud): search for that cloud's standard data model, key objects, recommended patterns. Cross-reference against objects the audit found with data.
2. **Feature-specific** (if SE named a feature in question 6): current capabilities, setup requirements, known limitations.
3. **Agentforce patterns** (if the org has existing agents or scenario involves AI/automation): current Agent Script capabilities, available agent templates, topic routing patterns. Agentforce ships features monthly — always check current state.
4. **Data Cloud / Analytics** (if mentioned): current integration patterns, relevant features.
5. **Platform capabilities** (for non-trivial features): Flow capabilities, LWC patterns, custom metadata approaches.

For iterations: narrow to 1-3 searches focused on the specific change and its integration points.

## Step 2 — SE Refinement (conditional)

If topics are straightforward (SE named a cloud -> search its data model; SE named a feature -> search it) — skip to Step 3. The SE will review findings in Step 4.

If topics are ambiguous, numerous (>5), or span multiple unrelated areas, present and ask the SE to prioritize:

> "Before I propose a scenario, I'll research these against current Salesforce docs:
> 1. [topic — why it matters for this demo]
> 2. [topic — why]
> 3. [topic — why]
>
> Anything to add or remove from this list?"

**Wait for SE response.** Adjust topics based on their input.

## Step 3 — Execute Searches

For each confirmed topic: run `salesforce_docs_search`, capture URL + question + verdict. If a search reveals related objects, standard fields, or platform patterns that affect the data model, note them — these directly shape the scenario proposal.

Budget: 3-7 searches for new scenarios, 1-3 for iterations. If you find yourself exceeding 7, you're exploring too broadly — anchor on the SE's #1 pain point.

## Step 4 — Surface Findings

Present a structured summary of what docs revealed, grouped by impact:

> **Platform research findings:**
> - **Data model:** [which standard objects/fields map to the scenario — cite docs]
> - **Capabilities confirmed:** [features that work as expected — cite docs]
> - **Constraints discovered:** [limitations, prerequisites, or gotchas — cite docs]
> - **Recommendation:** [how findings should shape the scenario]
>
> "These findings will shape the scenario I propose next. Any questions before I proceed?"

**Wait for SE confirmation**, then return to the main command for Stage 7/7i.
