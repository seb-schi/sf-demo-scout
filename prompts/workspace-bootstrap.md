# Workspace Bootstrap

Read by `/scout` as its first step: one read-only gate with two outcomes.

## Step 1: Sanity gate

Substitute `[SCOUT_HOST]` (`claude`, `codex` or `cursor`, per `prompts/host-runtime.md`; an
unknown host is a check failure, not a Claude fallback) and the resolved absolute
plugin root for `[PLUGIN_ROOT]`, then run this one command with the host contract's
`[PYTHON]` in place of `python3`. It runs the same in any shell. The gate never
creates the workspace or its configuration.

```bash
python3 -B "[PLUGIN_ROOT]/scripts/setup-workspace.py" gate --host "[SCOUT_HOST]"
```

If Python or the helper can't start, that's `STATE=CHECK_FAILED` with that reason.

- `STATE=OK`: say nothing, and return to the command's next step.
- `STATE=CHECK_FAILED`, any nonzero exit, or no `STATE=OK`: show the verifier's
  complete output and the gate's diagnostic. When that output names
  `WORKSPACE_INVALID`, `SFDX_PROJECT_INVALID`, `FORCE_APP_INVALID`,
  `LESSONS_INVALID`, `SETTINGS_INVALID` or `CONFIG_INVALID`, Scout repairs
  itself: say so in one line, run `/scout-setup self-repair` once (the
  `sf-demo-scout:scout-setup` skill, or `[PLUGIN_ROOT]/skills/scout-setup/SKILL.md`),
  then rerun this gate. Otherwise, or if it still fails, stop. For a missing
  interpreter or helper, a permission error or an invocation failure, report
  that exact reason without calling it a fresh install.

## After bootstrap

The shell's working folder doesn't persist between tool calls: run each later
call in the printed `WORKSPACE`, or start it with a checked `cd` there. Every
`orgs/...` path, `orgs/lessons/` included, resolves against it.
