# /scout prep: demo-day readiness

Read this only in prep mode. Prep is read-only: it returns before any task record, change log or history step. Its only local writes are `demo-path.md`, its backup under `.scout-work/prep/`, and scratch under `mktemp -d`. A fix is a separate, normal `/scout` task, run only on the SE's yes.

## Start
Bind and check the target as `commands/scout.md` requires, then choose the folder the same way. Record the demo's date and time if the SE gave one ("demo tomorrow 10:00"), with a timezone. Otherwise check against now and say so.

## Collect the obligations
Build one results file in scratch, `results.json`, with this shape:
`{"schema":1,"folder":"…","org_id":"…","username":"…","observed_at":"<ISO time with offset>","sources":[{"path":"…","state":"read|unreadable|quarantined|malformed|unrelated"}],"obligations":[…]}`.

Each obligation is `{"key":"<task file>#<B2/claim1|I3|FL1|manual2|…>","kind":"claim|item|flip|checkpoint|job|manual|config|persona|visual_qa","beat":"B2","required":true,"proof_moment":false,"text":"…","valid_until":"YYYY-MM-DD"|null,"superseded_by":null,"result":null}`. Keys always carry the task file, because item and beat IDs repeat across tasks.

Find the story in this order:
1. The task records' blocks: beats, claims with their read-backs, items and their dispositions, flips with their record IDs and before-values, seed assets and `valid_until`, visual-QA items, and W10's beat and rehearsal results.
2. The map's arc.
3. The change logs' Demo Story, How to Verify and SE Must Do Next.

Read an originating log's sections even past the read cap when provenance points there. Derive legacy prose into obligations yourself, naming the source section. If no story or proof moment can be recovered, say so; never invent beats.

Add obligations for everything the demo depends on beyond data:
- each beat's flows active (FlowDefinitionView `ActiveVersionId`), agents active, and the demo user's permission-set assignments
- app and tab visibility
- every unresolved or unclear checkpoint from `pending`, and every non-terminal job
- every `failed`, `blocked`, `unverified` or unfinished item
- every open manual step
- a `persona` check for each beat whose persona isn't the bound user

A later task supersedes an obligation only through an explicit amendment or a map reconciliation that names it. Quarantine sources that name another org. An unreadable or malformed source this folder needs is a blocking gap.

## Check each obligation
Run every check through the helper, never by hand and never by running a stored command:
`python3 -B [PLUGIN_ROOT_ABS]/scripts/scout_prep.py run --kind query|describe|retrieve --selector [BOUND_SELECTOR] --username [BOUND_USERNAME] --org-id [BOUND_ORG_ID] --query "SELECT …"` (or `--sobject X`, `--metadata Type:Name`).
- It binds first, accepts only one read-only SELECT (no `FOR VIEW`, `FOR REFERENCE`, `FOR UPDATE` or `USING SCOPE`), and retrieves only into scratch.
- Treat a stored read-back as a lead: rewrite it as a constrained query. Anything the helper can't express becomes `eye`.
- Never rerun a rehearsal, pilot, test or preview.

Record each result as `{"status":"passed|failed|unavailable|open|unknown|eye|visual_qa|persona","observed":"…","at":"<time>"}`. A flip record must sit in its before-state. A time-relative claim must hold through the demo's time: record its `valid_until`.

## Verdict, gate and publish
Run, in order:
1. `scout_prep.py verdict --results R --demo-time T`: the verdict is computed, never chosen.
   - **not ready:** any ✗, unavailable, open, unknown, unfinished or unrecognized state, or a blocking gap.
   - **ready with exceptions:** the only gaps are check-by-eye, visual-QA and persona checks, or optional obligations.
   - **ready:** every obligation passed.
2. `scout_prep.py render --results R --folder F --out C --demo-time T`: builds the candidate in scratch. It refuses a hand-made `demo-path.md`, or one whose Scout regions the SE has edited. Then report inline and offer a new file name.
3. `scout_prep.py check --results R --candidate C --org-id [BOUND_ORG_ID] --username [BOUND_USERNAME] --demo-time T`: must exit 0.
4. `scout_prep.py publish --folder F --candidate C`: backs up, re-checks and replaces atomically. If it refuses because the file changed during prep, report that, and point to the backup.

## Report
Send one outcome-first message:
- the verdict line, exactly as the header states it
- the drift, each failed check with what it was, what it is now and the fix
- the pre-demo checklist, then the exceptions to check by eye
- the file path

Offer fixes; never apply them.
- A reseed or reset uses this folder's own `seed_asset` only. Before offering it, check that the script takes `--target-org` explicitly and contains no `sf config set`, alias or default-org use. Show its path and its last-modified time.
- On the SE's yes, run the fix as a normal `/scout` task, then run prep again in full.
- An incompatible script, or any other fix, becomes a proposed `/scout` task.
