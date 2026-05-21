# SF Demo Scout

> **Repository migrated.** SF Demo Scout is now distributed as a
> Claude Code plugin. The clone-install path served by this repo is
> retired — files in this branch are migration shims only.

## Install Scout (current method)

Inside Claude Code, run:

```
/plugin marketplace add https://github.com/seb-schi/sf-demo-scout-plugin.git
/plugin install sf-demo-scout@scout
```

Restart Claude Code, then run `/scout-sparring` or `/scout-switch-org`.
The plugin's first-run bootstrap handles workspace setup automatically.

## Migrating from clone-install

If you previously installed Scout via `git clone` or the curl
bootstrap, you have a clone-install workspace at
`~/claude-projects/sf-demo-scout/`. Two ways to migrate:

1. **Run `update.sh` one last time** (any pre-cached version on
   your disk works). This re-fetches this branch and prints a
   migration notice. Then follow the plugin install steps above.

2. **Just install the plugin directly** using the slash commands
   above. After it's installed, run `/setup-demo-scout` inside
   Claude Code — the migration command will clean up the old
   clone-install artifacts and hand you over to the plugin's
   commands.

Your org data at `~/claude-projects/sf-demo-scout/orgs/` is
preserved through either path.

## Archive

The full clone-install history is preserved at branch
`archive/clone-install-final` and tag `v-clone-install-final`
in this repository.

## Questions

Ping `#sf-demo-scout` on Slack.
