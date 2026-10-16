# Offer the demo flow as a Slack canvas

Read after the handover, when the task has a Demo Story and this session exposes a Slack tool that creates a standalone canvas without posting it to a channel, as the Slack connector's canvas-create tool does. Follow `${CLAUDE_PLUGIN_ROOT}/prompts/mcp-readiness.md`; a CLI listing alone doesn't establish the tool. Otherwise skip this silently.

1. **Ask once,** with the history question, in plain words: "Shall I put the demo flow on a Slack canvas for you? It's your own canvas, not posted to any channel; you decide whether to share it."
2. **On a yes, create one canvas** with the discovered tool's own schema. The title is `Demo flow — [Customer] — [YYYY-MM-DD]`. The content, in canvas-flavored Markdown:
   - the Demo Story, beat by beat, with each beat's persona and login, click path, record and proof moment, as the handover tells them
   - then "Before you present": the handover's visual checks and manual steps

   Use only what the handover states as verified or names as a check. Never include passwords, tokens or org IDs. Never post the canvas to a channel or share it; that's the SE's call.
3. **Show the link in one line:** "Your demo flow is on a Slack canvas: [link]. Check it before you share it." Record the link in the task record.
4. **On a no or a failure,** say so in one line, for example "The canvas didn't work: [reason]. The demo flow is above.", and don't retry.
