# Lessons Bootstrap

How Scout's lessons folder is created and loaded. `/scout` reads `orgs/lessons/INDEX.md`
at its start (`skills/scout/SKILL.md`), and runs Step 1 below on the builder's yes to a first lesson
(`prompts/scout/history.md`).

Lessons live in the builder's PERSONAL workspace (`orgs/lessons/`), not in the
plugin — so the plugin cannot ship them. This fragment creates the INDEX
lazily on first run, then drives the load.

## Step 1: Ensure the lessons directory + INDEX exist (idempotent)

Run this one command with the host contract's `[PYTHON]` and the resolved root for
`[PLUGIN_ROOT]`. It prints `LESSONS_PRESENT` or `LESSONS_WRITTEN`, and never replaces
an existing index.

```bash
python3 -B "[PLUGIN_ROOT]/scripts/setup-workspace.py" lessons
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
is non-empty (more than its header), Read it too — legacy lessons still count.
