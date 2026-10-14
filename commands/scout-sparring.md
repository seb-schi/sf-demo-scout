---
name: scout-sparring
description: >
  Classic command name, kept for familiarity. Opens Scout 2.0 (/scout), which spars on the story and builds in one session.
argument-hint: "[request] [org alias or username]"
allowed-tools: Read, Grep, Glob, Write, Edit, Bash, Agent, AskUserQuestion, mcp__salesforce-docs__salesforce_docs_search, mcp__salesforce-docs__salesforce_docs_fetch
---

# `/scout-sparring` opens Scout 2.0

This classic command now hands over to `/scout`. Request: $ARGUMENTS

On Claude, when this session identifies its model as an Opus, Sonnet or Haiku model older than 5.5, send only “Heads-up: this is a Classic command, and Scout 2.0 is built for Opus 5.5 and later. Run `/model`, pick Opus 5.5, then run `/scout` with your request. Details in #sf-demo-scout.” and stop.

Otherwise begin your first message with “Heads-up: `/scout-sparring` is a Classic command. Scout 2.0 replaces it, so I'm starting `/scout` with your request now. Details in #sf-demo-scout.” Then read `${CLAUDE_PLUGIN_ROOT}/prompts/host-runtime.md`, resolve its absolute root, read `commands/scout.md` from that root and follow it exactly, as if the SE had run `/scout` with the request above. With no request, ask what they want to build, fix or prep.
