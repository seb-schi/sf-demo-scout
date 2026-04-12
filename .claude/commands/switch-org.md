Switch to a different Salesforce demo org. Follow these steps:

1. Run `sf org list` to show all available orgs
2. Ask the SE which org they want to use (show the list clearly with aliases and usernames)
3. If the desired org is already in the list, skip to step 5.
   If not, tell the SE:
   > "I'll open a browser now — log in with your demo org credentials."
   Then run (in the foreground — wait for it to complete before continuing):
   ```
   sf org login web --alias [name] --set-default
   ```
   Wait for the command to return successfully before proceeding.

4. Set the chosen org as default:
   ```
   sf config set target-org [chosen-alias] --global
   ```

5. Get the org details:
   ```
   sf org display --target-org [chosen-alias] --json
   ```
   Extract:
   - Alias: [chosen-alias]
   - Username: from the `username` field
   - Org ID (18-char): from the `id` field
   - Org ID short: characters 10–14 of the 18-char org ID (5 chars, e.g. "P6teY" from "00DgL00000P6teYUAR")
   - Instance URL: from the `instanceUrl` field

6. Update the `## Org` section in CLAUDE.md with the new alias, username, org ID, and instance URL.
   Note: CLAUDE.md is documentation only — all slash commands read org identity from
   `sf config get target-org` at runtime. This update is for human reference.

7. Check for an existing org folder:
   - Folder path: `orgs/[chosen-alias]-[ORG_ID_SHORT]/`
   - If it exists: list available audits and tell the SE:
     "Org folder found for [alias] with [N] audit(s). Most recent: audit-[DATE].md ([N] days old).
     Run /scout-sparring to use this audit or run a fresh one."
   - If it does not exist: create it:
     ```
     mkdir -p orgs/[chosen-alias]-[ORG_ID_SHORT]/
     ```
     Tell the SE: "New org folder created. Run /scout-sparring to audit this org before building."

8. Confirm the switch:
   > "Switched to [alias] ([username]). Run /scout-sparring to start sparring against this org."