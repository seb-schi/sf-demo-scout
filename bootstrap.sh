#!/bin/bash
# SF Demo Scout — Bootstrap (migration shim)
# The clone-install bootstrap is retired. This file exists so the curl
# one-liner from old documentation still produces a useful message.

set +e

cat <<'EOF'

================================================================
  SF Demo Scout has moved to a Claude Code plugin.
================================================================

  The curl-pipe install path is being retired. There is no
  longer anything to clone.

  To install Scout:

  1. Make sure Claude Code is installed. If not, follow the
     "Installing Claude Code for Solutions" canvas first.

  2. Open a fresh Claude Code session (any project — plugins
     are global).

  3. Run these two slash commands inside Claude Code:

        /plugin marketplace add https://github.com/seb-schi/sf-demo-scout-plugin.git
        /plugin install sf-demo-scout@scout

  4. After the plugin installs, restart Claude Code.

  5. Run /scout-sparring or /scout-switch-org. The plugin's
     first-run bootstrap will set up your workspace.

  Questions? Ping #sf-demo-scout on Slack.

================================================================

EOF

exit 0
