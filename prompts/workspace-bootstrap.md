# Workspace Bootstrap

Shared fragment Read by `/scout-sparring` and `/scout-building` as their first step. Single read-only Bash gate — two explicit outcomes — one tool call.

## Step 1: Sanity gate

Apply `prompts/host-runtime.md`; substitute `[SCOUT_HOST]` with the active
`claude` or `codex` host. Unknown host is a check failure, not a Claude fallback.
Resolve `${CLAUDE_PLUGIN_ROOT}` to the absolute active Scout plugin directory,
then run this whole fence as written with that literal path substituted. The
quoted heredoc makes the check use `/bin/bash` even when the parent tool shell is
zsh. This gate is read-only: it never creates the workspace or configuration.

```bash
/bin/bash <<'SCOUT_WORKSPACE_BOOTSTRAP_BASH'
WORKSPACE="$HOME/claude-projects/sf-demo-scout"
CONFIG="$HOME/.config/sf-demo-scout/config.json"
WORKSPACE_HELPER="[PLUGIN_ROOT]/scripts/setup-workspace.py"
PYTHON_EXE=$(type -P python3 2>/dev/null || true)

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
  echo "STATE=OK"
  exit 0
fi
echo "STATE=CHECK_FAILED"
echo "Scout workspace verifier failed with exit $VERIFY_STATUS; its diagnostic output is above." >&2
exit "$VERIFY_STATUS"
SCOUT_WORKSPACE_BOOTSTRAP_BASH
```

Branch on output:

- `STATE=OK` → silent. Return control to the parent command's next step.

- `STATE=CHECK_FAILED`, any nonzero exit, or missing `STATE=OK` success evidence →
  ABORT and surface the verifier's complete stdout/stderr and the gate diagnostic.
  Suggest `/scout-setup` when the preserved verifier output identifies missing or
  invalid workspace artifacts (`WORKSPACE_INVALID`, `SFDX_PROJECT_INVALID`,
  `FORCE_APP_INVALID`, `LESSONS_INVALID`, `SETTINGS_INVALID`, or `CONFIG_INVALID`).
  For a missing interpreter/helper, permission error, or invocation failure, report
  that exact reason without claiming Scout is a fresh install.

Do not proceed past this step on the failure state, a nonzero exit, or absent
success evidence.

## After bootstrap

Do not rely on shell working-directory state persisting between tool calls. The
parent command must set `$HOME/claude-projects/sf-demo-scout` as the working
directory for each subsequent shell call, or begin that call with a checked
`cd` to the workspace. All subsequent `orgs/...` refs (including
`orgs/lessons/`) resolve against that explicit working directory.
