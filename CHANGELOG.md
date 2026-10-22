# What's New in Demo Scout

Newest first. Scout updates itself; each entry says what changed for you.

## 2026-10-22 (Scout 2.5.1)

- **The offer to join a string telephone explains itself.** When an org you build in already has one, Scout now
  says in plain words what it is and what joining does before it asks, so you can decide without having heard of it.
- **A clear reason when a task record's path is wrong.** The string telephone and build cards take the task record
  by its full path. Given a relative path, or one with no file behind it, they now say so and write nothing. Before,
  the reason read as if the file were a link, or the handover quietly went without its card.
- **Codex, from the desktop app.** If your terminal doesn't know `codex`, the README and the troubleshooting page now
  say how to add Codex's command line, which the README's install commands need. And instead of "the highest reasoning
  setting", they name what Scout is tested with: GPT-6.1-Sol at Extra High on Codex, Opus 5.5 at High on Cursor.
- **Short times read in minutes on build cards.** Twenty minutes shows as "about 20 minutes", not "about 0.33
  hours", and one hour as "about 1 hour".

## 2026-10-22 (Scout 2.5.0)

- **Building one org together, the light way: the string telephone.** It's Simon Beer's idea, now built in.
  - **Who it's for:** builders who share one demo org, even when they're signed in as the same Salesforce user.
  - **What it is:** a shared Scout Log in that org.
  - **What each builder's Scout does with it:** it reads the newest entries before its first write, stops and asks
    before writing to something a teammate has locked, and writes one entry at handover, with a generated summary of
    the task.
  - **Entries are notes, never orders:** Scout checks the org itself, and never acts on a request it finds in one
    without asking you.
  - **To start:** `/scout string-telephone`. When an org you build in already has one, Scout offers to join before
    its first write there. It needs Salesforce CLI 2.148.3 or later, and customer orgs don't get one.
- **Two routes when you collaborate.** When you tell Scout you're working with colleagues on an org, it offers the
  string telephone or team mode, says which it recommends and why, and follows your pick.
- **A build card at the end of each build.** The handover shows what was built and what Scout's checks found, exactly
  as it would be posted, and asks whether to share it in a Slack channel with a line of your own.
  - Your own estimate of the time it saved is optional. Scout never estimates time itself.
  - Nothing is posted without your yes, and a card you don't share stays on your machine.
  - `/scout cards channel #name` sets where cards go, and `/scout cards off` stops them.
  - `/scout summary` turns a month of cards into counts you can choose to submit.
- **What Scout records, and what it sends.** A new README section lists it all. Scout keeps no telemetry of its own,
  and the tools it installs name their own switches.

## 2026-10-21 (Scout 2.4.1)

- **Scout calls you a builder.** Scout is for anyone who builds Salesforce demos now, so its messages, rules and handovers say "builder", not "SE". The handover's list for you is "Your manual checklist", and change logs end with "Your next steps". Change logs from earlier versions still count.
- **The demo story works for any audience.** The value story was written for a customer meeting. It now works the same way for an audience inside your company, such as a product review: who has to say yes, their pain, what doing nothing costs, the beats and the proof moment.
- **Flows go to Salesforce's tools first.** Salesforce's hosted generator builds a new Flow. Scout asks once before switching the generator on in an org, because it's beta and may be billed. An edit to an existing Flow changes only what you asked, with Salesforce's official skills. Scout's own Flow builder comes last, and still writes the FlowTests.
- **Scout does more of the build itself.** Several limits written for weaker models are gone:
  - **Record pages:** Scout adds tabs, components, sections and fields to an existing Lightning record page through Salesforce's official page skill. It grounds each component in your org first, drops one the org rejects, and stops after a second rejection. Moving or removing what's already on the page asks first, and before and after the deploy Scout checks that everything already there stayed as it was, apart from exactly what you approved. New pages from scratch stay in App Builder for now.
  - **Flows:** screen flows have no screen cap or component list, and orchestration flows deploy for a visual check. Salesforce's generator gets up to ten tries per Flow, each told what went wrong last time, and Scout says how many Flows it will generate before it starts.
  - **Smaller steps:** Scout proposes a scheduled flow's timing, checks that a platform event exists, fills in a blank agent Role or Company, and sets an agent's model in Agent Script.
  - **Long fixes:** after ten Apex test runs or ten attempts on one item, Scout tells you what it tried and asks whether to go on, instead of stopping.
- **Opus 5.5 at High effort or higher.** Scout works best there. On Claude Code, Scout's session banner says so when the effort is lower; switch with `/effort high`, or under Effort in the model picker.
- **On Claude Code, Scout installs from a terminal.** The desktop app doesn't run `/plugin`, so the README's two install lines run in Terminal or PowerShell: `claude plugin marketplace add …`, then `claude plugin install sf-demo-scout@scout`. Then open a new session and run `/scout-setup`. Scout's automatic updates still switch on.
- **Windows, still in beta, with fewer snags:**
  - **Python:** setup's hint is `pymanager install default`, the install manager's own command, which an older Python launcher can't take over.
  - **The Salesforce CLI:** install it with npm. The copy from Salesforce's Windows installer, under `C:\Program Files\sf`, breaks when a command has a quoted argument. Setup says so and how to switch, and Scout reruns such a call through the CLI's own Node script.
  - **Logins:** a new org's alias has no spaces, and a login counts once Scout's binding confirms the org, whatever the login command's exit code.
  - **A tool you just installed** that this window can't see yet: setup says to reopen the app, instead of asking you to install it again.
  - **Behind a company proxy,** the README names the Git setting that lets Git for Windows reach GitHub.
  - **Scripts' output** no longer depends on the console's code page, and setup's model note names Windows' own settings there.
  - **Windows CI** runs the session-start and Salesforce CLI tests too, on Python 3.12 and 3.15.
- **Troubleshooting by message.** `docs/troubleshooting.md` starts from the exact message you see, with what it means, the fix and a quick check.
- **Notices you see.** On Claude Code, a newer Scout release, or a setup that needs repair, shows in the session's own banner, not only to Scout.
- **The update check keeps its last answer** when GitHub can't be reached, so a network hiccup doesn't hide a newer release for a day.

## 2026-10-21 (Scout 2.4.0)

- **Scout runs in Claude Code, Codex and Cursor; one of them is enough.** Claude Code and Codex install Scout as a plugin. Cursor installs it from a folder you clone, because managed Cursor installs often refuse third-party plugins: two small skills point Cursor at that folder. `/scout` and `/scout-setup` work the same everywhere; on Codex they're `$sf-demo-scout:scout` and `$sf-demo-scout:scout-setup`. The README has the steps for each.
- **Scout writes only to demo orgs.** When it binds an org, Scout reads the org's type. It writes to trials (an org with an expiry date still ahead), sandboxes, scratch orgs and Developer Editions. In a production org, or one it can't tell, it inspects, plans and preps, but changes nothing, and it says so. Your confirmation doesn't change that.
- **Salesforce's official skills on every host.** On Codex, setup offers to add Salesforce's plugins, which Codex keeps up to date. On Cursor, it offers a clone of Salesforce's public skills repository, read in place. Where Salesforce's own deploy checks don't run, Scout deploys with its own checks and tells you.
- **Windows 11, host by host.** Setup, builds, repairs and prep run on Windows in Claude Code, Codex and Cursor. Scout's own scripts are Python now, and its session hooks start through one small launcher that works the same from Git Bash and PowerShell. You need Git for Windows, Python 3.9 or later, Node 22.20 or later, the Salesforce CLI and `jq`; the README lists them. A host is marked tested once it has passed the release's Windows checklist. Building one demo org together stays on macOS for now; on Windows, Scout says so.
- **Scout tells you when a newer release is out,** with your host's way to update. It asks GitHub at most once a day, and only for the version number. Set `SCOUT_NO_UPDATE_CHECK=1` to turn it off.
- **Staying on a release, or going back.** Every release has a tag, and the README shows how to pin each host to one. To go back to 2.3.2 on Claude Code, use the `recovery-2.3.2` branch the README names: 2.3.2's own tag still follows `main`.
- **Scout relies only on what anyone can get.** It needs nothing that only Salesforce colleagues have: Salesforce's official plugins from their public GitHub marketplace, the Salesforce CLI, and the public Agentforce Labs Salesforce Docs MCP. Setup now offers the Docs MCP and adds it only on your yes. Without it, Scout carries on and marks what it couldn't check against the Docs.
- **Setup no longer sets up Slack or Google Drive.** Scout can still use whatever your coding tool has connected, but only when you ask it to, read-only unless you ask for a change and approve it, and it never searches a connected workspace on its own. Check what's connected in your environment. The offer to put the demo flow on a Slack canvas is gone too; the demo map stays in your workspace.
- **Setup leaves your shell and other tools alone.** `/scout-setup` no longer writes to `~/.zshrc`, changes other tools' hooks or model settings, or adds permission rules to your Claude settings. What earlier versions wrote stays as it was. To tidy up by hand:
  - delete the block from `# BEGIN SF-DEMO-SCOUT` to `# END SF-DEMO-SCOUT` in `~/.zshrc`
  - remove the allow rules earlier setups added to `~/.claude/settings.json`, unless you want them: `mcp__slack__*`, `mcp__plugin_slack_*`, `mcp__salesforce-docs__*`, `Agent` and `Skill`
- **Auto-update stays your choice.** Setup turns on auto-update for Scout's marketplace only when you haven't set it either way.
- **A quieter session start,** without a sign-in check that applied only inside Salesforce.
- **Building one demo org together, ready for customer teams** (Lifecycle Center mode):
  - **The guard is your choice at join.** Scout explains in two sentences what its guard does, and turns it on only on your yes. A member can join without it, and the captain's status shows whose guard is off. Taking an earlier guard off is its own step, on your yes. Scout's own lane still needs the guard.
  - **A protected `main`:** the team's rules arrive as a pull request, and the team start waits until it's merged. A reviewer's edits to that pull request stay as they are, and after a squash merge the next rules update goes out as a new pull request.
  - **Line endings:** the team start sets LF line endings for the repository, tells open work items how to take the new rule, and names every file and component `main` already holds with CRLF.
  - **For builders without Scout,** the team's rules gain three lines: deploy to your own sandbox when an official deploy skill fails; ship a new object with its tab and a permission set that shows it; and let tests that insert a new record type's records create their own user. For every new object, the captain's read-back asks the presenting user to check that they see its tab: Scout reads Git, not who can see what.
  - **Checks that stop instead of guessing:** a build org that turns out to be the common org is refused, and a delivery check whose input is missing stops or says not verified, instead of passing. A missing answer after a promotion went out says where the delivery stands and how to resume. A member's guard is reported as unknown, not off, when Scout can't tell.
  - **The kit needs Node 22 or later,** like the Salesforce CLI.
- **Apex tests and new record types.** From API 67.0, Apex checks that the running user can use a record type: a test that inserts records of a new record type before anyone is granted it fails with `INVALID_CROSS_REFERENCE_KEY … this ID value isn't valid for the user`, even when it runs as the admin who deployed it. Scout's tests create their own user, grant the record type through a permission set, and insert as that user.
- **Uninstall.** Ask Scout to uninstall itself. It shows what it would remove, removes only its own configuration and cache on your yes, and your workspace with its org histories only on a separate yes. Then it tells you how to remove the plugin.

## 2026-10-19 (Scout 2.3.2)

- **A delivery says where it is while it waits.** On Lifecycle Center, a promotion or the tests after it can take minutes. Scout's delivery now reports each step as it goes, Scout can look at Lifecycle Center and the common org while it waits, and when you'd rather not wait, it stops at the next safe point, so it tells you where things stand instead of going quiet. When an answer from Lifecycle Center goes missing, Scout never submits the promotion a second time on its own.
- **A failed test after a promotion is said on the pull request too.** When the tests a delivery owes fail after its promotion, Scout comments "Not verified: …" on the pull request, and teammates' Scout sessions show the same line. A builder without Scout learns of it on GitHub, even though Lifecycle Center marks the work item closed.

## 2026-10-19 (Scout 2.3.1)

- **Asking for a team on Lifecycle Center now always gets you one.** When you tell Scout your team should run on Lifecycle Center, its team guide now points straight to Lifecycle Center mode. Before, Scout found that mode only by looking for it, and could have started a team on its own lane instead.

## 2026-10-19 (Scout 2.3.0)

- **Teams can run on Salesforce's Lifecycle Center** (the next-generation DevOps Center), in beta. Your team's work items, reviews and promotions are Salesforce's own, set up with Salesforce's official skills, and everyone on the team can use Cursor, Agentforce Vibes or Scout. When a captain sets a team up, Scout offers Salesforce's official Lifecycle Center plugin (`dx-devops`) if it isn't installed yet; it updates itself like the others. Scout adds what nothing official covers:
  - before a delivery merges, it checks what's in it, that its builder started from the team's latest copy, and that the common org still holds what the pipeline last delivered, and it runs the stage's tests against the common org without changing it
  - the captain's yes covers exactly what was checked; a delivery that's interrupted, or merged on GitHub directly, picks up from what Salesforce and GitHub show, and nothing deploys without a yes for what's actually on `main`; when Lifecycle Center can't work out what a promotion should deploy, Scout offers a full promotion, after checking everything on `main` against the common org, and asks the team to hold merges while it runs
  - after a delivery, it reads the result back; in an org that runs no tests during a deploy, Scout says so before the merge, and with the captain's yes the tests run right after the promotion, and only a passing run counts as verified
  - it brings teammates' updates to your session, and keeps each one until your session has shown it
  - the beta's known limits: Lifecycle Center can't promote a new component whose files reach the work item in separate commits, so the team's rules say to commit them together, and Scout points out a delivery that needs the full promotion; DevOps Testing doesn't run on promotions from the command line, so Scout runs the stage's tests itself; required reviews on a protected `main` aren't tested yet
- **Build one demo org together.** Tell Scout you're working with colleagues on an org ("/scout session: start a team on acme-sdo with Bob"), and it sets up the team for you: a private GitHub repository, a team board, and a guard in each teammate's Salesforce CLI. Each of you builds in your own sandbox exactly as before. When you say "hand it over", Scout puts your work on its own branch with a pull request. The captain's Scout delivers it into the common org through one guarded lane, and nobody types a git or sf command.
- **Nothing overwrites a teammate's work.** Before you change something the team already has, Scout makes sure your sandbox has the team's latest version. A delivery stops when the common org was changed outside the team, shows who changed it, and asks the captain what to keep. Every delivery keeps a backup and is read back afterwards.
- **Teammates' updates come to you.** When a teammate hands over or the captain delivers, your Scout tells you at your next message, or wakes an idle session, with a short "📨 Team update". GitHub's own pull-request notifications reach you away from Claude.
- **Teammates without Scout can join in.** The team repository explains, for Cursor and other AI tools, how to install the guard, keep their editor from deploying on save, and hand work over with a pull request. The captain's Scout delivers it the same way, and when it comes back for a fix, they push the same branch again.

## 2026-10-18 (Scout 2.2.1)

- **Automotive Cloud and Manufacturing Cloud join the clouds Scout reads up on.** When a request is about either one, Scout reads that product team's data model, setup order and module notes from its public GitHub repo, at a version Scout's maintainer has reviewed, the same way it reads Life Sciences, Net Zero and Revenue Cloud. As before, Scout checks every name against your org or the Salesforce Docs, never installs the teams' plugins or runs their tools, and stops to ask before a step that changes the whole org, such as switching on Person Accounts, Timeline or a Manufacturing Settings feature.

## 2026-10-18 (Scout 2.2.0)

- **Scout now reads what Salesforce's product teams publish for their clouds.** When a request is about Life Sciences Cloud, Net Zero Cloud or Revenue Cloud, Scout reads that team's setup notes, data model and troubleshooting from its public GitHub repo, at a version Scout's maintainer has reviewed, and builds with it. It checks every object and setting name against your org or the Salesforce Docs before relying on it. Scout only reads these repos: it never installs the teams' plugins or runs their tools or scripts, and every change still goes through Salesforce's official skills, with your confirmation, in the org you named. When an installed knowledge pack covers your industry, Scout uses that pack first.
- **Org-wide settings get asked about first.** When a cloud's notes show that a step changes a setting for the whole org, such as switching a cloud on, Scout stops and asks before making it.
- **Industry plugins you install yourself stay out of Scout's builds.** Several of them come with their own tools, which pick an org on their own. Scout leaves those tools alone and makes changes the usual way.

## 2026-10-17 (Scout 2.1.5)

- **Scout no longer starts its own Salesforce DX connection.** Salesforce ends support for that server (`@salesforce/mcp`) on 2026-11-02 and points to its official skills, which Scout already uses. Scout did its org work with the Salesforce CLI anyway. LWC guidance now comes from Salesforce's LWC plugin, and code checks from its code-quality plugin, through the Salesforce CLI. Apex checks still need Java 11 or later; when they can't run, Scout says so rather than reporting a clean scan.
- **Scout repairs its own setup.** When Scout finds its setup unfinished or broken, or Salesforce's official plugins not set up, it now runs `/scout-setup` itself before your first Scout task, instead of asking you to. It fixes its own files and installs Salesforce's plugins on its own, with the settings those plugins need, saying so in one line. Before it updates the Salesforce CLI, changes your `~/.zshrc`, makes any other change to your Claude settings, or turns back on or installs a plugin that's switched off or missing, it asks you once; on a no it skips those and tells you. After installing plugins, it asks you to run `/reload-plugins`.
- **A heads-up before Salesforce's Flow generator runs.** When Scout builds a Flow with Salesforce's hosted metadata-experts server, it now tells you before the first request that Salesforce may bill that use, instead of only at the end. The route is also verified with version 2.5.0 of Salesforce's plugin.
- **A lighter `/scout-setup`.** It removes the permission rule Scout added for that server from your workspace and Claude settings, changing nothing else, and no longer downloads the server or warns when `npx` is missing. It leaves updating Claude Code to Claude Code's own updater, and still tells you which version you're running and how to update when Scout needs a newer one. It also stops repairing permission names from Scout versions before July 2026, which every refresh since then has fixed.

## 2026-10-17 (Scout 2.1.4)

- **A quicker session start.** When a session starts, Scout now shows only your default org: its alias, username and org ID, from its latest connection check. It no longer lists all your connected orgs, checks Slack's connection or lists your customer folders first, and when you name an org, Scout looks up only that one. `/scout` still checks Slack, Google and the Salesforce Docs when a task needs them, and reads your customer folder's history itself.
- **A shorter setup message.** `/scout-setup` ends with one line saying whether Scout is ready, plus short notes only where they apply: CLI updates, connections to finish and shell changes.

## 2026-10-17 (Scout 2.1.3)

- **A lighter Scout.** Scout no longer carries the classic instructions that `/scout` replaced in 2.0, and the text that pointed at them now points at the rules `/scout` follows. Scout reads less before it starts, and nothing changes in how you use it.
- **Fewer tools in every session.** Scout's Salesforce DX connection no longer offers its org tools for deploys, queries, deletes and permission assignments. Scout already did that work with the Salesforce CLI, always naming the org. Its LWC guidance and code-analysis tools stay.
- **One command fewer.** `/scout-repair` is gone. Ask `/scout` to change an existing report's filter, and it makes the same repair with the same checks.
- **Clearer rules in a few corners.** A deploy that keeps failing is reported as failed, with what's left in the org; a deploy whose result isn't known yet stays unverified and is never sent again. Screen flows with components outside the usual set are deployed and flagged for a visual check, instead of going to your manual list. List views are written the way Salesforce's own skill writes them.

## 2026-10-16 (Scout 2.1.2)

- **Scout tries harder.** When a deploy, an Apex test or its own records check fails, Scout finds the cause and keeps going while each attempt fixes something new: up to ten deploy attempts, ten test runs and ten repair rounds for its own records, where it used to stop after two or three. It still never re-sends a write with an unknown outcome, never deletes without your yes, and never goes beyond what you approved.
- **The demo flow on a Slack canvas.** After the handover, Scout offers to put the demo flow on a Slack canvas in your own Slack: each beat's click path, records and proof moment, and the checks to do before you present. It isn't posted anywhere; you decide whether to share it.
- **No more "History incomplete" over dry runs.** Salesforce's deploy skill checks each deploy with a dry run first. Scout now records those dry runs the way it records every deploy, so its history check settles them instead of reporting the history as incomplete.

## 2026-10-16 (Scout 2.1.1)

- **Scout opens Salesforce's login page for you again.** If the org you want isn't connected yet, or its login has expired, Scout offers to open Salesforce's login page in your browser, as the classic commands did. You sign in there, and Scout never sees your password. It never re-points an existing alias, checks that a renewed login is still the same user, and leaves your default org as it is.
- **Scout installs Salesforce's plugins for you.** If they aren't set up yet, for example right after this update, `/scout` offers to install them in one line, instead of sending you to `/scout-setup`. Then run `/reload-plugins` and Scout carries on.
- **Scout can pull in what Slack and Google know about your customer.** When your request names a customer, Scout asks once whether to search Slack and Google for them, read-only. On your yes it digs in, and uses what it finds as leads with their sources, never as facts.
- **Industry knowledge packs work in the desktop app too.** Scout finds an installed knowledge pack, such as the Life Sciences Booster Pack, through the desktop app's own Claude Code, so it no longer needs the `claude` command in Terminal.

## 2026-10-16 (Scout 2.1)

- **Flows from Salesforce's own Flow generator.** When the official `salesforce-development` plugin is installed, Scout can have Salesforce's hosted metadata-experts server generate a Flow. Scout then checks, deploys, tests and activates it as usual. Scout's own Flow skill stays the fallback.
- **Scout can switch the server on for you.** If the server isn't active in the org, Scout offers to activate it as its own line in the plan's confirmation. Activation applies to the whole org, the server is in beta, and Salesforce may bill its use. Scout acts only on your explicit yes, and reads the setting back.
- **A warning when the official plugin would get in the way.** Scout tells you before building if the official plugin's auto-deploy is on, or if its deploy check would block because no working default org is set where your session started. In that case Scout asks, in plain words, whether to make the task's org your default. It changes it only on your yes, and never touches your logins or aliases.
- **Scout now drives Salesforce's official plugins instead of copying their skills.** `/scout-setup` installs the five Scout uses from Salesforce's own GitHub marketplace, once, and switches auto-update on, so you always get Salesforce's latest skills: the core platform and code-quality plugins, plus Agentforce, Lightning Web Components, and Email-to-Case and messaging. If one ever goes missing, Scout offers to reinstall it when a build needs it. Scout's 25 copied skills are gone. Note that Salesforce's LWC plugin runs a quick style check whenever Claude writes a web file (HTML, CSS or JavaScript), in any folder.
- **Scout takes charge of Salesforce plugins you already have.** If your Salesforce marketplace is fixed to an older release, or Anthropic's copy is also switched on, `/scout-setup` asks once and then switches you to Salesforce's latest, naming every plugin that changes. Personal copies of Salesforce skills (for example from `npx skills add`) are only reported: Scout never moves or deletes them.
- **Other official plugins only when a build needs them.** Salesforce publishes more plugins, such as one for Omni-Channel routing. When a build falls in one of their areas, Scout offers that one plugin in its confirmation. It never installs them all, because each one makes every Claude session a little heavier.
- **Scout checks the official plugins before every build.** If one isn't installed, is switched off, or appears twice, Scout says so and names the fix. Items that need a missing plugin are reported as blocked; everything else still builds.
- **Scout follows the official plugin's own checks.** It loads Salesforce's query, retrieve and test skills where the official plugin expects them. For an org the plugin treats as production, it asks you once per task before deploying.
- **The change log says why, and with what.** Each change records the criterion it serves and the skill, helper or command that made it.

## 2026-10-14 (Scout 2.0.2)

- **Model and Slack hints that work in the desktop app.** When Scout asks you to switch to Opus 5.5, it now points to the model picker as well as `/model`. When Slack or Google needs authenticating, it tells you to use Terminal (`claude`, then `/mcp`) if `/mcp` isn't available in the desktop app.

## 2026-10-14 (Scout 2.0.1)

- **An interrupted deploy no longer blocks an org for good.** If a session ended while a deploy or bulk data load was still running, the next session still checks that job before writing. It now records what it found in its own change log, so later sessions don't check again. When Salesforce no longer has the job, or the job has no status to read, Scout reads back what it changed instead of stopping every write in that org.
- **Two more deploy states are recognized.** A deploy that fails while finalizing counts as failed, and a queued deploy can be recorded as `Pending`.
- **Two honest records now pass the history check:** a retry while Salesforce Docs is unavailable, and a companion permission set that leaves out a failed item's grants.
- **The handover's Demo Story fits the task.** A task with a story gets its verified beats; a small change gets one line naming the beat it serves. A complete brief is never given an invented story.
- **Naming an org by username finds its customer folder,** because Scout can look up the org's alias.

## 2026-10-14 (Scout 2.0)

The biggest update since Scout launched. `/scout` replaces the two-step sparring-and-building flow with one session that spars, builds, checks, and preps your demo. It's built for Opus 5.5 and later.

- **One command, `/scout`, takes you from idea to a checked demo.** Bring your request in any shape: a one-line idea, a complete brief, a pasted demo plan or discovery notes, a fix, or a task record to resume. Scout plans it, asks once, builds it and checks it in one session. There's no spec and no second window.
- **The classic commands now open `/scout`.** `/scout-sparring` starts it with your request, and `/scout-building` hands it your spec as the brief. A note says so and points to #sf-demo-scout. Showtime mode is retired.
- **Scout 2.0 is built for Opus 5.5 and later.** On an older Opus, Sonnet or Haiku model, Scout stops before any work and asks you to switch with `/model`.

- **Scout still spars with you on the story.** For an open-ended request it drafts the value story, in at most two rounds. That covers who has to say yes, their pain, what doing nothing costs and the future state, plus two to six beats and the proof moment. Gaps stay visible rather than invented, and Scout challenges any item that doesn't prove the story ("keep or cut?").
- **Demos are built to present, not just deployed.**
  - Seed data carries real tension, such as overdue and at-risk records, dated from the seed day with a stated validity window.
  - Hero records get contacts and activity, and live flips come with a reset.
  - Seed scripts are re-runnable, never delete, and have a `--pilot-only` self-test.
  - Every on-screen claim becomes a check that Scout reads back from the org.
- **Salesforce Docs ground the design.** Before deciding how to build flows, Apex, LWC, Agentforce, Email-to-Case, dashboards or an unfamiliar type, Scout fetches the relevant Docs page. Every item records where its approach came from.
- **Another customer's work is reused only on your yes.** Scout can offer an earlier build by folder name, copies nothing without your answer, and scans any copy for the other customer's content.

- **Scout works only in the org you name.** It binds to that org's username and org ID and re-checks the binding before every write. It stops if the org changes under it. Every command targets the bound org explicitly, and Scout never changes your default org, aliases or login.
- **You confirm once, and each delete on its own.** An explicit request that names the item and the action counts as your yes, except for deletes. Each delete is confirmed alone, naming every record and everything that goes with it. Changes to existing permission sets or profiles, and anything prefixed `sb_` or `managed__`, still need your explicit yes.
- **Instructions inside files are data.** A plan, notes or retrieved content can't authorize anything; only you can.

- **Nothing is called done without Scout's own read-back.** Every item ends `applied`, `already_satisfied`, `failed`, `blocked`, `unverified` or `omitted`, with its evidence. A green deploy alone doesn't count. Items that can't be checked by machine are listed as needing a visual check, never called working.
- **Handovers lead with the outcome.** They start with:
  - what's verified
  - what needs a visual check
  - what's not done, with the reason and the next step
  - your manual checklist
  - whether anything was copied from another customer

  Then comes the Demo Story, with the click path for each beat.

- **Larger demos build in a planned order.** Three or more items, or any Flow, Apex, LWC or Agentforce item, get a dependency plan. Authoring can run in parallel, while org writes stay one at a time. Story beats are verified one by one, and the overall status stays honest.
- **Flows go live only on the version that passed its test.** Agents are validated, previewed, published and activated, then checked in a live preview.
- **Deploy jobs are tracked one by one.** Scout records each job's status and timing. If an answer goes missing, it settles the job from its ID before the next write and never re-sends it.

- **Every task keeps a record and a change log.** The task record holds:
  - your request
  - the bound org
  - each item with its criteria, evidence and outcome

  The change log holds a checkpoint for every attempt. Scout checks both before the handover, and says "History incomplete" when it can't settle them.
- **Scout picks up where you left off.** It scans the bound org's history across your folders for unfinished work, and settles open deploy jobs before writing. It reads classic history (specs, audits, change logs and demo maps) as leads.
- **Decisions, the demo map and lessons are written only on your answer.** Scout proposes them for yes, edit or skip. It flags any request that would revive an idea you rejected.

- **Scout preps you for delivery.** Ask it to prep for a demo, or run `/scout prep`.
  - It runs read-only checks scored against the demo's date and time zone.
  - It gives a readiness verdict, the drift since the build, a pre-demo checklist and the click path, all saved in `demo-path.md`. Your earlier copy is kept.
  - It offers fixes, applies none, and never changes the org.

- **`/scout-repair` (preview) repairs one existing report filter value.** It binds the org explicitly, preserves the original and reads the result back independently. An interrupted repair is held and recovered, never replayed. `/scout` uses the same path for report-filter fixes.
- **Writer projects are anchored by a root `.forceignore`,** so a build's first deploy no longer needs a repair.
- **The bundled Salesforce skills are refreshed to upstream v1.62.0,** Agentforce skills included.
- **The README, startup banner, setup's closing message and the standing rules now point to `/scout`.**

## Before Scout 2.0

Older entries, from before Scout 2.0, are in [this file as it stood in Scout 2.1.2](https://github.com/seb-schi/sf-demo-scout/blob/scout-2.1.2/CHANGELOG.md), and on the Scout Changelog canvas in #sf-demo-scout.
