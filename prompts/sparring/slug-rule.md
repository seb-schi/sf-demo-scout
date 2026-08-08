# Folder-Slug Rule (shared)

The single source of truth for turning a Salesforce org alias or a customer
name into a folder-safe slug. Read by `customer-normalization.md` (sparring)
and `scout-building.md` so both derive identical folder names. Do NOT
re-implement this rule inline anywhere — reference this file.

## Slug transform

Apply to a single token (an alias OR a customer name — never the combined path):

1. Lowercase the whole string.
2. Strip diacritics (é→e, ü→u, ñ→n, ø→o, ß→ss, etc.).
3. Replace every run of non-`[a-z0-9]` characters with a single hyphen.
4. Trim leading and trailing hyphens.
5. Truncate at 40 characters (trim to the last whole hyphen-delimited segment
   if the cut lands mid-word).

Worked examples — follow exactly:
- `Deutsche Fachpflege` → `deutsche-fachpflege`
- `L'Oréal` → `l-oreal`
- `AT&T` → `at-t`
- `Metro CPQ` → `metro-cpq`
- `3M` → `3m`

## ORG_FOLDER

The canonical org-folder path is:

```
ORG_FOLDER = orgs/<slug(alias)>-<slug(customer)>/
```

Resolve `ORG_FOLDER` **once** per session and pass it verbatim wherever a
customer-folder path is needed. Never reconstruct it from alias + customer
downstream — a second derivation is how divergent folders (`Metro CPQ-metro`
vs `metro-cpq-metro`) get created.

**The raw alias is a separate value.** `sf` identifies an org by its real
alias (e.g. `Metro CPQ`), so anything passed to `--target-org`, or shown as
`Target org:`, uses the RAW alias — never the slug. Only *folder paths* use
the slug.
