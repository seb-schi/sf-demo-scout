# Scout-owned vendor compatibility

This Scout contract overrides only the named vendor conflicts below. All caller rules for scope, category permissions, retries, preservation, and acceptance remain binding. Missing dependency is evidence to report, never authorization to install, upgrade, broaden work, substitute unrelated work, or mark a check passed. Direct invocation outside Scout's callers is outside this compatibility guarantee.

## Flow scope

The maintained `sf-flow` skill owns its current bundled handoffs and FlowTest
schema/templates. Only execute an exact approved schema dependency through its
named skill; a Flow-only phase or repair cannot execute unrelated schema or agent
work. An absent or unapproved dependency stays BLOCKED. Preserve Scout's exact
required-test set, version, activation, and rollback contract in Phase 2.

## Analyzer prerequisites

Prefer the available MCP `run_code_analyzer` tool. Use the CLI fallback through `dx-code-analyzer-run` only when its own prerequisite checks succeed. Do not delegate to absent `configuring-code-analyzer`, do not install or upgrade tools, and do not disable required engines. If fallback prerequisites fail, preserve the exact failure and scan gap. A successful MCP scan supports only the coverage it actually ran. If both paths are unavailable, state `scan not run/unverified` and keep required scan acceptance unresolved.

## Report tools

When the named API-context tools are unavailable, use the bundled static `${CLAUDE_PLUGIN_ROOT}/skills/platform-report-generate/references/column-names.md` mapping and the existing Phase 1 report fallback and read-back rules. Resolve that reference to its absolute installed path before dispatch. Never fabricate tool calls or treat a static mapping as live validation. Unknown columns require supported evidence or documentation; otherwise they are BLOCKED before writing. Preserve exact filter values, filter logic, ReportType and folder identity, incumbent originals, and post-deploy read-back.

## Validation formulas

Correct vendor `ISCHANGE()` guidance to Salesforce `ISCHANGED(field)` before deployment. Preserve formula semantics, CDATA, error placement, and existing validation rules. Do not perform blind text replacement inside literal strings. This caller instruction is not an executable formula parser and does not prove live validation.

## FlexiPage scope

All new whole RecordPages remain manual/App Builder work; do not use the vendor base-generation workflow as a substitute for completing the requested page. A supported direct edit is limited to Phase 1's compatible field-section append path with a confirmed page, confirmed section and column, incumbent preservation, and read-back. Other component changes remain explicit manual/BLOCKED work under current scope.

## Agentforce prerequisites and precedence

Scout's orchestration may use its named skills and MCP tools despite `agentforce-generate`'s global no-dependencies statement. This is a Scout caller override, not a claim about upstream intent. Phase 3 owns metadata MCP operations, `sf agent` owns lifecycle operations, and `agentforce-test` owns testing and schema guidance.

Before a selected simulated programmatic authoring preview, capture a successful `sf --version` result and actual command readiness. Every selected help probe must exit 0 and expose all required flags: `sf agent preview start --help` must expose `--authoring-bundle`, `--simulate-actions`, and `--use-live-actions`; the selected send/end command help must expose send: `--utterance`, `--session-id`, and `--authoring-bundle`; end: `--session-id` and `--authoring-bundle`. The send/end commands do not take the action-mode flags. Start with `--authoring-bundle` and `--simulate-actions`. A published `--api-name` preview executes real actions and cannot substitute for this simulation. Salesforce CLI 2.130.9 release notes are dated context for the action-mode selection, but numeric version alone is not capability proof. Do not install or update anything. Do not silently use `--use-live-actions`, and never use a live-action fallback for failed simulation readiness.

A failed or unknown prerequisite leaves only this simulated-preview mode unavailable. Record exact `PREVIEW_SIMULATION_UNAVAILABLE` evidence. Use an already-approved supported alternate validation only when it meets the same canonical evidence requirement; otherwise validation remains unresolved. Mode B is separately checked and can execute real actions, so this simulation gate neither universally blocks Mode B nor blocks unrelated operations. CLI help proves a command surface only, not auth, license, runtime, or action readiness.
