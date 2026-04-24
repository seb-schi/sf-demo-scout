# Slack Sources — Load & Collect

Reusable procedure for loading Slack source lists and — on first use —
collecting them from the SE. Callers: `sparring-slack-context.md`.

Read `.claude/prompts/slack-epistemic-framing.md` and apply its rules
to any Slack content this procedure produces or writes.

## Inputs

- `{{ORG_ALIAS}}` — active org alias
- `{{CUSTOMER}}` — lowercase-hyphenated customer name
- `{{ORG_FOLDER}}` — `orgs/[alias]-[customer]/`

## File Paths

- Master list: `orgs/slack-sources.md`
- Account-specific list: `{{ORG_FOLDER}}/slack-sources-{{CUSTOMER}}.md`

The account-specific filename intentionally repeats the customer — makes
it self-describing when an SE browses `orgs/[alias]-[customer]/` later.

## Step 1 — Load both files

Read both files if they exist. Parse each using these rules (same parser
for both):

- Section headers `## Channels` and `## Canvases` delimit the two source types.
- In `## Channels`: any bullet line that contains `#word` — the first `#word`
  token is the channel name (strip the `#` when passing to Slack MCP).
- In `## Canvases`: any bullet line containing a URL matching
  `https://*slack.com/docs/*` — the full URL is the canvas pointer.
- At the top of the master file, a line matching
  `Handover Canvas: (on|off)` sets the handover-canvas toggle (case-insensitive;
  anything other than `on` reads as `off`). Account-specific files do not
  carry this toggle — handover canvas is per-SE, not per-account.
- Ignore everything else (descriptions, SE notes, blank lines).

Hold the parsed results as:

```
master_channels      = [...]   # e.g. ['help-sell-medtech', 'global-medtech']
master_canvases      = [...]   # full URLs
account_channels     = [...]
account_canvases     = [...]
handover_canvas      = 'on' | 'off'
```

## Step 2 — Decide whether to collect

Four possible states for each list:
- File missing entirely.
- File exists, zero channels, zero canvases (template placeholder state).
- File exists, at least one source parsed.

Offer collection when EITHER list (master or account-specific) is in
the first two states. If both lists already carry at least one source,
skip Step 3 entirely and return the merged sources to the caller.

## Step 3 — Offer collection (SE-facing prompt)

Output this as a standalone message. Include both halves; the SE can
answer one or both or skip.

> "Before I pull Slack context, I want to know where to look. Slack is
> context only, not a substitute for your knowledge or docs, so treat
> this as seeding a watchlist — not an authority list.
>
> **(1) General sources — channels or canvas URLs you find useful across
> customers in this space.** These persist across every demo prep session.
> For example: industry help channels, regional rollups, enablement
> canvases. Reply with a comma-separated list, or `skip`.
>
> **(2) Account-specific sources for [customer] — channels or canvases
> tied specifically to this customer or opportunity.** These live in the
> customer folder. Reply with a comma-separated list, or `skip`.
>
> You can always edit these lists later — they're plain markdown in
> `orgs/slack-sources.md` and `orgs/[alias]-[customer]/slack-sources-[customer].md`."

**Wait for the SE's answer.** Accept either mixed answers (both halves
in one reply) or sequential. Parse each entry:
- Starts with `#` or is a bare word → channel name.
- Starts with `http` → canvas URL. Ask for a title if not provided:
  *"Short title for [url]? (or press Enter to use the URL as title)"*

## Step 4 — Write / update files

For each non-empty half of the answer:

### Master list

If `orgs/slack-sources.md` is missing, create it first with this exact
content:

```markdown
# Slack Sources — General

Channels and canvases useful across demo prep sessions in this account team's
Slack. Scout reads this file when pulling Slack context during /scout-sparring.

**Slack is background colour, not ground truth.** SE knowledge and Salesforce
documentation take precedence in specs and handovers. Slack content gets
attributed to source messages so you can trace where something came from —
it is not synthesised into assertive claims.

Handover Canvas: off  <!-- on / off — when on, /scout-building writes the demo handover to a new Slack canvas you own -->

## Channels

<!-- Add channels you find useful across customers. One per line. Format: - #channel-name — short note on why it helps -->

## Canvases

<!-- Add Slack canvas URLs you reference regularly. One per line. Format: - [Canvas title](full-canvas-url) — short note -->
```

Then append the new channels under `## Channels` and new canvases under
`## Canvases`. Preserve everything else (toggle line, preamble). Use
the exact bullet format:

```
- #channel-name — added YYYY-MM-DD during sparring
- [Canvas title](https://...slack.com/docs/...) — added YYYY-MM-DD during sparring
```

Substitute `YYYY-MM-DD` with today's date from `date +%Y-%m-%d`.

### Account-specific list

If `{{ORG_FOLDER}}/slack-sources-{{CUSTOMER}}.md` is missing, create it
with this minimal header:

```markdown
# Slack Sources — {{CUSTOMER}}

Channels and canvases specifically tied to this customer or opportunity.
Scout reads this alongside `orgs/slack-sources.md` during /scout-sparring.

Context only — not ground truth.

## Channels

## Canvases
```

Then append entries same format as master.

## Step 5 — Return to caller

Return the merged list (master + account-specific, deduplicated by name
or URL) to the caller, plus the `handover_canvas` toggle. Shape:

```
{
  "channels": ["help-sell-medtech", "global-medtech", "zc-acme"],
  "canvases": [
    {"title": "Evident SDO Setup", "url": "https://...slack.com/docs/..."}
  ],
  "handover_canvas": "off"
}
```

The caller decides what to do with these — typically offer a Stage-4
Slack skim, or (for `scout-building`) consult the handover_canvas flag
at Step 8c.
