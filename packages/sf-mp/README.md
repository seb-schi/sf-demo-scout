# sf-mp

A Salesforce CLI plugin for teams that build in their own sandboxes and deliver into one common org through one guarded lane. It works with any AI coding tool, because it acts inside `sf` itself. Unpublished; part of SF Demo Scout 2.3 ("multiplayer").

## What it does
- **The guard** refuses commands that would write to the bound common org outside `sf mp deploy`:
  - `project deploy start` and `validate`, `project delete source`
  - tracking resets, `apex run`
  - `agent create` (except `--preview`), `activate`, `deactivate` and `publish authoring-bundle`

  It works out the target offline (the flag, else your default org). Writes to any other org, such as your own sandbox, pass untouched.
- **Three exceptions** apply wherever the guard is awake, so also towards other orgs:
  - `project deploy quick`, which takes its org from a cache the guard can't check
  - `--flags-dir` on a protected command, which adds flags after the guard has looked
  - a protected command whose target is a token the guard can't read, such as a JWT access token (an opaque token is read by its org ID). Use a locally authenticated username or alias instead
- **`sf mp deploy`** deploys named components (`--metadata Type:Name`, at most 25), taken from HEAD's committed content:
  1. It checks the org's copy against your baseline.
  2. It keeps a backup.
  3. It records the operation before anything is sent.
  4. It deploys, then reads the result back.

  A stale, unowned or over-wide deploy is refused.
- **`sf mp retrieve`** records baselines. It never overwrites a different local copy: it saves the org's copy for you to merge, and `--merged` records it after you've committed the merge.
- **`sf mp reconcile`** settles an interrupted operation and never redeploys. **`sf mp status`** shows the state, and **`sf mp init`** binds a project to its common org and registers its lane on this machine.
- **`sf mp init --guard-only`** is for every other machine in a team: it guards the kit project's common org from every folder there, without a lane and without needing a login to that org. Outside a kit project, as in a team on Salesforce's Lifecycle Center, it guards the org named with `--target-org`; the team captain's machine adds `--lifecycle-captain`.
- **`sf mp validate`** is for a team whose promotions run on Lifecycle Center, where they deploy server-side. It runs only on the captain's machine (bound with `--lifecycle-captain`):
  - It's a check-only deploy into the common org, of a folder of source, running the Apex tests you name (`--tests`), or none for source without Apex (`--no-tests`).
  - It's check-only by construction: no flag reaches that setting.
  - It counts as validated only if the platform reports that the tests ran.
  - Quick deploy stays refused, so a validation can't become a deploy through `sf`.
- **`--steward`** on `deploy` and `retrieve` is the steward's route for allow-listed types that have no lane contract yet (CustomObject, PermissionSet, CustomTab and Layout). It runs the same checked sequence and refuses an object file that would change page assignments. See `CONTRACT.md` §5.

## Limits (v1)
- **Types:** ApexClass, LightningComponentBundle, and CustomField except picklists; with `--steward`, CustomObject, PermissionSet, CustomTab and Layout. Profiles, settings, agents, prompt templates, flow definitions, deletes, renames and destructive changes go to the steward by hand.
- **Repository:** it must be a Git repository; the lane deploys committed work only.
- **Deploys:** SOAP only; test levels NoTestRun or RunLocalTests (set by `sf mp init`); `replacements` in `sfdx-project.json` are refused.
- **One lane per org per machine:** another checkout of the same org is refused.
- **Reach:** the guard only sees commands run through `sf`. VS Code's deploy-on-save, the DX MCP Server and other tools that deploy in their own process aren't covered, so switch those off. Pointing `SF_DATA_DIR` elsewhere or uninstalling the plugin turns the guard off. The guard stops accidents, not deliberate bypass.
- **Tested on:** Salesforce CLI 2.154.4 (source-deploy-retrieve 13.4.4) on macOS. Windows isn't tested yet.

## How it works
- **The contract:** `CONTRACT.md` says who may write to the common org and how an interrupted write is settled.
- **No npm dependencies:** the plugin uses the libraries of the `sf` that loads it.
- **The lane's state:** the journal, baselines, merge copies and backups live in `.mp/`, outside Git. Only `.mp/config.json` and `.mp/owners.yaml` are shared.

## Tests
```bash
node --test test/
```
They need `sf` on your PATH, or `SF_MP_CLI_ROOT` set to its install folder. They're offline: they use real source-deploy-retrieve resolution and conversion, real Git, and a fake org.

Apache-2.0.
