# Cross-Org Extract (shared fragment)

Read + followed inline by `/scout-sparring` and `/scout-building` when the SE
wants to pull an asset (metadata, a component, a data sample, a config
pattern) OUT of a DIFFERENT org than the active demo org, to reuse it in the
demo being built.

**This does NOT switch the project default org.** Every `@salesforce/mcp` DX
tool and every `sf` CLI call takes `usernameOrAlias` (`--target-org`) as a
per-call parameter, so the source org is read by passing its alias explicitly
— the active demo org (the project default) is untouched. If the SE actually
wants to CHANGE which org they're building against, that is `switch-org.md`,
not this fragment.

The parent command has already run `workspace-bootstrap.md` (cwd is
`~/claude-projects/sf-demo-scout`) and resolved `[ORG_FOLDER]` for the active
demo org. Do NOT re-cd or re-resolve the folder here — the extraction artifact
lands in the ACTIVE demo org's folder (the org the asset is being pulled INTO).

## Step 1: Identify the source org

```bash
sf org list --json
```

Present the connected orgs (alias + username per row) and ask:

> "Which org do you want to pull from? Name one from the list, or type **new**
> to connect one first."

- **Existing org** → capture its alias. (No login, no default change — extraction
  just passes `--target-org [source-alias]` in Step 3.)
- **new** (or an org not in the list) → authenticate the source org INLINE here.
  Do NOT delegate to `switch-org.md`: its login commands carry `--set-default`
  (correct for deliberate org switching — its three callers rely on it), which
  changes the active project default, the opposite of what extraction needs.
  Instead:
  1. Ask for an alias, then: "Is this a **sandbox** or a **production/developer** org?"
  2. Tell the SE: "I'll open a browser now — log in with the SOURCE org's credentials."
  3. Run the matching command in the FOREGROUND (wait for it to return),
     **without `--set-default`** — this authenticates the source without touching
     the active default:
     - **Production / Developer** (default `login.salesforce.com`):
       ```
       sf org login web --alias [source-alias]
       ```
     - **Sandbox** (authenticates against `test.salesforce.com`):
       ```
       sf org login web --alias [source-alias] --instance-url https://test.salesforce.com
       ```
  4. If the login fails or the SE cancels, **STOP** — do NOT run any retrieve /
     SOQL-pull against any org, and do NOT claim authentication succeeded. Report
     the failure and return. Only on a confirmed successful login, capture the new
     source alias and continue.

  (Cross-reference: `switch-org.md` is the deliberate-switch path and intentionally
  DOES set the default via `--set-default`. These two login procedures must be
  reviewed together if the `sf org login web` invocation ever changes.)

Read the source org's identity for the documentation entry:
```bash
sf org display --target-org [source-alias] --json
```
Extract: **Alias**, **Username** (`username`), **Org ID** (`id`),
**Instance URL** (`instanceUrl`).

## Step 2: Document the extraction — MANDATORY, before any retrieve

**This step is a hard gate. Do NOT run any retrieve / SOQL-pull / component
fetch against the source org until the extraction entry is written to disk.**
Ask the SE (in one message):

> "Before I pull anything, let me log what we're extracting. Tell me:
> 1. **What** — the metadata type + API name, component, or data you want
>    (e.g. `Flow:Lead_Router`, the `caseDeflection` LWC, a sample of Account
>    records). List several if it's a set.
> 2. **Why** — what this becomes in the [active demo customer] demo."

Then append an entry to `[ORG_FOLDER]/cross-org-extracts.md` (the ACTIVE demo
org's folder — create the file with the `# Cross-Org Extracts` header if it
does not exist; this file is append-only, never rewrite prior entries):

```markdown
## [YYYY-MM-DD HHmm] — [short label for this extraction]

- **Source org:** [source-alias] ([source-username], Org ID [source-id])
- **Pulled into:** [active-alias] ([active demo customer])
- **What:** [metadata types + API names / component / data described by the SE]
- **Intent:** [what it becomes in this demo, in the SE's words]
- **Status:** requested
```

Use a real timestamp (`date '+%Y-%m-%d %H%M'`). Confirm the entry is written
before continuing — and if the SE cannot articulate what/why, STOP rather than
pull an undocumented asset.

## Step 3: Pull, targeting the SOURCE org explicitly

Retrieve ONLY what the entry names, always passing the source alias — never the
active default:
- Metadata: `retrieve_metadata` with `usernameOrAlias: [source-alias]`, or
  `sf project retrieve start -m [Type:ApiName] --target-org [source-alias]`.
- Data sample: `sf data query -q "[SOQL]" --target-org [source-alias] --json`.

Read `${CLAUDE_PLUGIN_ROOT}/prompts/operation-safety.md` before retrieval. Prepare
and verify a writer-owned project with `WRITER=cross-org-extract` using the resolved
workspace and selected destination customer. Pin `retrieve_metadata.directory` and
each CLI cwd to its unchanged `project_root`; pass the source alias explicitly.
Retain its `source_root` and `rollback_dir` as `SOURCE_ROOT` and `ROLLBACK_DIR`.
**Preserve every successful pull before returning, for BOTH callers.** Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build-assets.py" preserve \
  --source-root "$SOURCE_ROOT" \
  --rollback-dir "$ROLLBACK_DIR" --kind imports \
  --path "[retrieved type folder]"
```

Repeat `--path` for each retrieved type folder (e.g. `classes`, `flows`,
`lwc`). Copy whole directories so companions and nested bundle files survive;
check that the requested components actually landed, including required
companions. The helper creates a unique snapshot, compares complete paths and
content, and writes an integrity receipt only on success. A type-folder snapshot
may contain other members: it does NOT select those members for deployment.
Record the exact complete component paths separately (e.g.
`classes/CaseHelper.cls` plus its metadata companion, `lwc/casePanel`, or
`flows/Lead_Router.flow-meta.xml`).

For a data sample, save the successful query's JSON response to a uniquely named
subdirectory of scratch `data-samples/`, then preserve that directory with the
same helper. Return its durable file path as a data sample; it is NOT a metadata
staging selection or permission to seed data outside the spec.

**Failure gate:** any missing component, copy failure, comparison error, or
nonzero helper exit means preservation FAILED/unverified. Keep the originals,
record their absolute paths and the error in this extraction entry, and STOP the
parent's build before any scratch cleanup. Never substitute file counts for
content verification or report success from the mere existence of a directory.

## Step 4: Update the entry status, then return

On verified preservation, set this entry's `**Status:**` to `pulled — preserved`
and add `**Preserved:** [absolute artifact path from helper JSON]`, exact
component identities + relative paths, and `**Original scratch:** [absolute
paths]`. If retrieve failed, record `failed — retrieve: [reason]`; if retrieval
landed files but preservation did not verify, record `blocked — preservation:
[reason]` with the originals' paths. Do not flip that case to `pulled`.

Return the verified artifact path, exact component paths, and extraction intent
to the parent. The parent binds selected metadata to an existing spec item and
phase; intent is provenance, never independent deployment scope. Unselected
assets remain archived. The parent continues against the ACTIVE demo org
(default org unchanged). Do not add a consumed marker: a spec-selected import
must remain available for retries and later builds.
