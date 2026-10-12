#!/bin/bash
# Fast path for current clients on macOS. No cache text is ever executed.
# Other platforms or uncertain inputs use client-version.py's bounded probe.
scout_current_client_cached() {
  local executable cache resolved metadata binary_stat cache_stat cached_size
  local header binary mtime size version count=0 hit="" major minor patch
  if [ "${SCOUT_HOST+x}" = x ]; then
    [ "$SCOUT_HOST" = claude ] || return 1
  else
    [ "${CLAUDECODE:-}" = 1 ] && [ -z "${CODEX_THREAD_ID:-}" ] || return 1
  fi
  executable="${CLAUDE_CODE_EXECPATH:-}"
  if [ -z "$executable" ] && [ "${CLAUDE_CODE_ENTRYPOINT:-}" = cli ]; then
    executable=$(command -v claude) || return 1
  fi
  case "$executable" in /*) ;; *) return 1 ;; esac
  case "${CLAUDE_PLUGIN_DATA:-}" in /*) ;; *) return 1 ;; esac
  cache="$CLAUDE_PLUGIN_DATA/scout-client-versions.txt"
  [ -f "$cache" ] && [ ! -L "$cache" ] && [ -r "$cache" ] || return 1
  resolved=$(cd -P -- "${executable%/*}" 2>/dev/null && printf '%s/%s' "$PWD" "${executable##*/}") || return 1
  if [ -L "$resolved" ]; then
    resolved=$(realpath "$resolved" 2>/dev/null) || return 1
  fi
  case "$resolved" in *$'\n'*|*$'\r'*) return 1 ;; esac
  [ -f "$resolved" ] || return 1
  metadata=$(stat -f '%Fm %z' "$resolved" "$cache" 2>/dev/null) || return 1
  binary_stat=${metadata%%$'\n'*}
  cache_stat=${metadata#*$'\n'}
  [[ "$binary_stat" =~ ^[0-9]+\.[0-9]{9}\ [0-9]+$ ]] || return 1
  [[ "$cache_stat" =~ ^[0-9]+\.[0-9]{9}\ [0-9]+$ ]] || return 1
  cached_size=${cache_stat##* }
  [ "$cached_size" -le 16384 ] || return 1
  {
    IFS= read -r header || return 1
    [ "$header" = scout-client-versions-v1 ] || return 1
    while IFS= read -r binary || [ -n "$binary" ]; do
      IFS= read -r mtime && IFS= read -r size && IFS= read -r version || return 1
      count=$((count + 1))
      [ "$count" -le 16 ] || return 1
      case "$binary" in /*) ;; *) return 1 ;; esac
      [[ "$mtime" =~ ^[0-9]{1,24}$ && "$size" =~ ^[0-9]{1,24}$ ]] || return 1
      [[ "$version" =~ ^[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}$ ]] || return 1
      if [ "$binary" = "$resolved" ] && [ "$mtime $size" = "${binary_stat/./}" ]; then
        hit=$version
      fi
    done
  } < "$cache"
  [ -n "$hit" ] || return 1
  IFS=. read -r major minor patch <<< "$hit"
  # Older clients still use Python's cached observation to render the notice.
  ((10#$major > 2 || (10#$major == 2 && 10#$minor > 1) ||
     (10#$major == 2 && 10#$minor == 1 && 10#$patch >= 293)))
}
