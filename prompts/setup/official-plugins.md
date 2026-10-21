# Scout Setup — Salesforce's official plugins

Scout builds by driving Salesforce's official Claude plugins from Salesforce's own GitHub marketplace (`salesforce`), kept current by auto-update. This step installs all five Scout uses, once: `salesforce-development`, `salesforce-code-quality`, `agentforce-adlc` (Agentforce), `experience-lwc` (Lightning Web Components) and `service-engagement` (Email-to-Case and messaging). It also switches off the official plugin's plugin suggestions inside Scout's workspace, where its hook would interrupt Scout's commands. It never touches logins, default orgs or aliases, changes other plugins only after the builder's yes, and never removes anything.

Resolve this active Scout installation's root to an absolute path first, substitute it, `[SCOUT_HOST]` and `[LAUNCH_DIR]` (the folder this session started in), then run it with a 10-minute timeout, since downloading five plugins from GitHub can take a few minutes:

```bash
SCOUT_OFFICIAL_SETUP="/absolute/path/of/active/sf-demo-scout/scripts/setup-official-plugins.py"
WS_SETTINGS="${SCOUT_WORKSPACE:-$HOME/claude-projects/sf-demo-scout}/.claude/settings.json"
if [ ! -f "$SCOUT_OFFICIAL_SETUP" ]; then
  echo "OFFICIAL_PLUGINS_UNAVAILABLE shipped script not found"
else
  python3 -B "$SCOUT_OFFICIAL_SETUP" --host "[SCOUT_HOST]" --workspace-settings "$WS_SETTINGS" --launch-dir "[LAUNCH_DIR]"
fi
```

In a self-repair run where the builder said no (`skills/scout-setup/SKILL.md`), add `--keep-builder-choices` to that command, and skip the next block.

Then update the Salesforce CLI's own add-on plugins (built-in ones update with the CLI; plugins such as `flow` and `code-analyzer` install themselves the first time Scout uses them):

```bash
sf plugins update >/dev/null 2>&1 && echo "SF_PLUGINS_UPDATED" || echo "SF_PLUGINS_UPDATE_FAILED"
```

Surface in plain language, and carry every non-silent line into the done summary:
- `OFFICIAL_PLUGINS_SKIPPED host=…` — silent: on Codex and Cursor, `prompts/setup/other-hosts.md` sets up Salesforce's skills instead.
- `OFFICIAL_PLUGINS_UNAVAILABLE <reason>` — "Scout couldn't install Salesforce's plugins (<reason>). Run `/scout-setup` again from the Terminal app (`claude`, then `/scout-setup`)."
- `OFFICIAL_MARKETPLACE_ADDED <name>` — "Added Salesforce's official plugin marketplace from GitHub." `…_PRESENT` — silent.
- `OFFICIAL_MARKETPLACE_FAILED <reason>` or `…_UNKNOWN` — "Scout couldn't add Salesforce's plugin marketplace (<reason>). Scout needs it for building: check your network or company plugin policy, then run `/scout-setup` again." Skip the remaining lines' messages.
- `OFFICIAL_AUTOUPDATE_SET[…]` — "Turned on automatic updates for Salesforce's plugins." `…_ALREADY[…]` — silent. `…_LEFT_AS_CHOSEN[…]` — "Automatic updates for Salesforce's plugins are switched off, as you set them; turn them on under `/plugin` → Marketplaces if you want Scout to drive Salesforce's latest skills." `…_NO_ENTRY[…]` — "Turn on auto-update for the `salesforce` marketplace in `/plugin` → Marketplaces." Any other `OFFICIAL_AUTOUPDATE_…` — one-line note.
- `OFFICIAL_PLUGIN_INSTALLED <name>` / `…_ENABLED <name>` — one combined line naming them, with versions from `OFFICIAL_PLUGIN_VERSION <name> <version>`. `…_PRESENT` and `…_VERSION` alone — silent. When `experience-lwc` was just installed, add: "Salesforce's LWC plugin also runs a quick style check whenever Claude writes a web file (HTML, CSS or JavaScript), in any folder; the first time, it downloads Salesforce's style checker."
- `OFFICIAL_PLUGIN_LEFT <name> <state>` — a self-repair run left, as the builder asked, a plugin that's switched off (`disabled`) or not installed (`installable`, whether removed or never installed): "<name> stays as it is; builds that need it will ask."
- `OFFICIAL_PLUGIN_FAILED <name> <reason>` — one line each: "<name> didn't install (<reason>). Builds that need it will report those items blocked until `/scout-setup` succeeds."
- `OFFICIAL_PINNED <name> <ref> <plugins>` and `OFFICIAL_DUPLICATE <id>` — Scout takes charge of the builder's existing Salesforce plugins, with **one** question naming exactly what would change, in plain words: "Scout would like to take charge of your Salesforce plugins: [for each pinned line: your Salesforce marketplace '<name>' is fixed to <ref>; switch it to follow Salesforce's latest from now on, which updates every plugin installed from it: <plugins>] [for each duplicate: switch off the extra copy <id>; it stays installed and you can switch it back on in `/plugin`]. OK?" On a yes, rerun the exact same command (keeping any `--plugins`) with `--unpin <name>:<ref>` for each pinned line and `--disable-duplicates <id> …` naming each listed duplicate. Setup acts only on those. On a no, change nothing and say: "Then Scout keeps working with what's there: [the version it's fixed to / it will stop before using a skill that loads from the extra copy]."
- `OFFICIAL_UNPINNED <name>` — "Your Salesforce plugins now follow Salesforce's latest." `OFFICIAL_PLUGIN_UPDATED <name> <old> <new>` — one combined line with the versions; `OFFICIAL_PLUGIN_CURRENT …` — silent. `OFFICIAL_UNPIN_PARTIAL <name> <updated>/<total> <plugins>` with its `OFFICIAL_PLUGIN_UPDATE_FAILED <name> <reason>` lines — "<updated> of <total> plugins updated; these didn't: <plugins> (<reasons>)." Then retry once, within the same approval, by rerunning the same command with `--unpin <name>`. `OFFICIAL_UNPIN_FAILED …`, `…_INCOMPLETE …` or `…_SKIPPED …` — one line with its reason, as given.
- `OFFICIAL_DUPLICATE_SKIPPED <id> …` — one line: that copy is no longer an extra one, so nothing changed.
- `OFFICIAL_PROJECT_COPY <id> <file>` — "This folder's own plugin selection (<file>) switches on another copy, <id>. Scout doesn't change project plugin selections: switch it off there if you'd like Scout to build from this folder." (Builds report it too.)
- `OFFICIAL_PERSONAL_COPIES <count> <folders>` — "There are <count> possible personal copies of Salesforce skills in <folders>, probably from `npx skills add`. They're outside Scout's automatic updates, and Scout uses the official plugins' versions. Keep or remove them as you like." Never offer to move or delete them. `OFFICIAL_PERSONAL_COPIES_UNKNOWN …` — silent.
- `OFFICIAL_DUPLICATE_DISABLED <id>` — one combined line naming them. `OFFICIAL_DUPLICATE_FAILED <id> <reason>` — one line each.
- `OFFICIAL_RECOMMENDER_ENV_SET[…]` — "Switched off the official plugin's plugin suggestions inside Scout's workspace, where they would interrupt Scout's commands." `…_ALREADY[…]` — silent. Any other `OFFICIAL_RECOMMENDER_…` — one-line note.
- `OFFICIAL_PLUGINS_DONE restart=needed` — "Restart Claude Code, or run `/reload-plugins`, so the new plugins load." `restart=no` — silent.
- `OFFICIAL_READINESS ready` — silent. `OFFICIAL_READINESS blocked <plugin>:<state> …` — the done summary must not say "ready": name each plugin and its fix (`setup-needed`, `installable` or `unknown`: rerun `/scout-setup`; `conflict`: switch the other copy off; `disabled`: switch it on in `/plugin`). `OFFICIAL_READINESS not-applicable …` — silent.
- `SF_PLUGINS_UPDATED` — silent. `SF_PLUGINS_UPDATE_FAILED` — one-line note; Scout still works.
