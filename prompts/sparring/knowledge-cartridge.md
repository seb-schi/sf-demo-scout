# Knowledge Cartridge Consult

Read + executed by `/scout-sparring` **Stage 4**, after `platform-research.md`
and before the Stage 5 scenario proposal. Lets Scout draw on an installed,
contract-conforming **knowledge cartridge** — a plugin that publishes a stable
Life-Sciences-style knowledge layer — when the audited org's industry matches
what that cartridge covers.

**This is a KNOWLEDGE consult, not a build-tool offer.** It is deliberately
separate from Stage 5's *External skills (surface + gated offer)* step, which
surfaces build-EXECUTOR skills by name-family → build-category and gates them
behind SE approval with a "verify the output yourself" caveat. A cartridge here
supplies *knowledge that shapes scenario design* (traps, recipes, regulatory
framing, release truth) — reading it is not executing an unvalidated build, so
it needs no approval gate. If a cartridge ALSO ships a build-executor skill that
should drive part of the build, that still flows through the Stage 5 offer-gate
and the spec's `### External Skills` section with SE approval — unchanged. The
two mechanisms do not overlap.

**Dependency direction (do not invert):** Scout reads the cartridge's published
contract; the cartridge never detects, depends on, or hardcodes Scout. All
consumer-specific adoption logic lives here, in Scout. A cartridge is any plugin
that conforms to the contract — Scout names no specific cartridge.

## Step 1 — Discover conforming cartridges (cheap; always runs)

A **conforming knowledge cartridge** is an installed plugin whose cache version
dir contains BOTH `INTEGRATING.md` and `KNOWLEDGE-INDEX.md` at its root. Both
files present = the plugin publishes the adoption contract AND a machine-readable
knowledge map. `INTEGRATING.md` ships only in current, contract-aware versions,
so requiring both naturally selects conforming + current cartridges and ignores
stale side-by-side version dirs.

```bash
# One conforming cartridge per plugin: latest version dir that has BOTH files.
# sort -V | tail -1 picks the highest version when multiple are cached
# (e.g. mid-update, two versions side by side) — same idiom as maintainer-bootstrap.
for KIDX in $(find "$HOME/.claude/plugins/cache" -name KNOWLEDGE-INDEX.md 2>/dev/null); do
  DIR=$(dirname "$KIDX")
  [ -f "$DIR/INTEGRATING.md" ] && echo "$DIR"
done | sort -V | awk -F/ '{ key=$(NF-1); ver=$NF; latest[key]=$0 } END { for (k in latest) print latest[k] }'
```

(The `awk` keeps only the latest version dir per plugin name. If the one-liner
is awkward in practice, an equivalent is: group the found dirs by the
second-to-last path segment (the plugin name), `sort -V` within each group, keep
the last. The invariant that matters: **at most one conforming dir per installed
plugin, the highest version.**)

If NO conforming cartridge is found: emit nothing, skip to "After this fragment."
This is the common case on a machine with no cartridge installed — zero ceremony.

## Step 2 — Match the audited industry against each cartridge's Coverage

Each conforming cartridge declares a machine-readable **Coverage** block near the
top of its `KNOWLEDGE-INDEX.md`:

```
## Coverage
industry: <human name, e.g. Life Sciences>
signals:
  namespaces: [<managed-package namespaces, e.g. lsc4ce>]
  objects: [<distinctive EntityDefinition API names, if any>]
```

Read each cartridge's Coverage block. **Match = the audit's detected
industry-cloud signal (the Demo Surface Notes non-universal objects / namespaces
from Stage 2–3, and the cloud the SE confirmed in Stage 3 Q2) overlaps a
cartridge's declared `namespaces` or `objects`.** Declared signals are the
primary key — precise and self-describing. Match on any signal overlap; do not
require all.

Distinguish the no-match cases:

- **No conforming cartridge discovered** (Step 1 found none) → this fragment is done. Proceed silently — do NOT tell the SE a cartridge is missing. Scout grounds the scenario in docs + audit exactly as it always has. (Knowledge cartridges are rare; the LS Booster Pack is the only one today. A "no cartridge for this industry" flag would nag the SE about something they cannot install, and Scout can't tell "no cartridge exists" from "exists but not installed" — it sees only the local plugin cache. Where a future cartridge should go is a maintainer signal, gathered outside the SE's prep session.)
- **Conforming cartridge, Coverage present, industry doesn't overlap** → silent (same rationale: the cartridge legitimately doesn't cover this org's industry).
- **Conforming cartridge, Coverage ABSENT or unparseable** (no `## Coverage` block at all, OR a Coverage block missing BOTH `namespaces` and `objects`) → emit exactly one diagnostic line, then proceed as no-match (do NOT block, do NOT guess a match):
  > "⚠ Knowledge cartridge [plugin name] is installed and contract-conforming, but its KNOWLEDGE-INDEX.md has no parseable `## Coverage` block — I can't match it to this org's industry, so I'm grounding the scenario in docs + audit as usual. (This is a cartridge-side contract gap, not something you can fix from here.)"
- **Conforming cartridge, Coverage present, industry overlaps** → Step 3.

## Step 3 — Consult the matched cartridge (proactive, read-only)

Apply the cartridge's OWN adoption contract — read its `INTEGRATING.md` "How to
adopt it" section and follow the three rules it publishes. In practice for a
conforming cartridge that means:

1. **Enumerate its skills.** List the cartridge dir's `skills/*/SKILL.md` and read
   each frontmatter `description` (TRIGGER / DO NOT TRIGGER). That set + the
   `KNOWLEDGE-INDEX.md` map is the cartridge's full surface.
2. **Route the scenario's industry-touching questions to owning skills.** For any
   data-model, build-correctness, competitive, regulatory, localization, or
   release question the scenario raises that the cartridge's map owns, consult
   that skill's body BEFORE designing from your own memory. The cartridge is
   authored to be more current and correct on its industry than a general model.
3. **Honor the one hard retrieval rule.** Index/hybrid-disposition skills point at
   large external hubs (Slack canvases, Google decks, product repos). NEVER read
   a hub into this sparring context — dispatch a Sonnet subagent that returns only
   the distilled answer, and never cache release/competitive/setup figures the
   skill marks churny. (This is already Scout's named-source discipline from
   Stage 3 — the same subagent pattern.)

Announce the consult in one line so the SE sees it happen, e.g.:
> "This org is [industry] and the [cartridge name] knowledge cartridge covers it
> — consulting its playbook / recipes / [relevant skills] to ground the scenario."

Then fold the cartridge's findings into Stage 4's research output and the Stage 5
proposal, cited like any other Stage-4 finding. Cartridge knowledge INFORMS
scenario design and the spec — it does NOT get injected into the build phase
prompts. If the cartridge surfaces a build-executor skill that should drive a
build, route it through the Stage 5 offer-gate (SE approval → `### External
Skills`), not here.

## Step 4 — Docs cross-check the matched cartridge (rides the existing budget)

Runs ONLY when Step 3 consulted a matched cartridge — it keeps that cartridge
honest. On a no-match org there is nothing to cross-check; Step 2 already exited
silently.

Scout's Stage 4 already consults Salesforce Docs on industry-cloud data models
(`platform-research.md` + `demo-docs-consultation` trigger 9). Use that SAME
budget — no new ambient call — to **ground the match:** confirm the audit's
detected objects/namespaces map to a real Salesforce industry solution, so a
cartridge can't over-claim coverage and the consult is anchored in what
Salesforce actually ships. If the docs check contradicts the cartridge's claimed
coverage, trust docs + audit and note the mismatch rather than the cartridge.

## After this fragment

Return to Stage 4's normal flow (SE confirms findings, proceed per the Stage 2
route table). This fragment only adds knowledge when a cartridge matches; it
changes no gating and blocks nothing. On any org with no matching cartridge it is
silent on a legitimate no-match — no "missing cartridge" nag. On a conforming
cartridge whose Coverage block is absent/unparseable, one diagnostic line surfaces
the contract gap so it doesn't stay invisible.
