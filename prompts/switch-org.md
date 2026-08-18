# Switch / Connect Org (shared fragment)

Read + followed inline by `/scout-sparring` and `/scout-building` when the SE
has no connected org, or wants to change orgs, at the startup org-check. It
replaces the former standalone `/scout-switch-org` command.

**No Claude Code restart required.** Every `@salesforce/mcp` DX tool takes
`usernameOrAlias` as a per-call parameter — the MCP server resolves the org on
each call, so a switched org is reachable immediately by passing its alias.
Restart is a LAST resort, only for the narrow case where the running MCP server
will not pick up a mid-session change to the *default* org (per-call alias
targeting still works in that case — see Step 4).

**Two config scopes — set both.** `sf` resolves the default org from a *local*
`.sf/config.json` (the directory the CLI runs in) when present, else from the
*global* `~/.sf/config.json`. Scout's commands `cd` into the workspace, so they
read the local file — but a fresh Claude Code window opens with cwd at `$HOME`
and reads the global file. `sf config set target-org` with no flag writes LOCAL
only, so a switch that sticks inside Scout can be invisible to a fresh window.
Step 3 therefore writes BOTH scopes so they can never disagree.

The parent command has already run `workspace-bootstrap.md` (cwd is
`~/claude-projects/sf-demo-scout`). Do NOT re-cd or re-check config here.

## Step 1: List connected orgs

```bash
sf org list --json
```

Present the connected orgs clearly — alias + username per row — then:

> "Pick an org from the list, or type **new** to connect a different one."

## Step 2: SE picks

- **Existing org** (SE names one already in the list) → skip to Step 3.
- **new** (or an org not in the list) → ask for an alias, then:
  > "Is this a **sandbox** or a **production/developer** org?"

  Then tell the SE:
  > "I'll open a browser now — log in with your demo org credentials."

  Run the matching command in the FOREGROUND (wait for it to return before
  continuing):
  - **Production / Developer org** (default `login.salesforce.com`):
    ```
    sf org login web --alias [name] --set-default
    ```
  - **Sandbox** (authenticates against `test.salesforce.com`):
    ```
    sf org login web --alias [name] --set-default --instance-url https://test.salesforce.com
    ```
  Wait for success, then continue to Step 3.

## Step 3: Set the chosen org as the default — BOTH scopes

```
sf config set target-org [chosen-alias]            # local: workspace + Scout commands
sf config set target-org [chosen-alias] --global   # global: fresh windows (cwd at $HOME)
```
The first writes `.sf/config.json` in the project (local scope, read when cwd is
inside the workspace). The second writes `~/.sf/config.json` (global scope, read by
a fresh Claude Code window that opens at `$HOME`). Write BOTH — a local-only write
sticks inside Scout but is invisible to a fresh window, and a global-only write is
overridden by any stale local value. `sf org login web --set-default` writes LOCAL
only for a `new` org, so the explicit `--global` above is still required in that case.

Then read the org details:
```
sf org display --target-org [chosen-alias] --json
```
Extract: **Alias** (`[chosen-alias]`), **Username** (`username`), **Org ID**
(`id`), **Instance URL** (`instanceUrl`).

## Step 4: Verify connectivity, then return

Confirm BOTH scopes resolve the new org. Check the global scope from a neutral cwd
(this is the fresh-window path — the one that silently diverged before):
```
( cd "$HOME" && sf config get target-org --json )
```
It must report `[chosen-alias]`. If it does, a fresh Claude Code window will
resolve the new org regardless of where it opens, and the switch is live for
every CLI call and for every MCP call that passes `[chosen-alias]` as
`usernameOrAlias` (which the audit/deploy sub-agents do).

**Optional MCP default-resolution check (only if the parent will rely on MCP
default resolution rather than passing the alias explicitly):** the running MCP
server can lag on a mid-session change to the *default* org. Downstream Scout
calls pass the alias explicitly, so this rarely matters — but if a later MCP
call returns the wrong org's data, that lag is why. The fix is to pass
`[chosen-alias]` per call (preferred), and only as a LAST resort exit + restart
Claude Code (Cmd+Q in VS Code, not just a new tab) to reload the MCP server.
Do NOT present restart as the default step.

## Return to parent

Return control to the parent command with the active org identity
(alias / username / Org ID / instance URL). The parent re-derives its org
context (folder slug, etc.) from the new alias and continues — no new session.
