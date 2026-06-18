# SF Demo Scout

A Claude Code plugin for Salesforce Solutions Engineers. Scout audits
your demo org, spars with you on the scenario, and deploys the
configuration via Headless 360 — so you ship CLI-driven demos this
week instead of next quarter.

> **Full setup guide with videos and screenshots:**
> [Demo Scout Canvas](https://salesforce.enterprise.slack.com/docs/T01G0063H29/F0AQP1A7YMD)
> (internal Salesforce link)

## Install

Inside Claude Code, run these four commands in order:

```
/plugin marketplace add https://github.com/seb-schi/sf-demo-scout.git
/plugin install sf-demo-scout@scout
/reload-plugins
/scout-setup
```

When prompted on the install step, select `Install for you (user scope)`.
`/scout-setup` handles all prerequisites: Homebrew check, Node / Python /
Salesforce CLI install, SFDX scaffold, 14 community skills sync, shell
environment, and Slack MCP registration + auth.

After setup, kick off your first demo with `/scout-sparring`.

## Migrating from the clone-install version

If you installed Scout before 2026-05-23 (via `git clone` or the curl
bootstrap), run the migration trampoline one last time:

```
cd ~/claude-projects/sf-demo-scout
bash update.sh
```

This opens a fresh Claude Code window and walks you through the plugin
install — same four commands as above, plus a finishing
`/setup-demo-scout` step that migrates your workspace in place. Your
org data at `~/claude-projects/sf-demo-scout/orgs/` is preserved.

After today, you never run `update.sh` again — Claude Code pulls plugin
updates automatically in the background.

## Updates

Updates are automatic. Claude Code pulls new plugin versions on session
startup; if an update is downloaded but not yet installed, you'll see a
one-line banner suggesting `/scout-setup` to finish. To trigger
manually: `/plugin marketplace update scout`.

## Archive

The full clone-install history is preserved at branch
`archive/clone-install-final` and tag `v-clone-install-final`.

## Questions

Ping `#sf-demo-scout` on Slack.
