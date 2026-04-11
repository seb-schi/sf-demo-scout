# SF Demo Scout

A Claude Code pipeline for configuring Salesforce demo orgs from customer discovery notes.
Two phases: **sparring** (Opus 4.6) develops the scenario and spec, **building** (Sonnet 4.6) deploys it.

## Setup

Complete the [Embark + AWS Bedrock setup guide] first, then:

```bash
curl -o ~/.claude/commands/setup-demo-scout.md \
  https://raw.githubusercontent.com/seb-schi/sf-demo-scout/main/setup-demo-scout.md
```

Then: `claude` → `/setup-demo-scout`

## Commands

| Command | Model | What it does |
|---|---|---|
| `/setup-demo-scout` | — | One-time setup: connects org, runs first audit |
| `/scout-sparring` | Opus 4.6 | Discovery sparring + spec generation |
| `/scout-building` | Sonnet 4.6 | Deploys spec to org, writes change log |
| `/switch-org` | — | Switch active demo org |

## File layout

```
orgs/
  [alias]-[ORG_ID]/
    audit-[DATE].md          ← org state snapshots
    changes-[DATE]-[CUSTOMER].md  ← deployment change logs
demo-spec-[CUSTOMER]-[DATE].md   ← generated specs (project root)
```

## Questions

Reach out to @Sebastian Schickhoff.
