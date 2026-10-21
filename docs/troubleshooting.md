# Troubleshooting

Find the message you saw, then follow its fix. Each entry says what the message means and how to check that
it's this problem and not a look-alike. Commands are labelled with where they run: **PowerShell** (Windows),
**Terminal** (macOS), or **chat** (your Claude Code, Codex or Cursor session).

If none of these fits, open an issue on this repository with the exact message, your tool and its version,
your OS, and the step you were on.

## Installing

### "`/plugin` is a terminal-dialog command" (Claude desktop app)

The desktop app's Code tab doesn't run `/plugin`. Install from a terminal instead, then open a new session:

**PowerShell or Terminal:**

```bash
claude plugin marketplace add https://github.com/seb-schi/sf-demo-scout.git
```

```bash
claude plugin install sf-demo-scout@scout
```

**Check:** `claude plugin list` shows `sf-demo-scout@scout`.

### "'claude' is not recognized" or "command not found: claude"

The desktop app doesn't always put Claude Code's command line on the PATH. Install it as
[Anthropic's setup guide](https://code.claude.com/docs/en/setup) shows (on Windows:
`winget install Anthropic.ClaudeCode`), then open a new PowerShell or Terminal window.

### "self-signed certificate in certificate chain"

Your network inspects encrypted traffic, and Git for Windows checks certificates against its own list, not
Windows'. Adding Scout's marketplace or a `git clone` fails until Git uses Windows' certificate store:

**PowerShell:**

```powershell
git config --global http.sslBackend schannel
```

If Git then reports that it couldn't check a certificate's revocation, also run
`git config --global http.schannelCheckRevoke false`. See Git's documentation for
[`http.sslBackend`](https://git-scm.com/docs/git-config#Documentation/git-config.txt-httpsslBackend).

**Check:** `git config --get http.sslBackend` prints `schannel`.

## Windows tools

### `py install default` fails, or says the install command is unavailable

An older Python launcher answers `py` before Python's install manager does. If `py -3 --version` prints
Python 3.9 or later, you already have Python and can skip this. Otherwise, in a new PowerShell window, use the
install manager's own command, which the older launcher can't take over:

**PowerShell:**

```powershell
pymanager install default
```

**Check:** `py -3 --version` prints 3.9 or later.

### `python` opens the Microsoft Store, or `py` is not recognized

That `python` is Windows' placeholder for the Store, not a Python. Install Python's install manager
(`winget install --exact --id Python.PythonInstallManager`), open a new PowerShell window, and run
`pymanager install default`. If `py` is still not recognized, open **Manage app execution aliases** from the
Start menu and turn on the Python entries.

### "npm.ps1 cannot be loaded because running scripts is disabled on this system"

PowerShell picked npm's PowerShell script, and Windows blocks scripts by default. Type the command's `.cmd`
version instead, which isn't a script: `npm.cmd` for `npm`, `sf.cmd` for `sf`.

**PowerShell:**

```powershell
npm.cmd install --global @salesforce/cli
```

**Check:** `sf.cmd --version` prints the CLI's version. Scout's own steps aren't affected.

### A tool you just installed isn't found

Windows gives each window the PATH it had when it started. After installing Git, Python, Node, the Salesforce
CLI or jq, open a new PowerShell window, and quit and reopen your Claude, Codex or Cursor app. Then run
`/scout-setup` again.

**Check:** in a new PowerShell window, `Get-Command <tool>` finds it.

### "'C:\Program' is not recognized as an internal or external command"

Your Salesforce CLI comes from its Windows installer, under `C:\Program Files\sf`. When a command also passes a
quoted argument, such as an alias with spaces or a query, Windows' command interpreter drops the quotes around
the CLI's own path and cuts it at the space. Scout's own steps avoid this, and Scout reruns its other calls the same way. To stop it at the source, switch
to npm's copy of the CLI, which lives in `%APPDATA%\npm`: a folder without spaces, unless your Windows user name
has one:

1. Settings → Apps → Installed apps: uninstall **Salesforce CLI**. Your saved logins stay.
2. In a new PowerShell window: `npm.cmd install --global @salesforce/cli`.
3. Quit and reopen your coding tool's app.

**Check:** `where.exe sf` (PowerShell) lists a path under `AppData\Roaming\npm` first. Until you switch, give
orgs aliases without spaces.

### Scout says `bash` or `jq` is missing or wrong

Salesforce's official skills run bash scripts and `jq` 1.7 or later. On Windows, `bash` must be Git for
Windows' (`C:\Program Files\Git\bin\bash.exe`); `C:\Windows\System32\bash.exe` is WSL's and won't do.
Install what's missing (`winget install --exact --id Git.Git`, `winget install --exact --id jqlang.jq`) and
open a new window.

**Check:** `Get-Command bash` and `jq --version` in PowerShell.

## Using Scout

### `sf org login web` says "Successfully authorized" but the command failed

Scout confirms an org by binding it, not by the login command's exit code: when the binding then shows your org,
the login worked, and you can carry on.

### "Scout 2.0 is built for Opus 5.5 and later"

On Claude Code, pick Opus 5.5 in the model picker (or `/model` in a terminal session), then run `/scout`
again. Ideally set its effort to High or higher: `/effort high`, or Effort in the desktop app's model picker.
On Codex and Cursor, pick the strongest model you have, at its highest reasoning setting.

### Scout says Salesforce's official plugins aren't set up, or that two copies are switched on

**Chat:** run `/scout-setup` (on Codex, `$sf-demo-scout:scout-setup`). It installs them, or asks once before
switching the extra copy off. Then open a new session.

### "This org is read-only" or "not a demo org"

Scout writes only to demo orgs: trials (an org with an expiry date), sandboxes, scratch orgs and Developer
Editions. Anywhere else it inspects, plans and preps, but changes nothing. Use a demo org.

### Building one demo org together on Windows

Team mode runs on macOS for now, and Scout says so on Windows.
