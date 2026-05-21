#!/bin/bash
# SF Demo Scout — Update (migration shim)
# This file replaces the old self-relocating update.sh on new main. SEs
# whose pre-cached old update.sh has already run land here on subsequent
# invocations (because old update.sh did `rm -rf $REPO_DIR && git clone`,
# leaving the new payload on disk). Idempotent: anyone running update.sh
# from inside the migrated dir gets the migration banner.

set +e

cat <<'EOF'

================================================================
  SF Demo Scout has moved to a Claude Code plugin.
================================================================

  This update.sh is a migration shim. The clone-install upgrade
  path is being retired.

  If you have NOT yet installed the plugin:

    1. Open a fresh Claude Code session.
    2. Run inside Claude Code:

         /plugin marketplace add https://github.com/seb-schi/sf-demo-scout-plugin.git
         /plugin install sf-demo-scout@scout

    3. Restart Claude Code, then run /setup-demo-scout to finish
       cleanup of this old clone-install directory.

  If you HAVE already installed the plugin:

    Run /setup-demo-scout inside Claude Code. It will detect
    the plugin and clean up the old clone-install artifacts.

  Your org data at ~/claude-projects/sf-demo-scout/orgs/ is
  safe and will be picked up by the plugin automatically.

  Questions? Ping #sf-demo-scout on Slack.

================================================================

EOF

exit 0
