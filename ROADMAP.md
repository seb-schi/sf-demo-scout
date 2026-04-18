# Scout Roadmap

Status snapshot of Scout's milestone plan. Updated during /project-sparring when milestones ship or shift. This file is the source of truth for "what are we building next."

## Guiding Principles

- **Test before expand.** Self-testing (M1) precedes capability expansion.
- **Gates stay.** SE confirmation on risky deploys is a feature. Gate reduction is fine; gate elimination is not.
- **Existing patterns first.** Adopt Salesforce-native tooling (Agent Script, Grid, Docs MCP) over custom layers where it covers the need.
- **Bedrock-compatible only.** No milestone depends on Anthropic-direct-only features unless the provider changes.

## Milestones

### M0 — Docs MCP Adoption ✅ shipped 2026-04-18
Adds the Salesforce Docs MCP server. Closes the Bedrock no-web-access gap for sparring (version-aware feature confirmation, real citations) and deployment diagnostics (look up error messages instead of guessing).

### M1 — Self-Testing Harness
`npm test`-equivalent for the pipeline itself. Fixture PLAN files with expected LOGs; scratch-org CI runs canonical /scout-building against a fixture spec; regression corpus where every lesson has an executable repro.
- **Why first after M0:** every other milestone adds risk. Without tests, capability expansion compounds that risk.
- **Hard part:** scratch-org auth that survives CI. Local-only is acceptable for v1.

### M5 — Rollback Automation
`/undo-last` command that parses the most recent change log and executes rollback commands in reverse dependency order. Small (1-day), high-value, ships before M3/M4.

### M7 — Spec Validation Before Build
Opus self-reviews its own spec against a schema before handing off to Sonnet. Closes the class of failures where ambiguous spec items ("add a formula field") become sub-agent guesses that break demos subtly.

### M2 — Scratch-Org Staging for /scout-building
Deploy to ephemeral scratch org first, smoke-test (SOQL verifies records, permset assignment), promote to real org on success only. Scope: net-new metadata only (scratch orgs don't have IDO/SDO managed packages; modifications to pre-installed scenarios still hit the real org).

### M3 — Advanced Flows
Lift SE Manual Checklist restriction for screen flows, scheduled flows, multi-object flows. Requires M1 + M2 first. New skill: `validating-flow` (execution-order check, fault-path validation). Subflows last (dependency resolution).

### M4 — Advanced Agentforce (Agent Script exploitation)
Fully exploit Agent Script features Scout doesn't currently spec:
- **M4a:** expand `.claude/prompts/spec-template.md` to include subagents, `before_reasoning` hooks, filtered visibility (`available when`), action chaining as first-class spec elements.
- **M4b:** update `scout-sparring` to ask Agent Script-aware questions (role-based views? pre-turn hydration? deterministic steps?).
- **M4c:** new `validating-agent-script` skill — variable kind misuse, transition dead-ends, missing `after_reasoning` cleanup, `available when` gaps.
- **M4d (wait for roadmap):** Cross-Agent Orchestration is on Salesforce's Agent Script roadmap. Do not build a custom multi-agent layer; adopt natively when it ships.

### M6 — Lesson Pruning
Quarterly or manual `/prune-lessons`. Opus reads all lessons, proposes merges / deletions / contradictions, SE approves. Prevents linear lesson-file bloat.

### M8 — Grid-Based Demo Verification
After Phase 3 deploys an agent, auto-create a Grid worksheet pre-populated with demo scenarios from the spec, run the worksheet, assert pass rate. Failures land in change log's "SE Must Do Next". New skill: `verifying-agentforce-grid` (narrow scope — not a generic Grid configuration kit).
- **Prerequisite:** verify Grid endpoints are GA (not pilot) and licensed on common demo orgs.

## Watch List (Do Not Build Against Yet)

- **Agentforce Arc** — "agents building agents" plan generator. Architecturally overlaps with Scout's orchestrator. May collapse M4 to a thin wrapper. Waiting for full documentation before scoping.
- **MCP+** — post-processing token compression. Marginal fit for Scout (our bottleneck is orchestrator context, already solved via sub-agents). Revisit if audit step runs long.
- **Agent Script native MCP integration** — once shipped, agents call MCP directly instead of via Apex. Changes the right answer for "how do I give the agent data access." Track release notes.
- **Bedrock auto mode** — when it ships, replaces `permissions.allow` as the primary permission strategy.

## Exploration Threads

- **Remote HTTP MCP ecosystem scan.** M0 proved remote HTTP MCPs bypass the Bedrock Haiku sub-processor block. Every remote HTTP MCP is therefore a Bedrock-safe capability Scout can adopt. Scan the MCP ecosystem (GitHub, Linear, Jira, internal Salesforce tooling, Grid when it ships as MCP) filtered by transport type; catalogue which are remote HTTP vs stdio + Anthropic-hosted processing. Afternoon's work. Output: a shortlist of Bedrock-compatible MCPs worth piloting.
- **Scout as an MCP composition layer.** If remote HTTP MCPs keep shipping, Scout's value increasingly becomes *orchestrating across them* — demo org config (Salesforce DX) + docs (Docs MCP) + verification (Grid MCP, if it comes) + customer-specific knowledge sources. The Opus-orchestrator + Sonnet-executor pattern is already the right shape for this. Revisit when the ecosystem scan returns — if there are 3+ worthwhile MCPs to compose, this becomes a first-class architectural direction rather than an ad-hoc adoption per server.

## Sequence Summary

Q1: M0 ✅ → M1 → M5 → M7 (foundations)
Q2: M2 → M3 (capability expansion on stable foundation)
Q3: M4 → M6 → M8 (hardest work; needs everything else in place)
