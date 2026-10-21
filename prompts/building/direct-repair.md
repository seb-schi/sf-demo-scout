# Compact Direct Repair

Use this route when the builder asks for a small fix or tweak, in `/scout` or outside
any command: the current repair instruction supplies the scope. Keep the confirmation tier in Scout's `AGENTS.md`, category gates, no-Apex choice,
target-org checks, and the new-page exclusion (a new Lightning record page stays manual) unchanged.

Read `${CLAUDE_PLUGIN_ROOT}/prompts/host-runtime.md` from the active plugin context first, then `${CLAUDE_PLUGIN_ROOT}/prompts/operation-safety.md` before any tool mutation.
Resolve the successful bootstrap workspace and selected customer as absolute paths;
prepare and verify a writer-owned project with `WRITER=direct-repair`. Use only its
returned `project_root`, `source_root`, `rollback_dir` and `customer_dir`, unchanged.
When loading Phase 1/2/3, materialize `PROJECT_ROOT`, `ASSET_HELPER`, `ROLLBACK_DIR`
and the shared operation-safety block for this repair. Retain its source at finish.

1. Freeze the exact requested item, target org, metadata identity, expected delta,
   and exclusions from the current instruction. Ask only when the target, requested
   state, or required permission is genuinely ambiguous. Do not start a scenario
   interview, create a new spec/ledger, or restart the phased build for a filter,
   value, trigger, seed, or similarly bounded repair. Outside `/scout`, bind the target
   with `python3 [PLUGIN_ROOT_ABS]/scripts/scout_target.py bind --selector [ORG]` first and
   require exit 0; keep the selector, username and org ID it returns, and use that
   username as `--target-org` from then on. When it reports `writes: read-only`
   (production, or an org it can't classify), write nothing there, say so, and stop.
   Before every write and retry, run `scout_target.py check --selector [SELECTOR]
   --username [USERNAME] --org-id [ORG_ID] --write`; on a nonzero exit, write nothing
   and report the reason.
2. Read `${CLAUDE_PLUGIN_ROOT}/prompts/building/official-skill-overrides.md` before
   resolving or invoking an official skill. Run its §"Readiness" inspection before any
   source write, then apply its common preamble, §"The official hooks", §"The action log"
   and only the applicable named overrides, resolving reference paths to absolute installed paths.
   If an approved Agentforce repair applies, also load
   `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase3.md` and the canonical
   `${CLAUDE_PLUGIN_ROOT}/prompts/building/agentforce-validation-gate.md`; otherwise do not load either Agentforce file.
3. Resolve the installed supported skill/tool before any write and follow its compact
   technical procedure. Do not invent a missing skill or substitute an incompatible
   generator. New-page FlexiPage authoring and other unsupported operations remain
   explicit BLOCKED/manual outcomes. For a Report or ReportType, use the report
   fallback and read-back rules in
   `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md`. For a Flow, load the Flow
   identity, testing, activation, and rollback rules in
   `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase2.md` plus the Phase-2 Flow Evidence
   section in `${CLAUDE_PLUGIN_ROOT}/prompts/building/sub-agent-validation.md`, and
   edit it in the order of `${CLAUDE_PLUGIN_ROOT}/prompts/building/official-skill-overrides.md`
   §"Flow scope": the retrieved XML, changed only where the request changes it, with
   the official skills, and `sf-flow` last. A
   direct Flow repair does not create a full ledger: freeze the exact Flow API name,
   expected state, supported validation mode and every exact required test API name (or concrete
   unsupported reason), pre-repair source identity, and original activation evidence
   in the pending repair checkpoint. Wherever those loaded rules say frozen ledger,
   use these immutable checkpoint fields for this repair only. A
   record page repair follows Phase 1's §"Lightning Record Page — Edit Rules":
   additive edits through `salesforce-development:platform-flexipage-generate`,
   its convergence rule (nothing ungrounded is written, a rejected component is
   dropped, and a second rejection stops the edit) and the incumbent read-back.
   Moving or removing an existing component needs its own yes; a new page is
   BLOCKED/manual.
4. Read and follow `${CLAUDE_PLUGIN_ROOT}/prompts/building/component-rollback.md`
   before retrieve scratch can be overwritten/cleaned or any mutation occurs. Resolve
   `ASSET_HELPER` to the absolute installed `scripts/build-assets.py` path and
   `ROLLBACK_DIR` to the unchanged helper-returned `rollback_dir`. Use the
   existing org change log for its checkpoint, or create the conventional
   `changes-[YYYY-MM-DD]-[HHmm]-[CUSTOMER].md` there when none exists.
5. Deploy only the frozen delta, then perform targeted read-back. Preserve Report
   filter values and logic, unrelated incumbent content, and the Phase 2 exact Flow
   test/version/activation contract. Do not infer success from a deploy receipt.
6. For a bounded record-data repair, invoke `salesforce-development:platform-data-manage` and write a pending
   row before mutation with exact object, record IDs/stable keys, fields, typed before
   values, and requested after values. Do not use the metadata snapshot helper. Read
   back those same records/fields; rollback restores only recorded field values and
   never deletes an incumbent record. Missing stable identity or before-values is
   BLOCKED. This is a direct data operation, not a new seed/completion engine.
7. Append the outcome automatically to the same change log as `applied`, `failed`,
   `blocked`, `already_satisfied`, or `unverified`. Give the builder the concrete result,
   saved evidence, rollback route, and next action. Supported handoffs remain explicit;
   do not build a new completion engine or ask the builder to remember to log the repair.
