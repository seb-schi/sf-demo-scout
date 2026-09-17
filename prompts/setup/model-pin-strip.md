# Setup — Model-Pin Strip (self-heal)

Read + executed by both `fresh-install.md` and `refresh.md`. Frees the `/model`
picker by removing stale model pins that various Salesforce tools (AI Suite,
DevBar, etc.) inject, sometimes erroneously — they collapse the picker so the SE
can't reach newer models. That residue is NOT written by Scout, so it lands on
Scout-FRESH machines too; this runs on both the fresh and refresh paths.
**Removal set is exactly the 3 model keys (`ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL`)
+ the two retired knobs `MAX_THINKING_TOKENS` and `CLAUDE_CODE_MAX_OUTPUT_TOKENS`.
`modelOverrides` is FLAG-ONLY, never deleted — on Bedrock / Vertex / Foundry it is
the live model-alias → inference-profile routing map, which Scout does not write and
must not remove (auto-deleting it broke live model routing on an Enterprise-account
machine, 2026-09-10). Auth, gateway, and OTEL keys are likewise NEVER touched; Scout
never writes a model value.** The shipped helper retains the established exact
removal set and treats every other field as out of scope. Idempotent, safe-fail.

The `.zshrc` surface is handled separately by the dispatching prompt's managed-block refresh (`zshrc-block.md` sweeps these keys as out-of-block stragglers). This fragment covers the two `~/.claude` JSON files, VS Code's settings, and launchctl.

**a — `~/.claude/settings.json` and `~/.claude/settings.local.json` (shared user-owned JSON, bounded exact-key removal):**

Resolve `${CLAUDE_PLUGIN_ROOT}` to the absolute active Scout plugin directory
and substitute it for `[PLUGIN_ROOT]`. Run the shipped helper with each settings
path explicit:

```bash
SETTINGS_HELPER="[PLUGIN_ROOT]/scripts/setup-settings.py"
PYTHON_EXE=$(type -P python3 2>/dev/null || true)
if [ -z "$PYTHON_EXE" ] || [ ! -f "$SETTINGS_HELPER" ]; then
  echo "SETTINGS_HELPER_UNAVAILABLE"
else
for USER_SETTINGS in "$HOME/.claude/settings.json" "$HOME/.claude/settings.local.json"; do
  "$PYTHON_EXE" -B "$SETTINGS_HELPER" json-pins --settings "$USER_SETTINGS"
done
fi
```

**b — VS Code `claudeCode.environmentVariables` (JSONC, comment-preserving bounded edit):**

VS Code's user settings is JSONC — it may contain strings with comment-like
text, comments, and trailing commas. The helper parses it with a string-aware
bounded JSONC parser, targets only the top-level
`claudeCode.environmentVariables` array, deletes only exact model-key entry and
adjacent-comma spans, then reparses and compares the full semantic value to the
expected deletion. Unsupported or ambiguous documents remain byte-identical.

```bash
SETTINGS_HELPER="[PLUGIN_ROOT]/scripts/setup-settings.py"
PYTHON_EXE=$(type -P python3 2>/dev/null || true)
if [ -z "$PYTHON_EXE" ] || [ ! -f "$SETTINGS_HELPER" ]; then
  echo "SETTINGS_HELPER_UNAVAILABLE"
else
  "$PYTHON_EXE" -B "$SETTINGS_HELPER" vscode-pins \
    --settings "$HOME/Library/Application Support/Code/User/settings.json"
fi
```

**c — launchctl GUI env (best-effort detect + unset):**

```bash
LC_HIT=0
for K in ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL ANTHROPIC_DEFAULT_HAIKU_MODEL; do
  if [ -n "$(launchctl getenv $K 2>/dev/null)" ]; then
    launchctl unsetenv $K 2>/dev/null && LC_HIT=1
  fi
done
[ "$LC_HIT" = "1" ] && echo "LAUNCHCTL_PINS_CLEARED" || echo "LAUNCHCTL_PINS_NONE"
```

Surface inline (compose one combined note; silent only if every surface was already clean):
- All clean (`PINS_NONE`/`PINS_ABSENT` for both JSON files, with NO `FLAGS[...]`, + `VSCODE_PINS_NONE`/`VSCODE_ABSENT` + `LAUNCHCTL_PINS_NONE`) — silent.
- Any `FLAGS[modelOverrides]` (on a `PINS_NONE` or `PINS_REMOVED` result) — add a line: "Spotted a `modelOverrides` block in your Claude settings — left it UNTOUCHED. On Bedrock/Vertex/Foundry that's your live model-routing map, which Scout doesn't manage; noting it only so you know it's there."
- Any `PINS_REMOVED[...]` and/or `VSCODE_PINS_REMOVED` and/or `LAUNCHCTL_PINS_CLEARED` — "Cleared stale model pins so your `/model` picker shows the full list (including Opus 4.8): [list the surfaces that changed in plain words — e.g. 'Claude settings, VS Code settings']. Scout also removed the leftover output-length setting it used to write — Claude Code's own default applies now. **Restart Claude Code** (and if VS Code changed, fully quit it with Cmd+Q and relaunch) to pick up."
- `VSCODE_UNPARSEABLE` / `VSCODE_UNSUPPORTED_TARGET` / `VSCODE_SEMANTIC_MISMATCH` / `VSCODE_UNSAFE_FILE` / `VSCODE_BACKUP_FAILED` / `VSCODE_WRITE_FAILED` — "Couldn't safely auto-edit VS Code's settings (`~/Library/Application Support/Code/User/settings.json`) — left it untouched. Remove the three `ANTHROPIC_DEFAULT_*_MODEL` entries from the `claudeCode.environmentVariables` array by hand, then fully quit VS Code (Cmd+Q) and relaunch."
- `VSCODE_POST_WRITE_FAILED` — replacement completed but read-back verification failed; do not claim the settings file is unchanged. The exact pre-edit recovery copy remains at `settings.json.scout-bak`; inspect or restore it before retrying.
- `PINS_PARSE_ERROR` / `PINS_UNSAFE_FILE` / `PINS_BACKUP_FAILED` / `PINS_WRITE_FAILED` — one-line note naming the affected Claude settings file; leave it untouched and proceed.
- `PINS_POST_WRITE_FAILED` — replacement completed but read-back verification failed; do not claim the named file is unchanged. Its exact pre-edit recovery copy remains beside it with suffix `.scout-bak-modelpins`.
- `SETTINGS_HELPER_UNAVAILABLE` — one-line note that the shipped cleanup helper could not be run; leave the helper's JSON/JSONC files untouched and proceed. The independent launchctl check remains unchanged.
- Any other error variant — one-line note, proceed.

## Done

Return to the dispatching prompt (fresh-install or refresh). This fragment writes only to the two `~/.claude` settings JSON files, VS Code's user settings, and launchctl GUI env — it never changes Scout's own state. Pass any `PINS_REMOVED[...]` / `VSCODE_PINS_REMOVED` / `LAUNCHCTL_PINS_CLEARED` / VS-Code-restore-or-warn result back so the caller's done message carries the restart (and possible manual VS Code edit) note.
