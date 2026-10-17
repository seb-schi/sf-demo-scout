# Workspace Bootstrap

Read by `/scout` as its first step: one read-only Bash gate with two outcomes.

## Step 1: Sanity gate

Substitute `[SCOUT_HOST]` (`claude` or `codex`, per `prompts/host-runtime.md`; an
unknown host is a check failure, not a Claude fallback) and the resolved absolute
plugin root for `[PLUGIN_ROOT]`, then run the whole fence as written. The quoted
heredoc runs in `/bin/bash`, even under zsh. The gate never creates the workspace
or its configuration.

```bash
/bin/bash <<'SCOUT_WORKSPACE_BOOTSTRAP_BASH'
WORKSPACE="${SCOUT_WORKSPACE:-$HOME/claude-projects/sf-demo-scout}"
CONFIG="${SCOUT_CONFIG_FILE:-$HOME/.config/sf-demo-scout/config.json}"
WORKSPACE_HELPER="[PLUGIN_ROOT]/scripts/setup-workspace.py"
PYTHON_EXE=$(/usr/bin/which python3 2>/dev/null || true)
case "$PYTHON_EXE" in ""|/*) ;; *) PYTHON_EXE="$PWD/$PYTHON_EXE" ;; esac

if [ -z "$PYTHON_EXE" ]; then
  echo "STATE=CHECK_FAILED"
  echo "Scout workspace check failed: verified Python 3 executable unavailable." >&2
  exit 1
fi
if [ ! -f "$WORKSPACE_HELPER" ]; then
  echo "STATE=CHECK_FAILED"
  echo "Scout workspace check failed: shipped verifier helper missing: $WORKSPACE_HELPER" >&2
  exit 1
fi

"$PYTHON_EXE" -B "$WORKSPACE_HELPER" verify \
  --workspace "$WORKSPACE" --config "$CONFIG" --host "[SCOUT_HOST]"
VERIFY_STATUS=$?
if [ "$VERIFY_STATUS" -eq 0 ]; then
  echo "STATE=OK WORKSPACE=$WORKSPACE"
  exit 0
fi
echo "STATE=CHECK_FAILED"
echo "Scout workspace verifier failed with exit $VERIFY_STATUS; its diagnostic output is above." >&2
exit "$VERIFY_STATUS"
SCOUT_WORKSPACE_BOOTSTRAP_BASH
```

- `STATE=OK`: say nothing, and return to the command's next step.
- `STATE=CHECK_FAILED`, any nonzero exit, or no `STATE=OK`: stop, and show the
  verifier's complete output and the gate's diagnostic. Suggest `/scout-setup`
  when that output names `WORKSPACE_INVALID`, `SFDX_PROJECT_INVALID`,
  `FORCE_APP_INVALID`, `LESSONS_INVALID`, `SETTINGS_INVALID` or `CONFIG_INVALID`.
  For a missing interpreter or helper, a permission error or an invocation
  failure, report that exact reason without calling it a fresh install.

## After bootstrap

The shell's working folder doesn't persist between tool calls: run each later
call in the printed `WORKSPACE`, or start it with a checked `cd` there. Every
`orgs/...` path, `orgs/lessons/` included, resolves against it.
