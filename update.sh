#!/bin/bash
# SF Demo Scout — Update Script
# Preserves org data (audits, specs, change logs) and org config.
# Safe to run from inside or outside the project directory.

set -e

REPO_NAME="sf-demo-scout"
PROJECTS_DIR="$HOME/claude-projects"
REPO_DIR="$PROJECTS_DIR/$REPO_NAME"
BACKUP_DIR="$PROJECTS_DIR/.sf-demo-scout-backup"
TMP_SCRIPT="/tmp/sf-demo-scout-update.sh"
REPO_URL="https://github.com/seb-schi/sf-demo-scout"

# --- 0. Self-relocate to /tmp if running from inside the repo ---
if [ "${1:-}" != "--from-tmp" ]; then
  cp "$0" "$TMP_SCRIPT"
  chmod +x "$TMP_SCRIPT"

  # If inside VS Code terminal, open Terminal.app instead
  if [ "$TERM_PROGRAM" = "vscode" ]; then
    osascript -e "tell application \"Terminal\" to do script \"bash $TMP_SCRIPT --from-tmp\"" 2>/dev/null
    echo ""
    echo "Opened Terminal.app for the update."
    echo "Close VS Code now — reopen it after the update finishes."
    exit 0
  fi

  exec bash "$TMP_SCRIPT" --from-tmp
fi

# --- Running from /tmp beyond this point ---
echo ""
echo "🔄 SF Demo Scout — Update"
echo "================================"
echo ""

# --- 1. Confirm ---
if [ ! -d "$REPO_DIR" ]; then
  echo "❌ $REPO_DIR not found. Nothing to update."
  echo "   To install from scratch: git clone $REPO_URL $REPO_DIR"
  exit 1
fi

echo "This will update SF Demo Scout to the latest version."
echo "Your org data (audits, specs, change logs) will be preserved."
echo ""
printf "Continue? [y/N] "
read -r CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
  echo "Cancelled."
  exit 0
fi

echo ""

# --- 2. Backup ---
echo "📦 Backing up org data..."
rm -rf "$BACKUP_DIR"
mkdir -p "$BACKUP_DIR"

if [ -d "$REPO_DIR/orgs" ]; then
  cp -R "$REPO_DIR/orgs" "$BACKUP_DIR/orgs"
  ORG_COUNT=$(ls -d "$BACKUP_DIR/orgs"/*/ 2>/dev/null | wc -l | tr -d ' ')
  echo "   ✅ orgs/ backed up ($ORG_COUNT folder(s))"
else
  echo "   ℹ️  No orgs/ folder found (fresh install?)"
fi

if [ -f "$REPO_DIR/.sf/config.json" ]; then
  mkdir -p "$BACKUP_DIR/.sf"
  cp "$REPO_DIR/.sf/config.json" "$BACKUP_DIR/.sf/config.json"
  echo "   ✅ .sf/config.json backed up"
else
  echo "   ℹ️  No .sf/config.json found"
fi

# --- 3. Delete ---
echo ""
echo "🗑️  Removing old installation..."
rm -rf "$REPO_DIR"
echo "   ✅ Removed $REPO_DIR"

# --- 4. Re-clone ---
echo ""
echo "📥 Cloning latest version..."
git clone "$REPO_URL" "$REPO_DIR" 2>&1 | tail -1
echo "   ✅ Cloned"

# --- 5. Restore backups ---
echo ""
echo "📂 Restoring org data..."

if [ -d "$BACKUP_DIR/orgs" ]; then
  cp -R "$BACKUP_DIR/orgs" "$REPO_DIR/orgs"
  echo "   ✅ orgs/ restored"
fi

if [ -f "$BACKUP_DIR/.sf/config.json" ]; then
  mkdir -p "$REPO_DIR/.sf"
  cp "$BACKUP_DIR/.sf/config.json" "$REPO_DIR/.sf/config.json"
  echo "   ✅ .sf/config.json restored"
fi

# --- 6. Run install ---
echo ""
echo "⚙️  Running install.sh..."
cd "$REPO_DIR"
bash install.sh

# --- 7. Cleanup ---
rm -rf "$BACKUP_DIR"
rm -f "$TMP_SCRIPT"

echo ""
echo "================================"
echo "✅ Update complete!"
echo ""
echo "Next: open VS Code → File → Open Folder → $REPO_DIR"
echo "      Claude Code will start with the latest version."
echo ""
