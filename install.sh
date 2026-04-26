#!/bin/bash
# SF Demo Scout — One-time install script
# Run once after cloning the repo. Sets up SFDX and shell environment.
# Safe to re-run if something went wrong the first time.

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZSHRC="$HOME/.zshrc"

echo ""
echo "🤖 SF Demo Scout — Install"
echo "================================"
echo ""

# --- 1. Homebrew ---
echo "🔍 Checking Homebrew..."
if ! command -v brew &>/dev/null; then
  echo "📦 Homebrew not found. Installing..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Add brew to PATH for Apple Silicon Macs
  if [ -f "/opt/homebrew/bin/brew" ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
    echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> "$ZSHRC"
  fi
  echo "✅ Homebrew installed."
else
  echo "✅ Homebrew found."
fi

# --- 2. Node.js ---
echo ""
echo "🔍 Checking Node.js..."
if ! command -v node &>/dev/null; then
  echo "📦 Node.js not found. Installing via Homebrew..."
  brew install node
  echo "✅ Node.js installed."
else
  NODE_VERSION=$(node --version)
  echo "✅ Node.js found ($NODE_VERSION)."
fi

# --- 3. Claude Code (prerequisite — installed via LLMGW installer) ---
echo ""
echo "🔍 Checking Claude Code..."
if command -v claude &>/dev/null; then
  CLAUDE_VERSION=$(claude --version 2>/dev/null | head -1)
  echo "✅ Claude Code found ($CLAUDE_VERSION)."
else
  echo ""
  echo "❌ Claude Code not found."
  echo "   Install it first using the 'Installing Claude Code for Solutions' canvas:"
  echo "     macOS/Linux: curl -fsSL https://plugins.codegen.salesforceresearch.ai/claude/install.sh | bash"
  echo "     Windows:     irm https://plugins.codegen.salesforceresearch.ai/claude/install.ps1 | iex"
  echo ""
  echo "   Then re-run: bash install.sh"
  exit 1
fi

# --- 4. Python 3.9+ (required for Agentforce ADLC skills) ---
echo ""
echo "🔍 Checking Python 3.9+..."
if command -v python3 &>/dev/null; then
  PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
  if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 9 ]; then
    echo "✅ Python $PY_VERSION found."
  else
    echo "⚠️  Python $PY_VERSION found but 3.9+ required. Installing..."
    brew install python@3.13
    echo "✅ Python 3.13 installed."
  fi
else
  echo "📦 Python not found. Installing via Homebrew..."
  brew install python@3.13
  echo "✅ Python 3.13 installed."
fi

# --- 5. Salesforce CLI ---
echo ""
echo "🔍 Checking Salesforce CLI..."
if ! command -v sf &>/dev/null; then
  echo "📦 Salesforce CLI not found. Installing..."
  npm install @salesforce/cli --global
  echo "✅ Salesforce CLI installed."
else
  SF_VERSION=$(sf --version | head -1)
  echo "✅ Salesforce CLI found ($SF_VERSION). Checking for updates..."
  sf update 2>&1 | tail -3
  echo "✅ Salesforce CLI up to date."
fi

# --- 6. Pre-cache MCP server ---
echo ""
echo "📦 Pre-caching Salesforce MCP server..."
npx -y @salesforce/mcp --help >/dev/null 2>&1
if [ $? -eq 0 ]; then
  echo "✅ Salesforce MCP server cached."
else
  echo "⚠️  MCP server pre-cache failed. Claude Code may need a retry on first start."
fi

# --- 7. Slack MCP Registration (user-scope, persistent across update.sh) ---
echo ""
echo "🔍 Checking Slack MCP registration..."
if command -v claude &>/dev/null; then
  if claude mcp list 2>/dev/null | grep -qE '^[[:space:]]*slack[[:space:]]*:'; then
    echo "✅ Slack MCP already registered (user scope)."
  else
    echo "📦 Registering Slack MCP (user scope — persists across update.sh)..."
    if claude mcp add -s user -t http \
        --client-id 188160004832.9210129962818 \
        --callback-port 3118 \
        slack https://mcp.slack.com/mcp >/dev/null 2>&1; then
      echo "✅ Slack MCP registered. Authenticate in your first Claude Code session:"
      echo "   run /mcp, select 'slack', choose 'Authenticate', complete OAuth in browser."
    else
      echo "⚠️  Slack MCP registration failed. You can add it manually later:"
      echo "   claude mcp add -s user -t http --client-id 188160004832.9210129962818 \\"
      echo "     --callback-port 3118 slack https://mcp.slack.com/mcp"
    fi
  fi
else
  echo "⚠️  Skipping Slack MCP registration — 'claude' CLI not found (see section 3)."
fi

# --- 8. SFDX Project ---
echo ""
echo "🔍 Checking SFDX project..."
if [ ! -f "$REPO_DIR/sfdx-project.json" ]; then
  echo "📁 Initialising SFDX project..."
  cd "$REPO_DIR"
  sf project generate --name sf-demo-scout --template empty 2>/dev/null || true
  # sf project generate creates a subfolder — move sfdx-project.json up if needed
  if [ -f "$REPO_DIR/sf-demo-scout/sfdx-project.json" ]; then
    mv "$REPO_DIR/sf-demo-scout/sfdx-project.json" "$REPO_DIR/"
    mv "$REPO_DIR/sf-demo-scout/force-app" "$REPO_DIR/" 2>/dev/null || true
    rm -rf "$REPO_DIR/sf-demo-scout"
  fi
  echo "✅ SFDX project initialised."
else
  echo "✅ SFDX project already exists."
fi

# --- 9. External Skills (manifest-driven) ---
echo ""
echo "🔍 Syncing external skills from manifest..."

# Ensure pyyaml is available for sync-skills.sh manifest parser
if ! python3 -c 'import yaml' 2>/dev/null; then
  echo "  📦 Installing pyyaml (required for manifest parsing)..."
  pip3 install --quiet --user pyyaml 2>/dev/null || pip3 install --quiet --break-system-packages pyyaml 2>/dev/null || true
fi

SYNC_SCRIPT="$REPO_DIR/.claude/scripts/sync-skills.sh"
if [ -f "$SYNC_SCRIPT" ]; then
  # Invoke via `bash` so we don't depend on the exec bit being set yet —
  # the chmod step runs later in this script.
  bash "$SYNC_SCRIPT" | grep -E '^(SYNCED|PRUNED|FAILED)=' | sed 's/^/  /' || true
  echo "  ✅ Skill sync complete (see lines above for details)."
else
  echo "  ⚠️  Sync script not found at $SYNC_SCRIPT"
  echo "       Check your clone is complete, then re-run: bash install.sh"
fi

cd "$REPO_DIR"

# --- 10. Shell Environment Variables ---
echo ""
echo "🔍 Checking shell environment..."

# Claude Code PATH (installer puts binary in ~/.local/bin).
# PATH stays outside the managed block — it's an append and SEs often
# already have their own entry.
if ! grep -q 'PATH="$HOME/.local/bin' "$ZSHRC" 2>/dev/null; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$ZSHRC"
  echo "  ➕ Added: ~/.local/bin to PATH"
else
  echo "  ✅ PATH already includes ~/.local/bin"
fi

# Scout-managed block: values Scout owns outright.
# Rewritten fresh on every install/update so SEs always pick up the
# current canonical values (models, token limits) without per-key
# migration hacks.
SCOUT_KEYS=(
  CLAUDE_CODE_MAX_OUTPUT_TOKENS
  MAX_THINKING_TOKENS
  ANTHROPIC_DEFAULT_OPUS_MODEL
  ANTHROPIC_DEFAULT_SONNET_MODEL
  ANTHROPIC_DEFAULT_HAIKU_MODEL
)
BLOCK_BEGIN="# BEGIN SF-DEMO-SCOUT"
BLOCK_END="# END SF-DEMO-SCOUT"
TODAY=$(date +%Y-%m-%d)

touch "$ZSHRC"

# (a) Comment out pre-existing Scout-owned exports that live OUTSIDE the
# managed block. Uses a Python pass for safe multi-line state tracking.
python3 - "$ZSHRC" "$TODAY" "$BLOCK_BEGIN" "$BLOCK_END" "${SCOUT_KEYS[@]}" <<'PYEOF'
import re, sys
path, today, begin, end, *keys = sys.argv[1:]
with open(path) as f:
    lines = f.readlines()
key_re = re.compile(r'^\s*export\s+(' + '|'.join(re.escape(k) for k in keys) + r')\s*=')
in_block = False
out = []
redacted = 0
for line in lines:
    stripped = line.rstrip('\n')
    if stripped == begin:
        in_block = True
        out.append(line); continue
    if stripped == end:
        in_block = False
        out.append(line); continue
    if not in_block and key_re.match(line):
        out.append(f"# [sf-demo-scout {today}] superseded by managed block: {stripped}\n")
        redacted += 1
    else:
        out.append(line)
with open(path, 'w') as f:
    f.writelines(out)
print(f"REDACTED={redacted}")
PYEOF

# (b) Delete the previous managed block (if any).
if grep -q "^$BLOCK_BEGIN\$" "$ZSHRC"; then
  sed -i '' "/^$BLOCK_BEGIN\$/,/^$BLOCK_END\$/d" "$ZSHRC"
fi

# (c) Append the fresh managed block.
{
  echo ""
  echo "$BLOCK_BEGIN"
  echo "# Managed by install.sh — do not edit. Run update.sh to refresh."
  echo "export CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192"
  echo "export MAX_THINKING_TOKENS=4096"
  echo "export ANTHROPIC_DEFAULT_OPUS_MODEL=us.anthropic.claude-opus-4-7"
  echo "export ANTHROPIC_DEFAULT_SONNET_MODEL=us.anthropic.claude-sonnet-4-6"
  echo "export ANTHROPIC_DEFAULT_HAIKU_MODEL=anthropic.claude-haiku-4-5-20251001-v1:0"
  echo "$BLOCK_END"
} >> "$ZSHRC"
echo "  ✅ Scout-managed block refreshed in $ZSHRC"

# Legacy warning: ANTHROPIC_MODEL is not a Claude Code variable and is
# not in our managed set. If the SE has one lingering, flag it — they
# need to delete it manually.
if grep -q "^\s*export\s*ANTHROPIC_MODEL\s*=" "$ZSHRC" 2>/dev/null; then
  echo "  ⚠️  Found ANTHROPIC_MODEL in .zshrc — this is not a Claude Code variable."
  echo "     Remove it manually: edit ~/.zshrc and delete the line."
fi

# --- 11. Script permissions ---
echo ""
echo "🔍 Checking script permissions..."
HOOK="$REPO_DIR/.claude/hooks/session-startup.sh"
if [ -f "$HOOK" ]; then
  chmod +x "$HOOK"
  echo "✅ session-startup.sh is executable."
else
  echo "⚠️  session-startup.sh not found at $HOOK — check your clone is complete."
fi

SYNC_SCRIPT="$REPO_DIR/.claude/scripts/sync-skills.sh"
if [ -f "$SYNC_SCRIPT" ]; then
  chmod +x "$SYNC_SCRIPT"
  echo "✅ sync-skills.sh is executable."
else
  echo "⚠️  sync-skills.sh not found at $SYNC_SCRIPT — check your clone is complete."
fi

# --- Done ---
echo ""
echo "================================"
echo "✅ Install complete!"
echo ""
echo "Next steps:"
echo "  1. Open VSCode"
echo "  2. File → Open Folder → select: ~/claude-projects/sf-demo-scout"
echo "  3. Open the integrated terminal (Ctrl+\`)"
echo "  4. Type: claude"
echo "  5. In Claude Code, run /mcp → select 'slack' → 'Authenticate' → complete OAuth in browser"
echo "  6. Then type: /setup-demo-scout"
echo ""
echo "Claude Code will connect your demo org and run your first audit. ☕"
echo ""