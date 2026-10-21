---
name: scout-setup
description: >
  One-stop install, refresh, and repair for Scout. Use when the SE asks to set up or update Scout, or when
  Scout's own checks report its setup broken (self-repair). Idempotent — safe to re-run any time.
argument-hint: "[self-repair]"
allowed-tools: Read, Write, Edit, Bash
---

# Scout Setup — Install, Refresh, Repair

You are the setup orchestrator. This skill is idempotent and state-driven: detect what needs doing, dispatch to the matching prompt, then hand off to the done prompt. Each state's procedure is in its own file so this command stays small and reliable. Read each prompt fully and execute its procedure end-to-end before returning here.

Run each bash fence in this command and every setup prompt it dispatches in its own Bash call, exactly as written once placeholders are substituted. Keep any `/bin/bash <<'…'` wrapper; don't merge fences or retype their bodies, because the tool shell may be zsh.

## Self-repair runs

Scout runs this command itself, with the argument `self-repair`, when one of its checks finds its setup broken; this run's arguments are the text sent with it (on Claude Code, the `ARGUMENTS:` line). A self-repair run fixes Scout's workspace files and installs Salesforce's official plugins without asking, and says so in one line. Before its first step, it asks the SE one question, in plain words, about the steps below, which change the SE's machine:
- the Salesforce CLI and its tools: fresh install `b`, refresh `a`, and `sf plugins update` in the official-plugins step (fresh install `g.6`, refresh `b.5`)
- Scout's marketplace auto-update setting in Claude's settings: fresh install `g.5`, which only fills in a missing setting
- turning back on, or installing, a Salesforce plugin that's switched off or missing while Salesforce's marketplace is set up, which may be the SE's choice

On a yes, run the procedure as usual. On a no, skip those steps, and fresh install `a` too, since the Homebrew check only serves `b`'s installs; add `--keep-se-choices` to the official-plugins helper, which leaves such plugins as they are and names each in an `OFFICIAL_PLUGIN_LEFT` line. Read-only reports run either way, such as the running-client and model-routing reports. Name each skipped step and left plugin in the closing message, with `/scout-setup` to run them any time, and carry on. A `/scout-setup` the SE runs themselves asks nothing extra.

## Step 1: Detect State

Read `${CLAUDE_PLUGIN_ROOT}/prompts/host-runtime.md` first and apply its active-host contract throughout this command and all worker handoffs. Resolve the root from the current plugin context before expanding this path.

If the active host is unknown, report it and stop before setup writes.
Substitute `[SCOUT_HOST]` with `claude`, `codex` or `cursor` in each shell call, and
the absolute active Scout plugin directory for `[PLUGIN_ROOT]`. Then run this one
command with the host contract's `[PYTHON]` in place of `python3`; it runs the same
in any shell, and creates the workspace folder if it's missing:

```bash
python3 -B "[PLUGIN_ROOT]/scripts/setup-workspace.py" state --host "[SCOUT_HOST]"
```

When no Python 3.9 or later can start at all, the state is `STATE=FRESH`: the fresh
install provides Python first. `SETUP_ABORTED` is an abort, never a setup state.

Capture the STATE value — Step 3 (Done) needs it. Preserve and surface any verifier
diagnostic printed before the state instead of replacing it with a generic reason.
`STATE=FRESH` includes an
interrupted or partial install even when `config.json` exists; the fresh path
is idempotent and repairs missing mandatory artifacts without replacing valid
incumbent workspace files or config.

## Step 2: Dispatch

Branch on STATE:

- `STATE=FRESH` → Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/fresh-install.md` and execute its procedure end-to-end.
- `STATE=REFRESH` → Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/refresh.md` and execute its procedure end-to-end.

Both `fresh-install.md` and `refresh.md` end by returning the outcome lines their steps printed. Capture them — Step 3 needs them.

If the dispatched prompt aborts (e.g. brew missing or pyyaml missing), STOP. Do NOT proceed to Step 3. The abort messages already tell the SE what to do next. The optional Docs check returns with its observed status; an unavailable check or pending connection does not abort setup.

## Step 3: Done

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/done.md` and execute it. Pass the captured `STATE`, all CLI and report outcome tokens and the Docs MCP status note so the closing message preserves unresolved checks and connections.
