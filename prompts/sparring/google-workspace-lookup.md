# Sparring — Google Workspace Lookup Procedure

Called when the SE names a Google Doc or Sheet (RfP, capability map, account
plan, etc.) during Stage 3 discovery — by URL, file name, or "the RfP sheet".
No curated sources file, no persistent state — an in-session ask only. Twin of
`slack-lookup.md`.

## Epistemic Framing

Google Workspace content is **context, not ground truth** — with one nuance an
RfP makes important:

- The customer's **stated requirements** (the questions, the capability rows
  they care about) are high-signal — that IS what they asked for.
- Any **solution-fit assertion** in the doc (an SE's "Core capability",
  "Limited", "requires X add-on", a cloud-fit column) is a *hypothesis to
  validate* against Stage 4 docs + the org audit — NOT a fact to assert.

Rules:
- Attribute every claim to its source: `[<doc/sheet title>], <tab/range>:
  "<quoted requirement>".`
- Treat fit/capability claims as the SE's working hypotheses. If a claim
  conflicts with a Salesforce doc or the org audit, flag the conflict — the
  doc and audit win.
- Do not invent customer pains or goals not present in the document.
- Customer-authored requirement text may directly shape the scenario; SE/doc
  knowledge remains authoritative in the spec body.

## Availability Probe

Run once before the first Google tool call:
- Bash: `claude mcp list 2>/dev/null | grep -qE '^[[:space:]]*google-workspace:.*Connected' && echo OK || echo MISSING`
- On `MISSING`: tell the SE *"Google Workspace MCP not connected — skipping the
  lookup. (Register + authenticate via `/scout-setup`.)"* and return empty.
- On `OK`: proceed.

## Inputs (from SE reply in Stage 3)

- `doc_refs`: list of Google Doc/Sheet URLs, IDs, or titles the SE named.

## Procedure

Budget: up to 3 documents total.

For each named reference (cap at 3):
1. **Resolve to an ID.** If the SE gave a URL, extract the file ID from
   `/d/<ID>/`. If they gave a title, resolve with
   `mcp__google-workspace__search_drive_files` (`query="<title>"`,
   `page_size=5`) and pick the exact match. If none, tell the SE *"Couldn't
   locate '<name>' in your Drive — skipping."* and continue.
2. **Branch on type:**
   - **Sheet** → `mcp__google-workspace__get_spreadsheet_info` first (lists
     tabs). If the SE's URL carried a `gid`, read that tab; else if one tab,
     read it; else surface the tab list and ask which to read. Then
     `mcp__google-workspace__read_sheet_values` on the chosen tab (default
     range `A1:Z1000`; narrow if the SE named one).
   - **Doc** → `mcp__google-workspace__get_doc_as_markdown` (clean Markdown,
     preserves tables/headings).
3. Extract requirements, capability rows, open questions, embedded links —
   whatever the document actually contains. Surface to Opus for scenario
   integration, attributed per the framing above.

## Read-only by intent

This procedure calls ONLY read tools: `search_drive_files`,
`get_spreadsheet_info`, `read_sheet_values`, `get_doc_as_markdown`,
`get_drive_file_content`. The underlying connection is read-write (the gateway
binds the `-rw` provider), but the discovery lookup never writes. Writing back
to a customer document is out of scope for sparring.

## Output

**Sub-agent return contract.** This procedure is normally dispatched as a Sonnet sub-agent (see scout-sparring.md "Slack & Google Workspace lookup handling"). Return ONLY the compact attributed findings — never the raw sheet rows or doc markdown. Format each finding as `[<doc/sheet title>], [tab/range]: "[quoted requirement]".` Hold any solution-fit/capability claim as the SE's working hypothesis, not fact. If a named source could not be located or read, return a one-line note saying so. The caller (Opus) keeps your return as Stage 5 context; the raw payloads must die in your context, not the caller's.

Findings feed Stage 5 scenario proposal as **context** — attributed, with
fit-claims held as hypotheses. They also get a 1-line synthesis per source in
the spec's Google Workspace References section (see `spec-template.md`).

## Notes

- No files written. No persistent state. The SE names sources in-session.
- Iteration intent never reaches this procedure — gated upstream in Stage 3.
- If the SE names more than 3 documents, read the first 3 and say so.
