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
Synthesise from the change log — reassure the SE about what they do NOT own. Each bullet is a plain statement of a completed fact, not a checkbox. Include whichever of the following are present in the change log:
- Companion permset deployed and assigned to the running user: [name]
- Standard Agentforce runtime permset assigned: [name] (only if `deployed.standard_permset_assignment.status = "SUCCESS"`)
- Deployed metadata summary in one line: [N objects, N fields, N flows, N Apex classes, N LWC, N Agentforce agents — pull from change log counts]
- Data seeded: [object counts — pull from change log]
- Calibration applied (only if `discovery_notes` carries a `"Calibration applied:"` entry): [directive — reference query returned X, seed value computed as Y, spec literal was Z]
- Agentforce smoke test: [pass/fail count from change log]

**Your Setup (Salesforce UI — no API path)**
These are Salesforce platform limits, not Scout gaps — the Metadata API does not expose these surfaces, so no tool can automate them. Populate from the spec's SE Manual Checklist + the change log's "SE Must Do Next":
- [ ] [SE Manual Checklist items from spec + change log "SE Must Do Next", rephrased with Setup navigation paths where applicable]

**For each `actions_unverified_in_preview` entry in the change log, append a checklist item under Your Setup.** The canonical definition of this field lives in `${CLAUDE_PLUGIN_ROOT}/prompts/building/phase3.md`. Formatting rules:
- **Knowledge grounding entry:** append verbatim:
  - [ ] After creating the Data Library, run one grounded utterance in Builder (e.g. an utterance that should pull from a specific Knowledge article) and confirm a citation or source reference appears in the response. If the response is plausible prose without a source, the Data Library is not linked — fix before demo.
- **Any other entry** (MessagingSession-dependent actions, etc.): append one line per entry in the form `- [ ] [action name]: [reason from the entry]`.

**If the change log has an "Agent Not Live — UI Commit Required" section** (Phase 3 `NeedsUICommit`), append this checklist item verbatim under Your Setup — the agent is authored + validated but the org instance's headless publish route 404'd, so go-live is a UI step:
- [ ] Agent **[api_name]** is authored + validated but NOT live (this org instance's headless publish route is not provisioned — a Salesforce platform gap, not a Scout limit). Take it live via the Builder UI runbook (`skills/agentforce-generate/references/agent-ui-commit-runbook.md`): New Draft → merge your real topics into the template shell → reconcile action I/O → Commit → Activate. Then verify action side-effects in a live Messaging Session. Escalate the instance gap: Salesforce Support case citing the org instance ID.

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
