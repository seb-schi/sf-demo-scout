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

---

## Propose Lessons (sparring)

Loaded by `/scout-sparring` Stage 6 just before emitting the Done message.

Review the session for moments where:
- The SE corrected a wrong assumption
- An existing-first evaluation caught unnecessary new metadata
- A gate question revealed a gap in reasoning
- The audit surfaced something unexpected
- A docs consultation contradicted or sharpened the scope

If any occurred, propose 1-3 candidate lessons:

> "Before we wrap up — I'd suggest adding these to our lessons file:
> 1. [lesson]
> 2. [lesson]
> Want me to add these, edit them, or skip?"

If the SE approves, follow the Append Format section above to append each lesson to `orgs/sparring-lessons.md`, then follow the Trim & Share procedure if triggered. If nothing noteworthy occurred, skip silently.

**Do not let `/scout-sparring` emit its Done message until this section is resolved (or skipped).**

---

## Propose Lessons (building)

Loaded by `/scout-building` Step 6b just before the Demo Handover Brief.

Review the session for:
- Two-attempt failures reported by sub-agents (what failed and why)
- Sub-agent output validation failures — especially schema-drift-with-successful-deployment (the sub-agent emitted the wrong envelope but the org probe passed). Candidate lesson: the drift vector itself (what the sub-agent emitted vs what the schema required), so the next author can tighten the prompt.
- Unexpected conflict check findings from Step 4
- SE corrections during gated confirmations
- Permission set or layout issues reported by sub-agents
- Phase 2 AND Phase 3 `discovery_notes` entries — if any describe a new platform restriction, validate/publish/activate-time workaround, or standard-action-to-Apex fallback, propose adding it to `orgs/building-lessons.md` with the exact error message or symptom as a diagnostic pattern. Phase 3 publish-time fixes (nested-if syntax, license-restricted permissions, CLI prefix requirements) are high-value lessons — they recur across every Agentforce deployment.
- `actions_unverified_in_preview` entries — if a new category appears (e.g. a new stateless-preview gap not seen before), propose a lesson so future Phase 3 prompts can pre-emptively warn.

If any occurred, propose 1-3 candidate lessons:

> "A few things worth remembering for next time:
> 1. [lesson]
> 2. [lesson]
> Add these to lessons? (yes / edit / skip)"

If approved, follow the Append Format section above to append each lesson to `orgs/building-lessons.md`, then follow the Trim & Share procedure if triggered. If the deployment was clean, skip silently.
