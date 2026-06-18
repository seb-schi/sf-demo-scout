# Lessons Handling

Canonical procedure for routing lessons into the topic-clustered
`orgs/lessons/` directory and, when a topic file gets long, offering the SE a
per-topic review. Also covers the one-time drain of legacy flat files. Both
`/scout-sparring` and `/scout-building` Read this file when the SE approves a
lesson proposal, and at the end-of-session lessons step.

The INDEX and topic files are created + loaded by
`${CLAUDE_PLUGIN_ROOT}/prompts/lessons-bootstrap.md` at session start. This
file governs WRITING lessons, not loading them.

## Append Format

Capture the current commit SHA via `git rev-parse --short HEAD`, then append
each approved lesson to the relevant TOPIC file under `orgs/lessons/` in this
format:

- First line: `- YYYY-MM-DD [sha]: <rule, one sentence>` — today's date, the short SHA in square brackets, colon, then the rule.
- Optional sub-bullets, indented 2 spaces:
  - `Symptom: <verbatim error, quote, or observed behaviour that prompted the lesson>`
  - `Tried: <what failed — ≤3 lines of code or command if it adds signal>`
  - `Fix: <what worked — ≤3 lines of code or command if it adds signal>`

A lesson is WHOLE — if it carries both a sparring rule and a building backstop,
write both halves in the one lesson, in the one topic file. Do not split by
phase.

Soft guidance on sub-bullets: include them only when the context is actually in
session. Debugging and platform-quirk lessons almost always have a verbatim
error to quote — use Symptom. Pure heuristics can skip sub-bullets entirely.
Don't pad — omit sub-bullets rather than invent generic filler.

## Routing — which topic file

Pick the topic file from the INDEX whose descriptive line best fits. If the
lesson spans two topics, put it in the more specific one (e.g. an lsc4ce
Agentforce-action block goes in `managed-packages.md`, not `agentforce.md`,
because the managed-package restriction is the load-bearing fact). If NO topic
fits, create a new topic file (`# <Topic>` header + the lesson) AND add a new
`- **<file>.md** — <descriptive line>` bullet to `orgs/lessons/INDEX.md` so it
is discoverable next session. Keep INDEX descriptive lines concrete — they are
what the next session's topic-selection judgment reads.

After appending, count the lessons (top-level `- ` bullets) in the topic file
you just wrote. If it exceeds 15, continue with the Per-Topic Review below.
Otherwise you are done with this lesson.

## Per-Topic Review (replaces the old global 25-line trim)

You are here because ONE topic file exceeded 15 lessons after the latest
append. Tell the SE:

> "Your `orgs/lessons/[topic].md` is getting long ([N] lessons). Want to review
> and trim entries that feel obvious, outdated, or now baked into Scout itself?
> I can show you just this topic. (review / skip)"

If "review": display that topic file's contents (excluding the header) as a
numbered list. Ask which entries to remove. Apply removals. A lesson that is
now enforced by a built-in prompt/skill (i.e. the team upstreamed it via
`/project-sparring`) is the prime removal candidate — its job is done.

If "skip": done.

Only the over-length topic is reviewed — never the whole corpus. This is what
makes the review actually get done.

## Slack Upstream (graduation path — decoupled from length)

Independently of length, the end-of-session lessons step MAY offer to share
newly-added lessons with the team — this is how an SE lesson graduates into a
built-in Scout behaviour (the team folds it into a prompt/skill via
`/project-sparring`). Offer this ONLY when this session added at least one new
lesson:

> "Want to share this session's new lessons with the Scout team? Upstreaming a
> recurring lesson is how it becomes a built-in Scout guardrail for everyone.
> I'll draft a Slack message you can copy. (yes / no)"

If "yes": compose this message and display it in a fenced block for the SE to
copy:

```
Posting recent Scout lessons to #sf-demo-scout — feel free to upstream anything useful into the pipeline via /project-sparring. Each lesson carries a `[sha]` tag showing which Scout build produced it; entries without one predate version stamping.

[paste the lessons added this session, with their topic file noted]
```

If "no": done.

## Legacy Flat-File Drain (one-time, self-terminating)

If `orgs/sparring-lessons.md` or `orgs/building-lessons.md` exists and is
non-empty (has lesson bullets beyond its header), offer ONCE per session, at
the end-of-session lessons step:

> "You still have legacy flat lessons files ([sparring: N / building: M]
> lessons). Want me to sort them into the topic files now? I'll cluster each by
> topic, write them into `orgs/lessons/`, and remove the flat file. (sort /
> skip)"

If "sort": for each non-empty flat file, read it, cluster each lesson into the
best-fit topic per the Routing rules above (preserving the original date +
`[sha]` prefix verbatim — do NOT restamp), append into the topic files, then
DELETE the flat file (`rm orgs/sparring-lessons.md` / `rm
orgs/building-lessons.md`). Once both flat files are gone, this offer never
fires again — the migration is self-terminating.

If "skip": leave the flat files in place; they remain authoritative and loaded
(per lessons-bootstrap Step 3) until drained. Re-offer next session.

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

> "Before we wrap up — I'd suggest adding these to our lessons:
> 1. [lesson] → [topic file]
> 2. [lesson] → [topic file]
> Want me to add these, edit them, or skip?"

If the SE approves, follow the Append Format + Routing sections above to append
each lesson to the right topic file, then run the Per-Topic Review if a topic
went over length. Then run the Slack Upstream offer (if any lesson was added)
and the Legacy Flat-File Drain offer (if legacy files remain). If nothing
noteworthy occurred, skip lesson-proposal silently — but still run the drain
offer if legacy files remain.

**Do not let `/scout-sparring` emit its Done message until this section is
resolved (or skipped).**

---

## Propose Lessons (building)

Loaded by `/scout-building` Step 6b just before the Demo Handover Brief.

Review the session for:
- Two-attempt failures reported by sub-agents (what failed and why)
- Sub-agent output validation failures — especially schema-drift-with-successful-deployment (the sub-agent emitted the wrong envelope but the org probe passed). Candidate lesson: the drift vector itself (what the sub-agent emitted vs what the schema required), so the next author can tighten the prompt.
- Unexpected conflict check findings from Step 4
- SE corrections during gated confirmations
- Permission set or layout issues reported by sub-agents
- Phase 2 AND Phase 3 `discovery_notes` entries — if any describe a new platform restriction, validate/publish/activate-time workaround, or standard-action-to-Apex fallback, propose adding it (with the exact error message or symptom as a diagnostic pattern). Managed-package restrictions → `managed-packages.md`; generic deploy/parse gotchas → `metadata-deploy.md`; Agentforce publish-time fixes (nested-if syntax, license-restricted permissions, CLI prefix requirements) → `agentforce.md`. These recur across every Agentforce deployment.
- `actions_unverified_in_preview` entries — if a new category appears (e.g. a new stateless-preview gap not seen before), propose a lesson so future Phase 3 prompts can pre-emptively warn.

If any occurred, propose 1-3 candidate lessons:

> "A few things worth remembering for next time:
> 1. [lesson] → [topic file]
> 2. [lesson] → [topic file]
> Add these to lessons? (yes / edit / skip)"

If approved, follow the Append Format + Routing sections above to append each
lesson to the right topic file, then run the Per-Topic Review if a topic went
over length. Then run the Slack Upstream offer (if any lesson was added) and the
Legacy Flat-File Drain offer (if legacy files remain). If the deployment was
clean, skip lesson-proposal silently — but still run the drain offer if legacy
files remain.
