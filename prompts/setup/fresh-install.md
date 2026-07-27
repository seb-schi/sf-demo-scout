# Scout Setup — Fresh Install

End-to-end install procedure. Run on `STATE=FRESH`.

**Idempotency contract:** every step below is idempotent and self-detecting. Re-running after an abort (e.g. SE returning from `/mcp` Slack auth) is safe and fast — completed steps fast-no-op via their own probes (`BREW_OK`, `NODE_PRESENT`, `SETTINGS_PRESENT`, `USER_SETTINGS_NO_CHANGES`, `AUTOUPDATE_ALREADY_ON`, `SLACK_MCP_ALREADY_REGISTERED`, etc.). Always run end-to-end; do NOT skip steps trying to "resume" — the no-ops are the resume mechanism. Within the same CC session you may rely on conversation memory to fast-forward; across sessions, just run the full sequence — it will land in the right place naturally.

## a: Brew Check (hard abort if missing)

`command -v brew` misses when brew is installed but not yet on PATH (Apple
Silicon installs to `/opt/homebrew/bin`; the post-install `eval` line adds it
to PATH). So probe the known install locations before concluding it's missing —
otherwise an SE who installed brew but skipped the `eval` step gets a false
`BREW_MISSING` and dead-ends.

```bash
if command -v brew >/dev/null 2>&1; then
  echo "BREW_OK"
elif [ -x /opt/homebrew/bin/brew ]; then
  echo "BREW_NOT_ON_PATH /opt/homebrew/bin/brew"
elif [ -x /usr/local/bin/brew ]; then
  echo "BREW_NOT_ON_PATH /usr/local/bin/brew"
else
  echo "BREW_MISSING"
fi
```

If `BREW_NOT_ON_PATH <path>`, brew is installed but this shell can't see it.
Report it as installed but not on PATH. ABORT and emit (substitute the `<path>`
dir from the probe output — `/opt/homebrew/bin` or `/usr/local/bin`):

> ⚠️ **Homebrew is installed but not on your PATH yet** — one line fixes it.
>
> Run this, then re-run `/scout-setup`:
> ```
> eval "$(<path>/brew shellenv)"
> ```
> To make it stick for new shells, add that same line to your `~/.zprofile`.

If `BREW_MISSING`, ABORT and emit:

> ⚠️ **Homebrew isn't installed — the one step Claude Code can't do for you** (the installer needs your Mac password).
>
> 1. Open a **fresh macOS Terminal**: ⌘+Space → type `Terminal` → Enter. *Not* the terminal running Claude (VS Code / desktop app / current tab) — you need a separate window at a plain `you@Mac ~ %` prompt.
> 2. Paste & run:
>    ```
>    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
>    ```
> 3. Enter your Mac password (invisible as you type — normal).
> 4. Run the `eval …` lines it prints at the end — skip these and brew won't be found.
> 5. Back in Claude Code: `/scout-setup` again.

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
mkdir -p orgs/lessons
if [ ! -f orgs/lessons/INDEX.md ]; then
  cat > orgs/lessons/INDEX.md <<'EOF'
# Lessons Index

Topic-clustered lessons from scout-sparring + scout-building sessions.
This INDEX is loaded at the start of every session; topic files are
loaded on demand based on the descriptive lines below.

Each lesson is whole — it may carry both a sparring rule and a building
backstop. Lessons are not split by phase. Add new lessons to the topic
file that best fits; create a new topic + INDEX line if none fit.

## Topics

- **agentforce.md** — Agentforce agent build + iteration: action-invocation-as-proof, GenAiPlannerBundle safety, enhanced-event-log diagnostics, pre-Agent-Script (Atlas/UI-built) agent handling, headless/Agent API recipes, agent action schema.
- **managed-packages.md** — Managed-package write/read restrictions and schema quirks (lsc4ce / LSC, Health Cloud, FSC, industry clouds): namespaced retrieve names, trigger/validation DML gates, stage-gated field locks, territory/sharing blast radius.
- **flow.md** — Flow + FlowTest: generated-flow defect patterns, FlowTest XML schema, CLI flow-run breakage, record-triggered vs screen flow gotchas.
- **data-seeding.md** — Data seeding: CLI `sf data` envelope/Bash quirks, pilot-self-test limits, pricebook/SKU gating, paired-record cleanup, idempotency.
- **metadata-deploy.md** — Org-SPECIFIC metadata deploy/parse gotchas (distinct from the org-agnostic Known Deploy-Error Patterns catalog): roll-up-summary relationship traps, permset description limits, field/picklist verification, RT-specific values.
- **discovery-and-scoping.md** — Sparring heuristics: customer-evidence gate, reuse-orgs-aggressively, booth-vs-WorldTour scoping, existing-first object/field probing, marketed-vs-shorthand product names, data-quality-before-reuse.
- **lwc-slds.md** — LWC + SLDS: internal-token hard-fails, SLDS2 utility/global-hook fixes, Code Analyzer deprecation warnings.
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
    "mcp__plugin_sf-demo-scout_Salesforce_DX__*",
    "mcp__plugin_sf-demo-scout_Salesforce_Docs__*",
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

## g.7: Scrub stale AI-Suite hooks (self-heal)

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/aisuite-scrub.md` and execute its procedure. Ex-AI-Suite machines carry hook registrations under `~/.aisuite/` that throw every turn once AI Suite is uninstalled — and because that residue is not written by Scout, it exists even on a Scout-fresh install. The fragment removes only those hook entries from the two `~/.claude` settings JSON files and surfaces (without touching) any leftover aisuite cert path or plugin/marketplace config. Idempotent, safe-fail, never aborts. Carry any `AISUITE_HOOKS_REMOVED` / `FLAGS` note into the closing message.

## g.8: Strip stale model pins across all surfaces (self-heal)

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/model-pin-strip.md` and execute its procedure. Various Salesforce tools (AI Suite, DevBar, etc.) hard-pin `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL` / `modelOverrides`, sometimes erroneously, which collapses the `/model` picker so the SE can't reach newer models (e.g. Opus 4.8) — and because that residue is not written by Scout, it exists even on a Scout-fresh install. The fragment removes those pins (plus the retired `MAX_THINKING_TOKENS` and `CLAUDE_CODE_MAX_OUTPUT_TOKENS`) from the two `~/.claude` settings JSON files, VS Code's user settings, and launchctl GUI env. Idempotent, safe-fail, never aborts. Carry any `PINS_REMOVED[...]` / `VSCODE_PINS_REMOVED` / `LAUNCHCTL_PINS_CLEARED` / VS-Code-restore-or-warn note into the closing message (a restart, and possibly a manual VS Code edit, is pending).

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

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/slack-mcp.md` and execute it with `mode=soft`. The prompt handles registration + auth probe; it never aborts setup — any failure surfaces a loud "Slack not connected — X will be skipped, re-run anytime" notice and returns. (The `SLACK_MCP_REGISTERED` branch still returns so the SE can `/reload-plugins`.)

## h.5: Google Workspace MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/google-mcp.md` and execute it with `mode=soft`. Optional discovery enhancement (read Docs/Sheets during sparring); gated behind the DevBar `mcp-adaptor` binary. Never aborts — if the binary is absent or auth is pending, it surfaces a note and returns.

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
