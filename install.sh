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

# --- 3. Python 3.9+ (required for Agentforce ADLC skills) ---
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

# --- 4. Salesforce CLI ---
echo ""
echo "🔍 Checking Salesforce CLI..."
if ! command -v sf &>/dev/null; then
  echo "📦 Salesforce CLI not found. Installing..."
  npm install @salesforce/cli --global
  echo "✅ Salesforce CLI installed."
else
  SF_VERSION=$(sf --version | head -1)
  echo "✅ Salesforce CLI found ($SF_VERSION)."
fi

# --- 5. SFDX Project ---
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

# --- 6. Salesforce Skills (Jaganpro/sf-skills) ---
echo ""
echo "🔍 Installing Salesforce skills..."
SKILLS_BASE_URL="https://raw.githubusercontent.com/Jaganpro/sf-skills/main/skills"
SKILLS_DIR="$REPO_DIR/.claude/skills"

for SKILL in sf-flow sf-metadata sf-permissions sf-deploy sf-apex sf-soql sf-data sf-debug; do
  echo "  📦 Installing $SKILL..."
  mkdir -p "$SKILLS_DIR/$SKILL"
  if curl -fsSL "$SKILLS_BASE_URL/$SKILL/SKILL.md" -o "$SKILLS_DIR/$SKILL/SKILL.md"; then
    echo "  ✅ $SKILL installed."
  else
    echo "  ⚠️  $SKILL install failed. Run manually:"
    echo "       curl -fsSL $SKILLS_BASE_URL/$SKILL/SKILL.md -o $SKILLS_DIR/$SKILL/SKILL.md"
  fi
done

# --- 7. Agentforce ADLC Skills (SalesforceAIResearch/agentforce-adlc) ---
echo ""
echo "🔍 Installing Agentforce ADLC skills..."
ADLC_REPO="https://github.com/SalesforceAIResearch/agentforce-adlc.git"
ADLC_TMP="/tmp/agentforce-adlc"

# Clone or update the ADLC repo
if [ -d "$ADLC_TMP" ]; then
  echo "  📦 Updating agentforce-adlc..."
  cd "$ADLC_TMP" && git pull --quiet 2>/dev/null || true
else
  echo "  📦 Cloning agentforce-adlc..."
  git clone --depth 1 --quiet "$ADLC_REPO" "$ADLC_TMP" 2>/dev/null
fi

# Copy the three skill directories
for ADLC_SKILL in developing-agentforce testing-agentforce observing-agentforce; do
  if [ -d "$ADLC_TMP/skills/$ADLC_SKILL" ]; then
    echo "  📦 Installing $ADLC_SKILL..."
    mkdir -p "$SKILLS_DIR/$ADLC_SKILL"
    cp -r "$ADLC_TMP/skills/$ADLC_SKILL/"* "$SKILLS_DIR/$ADLC_SKILL/"
    echo "  ✅ $ADLC_SKILL installed."
  else
    echo "  ⚠️  $ADLC_SKILL not found in repo — check https://github.com/SalesforceAIResearch/agentforce-adlc"
  fi
done

cd "$REPO_DIR"

# --- 8. Shell Environment Variables ---
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

append_if_missing "CLAUDE_CODE_MAX_OUTPUT_TOKENS" "export CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192"
append_if_missing "MAX_THINKING_TOKENS" "export MAX_THINKING_TOKENS=1024"
append_if_missing "ANTHROPIC_DEFAULT_OPUS_MODEL" "export ANTHROPIC_DEFAULT_OPUS_MODEL=us.anthropic.claude-opus-4-6-v1"
append_if_missing "ANTHROPIC_DEFAULT_SONNET_MODEL" "export ANTHROPIC_DEFAULT_SONNET_MODEL=us.anthropic.claude-sonnet-4-6"
append_if_missing "ANTHROPIC_DEFAULT_HAIKU_MODEL" "export ANTHROPIC_DEFAULT_HAIKU_MODEL=anthropic.claude-haiku-4-5-20251001-v1:0"

# If MAX_OUTPUT_TOKENS was previously set to 4096, bump it
sed -i '' 's/CLAUDE_CODE_MAX_OUTPUT_TOKENS=4096/CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192/' "$ZSHRC" 2>/dev/null || true

source "$ZSHRC" 2>/dev/null || true

# --- 9. session-startup.sh permissions ---
echo ""
echo "🔍 Checking hook permissions..."
HOOK="$REPO_DIR/.claude/hooks/session-startup.sh"
if [ -f "$HOOK" ]; then
  chmod +x "$HOOK"
  echo "✅ session-startup.sh is executable."
else
  echo "⚠️  session-startup.sh not found at $HOOK — check your clone is complete."
fi

# --- Done ---
echo ""
echo "================================"
echo "✅ Install complete!"
echo ""
echo "Next steps:"
echo "  1. Open VSCode"
echo "  2. File → Open Folder → select: $REPO_DIR"
echo "  3. Open the integrated terminal (Ctrl+\`)"
echo "  4. Type: claude"
echo "  5. Once Claude Code starts, type: /setup-demo-scout"
echo ""
echo "Claude Code will connect your demo org and run your first audit. ☕"
echo ""