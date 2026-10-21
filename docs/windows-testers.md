# Testing Scout on Windows

Thank you for testing. This takes about 45 minutes per host. Use a **test org you own**: a Developer Edition, a
trial or a sandbox, never a customer's org. Every sign-in is yours; Scout opens Salesforce's login page and never
asks for a password.

## Before you start

You need Windows 11 (x64 or ARM). In PowerShell, check the five tools in the README's
[On Windows (beta): the tools first](../README.md#on-windows-beta-the-tools-first), and fix what's missing the
way it says. Then open a new PowerShell window, and quit and reopen the Claude, Codex or Cursor app, so the new
commands are found. If a step fails, look up its message in [Troubleshooting](troubleshooting.md) before you
report it, and say in your report whether a fix from there worked.

## The checks, once for each host you use

Install Scout the way the README says for that host (Claude Code, Codex or Cursor). On Claude Code, the install
lines run in PowerShell (`claude plugin marketplace add …`, then `claude plugin install …`), because the desktop
app doesn't run `/plugin`; if PowerShell doesn't know `claude`, install it first with
`winget install Anthropic.ClaudeCode`. Then:

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
