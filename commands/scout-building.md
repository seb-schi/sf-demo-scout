---
name: scout-building
description: >
  Classic command name, kept for familiarity. Opens Scout 2.0 (/scout), which builds your spec as its brief and checks each item in the org.
argument-hint: "[spec path] [org alias or username]"
allowed-tools: Read, Grep, Glob, Write, Edit, Bash, Agent, AskUserQuestion, mcp__salesforce-docs__salesforce_docs_search, mcp__salesforce-docs__salesforce_docs_fetch
---

# `/scout-building` opens Scout 2.0

This classic command now hands over to `/scout`. Spec or request: $ARGUMENTS

On Claude, when this session identifies its model as an Opus, Sonnet or Haiku model older than 5.5, send only “Heads-up: this is a Classic command, and Scout 2.0 is built for Opus 5.5 and later, ideally at High effort or higher. Pick Opus 5.5 (model picker or `/model`), then run `/scout` with your spec.” and stop.

Otherwise begin your first message with “Heads-up: `/scout-building` is a Classic command. Scout 2.0 replaces it, so I'm starting `/scout` with your spec as the brief.” Then read `${CLAUDE_PLUGIN_ROOT}/prompts/host-runtime.md`, resolve its absolute root, read `skills/scout/SKILL.md` from that root and follow it exactly, as if the builder had run `/scout` with that brief: the spec named above or, when none is named, the newest `demo-spec-*.md` in the customer folder you settle on. The spec is a supplied plan, so its items, beats and claims become the brief, and confirmation still applies.
