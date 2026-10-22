# /scout when builders collaborate: two routes

Read this when the builder says they're working with others on the bound org ("I'm collaborating with … on …", "we're building this together"), and the org has neither a team (`scout_team.py context` names none) nor a string telephone (`scout_log.py status` reports `ABSENT`).

## One short message: both routes, one recommendation

- **The string telephone (light):**
  - a shared log in this org
  - nothing to install beyond Scout
  - no sandboxes, no GitHub
  - works when builders share one Salesforce user
  - advisory locks that make each Scout stop and ask

  Best for a few builders on one demo org, for days to weeks.
- **Team mode (full):**
  - each builder in their own sandbox
  - one guarded lane into the common org
  - a GitHub repository, optionally on Lifecycle Center (Salesforce's DevOps product)

  Best for longer or larger builds, and the right one for customer-facing delivery, which stays on official tech.

## What the recommendation weighs

Name these in the message, so the builder can correct them:
- **The org:**
  - a trial or demo org points to the string telephone
  - a customer's org points to team mode on Lifecycle Center
  - customer orgs never get a string telephone unless the maintainer named the org
- **What the builders have:** sandbox licences and the time to set sandboxes up; GitHub accounts.
- **How long it runs, and how many builders.**
- **Whether they share one Salesforce user:** the string telephone handles that; team mode gives each builder their own org.

Ask at most one question to settle it. Then follow the builder's pick:
- the string telephone: `${CLAUDE_PLUGIN_ROOT}/prompts/scout/string-telephone.md`, starting with eligibility, then setup
- team mode: `${CLAUDE_PLUGIN_ROOT}/prompts/scout/team.md`, or `${CLAUDE_PLUGIN_ROOT}/prompts/scout/team-lifecycle.md` for Lifecycle Center

## No switching on its own

- **A declined offer** isn't repeated on the same org in this session.
- **An existing team or string telephone** is never replaced. Mention the other route only when the builder asks.
