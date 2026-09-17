# Setup — AI-Suite Residue Scrub (self-heal)

Read + executed by both `fresh-install.md` and `refresh.md`. Ex-AI-Suite
machines carry stale hook registrations in `~/.claude/settings.json` (and
possibly `settings.local.json`) whose command paths point under `~/.aisuite/`.
Once AI Suite is uninstalled, every such hook throws on its matching event —
the loudest is a `Stop hook error: … /.aisuite/hooks/stop-hook.sh: No such
file or directory` after each turn, but PostToolUse / PreToolUse / SessionStart
aisuite hooks fail the same way, more quietly. This residue is NOT written by
Scout and is NOT gated behind a Scout `config.json`, so it must be scrubbed on
the FRESH path too, not only REFRESH.

**Auto-strip scope is deliberately narrow.** Remove a hook ONLY when its
`command` points under `/.aisuite/` AND that target script no longer exists on
disk. Path-substring alone is NOT enough: on a machine where AI Suite is still
installed the hooks are LIVE, and stripping them breaks working functionality
(observed 2026-09-10 — 4 live hooks disabled on an AI-Suite box). A hook whose
script is GONE can do nothing but throw, so removing THAT is pure repair; a hook
whose script is PRESENT is live and left untouched. Two other
aisuite artifacts are SURFACED, never touched:
- `env.NODE_EXTRA_CA_CERTS` pointing under `~/.aisuite/` — a corporate-proxy CA
  cert path. This is the auth/gateway class Scout NEVER edits; behind a
  TLS-inspecting proxy it may be load-bearing even when the file moved. Flag it.
- `extraKnownMarketplaces` / `enabledPlugins` entries keyed `*@aisuite` or an
  `aisuite` marketplace registration — the SE's plugin config, a `/plugin`
  decision. Flag it.

Idempotent, safe-fail, backup-before-write. Never aborts.

Resolve `${CLAUDE_PLUGIN_ROOT}` to the absolute active Scout plugin directory
and substitute it for `[PLUGIN_ROOT]`. The helper accepts only a literal direct
AI Suite script command or a literal script passed to an allowlisted
interpreter (`sh`, `bash`, `zsh`, `python`, `python3`, or `node`). Shell
expansion, compound commands, options-before-script, unknown wrappers,
inaccessible targets, settings symlinks, and any other uncertainty remain
untouched and are reported.

```bash
SETTINGS_HELPER="[PLUGIN_ROOT]/scripts/setup-settings.py"
PYTHON_EXE=$(type -P python3 2>/dev/null || true)
if [ -z "$PYTHON_EXE" ] || [ ! -f "$SETTINGS_HELPER" ]; then
  echo "SETTINGS_HELPER_UNAVAILABLE"
else
  for USER_SETTINGS in "$HOME/.claude/settings.json" "$HOME/.claude/settings.local.json"; do
    "$PYTHON_EXE" -B "$SETTINGS_HELPER" aisuite-hooks --settings "$USER_SETTINGS"
  done
fi
```

Surface inline (compose one combined note across both files; silent only if every result was `AISUITE_ABSENT` / `AISUITE_HOOKS_NONE` with no `FLAGS`):
- Any `AISUITE_HOOKS_REMOVED[...]` — "Removed leftover AI Suite hooks that were erroring every turn (they pointed at a deleted `~/.aisuite/` script that no longer exists): [name the events in plain words — e.g. 'Stop, PreToolUse']. Backed up your settings to `settings.json.scout-bak-aisuite` first. **Restart Claude Code** to stop the errors."
- Any `FLAGS[...]` (on either a REMOVED or NONE result) — add a second line: "Also spotted leftover AI Suite config I did NOT touch: [cert path in `NODE_EXTRA_CA_CERTS` / an `aisuite` plugin marketplace + `@aisuite` plugins]. If npm/TLS behaves oddly, check the cert path; manage the plugins via `/plugin`."
- Any `UNSUPPORTED[N]` — note that N ambiguous AI Suite command forms were left untouched for manual review.
- `AISUITE_PARSE_ERROR` / `AISUITE_UNSAFE_FILE` / `AISUITE_BACKUP_FAILED` / `AISUITE_WRITE_FAILED` — one-line note ("couldn't safely scrub AI Suite hooks from [file] — left it untouched; if you see a `Stop hook error` about `~/.aisuite/`, remove those hook entries by hand"), proceed. Never abort.
- `AISUITE_POST_WRITE_FAILED` — replacement completed but read-back verification failed; do not claim the named file is unchanged. Its exact pre-edit recovery copy remains beside it with suffix `.scout-bak-aisuite`.
- `SETTINGS_HELPER_UNAVAILABLE` — one-line note that the shipped cleanup helper could not be run; leave both files untouched and proceed.

## Done

Return to the dispatching prompt (fresh-install or refresh). This fragment writes only to the two `~/.claude` settings JSON files and never changes Scout's own state — no token needs to propagate to the done message beyond the restart note above.
