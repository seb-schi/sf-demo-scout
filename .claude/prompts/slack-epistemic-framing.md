# Slack — Epistemic Framing

Shared framing loaded by every prompt that touches Slack content.
Single source of truth — do not duplicate this block inline anywhere else.

Slack content is **medium-confidence context, not ground truth**. SE knowledge
and Salesforce docs take precedence in specs and handovers. Never assert a
Slack claim as fact — always attribute to source message + date.

Rules:
- Attribute every claim: `[#channel], [date]: [author] mentioned [X].`
- Avoid assertive framing. Not: *"The customer's top pain is X."* Yes: *"[#help-sell-medtech], 2026-03-18: @simon flagged X as a recurring concern."*
- When signals conflict across messages, surface both. Do not synthesise a winner.
- If Slack content contradicts a Salesforce doc or the org audit, flag the conflict. Slack does not override docs or the audit.
- Do not infer pain points or goals the customer has not said themselves in a quoted message. Account-team chatter is colour, not ground truth.
