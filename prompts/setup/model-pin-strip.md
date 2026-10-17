# Setup — Preserve Model Routing, Clean Retired Scout Settings

Read by `fresh-install.md` and `refresh.md`. Scout does not own model selection.
Preserve `ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL`,
`ANTHROPIC_DEFAULT_HAIKU_MODEL`, `ANTHROPIC_MODEL`, `modelOverrides`, and all
provider/auth/gateway/OTEL settings. Their presence or an older-looking value
is not evidence of stale configuration. Never replace them with guessed 5.5 IDs.

Only two cleanups mutate: the JSON cleanup of Scout's retired
`MAX_THINKING_TOKENS` and `CLAUDE_CODE_MAX_OUTPUT_TOKENS` settings, and the
removal of Scout's retired Salesforce DX allow rule. The legacy helper
operation names below are retained for caller compatibility. VS Code and
launchctl model checks are read-only. Shell refresh preserves outside model
mappings. Within its marked block it retires only literal historical Scout
exports; unknown non-comment content preserves the whole file for review.

## Claude settings

Resolve the active plugin root to `[PLUGIN_ROOT]`, then run:

```bash
/bin/bash <<'SCOUT_JSON_PINS_BASH'
SETTINGS_HELPER="[PLUGIN_ROOT]/scripts/setup-settings.py"
PYTHON_EXE=$(/usr/bin/which python3 2>/dev/null || true)
case "$PYTHON_EXE" in ""|/*) ;; *) PYTHON_EXE="$PWD/$PYTHON_EXE" ;; esac
if [ -z "$PYTHON_EXE" ] || [ ! -f "$SETTINGS_HELPER" ]; then
  echo "SETTINGS_HELPER_UNAVAILABLE"
else
for USER_SETTINGS in "$HOME/.claude/settings.json" "$HOME/.claude/settings.local.json"; do
  "$PYTHON_EXE" -B "$SETTINGS_HELPER" json-pins --settings "$USER_SETTINGS"
done
fi
SCOUT_JSON_PINS_BASH
```

## Retired Salesforce DX allow rule

Scout no longer ships its own Salesforce DX MCP server: Salesforce ends support
for `@salesforce/mcp` on 2026-11-02. Remove only the allow rules Scout wrote for
it, from the workspace and user settings:

```bash
/bin/bash <<'SCOUT_RETIRED_ALLOW_BASH'
SETTINGS_HELPER="[PLUGIN_ROOT]/scripts/setup-settings.py"
PYTHON_EXE=$(/usr/bin/which python3 2>/dev/null || true)
case "$PYTHON_EXE" in ""|/*) ;; *) PYTHON_EXE="$PWD/$PYTHON_EXE" ;; esac
if [ -z "$PYTHON_EXE" ] || [ ! -f "$SETTINGS_HELPER" ]; then
  echo "SETTINGS_HELPER_UNAVAILABLE"
else
WS_SETTINGS="${SCOUT_WORKSPACE:-$HOME/claude-projects/sf-demo-scout}/.claude/settings.json"
for SETTINGS in "$WS_SETTINGS" "$HOME/.claude/settings.json"; do
  "$PYTHON_EXE" -B "$SETTINGS_HELPER" retired-allow --settings "$SETTINGS"
done
fi
SCOUT_RETIRED_ALLOW_BASH
```

## VS Code mappings

Inspect only the top-level `claudeCode.environmentVariables` array. Preserve
its bytes, comments, repeated entries, modes and any existing recovery backup.
Unsupported or malformed JSONC remains unchanged; never suggest deleting model
mappings merely because the inspector cannot parse the file.

```bash
/bin/bash <<'SCOUT_VSCODE_PINS_BASH'
SETTINGS_HELPER="[PLUGIN_ROOT]/scripts/setup-settings.py"
PYTHON_EXE=$(/usr/bin/which python3 2>/dev/null || true)
case "$PYTHON_EXE" in ""|/*) ;; *) PYTHON_EXE="$PWD/$PYTHON_EXE" ;; esac
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

On Claude only, run the read-only report after the cleanup checks:

```bash
SCOUT_HOST=claude python3 -B "[PLUGIN_ROOT]/scripts/setup-model-report.py"
```

It inspects user/project/local settings, the managed settings file, the session
environment, literal `.zshrc` assignments, VS Code and read-only launchctl values.
It never sources shell files or changes a model setting. Managed policy supplied
through MDM/server/embedding APIs may not be visible in the local file; the report
does not certify effective routing or account access. Carry each reported older
model's source and provider-specific fix verbatim; do not invent model IDs or
add an update-prompt recommendation. Unknown/deployment-name values are unassessed.

Return all helper tokens to the caller. Use the report as the model-routing note;
also describe any actual cleanup or limitation:

- `FLAGS[...]` containing `modelMappings` or `modelOverrides`,
  `VSCODE_PINS_PRESERVED`, or `LAUNCHCTL_PINS_PRESERVED`: provider/user model
  routing is present and preserved. The report separately assesses recognized
  values and documented alias defaults; it does not verify the effective model.
- `PINS_REMOVED[...]`: only retired Scout tuning settings were removed. Explain
  which settings surface changed; a new Claude session picks up the change.
- `PINS_POST_WRITE_FAILED`: replacement happened but read-back failed. Keep the
  `.scout-bak-modelpins` recovery copy and do not claim the file is unchanged.
- `RETIRED_ALLOW_SET[...]`: one line saying Scout removed its retired Salesforce
  DX permission rule and changed nothing else; no restart is needed, because
  Scout no longer starts that server. `RETIRED_ALLOW_NONE[...]` and
  `RETIRED_ALLOW_ABSENT[...]` are silent. `RETIRED_ALLOW_POST_WRITE_FAILED[...]`:
  the write landed but its read-back failed; give its detail as printed (original
  restored, or left as found) with the backup's name, and don't call the file
  unchanged. Any other `RETIRED_ALLOW_` result: one line saying that file was left
  as it was.
- Parse, unsafe-path, backup, write, or helper-unavailable results: report the
  actual limitation; do not invent a cleanup success or manually remove mappings.
- All absent/none with no flags: use only the report's single summary line.

This is setup compatibility, not an inference test or permission to change a
managed model policy. A host refusing a model is not a reason to try a new route.
