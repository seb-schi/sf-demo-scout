#!/bin/bash
# SF Demo Scout — Migration Notice (trampoline payload)
#
# Production update.sh on the SE's disk runs us via:
#   SF_SCOUT_CHAINED=1 bash install.sh
# and then `exec claude "/setup-demo-scout"`. Our job is just to print
# the banner and exit 0. The actual migration work happens inside
# Claude Code via /setup-demo-scout (in this trampoline's .claude/commands/).
#
# CRITICAL: exit 0 is mandatory — production update.sh's ERR trap fires
# on non-zero with stale "rm -rf and re-clone" recovery advice that loops
# the SE back here.
#
# We do NOT self-clean the trampoline scaffolding here. Production
# update.sh's tail does `exec claude "/setup-demo-scout"`, which needs
# .claude/commands/setup-demo-scout.md to be present on disk.

set +e

cat <<'EOF'

================================================================
  SF Demo Scout has moved to a Claude Code plugin.
================================================================

  Update fetched the migration shim. Claude Code is about to open
  with the migration handler — follow its instructions to finish.

  Your org data at ~/claude-projects/sf-demo-scout/orgs/ is
  preserved throughout.

  Questions? Ping #sf-demo-scout on Slack.

================================================================

EOF

exit 0
