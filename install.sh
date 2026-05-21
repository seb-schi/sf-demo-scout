#!/bin/bash
# SF Demo Scout — Migration Notice + Self-Cleanup
# This file is the trampoline payload. Old update.sh invokes it via
# `SF_SCOUT_CHAINED=1 bash install.sh`. We MUST exit 0 — old update.sh's
# ERR trap on non-zero prints stale recovery advice that loops back here.
#
# This script self-cleans the trampoline scaffolding so the workspace
# is left in the same shape the plugin's bootstrap expects: orgs/, .sf/,
# nothing else. Bash on Unix can keep running after deleting its own
# script file (inode-pinned).

set +e

WORKSPACE="$HOME/claude-projects/sf-demo-scout"
cd "$WORKSPACE" 2>/dev/null || true

# Self-clean trampoline scaffolding. Each guarded so re-running stays idempotent.
for path in .git install.sh bootstrap.sh update.sh README.md .claude force-app sfdx-project.json CLAUDE.md; do
  [ -e "$path" ] && rm -rf "$path"
done

cat <<'EOF'

================================================================
  SF Demo Scout has moved to a Claude Code plugin.
================================================================

  The clone-install path is retired. Your org data at
  ~/claude-projects/sf-demo-scout/orgs/ is preserved and will be
  picked up by the plugin automatically on first command run.

  To finish the migration:

  1. Open a fresh Claude Code session (any project — plugins are
     global).

  2. Run these two slash commands inside Claude Code:

        /plugin marketplace add https://github.com/seb-schi/sf-demo-scout-plugin.git
        /plugin install sf-demo-scout@scout

  3. After the plugin installs, restart Claude Code.

  4. Run /scout-sparring (or /scout-switch-org). The plugin's
     first-run bootstrap detects the missing workspace state and
     finishes setup automatically.

  Why the change?
    - One-step install (no curl pipe, no git clone)
    - Auto-update via the plugin marketplace
    - Cleaner shell environment, idempotent setup
    - Faster, leaner sessions

  Questions? Ping #sf-demo-scout on Slack.

================================================================

EOF

# Exit 0 is mandatory — old update.sh's ERR trap fires on non-zero.
exit 0
