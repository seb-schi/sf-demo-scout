# SF Demo Scout

> **Repository migrated.** SF Demo Scout is now distributed as a
> Claude Code plugin. The clone-install path served by this repo is
> retired — files in this branch are migration shims only.

## Install Scout (current method)

Inside Claude Code, run:

```
/plugin marketplace add https://github.com/seb-schi/sf-demo-scout.git
/plugin install sf-demo-scout@scout
```

Restart Claude Code, then run `/scout-sparring` or `/scout-switch-org`.
The plugin's first-run bootstrap handles workspace setup automatically.

## Migrating from clone-install

If you previously installed Scout via `git clone` or the curl
bootstrap, run `update.sh` one last time:

```
cd ~/claude-projects/sf-demo-scout
bash update.sh
```

This re-fetches this branch, self-cleans the old clone-install
artifacts, and prints the plugin install instructions. Your org
data at `~/claude-projects/sf-demo-scout/orgs/` is preserved.

Then follow the plugin install steps above.

## Archive

The full clone-install history is preserved at branch
`archive/clone-install-final` and tag `v-clone-install-final`
in this repository.

## Questions

Ping `#sf-demo-scout` on Slack.
