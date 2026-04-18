---
name: demo-docs-consultation
description: >
  Decision tree for when to consult the Salesforce Docs MCP during sparring
  and deployment. Loaded on-demand by scout-sparring, scout-building, and
  the phase1/2/3 sub-agent prompts. Targeted, not ambient — every call
  must earn its latency.
---

# Salesforce Docs Consultation — Decision Tree

The Salesforce Docs MCP (`salesforce_docs_search`, `salesforce_docs_fetch`) exposes the official Salesforce documentation over HTTP. Use it when release-accuracy or error diagnosis genuinely moves the needle. Do NOT use it as ambient verification — org audit and skill-library metadata rules remain primary.

## When to Consult — YES

1. **Release-gated feature** mentioned by the SE that you cannot immediately name the release for (e.g. "Agent Script subagents", "Data Cloud zero-copy", "Flow HTTP Callout").
2. **Novel metadata type** you haven't deployed in this session — unfamiliar XML structure, unfamiliar CLI command, unfamiliar agent-bundle element.
3. **Unfamiliar deployment error message** — the error text isn't in `building-lessons` and isn't obvious from the component name. Consult docs BEFORE the retry attempt.
4. **SE-referenced concept by name** you don't recognise ("is [term] the right fit here?"). One search, one citation, proceed.
5. **Agentforce Agent Script capability check** — Agent Script ships features monthly; default to consulting docs for any non-trivial agent spec.

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

- **Sparring**: aim for 0–3 consultations per session. More than 5 = you're using docs as a crutch; re-anchor on audit and SE input.
- **Building**: 0 consultations is the happy path. Consultations happen on unfamiliar-error recovery, not as a pre-flight check.
- **Phase 3 (Agentforce)** is the one exception — expect 1–2 consultations for any non-trivial agent spec (Agent Script surface changes monthly).
