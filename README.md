# SF Demo Scout — Plugin

Claude Code plugin for Salesforce demo preparation: sparring partner, org
audit, and deployment orchestration for SE demo orgs.

Three slash commands:

- `/scout-sparring` — Opus discovery sparring + spec generation
- `/scout-building` — Opus orchestrator for org deployment
- `/scout-switch-org` — change active demo org

## Prerequisites

- macOS with Homebrew installed (`brew --version` returns a version)
- LLMGW Claude Code access (the `claude` CLI you already use)
- A Salesforce demo org you can connect to via `sf` CLI

The first run of `/scout-sparring` (or any Scout command) will auto-install
Node, Python 3.9+, and the Salesforce CLI via Homebrew/npm if missing,
scaffold the workspace, and append a managed `.zshrc` block. Brew is the
only step that requires sudo and stays out-of-session.

## Install

In any Claude Code session, run:

```
/plugin marketplace add https://github.com/seb-schi/sf-demo-scout-plugin.git
/plugin install sf-demo-scout@scout
```

> Use the explicit `.git` HTTPS URL above. The shorthand
> `/plugin marketplace add seb-schi/sf-demo-scout-plugin` forces SSH and
> will fail on machines without a GitHub SSH host key (most fresh installs).

Restart Claude Code (quit fully and reopen) so the plugin's MCP servers
register.

## First run

Open a Claude Code session anywhere on your machine and run any of the
three Scout commands. The first command run triggers in-session bootstrap:

1. Workspace created at `~/claude-projects/sf-demo-scout/` (Scout is
   hard-coded to this path — do not rename or move it)
2. SFDX project scaffold (`sf project generate --template empty`)
3. Starter `sparring-lessons.md` and `building-lessons.md` files
4. Slack MCP auth check (Scout uses Slack for canvas writes during
   handover; if unauthenticated you'll see a `/mcp` instruction)
5. `~/.config/sf-demo-scout/config.json` written as the "setup done" marker
6. Managed block appended to `~/.zshrc` (5 env vars: max output tokens,
   max thinking tokens, Opus/Sonnet/Haiku model defaults). **Open a fresh
   terminal after first install** so the new env vars take effect.

Subsequent invocations skip the slow path entirely once
`~/.config/sf-demo-scout/config.json` exists.

## Connecting an org

Run `/scout-switch-org` and follow the prompts. Scout reuses any orgs
already connected via `sf org login`.

## Updating

```
/plugin marketplace update scout
```

Then relaunch Claude Code. Re-running a Scout command after an update
is idempotent — the workspace bootstrap detects existing config and
stays silent.

## Uninstall

```
/plugin uninstall sf-demo-scout@scout
/plugin marketplace remove scout
```

Workspace contents at `~/claude-projects/sf-demo-scout/` and customer
history in `orgs/` are preserved. The `.zshrc` managed block stays
until manually removed (look for `# BEGIN SF-DEMO-SCOUT` /
`# END SF-DEMO-SCOUT` markers).

## Local development

```
claude --plugin-dir ~/claude-projects/sf-demo-scout-plugin
```

## Migration roadmap

See [`pipeline-changes/plugin-migration-roadmap.md`](https://github.com/seb-schi/sf-demo-scout/blob/main/pipeline-changes/plugin-migration-roadmap.md)
in the parent repo for migration history and remaining work.

## License

MIT — see [LICENSE](./LICENSE).
