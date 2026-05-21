#!/bin/bash
# SF Demo Scout — Migration Notice
# This file is the trampoline payload. Old update.sh invokes it via
# `SF_SCOUT_CHAINED=1 bash install.sh`. We MUST exit 0 — old update.sh's
# ERR trap on non-zero prints stale recovery advice that loops back here.

set +e

cat <<'EOF'

================================================================
  SF Demo Scout has moved to a Claude Code plugin.
================================================================

  The clone-install path (this script) is being retired. Your org
  data at ~/claude-projects/sf-demo-scout/orgs/ is safe and will
  be picked up by the plugin automatically on first command run.

  To finish the migration:

  1. Open a fresh Claude Code session (any project, doesn't matter
     where — plugins are global).

  2. Run these two slash commands inside Claude Code:

        /plugin marketplace add https://github.com/seb-schi/sf-demo-scout-plugin.git
        /plugin install sf-demo-scout@scout

  3. After the plugin installs, restart Claude Code.

  4. Run /setup-demo-scout one last time. It will detect the
     plugin, clean up the old clone-install artifacts, and hand
     you over to /scout-sparring or /scout-switch-org.

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
