# Lessons Bootstrap

Shared fragment Read by `/scout-sparring` (Step 0) and `/scout-building`
(Step 1, before constructing sub-agents) as their lessons-load step.
Replaces the old "Read `orgs/sparring-lessons.md`" / "Read
`orgs/building-lessons.md`" line.

Lessons live in the SE's PERSONAL workspace (`orgs/lessons/`), not in the
plugin — so the plugin cannot ship them. This fragment creates the INDEX
lazily on first run, then drives the load.

## Step 1: Ensure the lessons directory + INDEX exist (idempotent)

```bash
cd "$HOME/claude-projects/sf-demo-scout"
mkdir -p orgs/lessons
if [ ! -f orgs/lessons/INDEX.md ]; then
  cat > orgs/lessons/INDEX.md <<'EOF'
# Lessons Index

Topic-clustered lessons from scout-sparring + scout-building sessions.
This INDEX is loaded at the start of every session; topic files are
loaded on demand based on the descriptive lines below.

Each lesson is whole — it may carry both a sparring rule and a building
backstop. Lessons are not split by phase. Add new lessons to the topic
file that best fits; create a new topic + INDEX line if none fit.

## Topics

- **agentforce.md** — Agentforce agent build + iteration: action-invocation-as-proof, GenAiPlannerBundle safety, enhanced-event-log diagnostics, pre-Agent-Script (Atlas/UI-built) agent handling, headless/Agent API recipes, agent action schema.
- **managed-packages.md** — Managed-package write/read restrictions and schema quirks (lsc4ce / LSC, Health Cloud, FSC, industry clouds): namespaced retrieve names, trigger/validation DML gates, stage-gated field locks, territory/sharing blast radius.
- **flow.md** — Flow + FlowTest: generated-flow defect patterns, FlowTest XML schema, CLI flow-run breakage, record-triggered vs screen flow gotchas.
- **data-seeding.md** — Data seeding: CLI `sf data` envelope/Bash quirks, pilot-self-test limits, pricebook/SKU gating, paired-record cleanup, idempotency.
- **metadata-deploy.md** — Org-SPECIFIC metadata deploy/parse gotchas (distinct from the org-agnostic Known Deploy-Error Patterns catalog): roll-up-summary relationship traps, permset description limits, field/picklist verification, RT-specific values.
- **discovery-and-scoping.md** — Sparring heuristics: customer-evidence gate, reuse-orgs-aggressively, booth-vs-WorldTour scoping, existing-first object/field probing, marketed-vs-shorthand product names, data-quality-before-reuse.
- **lwc-slds.md** — LWC + SLDS: internal-token hard-fails, SLDS2 utility/global-hook fixes, Code Analyzer deprecation warnings.
EOF
fi
```

## Step 2: Load the INDEX, then select topics

Read `orgs/lessons/INDEX.md` now. It is small — always load it in full.

Then select and Read the topic files relevant to THIS session, using the
INDEX's descriptive lines to decide:

- **Sparring:** load topics matching the org's detected clouds / managed
  namespaces (from the audit) and the session intent. E.g. an LSC org →
  `managed-packages.md`; an Agentforce iteration → `agentforce.md`; any
  new-scenario discovery → `discovery-and-scoping.md`. When unsure, prefer
  loading a topic over skipping it — these files are small.
- **Building:** load topics matching the spec's component classes (the same
  classification you use to route phase sub-agents): Agentforce in the spec
  → `agentforce.md`; Flow → `flow.md`; data seeding → `data-seeding.md`;
  LWC → `lwc-slds.md`; a managed namespace in the org → `managed-packages.md`.
  On ANY sub-agent deploy error during the session, load `metadata-deploy.md`
  (and `managed-packages.md` if a managed namespace is in play) before the
  next attempt if not already loaded.

The INDEX is the deterministic anchor (always loaded); topic selection is
the flexible layer (judgment from the descriptive lines). The goal is no
missed load on a topic the session actually touches.

## Step 3: Legacy flat files (backward-compat)

If `orgs/sparring-lessons.md` or `orgs/building-lessons.md` still exists and
is non-empty (more than its header), Read it too — legacy lessons are still
authoritative until drained. The end-of-session lessons step (in
`lessons-maintenance.md`) offers a one-time drain into topic files.
