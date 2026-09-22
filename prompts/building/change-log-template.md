# Change Log — Template

Save to: `[ORG_FOLDER]/changes-[YYYY-MM-DD]-[HHmm]-[CUSTOMER].md` (the ORG_FOLDER resolved at building Step 1)
Also output the full change log to the terminal.

HHmm = local time at change log creation (e.g. 0930, 1445).

```markdown
# Change Log — [Customer] — [Date] [HHmm]
Org: [alias] ([username])
Spec: demo-spec-[DATE]-[HHmm]-[CUSTOMER].md
Audit used: audit-[YYYY-MM-DD]-[HHmm].md

## Achieved State — [as-of receipt timestamp]
[Current reconciler disposition and observed state; distinguish active/Draft,
failed/blocked work and remaining runtime, agent, UI and recovery obligations.]
[When newer evidence changes an earlier summary, name the receipt/time and the
summary it supersedes. Keep the earlier report as history. Preserve policy refusals
separately from actual state; do not undo or conceal a later successful mutation.]
[Writer-owned project and ownership receipt paths; preservation failures retained.]

## What Was Deployed
[Every component, grouped by type — include API names]

## What Was Skipped
[Only reconciler SKIPPED items: item id, explicit authorization type, independent
decision source, and reason. Do not put failures, blocked/manual work, or QA here.]

## Completion Reconciliation
Overall: [FULLY_VERIFIED | FINISHED_WITH_EXCEPTIONS | UNRESOLVED]
Spec SHA-256: [digest]
Build ID: [id]

### Verified — Applied This Build
- [ledger item id] — [targeted current-state evidence] — change source: [current
  receipt or saved before/after evidence]

### Verified — Already Satisfied Before This Build
- [ledger item id] — [exact targeted state] — baseline source: [saved pre-dispatch
  observation]. Never describe these as deployed by this run.

### Accounted-for Exceptions
- [SKIPPED item + decision source, or AWAITING_QA item + remaining confirmation]

### Unresolved Work
- [FAILED | BLOCKED | INCOMPLETE] [ledger item id] — [cause] — [specific next action]

Preserve the reconciler's validation errors and independent evidence/probe references.
Presence and deployment receipts alone never belong in either Verified subsection.

## Companion Permission Set
[Name, coverage, assignment status]

## Business Processes Deployed (if any)
[API names (as Object.ProcessName), driving picklist, values, record type bindings]
Rollback: restore an incumbent from its verified before-state under the shared
component contract; delete only an exact positively-proven-new BusinessProcess.

## Paths Deployed (if any)
[API names, object, record type, driving field, step count]
Rollback: restore an incumbent from its verified before-state under the shared
component contract; delete only an exact positively-proven-new PathAssistant.
Note: visual placement of the Path component on the Lightning record page is SE Manual (App Builder).

## Flows Deployed (if any)
[API names, description, active/draft status]
Rollback: incumbents stage the preserved original definition; reactivate only a
recorded original active ID/version. An originally inactive Flow requires read-back
that still proves inactivity. Unknown state remains unresolved; current active state
requires a supported deactivation/read-back route or BLOCKED manual deactivation. Do
not claim completed rollback. Delete only an exact positively-proven-new Flow.

## Apex Deployed (if any)
[Names, description]
Rollback: incumbents restore the verified first source+companion snapshot; delete only
exact positively-proven-new classes/triggers/tests.

## LWC Deployed (if any)
[Names, description]
Rollback: incumbents restore the verified first whole bundle snapshot; delete only an
exact positively-proven-new bundle.

## Agentforce Deployed (if any)
[Names, description]
Rollback: for existing-agent modifications, reactivate only the recorded original
active version and use the verified Phase 3 before-state member paths if source restore
is required. Delete only an exact positively-proven-new AiAuthoringBundle and its
positively-proven-new backing classes after the explicit destructive-action guard.

## Agentforce Current-Test Evidence (if any)
[For every action-bearing ledger item: item id; runtime assessment
PASS|FAIL|BLOCKED|UNAVAILABLE|INVALID and reason; independently recorded deployed version
+ deployment source; selected current session+turn or exact job+case +
identity source; canonical gate digest; invocation evidence channel/kind/source;
mutating target/before/after delta or read-only output assertions; structural method
and source. Preserve prior failed attempt references and any explicitly selected
fixed retest. Worker smoke booleans are summary only. A PASS resolves only that item;
list every remaining Agentforce action, guardrail and QA obligation separately.]

## Actions Unverified in Preview (if any)
Aggregated from the Phase 3 sub-agent's `actions_unverified_in_preview` array (see `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase3.md` for the canonical definition). The SE must verify each entry manually — in a live Messaging Session for session-context-dependent actions, or in Builder after creating dependent resources (e.g. Data Libraries for Knowledge grounding).
- **[Action name]** — [reason]

## Agent Not Live — UI Commit Required (only if Phase 3 `deployed.agent.status` = NeedsUICommit)
Include ONLY when the Phase 3 sub-agent set `deployed.agent.status: NeedsUICommit` — the headless SFAP publish route returned 404 on this org instance (a per-instance platform provisioning gap; the agent is authored + validated but NOT live). Record the verbatim endpoint/404/instance-ID evidence from the sub-agent's `discovery_notes`. Go-live path: `${CLAUDE_PLUGIN_ROOT}/prompts/building/agent-ui-commit-runbook.md` (Builder UI). Escalation: file a Salesforce Support case citing the org instance ID (cross-post evidence to #agentforce-dx).
- **Agent:** [api_name] — authored + validated, NOT live. Go live via the Builder UI runbook; escalate the instance gap to Support.
- **Recovery artifact:** [actual absolute verified artifact path]
- **Recovery bundle path:** [actual absolute artifact/source/aiAuthoringBundles/AgentName path]
- **Preservation:** [verified by orchestrator / BLOCKED with error + original scratch path; cleanup withheld]
Use actual paths from `deployed.agent.recovery` only after independent verification;
on failure leave the durable-path fields unavailable and record the original path.

## Imported Assets Used (if any)
- [component identity] — [existing spec item + phase]; preserved at [absolute artifact path]; [used/adapted/skipped/blocked + reason]. List selected imports only; preservation does not prove deployment.

## Existing Agent Before-State (only for modified incumbent agents)
- **Agent / original active version:** [actual API name and version before editing]
- **Pre-edit artifact / source:** [actual absolute independently verified `agent-preedit` artifact and source paths]
- **Exact bundle members:** [relative receipt paths, including actual suffixes]
- **Preservation:** [verified / BLOCKED with error and original scratch location; cleanup withheld]
- **Rollback:** [recorded version reactivation; if source restore is needed, verify the artifact and copy/redeploy these exact members from its immutable source into a disposable restore project]
Never use a later retrieve as the original before-state or imply a redeploy deletes
a published version. Keep this evidence separate from a new-agent UI-commit blueprint.

## Existing Component Before-State and Direct Repairs (if any)
- **Attempt / org / exact component:** [pending attempt id, target org, metadata identity]
- **Classification / source:** [existing | new | unknown] — [saved exact-target or positive-absence evidence]
- **Requested delta / exclusions:** [frozen values]
- **First pre-edit artifact / source / members:** [actual absolute verified `component-preedit` paths and exact receipt members, or not_needed/BLOCKED]
- **Original Flow activation (Flow only):** [active with exact ID/version | inactive | unknown] — [saved source]
- **Outcome / read-back:** [applied | already_satisfied | failed | blocked | unverified] — [targeted evidence and unrelated incumbent checks]
- **Rollback:** [verified exact restore/reactivation route, or proven-new exact delete route]

Write the `PENDING — component repair` row before retrieval or mutation, then update
the same row with its outcome even on failure or no-op. Never replace the first
before-state on retry. Keep Report and ReportFolder classification separate; a folder
with later-added or unknown contents is retained.

## Execution Order Check
[Per-object list of active flows after deployment. Flag objects with multiple after-save record-triggered flows and note execution order risks.]

## Script Deliverables

Persistent artifacts from this deployment the SE can re-run after a re-spin or hand to a colleague. Each script is idempotent and exposes `--pilot-only` for a safe one-record rehearsal.

- **[script path]**
  - Pilot: `[pilot_command]`
  - Bulk: `[bulk_command]`
  - Self-test: [PASS | FAIL with brief reason]

(If this deployment produced no scripts, write "None — deployment was metadata-only.")

## Issues Encountered
[Errors, workarounds, second attempts]

## Docs Consulted
Aggregated from sub-agent `docs_consulted` arrays + any orchestrator-level error-recovery consultations.
- **Phase:** [1|2|3|orchestrator] — **Question:** [one line]
  - **URL:** [doc URL]
  - **Verdict:** [what the doc confirmed/contradicted/left ambiguous]

## SE Must Do Next (in order)
1. [Specific steps with UI paths]

## How to Verify
[Step-by-step test sequence]

## Open Questions for Next Session
[Unresolved items, follow-up]
```

After saving, tell the SE:
> "Change log saved. Review 'SE Must Do Next' — complete those before the demo."

Diagnostic accuracy: a test execution may roll back business DML while persisting test
result records; do not label it literally read-only. Aggregate failures do not identify
a failed assertion. A failed inventory pipeline is unavailable evidence, not absence
or proof that every supported route is impossible. Retain inconclusive diagnostics
separately from the required acceptance tests.
