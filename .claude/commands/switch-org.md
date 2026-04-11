Switch to a different Salesforce demo org. Follow these steps:

1. Run `sf org list` to show all available orgs
2. Ask the SE which org they want to use (show the list clearly with aliases and usernames)
3. Once they choose, run:
   - `sf config set target-org [chosen-alias] --global`
4. Run `sf org display --target-org [chosen-alias]` to get the org details
5. Update the `## Org` section in CLAUDE.md with the new:
   - Alias
   - Username
   - Org ID (the `Id` field)
   - Instance URL (the `InstanceUrl` field)
6. Update the `--target-org` references in the Companion Permission Set section of CLAUDE.md
7. Confirm the switch is complete and suggest re-running the org audit:
   "Org switched to [alias]. Your org audit may be stale — run `/demo-scout` or ask me to audit the new org."

If the desired org isn't in the list, offer:
   `sf org login web --alias [name] --set-default`
Then wait for the SE to complete the browser login before continuing.
