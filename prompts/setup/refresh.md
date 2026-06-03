# Scout Setup — Refresh

Workspace already configured. Update CLIs, sync skills, refresh `.zshrc` block, bump config version.

**Idempotency contract:** every step below is idempotent and self-detecting. Re-running after an abort (e.g. SE returning from `/mcp` Slack auth) is safe and fast — completed steps fast-no-op via their own probes (`SLACK_MCP_ALREADY_REGISTERED`, `ZSHRC_UNCHANGED`, etc.). Always run end-to-end; do NOT skip steps trying to "resume" — the no-ops are the resume mechanism. Within the same CC session you may rely on conversation memory to fast-forward; across sessions, just run the full sequence — it will land in the right place naturally.

## a: Update Salesforce CLI

```bash
echo "UPDATING_SF_CLI"
npm install @salesforce/cli --global 2>&1 | tail -1
echo "SF_CLI_AT $(sf --version | head -1)"
```

## b: Update Claude Code CLI

```bash
echo "UPDATING_CLAUDE_CLI"
npm install @anthropic-ai/claude-code --global 2>&1 | tail -1
echo "CLAUDE_CLI_AT $(claude --version 2>/dev/null || echo 'unknown')"
```

If either npm command fails (non-zero exit), surface a one-line note ("[sf|claude] CLI update failed — continuing") and proceed. Don't abort.

## c: Slack MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/slack-mcp.md` and execute it with `mode=soft`. The prompt handles registration heal + auth probe; in soft mode failures surface notes and continue (heal-when-broken semantics). The `SLACK_MCP_REGISTERED` branch still aborts (TUI snapshot needs `/reload-plugins`).

## d: Refresh .zshrc managed block

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/zshrc-block.md` and execute it. Capture the result (`ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED`, plus optional `ANTHROPIC_MODEL_PRESENT`) — the orchestrator's done step needs it.

## d.5: Pin Opus 1M context window

Set `~/.claude/settings.json` `model` to `opus[1m]` so Scout sessions land on the 1M-context Opus variant regardless of CC launch path (terminal vs VS Code GUI). `opus[1m]` is an alias — it resolves to whatever this SE's CC build calls "Opus," just with the 1M window — so it can never name a Bedrock version the CLI can't reach. Only upgrades when current value is the bare `opus` alias — preserves any deliberate SE override (`sonnet`, `haiku`, custom model ID). Idempotent, safe-fail.

```bash
USER_SETTINGS="$HOME/.claude/settings.json"

python3 - "$USER_SETTINGS" <<'PYEOF'
import json, os, sys, tempfile
path = sys.argv[1]

if not os.path.exists(path):
    data = {}
else:
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"MODEL_PARSE_ERROR: {e}"); sys.exit(0)

if not isinstance(data, dict):
    print("MODEL_NOT_OBJECT"); sys.exit(0)

current = data.get("model")
if current == "opus[1m]":
    print("MODEL_ALREADY_1M"); sys.exit(0)
if current is not None and current != "opus":
    print(f"MODEL_PRESERVED: {current}"); sys.exit(0)

data["model"] = "opus[1m]"

tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=".settings.", suffix=".tmp")
try:
    with os.fdopen(tmp_fd, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.rename(tmp_path, path)
except Exception as e:
    try: os.unlink(tmp_path)
    except OSError: pass
    print(f"MODEL_WRITE_FAILED: {e}"); sys.exit(0)

print("MODEL_UPGRADED" if current == "opus" else "MODEL_SET")
PYEOF
```

Surface inline:
- `MODEL_ALREADY_1M` — silent.
- `MODEL_UPGRADED` — "Upgraded `~/.claude/settings.json` model from `opus` to `opus[1m]` — Scout sessions now use the 1M-context window. Restart CC to pick up."
- `MODEL_SET` — "Set `~/.claude/settings.json` model to `opus[1m]` — Scout sessions use the 1M-context window. Restart CC to pick up."
- `MODEL_PRESERVED: <value>` — "Left existing `model: <value>` in `~/.claude/settings.json` untouched. Set to `opus[1m]` manually if you want the 1M-context window for Scout."
- Any error variant — one-line note, proceed.

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

## d.7: Strip stale model pins (self-heal old installs)

Older Scout/aisuite installs hard-pinned three model env vars and a `modelOverrides` block in `~/.claude/settings.json`. Claude Code collapses the `/model` picker to those pins, hiding newer models (e.g. Opus 4.8). Scout no longer writes these (since 2026-06-02), so on existing installs they're pure stale state. This step REMOVES them — it never writes a model value (d.5's `opus[1m]` alias is the only model Scout sets). Surgical: only the three `ANTHROPIC_DEFAULT_*_MODEL` keys and top-level `modelOverrides`; never auth/gateway/OTEL/quality keys. Idempotent, safe-fail.

```bash
USER_SETTINGS="$HOME/.claude/settings.json"

python3 - "$USER_SETTINGS" <<'PYEOF'
import json, os, sys, tempfile
path = sys.argv[1]
PIN_KEYS = [
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
]

if not os.path.exists(path):
    print("PINS_NO_SETTINGS"); sys.exit(0)
try:
    with open(path) as f:
        data = json.load(f)
except (json.JSONDecodeError, OSError) as e:
    print(f"PINS_PARSE_ERROR: {e}"); sys.exit(0)

if not isinstance(data, dict):
    print("PINS_NOT_OBJECT"); sys.exit(0)

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
    print("PINS_NONE"); sys.exit(0)

tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=".settings.", suffix=".tmp")
try:
    with os.fdopen(tmp_fd, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.rename(tmp_path, path)
except Exception as e:
    try: os.unlink(tmp_path)
    except OSError: pass
    print(f"PINS_WRITE_FAILED: {e}"); sys.exit(0)

print("PINS_REMOVED: " + ",".join(removed))
PYEOF
```

Then check VS Code's own settings (a separate surface Scout must NOT auto-edit — it's JSONC with SE-authored comments). Detect-and-warn only:

```bash
VSC="$HOME/Library/Application Support/Code/User/settings.json"
if [ -f "$VSC" ] && grep -q 'ANTHROPIC_DEFAULT_[A-Z]*_MODEL' "$VSC"; then
  echo "VSCODE_PINS_PRESENT"
else
  echo "VSCODE_PINS_ABSENT"
fi
```

Surface inline:
- `PINS_NONE` + `VSCODE_PINS_ABSENT` — silent (nothing stale).
- `PINS_REMOVED: <keys>` — "Removed stale model pins from `~/.claude/settings.json` (`<keys>`) — your `/model` picker now shows the full model list including Opus 4.8. Restart CC to pick up."
- `VSCODE_PINS_PRESENT` — "Heads up: VS Code's own settings (`~/Library/Application Support/Code/User/settings.json`) still pin the model env vars under `claudeCode.environmentVariables`, which keeps the VS Code picker locked. Scout won't auto-edit that file (it's hand-curated). Remove the three `ANTHROPIC_DEFAULT_*_MODEL` entries from the `claudeCode.environmentVariables` array, then fully quit VS Code (Cmd+Q, not just close the window) and relaunch."
- Any error variant — one-line note, proceed.

## Done

Refresh procedure complete. Return to the orchestrator. Pass the result of step d (`ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED`, plus optional `ANTHROPIC_MODEL_PRESENT`) so the done message can include the shell-refresh note. If d.7 emitted `PINS_REMOVED` or `VSCODE_PINS_PRESENT`, the SE has a restart/manual-edit action pending — make sure that note survived into the done summary.
