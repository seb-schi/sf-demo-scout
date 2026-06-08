# Customer-Name Normalization

Read by scout-sparring Stage 1 after the SE names a customer. Produces the deterministic `ORG_FOLDER` path and handles existing-folder matching.

## Slug Rule

Read `${CLAUDE_PLUGIN_ROOT}/prompts/sparring/slug-rule.md` — it is the single source of truth for the slug transform AND for the `ORG_FOLDER` / raw-alias split. Apply its transform to **both** the org alias and the customer name. More examples there; the canonical few:
- `Deutsche Fachpflege` → `deutsche-fachpflege`
- `L'Oréal` → `l-oreal`
- `Metro CPQ` → `metro-cpq`  (alias with caps + space — this is the case that previously produced duplicate folders)
- `Ben & Jerry's` → `ben-jerry-s`
- `BD (Becton Dickinson)` → `bd-becton-dickinson`

Resolve `ORG_FOLDER = orgs/<slug(alias)>-<slug(customer)>/` once here. The RAW alias (for `--target-org`) is a separate value — keep both.

## Existing-Folder Match Check

Before creating the folder, run `ls -d orgs/<slug(alias)>-*/ 2>/dev/null` (use the slugified alias in the glob — the on-disk folders are slug-named) and scan for any folder whose suffix is equal to, a prefix of, or shares the first hyphen-delimited segment with the normalized slug. If one or more matches exist, ask the SE in a single message:

> "Found existing folder(s) for this org: [list]. Same customer as one of these, or a new one?
> - Reply with the matching folder name to continue in it.
> - Reply `new` to create a fresh customer folder."

Wait for the reply. If the SE names an existing folder, set `ORG_FOLDER` to that folder verbatim. If `new`, create `ORG_FOLDER`. If no matches, proceed with the resolved `ORG_FOLDER` without prompting.

Final value: **ORG_FOLDER** = `orgs/<slug(alias)>-<slug(customer)>/` — pass this verbatim to every downstream step (audit orchestration, spec write). The raw alias travels alongside it for `--target-org` use only.
