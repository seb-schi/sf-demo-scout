---
name: switch-org
description: >
  Switch to a different Salesforce demo org.
model: sonnet
allowed-tools: Bash, Read, mcp__Salesforce_DX__run_soql_query
---

Switch to a different Salesforce demo org. Follow these steps:

1. Run `sf org list` to show all available orgs
2. Ask the SE which org they want to use (show the list clearly with aliases and usernames). After the list, add:
   > "Pick an org from the list, or type **new** to connect a different org."
3. If the SE picks an existing org, skip to step 5.
   If the SE types "new" or names an org not in the list, ask for an alias, then:
   > "I'll open a browser now — log in with your demo org credentials."
   Then run (in the foreground — wait for it to complete before continuing):
   ```
   sf org login web --alias [name] --set-default
   ```
   Wait for the command to return successfully before proceeding.

4. Set the chosen org as default for this project (writes to `.sf/config.json` in the project — local scope takes precedence over global, so this is what MCP actually reads):
   ```
   sf config set target-org [chosen-alias]
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

6. Check for existing org folders:
   ```
   ls -d orgs/[chosen-alias]-*/ 2>/dev/null
   ```
   - If folders exist: list them and tell the SE:
     "Found existing customer folder(s) for [alias]: [list]. Run /scout-sparring to continue with one of these or start a new customer."
   - If no folders exist: tell the SE:
     "No customer folders for this org yet. Run /scout-sparring — it will create one when you name the customer."

7. Verify MCP connectivity against the new org:

   Call `run_soql_query` with: `SELECT Id, Name FROM Organization LIMIT 1`

   - If the returned Id matches the Org ID from step 5 → MCP is already pointing to the new org:
     > "Switched to [alias] ([username]). MCP verified — ready to go.
     > Run /scout-sparring to start sparring against this org."
   - If the returned Id does NOT match → MCP is still on the old org:
     > "Switched to [alias] ([username]).
     > ⚠️ MCP is still connected to the previous org. Restart VS Code now (CMD+Q) — the MCP server only picks up org changes on startup.
     > Once restarted, run /scout-sparring to start sparring against this org."
   - If MCP fails or times out:
     > "Switched to [alias] ([username]).
     > ⚠️ MCP is not responding. Restart VS Code now (CMD+Q) to initialize the MCP connection.
     > Once restarted, run /scout-sparring to start sparring against this org."
