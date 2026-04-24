# Sparring — Slack Context Procedures

Read and execute when scout-sparring invokes Light Context or Deep Research.
This fragment holds the procedural body for both — the command file only
holds the gates and routing.

## Availability Probe

Before offering any Slack gate, run a single check:

- Bash: `claude mcp list 2>/dev/null | grep -qE '^slack:.*✓ Connected' && echo OK || echo MISSING`
- On `OK`: proceed to offer the gate.
- On `MISSING`: emit one line and skip both Light Context and Deep Research:
  > "Slack MCP not available — skipping Slack context. (Register via install.sh, authenticate via /mcp.)"

Do not retry. Do not attempt direct Slack tool calls as a probe — they
cost tokens and the error surface is inconsistent.

---

## Light Context (≤5 tool calls, ~3K tokens, inline in Opus)

Offer the gate as a standalone message:

> "Pull recent Slack context on **[customer]**? This runs ~3 cheap
> Slack searches to surface the account channel, recent chatter, and
> any pinned canvas. Useful if there's an existing internal narrative
> on this customer. (y/n — default n)"

On `n` or silence, skip. On `y`:

1. `slack_search_channels` with `query="[customer]"`, `limit=10`,
   `channel_types="public_channel,private_channel"`,
   `response_format="concise"`. If 0 results, tell the SE and offer
   Deep Research instead.
2. Show the top 5 channels with a number, name, type, and creation
   date. Ask: "Which channel should I read? (number / 'skip' / paste
   a channel ID)". If only 1 high-confidence hit (ZC:-prefixed shared
   channel OR channel name contains the exact customer string),
   auto-pick and tell the SE which you picked.
3. `slack_read_channel` on the chosen channel, `limit=30`,
   `response_format="concise"`.
4. `slack_search_public_and_private` with
   `query="[customer] pain OR concern OR demo"`, `limit=10`,
   `include_context=false`, `response_format="concise"`.
5. Summarise findings in 4-6 sentences: what the account team is
   focused on, any pain points surfaced, any demo history, any Org62
   pointers found (extract URLs matching `org62.lightning.force.com`).
   Offer to run Deep Research if the light pass surfaced something
   worth digging into.

Findings are then referenced in Stage 4 discovery and Stage 6 scenario
proposal.

---

## Deep Research (Sonnet sub-agent, up to 8 calls)

Offer the gate:

> "Run deep Slack research on **[customer]**? This spawns a Sonnet
> sub-agent that pulls 5-8 targeted searches and writes a brief to
> `orgs/[alias]-[customer]/`. Useful when the light pass found
> something worth digging into, or when you want a standing record
> of what Slack knows about this account. Reply `y` or `skip`."

On `skip` or silence, proceed. On `y`:

1. Construct the sub-agent prompt: read
   `.claude/prompts/sparring-slack-research.md`, substitute
   placeholders ({{CUSTOMER}}, {{ORG_ALIAS}}, {{OUTPUT_PATH}},
   {{KNOWN_CHANNELS}} — inject channel IDs from Light Context if it
   ran, empty string otherwise).
2. OUTPUT_PATH:
   `orgs/[alias]-[customer]/slack-research-[YYYY-MM-DD]-[HHmm].md`
   — use `date +%Y-%m-%d` and `date +%H%M` for the timestamp parts.
3. Spawn a Sonnet sub-agent via the `Agent` tool,
   `subagent_type=general-purpose`, `model=sonnet`, with the filled
   prompt as the description/prompt body.
4. Sub-agent writes the brief to disk and returns a fenced JSON
   summary. Parse it.
5. On `status` of `success` or `partial`: summarise for the SE in 4-6
   sentences referencing identified pains, demo history, and the brief
   file path. Pass findings into Stage 4 discovery context.
6. On `status` of `no_signal`: tell the SE "No customer-specific Slack
   signal found — proceeding without Slack context."
7. On `status` of `error`: surface the reason, offer to skip or retry
   once.

Opus never reads the raw brief or raw Slack payloads — only the JSON
summary and the file path. Brief persists on disk for SE reference
and for the spec's Slack Research Briefs citation block.

The SE can invoke Deep Research again later in the session (e.g.
after Stage 5 uncovers something worth researching).
