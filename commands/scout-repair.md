---
name: scout-repair
description: >
  Opt-in Scout 2.0 repair of one existing report filter value. Uses explicit org
  binding, preserved originals and independent read-back. No full org audit or
  scenario interview. Other repair types continue through the existing workflow.
allowed-tools: Read, Write, Bash
---

# Scout Report Repair — opt-in preview

Read `${CLAUDE_PLUGIN_ROOT}/prompts/host-runtime.md`, resolve the active plugin
root, then follow `${CLAUDE_PLUGIN_ROOT}/prompts/building/scout-2-repair.md`.
Use the active model; no mandatory model switch or subagent is needed.
