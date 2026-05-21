# Customer-Name Normalization

Read by scout-sparring Stage 2 after the SE names a customer. Produces a deterministic folder slug and handles existing-folder matching.

## Slug Rule

Normalize the customer name to a folder-safe slug using this deterministic rule:

1. Lowercase the whole string.
2. Strip diacritics (é→e, ü→u, ñ→n, ø→o, ß→ss, etc.).
3. Replace every run of non-`[a-z0-9]` characters with a single hyphen.
4. Trim leading and trailing hyphens.
5. Truncate at 40 characters (trim to the last whole hyphen-delimited segment if the cut lands mid-word).

Worked examples — follow these exactly:
- `Deutsche Fachpflege` → `deutsche-fachpflege`
- `L'Oréal` → `l-oreal`
- `AT&T` → `at-t`
- `Ben & Jerry's` → `ben-jerry-s`
- `Siemens Healthineers AG & Co. KG` → `siemens-healthineers-ag-co-kg`
- `3M` → `3m`
- `BD (Becton Dickinson)` → `bd-becton-dickinson`

## Existing-Folder Match Check

Before creating the folder, run `ls -d orgs/[alias]-*/ 2>/dev/null` and scan for any folder whose suffix is equal to, a prefix of, or shares the first hyphen-delimited segment with the normalized slug. If one or more matches exist, ask the SE in a single message:

> "Found existing folder(s) for this org: [list]. Same customer as one of these, or a new one?
> - Reply with the matching folder name to continue in it.
> - Reply `new` to create `orgs/[alias]-[slug]/` as a fresh customer folder."

Wait for the reply. If the SE names an existing folder, use it verbatim. If `new`, create `orgs/[alias]-[slug]/`. If no matches, proceed with the normalized slug without prompting.

Final value: **Org folder:** `orgs/[alias]-[customer]/`
