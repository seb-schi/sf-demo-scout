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

# --- 7. SFDX Project ---
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

# --- 8. External Skills (manifest-driven) ---
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

append_if_missing() {
  local key="$1"
  local line="$2"
  if ! grep -q "$key" "$ZSHRC" 2>/dev/null; then
    echo "$line" >> "$ZSHRC"
    echo "  ➕ Added: $key"
  else
    echo "  ✅ Already set: $key"
  fi
}

# Claude Code PATH (installer puts binary in ~/.local/bin)
append_if_missing 'PATH="$HOME/.local/bin' 'export PATH="$HOME/.local/bin:$PATH"'

# Claude Code configuration
append_if_missing "CLAUDE_CODE_MAX_OUTPUT_TOKENS" "export CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192"
append_if_missing "MAX_THINKING_TOKENS" "export MAX_THINKING_TOKENS=1024"

# Model aliases
append_if_missing "ANTHROPIC_DEFAULT_OPUS_MODEL" "export ANTHROPIC_DEFAULT_OPUS_MODEL=us.anthropic.claude-opus-4-7"
append_if_missing "ANTHROPIC_DEFAULT_SONNET_MODEL" "export ANTHROPIC_DEFAULT_SONNET_MODEL=us.anthropic.claude-sonnet-4-6"
append_if_missing "ANTHROPIC_DEFAULT_HAIKU_MODEL" "export ANTHROPIC_DEFAULT_HAIKU_MODEL=anthropic.claude-haiku-4-5-20251001-v1:0"

# Warn about common issues
if grep -q "ANTHROPIC_MODEL" "$ZSHRC" 2>/dev/null; then
  echo "  ⚠️  Found ANTHROPIC_MODEL in .zshrc — this is not a Claude Code variable."
  echo "     The default model is set via ANTHROPIC_DEFAULT_SONNET_MODEL."
  echo "     Remove the ANTHROPIC_MODEL line from ~/.zshrc"
fi

if [ "$(grep -c "CLAUDE_CODE_MAX_OUTPUT_TOKENS" "$ZSHRC" 2>/dev/null)" -gt 1 ]; then
  echo "  ⚠️  CLAUDE_CODE_MAX_OUTPUT_TOKENS appears more than once in .zshrc."
  echo "     Keep only one: export CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192"
fi

# If MAX_OUTPUT_TOKENS was previously set to 4096, bump it
sed -i '' 's/CLAUDE_CODE_MAX_OUTPUT_TOKENS=4096/CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192/' "$ZSHRC" 2>/dev/null || true

source "$ZSHRC" 2>/dev/null || true

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
echo "  5. Once Claude Code starts, type: /setup-demo-scout"
echo ""
echo "Claude Code will connect your demo org and run your first audit. ☕"
echo ""
echo "To pull the latest skills from upstream later, run: /sync-skills"
echo ""