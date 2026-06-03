# Scout Setup — Fresh Install

End-to-end install procedure. Run on `STATE=FRESH` or after a `STATE=COLLISION` scrub.

**Idempotency contract:** every step below is idempotent and self-detecting. Re-running after an abort (e.g. SE returning from `/mcp` Slack auth) is safe and fast — completed steps fast-no-op via their own probes (`BREW_OK`, `NODE_PRESENT`, `SETTINGS_PRESENT`, `USER_SETTINGS_NO_CHANGES`, `AUTOUPDATE_ALREADY_ON`, `SLACK_MCP_ALREADY_REGISTERED`, etc.). Always run end-to-end; do NOT skip steps trying to "resume" — the no-ops are the resume mechanism. Within the same CC session you may rely on conversation memory to fast-forward; across sessions, just run the full sequence — it will land in the right place naturally.

## a: Brew Check (hard abort if missing)

```bash
command -v brew >/dev/null 2>&1 && echo "BREW_OK" || echo "BREW_MISSING"
```

If `BREW_MISSING`, ABORT and emit:

> "Scout setup needs Homebrew installed first. Brew install requires interactive sudo so it can't run inside Claude Code.
>
> Open a terminal and run:
>
> ```
> /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
> ```
>
> Then re-run `/scout-setup`."

## b: Auto-install Node, Python, sf CLI

Each tool: check first, install only if missing.

```bash
if ! command -v node >/dev/null 2>&1; then
  echo "INSTALLING_NODE"
  brew install node 2>&1 | tail -1
  echo "NODE_DONE"
else
  echo "NODE_PRESENT ($(node --version))"
fi
```

```bash
if command -v python3 >/dev/null 2>&1; then
  PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
  if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 9 ]; then
    echo "PYTHON_PRESENT ($PY_VERSION)"
  else
    echo "INSTALLING_PYTHON (current: $PY_VERSION, need 3.9+)"
    brew install python@3.13 2>&1 | tail -1
    echo "PYTHON_DONE"
  fi
else
  echo "INSTALLING_PYTHON (none found)"
  brew install python@3.13 2>&1 | tail -1
  echo "PYTHON_DONE"
fi
```

```bash
if ! command -v sf >/dev/null 2>&1; then
  echo "INSTALLING_SF_CLI"
  npm install @salesforce/cli --global 2>&1 | tail -1
  echo "SF_CLI_DONE"
else
  echo "SF_CLI_PRESENT ($(sf --version | head -1))"
fi
```

If any install fails, ABORT and emit:

> "Scout couldn't auto-install [tool name]. Last line from install command:
>
> ```
> [last line]
> ```
>
> Open a terminal and run the install manually, then re-run `/scout-setup`."

## c: Pre-cache Salesforce MCP server

```bash
echo "PRE_CACHING_MCP"
npx -y @salesforce/mcp --help >/dev/null 2>&1 && echo "MCP_CACHED" || echo "MCP_CACHE_FAILED"
```

On `MCP_CACHE_FAILED`, surface a one-line note ("MCP pre-cache failed — first MCP call may be slow") and proceed.

## d: Workspace Directory + SFDX Scaffold

```bash
mkdir -p "$HOME/claude-projects/sf-demo-scout/orgs"
cd "$HOME/claude-projects/sf-demo-scout"
if [ ! -f sfdx-project.json ]; then
  sf project generate --name sf-demo-scout --template empty >/dev/null 2>&1 || true
  if [ -f sf-demo-scout/sfdx-project.json ]; then
    mv sf-demo-scout/sfdx-project.json ./
    mv sf-demo-scout/force-app ./ 2>/dev/null || true
    rm -rf sf-demo-scout
  fi
  echo "SFDX_INITIALISED"
else
  echo "SFDX_PRESENT"
fi
```

## e: Starter Lessons Files

```bash
cd "$HOME/claude-projects/sf-demo-scout"
if [ ! -f orgs/sparring-lessons.md ]; then
  cat > orgs/sparring-lessons.md <<'EOF'
# Sparring Lessons

Accumulated lessons from scout-sparring sessions. Add new lessons at the end with today's date.
EOF
fi
if [ ! -f orgs/building-lessons.md ]; then
  cat > orgs/building-lessons.md <<'EOF'
# Building Lessons

Accumulated lessons from scout-building sessions. Add new lessons at the end with today's date.
EOF
fi
```

## f: Workspace `.claude/settings.json`

Resolve `${CLAUDE_PLUGIN_ROOT}` to its absolute filesystem path (the directory `plugin.json` lives in, minus `/.claude-plugin`) and substitute as `[PLUGIN_ROOT]` below — `${CLAUDE_PLUGIN_ROOT}` does NOT expand inside Bash shell context, only inside Read-tool path arguments, so the bash invocation must receive the literal absolute path.

```bash
SETTINGS="$HOME/claude-projects/sf-demo-scout/.claude/settings.json"
TEMPLATE="[PLUGIN_ROOT]/assets/workspace-settings.template.json"
mkdir -p "$(dirname "$SETTINGS")"
if [ ! -f "$SETTINGS" ]; then
  cp "$TEMPLATE" "$SETTINGS"
  echo "SETTINGS_WRITTEN"
else
  echo "SETTINGS_PRESENT"
fi
```

## g: User-scope permissions merge

Merge the 6 fixed Scout entries into `~/.claude/settings.json` `permissions.allow` so MCP calls don't prompt when CC is launched outside the workspace. Idempotent, safe-fail.

```bash
USER_SETTINGS="$HOME/.claude/settings.json"
mkdir -p "$(dirname "$USER_SETTINGS")"

python3 - "$USER_SETTINGS" <<'PYEOF'
import json, os, sys, tempfile
path = sys.argv[1]
SCOUT_ALLOW = [
    "mcp__Salesforce_DX__*",
    "mcp__Salesforce_Docs__*",
    "mcp__slack__*",
    "mcp__plugin_slack_*",
    "Agent",
    "Skill",
]

if os.path.exists(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"USER_SETTINGS_PARSE_ERROR: {e}")
        sys.exit(0)
else:
    data = {}

if not isinstance(data, dict):
    print("USER_SETTINGS_NOT_OBJECT")
    sys.exit(0)

perms = data.setdefault("permissions", {})
if not isinstance(perms, dict):
    print("USER_SETTINGS_PERMS_NOT_OBJECT")
    sys.exit(0)

allow = perms.setdefault("allow", [])
if not isinstance(allow, list):
    print("USER_SETTINGS_ALLOW_NOT_LIST")
    sys.exit(0)

added = [e for e in SCOUT_ALLOW if e not in allow]
if not added:
    print("USER_SETTINGS_NO_CHANGES")
    sys.exit(0)

allow.extend(added)

tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".settings.", suffix=".tmp")
try:
    with os.fdopen(tmp_fd, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.rename(tmp_path, path)
except Exception as e:
    try: os.unlink(tmp_path)
    except OSError: pass
    print(f"USER_SETTINGS_WRITE_FAILED: {e}")
    sys.exit(0)

print(f"USER_SETTINGS_UPDATED: added {len(added)} of {len(SCOUT_ALLOW)} entries")
PYEOF
```

Surface inline:
- `USER_SETTINGS_NO_CHANGES` — silent.
- `USER_SETTINGS_UPDATED: added N of 6 entries` — "Added N Scout entries to `~/.claude/settings.json` allowlist (inert outside Scout sessions)."
- Any error variant — one-line note, proceed.

## g.9: Mirror quality-knob env vars to settings.json

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

## g.5: Ensure marketplace autoUpdate is enabled

Fresh-install SEs add the Scout marketplace via `/plugin marketplace add` BEFORE running `/scout-setup`, so CC writes the `extraKnownMarketplaces.scout` entry without `autoUpdate: true`. The migration trampoline pre-writes the flag; fresh installs need this fallback. Idempotent, safe-fail.

```bash
USER_SETTINGS="$HOME/.claude/settings.json"

python3 - "$USER_SETTINGS" <<'PYEOF'
import json, os, sys, tempfile
path = sys.argv[1]

if not os.path.exists(path):
    print("AUTOUPDATE_NO_SETTINGS"); sys.exit(0)

try:
    with open(path) as f:
        data = json.load(f)
except (json.JSONDecodeError, OSError) as e:
    print(f"AUTOUPDATE_PARSE_ERROR: {e}"); sys.exit(0)

if not isinstance(data, dict):
    print("AUTOUPDATE_NOT_OBJECT"); sys.exit(0)

marketplaces = data.get("extraKnownMarketplaces")
if not isinstance(marketplaces, dict):
    print("AUTOUPDATE_NO_MARKETPLACES"); sys.exit(0)

scout = marketplaces.get("scout")
if not isinstance(scout, dict):
    print("AUTOUPDATE_NO_SCOUT_ENTRY"); sys.exit(0)

if scout.get("autoUpdate") is True:
    print("AUTOUPDATE_ALREADY_ON"); sys.exit(0)

scout["autoUpdate"] = True

tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".settings.", suffix=".tmp")
try:
    with os.fdopen(tmp_fd, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.rename(tmp_path, path)
except Exception as e:
    try: os.unlink(tmp_path)
    except OSError: pass
    print(f"AUTOUPDATE_WRITE_FAILED: {e}"); sys.exit(0)

print("AUTOUPDATE_ENABLED")
PYEOF
```

Surface inline:
- `AUTOUPDATE_ALREADY_ON` — silent.
- `AUTOUPDATE_ENABLED` — "Enabled auto-updates for Scout marketplace — future versions will install automatically on session start."
- `AUTOUPDATE_NO_SETTINGS` / `AUTOUPDATE_NO_MARKETPLACES` / `AUTOUPDATE_NO_SCOUT_ENTRY` — silent (the marketplace add step writes these; absence means setup is being run in an unexpected state, not Scout's problem).
- Any error variant — one-line note, proceed.

## h: Slack MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/slack-mcp.md` and execute it with `mode=strict`. The prompt handles registration + auth probe; in strict mode any failure aborts. Resume here only on success.

## i: Write config.json

Read `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`. Extract the `version` field as a string for `[PLUGIN_VERSION]`.

Pre-compute the dynamic values via Bash so they land as literals (not unevaluated `$()` strings) regardless of how the heredoc gets executed:

```bash
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
WORKSPACE="$HOME/claude-projects/sf-demo-scout"
mkdir -p "$HOME/.config/sf-demo-scout"
cat > "$HOME/.config/sf-demo-scout/config.json" <<EOF
{
  "workspace_path": "$WORKSPACE",
  "install_method": "plugin",
  "plugin_version": "[PLUGIN_VERSION]",
  "setup_completed_at": "$NOW"
}
EOF
echo "CONFIG_WRITTEN"
```

The heredoc is unquoted on purpose — `$WORKSPACE` and `$NOW` must expand. Only `[PLUGIN_VERSION]` is a literal-text substitution you do before running this block.

## j: .zshrc Scout-managed block

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/zshrc-block.md` and execute it. Capture the result (`ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED`, plus optional `ANTHROPIC_MODEL_PRESENT`) — the orchestrator's done step needs it.

## Done

Fresh-install procedure complete. Return to the orchestrator. Pass the result of step j (`ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED`, plus optional `ANTHROPIC_MODEL_PRESENT`) so the done message can include the shell-refresh note.
