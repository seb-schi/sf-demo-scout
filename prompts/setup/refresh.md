# Scout Setup — Refresh

Workspace already configured. Update CLIs, sync skills, refresh `.zshrc` block, bump config version.

**Idempotency contract:** every step below is idempotent and self-detecting. Re-running after an abort (e.g. SE returning from `/mcp` Slack auth) is safe and fast — completed steps fast-no-op via their own probes (`SLACK_MCP_ALREADY_REGISTERED`, `ZSHRC_UNCHANGED`, etc.). Always run end-to-end; do NOT skip steps trying to "resume" — the no-ops are the resume mechanism. Within the same CC session you may rely on conversation memory to fast-forward; across sessions, just run the full sequence — it will land in the right place naturally.

## a: Update Salesforce CLI (only if behind latest)

Reinstall the global `sf` CLI ONLY when the installed version is behind the
latest published version. An unconditional `npm install --global` on every
refresh churns the global binary needlessly and can orphan the keychain-backed
org-auth token across a node rebuild — the SE then sees an empty/stale org list
and assumes their connections were lost (the auth files in `~/.sfdx` are never
actually deleted). Version-gating makes the common no-op case a true no-op.

```bash
echo "CHECKING_SF_CLI"
SF_LATEST=$(npm view @salesforce/cli version 2>/dev/null)
SF_CURRENT=$(sf --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [ -z "$SF_LATEST" ]; then
  echo "SF_CLI_VERSION_CHECK_FAILED (offline?) — skipping update, current: ${SF_CURRENT:-unknown}"
elif [ "$SF_CURRENT" != "$SF_LATEST" ]; then
  echo "UPDATING_SF_CLI ($SF_CURRENT -> $SF_LATEST)"
  npm install @salesforce/cli --global 2>&1 | tail -1
  echo "SF_CLI_AT $(sf --version | head -1)"
else
  echo "SF_CLI_CURRENT ($SF_CURRENT)"
fi
```

## b: Update Claude Code CLI (only if behind latest)

Same version-gate rationale as step a — reinstall only when behind latest.

```bash
echo "CHECKING_CLAUDE_CLI"
CC_LATEST=$(npm view @anthropic-ai/claude-code version 2>/dev/null)
CC_CURRENT=$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [ -z "$CC_LATEST" ]; then
  echo "CLAUDE_CLI_VERSION_CHECK_FAILED (offline?) — skipping update, current: ${CC_CURRENT:-unknown}"
elif [ "$CC_CURRENT" != "$CC_LATEST" ]; then
  echo "UPDATING_CLAUDE_CLI ($CC_CURRENT -> $CC_LATEST)"
  npm install @anthropic-ai/claude-code --global 2>&1 | tail -1
  echo "CLAUDE_CLI_AT $(claude --version 2>/dev/null || echo 'unknown')"
else
  echo "CLAUDE_CLI_CURRENT ($CC_CURRENT)"
fi
```

Surface inline:
- `SF_CLI_CURRENT` / `CLAUDE_CLI_CURRENT` — silent (already latest; the common case).
- `UPDATING_SF_CLI` / `UPDATING_CLAUDE_CLI` followed by a clean install — one-line note that the CLI was updated.
- `SF_CLI_VERSION_CHECK_FAILED` / `CLAUDE_CLI_VERSION_CHECK_FAILED` — one-line note ("couldn't reach npm to check [sf|claude] CLI version — kept the installed one"), proceed.
- If an `npm install` that DID run fails (non-zero exit), surface a one-line note ("[sf|claude] CLI update failed — continuing") and proceed. Don't abort.

## c: Slack MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/slack-mcp.md` and execute it with `mode=soft`. The prompt handles registration heal + auth probe; in soft mode failures surface notes and continue (heal-when-broken semantics). The `SLACK_MCP_REGISTERED` branch still returns (TUI snapshot needs `/reload-plugins`).

## c.5: Google Workspace MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/google-mcp.md` and execute it with `mode=soft`. Heals the registration if the binary is present; surfaces a note and returns if the `mcp-adaptor` binary is absent or auth is pending. Never aborts.

## d: Refresh .zshrc managed block

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/zshrc-block.md` and execute it. Capture the result (`ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED`, plus optional `ANTHROPIC_MODEL_PRESENT`) — the orchestrator's done step needs it.

## d.6: Mirror quality-knob env vars to settings.json

Write Scout's two CC-native quality knobs — `MAX_THINKING_TOKENS=8192` and `CLAUDE_CODE_MAX_OUTPUT_TOKENS=16384` — into `~/.claude/settings.json` `env`. These also live in the `.zshrc` managed block, but `.zshrc` is not read by the VS Code extension (GUI launches skip interactive shell rc files), so settings.json is the launch-path-independent home. Authoritative overwrite (these are Scout-owned, CC-native, and version-independent — unlike model-profile vars, there's no CLI-version trap). Surgical: only the two keys, never auth/gateway/OTEL keys. Idempotent, safe-fail.

```bash
USER_SETTINGS="$HOME/.claude/settings.json"

python3 - "$USER_SETTINGS" <<'PYEOF'
import json, os, sys, tempfile
path = sys.argv[1]
KNOBS = {
    "MAX_THINKING_TOKENS": "8192",
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "16384",
}

if not os.path.exists(path):
    data = {}
else:
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"ENV_PARSE_ERROR: {e}"); sys.exit(0)

if not isinstance(data, dict):
    print("ENV_NOT_OBJECT"); sys.exit(0)

env = data.get("env")
if not isinstance(env, dict):
    env = {}
    data["env"] = env

changed = [k for k, v in KNOBS.items() if env.get(k) != v]
if not changed:
    print("ENV_KNOBS_CURRENT"); sys.exit(0)
for k in changed:
    env[k] = KNOBS[k]

tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=".settings.", suffix=".tmp")
try:
    with os.fdopen(tmp_fd, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.rename(tmp_path, path)
except Exception as e:
    try: os.unlink(tmp_path)
    except OSError: pass
    print(f"ENV_WRITE_FAILED: {e}"); sys.exit(0)

print("ENV_KNOBS_SET: " + ",".join(changed))
PYEOF
```

Surface inline:
- `ENV_KNOBS_CURRENT` — silent.
- `ENV_KNOBS_SET: <keys>` — "Wrote Scout quality settings (thinking + output budgets) to `~/.claude/settings.json` — now active in both terminal and VS Code. Restart CC to pick up."
- Any error variant — one-line note, proceed.

## d.7: Strip stale model pins across all surfaces (self-heal)

Older Scout/aisuite installs hard-pinned three model env vars (`ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL`) and/or a `modelOverrides` block across several config surfaces. Claude Code collapses the `/model` picker to those pins, hiding newer models (e.g. Opus 4.8). Scout no longer writes any of them (since 2026-06-02), so on existing installs they're pure stale state. This step REMOVES them from every surface so the SE gets the full model list in both terminal and VS Code — it never writes a model value (Scout is out of model selection; the `/scout-sparring` and `/scout-building` gate is the only nudge, and the SE picks via `/model`). **Removal set is exactly the 3 model keys + `modelOverrides`. Token-window knobs (`MAX_THINKING_TOKENS`, `CLAUDE_CODE_MAX_OUTPUT_TOKENS`), auth, gateway, and OTEL keys are NEVER touched.** Idempotent, safe-fail.

The `.zshrc` surface is handled in step d (the managed-block refresh now sweeps these three keys as out-of-block stragglers — see `zshrc-block.md`). This step covers the two `~/.claude` JSON files, VS Code's settings, and launchctl.

**d.7a — `~/.claude/settings.json` and `~/.claude/settings.local.json` (Scout-owned JSON, auto-remove):**

```bash
for USER_SETTINGS in "$HOME/.claude/settings.json" "$HOME/.claude/settings.local.json"; do
python3 - "$USER_SETTINGS" <<'PYEOF'
import json, os, sys, tempfile
path = sys.argv[1]
PIN_KEYS = [
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
]
label = os.path.basename(path)

if not os.path.exists(path):
    print(f"PINS_ABSENT[{label}]"); sys.exit(0)
try:
    with open(path) as f:
        data = json.load(f)
except (json.JSONDecodeError, OSError) as e:
    print(f"PINS_PARSE_ERROR[{label}]: {e}"); sys.exit(0)

if not isinstance(data, dict):
    print(f"PINS_NOT_OBJECT[{label}]"); sys.exit(0)

removed = []
env = data.get("env")
if isinstance(env, dict):
    for k in PIN_KEYS:
        if k in env:
            del env[k]
            removed.append(k)
if "modelOverrides" in data:
    del data["modelOverrides"]
    removed.append("modelOverrides")

if not removed:
    print(f"PINS_NONE[{label}]"); sys.exit(0)

tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=".settings.", suffix=".tmp")
try:
    with os.fdopen(tmp_fd, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.rename(tmp_path, path)
except Exception as e:
    try: os.unlink(tmp_path)
    except OSError: pass
    print(f"PINS_WRITE_FAILED[{label}]: {e}"); sys.exit(0)

print(f"PINS_REMOVED[{label}]: " + ",".join(removed))
PYEOF
done
```

**d.7b — VS Code `claudeCode.environmentVariables` (JSONC, comment-preserving auto-edit with backup/validate/restore):**

VS Code's user settings is JSONC — it may contain `//` comments and trailing commas, and it's the SE's hand-curated personal config. Strategy: back it up, surgically delete just the three `ANTHROPIC_DEFAULT_*_MODEL` array entries via line-oriented editing that preserves comments, then validate the result still parses (comments/trailing-commas stripped for the parse check only). On ANY anomaly — parse failure after edit, unexpected structure — restore the backup and fall back to the warn message. The token-knob entries and every other entry are preserved.

```bash
python3 - "$HOME/Library/Application Support/Code/User/settings.json" <<'PYEOF'
import os, sys, re, shutil

path = sys.argv[1]
if not os.path.exists(path):
    print("VSCODE_ABSENT"); sys.exit(0)

try:
    with open(path) as f:
        src = f.read()
except OSError as e:
    print(f"VSCODE_READ_ERROR: {e}"); sys.exit(0)

PINS = ("ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL")

if not any(p in src for p in PINS):
    print("VSCODE_PINS_NONE"); sys.exit(0)

# --- helper: strip JSONC comments + trailing commas for a parse-only check
def jsonc_loads(text):
    import json
    # remove /* */ block comments
    t = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    # remove // line comments (not inside strings — best-effort: only at line starts or after whitespace/commas)
    t = re.sub(r"(^|[\s,{\[])//[^\n]*", r"\1", t)
    # remove trailing commas before } or ]
    t = re.sub(r",(\s*[}\]])", r"\1", t)
    return json.loads(t)

# Validate the file parses BEFORE we touch it; if it doesn't, don't risk an edit.
try:
    before = jsonc_loads(src)
except Exception as e:
    print(f"VSCODE_UNPARSEABLE_PREEDIT: {e}"); sys.exit(0)

# Backup
bak = path + ".scout-bak"
try:
    shutil.copy2(path, bak)
except OSError as e:
    print(f"VSCODE_BACKUP_FAILED: {e}"); sys.exit(0)

# Surgical removal: the entries are objects of the shape
#   { "name": "ANTHROPIC_DEFAULT_*_MODEL", "value": "..." }
# possibly spanning multiple lines, each followed by an optional comma.
# Remove each such object literal wherever it appears in the array.
out = src
for pin in PINS:
    # match an object literal containing "name": "<pin>" with its trailing comma (or leading comma)
    pattern = re.compile(
        r"\{\s*\"name\"\s*:\s*\"" + re.escape(pin) + r"\"\s*,\s*\"value\"\s*:\s*\"[^\"]*\"\s*\}\s*,?\s*\n?",
        re.S,
    )
    out = pattern.sub("", out)
    # also handle value-before-name ordering
    pattern2 = re.compile(
        r"\{\s*\"value\"\s*:\s*\"[^\"]*\"\s*,\s*\"name\"\s*:\s*\"" + re.escape(pin) + r"\"\s*\}\s*,?\s*\n?",
        re.S,
    )
    out = pattern2.sub("", out)

# Fix any dangling comma left before a closing bracket of the array
out = re.sub(r",(\s*\])", r"\1", out)

# Validate post-edit
try:
    after = jsonc_loads(out)
except Exception as e:
    shutil.copy2(bak, path)
    print(f"VSCODE_VALIDATE_FAILED_RESTORED: {e}"); sys.exit(0)

# Sanity: the only difference should be the removed pins. Confirm no pin remains.
flat = str(after)
if any(p in flat for p in PINS):
    shutil.copy2(bak, path)
    print("VSCODE_PINS_SURVIVED_RESTORED"); sys.exit(0)

try:
    with open(path, "w") as f:
        f.write(out)
except OSError as e:
    shutil.copy2(bak, path)
    print(f"VSCODE_WRITE_FAILED_RESTORED: {e}"); sys.exit(0)

print("VSCODE_PINS_REMOVED")
PYEOF
```

**d.7c — launchctl GUI env (best-effort detect + unset):**

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
- All clean (`PINS_NONE`/`PINS_ABSENT` for both JSON files + `VSCODE_PINS_NONE`/`VSCODE_ABSENT` + `LAUNCHCTL_PINS_NONE`) — silent.
- Any `PINS_REMOVED[...]` and/or `VSCODE_PINS_REMOVED` and/or `LAUNCHCTL_PINS_CLEARED` — "Cleared stale model pins so your `/model` picker shows the full list (including Opus 4.8): [list the surfaces that changed in plain words — e.g. 'Claude settings, VS Code settings']. Your thinking/output token settings were kept. **Restart Claude Code** (and if VS Code changed, fully quit it with Cmd+Q and relaunch) to pick up."
- `VSCODE_VALIDATE_FAILED_RESTORED` / `VSCODE_PINS_SURVIVED_RESTORED` / `VSCODE_UNPARSEABLE_PREEDIT` / `VSCODE_BACKUP_FAILED` — "Couldn't safely auto-edit VS Code's settings (`~/Library/Application Support/Code/User/settings.json`) — left it untouched. Remove the three `ANTHROPIC_DEFAULT_*_MODEL` entries from the `claudeCode.environmentVariables` array by hand, then fully quit VS Code (Cmd+Q) and relaunch."
- Any other error variant — one-line note, proceed.

## Done

Refresh procedure complete. Return to the orchestrator. Pass the result of step d (`ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED`, plus optional `ANTHROPIC_MODEL_PRESENT`) so the done message can include the shell-refresh note. If d.7 emitted any `PINS_REMOVED[...]`, `VSCODE_PINS_REMOVED`, `LAUNCHCTL_PINS_CLEARED`, or a VS-Code-restore/warn variant, the SE has a restart (and possibly a manual VS Code edit) pending — make sure that note survived into the done summary.
