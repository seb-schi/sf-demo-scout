# Shape the demo

Read before the first SE-facing question on open-ended work, or when adding a demo-facing capability to a folder with history. Read the referenced sections only as needed. Follow their content, not their stage numbers, questionnaires, acknowledgement stops, audit modes, spec writes or model choices. Write no spec.

## Draft the spine and proposal

For open-ended work, use at most two discovery rounds. Draft, not a questionnaire: use the request, structured inputs, map, inspection and cartridge findings. Read `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/value-story.md` §"Scope (read this before drafting)", §"Output Format", §"Drafting Rules", and §"Use in Scenario Proposal".

Round 1 drafts the residual message, audience and KP1–3, plus 2–6 beats. Each beat has a name, persona, stated pain and climax: the on-screen turn. Mark the proof moment where KP3 contrasts visibly with KP1, and name the record or list opened. Gaps stay visible; never invent a KP2 metric or pain. Assumed pains must be marked for deliberate SE acceptance.

Round 2 is the bundled confirmation: concrete items, each assigned a beat and tagged `Proves: KP[n]` or `Supports: I[n]`; objects, fields, counts and fictional names; demo-day data and its validity window; and one grounding line per item. Name every Docs finding that changed the design. Challenge an unconnected item: “X doesn't prove KP1–3 — keep or cut?” Record a kept exception; propose a `[REJECTED]` decision for a cut. Skip the mandatory half-prep-time question.

Merge the spine and proposal into one message when round 1 has no gap that changes the build. “Just build it” still gets proposed defaults with beats and a proof moment. The proof moment is required before the first write; record its source as `se-stated` or `se-confirmed` when the SE accepts the proposal. “Go” accepts that proposal, not an unstated moment.

## Inspect with SE knowledge

The open-ended baseline is read-only: installed managed namespaces and industry cloud, apps/objects matching the domain nouns, Account record types and folder history. Record it in the task, never an audit file. A full audit runs only on request.

Discover selected cartridges through `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/knowledge-cartridge.md` §"Step 1 — Discover enabled, selected cartridges (cheap; always runs)" and §"Step 2 — Match the audited industry against each cartridge's Coverage". When the industry or touched industry objects match, follow §"Step 3 — Consult the matched cartridge (proactive, read-only)". Announce the consult in one line; record findings as `skill` grounding in the task and proposal. A hub worker follows the command's model-mirroring rule.

Before the proposal, consult Docs for the industry cloud's data model if present or named, each gated item's approach, release-gated features against this org's release, and capability classifications. Fetch a page before a design decision rests on it; a search snippet is insufficient. Docs findings change the proposal, including any SE checklist steps. The command's building-half and unavailable-Docs rules apply too.

## Change an existing demo

Read the map and `reconcile-plan`'s newer logs as leads first. Say “as I have it recorded” inside an already-needed message, without adding a turn. Follow `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/iteration.md` §"Delta Conflict Check", including §"Agent source evidence gate": flows sharing an object, field-name collisions, layout crowding, permission overlaps, a weak foundation, and revived `[REJECTED]` decisions. Put findings in the bundled confirmation.

Use question 3 and the bolted-on pushback in §"Audit-independent iteration questions" only when adding a demo-facing capability and neither request nor map names its moment. Ask inside confirmation; pure repairs skip it. If the SE keeps the item without a moment, build it and propose a decision entry. For a fix naming a symptom without its exact text, use §"Symptom Follow-up (fix intent only)": ask for exact error text and when it fires; carry both into Docs research.

## Apply the presales lens

Apply what a top SE would; at minimum:

- Start by building the end state that proves the outcome, whether the demo opens there or reaches it later.
- Give the opening beat to the person who must say yes; answer their first question or chief pain. Serve other audiences later.
- Every beat answers a stated pain and names a persona. Shape its data around that person; flag assumed pain.
- A vision demo emphasizes breadth and story. A proof demo uses their scenario and language with at least one live flip. A working session favors fewer, deeper beats.
- Allow roughly one beat per three to four minutes, 2–6 total, leaving room for questions. Ask slot length or demo type only if it changes beat count.
- Say only what verified data shows. For an excluded process, automate the hand-off into it; talk through the process itself.
- Treat object, tab and field labels as org-wide. Prefer a local presentation surface, with the surface and its scope grounded in Docs before proposing it. A wider relabel needs the SE's explicit yes and a decision entry. Use their named stages.
- Build in the audience's existing app. Create another only if requested or the existing app cannot support the change; ground that limitation in Docs, especially for managed apps. Record the app choice as a decision.
- Propose AI only with customer appetite and trusted data. If trust is the concern, show the human-in-the-loop step.

## Tell the verified story

After the outcome sections, use `${CLAUDE_PLUGIN_ROOT}/prompts/building/handover-brief.md` §"Demo Story" for the open-ended Demo Story. Each beat names persona, click path, record, KP, verified claims and climax; mark the proof moment. Label unfulfilled beats planned/unverified. Drop claims without data. These beats become the map's Narrative Arc. A bounded change needs one line naming the beat it serves.
