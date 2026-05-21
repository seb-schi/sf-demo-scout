# Workspace Setup (slow path)

Loaded by `workspace-bootstrap.md` when `~/.config/sf-demo-scout/config.json`
is missing. Replicates the install.sh + setup-demo-scout.md behaviours from
the clone-install path. All steps are idempotent — safe to re-run.

Each step that fails-hard ABORTS the parent Scout command (the SE re-invokes
after fixing). Bootstrap fragments cannot pause for SE replies mid-Read.

## Step 1: Brew Check (hard abort if missing)

Homebrew install requires interactive sudo to claim ownership of `/opt/homebrew/`,
which cannot run inside a Claude Code session. If brew is missing, the SE
must install it from a terminal first; everything else (node/python/sf) we
can auto-install in-session.

```bash
command -v brew >/dev/null 2>&1 && echo "BREW_OK" || echo "BREW_MISSING"
```

If output is `BREW_MISSING`, ABORT the parent command and emit:

> "Scout setup needs Homebrew installed first. Brew install requires
> interactive sudo so it can't run inside Claude Code.
>
> Open a terminal and run:
>
> ```
> /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
> ```
>
> Then re-run the Scout command — Scout will auto-install Node, Python, and
> the Salesforce CLI from there."

Do not proceed past this step on `BREW_MISSING`.

## Step 2: Auto-install Node, Python, sf CLI

Each tool: check first, install only if missing. Emit a one-line status
message to the SE before each install (Opus-side procedure: read the
bash output, surface "Installing X (~30-60s)..." before proceeding).

```bash
# Node.js
if ! command -v node >/dev/null 2>&1; then
  echo "INSTALLING_NODE"
  brew install node 2>&1 | tail -1
  echo "NODE_DONE"
else
  echo "NODE_PRESENT ($(node --version))"
fi
```

```bash
# Python 3.9+
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
# Salesforce CLI
if ! command -v sf >/dev/null 2>&1; then
  echo "INSTALLING_SF_CLI"
  npm install @salesforce/cli --global 2>&1 | tail -1
  echo "SF_CLI_DONE"
else
  echo "SF_CLI_PRESENT ($(sf --version | head -1))"
fi
```

If any install command fails (non-zero exit, or the post-install
`command -v` re-check fails), ABORT the parent command and emit:

> "Scout couldn't auto-install [tool name]. The brew/npm output was:
>
> ```
> [last line from install command]
> ```
>
> Open a terminal and run the install command manually, then re-run the
> Scout command — Scout will pick up from where it left off."

## Step 3: Pre-cache Salesforce MCP server

Mirrors install.sh §6. First-time `npx -y @salesforce/mcp` downloads ~50MB;
doing it now means the first MCP call inside a Scout command doesn't stall.

```bash
echo "PRE_CACHING_MCP"
npx -y @salesforce/mcp --help >/dev/null 2>&1 && echo "MCP_CACHED" || echo "MCP_CACHE_FAILED"
```

On `MCP_CACHE_FAILED` do NOT abort — the MCP will lazy-load on first use,
just slower. Note the failure to the SE inline ("MCP pre-cache failed —
first MCP call may be slow") and proceed.

## Step 4: Workspace Directory

```bash
mkdir -p "$HOME/claude-projects/sf-demo-scout/orgs"
```

Idempotent. No abort branch — `mkdir -p` doesn't fail on existing dirs.

## Step 5: SFDX Scaffold

```bash
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

No abort branch — `sf project generate` errors are absorbed (`|| true`)
because the move-up dance handles the "subfolder already exists" case
on re-run. If `sfdx-project.json` is still missing after this step,
Step 8 (config writer) will not flip the marker and the slow path will
re-run on next invocation.

## Step 5.5: Sync upstream skills

Mirror clone-install's install.sh §9 (skill manifest sync). Pulls the
16 upstream skills declared in `${CLAUDE_PLUGIN_ROOT}/skills-manifest.yaml`
into `${WORKSPACE_DIR}/.claude/skills/`. Plugin-vendored homegrown
skills (`demo-*`) live at `${CLAUDE_PLUGIN_ROOT}/skills/` and are NOT
touched by sync.

First, ensure pyyaml is available (the sync engine's manifest parser):

```bash
if ! python3 -c 'import yaml' 2>/dev/null; then
  pip3 install --quiet --user pyyaml 2>/dev/null || pip3 install --quiet --break-system-packages pyyaml 2>/dev/null || true
fi
python3 -c 'import yaml; print("PYYAML_OK")' 2>/dev/null || echo "PYYAML_MISSING"
```

On `PYYAML_MISSING`, ABORT and emit:

> "Scout's skill sync needs Python's pyyaml module, which couldn't
> auto-install. Run this in a terminal, then re-run the Scout command:
>
> ```
> pip3 install --user pyyaml
> ```"

Then Read `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json` (Read-tool
path resolution; bash shell expansion does not work for
`${CLAUDE_PLUGIN_ROOT}` — see [[project_plugin_root_no_shell_expansion]]).
Extract the `version` field as a string. This same value is reused in
Step 8 (config writer) — surface it once here as `[PLUGIN_VERSION]`
and substitute literally in both bash blocks.

Run the sync:

```bash
WORKSPACE_DIR="$HOME/claude-projects/sf-demo-scout" \
  PLUGIN_VERSION="[PLUGIN_VERSION]" \
  bash "${CLAUDE_PLUGIN_ROOT}/scripts/sync-skills.sh"
```

Read the SYNCED_COUNT / FAILED_COUNT / PRUNED_COUNT lines from output
and surface a one-line status:

> "Synced [N] upstream skills into the workspace."

On `FAILED_COUNT > 0`: do NOT abort the bootstrap (skills will
fall back to whatever was previously in place; first-time runs end up
with partial coverage). Surface a warning:

> "[F] of [N+F] skills failed to sync. Setup will continue. You can
> retry later with `/scout-sync-skills`. The failed skill folders are
> listed below:"

followed by the FAILED= lines from output.

## Step 6: Starter Lessons Files

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

Idempotent — only writes if file is missing.

## Step 7: Slack MCP Auth Check

Probe keychain for an active Slack OAuth token:

```bash
security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null | \
  python3 -c "import json,sys; d=json.loads(sys.stdin.read()); oauth=d.get('mcpOAuth',{}); slack=[k for k in oauth if k.startswith('slack')]; tok=oauth[slack[0]].get('accessToken') if slack else None; print('authenticated' if tok else 'needs_auth')" 2>/dev/null || echo "needs_auth"
```

Interpret the single-word output:

- `authenticated` — proceed to Step 8.

- `needs_auth` (or any other output) — ABORT the parent command and emit:

  > "Slack MCP needs authentication before Scout setup can finish. It powers customer canvas lookups during sparring and the post-deployment handover canvas.
  >
  > **Run `/mcp` in this session now.** Select 'slack' from the MCP server list (under User MCPs) and hit 'Enter'. A browser window will open that will prompt you to authenticate. Select 'Salesforce Internal' and log in.
  >
  > When you're back, re-invoke the Scout command — setup will resume."

Do not proceed past this step on `needs_auth`.

## Step 7.5: Write workspace `.claude/settings.json`

Plugin scope can't ship a workspace-scope settings.json (plugins are
global; settings.json is per-workspace). Bootstrap writes it on first
run so the SE gets:

- Opus as default model (Scout sparring + audit work better on Opus
  than Sonnet)
- Permissions allowlist for common tools (avoids per-call approval
  prompts for Bash, Edit, MCP tools, etc.)
- Permissions denylist for destructive operations (rm -rf on workspace
  data, sf org delete, force-push, etc.)

The SessionStart hook block is intentionally NOT written here — it
ships in plugin land via `${CLAUDE_PLUGIN_ROOT}/hooks/hooks.json`.
Adding it to workspace settings would double-register and double-fire
the banner.

Idempotent: only writes if `.claude/settings.json` is missing. Don't
clobber if SE has hand-edited (e.g. raised model thinking budget,
added local permissions).

```bash
SETTINGS="$HOME/claude-projects/sf-demo-scout/.claude/settings.json"
mkdir -p "$(dirname "$SETTINGS")"
if [ ! -f "$SETTINGS" ]; then
  cat > "$SETTINGS" <<'EOF'
{
  "model": "opus",
  "permissions": {
    "allow": [
      "mcp__Salesforce_DX__*",
      "mcp__Salesforce_Docs__*",
      "mcp__slack__*",
      "mcp__plugin_slack_*",
      "Bash",
      "Edit",
      "Write",
      "Read",
      "Agent",
      "Skill"
    ],
    "deny": [
      "Bash(rm -rf orgs*)",
      "Bash(rm -r orgs*)",
      "Bash(rm -rf ~*)",
      "Bash(rm -rf $HOME*)",
      "Bash(rm -rf /Users/*)",
      "Bash(rm -rf /*)",
      "Bash(rm -rf ~/.sf*)",
      "Bash(rm -rf .sf*)",
      "Bash(sf org delete*)",
      "Bash(sf org logout --all*)",
      "Bash(git push --force*)",
      "Bash(git push -f *)"
    ]
  },
  "showThinkingSummaries": true
}
EOF
  echo "SETTINGS_WRITTEN"
else
  echo "SETTINGS_PRESENT"
fi
```

On `SETTINGS_WRITTEN`, surface a one-line note to the SE:

> Wrote workspace `.claude/settings.json` (Opus default, MCP/Bash
> allowlist, destructive-op denylist). Reload in your current session
> by quitting + relaunching Claude Code from this workspace, OR keep
> going on Sonnet for now — Opus picks up next session.

(The settings file is loaded on session start, not on write — running
session won't hot-pick-up the model change.)

## Step 8: Write config.json

First, Read `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json` (the Read tool
resolves `${CLAUDE_PLUGIN_ROOT}` correctly; shell expansion does not — that's
why we cannot grep the file from inside bash). Extract the `version` field
value as a string.

Then run this Bash, substituting `[PLUGIN_VERSION]` with the extracted value:

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

Once written, future bootstrap fast-path checks see config.json present
and skip the slow path entirely.

## Step 8.5: .zshrc Scout-managed block

Append (or refresh) the Scout-managed env-var block in `~/.zshrc`. Mirrors
install.sh §10 so a single SE switching install methods only ever has one
managed block. Block markers are `# BEGIN SF-DEMO-SCOUT` / `# END SF-DEMO-SCOUT`
(matching install.sh exactly).

The Python pass below atomically:
- strips Scout-owned exports outside the managed block (canonical values
  live inside the block; outside-block exports otherwise win on shell
  load order and create silent drift),
- sweeps legacy "superseded by managed block" redaction comments from
  prior install.sh versions,
- removes the existing managed block AND any blank lines immediately
  surrounding it (fixes install.sh's blank-line-accumulation bug —
  every install.sh refresh prepends a blank, so after N updates the
  file has N stray blanks before the block),
- appends exactly one blank line + the fresh managed block at EOF.

Determine whether the block changed by comparing pre/post file contents;
set `ZSHRC_MODIFIED=1` if changed, else `0`. Pass the value to Step 9.

Run this Bash:

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
    "export CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192",
    "export MAX_THINKING_TOKENS=4096",
    "export ANTHROPIC_DEFAULT_OPUS_MODEL=us.anthropic.claude-opus-4-7",
    "export ANTHROPIC_DEFAULT_SONNET_MODEL=us.anthropic.claude-sonnet-4-6",
    "export ANTHROPIC_DEFAULT_HAIKU_MODEL=anthropic.claude-haiku-4-5-20251001-v1:0",
    END,
]

with open(path) as f:
    lines = f.readlines()

key_re = re.compile(r'^\s*export\s+(' + '|'.join(re.escape(k) for k in KEYS) + r')\s*=')
legacy_re = re.compile(r'^# \[sf-demo-scout \d{4}-\d{2}-\d{2}\] superseded by managed block: ')

# Pass 1: strip Scout-owned exports outside the block + legacy comments.
# Track block boundaries.
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

# Pass 2: remove existing block (including the BEGIN/END lines).
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

# Pass 3: trim trailing blank lines (collapses the install.sh accumulation).
while cleaned and cleaned[-1].strip() == "":
    cleaned.pop()

# Append: exactly one blank + fresh block + trailing newline.
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

# Legacy ANTHROPIC_MODEL warning (not a Claude Code variable, not in our managed set).
if grep -qE '^\s*export\s+ANTHROPIC_MODEL\s*=' "$ZSHRC" 2>/dev/null; then
  echo "ANTHROPIC_MODEL_PRESENT"
fi
```

Capture the bash output. If the last meaningful line is `ZSHRC_MODIFIED`,
set `ZSHRC_MODIFIED=true` for Step 9; otherwise `false`. If the bash also
emitted `ANTHROPIC_MODEL_PRESENT`, surface a one-line warning to the SE
BEFORE the Step 9 confirmation:

> "⚠️ Found legacy `ANTHROPIC_MODEL` in your `~/.zshrc` — this is not a Claude Code variable. Remove it manually: edit `~/.zshrc` and delete the line."

## Step 9: Confirm to SE

Emit one of these messages depending on `ZSHRC_MODIFIED`:

**If `ZSHRC_MODIFIED=true`:**

> "Scout workspace setup complete at `~/claude-projects/sf-demo-scout/`.
>
> Note: Scout added a managed block to your `~/.zshrc` for default model env vars. **Open a new terminal window** before any non-Claude-Code shell session — current Claude Code session is unaffected. Continuing with your command."

**If `ZSHRC_MODIFIED=false`:**

> "Scout workspace setup complete at `~/claude-projects/sf-demo-scout/`. Continuing with your command."

Then return control to the parent Scout command.
