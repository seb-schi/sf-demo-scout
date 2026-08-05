# Setup — Model-Pin Strip (self-heal)

Read + executed by both `fresh-install.md` and `refresh.md`. Frees the `/model`
picker by removing stale model pins that various Salesforce tools (AI Suite,
DevBar, etc.) inject, sometimes erroneously — they collapse the picker so the SE
can't reach newer models. That residue is NOT written by Scout, so it lands on
Scout-FRESH machines too; this runs on both the fresh and refresh paths.
**Removal set is exactly the 3 model keys (`ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL`)
+ `modelOverrides` + the two retired knobs `MAX_THINKING_TOKENS` and
`CLAUDE_CODE_MAX_OUTPUT_TOKENS`. Auth, gateway, and OTEL keys are NEVER touched;
Scout never writes a model value.** The per-knob retirement rationale lives in the
`PIN_KEYS` comments below. Idempotent, safe-fail.

The `.zshrc` surface is handled separately by the dispatching prompt's managed-block refresh (`zshrc-block.md` sweeps these keys as out-of-block stragglers). This fragment covers the two `~/.claude` JSON files, VS Code's settings, and launchctl.

**a — `~/.claude/settings.json` and `~/.claude/settings.local.json` (Scout-owned JSON, auto-remove):**

```bash
for USER_SETTINGS in "$HOME/.claude/settings.json" "$HOME/.claude/settings.local.json"; do
python3 - "$USER_SETTINGS" <<'PYEOF'
import json, os, sys, tempfile
path = sys.argv[1]
PIN_KEYS = [
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    # Retired 2026-07-08: no-op on adaptive-thinking models (Sonnet 5 /
    # Opus 4.8), and a hard 400 landmine when a gateway routes an older CC
    # build to a newer model. Stripped here so existing installs self-heal;
    # Scout no longer writes it anywhere.
    "MAX_THINKING_TOKENS",
    # Retired 2026-07-27: Scout no longer sets an output-length knob. Probes
    # showed 16384 was NOT applied as a cap on sub-agent output (a sub-agent
    # emitted ~24k tokens and completed), so the truncation rationale it was
    # kept for did not hold. Removed rather than re-tuned: Scout should not
    # leave an un-sourced tuning value on an SE's machine. CC's own default
    # applies. Stripped here so existing installs self-heal.
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
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

**b — VS Code `claudeCode.environmentVariables` (JSONC, comment-preserving auto-edit with backup/validate/restore):**

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
- All clean (`PINS_NONE`/`PINS_ABSENT` for both JSON files + `VSCODE_PINS_NONE`/`VSCODE_ABSENT` + `LAUNCHCTL_PINS_NONE`) — silent.
- Any `PINS_REMOVED[...]` and/or `VSCODE_PINS_REMOVED` and/or `LAUNCHCTL_PINS_CLEARED` — "Cleared stale model pins so your `/model` picker shows the full list (including Opus 4.8): [list the surfaces that changed in plain words — e.g. 'Claude settings, VS Code settings']. Scout also removed the leftover output-length setting it used to write — Claude Code's own default applies now. **Restart Claude Code** (and if VS Code changed, fully quit it with Cmd+Q and relaunch) to pick up."
- `VSCODE_VALIDATE_FAILED_RESTORED` / `VSCODE_PINS_SURVIVED_RESTORED` / `VSCODE_UNPARSEABLE_PREEDIT` / `VSCODE_BACKUP_FAILED` — "Couldn't safely auto-edit VS Code's settings (`~/Library/Application Support/Code/User/settings.json`) — left it untouched. Remove the three `ANTHROPIC_DEFAULT_*_MODEL` entries from the `claudeCode.environmentVariables` array by hand, then fully quit VS Code (Cmd+Q) and relaunch."
- Any other error variant — one-line note, proceed.

## Done

Return to the dispatching prompt (fresh-install or refresh). This fragment writes only to the two `~/.claude` settings JSON files, VS Code's user settings, and launchctl GUI env — it never changes Scout's own state. Pass any `PINS_REMOVED[...]` / `VSCODE_PINS_REMOVED` / `LAUNCHCTL_PINS_CLEARED` / VS-Code-restore-or-warn result back so the caller's done message carries the restart (and possible manual VS Code edit) note.
