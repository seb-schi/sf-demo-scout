# Sparring — Slack Context Procedure

Read and execute when scout-sparring invokes the Stage 4 Slack offer.

Read `.claude/prompts/slack-epistemic-framing.md` and apply its rules to
everything you surface from Slack in this session.

## Availability Probe

Run this check first:

- Bash: `claude mcp list 2>/dev/null | grep -qE '^slack:.*✓ Connected' && echo OK || echo MISSING`
- On `OK`: proceed.
- On `MISSING`: emit one line and skip:
  > "Slack MCP not available — skipping Slack context. (Register via install.sh, authenticate via /mcp.)"

Do not retry. Do not attempt direct Slack tool calls as a probe.

## Step 1 — Offer the Slack skim

Before loading or collecting sources, ask the SE whether Slack context is
wanted at all. An SE who answers `n` never sees the source-collection
prompt.

> "Pull Slack context on **[customer]**? Background colour only, not a
> substitute for your knowledge or docs.
>
> - `y` — Light skim (≤5 searches, inline here)
> - `deep` — Full research brief (Sonnet sub-agent, writes file to disk)
> - `n` or silence — skip
>
> Default: `n`."

Wait for the SE's reply.

- On `n` or silence: skip. Do not offer again in this session unless asked.
- On `y` or `deep`: continue to Step 2.

## Step 2 — Load and (if needed) collect sources

Only reached when the SE said `y` or `deep`.

Read `.claude/prompts/slack-sources-collection.md` and execute its
procedure with `{{ORG_ALIAS}}`, `{{CUSTOMER}}`, `{{ORG_FOLDER}}`
substituted. It returns the merged sources object:

```
{channels: [...], canvases: [...], handover_canvas: 'on'|'off'}
```

If both source lists remain empty after the collection step (SE declined
to configure, or skipped entirely), tell the SE:

> "No Slack sources configured — skipping Slack context for this session.
> Edit `orgs/slack-sources.md` or the customer file to enable next time."

Then skip. Do not attempt an unscoped search.

## Step 3 — Execute based on the Step 1 reply

### Reply `y` — Light skim (inline, ≤5 tool calls)

1. For each canvas in sources: `slack_read_canvas` (budget: up to 2 canvases).
2. `slack_search_public_and_private` with
   `query='"[customer]"'`,
   `channels=[resolved channel IDs]` (resolve names to IDs via one
   `slack_search_channels` call first if needed),
   `limit=10`, `include_context=false`, `response_format="concise"`.
3. If the search returns a relevant thread, `slack_read_thread` on it
   (budget: 1 thread).
4. Summarise in 4-6 sentences with attributed phrasing per the framing
   fragment. Extract any `org62.lightning.force.com` URLs as Org62
   pointers for the SE to traverse manually.
5. Close with: *"Slack surfaced these — treat as starting points, not
   confirmed facts. Anything I should dig into before we move on?"*

Findings feed Stage 4 discovery and Stage 6 scenario proposal. Never
promote a Slack finding into the spec's Business story or Pain point
without the SE restating it in their own words.

### Reply `deep` — Deep Research sub-agent

1. Construct the sub-agent prompt: read
   `.claude/prompts/sparring-slack-research.md`, substitute
   placeholders ({{CUSTOMER}}, {{ORG_ALIAS}}, {{OUTPUT_PATH}},
   {{SLACK_SOURCES}}).
2. OUTPUT_PATH:
   `orgs/[alias]-[customer]/slack-research-[YYYY-MM-DD]-[HHmm].md`
   — use `date +%Y-%m-%d` and `date +%H%M`.
3. SLACK_SOURCES: render as markdown list combining channels (as
   `- #name`) and canvases (as `- [title](url)`), or the literal string
   `none` if both lists are empty.
4. Spawn a Sonnet sub-agent via the `Agent` tool,
   `subagent_type=general-purpose`, `model=sonnet`, with the filled
   prompt as the prompt body.
5. Sub-agent writes the brief to disk and returns a fenced JSON summary.
   Parse it. Do not read the raw brief — only the JSON + file path.
6. On `status` of `success` or `partial`: summarise for the SE in 4-6
   sentences with attributed phrasing. Include a reminder line:
   *"Full brief at [path] — remember, this is context, not truth."*
7. On `status` of `no_signal`: *"No customer-specific Slack signal found
   in your sources — proceeding without Slack context."*
8. On `status` of `error`: surface reason, offer skip or retry once.

## Notes for the caller

- This procedure is gated by the SE every time — never auto-run.
- Iteration intent skips this entirely; the caller checks intent
  before invoking this file.
- The handover_canvas toggle returned by slack-sources-collection is
  not consumed here — scout-building Step 8c reads the toggle
  directly from `orgs/slack-sources.md` at deploy time.
