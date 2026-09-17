# Setup — .zshrc Managed Block

Refresh `~/.zshrc` with the Scout-managed environment block (idempotent, transactional). Adds `~/.local/bin` to PATH if missing, rewrites the managed `# BEGIN SF-DEMO-SCOUT` … `# END SF-DEMO-SCOUT` block, sweeps Scout-owned keys that escaped the block (including the retired `MAX_THINKING_TOKENS` and `CLAUDE_CODE_MAX_OUTPUT_TOKENS`, and the `ANTHROPIC_DEFAULT_*_MODEL` pins — swept out and never re-added), and warns about legacy `ANTHROPIC_MODEL`.

As of 2026-07-27 Scout sets no shell environment variables, so the managed block
is marker-only. The machinery is kept deliberately: it still removes the exports
Scout used to write (that is how existing installs self-heal) and still catches a
legacy `ANTHROPIC_MODEL`. Do not delete the block or this fragment.

**Transactional contract (2026-09-16, Batch 1 B2).** The refresh NEVER mutates the
file until a validated result is ready. In order: (1) classify the path — a
symlink is detected BEFORE a missing regular file, and a symlink whose target is
missing (dangling) leaves the link untouched and reports it; (2) a missing file is
an empty first-install; (3) syntax-check the ORIGINAL without sourcing it — a
pre-existing syntax error is reported and the file left untouched (Scout did not
cause it); (4) validate marker structure using EXACTLY the same delimiter
recognition the rewrite passes use — zero pairs (first install) or exactly one
correctly-ordered exact pair (refresh) are the only valid cases; anything else
(lone/reversed/duplicate/nested, or a marker line with trailing whitespace that
does not match the exact contract) is reported and the file left byte-for-byte
unchanged; (5) compute the new content in memory and stage it to a temp file
beside the real target; (6) syntax-check the STAGED result — if applying the edit
would produce invalid zsh (e.g. a multi-line `export ...=$( … )` whose first line
the line-oriented sweep would strip, orphaning the `)`), the edit is rejected and
the original preserved; (7) only a validated result is committed, with a
`.scout-bak-zshrc` backup, mode preservation, atomic replace, and symlink
preservation (the link is kept; the resolved target is replaced beside itself). A
staging/replace error preserves the original and reports a write failure. If no
`zsh` validator is available, the refresh is skipped and reported rather than
risking an unchecked write.

Set `SCOUT_ZSHRC_OVERRIDE=/path/to/fixture` to point the refresh at a fixture file
(used by the maintained offline verification suite; unset in normal use). Set
`SCOUT_ZSH_BIN` to override the `zsh` validator path (test seam for the
validator-unavailable case; unset in normal use).

Before invoking Bash, resolve this active Scout plugin installation's root from
the current plugin context to a concrete absolute path. Do not pass a literal
`${CLAUDE_PLUGIN_ROOT}` to the shell and do not search for or guess another cached
plugin version. Substitute the resolved absolute path in the command below. If
the path cannot be resolved or the shipped script is missing, surface the step as
unavailable and continue setup; do not reconstruct the implementation in the
conversation.

```bash
SCOUT_SETUP_ZSHRC_SCRIPT="/absolute/path/of/active/sf-demo-scout/scripts/setup-zshrc.sh"
if [ ! -f "$SCOUT_SETUP_ZSHRC_SCRIPT" ]; then
  echo "ZSHRC_REFRESH_UNAVAILABLE: shipped script not found at $SCOUT_SETUP_ZSHRC_SCRIPT"
else
  /bin/bash "$SCOUT_SETUP_ZSHRC_SCRIPT"
fi
```

If any `SCOUT_ZSHRC_DIAG:` line was emitted, surface it to the SE verbatim (one line) — it explains why the managed block was left unchanged.

If `ANTHROPIC_MODEL_PRESENT`, surface a one-line warning:

> "⚠️ Found legacy `ANTHROPIC_MODEL` in your `~/.zshrc` — this is not a Claude Code variable. Remove it manually."

If `ZSHRC_REFRESH_UNAVAILABLE` was emitted, surface it as a one-line setup warning
and do not report the shell file as refreshed.

## Done

Return to the dispatching prompt. Pass back `ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED` (and optional `ANTHROPIC_MODEL_PRESENT`). Every non-modify outcome (validation skip, marker/syntax rejection, symlink/validator issue, write failure) returns `ZSHRC_UNCHANGED` to the orchestrator and surfaces its `SCOUT_ZSHRC_DIAG` line to the SE inline. A missing shipped script instead returns the visible `ZSHRC_REFRESH_UNAVAILABLE` result.
