# /scout build cards and the monthly summary

Every finished task's handover ends with a build card: the build's facts, as they would be posted, and one question, whether to share it in a Slack channel with a line from the builder. Cards are on by default, and `/scout cards off` stops them.
- **Nothing is posted** without the builder's yes to the exact text.
- **Scout never gives a time estimate of its own.** The time saved is only ever the builder's own estimate.
- **No telemetry:** a card the builder doesn't share stays on this machine.

**Run every step with the helper:** `python3 -B [PLUGIN_ROOT_ABS]/scripts/scout_card.py <command>`.
- It needs no org. `[T]` is the task record's absolute path.
- It prints JSON. Exit 0 means done; 3 refused (say the reason); 4 a local file couldn't be read or written (it's kept as it is; say so, and the handover still goes out).

## Local commands

| The builder says | Run |
|---|---|
| `/scout cards on` or `/scout cards off` | `cards on` or `cards off`, then confirm in one line |
| `/scout cards channel #name` | `channel --set "#name"`, which saves where cards are shared |

## At handover

`${CLAUDE_PLUGIN_ROOT}/prompts/scout/history.md` sends you here last, after any string telephone line.
- **Run** `handover --task [T] --host [SCOUT_HOST]`.
  - Add `--logbook` when this task went through a string telephone.
  - Add `--products '[…]'` with your proposal from the fixed list: Sales, Service, Marketing, Commerce, Data 360, Agentforce, Industries, Platform.
- **End the handover message with the `lines` it returns,** after the history block's yes, edit or skip question. With cards on, the helper saves the task's card before you send. A task that already has a card returns no lines.

## The builder's reply

**A reply starting with `share`:**
1. **The channel:** if the reply names one, or none is saved yet, run `channel --set "#name"`. With no channel at all, ask for one.
2. **The builder's own answers,** saved with `answer --task [T]` plus what they gave:
   - `--comment "…"`: their words as written. First check that the words hold no org or customer names, IDs, usernames or record values. On exit 3, ask them to rephrase.
   - `--rating good|ok|poor`
   - `--time-kind hours|unknown|none|time_lost`, with `--hours N` if they gave a number. "It cost me time" is `time_lost`.
   - `--products '[…]'`
3. **The exact post:** `share-text --task [T]` returns the text, the channel, their `digest`, and whether each still matches the handover's preview (`text_shown`, `channel_shown`). The flags compare content; they don't prove the builder saw it.
   - A bare `share` goes ahead only as the builder's reply to a message in this conversation that showed this exact text and channel, such as the handover's card, with both flags true. When the builder named the channel in this reply, `channel_shown` may be false.
   - Anything else, such as added words, an answer saved earlier, a new channel, or a preview the builder may not have seen after an interruption or a compaction: show the exact text and the channel, and ask once for a yes.
4. **Post it,** when the host has its own Slack tool: run `posting --task [T] --digest [the digest of the text the builder approved]` right before the send, then post its `text` as a message to that channel. When the host has no Slack tool, say so and give the text to copy; the card isn't marked.
5. **Then settle it:**
   - After a successful post, run `shared --task [T]`.
   - When the tool says nothing was sent, run `not-posted --task [T]`.
   - When the outcome is unclear, never send again. Ask the builder to check the channel; if the post isn't there, `not-posted` frees the card.
   A shared card isn't offered for posting again.

**Other replies:**
- A bare "yes", "edit" or "skip" answers the history question, not the card. The card stays on this machine.
- A rating or time answer without `share` saves it on the card through `answer`. Nothing is posted.

## The monthly summary

- **Run** `/scout summary [YYYY-MM]`, which calls `summary [--month YYYY-MM]`. The default is last month.
- **Show its `text` as a copyable block.** It carries counts only, and its time figures are the builders' own estimates.
- **List `invalid_cards` to the builder separately,** never inside the text.
