# Testing Scout on Windows

Thank you for testing. This takes about 45 minutes per host. Use a **test org you own**: a Developer Edition, a
trial or a sandbox, never a customer's org. Every sign-in is yours; Scout opens Salesforce's login page and never
asks for a password.

## Before you start

You need Windows 11 (x64), and in a PowerShell window:

1. **Git for Windows:** `git --version`. If it's missing: `winget install Git.Git`.
2. **Python 3.9 or later:** `py -3 --version`. If it's missing: `winget install Python.Python.3.12`.
3. **Node 22.20 or later:** `node --version`. If it's missing or older: `winget install OpenJS.NodeJS.LTS`.
4. **The Salesforce CLI:** `sf --version`. If it's missing: `npm install --global @salesforce/cli`.
5. **jq:** `jq --version`. If it's missing: `winget install jqlang.jq`. Salesforce's official skills use it.

Open a new PowerShell window after any install, so the new commands are found.

## The checks, once for each host you use

Install Scout the way the README says for that host (Claude Code, Codex or Cursor), then:

| # | Do this | It passes when |
|---|---|---|
| 1 | Run setup: `/scout-setup` (on Codex `$sf-demo-scout:scout-setup`) | it ends with "Scout is set up and ready", or tells you exactly what's missing |
| 2 | `/scout connect my test org` | Salesforce's login page opens, and Scout shows your org's username and ID |
| 3 | `/scout add a text field Tester_Note__c to Account in <your org>` | Scout builds it without another question, since you named the item and the action, and says it's applied and checked |
| 4 | `/scout rename the field's label to Tester note` | it changes only the label, and checks it |
| 5 | `/scout prep my demo in <your org>` | you get a readiness check and a click path, and nothing is written |
| 6 | Run setup again | it takes the refresh path, says Scout is ready, and changes nothing you didn't approve |
| 7 | Start a new chat and ask Scout whether it's up to date | it answers, or says it couldn't check |
| 8 | When the maintainer tells you a newer test build is out: update the way the README says for your host, restart or reload as it says, then ask Scout which version it runs | Scout names the new version, and step 3's field is still there |

If anything fails, note the step, copy the message, and carry on with the next step if you can.

## What to send back

- Which host and version, and Windows 11 x64 or ARM.
- For each step: passed, failed (with the message), or skipped.
- Anything that felt slow, confusing or surprising.

Afterwards you can remove the test field from your org yourself, or ask Scout to (it asks you before deleting).
