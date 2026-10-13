# Active host contract

Apply this before Scout setup, discovery, builds, repairs, or tool calls.

- Identify the active host from the current session: `claude`, `codex`, or
  `unknown`. The presence of a CLI on PATH does not identify the host. Set the
  logical `SCOUT_HOST` value and substitute it into each `[SCOUT_HOST]` argument;
  shell variables and working directories do not persist between tool calls.
  If the host is unknown, perform only host-neutral work; do not edit a host's
  settings or run another host's setup as a fallback.
- Resolve `PLUGIN_ROOT_ABS` from the active plugin/skill context. Throughout
  Scout, `${CLAUDE_PLUGIN_ROOT}` means this resolved root, including in migrated
  commands. Substitute a concrete absolute path before calling a shell or
  delegating. Do not read another host's installed-plugin registry or guess a
  cached version. Missing source context is an explicit unavailable result.
- Claude-specific `allowed-tools` and `mcp__plugin_...`/`mcp__...` names are
  Claude permission references, not portable callable identifiers. Discover the
  actual tools exposed by this session. Resolve each required operation against
  the published tool description and input schema; never manufacture a prefix
  or assume a different connector has the same arguments or write scope.
- Use `prompts/mcp-readiness.md` at the first provider-dependent operation.
  Existing org-selection, user-approval, and read/write boundaries still apply.
  Use the established `sf` fallback when DX tools are unavailable, always with
  the explicitly selected org. Do not replace a policy-blocked MCP registration.
- `/model` notices and `Agent(...)` examples apply
  to Claude. On Codex use the host's available delegation tools and inherited
  model settings, with the same task boundaries and result contracts. Pass the
  host, resolved root, selected org, and discovered tool contracts to workers.
  Never instruct a Codex user to switch to an unavailable Claude model.
- Claude setup repairs (`.claude` settings, model pins, AI-Suite hooks, Claude
  CLI updates, and Claude marketplace auto-update) apply only to Claude. Codex
  configuration and policy stay under its own host controls.

Salesforce CLI (`sf`) is a machine installation, usable without Scout. The
Salesforce DX MCP adapter (`@salesforce/mcp`) is a separate package launched by
each host from Scout's plugin manifest using `npx`. Pre-caching the adapter does
not register it globally or establish that any host connected successfully.

## Worker model mirroring

Before every Claude worker dispatch, set the per-call `model` to the alias of
this orchestrator's own model family. The session's version pins its matching
alias, so this mirrors the session instead of the host's default worker model.
If this session cannot identify its own family, omit `model`; do not guess.
The user's `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` can override this choice.
Apply this on initial calls and every redispatch. Codex keeps the inherited
model behavior described above.
