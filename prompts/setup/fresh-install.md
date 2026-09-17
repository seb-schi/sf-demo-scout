# Scout Setup — Fresh Install

End-to-end install procedure. Run on `STATE=FRESH`.

**Idempotency contract:** every step below is idempotent and self-detecting. Re-running after an abort (e.g. SE returning from `/mcp` Slack auth) is safe and fast — completed steps fast-no-op via their own probes (`BREW_OK`, `NODE_PRESENT`, `SETTINGS_PRESENT`, `USER_SETTINGS_NO_CHANGES`, `AUTOUPDATE_ALREADY_ON`, etc.). Always run end-to-end; do NOT skip steps trying to "resume" — the no-ops are the resume mechanism. Within the same CC session you may rely on conversation memory to fast-forward; across sessions, just run the full sequence — it will land in the right place naturally.

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

Each tool runs through the shipped Bash bootstrap independently. Before each
invocation, resolve this active Scout plugin installation's root from the
current plugin context to a concrete absolute path. Do not pass a literal
`${CLAUDE_PLUGIN_ROOT}`, reuse a variable from another shell invocation, search
for another cached version, or reconstruct the helper if it is unavailable.
Run the Node, Python, and sf blocks below in that order, in separate shell
invocations. Inspect each exit/result before starting the next; do not batch or
run them in parallel because the sf installation may depend on npm supplied by
the preceding Node installation.

The helper probes the actual selected executable and installs only when that
executable is missing. An existing broken, malformed, unreadable, or unsupported
tool is left unchanged; Scout never installs a competing runtime over it.

```bash
SCOUT_BOOTSTRAP_SCRIPT="/absolute/path/of/active/sf-demo-scout/scripts/setup-bootstrap.sh"
if [ ! -f "$SCOUT_BOOTSTRAP_SCRIPT" ]; then
  echo "NODE_UNAVAILABLE (shipped bootstrap missing)"
  exit 1
else
  /bin/bash "$SCOUT_BOOTSTRAP_SCRIPT" node
fi
```

```bash
SCOUT_BOOTSTRAP_SCRIPT="/absolute/path/of/active/sf-demo-scout/scripts/setup-bootstrap.sh"
if [ ! -f "$SCOUT_BOOTSTRAP_SCRIPT" ]; then
  echo "PYTHON_UNAVAILABLE (shipped bootstrap missing)"
  exit 1
else
  /bin/bash "$SCOUT_BOOTSTRAP_SCRIPT" python
fi
```

```bash
SCOUT_BOOTSTRAP_SCRIPT="/absolute/path/of/active/sf-demo-scout/scripts/setup-bootstrap.sh"
if [ ! -f "$SCOUT_BOOTSTRAP_SCRIPT" ]; then
  echo "SF_CLI_UNAVAILABLE (shipped bootstrap missing)"
  exit 1
else
  /bin/bash "$SCOUT_BOOTSTRAP_SCRIPT" sf
fi
```

For each independent call:

- `*_PRESENT` / `*_INSTALLED` — proceed. These tokens include the verified
  selected executable version.
- `*_UNVERIFIED` — ABORT. The selected executable could not be verified before
  installation, or an installer exited 0 without leaving a qualifying selected
  executable. Do not claim success or try another runtime.
- `PYTHON_UNSUPPORTED` — ABORT. Keep the existing Python unchanged and explain
  Scout requires Python 3.9+ within major 3.
- `*_INSTALL_FAILED` — ABORT. Report the installer exit code and warn that a
  failed installer may have partially changed state; do not promise the old
  state survived.
- `*_UNAVAILABLE` — ABORT. Surface the named missing prerequisite or shipped
  helper/log issue. In particular, missing npm blocks sf installation even when
  Node exists.

On any nonzero helper exit, stop the fresh-install procedure. Ask the SE to
select a suitable existing executable or repair it through its own manager in a
terminal, then rerun `/scout-setup`. Suggest installation only when the tool is
missing. Never fall through to the ready/Done handoff.

## c: Pre-cache Salesforce MCP server

```bash
echo "PRE_CACHING_MCP"
NPX_EXE=$(type -P npx 2>/dev/null || true)
if [ -z "$NPX_EXE" ]; then
  echo "MCP_CACHE_UNAVAILABLE (npx missing)"
elif "$NPX_EXE" -y @salesforce/mcp --help >/dev/null 2>&1; then
  echo "MCP_CACHED"
else
  echo "MCP_CACHE_FAILED"
fi
```

- `MCP_CACHE_UNAVAILABLE` — surface that npx is missing, so optional DX MCP
  pre-cache could not run. Do not replace Node automatically. Proceed.
- `MCP_CACHE_FAILED` — surface that the actual optional cache attempt failed, so
  DX MCP readiness remains unverified. Proceed with the existing runtime
  degradation path.
- `MCP_CACHED` — means only that this pre-cache command succeeded; it is not a
  provider compatibility or runtime capability claim.

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
    "mcp__salesforce-docs__*",
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

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/aisuite-scrub.md` and execute its procedure (the fragment carries the full "why"). Carry any `AISUITE_HOOKS_REMOVED` / `FLAGS` note into the closing message — a hook removal means a CC restart is pending.

## g.8: Strip stale model pins across all surfaces (self-heal)

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/model-pin-strip.md` and execute its procedure (the fragment carries the full "why"). Carry any `PINS_REMOVED[...]` / `VSCODE_PINS_REMOVED` / `LAUNCHCTL_PINS_CLEARED` / VS-Code-restore-or-warn note into the closing message — a restart, and possibly a manual VS Code edit, is pending.

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

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/slack-mcp.md` and execute it. Report the observed registration/transport state without inferring authentication or tool availability. Existing connections are preserved; an optional new registration is an explicit SE choice. Return and continue setup.

## h.5: Google Workspace MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/google-mcp.md` and execute it. Optional discovery enhancement for Docs/Sheets during sparring. Preserve existing connections even when their launcher differs from Scout's known default; check the DevBar adaptor only when offering that default. Return with observed status and continue setup.

## h.7: Salesforce Docs MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/salesforce-docs-mcp.md` and execute it. Preserve existing registrations and report observed status; the historical default is offered only for an explicit new connection. Required Docs tools are checked when needed. Return and continue setup.

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
