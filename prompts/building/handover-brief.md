# Demo Handover Brief Template

Synthesize a handover brief from the spec (Customer Context + Scenario) and the change log results. Output to terminal only — no file.

Format (output as plain text, not a blockquote):

**Demo Handover — [Customer]**

**What Was Built**
[1-2 sentences in business terms — from the spec scenario, not component names]

**Demo Story**
1. [Open with... — entry point and context-setting]
2. [Show... — core capability in action]
3. [Then... — supporting workflow or automation]
4. [Close with... — value moment tied to pain point]

(Derive from spec's Business story + Core capability + Pain point addressed.
Use "Show the customer..." framing. 3-5 steps.)

**Already Done (Scout handled this)**
Synthesise only reconciler VERIFIED items from the change log. Each bullet is a
plain completed fact, not a checkbox. Say "already matched before this build" for
`already_satisfied`; never imply this run changed it. Do not include SKIPPED,
AWAITING_QA, FAILED, BLOCKED, or INCOMPLETE items here. Include whichever of the
following are VERIFIED in the change log:
- Companion permset deployed and assigned to the running user: [name]
- Standard Agentforce runtime permset assigned: [name] (only if `deployed.standard_permset_assignment.status = "SUCCESS"`)
- Deployed metadata summary in one line: [N objects, N fields, N flows, N Apex classes, N LWC, N Agentforce agents — pull from change log counts]
- Data seeded: [object counts — pull from change log]
- Calibration applied (only if `discovery_notes` carries a `"Calibration applied:"` entry): [directive — reference query returned X, seed value computed as Y, spec literal was Z]
- Agentforce smoke test: [pass/fail count from change log]

**Built — Validate in Sonnet (Scout attempted these; finish them in this session)**
Scout attempts every metadata-authorable artifact — including ones with NO build-time signal. That covers complex Apex and screen flows (looped against an Apex test / happy-path FlowTest) AND no-signal *visual* surfaces (a deployed FlexiPage / Lightning page, a classic Page Layout arrangement, a screen flow using a non-whitelist component, a complex LWC's rendered UI, a dashboard). Where a signal existed but did NOT go green, or where there is no signal at all, the artifact was still DEPLOYED — but honestly reported unconfirmed, never "working." These are NOT platform limits; finish them right here by telling Claude what to adjust (it reaches for `sf-flow`, `platform-apex-test-run`, `platform-flexipage-generate`, and friends against your org). Include only what applies:
- [ ] **Every reconciler AWAITING_QA item:** [ledger item id] — [remaining test,
  visual, or live-runtime confirmation].
- [ ] **Every remaining Agentforce action, guardrail, or test obligation:** [ledger
  item id] — [runtime assessment and exact next live test]. A current hero-action
  PASS clears only its own ledger item. Do not carry worker smoke booleans forward
  as proof, and do not erase other required checks.
- [ ] **Test-unvalidated Apex:** for each Apex class in the change log's "Issues Encountered" whose generated test failed or is low-coverage — review the logic and the test, then iterate in this session until it passes (or confirm the demo path works without it). The class IS deployed.
- [ ] **Draft screen flows:** for each screen flow the change log lists as `Draft` (its happy-path FlowTest did not pass twice) — walk the logic, fix, re-run the test, and activate. A Draft flow will NOT fire on the org until activated.
- [ ] **Screen-flow visual QA:** walk through each activated screen flow once in the Lightning UI (labels, button order, help text) — this has no metadata signal and is always a human-eyes step.
- [ ] **No-signal visual artifacts (deployed, unconfirmed):** for each item the change log flags as deployed-but-needs-visual-QA (a new/edited Lightning page or FlexiPage, a Page Layout arrangement, a screen flow using a non-whitelist component, a custom LWC's rendered UI, a dashboard) — open it in the relevant builder, confirm it renders/behaves as the story needs, and adjust. The metadata IS deployed; there is simply no build-time signal that could confirm the visual result.

**Your Setup (Salesforce UI — no API path)**
These are Salesforce platform limits, not Scout gaps — the Metadata API does not expose these surfaces, so no tool can automate them. Populate from the spec's SE Manual Checklist + the change log's "SE Must Do Next":
- [ ] **Every reconciler BLOCKED manual item:** [ledger item id] — [specific SE
  action]. Keep it visible until completed; a manual handoff is not a skip.
- [ ] [SE Manual Checklist items from spec + change log "SE Must Do Next", rephrased with Setup navigation paths where applicable]

**For each `actions_unverified_in_preview` entry in the change log, append a checklist item under Your Setup only when its reconciled ledger item remains AWAITING_QA, BLOCKED, FAILED, or INCOMPLETE.** Do not resurrect an entry whose exact action obligation has a current independent PASS; keep unrelated outstanding entries. The canonical definition of this field lives in `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase3.md`. Formatting rules:
- **Knowledge grounding entry:** append verbatim:
  - [ ] After creating the Data Library, run one grounded utterance in Builder (e.g. an utterance that should pull from a specific Knowledge article) and confirm a citation or source reference appears in the response. If the response is plausible prose without a source, the Data Library is not linked — fix before demo.
- **Any other entry** (MessagingSession-dependent actions, etc.): append one line per entry in the form `- [ ] [action name]: [reason from the entry]`.

**If the change log has an "Agent Not Live — UI Commit Required" section** (Phase 3 `NeedsUICommit`), append this checklist item verbatim under Your Setup — the agent is authored + validated but the org instance's headless publish route 404'd, so go-live is a UI step:
- [ ] Agent **[api_name]** is authored + validated but NOT live (this org instance's headless publish route is not provisioned — a Salesforce platform gap, not a Scout limit). Take it live via the Builder UI runbook (`prompts/building/agent-ui-commit-runbook.md`): New Draft → merge your real topics into the template shell → reconcile action I/O → Commit → Activate. Then verify action side-effects in a live Messaging Session. Escalate the instance gap: Salesforce Support case citing the org instance ID.

Append the change log's **actual absolute recovery artifact and recovery bundle
paths** to that item so the SE can follow the runbook in a later session. If
preservation is blocked, say so, include the original scratch path and cleanup-
withheld warning, and direct the SE to resolve preservation before proceeding.
Never describe an unverified or scratch-only file as a preserved blueprint.

For an **Existing Agent Before-State** section, carry the original active version,
verified pre-edit artifact and exact source/member paths into the handover's
rollback notes. On preservation failure, carry the BLOCKED status and retained
scratch location; do not promise file-level rollback. Runtime validation never
substitutes for the missing before-state.

**Want to Change Something? Two Ways.**
This demo isn't locked. Pick the door that fits:

**Quick tweak, fix, or tinker — stay right here.** Wrong picklist value, a flow that should fire on close instead of create, seeded data that doesn't fit the story, a field in the wrong spot? Just tell Claude what you want changed in this session — it'll reach for the right Salesforce skill (`sf-flow`, `experience-lwc-generate`, `platform-data-manage`, and friends came with Scout) and make the change live against your org. Free-wheeling and fast. These edits won't be written back to the spec — and that's fine for iteration.

**New scenario or structural rework — run `/scout-sparring`.** A different headline, a new agent, a story rebuild, anything you want captured in a clean spec with a fresh talk track and click path. Open a new Claude Code session and run `/scout-sparring` (iteration intent — and if you know the scenario cold, just tell Scout to move fast). It writes a new spec; `/scout-building` re-deploys over the top. Iterating an existing demo is a first-class Scout capability — not a restart.

**Your Files**
All files for this demo live in one folder. To open it in Finder:
```
open [ORG_FOLDER]/
```
- `demo-spec-[...].md` — full build spec (what and why)
- `changes-[...].md` — deployment log (what actually happened, rollback commands)
- `audit-[...].md` — org snapshot before deployment

**For each entry in the change log's Script Deliverables section**, append under Your Files:
- `[script filename]` — reusable seed/harness script. Pilot rehearsal: `[pilot_command]`. Bulk run: `[bulk_command]`. Safe to re-run after a re-spin.

(Skip this block entirely if the change log's Script Deliverables section reads "None — deployment was metadata-only.")

**Caller note (not part of the rendered brief):** after outputting the brief, scout-building offers the SE a y/n to write this same content to a Slack canvas in their personal Slack. See `scout-building.md` Step 6c for the procedure.
