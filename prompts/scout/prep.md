# /scout prep: demo-day readiness

Read this only in prep mode. Prep is read-only: it returns before any task record, change log or history step. Its only local writes are `demo-path.md`, its backup under `.scout-work/prep/`, and scratch from `python3 -B [PLUGIN_ROOT_ABS]/scripts/scout_prep.py scratch`.

## Start
Bind, check the target and choose the folder as `commands/scout.md` requires, but never create a folder: with no matching folder, say so and stop. Note the demo's date and time if the SE gave one ("demo tomorrow 10:00"), with a timezone; otherwise checks run against now. Before the first check, set `started_at` from `date +%Y-%m-%dT%H:%M:%S%z`.

## Collect the obligations
Build one results file in scratch, `results.json`:
`{"schema":1,"folder":"…","org_id":"…","username":"…","started_at":"…","observed_at":"…","sources":[{"path":"…","state":"read|unreadable|quarantined|malformed|unrelated"}],"beats":[…],"constraints":["…"],"obligations":[…]}`.

Each obligation is `{"key":"<task-file>#<B2/claim1|I3|FL1|manual2|…>","kind":"claim|item|flip|checkpoint|job|manual|config|persona|visual_qa","beat":"B2","required":true,"proof_moment":false,"text":"…","valid_until":"YYYY-MM-DD"|null,"superseded_by":null,"supersession_source":null,"result":null}`. Keys always carry the task file, since IDs repeat across tasks; name another task's beat by its full key.

Find the story in this order:
1. The task records' blocks: beats, claims and read-backs, item dispositions, flips with record IDs and before-values, seed assets, `valid_until`, visual-QA items, and W10's beat and rehearsal results.
2. The map's arc.
3. The change logs' Demo Story, How to Verify and SE Must Do Next.

Follow provenance to an originating log's sections, even past the read cap. Derive legacy prose into obligations yourself, naming the source section. If no story or proof moment can be recovered, say so; never invent beats.

Map the records:
- A required `omitted` item is open.
- A recovered attempt counts by its latest disposition.
- A `failed` or `unverified` beat verdict is an `item` obligation, `failed` or `unknown`.
- A dropped optional claim is history: `"required":false,"dropped":true,"drop_source":"<path§section>"`.
- A validity window you can't derive is `unknown`.

Add obligations beyond data:
- each beat's flows active (FlowDefinitionView `ActiveVersionId`), agents active, the demo user's permission-set assignments, and app and tab visibility
- every unresolved or unclear checkpoint from `pending`, non-terminal job, `failed`, `blocked`, `unverified` or unfinished item, and open manual step
- a `persona` check for each beat whose persona isn't the bound user

A later task supersedes an obligation only through an explicit amendment or a map reconciliation that names it: set `superseded_by` to the live successor's key and `supersession_source` to its `<path§section>`. Quarantine sources that name another org. Only `read` and `unrelated` sources pass.

For the path, list the story's beats in order: `{"key":"<task-file>#B2","name":"…","persona":"…","login":"…","start":"…","steps":[{"do":"…","expect":"…","ref":"<obligation-key>"|null}],"climax":<step-number>|null,"transitions":["…"],"fallback":"…"|null}`. Name, persona and climax come from the beat; login from the record naming that persona's user, else null; start (app, tab, record) and steps from the Demo Story's click path, each `ref` naming the obligation that verifies its Expect; transitions from the arc; a fallback only where a change log names one. Put the map's org constraints in `constraints`. Give each failed obligation `was` (as built), `now` (as observed) and `fix` (the seed asset's refresh or reset, or a proposed `/scout` task).

## Check each obligation
Run every check through the helper, never by hand and never by running a stored command:
`python3 -B [PLUGIN_ROOT_ABS]/scripts/scout_prep.py run --kind query|describe|retrieve --selector [BOUND_SELECTOR] --username [BOUND_USERNAME] --org-id [BOUND_ORG_ID] --query "SELECT …"` (or `--sobject X`, `--metadata Type:Name`).
- It binds first, accepts one SELECT in its read-only grammar, and retrieves only into scratch.
- Rewrite a stored read-back as a constrained query. A check the helper refuses is `eye` for a claim, config, persona or visual-QA obligation, and `unknown` for any other kind.
- A result with `"complete":false` is `unknown`. Search a CLI error's printed name and message verbatim unless a loaded lesson covers it; record `unavailable`.
- Never rerun a rehearsal, pilot, test or preview.

Record each result as `{"status":"passed|failed|unavailable|open|unknown|eye|visual_qa|persona","observed":"…","at":"<the helper's at, else date's>"}`. A flip record must sit in its before-state. A time-relative claim must hold through the demo's time: record its `valid_until`. Set `observed_at` the same way after the last check.

## Verdict, gate and publish
Run in order, each with `--demo-time T` when the SE gave one:
1. `python3 -B [PLUGIN_ROOT_ABS]/scripts/scout_prep.py verdict --results R`: the verdict is computed, never chosen.
   - **not ready:** any ✗, unavailable, open, unknown, unfinished, expired or unrecognized state, or a blocking gap.
   - **ready with exceptions:** the only gaps are check-by-eye, visual-QA and persona checks.
   - **ready:** every obligation passed.
2. `python3 -B [PLUGIN_ROOT_ABS]/scripts/scout_prep.py render --results R --folder F`, which prints the candidate C. It refuses a hand-made `demo-path.md`, or one whose Scout regions the SE edited: then report inline and offer a new file name.
3. `python3 -B [PLUGIN_ROOT_ABS]/scripts/scout_prep.py check --results R --candidate C --org-id [BOUND_ORG_ID] --username [BOUND_USERNAME]`: must exit 0.
4. `python3 -B [PLUGIN_ROOT_ABS]/scripts/scout_prep.py publish --results R --folder F --candidate C --org-id [BOUND_ORG_ID] --username [BOUND_USERNAME]`: gates again and replaces atomically; if it refuses, say why and name the files it kept.

## Report
Send one outcome-first message:
- the verdict line, exactly as the header states it
- the drift: each failed check's was, now and fix
- the pre-demo checklist, then the exceptions to check by eye
- the file path

Offer fixes; never apply them.
- A reseed or reset uses this folder's own `seed_asset` only. Before offering it, check that the script takes `--target-org` explicitly and contains no `sf config set`, alias or default-org use. Show its path and last-modified time; recheck all three right before running it, and if anything changed, ask again.
- On the SE's yes, run the fix as a normal `/scout` task, then run prep again in full.
- An incompatible script, or any other fix, becomes a proposed `/scout` task.
