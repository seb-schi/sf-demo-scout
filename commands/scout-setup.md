---
name: scout-setup
description: >
  One-stop install, refresh, and repair for Scout.
  Run on first install, after a Scout update, or whenever something feels broken.
  Idempotent — safe to re-run any time.
model: sonnet
allowed-tools: Read, Write, Edit, Bash
---

# Scout Setup — Install, Refresh, Repair

You are the setup orchestrator. This command is idempotent and state-driven: it detects what needs doing and does it. No flags, no branches the SE has to pick.

## Step 1: Detect State

Run this Bash:

```bash
mkdir -p "$HOME/claude-projects/sf-demo-scout"
cd "$HOME/claude-projects/sf-demo-scout"
if [ -d .git ] && [ -f install.sh ]; then
  echo "STATE=COLLISION"
elif [ ! -f "$HOME/.config/sf-demo-scout/config.json" ]; then
  echo "STATE=FRESH"
else
  echo "STATE=REFRESH"
fi
```

Branch on output:
- `STATE=COLLISION` → run Step 2 (Collision Scrub), then Step 3 (Fresh Install) end-to-end.
- `STATE=FRESH` → run Step 3 (Fresh Install) end-to-end.
- `STATE=REFRESH` → run Step 4 (Refresh) — skips the install-from-scratch steps but does CLI updates + skill sync + Slack probe + config bump.

After the chosen branch returns, run Step 5 (Done) regardless of branch.

## Step 2: Collision Scrub (only if STATE=COLLISION)

Detected old clone-install residue (both `.git/` and `install.sh` present in workspace). Scrub it before proceeding. Preserves SE data (`orgs/`, `.sf/`).

```bash
cd "$HOME/claude-projects/sf-demo-scout"
rm -rf .git
rm -f install.sh
rm -rf .claude
echo "COLLISION_SCRUBBED"
```

Surface to SE:

> "Detected old clone-install residue — removed `.git/`, `install.sh`, and `.claude/`. Your `orgs/` data is preserved. Proceeding with fresh setup."

Then proceed to Step 3.

## Step 3: Fresh Install (STATE=FRESH or post-COLLISION)

Run the full setup procedure end-to-end.

### 3a: Brew Check (hard abort if missing)

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

### 3b: Auto-install Node, Python, sf CLI

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

### 3c: Pre-cache Salesforce MCP server

```bash
echo "PRE_CACHING_MCP"
npx -y @salesforce/mcp --help >/dev/null 2>&1 && echo "MCP_CACHED" || echo "MCP_CACHE_FAILED"
```

On `MCP_CACHE_FAILED`, surface a one-line note ("MCP pre-cache failed — first MCP call may be slow") and proceed.

### 3d: Workspace Directory + SFDX Scaffold

```bash
mkdir -p "$HOME/claude-projects/sf-demo-scout/orgs"
cd "$HOME/claude-projects/sf-demo-scout"
if [ ! -f sfdx-project.json ]; then
  sf project generate --name sf-demo-scout --template empty 2>/dev/null || true
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

### 3e: Starter Lessons Files

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

### 3f: Workspace `.claude/settings.json`

```bash
SETTINGS="$HOME/claude-projects/sf-demo-scout/.claude/settings.json"
TEMPLATE="${CLAUDE_PLUGIN_ROOT}/assets/workspace-settings.template.json"
mkdir -p "$(dirname "$SETTINGS")"
if [ ! -f "$SETTINGS" ]; then
  cp "$TEMPLATE" "$SETTINGS"
  echo "SETTINGS_WRITTEN"
else
  echo "SETTINGS_PRESENT"
fi
```

### 3g: User-scope permissions merge

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

### 3g.5: Ensure marketplace autoUpdate is enabled

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

### 3h: Slack MCP Auth Probe

```bash
security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null | \
  python3 -c "import json,sys; d=json.loads(sys.stdin.read()); oauth=d.get('mcpOAuth',{}); slack=[k for k in oauth if k.startswith('slack')]; tok=oauth[slack[0]].get('accessToken') if slack else None; print('authenticated' if tok else 'needs_auth')" 2>/dev/null || echo "needs_auth"
```

On `needs_auth`, ABORT:

> "Slack MCP needs authentication before Scout setup can finish. It powers customer canvas lookups during sparring and the post-deployment handover canvas.
>
> **Run `/mcp` in this session now.** Select 'slack' from the MCP server list (under User MCPs) and hit 'Enter'. A browser window will open that will prompt you to authenticate. Select 'Salesforce Internal' and log in.
>
> When you're back, re-run `/scout-setup` — setup will resume."

### 3i: Sync upstream skills

Ensure pyyaml first:

```bash
if ! python3 -c 'import yaml' 2>/dev/null; then
  pip3 install --quiet --user pyyaml 2>/dev/null || pip3 install --quiet --break-system-packages pyyaml 2>/dev/null || true
fi
python3 -c 'import yaml; print("PYYAML_OK")' 2>/dev/null || echo "PYYAML_MISSING"
```

On `PYYAML_MISSING`, ABORT:

> "Scout's skill sync needs Python's pyyaml module, which couldn't auto-install. Run this in a terminal, then re-run `/scout-setup`:
>
> ```
> pip3 install --user pyyaml
> ```"

Read `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`. Extract the `version` field as a string for `[PLUGIN_VERSION]`. ALSO resolve `${CLAUDE_PLUGIN_ROOT}` to its absolute filesystem path (the directory the plugin.json you just Read lives in, minus `/.claude-plugin`) and substitute as `[PLUGIN_ROOT]` below — `${CLAUDE_PLUGIN_ROOT}` does NOT expand inside Bash shell context, only inside Read-tool path arguments, so the bash invocation must receive the literal absolute path.

```bash
CLAUDE_PLUGIN_ROOT="[PLUGIN_ROOT]" \
  WORKSPACE_DIR="$HOME/claude-projects/sf-demo-scout" \
  PLUGIN_VERSION="[PLUGIN_VERSION]" \
  bash "[PLUGIN_ROOT]/scripts/sync-skills.sh"
```

Surface SYNCED/FAILED/PRUNED counts. On `FAILED_COUNT > 0`, also print FAILED= lines so the SE sees which skills broke. Do NOT abort — proceed to 3j.

### 3j: Write config.json

Substitute `[PLUGIN_VERSION]` with the value Read in 3i:

```bash
mkdir -p "$HOME/.config/sf-demo-scout"
cat > "$HOME/.config/sf-demo-scout/config.json" <<EOF
{
  "workspace_path": "$HOME/claude-projects/sf-demo-scout",
  "install_method": "plugin",
  "plugin_version": "[PLUGIN_VERSION]",
  "last_synced_plugin_version": "[PLUGIN_VERSION]",
  "setup_completed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
echo "CONFIG_WRITTEN"
```

### 3k: .zshrc Scout-managed block

Run:

```bash
ZSHRC="$HOME/.zshrc"
touch "$ZSHRC"
ZSHRC_BEFORE_HASH=$(shasum "$ZSHRC" | awk '{print $1}')

python3 - "$ZSHRC" <<'PYEOF'
import re, sys
path = sys.argv[1]
BEGIN = "# BEGIN SF-DEMO-SCOUT"
END = "# END SF-DEMO-SCOUT"
KEYS = [
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
    "MAX_THINKING_TOKENS",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
]
BLOCK_LINES = [
    BEGIN,
    "# Managed by Scout plugin — do not edit. Refreshed on first-run setup.",
    "export CLAUDE_CODE_MAX_OUTPUT_TOKENS=16384",
    "export MAX_THINKING_TOKENS=8192",
    "export ANTHROPIC_DEFAULT_OPUS_MODEL=us.anthropic.claude-opus-4-7[1m]",
    "export ANTHROPIC_DEFAULT_SONNET_MODEL=us.anthropic.claude-sonnet-4-6",
    "export ANTHROPIC_DEFAULT_HAIKU_MODEL=anthropic.claude-haiku-4-5-20251001-v1:0",
    END,
]

with open(path) as f:
    lines = f.readlines()

key_re = re.compile(r'^\s*export\s+(' + '|'.join(re.escape(k) for k in KEYS) + r')\s*=')
legacy_re = re.compile(r'^# \[sf-demo-scout \d{4}-\d{2}-\d{2}\] superseded by managed block: ')

in_block = False
out = []
for line in lines:
    stripped = line.rstrip('\n')
    if stripped == BEGIN:
        in_block = True
        out.append(line); continue
    if stripped == END:
        in_block = False
        out.append(line); continue
    if not in_block and key_re.match(line):
        continue
    if legacy_re.match(line):
        continue
    out.append(line)

cleaned = []
skip = False
for line in out:
    stripped = line.rstrip('\n')
    if stripped == BEGIN:
        skip = True
        continue
    if stripped == END:
        skip = False
        continue
    if not skip:
        cleaned.append(line)

while cleaned and cleaned[-1].strip() == "":
    cleaned.pop()

body = "".join(cleaned)
if body and not body.endswith("\n"):
    body += "\n"
body += "\n" + "\n".join(BLOCK_LINES) + "\n"

with open(path, "w") as f:
    f.write(body)
PYEOF

ZSHRC_AFTER_HASH=$(shasum "$ZSHRC" | awk '{print $1}')
if [ "$ZSHRC_BEFORE_HASH" = "$ZSHRC_AFTER_HASH" ]; then
  echo "ZSHRC_UNCHANGED"
else
  echo "ZSHRC_MODIFIED"
fi

if grep -qE '^\s*export\s+ANTHROPIC_MODEL\s*=' "$ZSHRC" 2>/dev/null; then
  echo "ANTHROPIC_MODEL_PRESENT"
fi
```

If `ANTHROPIC_MODEL_PRESENT`, surface a one-line warning:

> "⚠️ Found legacy `ANTHROPIC_MODEL` in your `~/.zshrc` — this is not a Claude Code variable. Remove it manually."

Proceed to Step 5 (Done) — fresh-install path complete.

## Step 4: Refresh (STATE=REFRESH)

Workspace already configured. Update CLIs, sync skills, refresh `.zshrc` block, bump config version. Idempotent.

### 4a: Update Salesforce CLI

```bash
echo "UPDATING_SF_CLI"
npm install @salesforce/cli --global 2>&1 | tail -1
echo "SF_CLI_AT $(sf --version | head -1)"
```

### 4b: Update Claude Code CLI

```bash
echo "UPDATING_CLAUDE_CLI"
npm install @anthropic-ai/claude-code --global 2>&1 | tail -1
echo "CLAUDE_CLI_AT $(claude --version 2>/dev/null || echo 'unknown')"
```

If either npm command fails (non-zero exit), surface a one-line note ("[sf|claude] CLI update failed — continuing") and proceed. Don't abort.

### 4c: Slack MCP probe (silent unless broken)

```bash
security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null | \
  python3 -c "import json,sys; d=json.loads(sys.stdin.read()); oauth=d.get('mcpOAuth',{}); slack=[k for k in oauth if k.startswith('slack')]; tok=oauth[slack[0]].get('accessToken') if slack else None; print('authenticated' if tok else 'needs_auth')" 2>/dev/null || echo "needs_auth"
```

On `authenticated` — silent.
On `needs_auth` — surface a one-line note (do NOT abort the refresh):

> "⚠️ Slack MCP needs re-authentication. Run `/mcp` → 'slack' → 'Authenticate' when convenient. Refresh continues."

### 4d: Sync upstream skills

Run 3i verbatim (pyyaml check + sync). On `PYYAML_MISSING`, surface the same note as 3i but do NOT abort the refresh — surface and proceed to 4e.

### 4e: Bump config.json `last_synced_plugin_version`

Substitute `[PLUGIN_VERSION]` with the value Read in 4d:

```bash
python3 - "$HOME/.config/sf-demo-scout/config.json" "[PLUGIN_VERSION]" <<'PYEOF'
import json, sys
path, version = sys.argv[1], sys.argv[2]
with open(path) as f:
    data = json.load(f)
data["plugin_version"] = version
data["last_synced_plugin_version"] = version
with open(path, "w") as f:
    json.dump(data, f, indent=2)
PYEOF
echo "CONFIG_BUMPED"
```

### 4f: Refresh .zshrc managed block

Run the 3k bash block verbatim (idempotent — `ZSHRC_UNCHANGED` if already current).

Proceed to Step 5.

## Step 5: Done

Read `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`. Extract `requires_reload` (default `false` if absent) and `version`.

Compose the closing message based on the branch taken:

**If STATE was FRESH or COLLISION:**

> "✓ Scout is set up and ready. Workspace at `~/claude-projects/sf-demo-scout/`.
>
> Next: run `/scout-switch-org` to connect a demo org, or `/scout-sparring` to start sparring."

**If STATE was REFRESH and `requires_reload: false`:**

> "✓ Scout refreshed to v[VERSION]. Skills synced, CLIs current. You're good to keep working."

**If STATE was REFRESH and `requires_reload: true`:**

> "✓ Scout refreshed to v[VERSION] (command surface changed). Skills synced, CLIs current.
>
> **Close + reopen this Claude tab** to load the new commands. (If running in VS Code and the new tab still feels stale, fully restart VS Code.) Then continue your work."

**If `ZSHRC_MODIFIED` (any branch):** append before the close:

> "Note: Scout refreshed your shell environment. Open a new terminal window for non-Claude-Code shell sessions to pick up the changes — current Claude Code session is unaffected."
