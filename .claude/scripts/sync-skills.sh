#!/bin/bash
# SF Demo Scout — Skill Sync Engine
# Reads .claude/skills-manifest.yaml, fetches each external skill from its
# source, prunes orphans, writes sync-state.
# Shared by install.sh (first-time install) and /sync-skills command (updates).
#
# Exit codes:
#   0 — success (all skills synced)
#   1 — manifest missing or unreadable
#   2 — one or more skills failed to sync (orphans still pruned)

set -u

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MANIFEST="$REPO_DIR/.claude/skills-manifest.yaml"
SKILLS_DIR="$REPO_DIR/.claude/skills"
STATE_FILE="$REPO_DIR/.claude/.sync-state.json"
TMP_DIR="/tmp/sf-demo-scout-sync"

if [ ! -f "$MANIFEST" ]; then
  echo "❌ Manifest not found at $MANIFEST" >&2
  exit 1
fi

mkdir -p "$TMP_DIR" "$SKILLS_DIR"

# --- Parse manifest via Python (YAML is not in bash's standard toolkit) ---
# Emits one line per skill: <name>|<source_name>|<path>|<source_type>|<source_url>|<raw_base_or_branch>
PARSED=$(python3 <<PYEOF
import sys
try:
    import yaml
except ImportError:
    sys.stderr.write("python3 yaml module missing. Install: pip3 install pyyaml\n")
    sys.exit(1)
with open("$MANIFEST") as f:
    m = yaml.safe_load(f)
sources = m.get("sources", {})
for s in m.get("skills", []):
    src_name = s["source"]
    src = sources.get(src_name, {})
    src_type = src.get("type", "")
    if src_type == "raw":
        extra = src.get("raw_base", "")
        url = src.get("repo", "")
    else:
        extra = src.get("branch", "main")
        url = src.get("repo", "")
    # Support both single 'path' and multi-file 'paths' list (raw sources only).
    if "paths" in s:
        joined = ";".join(s["paths"])
        print(f"{s['name']}|{src_name}|{joined}|{src_type}|{url}|{extra}|multi")
    else:
        print(f"{s['name']}|{src_name}|{s['path']}|{src_type}|{url}|{extra}|single")
PYEOF
)

if [ -z "$PARSED" ]; then
  echo "❌ Failed to parse manifest" >&2
  exit 1
fi

FAILED=()
SYNCED=()
CLONED_SOURCES=()

# --- Sync each skill ---
while IFS='|' read -r NAME SRC_NAME SKILL_PATH SRC_TYPE SRC_URL EXTRA MODE; do
  [ -z "$NAME" ] && continue
  TARGET="$SKILLS_DIR/$NAME"
  mkdir -p "$TARGET"

  if [ "$SRC_TYPE" = "raw" ]; then
    # Raw: EXTRA is raw_base.
    # single mode: SKILL_PATH is one file, fetched as SKILL.md at the skill root.
    # multi mode: SKILL_PATH is a ';'-separated list; first path is SKILL.md,
    # remainder keep their relative path under the skill root.
    if [ "$MODE" = "multi" ]; then
      IFS=';' read -ra PATH_LIST <<< "$SKILL_PATH"
      FIRST=1
      SKILL_FAILED=0
      for P in "${PATH_LIST[@]}"; do
        URL="$EXTRA/$P"
        if [ $FIRST -eq 1 ]; then
          DEST="$TARGET/SKILL.md"
          FIRST=0
        else
          # Strip the leading "<skill-name>/" segment if present so assets/foo.xml
          # lands at .claude/skills/<name>/assets/foo.xml, not .../<name>/<name>/assets/foo.xml.
          REL="${P#${NAME}/}"
          DEST="$TARGET/$REL"
          mkdir -p "$(dirname "$DEST")"
        fi
        if ! curl -fsSL "$URL" -o "$DEST"; then
          FAILED+=("$NAME ($URL)")
          SKILL_FAILED=1
          break
        fi
      done
      [ $SKILL_FAILED -eq 0 ] && SYNCED+=("$NAME")
    else
      URL="$EXTRA/$SKILL_PATH"
      if curl -fsSL "$URL" -o "$TARGET/SKILL.md"; then
        SYNCED+=("$NAME")
      else
        FAILED+=("$NAME ($URL)")
      fi
    fi
  elif [ "$SRC_TYPE" = "clone" ]; then
    CLONE_DIR="$TMP_DIR/$SRC_NAME"
    # Clone once per source per run
    if [[ ! " ${CLONED_SOURCES[*]:-} " =~ " $SRC_NAME " ]]; then
      if [ -d "$CLONE_DIR/.git" ]; then
        (cd "$CLONE_DIR" && git fetch --quiet --depth 1 origin "$EXTRA" && git reset --hard --quiet "origin/$EXTRA") \
          || { FAILED+=("$NAME (git fetch failed for $SRC_NAME)"); continue; }
      else
        rm -rf "$CLONE_DIR"
        git clone --depth 1 --branch "$EXTRA" --quiet "$SRC_URL" "$CLONE_DIR" \
          || { FAILED+=("$NAME (git clone failed for $SRC_NAME)"); continue; }
      fi
      CLONED_SOURCES+=("$SRC_NAME")
    fi
    SRC_PATH="$CLONE_DIR/$SKILL_PATH"
    if [ -d "$SRC_PATH" ]; then
      rm -rf "$TARGET"
      mkdir -p "$TARGET"
      cp -R "$SRC_PATH/"* "$TARGET/" 2>/dev/null
      SYNCED+=("$NAME")
    elif [ -f "$SRC_PATH" ]; then
      cp "$SRC_PATH" "$TARGET/"
      SYNCED+=("$NAME")
    else
      FAILED+=("$NAME (path not in clone: $SKILL_PATH)")
    fi
  else
    FAILED+=("$NAME (unknown source type: $SRC_TYPE)")
  fi
done <<< "$PARSED"

# --- Prune orphans: skills in manifest-expected folder that are no longer listed ---
EXPECTED_NAMES=$(echo "$PARSED" | cut -d'|' -f1 | sort -u)
# Never prune homegrown skills
HOMEGROWN_RE='^(demo-|pipeline-lessons$)'
PRUNED=()
if [ -d "$SKILLS_DIR" ]; then
  for DIR in "$SKILLS_DIR"/*/; do
    [ -d "$DIR" ] || continue
    FOLDER=$(basename "$DIR")
    if echo "$FOLDER" | grep -qE "$HOMEGROWN_RE"; then
      continue
    fi
    if ! echo "$EXPECTED_NAMES" | grep -qx "$FOLDER"; then
      rm -rf "$DIR"
      PRUNED+=("$FOLDER")
    fi
  done
fi

# --- Write sync-state: record last-synced upstream SHA per cloned source ---
mkdir -p "$(dirname "$STATE_FILE")"
{
  echo "{"
  echo "  \"synced_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
  echo "  \"sources\": {"
  FIRST=1
  for SRC_NAME in "${CLONED_SOURCES[@]:-}"; do
    [ -z "$SRC_NAME" ] && continue
    CLONE_DIR="$TMP_DIR/$SRC_NAME"
    SHA=$(cd "$CLONE_DIR" 2>/dev/null && git rev-parse HEAD 2>/dev/null || echo "unknown")
    [ $FIRST -eq 0 ] && echo ","
    printf "    \"%s\": \"%s\"" "$SRC_NAME" "$SHA"
    FIRST=0
  done
  # Raw sources: record synced_at only (no SHA available via raw URL)
  for SRC_NAME in $(echo "$PARSED" | awk -F'|' '$4=="raw"{print $2}' | sort -u); do
    [ $FIRST -eq 0 ] && echo ","
    printf "    \"%s\": \"raw\"" "$SRC_NAME"
    FIRST=0
  done
  echo ""
  echo "  }"
  echo "}"
} > "$STATE_FILE"

# --- Emit machine-readable summary on stdout ---
echo "SYNCED_COUNT=${#SYNCED[@]}"
echo "FAILED_COUNT=${#FAILED[@]}"
echo "PRUNED_COUNT=${#PRUNED[@]}"
for S in "${SYNCED[@]:-}"; do [ -n "$S" ] && echo "SYNCED=$S"; done
for F in "${FAILED[@]:-}"; do [ -n "$F" ] && echo "FAILED=$F"; done
for P in "${PRUNED[@]:-}"; do [ -n "$P" ] && echo "PRUNED=$P"; done

[ ${#FAILED[@]} -eq 0 ] || exit 2
exit 0
