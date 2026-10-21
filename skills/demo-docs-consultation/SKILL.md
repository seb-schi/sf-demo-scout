---
name: demo-docs-consultation
description: >
  Scout's reference for when and how to consult Salesforce Docs: the YES and NO lists, citation format and degraded mode. /scout and its workers read it by path; it is not invoked on its own.
disable-model-invocation: true
---

# Salesforce Docs Consultation — Decision Tree

The Salesforce Docs MCP (`salesforce_docs_search`, `salesforce_docs_fetch`) exposes the official Salesforce documentation over HTTP. Use it when release-accuracy or error diagnosis genuinely moves the needle. Do NOT use it as ambient verification — org audit and skill-library metadata rules remain primary.

## When to Consult — YES

1. **Industry cloud data model** — the builder named an industry cloud (Health Cloud, Life Sciences Cloud, FSC, Manufacturing Cloud, etc.). Always search for that cloud's standard data model, key objects, and recommended patterns before the proposal. The builder knows which cloud; docs know which objects.
2. **Object with platform restrictions** — EntityDefinition pre-flight found IsEverCreatable/IsQueryable/IsTriggerable/IsSearchable = false, or the object is not in QueueSobject. Search for practical workarounds so the plan carries actionable guidance (not just boolean flags) into building.
3. **Unconfirmed screen-flow component** — the screen-flow design uses a component you haven't confirmed in this session (Repeater, Data Table, File Upload/Preview, Kanban Board, a custom LWC screen component, reactive cross-screen formulas). Consult docs to confirm what it does today, then deploy it and report it as deployed — needs visual QA, as `AGENTS.md` §"Docs-Gated" says. Route it to the manual checklist only when Docs confirm the step is UI-only. Never silently swap components.
4. **Release-gated feature** mentioned by the builder that you cannot immediately name the release for (e.g. "Agent Script subagents", "Data Cloud zero-copy", "Flow HTTP Callout").
5. **Novel metadata type** you haven't deployed in this session — unfamiliar XML structure, unfamiliar CLI command, unfamiliar agent-bundle element.
6. **Unfamiliar deployment error message** — the error text isn't in the loaded `orgs/lessons/` topics (`metadata-deploy.md` / `managed-packages.md`) and isn't obvious from the component name. Consult docs BEFORE the retry attempt.
7. **Builder-referenced concept by name** you don't recognise ("is [term] the right fit here?"). One search, one citation, proceed.
8. **Agentforce Agent Script capability check** — Agent Script ships features monthly; default to consulting docs for any non-trivial agent design.
9. **Capability classification (the autonomy decision)** — any requested artifact OUTSIDE Scout's known-authorable skill set (the ~25 generation skills). Consult docs to classify it into one of three build dispositions (see Scout's `AGENTS.md` §Build Boundaries → Docs-Gated): (1) metadata-authorable WITH a build-time signal → build + loop; (2) metadata-authorable with NO signal → attempt + deploy + hand off "needs visual QA"; (3) genuinely UI-only / no Metadata API path → the only hard decline, skip with the citation. Do NOT decline an artifact as "manual" or "too complex" from memory — that verdict must carry a doc citation. Artifacts a known skill already covers are authorable by definition — no classification call needed. Record the disposition and citation in the item's grounding so the build honors it.

## When to Consult — NO

1. **Custom field / object / permission set XML structure** — afv-library skills (`salesforce-development:platform-custom-field-generate`, `salesforce-development:platform-custom-object-generate`, `salesforce-development:platform-permission-set-generate`) are authoritative.
2. **Standard object structure** — org audit is truth. Docs describe a generic org; the builder's org may have managed-package or admin-made variants.
3. **Anything you just consulted this session** — cache in your head for the session; don't re-fetch.
4. **Builder-asserted customer fact** — customer context is not in Salesforce docs.
5. **Known error message already in a loaded `orgs/lessons/` topic** — the lesson is the answer.

## How to Cite

Every consultation produces a citation. Capture:
- **URL** from the doc result (the `documentPath`-resolved link)
- **Question asked** — one line, so the reader can judge relevance later
- **Verdict** — what the doc confirmed, contradicted, or left ambiguous

Citations land in:
- **Task record**: the item's `grounding` entries (source `docs`, with the URL and verdict)
- **Change log**: Docs Consulted section
- **Worker output**: `docs_consulted` array

## Degraded Mode

If `salesforce_docs_search` fails, times out or isn't exposed:
- Do NOT block. Docs MCP is optional; Scout degrades gracefully.
- When the session has a web fetch tool, fetch the page from Salesforce's own documentation (`help.salesforce.com`, `developer.salesforce.com`) instead. It counts as a Docs citation only when the fetched body itself answers the question: record its URL and your verdict, never a search snippet.
- Otherwise record the item's grounding as `ungrounded`, with a verdict starting `Docs unavailable`, and name the uncertainty in the handover. A fetched official page that answers the question needs neither.
- If Docs is *persistently* unavailable (not a one-off timeout — e.g. the server shows "needs authentication" or publishes no tools), it likely needs re-wiring: tell the builder to run `/scout-setup`, which offers to register the public Agentforce Labs Docs MCP at user scope (bare HTTP, no auth) on their yes. Until a docs source is available, record the affected items as ungrounded.

## How Much to Consult

No count applies. Consult when a YES trigger fires, and always before the first write of a new metadata type, for every ungrounded assumption and on an unfamiliar error before the retry: `prompts/scout/router-build.md` §"Ground design and claims" sets that floor. Fetch the page a decision rests on; a search snippet isn't evidence. Skip what a NO trigger covers or this session already fetched. A capability classification (trigger 9) needs the page that decides it, not a research spree. Agent Script surfaces change monthly, so a non-trivial agent design consults (trigger 8).
