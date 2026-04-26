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

**Before You Demo**
- [ ] [SE Manual Checklist items from spec + change log "SE Must Do Next", rephrased with Setup navigation paths where applicable]

**For each `actions_unverified_in_preview` entry in the change log, append a checklist item.** The canonical definition of this field lives in `.claude/prompts/phase3.md`. Formatting rules:
- **Knowledge grounding entry:** append verbatim:
  - [ ] After creating the Data Library, run one grounded utterance in Builder (e.g. an utterance that should pull from a specific Knowledge article) and confirm a citation or source reference appears in the response. If the response is plausible prose without a source, the Data Library is not linked — fix before demo.
- **Any other entry** (MessagingSession-dependent actions, etc.): append one line per entry in the form `- [ ] [action name]: [reason from the entry]`.

**Your Files**
All files for this demo live in one folder. To open it in Finder:
```
open orgs/[alias]-[customer]/
```
- `demo-spec-[...].md` — full build spec (what and why)
- `changes-[...].md` — deployment log (what actually happened, rollback commands)
- `audit-[...].md` — org snapshot before deployment

**Caller note (not part of the rendered brief):** after outputting the brief, scout-building offers the SE a y/n to write this same content to a Slack canvas in their personal Slack. See `scout-building.md` Step 8c for the procedure.
