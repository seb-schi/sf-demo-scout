---
name: org-audit
description: >
  Format and procedure for auditing a Salesforce demo org.
  Used by /scout-sparring and /setup-demo-scout.
---

# Org Audit — Format & Procedure

Save to: `orgs/[alias]-[ORG_ID_SHORT]/audit-[YYYY-MM-DD].md`
- alias from `sf config get target-org`
- ORG_ID_SHORT = first 6 chars of 18-char org ID from `sf org display --json`

Use MCP `retrieve_metadata` for metadata and `run_soql_query` for record counts.

If MCP unavailable: "Check .mcp.json is in the project root and restart VS Code."

## Required Content

- **Custom objects** — API name, label, record count
- **Key fields and relationships** per object
- **Existing flows** — name, type, active/inactive, trigger object, brief logic summary
- **Existing LWC components** — name, purpose if inferrable
- **Existing custom permission sets** — custom only
- **Existing Agentforce agents and topics** — if any
- **Notable gaps or risks** relative to standard HLS demo scenarios