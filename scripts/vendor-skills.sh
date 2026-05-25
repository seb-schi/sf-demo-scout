#!/bin/bash
# SF Demo Scout — Skill Vendoring Script (maintainer-only)
# Reads skills-manifest.yaml from this plugin's root, shallow-clones each
# upstream source into /tmp, and copies declared skill paths into
# <plugin-root>/skills/<name>/. Run from anywhere — locates plugin root
# via $0. Maintainer reviews the resulting git diff and commits.
#
# Usage: bash scripts/vendor-skills.sh
#
# Exit codes:
#   0 — success (all skills vendored)
#   1 — manifest missing, plugin root unresolvable, or pyyaml missing
#   2 — one or more skills failed to vendor

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="$PLUGIN_ROOT/skills-manifest.yaml"
SKILLS_DIR="$PLUGIN_ROOT/skills"
TMP_DIR="/tmp/sf-demo-scout-vendor"

if [ ! -f "$MANIFEST" ]; then
  echo "❌ Manifest not found at $MANIFEST" >&2
  exit 1
fi

if ! python3 -c 'import yaml' 2>/dev/null; then
  echo "❌ python3 yaml module missing. Install: pip3 install --user pyyaml" >&2
  exit 1
fi

mkdir -p "$TMP_DIR" "$SKILLS_DIR"

PARSED=$(python3 <<PYEOF
import sys, yaml
with open("$MANIFEST") as f:
    m = yaml.safe_load(f)
sources = m.get("sources", {})
for s in m.get("skills", []):
    src_name = s["source"]
    src = sources.get(src_name, {})
    branch = src.get("branch", "main")
    url = src.get("repo", "")
    print(f"{s['name']}|{src_name}|{s['path']}|{url}|{branch}")
PYEOF
)

if [ -z "$PARSED" ]; then
  echo "❌ Failed to parse manifest" >&2
  exit 1
fi

FAILED=()
VENDORED=()
CLONED_SOURCES=()

while IFS='|' read -r NAME SRC_NAME SKILL_PATH SRC_URL BRANCH; do
  [ -z "$NAME" ] && continue
  CLONE_DIR="$TMP_DIR/$SRC_NAME"
  if [[ ! " ${CLONED_SOURCES[*]:-} " =~ " $SRC_NAME " ]]; then
    rm -rf "$CLONE_DIR"
    if git clone --depth 1 --branch "$BRANCH" --quiet "$SRC_URL" "$CLONE_DIR"; then
      SHA=$(cd "$CLONE_DIR" && git rev-parse --short HEAD)
      echo "CLONED $SRC_NAME @ $BRANCH ($SHA)"
      CLONED_SOURCES+=("$SRC_NAME")
    else
      FAILED+=("$NAME (git clone failed for $SRC_NAME)")
      continue
    fi
  fi
  SRC_PATH="$CLONE_DIR/$SKILL_PATH"
  TARGET="$SKILLS_DIR/$NAME"
  if [ -d "$SRC_PATH" ]; then
    rm -rf "$TARGET"
    mkdir -p "$TARGET"
    cp -R "$SRC_PATH/"* "$TARGET/" 2>/dev/null
    VENDORED+=("$NAME")
  else
    FAILED+=("$NAME (path not in clone: $SKILL_PATH)")
  fi
done <<< "$PARSED"

echo ""
echo "VENDORED_COUNT=${#VENDORED[@]}"
echo "FAILED_COUNT=${#FAILED[@]}"
for V in "${VENDORED[@]:-}"; do [ -n "$V" ] && echo "VENDORED=$V"; done
for F in "${FAILED[@]:-}"; do [ -n "$F" ] && echo "FAILED=$F"; done

echo ""
echo "Review the diff under $SKILLS_DIR/ and commit when ready."

[ ${#FAILED[@]} -eq 0 ] || exit 2
exit 0
