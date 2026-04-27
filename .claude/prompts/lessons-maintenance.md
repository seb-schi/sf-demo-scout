# Lessons Handling

Canonical procedure for appending lessons to `orgs/sparring-lessons.md` / `orgs/building-lessons.md` and, when the file gets long, offering the SE a trim + Slack share. Both `/scout-sparring` and `/scout-building` Read this file when the SE approves a lesson proposal.

## Append Format

Capture the current commit SHA via `git rev-parse --short HEAD`, then append each approved lesson to the relevant file in this format:

- First line: `- YYYY-MM-DD [sha]: <rule, one sentence>` — today's date, the short SHA in square brackets, colon, then the rule.
- Optional sub-bullets, indented 2 spaces:
  - `Symptom: <verbatim error, quote, or observed behaviour that prompted the lesson>`
  - `Tried: <what failed — ≤3 lines of code or command if it adds signal>`
  - `Fix: <what worked — ≤3 lines of code or command if it adds signal>`

Soft guidance on sub-bullets: include them only when the context is actually in session. Debugging and platform-quirk lessons almost always have a verbatim error to quote — use Symptom. Pure heuristics can skip sub-bullets entirely. Don't pad — omit sub-bullets rather than invent generic filler.

After appending, count lines in the file. If it exceeds 25 lines, continue with the procedure below. Otherwise you are done.

## After Append: Trim & Share Procedure

You are here because the lessons file exceeded 25 lines after the latest append.

### Step 1: Trim Offer

Tell the SE:

> "Your lessons file is getting long ([N] lines). Want to review and trim entries that feel obvious or outdated now? I can show you the full list. (review / skip)"

If "review": display the file contents (excluding the header) as a numbered list. Ask which entries to remove. Apply removals.

If "skip": proceed to Step 2.

### Step 2: Share with Scout Team

Tell the SE:

> "Want to share your lessons with the Scout team? I'll draft a Slack message you can copy. (yes / no)"

If "yes": compose this message and display it in a fenced block for the SE to copy:

```
Posting recent Scout lessons to #sf-demo-scout — feel free to upstream anything useful into the pipeline. Each lesson carries a `[sha]` tag showing which Scout build produced it; entries without one predate version stamping.

[paste full file contents, excluding the header lines]
```

If "no": done — proceed with the rest of the session.
