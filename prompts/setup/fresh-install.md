# Scout Setup — Fresh Install

End-to-end install procedure. Run on `STATE=FRESH`.

Apply `prompts/host-runtime.md`. On Codex and Cursor, run the shared
prerequisite and Salesforce workspace steps a, b and d–f, then
`${CLAUDE_PLUGIN_ROOT}/prompts/setup/other-hosts.md` in place of g.6 and h.7, and
config postcondition i. Skip the g steps (Claude's marketplace setting, the
running Claude client and its official plugins). Do not install or configure Claude as
a prerequisite for Codex. Substitute `[SCOUT_HOST]` in every helper call; unknown
host must return to the orchestrator before writes. In a self-repair run, ask
its one question first (`skills/scout-setup/SKILL.md`).

Setup changes nothing outside Scout's own files except what a step below names:
it never edits shell files such as `~/.zshrc`, other tools' hooks or settings,
or permission rules in `~/.claude/settings.json`.

**Idempotency contract:** every step below is idempotent and self-detecting. Re-running after an abort (e.g. after a step the SE ran in a terminal) is safe and fast — completed steps fast-no-op via their own probes (`BREW_OK`, `NODE_PRESENT`, `SETTINGS_PRESENT`, `AUTOUPDATE_ALREADY`, etc.). Always run end-to-end; do NOT skip steps trying to "resume" — the no-ops are the resume mechanism. Within the same CC session you may rely on conversation memory to fast-forward; across sessions, just run the full sequence — it will land in the right place naturally.

## a: Brew Check (hard abort if missing)

**macOS only.** On Windows and Linux, skip this step: step b names the install
commands there.

`command -v brew` misses when brew is installed but not yet on PATH (Apple
Silicon installs to `/opt/homebrew/bin`; the post-install `eval` line adds it
to PATH). So probe the known install locations before concluding it's missing —
otherwise an SE who installed brew but skipped the `eval` step gets a false
`BREW_MISSING` and dead-ends.

```bash
if command -v brew >/dev/null 2>&1; then
  echo "BREW_OK"
elif [ -x /opt/homebrew/bin/brew ]; then
  echo "BREW_NOT_ON_PATH /opt/homebrew/bin/brew"
elif [ -x /usr/local/bin/brew ]; then
  echo "BREW_NOT_ON_PATH /usr/local/bin/brew"
else
  echo "BREW_MISSING"
fi
```

If `BREW_NOT_ON_PATH <path>`, brew is installed but this shell can't see it.
Report it as installed but not on PATH. ABORT and emit (substitute the `<path>`
dir from the probe output — `/opt/homebrew/bin` or `/usr/local/bin`):

> ⚠️ **Homebrew is installed but not on your PATH yet** — one line fixes it.
>
> Run this, then re-run `/scout-setup`:
> ```
> eval "$(<path>/brew shellenv)"
> ```
> To make it stick for new shells, add that same line to your `~/.zprofile`.

If `BREW_MISSING`, ABORT and emit:

> ⚠️ **Homebrew isn't installed — the one step Claude Code can't do for you** (the installer needs your Mac password).
>
> 1. Open a **fresh macOS Terminal**: ⌘+Space → type `Terminal` → Enter. *Not* the terminal running Claude (VS Code / desktop app / current tab) — you need a separate window at a plain `you@Mac ~ %` prompt.
> 2. Paste & run:
>    ```
>    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
>    ```
> 3. Enter your Mac password (invisible as you type — normal).
> 4. Run the `eval …` lines it prints at the end — skip these and brew won't be found.
> 5. Back in Claude Code: `/scout-setup` again.

## b: Auto-install Node, Python, sf CLI

Each tool runs through the shipped Python bootstrap independently, one command
per tool. Before each call, replace `/absolute/path/of/active/sf-demo-scout`
with this active Scout plugin installation's root, resolved from the current
plugin context to a concrete absolute path. Do not pass a literal
`${CLAUDE_PLUGIN_ROOT}`, search for another cached version, or reconstruct the
helper if it is unavailable. When Python can't open the file, the shipped
bootstrap is missing: report `NODE_UNAVAILABLE (shipped bootstrap missing)`, or
the `PYTHON_` or `SF_CLI_` form, and ABORT.
Run the Node, Python, and sf blocks below in that order, in separate shell
invocations. Inspect each exit/result before starting the next; do not batch or
run them in parallel because the sf installation may depend on npm supplied by
the preceding Node installation.

The helper probes the actual selected executable and installs only when that
executable is missing. An existing broken, malformed, unreadable, or unsupported
tool is left unchanged; Scout never installs a competing runtime over it. On
Windows it installs nothing.

```bash
python3 -B "/absolute/path/of/active/sf-demo-scout/scripts/setup_bootstrap.py" node
```

```bash
python3 -B "/absolute/path/of/active/sf-demo-scout/scripts/setup_bootstrap.py" python
```

```bash
python3 -B "/absolute/path/of/active/sf-demo-scout/scripts/setup_bootstrap.py" sf
```

For each independent call:

- `*_PRESENT` / `*_INSTALLED` — proceed. These tokens include the verified
  selected executable version.
- `*_UNVERIFIED` — ABORT. The selected executable could not be verified before
  installation, or an installer exited 0 without leaving a qualifying selected
  executable. Do not claim success or try another runtime.
- `PYTHON_UNSUPPORTED` — ABORT. Keep the existing Python unchanged and explain
  Scout requires Python 3.9+ within major 3.
- `NODE_UNSUPPORTED` — ABORT. Keep the existing Node unchanged and explain
  Scout requires Node 22.20 or later.
- `*_MISSING` (Windows) — ABORT. Scout installs nothing on Windows: give the SE
  the install command from the line in a copyable block, to run in a terminal,
  then rerun `/scout-setup`.
- `*_INSTALL_FAILED` — ABORT. Report the installer exit code and warn that a
  failed installer may have partially changed state; do not promise the old
  state survived.
- `*_UNAVAILABLE` — ABORT. Surface the named missing prerequisite or shipped
  helper/log issue. In particular, missing npm blocks sf installation even when
  Node exists.

On any nonzero helper exit, stop the fresh-install procedure. Ask the SE to
select a suitable existing executable or repair it through its own manager in a
terminal, then rerun `/scout-setup`. Suggest installation only when the tool is
missing. Never fall through to the ready/Done handoff.

## d–f: Verified Workspace, SFDX Scaffold, Lessons, Settings, and Config

Read `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json` and extract its
`version` field as a string for `[PLUGIN_VERSION]`. Resolve
`${CLAUDE_PLUGIN_ROOT}` to its absolute active plugin directory for
`[PLUGIN_ROOT]`; neither placeholder is a shell expression.

Run the shipped helper once, with the host contract's `[PYTHON]` in place of
`python3`. It runs the same in any shell; the workspace and configuration paths
are its defaults, `~/claude-projects/sf-demo-scout` and
`~/.config/sf-demo-scout/config.json`.

```bash
python3 -B "[PLUGIN_ROOT]/scripts/setup-workspace.py" setup --template "[PLUGIN_ROOT]/assets/workspace-settings.template.json" --plugin-version "[PLUGIN_VERSION]" --host "[SCOUT_HOST]"
```

If Python or the helper can't start, report `WORKSPACE_SETUP_FAILED` with that
reason, and ABORT.

The helper stages `sf project generate --json` in a unique temporary
directory and accepts it only when the process exits zero, the JSON reports
integer status `0`, and the generated SFDX artifacts validate. It preserves
incumbent `force-app`, lessons, settings, and valid config files. New JSON and
text files use same-directory atomic replacement; config is created only after
the SFDX project, `force-app`, and lessons validate (plus workspace settings
on Claude; Codex neither requires nor changes those files).

On any nonzero helper exit, surface its outcome token and ABORT. Do not run
the later steps or Done. `WORKSPACE_READY` is the only success token.

## g.8: Report the running client and model routing (read-only)

On Claude, report the running client with
`SCOUT_HOST=claude python3 -B "[PLUGIN_ROOT]/scripts/client-version.py" setup`,
using the resolved active plugin root. Carry its version or unverified reason
and any floor notice into the setup message; it never updates the client.

Then run the read-only model-routing report:

```bash
SCOUT_HOST=claude python3 -B "[PLUGIN_ROOT]/scripts/setup-model-report.py"
```

It reads settings files, the session environment, literal `.zshrc` assignments,
VS Code and launchctl values, and changes none of them. Managed policy supplied through MDM, a server or an
embedding API may not be visible to it, so it doesn't certify effective routing.
Carry each reported older model's source and its provider-specific fix into the
closing message verbatim; don't invent model IDs. Unknown or deployment-name
values are unassessed.

## g.5: Turn on marketplace autoUpdate when the SE hasn't chosen

Fresh-install SEs add the Scout marketplace via `/plugin marketplace add` BEFORE running `/scout-setup`, so CC writes the `extraKnownMarketplaces.scout` entry without `autoUpdate`. This step turns it on only when the entry has no `autoUpdate` at all. An explicit `autoUpdate: false` is the SE's choice and stays as it is. Idempotent, safe-fail.

```bash
python3 -B "[PLUGIN_ROOT]/scripts/setup-settings.py" marketplace-autoupdate --name scout --settings "$HOME/.claude/settings.json"
```

Surface inline:
- `AUTOUPDATE_ALREADY[…]` — silent.
- `AUTOUPDATE_SET[…]` — "Enabled auto-updates for Scout marketplace — future versions will install automatically on session start."
- `AUTOUPDATE_LEFT_AS_CHOSEN[…]` — one line: "Scout's marketplace has auto-update switched off, as you set it; turn it on under `/plugin` → Marketplaces if you want updates to arrive on their own."
- `AUTOUPDATE_ABSENT[…]` / `AUTOUPDATE_NO_ENTRY[…]` — silent (the marketplace add step writes these; absence means setup is being run in an unexpected state, not Scout's problem).
- Any other `AUTOUPDATE_…` line — one-line note, proceed.

## g.6: Salesforce's official plugins

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/official-plugins.md` and execute it. Carry its non-silent lines into the done summary.

## h.7: Salesforce Docs MCP

Read `${CLAUDE_PLUGIN_ROOT}/prompts/setup/salesforce-docs-mcp.md` and execute it. Preserve existing registrations and report observed status; when none is observed, offer the Agentforce Labs Salesforce Docs MCP and register it only on the SE's yes. Required Docs tools are checked when needed. Return and continue setup.

Scout registers no other connection. Slack, Google Drive and similar tools come from the SE's own host connectors, if any; the closing message carries the heads-up note about them (`done.md`).

## i: Config Postcondition

Config creation and validation completed in step d–f after every mandatory
workspace artifact validated. Do not rewrite it here. If step d–f did not emit
`WORKSPACE_READY`, this procedure already aborted and must not reach this step.

## Done

Fresh-install procedure complete. Return to the orchestrator with every outcome line the steps above printed, so the done message can report them.
