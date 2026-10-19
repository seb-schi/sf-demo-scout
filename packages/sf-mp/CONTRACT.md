# sf-mp: the common-org contract
How sf-mp decides who may write to the common org, and how an interrupted write is settled. The code follows this file; comments cite it by section.

## 1. One authority
`.mp/config.json` binds a Salesforce project (the kit project) to one common org: `{schema, commonOrgId, session, authority, testLevel, createdAt}`. With `authority: lane`, one checkout on one machine is the org's lane. Only the lane writes to the common org, and it holds one slot for that org: a second writer waits or is refused. `board` (several machines writing directly through a shared claim) is reserved and refused.

## 2. Where the state lives
**Shared, in Git:** `.mp/config.json` and `.mp/owners.yaml` (who owns which component).

**The lane's own state, local and ignored by Git,** so a branch switch can never revert a baseline or hide an open operation:

| Path | What it holds |
|---|---|
| `.mp/baselines/<orgId>.json` | One baseline per component (§4 rule 3), plus the last deploy's source revision |
| `.mp/journal/open-<orgId>.json` | The org's open operation, at most one. Its existence is the slot. It's published complete (a flushed temporary file, hard-linked into place, which fails if a slot exists), and every later change replaces it atomically after checking it's still the same operation |
| `.mp/journal/<opId>.json` | A settled operation, written exclusively before the slot is removed |
| `.mp/merge/<orgId>/…` | The org's copy of a component that differs from your working tree, kept for a merge |
| `.mp/backups/<opId>/` | The backup: the fresh retrieve taken just before dispatch |

**On the machine:** `<sf data dir>/sf-mp/bound-orgs.json` lists every org bound here. A lane entry names its lane checkout (`{lane, boundAt}`); a guard-only entry names the checkout that registered it (`{role: "guard", checkout, boundAt}`). The guard protects every listed org from commands run in any folder. Updates are serialized and atomic, and org IDs compare on their first 15 characters.

## 3. The operation record
`{schema, opId, session, actor, platformUser, holder {pid, host, startedAt}, tool, kind, checkOnly, steward, targetOrgId, components[], approvals[], candidate {revision, digest, hashes, paths}, options, baselineRefs, backupRef, state, jobId?, transitions[{state, at}], createdAt, settledAt?, result?, readback?, note?}`
- `kind` is `deploy` (or `retrieve` while a retrieve holds the slot).
- `actor` is the person running the lane (Git's `user.name`); `platformUser` is the org username. `approvals` records an owner's yes for a component they own, tied to the candidate revision.
- `state` moves `intent` → `submitting` → `dispatched` → `settled-success` | `settled-failed` | `unresolved` → `reconciled-success` | `reconciled-failed`. `intent` means nothing has been sent; `submitting` is flushed immediately before the deploy is sent, so an operation without it was demonstrably never submitted.

## 4. Rules
1. **Intent before dispatch.** The slot is taken by publishing `open-<orgId>.json` exclusively. If that fails, or the intent can't be written, the operation is refused. The job ID is recorded the moment it exists.
2. **An open operation blocks** every new write to its org, even when its file is unreadable.
3. **Baselines.** Each component's baseline records the org content (`present` with a hash, last modified by and when; `confirmed-absent`; or `unknown`) and the committed source it maps to (a hash, and a commit that holds it when known). A baseline is recorded only when the kit can tie the working tree to it:
   - a retrieve that wrote the local files, or found them identical
   - a settled real deploy, from its verified read-back
   - `--merged`, run after you merged the org's saved copy and committed the result

   Refreshing a baseline never legitimizes a stale candidate.
4. **Freshness.** The candidate is HEAD's committed content for the named components; uncommitted changes in them are refused. Before dispatch every component is retrieved fresh (R) and checked against its baseline (B):
   - B `present`: R must hash the same. Otherwise stop, showing who, when and the difference.
   - B `confirmed-absent`: R must still be absent; then the create is allowed.
   - B `unknown` or missing: block.
   - HEAD's history must contain B's source, by commit or by content (which covers amended and rebased history).
5. **Settling.** Success needs a terminal success status and a verified read-back. Then, for a real deploy only, the baselines are refreshed, the last deploy's revision moves, the settled record is written and the slot is removed, in that order, so an interrupted finish can be repeated. A read-back mismatch, an unknown status or a partial result keeps the operation open as `unresolved`, with the evidence. Check-only deploys settle without touching baselines.
6. **Reconciling** (`sf mp reconcile`), never while the holder process is still running here:
   - (a) With a job ID: read its status; a terminal status settles the operation (rule 5).
   - (b) Without one, past `submitting`: look for exactly one deploy request by the operation's own submitter, in its mode, created no earlier than `submitting`. If found, treat it as the job; anything else is the steward's.
   - (c) Still `intent`: never submitted, so it settles as `reconciled-failed`.
   - (d) Otherwise the steward settles it by hand (`--settle success|failed --note "…"`) after confirming nothing is still running.

   Nothing is ever replayed automatically.
7. **No takeover by expiry.** A sleeping holder's operation is reconciled only after its process has stopped; a woken process re-checks that it still holds the slot before every change.
8. **Owners.** A component named in `.mp/owners.yaml` is deployed only when its owner runs the lane, or with `--approved-by <owner>` recording the owner's yes, tied to the candidate revision.
9. **Types.** Each type `sf mp deploy` enables has a tested contract (scope, comparison, completeness, what can't be restored): ApexClass, LightningComponentBundle and CustomField (not picklists). `--steward` (§5) is the steward's route for other named components. Read-backs compare code bodies exactly after line-ending normalization, except that an Apex body's trailing whitespace, which Salesforce strips on save, doesn't count; XML compares structurally (the candidate's elements, in order, with equal values; org defaults allowed).
10. **Validation (`sf mp validate`)** is outside the journal. It's a check-only deploy, fixed in code, of a folder of source into an org bound as a Lifecycle Center captain's (`--guard-only --lifecycle-captain`; never a builder's guard or a lane): it takes no slot, records no operation and moves no baseline. It counts as validated only when the platform reports the named tests ran, or when source without Apex ran none. Quick deploy stays refused, so a validation can't turn into a deploy through `sf`.

## 5. The steward route (`--steward`)
For named components whose type has no tested contract (objects, permission sets, flows, layouts, pages, tabs, apps and so on), `sf mp deploy --steward` and `sf mp retrieve --steward` run the same sequence: bind, freeze, exact scope, owners, slot, intent, freshness on the whole retrieved component, backup, deploy and read-back. The steward's yes replaces the missing per-type contract. A read-back that doesn't match, often the org's own normalization of a complex type, keeps the operation `unresolved` for the steward to settle (rule 6d).

Refused even with `--steward`: agent types (their publish and activation need an owner route), `Profile`, `Settings`, wildcards, deletes and destructive changes, field type changes, and more than 25 components.

## 6. Out of scope
- Hostile writers, and deliberate bypass: `SF_DATA_DIR`, uninstalling the plugin, editing the journal by hand.
- Deploys outside the `sf` process (VS Code, the DX MCP Server, other source-deploy-retrieve importers): switch those off.
- Forged Git identities or made-up owner approvals: cooperative attribution is enough.
- Exactly-once submission and atomic rollback. An operation left `unresolved` is a valid outcome.
- Two machines acting as the lane for one org.
