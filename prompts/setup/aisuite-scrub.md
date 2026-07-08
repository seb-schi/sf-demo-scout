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

**Auto-strip scope is deliberately narrow.** Remove ONLY hook entries whose
`command` string contains `/.aisuite/`. A hook pointing at a deleted script can
do nothing but throw, so removing it is pure repair — the same "target the exact
known-residue, nothing fuzzy" discipline as the d.7 model-pin strip. Two other
aisuite artifacts are SURFACED, never touched:
- `env.NODE_EXTRA_CA_CERTS` pointing under `~/.aisuite/` — a corporate-proxy CA
  cert path. This is the auth/gateway class Scout NEVER edits; behind a
  TLS-inspecting proxy it may be load-bearing even when the file moved. Flag it.
- `extraKnownMarketplaces` / `enabledPlugins` entries keyed `*@aisuite` or an
  `aisuite` marketplace registration — the SE's plugin config, a `/plugin`
  decision. Flag it.

Idempotent, safe-fail, backup-before-write. Never aborts.

```bash
for USER_SETTINGS in "$HOME/.claude/settings.json" "$HOME/.claude/settings.local.json"; do
python3 - "$USER_SETTINGS" <<'PYEOF'
import json, os, sys, tempfile, shutil
path = sys.argv[1]
label = os.path.basename(path)

if not os.path.exists(path):
    print(f"AISUITE_ABSENT[{label}]"); sys.exit(0)
try:
    with open(path) as f:
        data = json.load(f)
except (json.JSONDecodeError, OSError) as e:
    print(f"AISUITE_PARSE_ERROR[{label}]: {e}"); sys.exit(0)
if not isinstance(data, dict):
    print(f"AISUITE_NOT_OBJECT[{label}]"); sys.exit(0)

MARK = "/.aisuite/"

# --- Auto-strip: hook entries whose command path is under ~/.aisuite/ ---
removed_hooks = []
hooks = data.get("hooks")
if isinstance(hooks, dict):
    for event, groups in list(hooks.items()):
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                continue
            kept = []
            for h in group["hooks"]:
                cmd = h.get("command", "") if isinstance(h, dict) else ""
                if isinstance(cmd, str) and MARK in cmd:
                    removed_hooks.append(f"{event}:{cmd.split('/')[-1]}")
                else:
                    kept.append(h)
            group["hooks"] = kept
        # drop now-empty hook groups (no remaining commands)
        hooks[event] = [g for g in groups
                        if not (isinstance(g, dict) and isinstance(g.get("hooks"), list) and len(g["hooks"]) == 0)]
    # drop now-empty event arrays
    for event in list(hooks.keys()):
        if isinstance(hooks[event], list) and len(hooks[event]) == 0:
            del hooks[event]

# --- Flag-only (never edit): cert + marketplace/plugin residue ---
flags = []
env = data.get("env")
if isinstance(env, dict):
    cert = env.get("NODE_EXTRA_CA_CERTS", "")
    if isinstance(cert, str) and MARK in cert:
        flags.append("cert:NODE_EXTRA_CA_CERTS")
ekm = data.get("extraKnownMarketplaces")
if isinstance(ekm, dict) and any("aisuite" in str(k).lower() for k in ekm):
    flags.append("marketplace:aisuite")
ep = data.get("enabledPlugins")
if isinstance(ep, dict) and any(str(k).lower().endswith("@aisuite") for k in ep):
    flags.append("plugins:@aisuite")

if not removed_hooks:
    # nothing to strip; still report flags so the SE sees residue
    tail = (" FLAGS[" + ",".join(flags) + "]") if flags else ""
    print(f"AISUITE_HOOKS_NONE[{label}]{tail}"); sys.exit(0)

# Backup before write
bak = path + ".scout-bak"
try:
    shutil.copy2(path, bak)
except OSError as e:
    print(f"AISUITE_BACKUP_FAILED[{label}]: {e}"); sys.exit(0)

tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=".settings.", suffix=".tmp")
try:
    with os.fdopen(tmp_fd, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.rename(tmp_path, path)
except Exception as e:
    try: os.unlink(tmp_path)
    except OSError: pass
    try: shutil.copy2(bak, path)
    except OSError: pass
    print(f"AISUITE_WRITE_FAILED[{label}]: {e}"); sys.exit(0)

tail = (" FLAGS[" + ",".join(flags) + "]") if flags else ""
print(f"AISUITE_HOOKS_REMOVED[{label}]: " + ",".join(removed_hooks) + tail)
PYEOF
done
```

Surface inline (compose one combined note across both files; silent only if every result was `AISUITE_ABSENT` / `AISUITE_HOOKS_NONE` with no `FLAGS`):
- Any `AISUITE_HOOKS_REMOVED[...]` — "Removed leftover AI Suite hooks that were erroring every turn (they pointed at a deleted `~/.aisuite/`): [name the events in plain words — e.g. 'Stop, PreToolUse']. Backed up your settings to `settings.json.scout-bak` first. **Restart Claude Code** to stop the errors."
- Any `FLAGS[...]` (on either a REMOVED or NONE result) — add a second line: "Also spotted leftover AI Suite config I did NOT touch: [cert path in `NODE_EXTRA_CA_CERTS` / an `aisuite` plugin marketplace + `@aisuite` plugins]. If npm/TLS behaves oddly, check the cert path; manage the plugins via `/plugin`."
- `AISUITE_PARSE_ERROR` / `AISUITE_NOT_OBJECT` / `AISUITE_BACKUP_FAILED` / `AISUITE_WRITE_FAILED` — one-line note ("couldn't safely scrub AI Suite hooks from [file] — left it untouched; if you see a `Stop hook error` about `~/.aisuite/`, remove those hook entries by hand"), proceed. Never abort.

## Done

Return to the dispatching prompt (fresh-install or refresh). This fragment writes only to the two `~/.claude` settings JSON files and never changes Scout's own state — no token needs to propagate to the done message beyond the restart note above.
