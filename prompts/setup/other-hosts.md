# Setup — Salesforce's skills and the Docs MCP on Codex and Cursor

Run this on Codex and Cursor instead of the Claude-only official-plugins step. Apply `prompts/host-runtime.md`. Each change below happens only on the SE's yes, asked in one plain question per step; on a no, say what that leaves and carry on. Substitute the resolved root for `[PLUGIN_ROOT]` and the host for `[SCOUT_HOST]`.

## 1. Salesforce's official skills

```bash
python3 -B "[PLUGIN_ROOT]/scripts/scout_official.py" check --host "[SCOUT_HOST]"
```

The JSON lists each capability with the plugins it needs. Collect the state of the five Scout uses: `salesforce-development`, `salesforce-code-quality`, `agentforce-adlc`, `experience-lwc` and `service-engagement`.
- All `installed`: silent.
- **Codex,** any `setup-needed` or `installable`: offer to add what's missing, in one question: "Scout builds with Salesforce's official skills. Shall I add [Salesforce's GitHub marketplace and] these plugins to Codex: [the missing ones]? Codex keeps them up to date." On a yes, run `codex plugin marketplace add forcedotcom/sf-skills` when the state was `setup-needed`, then `codex plugin add <plugin>@<marketplace>` for each missing plugin, with the marketplace name Codex reports (normally `salesforce`). Then say: restart Codex so they load; their hooks, Salesforce's own deploy checks, run only after you trust them in `/hooks`, and not on native Windows, where Scout's own checks stand in.
- **Cursor** (and any other host), `setup-needed`: Salesforce ships no Cursor plugin, so offer a clone of its public skills repository, read in place: run `python3 -B "[PLUGIN_ROOT]/scripts/scout_install.py" official-skills --dry-run`, show its plan, and on a yes run it again with `--yes` (allow 15 minutes). It needs Git. A clone that lacks a plugin (`missing`) is out of date: offer `git -C "<clone>" pull --ff-only` on a yes.
- `disabled`: the SE switched it off; say so, and that builds needing it will ask.
- Anything else: one line with the state; builds that need the skills report those items blocked.

**When a build sends you here for named plugins** (a repair, or an optional plugin the SE approved), act on those, core or optional, on the yes the build already has:
- **Codex:** `codex plugin add <plugin>@<marketplace>` for an `installable` one. Codex's command line can't switch a `disabled` one back on, so ask the SE to switch it on in Codex's plugin settings.
- **Cursor:** the clone holds every plugin, so a `missing` one means an old clone: offer `git -C "<clone>" pull --ff-only`.
- **Then, for each named plugin,** run `python3 -B "[PLUGIN_ROOT]/scripts/scout_official.py" resolve --host "[SCOUT_HOST]" --plugin <plugin> --launch-dir "<the folder this session started in>"`, and report its `state`.

## 2. The Salesforce Docs MCP

Run `prompts/setup/salesforce-docs-mcp.md`'s status check first. When it reports `registration=not_observed` or `unknown`, offer the public Agentforce Labs Salesforce Docs MCP, and on a yes:
- **Codex:** `codex mcp add salesforce-docs --url https://salesforce-docs-76258744c9d7.herokuapp.com/api/mcp`, then a new chat.
- **Cursor:** `python3 -B "[PLUGIN_ROOT]/scripts/scout_install.py" docs-mcp --dry-run`, then with `--yes`; then a new chat, or Reload Window.

On a no, Scout reads Salesforce's documentation with the host's own web fetch where it has one, and otherwise records the items that need the Docs as ungrounded.

## 3. The sandbox

Codex and Cursor can run commands in a sandbox that blocks the network or files outside the project. The Salesforce CLI needs both: the org's APIs, and its own files in `~/.sf` and `~/.config`. If a setup or `sf` call is refused, follow the host contract's sandbox rule. Never retry around the refusal.

Return to the dispatching prompt with every line the steps above printed.
