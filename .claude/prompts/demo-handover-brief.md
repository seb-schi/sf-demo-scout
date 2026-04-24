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

**Your Files**
All files for this demo live in one folder. To open it in Finder:
```
open orgs/[alias]-[customer]/
```
- `demo-spec-[...].md` — full build spec (what and why)
- `changes-[...].md` — deployment log (what actually happened, rollback commands)
- `audit-[...].md` — org snapshot before deployment

Copy the spec and change log into your preferred AI tool (Gemini, ChatGPT, Slackbot) to rehearse talking points or generate a demo script.

**Caller note (not part of the rendered brief):** after outputting the brief, scout-building checks the handover-canvas toggle in `orgs/slack-sources.md` and optionally writes this same content to a Slack canvas owned by the SE. See `scout-building.md` Step 8c for the procedure.
