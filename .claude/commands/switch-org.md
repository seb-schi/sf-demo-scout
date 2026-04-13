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
   - Instance URL: from the `instanceUrl` field

6. Update the `## Org` section in CLAUDE.md with the new alias, username, org ID, and instance URL.
   Note: CLAUDE.md is documentation only — all slash commands read org identity from
   `sf config get target-org` at runtime. This update is for human reference.

7. Check for existing org folders:
   ```
   ls -d orgs/[chosen-alias]-*/ 2>/dev/null
   ```
   - If folders exist: list them and tell the SE:
     "Found existing customer folder(s) for [alias]: [list]. Run /scout-sparring to continue with one of these or start a new customer."
   - If no folders exist: tell the SE:
     "No customer folders for this org yet. Run /scout-sparring — it will create one when you name the customer."

8. Confirm the switch:
   > "Switched to [alias] ([username]).
   > ⚠️ Restart VS Code now (CMD+Q) — the MCP server only picks up org changes on startup.
   > Once restarted, run /scout-sparring to start sparring against this org."