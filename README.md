# SF Demo Scout — Plugin

Claude Code plugin for Salesforce demo preparation: sparring, audit, deployment for SE demo orgs.

> **Status: Phase B scaffold.** This repo contains only the manifest skeleton. Commands, skills, and prompts are still maintained in [`seb-schi/sf-demo-scout`](https://github.com/seb-schi/sf-demo-scout) and will be ported in Phase C.

## Install (preview — not yet functional)

```
/plugin marketplace add https://github.com/seb-schi/sf-demo-scout-plugin.git
/plugin install sf-demo-scout@scout
```

> Use the explicit `.git` HTTPS URL above. The shorthand
> `/plugin marketplace add seb-schi/sf-demo-scout-plugin` will fail on
> machines without a GitHub SSH host key (most fresh installs).

The plugin loads but the command palette is empty until Phase C.

## Local development

```
claude --plugin-dir ~/claude-projects/sf-demo-scout-plugin
```

## Migration roadmap

See [`pipeline-changes/plugin-migration-roadmap.md`](https://github.com/seb-schi/sf-demo-scout/blob/main/pipeline-changes/plugin-migration-roadmap.md) in the parent repo.

## License

MIT — see [LICENSE](./LICENSE).
