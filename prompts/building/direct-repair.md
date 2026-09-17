# Compact Direct Repair

Use this route when the SE asks for a small fix or tweak against the active org,
including requests made outside `/scout-building` Step 7. This is the explicit
post-build exception to `scout-building`'s Spec Only hard stop: the current repair
instruction supplies the scope. Keep the NEVER tier, category gates, no-Apex choice,
target-org checks, and whole-new-FlexiPage exclusion unchanged.

1. Freeze the exact requested item, target org, metadata identity, expected delta,
   and exclusions from the current instruction. Ask only when the target, requested
   state, or required permission is genuinely ambiguous. Do not start a scenario
   interview, create a new spec/ledger, or restart the phased build for a filter,
   value, trigger, seed, or similarly bounded repair.
2. Read `${CLAUDE_PLUGIN_ROOT}/prompts/building/vendor-compatibility.md` before
   resolving or invoking a vendor skill. Apply its common preamble plus only the
   applicable named sections, resolving reference paths to absolute installed paths.
   If an approved Agentforce repair applies, also load
   `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase3.md` and the canonical
   `${CLAUDE_PLUGIN_ROOT}/prompts/building/agentforce-validation-gate.md`; otherwise do not load either Agentforce file.
3. Resolve the installed supported skill/tool before any write and follow its compact
   technical procedure. Do not invent a missing skill or substitute an incompatible
   generator. Whole-page FlexiPage authoring and other unsupported operations remain
   explicit BLOCKED/manual outcomes. For a Report or ReportType, use the report
   fallback and read-back rules in
   `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase1.md`. For a Flow, load the Flow
   identity, testing, activation, and rollback rules in
   `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase2.md` plus the Phase-2 Flow Evidence
   section in `${CLAUDE_PLUGIN_ROOT}/prompts/building/sub-agent-validation.md`. A
   direct Flow repair does not create a full ledger: freeze the exact Flow API name,
   expected state, supported validation mode and exact test API name (or concrete
   unsupported reason), pre-repair source identity, and original activation evidence
   in the pending repair checkpoint. Wherever those loaded rules say frozen ledger,
   use these immutable checkpoint fields for this repair only. A
   FlexiPage repair may use only Phase 1's existing compatible field-section append
   path; an incompatible or whole-page request is BLOCKED/manual.
4. Read and follow `${CLAUDE_PLUGIN_ROOT}/prompts/building/component-rollback.md`
   before retrieve scratch can be overwritten/cleaned or any mutation occurs. Resolve
   `ASSET_HELPER` to the absolute installed `scripts/build-assets.py` path and
   `ROLLBACK_DIR` to the active org folder's durable rollback directory. Use the
   existing org change log for its checkpoint, or create the conventional
   `changes-[YYYY-MM-DD]-[HHmm]-[CUSTOMER].md` there when none exists.
5. Deploy only the frozen delta, then perform targeted read-back. Preserve Report
   filter values and logic, unrelated incumbent content, and the Phase 2 exact Flow
   test/version/activation contract. Do not infer success from a deploy receipt.
6. For a bounded record-data repair, invoke `platform-data-manage` and write a pending
   row before mutation with exact object, record IDs/stable keys, fields, typed before
   values, and requested after values. Do not use the metadata snapshot helper. Read
   back those same records/fields; rollback restores only recorded field values and
   never deletes an incumbent record. Missing stable identity or before-values is
   BLOCKED. This is a direct data operation, not a new seed/completion engine.
7. Append the outcome automatically to the same change log as `applied`, `failed`,
   `blocked`, `already_satisfied`, or `unverified`. Give the SE the concrete result,
   saved evidence, rollback route, and next action. Supported handoffs remain explicit;
   do not build a new completion engine or ask the SE to remember to log the repair.
