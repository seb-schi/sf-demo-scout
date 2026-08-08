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

- **Existing org** → capture its alias.
- **new** (or an org not in the list) → read `${CLAUDE_PLUGIN_ROOT}/prompts/switch-org.md`
  and follow it ONLY through authenticating + listing the org (Steps 1–2). Do
  NOT let it set the source org as the project default — after auth, come back
  here and keep the active demo org as default. Capture the new source alias.

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

Use a real timestamp (`date '+%Y-%m-%d %H%M'`). Confirm to the SE the entry is
written before continuing. If the SE cannot articulate what/why, STOP — do not
pull an undocumented asset.

## Step 3: Pull, targeting the SOURCE org explicitly

Retrieve ONLY what the entry names, always passing the source alias — never the
active default:
- Metadata: `retrieve_metadata` with `usernameOrAlias: [source-alias]`, or
  `sf project retrieve start -m [Type:ApiName] --target-org [source-alias]`.
- Data sample: `sf data query -q "[SOQL]" --target-org [source-alias] --json`.

Retrieved metadata converts into the SFDX project's transient
`force-app/main/default/` scratch (same as any retrieve — it is not committed;
the demo lives in `orgs/`). Keep the pulled asset there for the parent command
to adapt/redeploy into the active org, or save a copy under `[ORG_FOLDER]/` if
the parent wants a durable artifact.

## Step 4: Update the entry status, then return

Flip the entry's `**Status:**` line for this extraction from `requested` to
`pulled — [what landed]` (or `failed — [reason]` if the retrieve errored).
Then return control to the parent command with a one-line summary of what was
pulled and where it landed. The parent continues against the ACTIVE demo org
(default org unchanged).
