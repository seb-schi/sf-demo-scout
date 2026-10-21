# Lessons Handling

Canonical procedure for routing lessons into the topic-clustered
`orgs/lessons/` directory and, when a topic file gets long, offering the builder a
per-topic review. `/scout` reads it at its lessons step
(`prompts/scout/history.md`) and when the builder approves a lesson proposal.

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
because the managed-package restriction is the load-bearing fact).

If NO existing topic fits, do NOT silently mint one — propose it to the builder
first, so the taxonomy stays coherent and near-duplicate topics
(`permissions.md` vs a later `fls-and-sharing.md`) don't accumulate:

> "This lesson doesn't fit any existing topic. I'd start a new one:
> **`<file>.md` — <proposed descriptive line>**. Use that name, rename it, or
> point me at an existing topic instead?"

On approval (or a rename), create the topic file (`# <Topic>` header + the
lesson) AND add a new `- **<file>.md** — <descriptive line>` bullet to
`orgs/lessons/INDEX.md` so it is discoverable next session. Keep INDEX
descriptive lines concrete — they are what the next session's topic-selection
judgment reads. If the builder points at an existing topic instead, file it there.

After appending, count the lessons (top-level `- ` bullets) in the topic file
you just wrote. If it exceeds 15, continue with the Per-Topic Review below.
Otherwise you are done with this lesson.

## Per-Topic Review (replaces the old global 25-line trim)

You are here because ONE topic file exceeded 15 lessons after the latest
append. A long topic has two cures — trimming dead entries, or splitting a
topic that has quietly become two or three. Before offering, scan the topic:
if its lessons cluster into distinct sub-themes (e.g. `agentforce.md` splitting
into agent-build vs. agent-runtime-diagnostics), lead with the split option;
otherwise lead with trim.

> "Your `orgs/lessons/[topic].md` is getting long ([N] lessons). Two options —
> I can show you just this topic either way:
> - **trim** — remove entries that feel obvious, outdated, or now baked into
>   Scout itself
> - **split** — this looks like [N] sub-themes ([name them]); break it into
>   separate topics
> (trim / split / skip)"

If "trim": display the topic file's contents (excluding the header) as a
numbered list. Ask which entries to remove. Apply removals. A lesson that a
built-in prompt or skill now enforces (Scout's maintainers took it upstream) is
the prime removal candidate — its job is done.

If "split": propose the new topic names + which lessons go to each, get the builder's
sign-off, then create the new topic files (preserving each lesson's date +
`[sha]` verbatim), update `orgs/lessons/INDEX.md` (add the new bullets, remove
or rewrite the old one), and delete the now-empty original if everything moved.

If "skip": done.

Only the over-length topic is reviewed — never the whole corpus. This is what
makes the review actually get done.

## Propose Lessons (building)

Read by `/scout`'s history step (`prompts/scout/history.md`), before the handover.

Review the session for:
- Items that needed more than one attempt, or ended `failed` (what failed, why, and the fix that worked)
- Sub-agent output validation failures — especially schema-drift-with-successful-deployment (the sub-agent emitted the wrong envelope but the org probe passed). Candidate lesson: the drift vector itself (what the sub-agent emitted vs what the schema required), so the next author can tighten the prompt.
- Unexpected conflict check findings from Step 4
- The builder's corrections during gated confirmations
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
over length. Then run the Legacy Flat-File Drain offer (if legacy files remain). If the deployment was
clean, skip lesson-proposal silently — but still run the drain offer if legacy
files remain.
