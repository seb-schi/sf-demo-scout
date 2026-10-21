# Active host contract

Apply this before Scout setup, discovery, builds, repairs, or tool calls.

- Identify the active host from the current session: `claude` (`CLAUDECODE=1`),
  `codex` (`CODEX_THREAD_ID` is set), `cursor` (`CURSOR_AGENT` is set), otherwise
  what the session itself says it runs in, else `unknown`. The presence of a CLI on
  PATH does not identify the host. Set the logical `SCOUT_HOST` value and substitute
  it into each `[SCOUT_HOST]` argument; shell variables and working directories do
  not persist between tool calls. If the host is unknown, perform only host-neutral
  work; do not edit a host's settings or run another host's setup as a fallback.
- Resolve `PLUGIN_ROOT_ABS`, Scout's root, once. On Claude it is
  `${CLAUDE_PLUGIN_ROOT}` as filled in. On Codex and Cursor it is the folder two
  levels above the entry skill you loaded (`<root>/skills/scout/SKILL.md`), or the
  folder a thin user skill names. It holds `.claude-plugin/plugin.json`. Throughout
  Scout's own files, `${CLAUDE_PLUGIN_ROOT}`, `[PLUGIN_ROOT_ABS]` and `[PLUGIN_ROOT]`
  mean this resolved root, including in migrated commands; inside an official skill
  read from a clone, the token means that skill's own plugin folder. Substitute a concrete absolute path
  before calling a shell or delegating. Do not read another host's installed-plugin
  registry or guess a cached version. Missing source context is an explicit
  unavailable result.
- Resolve `[PYTHON]` once, too: the first of `python3`, `python` and `py -3` whose
  `--version` reports Python 3.9 or later. On Windows the order is `py -3`, `python`,
  `python3`: `py` is Python's own launcher, even in a `WindowsApps` folder, but skip a
  `python` or `python3` that resolves into one, where the Microsoft Store's install
  stubs live. On Windows, run each probe with `PYTHON_MANAGER_AUTOMATIC_INSTALL` set to
  `false` for that command, so a probe never installs a runtime (PowerShell:
  `$env:PYTHON_MANAGER_AUTOMATIC_INSTALL='false'; py -3 --version`; Git Bash:
  `PYTHON_MANAGER_AUTOMATIC_INSTALL=false py -3 --version`). Wherever Scout's text runs
  `python3`, run `[PYTHON]`. When none qualifies, say Python 3.9 or later is needed, name
  the install command for the OS (on Windows `winget install --exact --id
  Python.PythonInstallManager`, then `pymanager install default`), and stop before any helper call.
- Scout's fences are one command each wherever they run outside Claude. Values a
  fence writes as `$NAME`, `{{NAME}}` or `[NAME]` are placeholders: substitute them
  before running it, since on Windows the shell may be PowerShell or `cmd.exe`.
- In Git Bash on Windows (Claude Code's shell there), an argument that starts with `/`
  is rewritten into a Windows path before the command sees it, which breaks Salesforce
  URL paths such as `/lightning/...`. Put `MSYS_NO_PATHCONV=1` in front of such a
  command, that command only; never in PowerShell or `cmd.exe`.
- On Windows, `sf` is a batch launcher. When its folder has a space (the Windows
  installer's `C:\Program Files\sf`, or npm's under a user folder with a space), cmd.exe
  can cut that path at the space if another argument is quoted: the call fails with
  `'C:\Program' is not recognized`. Rerun it with the argv that `[PYTHON]
  "[PLUGIN_ROOT_ABS]/scripts/scout_sf_argv.py"` prints, the CLI Scout's own helpers run,
  and the same arguments; when it can't resolve one, say so and stop that call. For the installer's copy, say once that npm's usually avoids
  this: uninstall **Salesforce CLI** in Settings → Apps, then
  `npm.cmd install --global @salesforce/cli` in PowerShell.
- On Windows, Salesforce's official skills run bash scripts and `jq`. Check both once
  per session, before setup's official-skills step and before a build's first deploy
  through an official skill: `jq --version` must report 1.7 or later, and `bash` must
  be Git for Windows' (`Get-Command bash` in PowerShell, where
  `C:\Windows\System32\bash.exe` is WSL's). When Git Bash is installed but `bash`
  finds another, run a skill's scripts with Git Bash's full path
  (`C:\Program Files\Git\bin\bash.exe`). When a tool is missing, name its install
  line (`winget install --exact --id jqlang.jq`, `winget install --exact --id Git.Git`)
  and follow `prompts/building/official-skill-overrides.md` §Hosts.
- If a Scout file goes missing mid-task (an update can replace the plugin folder
  under a running session), stop, keep progress in the task record, and tell the builder
  to start a new session; never rebuild a helper or prompt from memory. On Codex, a
  restart of the app loads an update; a new chat alone keeps the version it has.
- Claude-specific `allowed-tools` and `mcp__plugin_...`/`mcp__...` names are
  Claude permission references, not portable callable identifiers. Discover the
  actual tools exposed by this session. Resolve each required operation against
  the published tool description and input schema; never manufacture a prefix
  or assume a different connector has the same arguments or write scope.
- Use `prompts/mcp-readiness.md` at the first provider-dependent operation.
  Existing org-selection, user-approval, and read/write boundaries still apply.
  Do org work with the `sf` CLI, always with the explicitly selected org. Do not
  replace a policy-blocked MCP registration.
- Scout's entry points are `/scout` and `/scout-setup` on Claude and Cursor; on Codex
  they're `$sf-demo-scout:scout` and `$sf-demo-scout:scout-setup`. Name them that
  way when you tell a Codex user to run one.
- Questions: on Claude use `AskUserQuestion`; on Codex and Cursor, ask in plain text
  with numbered options, and accept the builder's number or words.
- Long waits: on Claude, run them in the background and let the session wake; on
  Codex and Cursor, run them in the foreground and relay the helpers' progress lines.
- `/model` notices and `Agent(...)` examples apply to Claude. On Codex and Cursor use
  the host's own delegation tools and inherited model settings, with the same task
  boundaries and result contracts; working alone stays the default. Pass the host,
  resolved root, selected org, and discovered tool contracts to workers. Never
  instruct a Codex or Cursor user to switch to an unavailable Claude model.
- Reloads: on Claude, `/reload-plugins` or a new session; on Codex, a new chat, and a
  restart of the app to fetch an update; on Cursor, a new chat or Reload Window.
- Install, update or remove plugins only with the host's own commands (on Claude Code,
  `claude plugin …` in a terminal, since the desktop app doesn't run `/plugin`) or
  `/scout-setup`; never write a host's plugin registry or marketplace files yourself.
- When a host's sandbox or policy refuses a call, name the access the call needed
  (network to the org, or the Salesforce CLI's files in `~/.sf` and `~/.config`) and
  the host's own approval path. Tell a sandbox limit from a policy denial, and never
  retry around a refusal.
- Claude setup steps (the running-client and model-routing reports, and Claude
  marketplace auto-update) apply only to Claude. Codex and Cursor configuration and
  policy stay under their own host controls.

## Worker model mirroring

Before every Claude worker dispatch, set the per-call `model` to the alias of
this orchestrator's own model family. The session's version pins its matching
alias, so this mirrors the session instead of the host's default worker model.
If this session cannot identify its own family, omit `model`; do not guess.
The user's `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` can override this choice.
Apply this on initial calls and every redispatch. Codex and Cursor keep the
inherited model behavior described above.
