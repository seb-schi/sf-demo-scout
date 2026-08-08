#!/bin/bash
# SF Demo Scout — Maintainer Uninstall Script
# Wipes all local Scout state for clean reinstall testing.
# Idempotent. Default preserves SE workspace data (orgs/, .sf/);
# pass --wipe-orgs to nuke the whole workspace.
#
# Usage:
#   bash ~/claude-projects/sf-demo-scout-dev/scripts/scout-uninstall.sh
#   bash ~/claude-projects/sf-demo-scout-dev/scripts/scout-uninstall.sh --wipe-orgs

set -u

WIPE_ORGS=0
WIPE_INTERNAL=0
for arg in "$@"; do
  case "$arg" in
    --wipe-orgs) WIPE_ORGS=1 ;;
    --wipe-internal) WIPE_INTERNAL=1 ;;
    -h|--help)
      echo "Usage: $0 [--wipe-orgs] [--wipe-internal]"
      echo "  --wipe-orgs       Also remove ~/claude-projects/sf-demo-scout/ (otherwise preserved)"
      echo "  --wipe-internal   Also wipe the scout-internal maintainer plugin (default: preserved)"
      exit 0
      ;;
    *) echo "Unknown arg: $arg (use --help)"; exit 1 ;;
  esac
done

echo "=== Scout Uninstall ==="
echo ""

# 1. Wipe plugin on-disk artifacts
echo "[1/6] Removing plugin on-disk artifacts..."
rm -rf "$HOME/.claude/plugins/marketplaces/scout"
rm -rf "$HOME/.claude/plugins/cache/scout"
echo "    ✓ marketplaces/scout, cache/scout"
if [ "$WIPE_INTERNAL" = "1" ]; then
  rm -rf "$HOME/.claude/plugins/marketplaces/scout-internal"
  rm -rf "$HOME/.claude/plugins/cache/scout-internal"
  echo "    ✓ marketplaces/scout-internal, cache/scout-internal (--wipe-internal)"
else
  echo "    · scout-internal preserved (pass --wipe-internal to remove)"
fi

# 2. Surgically remove Scout from CC plugin registries
echo ""
echo "[2/6] Scrubbing CC plugin registries..."
python3 - "$WIPE_INTERNAL" <<'PYEOF'
import json, pathlib, sys

home = pathlib.Path.home()
wipe_internal = sys.argv[1] == "1"

def scrub(path, mutator):
    if not path.exists():
        print(f"    · {path.name} absent — skipped")
        return
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        print(f"    ⚠ {path.name} parse error: {e} — skipped")
        return
    mutator(data)
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"    ✓ {path.name} scrubbed")

# installed_plugins.json
def m1(d):
    if "plugins" in d:
        d["plugins"].pop("sf-demo-scout@scout", None)
        if wipe_internal:
            d["plugins"].pop("sf-demo-scout-internal@scout-internal", None)
scrub(home / ".claude/plugins/installed_plugins.json", m1)

# known_marketplaces.json
def m2(d):
    if isinstance(d, dict):
        d.pop("scout", None)
        if wipe_internal:
            d.pop("scout-internal", None)
scrub(home / ".claude/plugins/known_marketplaces.json", m2)

# settings.json
def m3(d):
    for k in ("enabledPlugins", "extraKnownMarketplaces"):
        if k in d and isinstance(d[k], dict):
            d[k].pop("sf-demo-scout@scout", None)
            d[k].pop("scout", None)
            if wipe_internal:
                d[k].pop("sf-demo-scout-internal@scout-internal", None)
                d[k].pop("scout-internal", None)
scrub(home / ".claude/settings.json", m3)
PYEOF

# 3. Scrub ~/.claude.json (CC's per-user state — separate from .claude/settings.json)
echo ""
echo "[3/6] Scrubbing ~/.claude.json Scout residue..."
python3 <<'PYEOF'
import json, pathlib, re

p = pathlib.Path.home() / ".claude.json"
if not p.exists():
    print("    · ~/.claude.json absent — skipped")
else:
    try:
        d = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        print(f"    ⚠ parse error: {e} — skipped")
    else:
        removed = 0
        # githubRepoPaths: drop seb-schi/sf-demo-scout*
        if isinstance(d.get("githubRepoPaths"), dict):
            for k in list(d["githubRepoPaths"].keys()):
                if "sf-demo-scout" in k or "sf-demo-prep" in k or "sf-demo-autopilot" in k:
                    del d["githubRepoPaths"][k]
                    removed += 1
        # projects: drop entries whose path contains sf-demo-scout
        if isinstance(d.get("projects"), dict):
            for k in list(d["projects"].keys()):
                if "sf-demo-scout" in k or "sf-demo-prep" in k or "sf-demo-autopilot" in k:
                    del d["projects"][k]
                    removed += 1
        # skillUsage: drop scout-related accumulators
        SCOUT_SKILL_RE = re.compile(
            r"(^|:)(demo-scout|setup-demo-scout|scout-sparring|scout-building|"
            r"scout-setup|scout-sync-skills|switch-org|"
            r"project-sparring|project-building)$|"
            r"^sf-demo-scout(-internal)?:"
        )
        if isinstance(d.get("skillUsage"), dict):
            for k in list(d["skillUsage"].keys()):
                if SCOUT_SKILL_RE.search(k):
                    del d["skillUsage"][k]
                    removed += 1
        p.write_text(json.dumps(d, indent=2) + "\n")
        print(f"    ✓ Removed {removed} Scout-related keys from ~/.claude.json")
PYEOF

# 4. Wipe workspace config marker
echo ""
echo "[4/6] Removing ~/.config/sf-demo-scout/..."
rm -rf "$HOME/.config/sf-demo-scout"
echo "    ✓ config dir removed"

# 5. Strip .zshrc managed block
echo ""
echo "[5/6] Stripping .zshrc managed block..."
ZSHRC="$HOME/.zshrc"
if [ -f "$ZSHRC" ]; then
  python3 - "$ZSHRC" <<'PYEOF'
import sys, re
path = sys.argv[1]
BEGIN = "# BEGIN SF-DEMO-SCOUT"
END = "# END SF-DEMO-SCOUT"
with open(path) as f:
    lines = f.readlines()
out = []
skip = False
removed = 0
for line in lines:
    s = line.rstrip("\n")
    if s == BEGIN:
        skip = True
        removed += 1
        continue
    if s == END:
        skip = False
        removed += 1
        continue
    if not skip:
        out.append(line)
    else:
        removed += 1
# trim trailing blanks
while out and out[-1].strip() == "":
    out.pop()
with open(path, "w") as f:
    f.write("".join(out))
    if out and not out[-1].endswith("\n"):
        f.write("\n")
if removed > 0:
    print(f"    ✓ Removed {removed} lines from .zshrc managed block")
else:
    print("    · No managed block found in .zshrc")
PYEOF
else
  echo "    · ~/.zshrc absent — skipped"
fi

# 6. Workspace data (gated on --wipe-orgs)
echo ""
if [ "$WIPE_ORGS" = "1" ]; then
  echo "[6/6] Wiping ~/claude-projects/sf-demo-scout/ (--wipe-orgs)..."
  rm -rf "$HOME/claude-projects/sf-demo-scout"
  echo "    ✓ workspace removed"
else
  echo "[6/6] Workspace preserved at ~/claude-projects/sf-demo-scout/"
  echo "    (orgs/ + .sf/ kept; pass --wipe-orgs to remove)"
fi

echo ""
echo "=== Uninstall complete ==="
echo ""
echo "To reinstall, in a fresh Claude Code session:"
echo "  /plugin marketplace add https://github.com/seb-schi/sf-demo-scout.git"
echo "  /plugin install sf-demo-scout@scout"
echo "  (restart CC)"
echo "  /scout-setup"
echo ""
