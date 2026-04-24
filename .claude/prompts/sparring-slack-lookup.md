# Sparring — Slack Lookup Procedure

Called when the SE names one or more setup canvases or a specific channel
during Stage 4 discovery. No curated sources file, no persistent state —
this is an in-session ask only.

## Epistemic Framing

Slack content is **medium-confidence context, not ground truth**. SE knowledge
and Salesforce docs take precedence in specs and handovers. Never assert a
Slack claim as fact — always attribute to source message + date.

Rules:
- Attribute every claim: `[#channel], [date]: [author] mentioned [X].`
- Avoid assertive framing. Not: *"The customer's top pain is X."* Yes: *"[#help-sell-medtech], 2026-03-18: @simon flagged X as a recurring concern."*
- When signals conflict across messages, surface both. Do not synthesise a winner.
- If Slack content contradicts a Salesforce doc or the org audit, flag the conflict. Slack does not override docs or the audit.
- Do not infer pain points or goals the customer has not said themselves in a quoted message. Account-team chatter is colour, not ground truth.

## Availability Probe

Run once before the first Slack tool call:
- Bash: `claude mcp list 2>/dev/null | grep -qE '^slack:.*✓ Connected' && echo OK || echo MISSING`
- On `MISSING`: tell the SE *"Slack MCP not connected — skipping the lookup. (Register via install.sh, authenticate via /mcp.)"* and return empty.
- On `OK`: proceed.

## Inputs (from SE reply in Stage 4)

- `canvas_names`: list of canvas titles the SE named (may be empty).
- `channel_name`: single channel the SE explicitly named (may be empty).

## Procedure

Budget: up to 3 canvas reads + 1 channel skim total.

### Canvases (if `canvas_names` non-empty)

For each named canvas (cap at 3):
1. `slack_search_public_and_private` with `query="<canvas name>"`, `limit=5`, filter for canvas results — the Slack MCP returns canvas objects with URLs. If no match, tell the SE *"Couldn't locate canvas '[name]' — skipping."* and continue.
2. `slack_read_canvas` on the resolved URL.
3. Extract post-spin setup steps, demo personas, known bugs, storyline scaffolding — whatever the canvas actually contains. Surface to Opus for scenario integration.

### Channel (if `channel_name` non-empty)

1. Resolve the channel via `slack_search_channels` with `query="<channel name>"`, `limit=3`. Pick the exact match. If none, tell the SE *"Couldn't resolve channel '[name]' — skipping."* and continue.
2. `slack_read_channel` on the resolved ID, `limit=20`, `response_format="concise"`.
3. Summarise anything customer-relevant in 2-3 sentences with attributed phrasing. Extract `org62.lightning.force.com` URLs as pointers for SE manual traversal.

## Output

Findings feed Stage 6 scenario proposal as **context only** — attributed,
never asserted. Canvas findings may directly shape demo storylines or
scenario integration (that is their intended use); channel findings
remain background colour. SE knowledge and Salesforce docs remain
authoritative in the spec body.

Findings also get referenced in the spec's Slack References section
(see spec-template.md) as a 1-line synthesis per source.

## Notes

- No files written. No persistent state. The SE names sources in-session.
- Iteration intent never reaches this procedure — it is gated upstream in scout-sparring Stage 4.
- If the SE names more than 3 canvases, read the first 3 and tell them *"Read the first 3 — name specific ones if you want a different set."*
