# Rules for Salesforce demo builds

## Org
- Work only in the org the request names. Put `--target-org <that org>` on every `sf` command; never rely on the default org.
- Never run `sf org login`, `sf org logout`, `sf config set` or `sf alias set`, and never change a default org. If a tool asks for a default, ask me first.

## Ask first
- Get my yes before deleting any metadata or record this session didn't create.
- Get my yes before an org-wide switch: org settings, sharing defaults, activating or assigning a page for all users, or changing existing automation, profiles or existing permission sets.
- Get my yes before editing a shared layout or page the request didn't name.

## Demo-ready
A build is demo-ready only when the demo user (the user the CLI runs as) can see and use it:
- a permission set gives access to every new object and field, and it's assigned to the demo user
- every new object has a tab, visible through that permission set
- existing records are backfilled from the right source (for example the record's own history), so new fields show real values, not blanks; never overwrite real values with made-up ones
- a new or changed page is active where the demo user opens it: check their app, their profile and their default record type
- a new hierarchy custom setting has its org-wide default value saved, so its switch is there to flip
Include these in your plan from the start, alongside what was asked.

## Tools
- If Salesforce's hosted Flow generator (metadata-experts) is off in the org, say so and offer to switch it on; that's an org-wide switch, so ask first.

## Done means proven
Before you call anything done, read every item back from the org and prove it at runtime: insert or update a test record, run the tests, preview the agent. Report each item as verified, deployed but unproven, or not done.
