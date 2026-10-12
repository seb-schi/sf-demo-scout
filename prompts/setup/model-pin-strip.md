# Setup — Preserve Model Routing, Clean Retired Scout Settings

Read by `fresh-install.md` and `refresh.md`. Scout does not own model selection.
Preserve `ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL`,
`ANTHROPIC_DEFAULT_HAIKU_MODEL`, `ANTHROPIC_MODEL`, `modelOverrides`, and all
provider/auth/gateway/OTEL settings. Their presence or an older-looking value
is not evidence of stale configuration. Never replace them with guessed 5.5 IDs.

Only the existing JSON cleanup of Scout's retired `MAX_THINKING_TOKENS` and
`CLAUDE_CODE_MAX_OUTPUT_TOKENS` settings remains mutating. The legacy helper
operation names below are retained for caller compatibility. VS Code and
launchctl model checks are read-only. Shell refresh preserves outside model
mappings. Within its marked block it retires only literal historical Scout
exports; unknown non-comment content preserves the whole file for review.

## Claude settings

Resolve the active plugin root to `[PLUGIN_ROOT]`, then run:

```bash
/bin/bash <<'SCOUT_JSON_PINS_BASH'
SETTINGS_HELPER="[PLUGIN_ROOT]/scripts/setup-settings.py"
PYTHON_EXE=$(type -P python3 2>/dev/null || true)
if [ -z "$PYTHON_EXE" ] || [ ! -f "$SETTINGS_HELPER" ]; then
  echo "SETTINGS_HELPER_UNAVAILABLE"
else
for USER_SETTINGS in "$HOME/.claude/settings.json" "$HOME/.claude/settings.local.json"; do
  "$PYTHON_EXE" -B "$SETTINGS_HELPER" json-pins --settings "$USER_SETTINGS"
done
fi
SCOUT_JSON_PINS_BASH
```

## VS Code mappings

Inspect only the top-level `claudeCode.environmentVariables` array. Preserve
its bytes, comments, repeated entries, modes and any existing recovery backup.
Unsupported or malformed JSONC remains unchanged; never suggest deleting model
mappings merely because the inspector cannot parse the file.

```bash
/bin/bash <<'SCOUT_VSCODE_PINS_BASH'
SETTINGS_HELPER="[PLUGIN_ROOT]/scripts/setup-settings.py"
PYTHON_EXE=$(type -P python3 2>/dev/null || true)
if [ -z "$PYTHON_EXE" ] || [ ! -f "$SETTINGS_HELPER" ]; then
  echo "SETTINGS_HELPER_UNAVAILABLE"
else
  "$PYTHON_EXE" -B "$SETTINGS_HELPER" vscode-pins \
    --settings "$HOME/Library/Application Support/Code/User/settings.json"
fi
SCOUT_VSCODE_PINS_BASH
```

## launchctl mappings

Detect without printing values or changing the GUI environment:

```bash
LC_HIT=0
for K in ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL ANTHROPIC_DEFAULT_HAIKU_MODEL; do
  if [ -n "$(launchctl getenv "$K" 2>/dev/null)" ]; then LC_HIT=1; fi
done
[ "$LC_HIT" = "1" ] && echo "LAUNCHCTL_PINS_PRESERVED" || echo "LAUNCHCTL_PINS_NONE"
```

## Result

Return all helper tokens to the caller and compose at most one concise note:

- `FLAGS[...]` containing `modelMappings` or `modelOverrides`,
  `VSCODE_PINS_PRESERVED`, or `LAUNCHCTL_PINS_PRESERVED`: provider/user model
  routing is present and preserved. Do not claim which model an alias resolves
  to. Confirm the effective model in the actual host when testing it.
- `PINS_REMOVED[...]`: only retired Scout tuning settings were removed. Explain
  which settings surface changed; a new Claude session picks up the change.
- `PINS_POST_WRITE_FAILED`: replacement happened but read-back failed. Keep the
  `.scout-bak-modelpins` recovery copy and do not claim the file is unchanged.
- Parse, unsafe-path, backup, write, or helper-unavailable results: report the
  actual limitation; do not invent a cleanup success or manually remove mappings.
- All absent/none with no flags: no model-routing note is needed.

This is setup compatibility, not an inference test or permission to change a
managed model policy. A host refusing a model is not a reason to try a new route.
