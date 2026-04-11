Switch to a different Salesforce demo org. Follow these steps:

1. Run `sf org list` to show all available orgs
2. Ask the SE which org they want to use (show the list clearly with aliases and usernames)
3. Once they choose, run:
   - `sf config set target-org [chosen-alias] --global`
4. Run `sf org display --target-org [chosen-alias] --json` to get the org details
5. Extract:
   - Alias: [chosen-alias]
   - Username: from the `username` field
   - Org ID short: first 6 characters of the 18-char `id` field
   - Instance URL: from the `instanceUrl` field
6. Update the `## Org` section in CLAUDE.md with the new alias, username, org ID, and instance URL.
   Note: CLAUDE.md is documentation only — all slash commands read org identity from
   `sf config get target-org` at runtime. This update is for human reference.
7. Check for an existing org folder:
   - Folder path: `orgs/[chosen-alias]-[ORG_ID_SHORT]/`
   - If it exists: list available audits and tell the SE:
     "Org folder found for [alias] with [N] audit(s). Most recent: audit-[DATE].md ([N] days old).
     Run /scout-sparring to use this audit or run a fresh one."
   - If it does not exist: create it now:
     ```bash
     mkdir -p orgs/[chosen-alias]-[ORG_ID_SHORT]/
     ```
     Tell the SE: "New org folder created. Run /scout-sparring to audit this org before building."
8. Confirm the switch is complete:
   "Org switched to [alias] ([username]). Run /scout-sparring to start sparring against this org."

If the desired org isn't in the list, offer:
   `sf org login web --alias [name] --set-default`
Then wait for the SE to complete the browser login before continuing.