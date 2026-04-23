---
name: demo-docs-consultation
description: >
  Decision tree for when to consult the Salesforce Docs MCP — YES/NO rules,
  citation format, and degraded-mode handling.
  TRIGGER when: deciding whether to call salesforce_docs_search/fetch (sparring
  Stage 5, building error recovery, sub-agent unfamiliar-error path).
  DO NOT TRIGGER when: actually executing a docs search (the decision is already
  made), during audits, or for standard metadata generation.
---

# Salesforce Docs Consultation — Decision Tree

The Salesforce Docs MCP (`salesforce_docs_search`, `salesforce_docs_fetch`) exposes the official Salesforce documentation over HTTP. Use it when release-accuracy or error diagnosis genuinely moves the needle. Do NOT use it as ambient verification — org audit and skill-library metadata rules remain primary.

## When to Consult — YES

1. **Industry cloud data model** — the SE named an industry cloud (Health Cloud, Life Sciences Cloud, FSC, Manufacturing Cloud, etc.). Always search for that cloud's standard data model, key objects, and recommended patterns in Stage 5. The SE knows which cloud; docs know which objects.
2. **Object with platform restrictions** — EntityDefinition pre-flight found IsEverCreatable/IsQueryable/IsTriggerable/IsSearchable = false, or the object is not in QueueSobject. Search for practical workarounds so the spec carries actionable guidance (not just boolean flags) into building.
3. **Screen-flow component outside Scout's autonomous whitelist** — the SE's screen-flow design references a component Scout cannot autonomously deploy (Repeater, Data Table, File Upload/Preview, Kanban Board, custom LWC screen component, reactive cross-screen formulas). Consult docs to confirm the component's current capabilities and decide: (a) scope down to whitelisted components, or (b) route the whole screen flow to the SE Manual Checklist. Never silently swap components.
4. **Release-gated feature** mentioned by the SE that you cannot immediately name the release for (e.g. "Agent Script subagents", "Data Cloud zero-copy", "Flow HTTP Callout").
5. **Novel metadata type** you haven't deployed in this session — unfamiliar XML structure, unfamiliar CLI command, unfamiliar agent-bundle element.
6. **Unfamiliar deployment error message** — the error text isn't in `building-lessons` and isn't obvious from the component name. Consult docs BEFORE the retry attempt.
7. **SE-referenced concept by name** you don't recognise ("is [term] the right fit here?"). One search, one citation, proceed.
8. **Agentforce Agent Script capability check** — Agent Script ships features monthly; default to consulting docs for any non-trivial agent spec.

## When to Consult — NO

1. **Custom field / object / permission set XML structure** — afv-library skills (`generating-custom-field`, `generating-custom-object`, `generating-permission-set`) are authoritative.
2. **Standard object structure** — org audit is truth. Docs describe a generic org; the SE's org may have managed-package or admin-made variants.
3. **Anything you just consulted this session** — cache in your head for the session; don't re-fetch.
4. **SE-asserted customer fact** — customer context is not in Salesforce docs.
5. **Known error message already in `building-lessons`** — the lesson is the answer.

## How to Cite

Every consultation produces a citation. Capture:
- **URL** from the doc result (the `documentPath`-resolved link)
- **Question asked** — one line, so the reader can judge relevance later
- **Verdict** — what the doc confirmed, contradicted, or left ambiguous

Citations land in:
- **Spec**: Release Notes & Citations section (sparring)
- **Change log**: Docs Consulted section (building)
- **Sub-agent JSON output**: `docs_consulted` array

## Degraded Mode

If `salesforce_docs_search` fails or times out:
- Do NOT block. Docs MCP is optional; Scout degrades gracefully.
- Record the attempt in citations with `verdict: "docs unavailable"`.
- Flag the uncertainty in the spec as `[UNVERIFIED — docs MCP unavailable, SE confirm]`.

## Budget Guidance

- **Sparring Stage 5 (Platform & Data Model Research)**: 3–7 consultations for new scenarios, 1–3 for iterations. This is the primary research step — invest here. More than 7 = too broad; anchor on the SE's #1 pain point.
- **Sparring Stage 7 (residual feasibility)**: 0–2 consultations. Stage 5 should have caught most things — this is a safety net for features that emerged during scenario definition.
- **Building**: 0 consultations is the happy path. Consultations happen on unfamiliar-error recovery, not as a pre-flight check.
- **Phase 3 (Agentforce)** is the one building exception — expect 1–2 consultations for any non-trivial agent spec (Agent Script surface changes monthly).
