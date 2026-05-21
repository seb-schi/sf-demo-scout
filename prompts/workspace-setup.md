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
  "setup_completed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
echo "CONFIG_WRITTEN"
```

Once written, future bootstrap fast-path checks see config.json present
and skip the slow path entirely.

## Step 9: Confirm to SE

Emit a single one-line message to the SE:

> "Scout workspace setup complete at `~/claude-projects/sf-demo-scout/`. Continuing with your command."

Then return control to the parent Scout command.
