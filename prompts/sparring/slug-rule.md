# Folder-Slug Rule (shared)

The single source of truth for turning a Salesforce org alias or a customer
name into a folder-safe slug. Read by `customer-normalization.md`, so every
folder name derives the same way. Do NOT
re-implement this rule inline anywhere — reference this file.

## Slug transform

Apply to a single token (an alias OR a customer name — never the combined path):

1. Lowercase the whole string.
2. Strip diacritics (é→e, ü→u, ñ→n, ø→o, ß→ss, etc.).
3. Replace every run of non-`[a-z0-9]` characters with a single hyphen.
4. Trim leading and trailing hyphens.
5. Truncate at 40 characters. If the 40-character cut lands mid-word, trim back
   to the last whole hyphen-delimited segment; if the cut lands exactly on a
   hyphen (the prefix already ends at a whole segment), keep the 40 characters as
   they are. A single first segment longer than 40 characters (no hyphen within
   the first 40) has no whole segment to fall back to — hard-cut it at 40.

Worked examples — follow exactly:
- `Nordlicht Fachpflege` → `nordlicht-fachpflege`
- `L'Étoile` → `l-etoile`
- `A&Z` → `a-z`
- `Example CPQ` → `example-cpq`
- `7K` → `7k`

## ORG_FOLDER

The canonical org-folder path is:

```
ORG_FOLDER = orgs/<slug(alias)>-<slug(customer)>/
```

Resolve `ORG_FOLDER` **once** per session and pass it verbatim wherever a
customer-folder path is needed. Never reconstruct it from alias + customer
downstream — a second derivation is how divergent folders (`Example CPQ-example`
vs `example-cpq-example`) get created.

**The raw alias is a separate value.** `sf` identifies an org by its real
alias (e.g. `Example CPQ`), so anything passed to `--target-org`, or shown as
`Target org:`, uses the RAW alias — never the slug. Only *folder paths* use
the slug.

## Reference implementation

`scripts/slugify.py` (SE-facing plugin, stdlib only — `unicodedata` NFKD + an
explicit map for non-decomposing characters like `ß`→`ss`, `ø`→`o`) is the
canonical **executable** implementation of the transform above, including the
40-character and overlong-first-segment boundary rules. It is pinned to the
worked examples by fixtures, and `/scout` calls it to match customer folders
by the alias slug (`skills/scout/SKILL.md`).

The prompt-based folder **writer** (`customer-normalization.md`) still applies
this documented rule directly and doesn't call the helper yet, so this text stays
the shared contract; the helper is what `/scout` runs.
