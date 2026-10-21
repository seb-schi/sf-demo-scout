# Shape the demo

Read before the first question to the builder whenever the task has a story (open-ended or structured audience/moment input), or when adding a demo-facing capability to a folder with history. Read the referenced sections only as needed. Follow their content, not their stage numbers, questionnaires, acknowledgement stops, audit modes, spec writes or model choices. Write no spec.

## Draft the spine and proposal

For open-ended work, use at most two discovery rounds. Draft, not a questionnaire: use the request, structured inputs, map, inspection and cartridge findings. Read `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/value-story.md` §"Scope (read this before drafting)", §"Output Format", §"Drafting Rules", and §"Use in Scenario Proposal".

Round 1 drafts the residual message, audience and KP1–3, plus 2–6 beats. Each beat has a name, persona, stated pain and climax: the on-screen turn. Mark the proof moment where KP3 contrasts visibly with KP1, and name the record or list opened. Gaps stay visible; never invent a KP2 metric or pain. Mark assumed pains for the builder to accept deliberately.

Round 2 is the bundled confirmation: concrete items, each assigned a beat and tagged `Proves: KP[n]` or `Supports: I[n]`; objects, fields, counts and fictional names; demo-day data and its validity window; and one grounding line per item. Name every Docs finding that changed the design. Challenge an unconnected item: “X doesn't prove KP1–3 — keep or cut?” Record a kept exception; propose a `[REJECTED]` decision for a cut. Skip the mandatory half-prep-time question.

Merge the spine and proposal into one message when round 1 has no gap that changes the build. “Just build it” still gets proposed defaults with beats and a proof moment. The proof moment is required before the first write; record its source as `se-stated` or `se-confirmed` when the builder states it or accepts the proposal (the tokens keep their older names). “Go” accepts that proposal, not an unstated moment.

## Inspect with the builder's knowledge

The open-ended baseline is read-only: installed managed namespaces and industry cloud, apps/objects matching the domain nouns, Account record types and folder history. Record it in the task, never an audit file. A full audit runs only on request.

Don't search connected tools such as Slack or Google Drive on your own. When the builder asks you to look something up there, do it read-only and treat each finding as an attributed lead, not a fact: say where it came from and how current it is, and confirm anything that shapes the build with the builder or the org.

Discover selected cartridges through `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/knowledge-cartridge.md` §"Step 1 — Discover enabled, selected cartridges (cheap; always runs)" and §"Step 2 — Match the audited industry against each cartridge's Coverage". When the industry or touched industry objects match, follow §"Step 3 — Consult the matched cartridge (proactive, read-only)". Announce the consult in one line; record findings as `skill` grounding in the task and proposal. A hub worker follows the command's model-mirroring rule. When the task is industry-specific, also follow `${CLAUDE_PLUGIN_ROOT}/prompts/scout/industry-sources.md`: the product team's reviewed source comes after a covering cartridge, not instead of it.

Before the proposal, consult Docs for the industry cloud's data model if present or named, each gated item's approach, release-gated features against this org's release, and capability classifications. Fetch a page before a design decision rests on it; a search snippet is insufficient. Docs findings change the proposal, including any manual checklist steps. The command's building-half and unavailable-Docs rules apply too.

## Change an existing demo

Read the map and `reconcile-plan`'s newer logs as leads first. Say “as I have it recorded” inside an already-needed message, without adding a turn. Follow `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/iteration.md` §"Delta Conflict Check", including §"Agent source evidence gate": flows sharing an object, field-name collisions, layout crowding, permission overlaps, a weak foundation, and revived `[REJECTED]` decisions. Put findings in the bundled confirmation.

Use question 3 and the bolted-on pushback in §"Audit-independent iteration questions" only when adding a demo-facing capability and neither request nor map names its moment. Ask inside confirmation; pure repairs skip it. If the builder keeps the item without a moment, build it and propose a decision entry. For a fix naming a symptom without its exact text, use §"Symptom Follow-up (fix intent only)": ask for exact error text and when it fires; carry both into Docs research.

## Apply the audience lens

Apply what a top demo builder would, for an audience outside the company or inside it; at minimum:

- Start by building the end state that proves the outcome, whether the demo opens there or reaches it later.
- Give the opening beat to the person who must say yes; answer their first question or chief pain. Serve other audiences later.
- Every beat answers a stated pain and names a persona. Shape its data around that person; flag assumed pain.
- A vision demo emphasizes breadth and story. A proof demo uses their scenario and language with at least one live flip. A working session favors fewer, deeper beats.
- Allow roughly one beat per three to four minutes, 2–6 total, leaving room for questions. Ask slot length or demo type only if it changes beat count.
- Say only what verified data shows. For an excluded process, automate the hand-off into it; talk through the process itself.
- Treat object, tab and field labels as org-wide. Prefer a local presentation surface, with the surface and its scope grounded in Docs before proposing it. A wider relabel needs the builder's explicit yes and a decision entry. Use their named stages.
- Build in the audience's existing app. Create another only if requested or the existing app cannot support the change; ground that limitation in Docs, especially for managed apps. Record the app choice as a decision.
- Propose AI only with the audience's appetite and trusted data. If trust is the concern, show the human-in-the-loop step.

## Story record

When a story exists, `story` requires residual, audience, kp1, kp2, kp3, source (`se-stated|se-confirmed`), and beats: id, name, persona, pain, climax, proof_moment (boolean), claims (text/item pairs). Mark a proof moment; record its claims' exact read-only commands in their items' `readback`.

## Tell the verified story

After the outcome sections, use `${CLAUDE_PLUGIN_ROOT}/prompts/building/handover-brief.md` §"Demo Story" for every task with a story, one step per beat. Each beat names persona, click path, record, KP, verified claims and climax; mark the proof moment. Label unfulfilled beats planned/unverified. Drop claims without data. These beats become the map's Narrative Arc. A bounded change needs one line naming the beat it serves.
