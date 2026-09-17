#!/bin/bash

case "${1:-}" in
  node)
    TOOL_NAME=node
    STATUS_PREFIX=NODE
    ;;
  python)
    TOOL_NAME=python3
    STATUS_PREFIX=PYTHON
    ;;
  sf)
    TOOL_NAME=sf
    STATUS_PREFIX=SF_CLI
    ;;
  *)
    echo "usage: setup-bootstrap.sh node|python|sf" >&2
    exit 64
    ;;
esac

probe_tool() {
  PROBE_OUTPUT=$("$1" --version 2>/dev/null)
  PROBE_RC=$?
  PROBE_VERSION=""
  PROBE_STATE=invalid
  if [ "$PROBE_RC" -ne 0 ]; then
    return
  fi
  case "$TOOL_NAME" in
    node)
      if [[ "$PROBE_OUTPUT" =~ ^v([0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6})([-+][0-9A-Za-z.-]{1,64})?$ ]]; then
        PROBE_VERSION="${BASH_REMATCH[1]}${BASH_REMATCH[2]}"
        PROBE_STATE=valid
      fi
      ;;
    python3)
      if [[ "$PROBE_OUTPUT" =~ ^Python[[:space:]]([0-9]{1,6})\.([0-9]{1,6})\.([0-9]{1,6})((a|b|rc)[0-9]{1,6})?$ ]]; then
        PROBE_VERSION="${BASH_REMATCH[1]}.${BASH_REMATCH[2]}.${BASH_REMATCH[3]}${BASH_REMATCH[4]}"
        if [ "${BASH_REMATCH[1]}" -eq 3 ] && [ "${BASH_REMATCH[2]}" -ge 9 ]; then
          PROBE_STATE=valid
        else
          PROBE_STATE=unsupported
        fi
      fi
      ;;
    sf)
      if [[ "$PROBE_OUTPUT" =~ ^@salesforce/cli/([0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6})([[:space:]][[:print:]]+)?$ ]]; then
        PROBE_VERSION="${BASH_REMATCH[1]}"
        PROBE_STATE=valid
      fi
      ;;
  esac
}

TOOL_PATH=$(type -P "$TOOL_NAME" 2>/dev/null || true)
if [ -n "$TOOL_PATH" ]; then
  probe_tool "$TOOL_PATH"
  if [ "$PROBE_STATE" = valid ]; then
    echo "${STATUS_PREFIX}_PRESENT ($PROBE_VERSION)"
    exit 0
  fi
  if [ "$PROBE_STATE" = unsupported ] && [ "$TOOL_NAME" = python3 ]; then
    echo "PYTHON_UNSUPPORTED (found ${PROBE_VERSION:-unknown}; need Python 3.9+)"
  else
    echo "${STATUS_PREFIX}_UNVERIFIED (existing executable version could not be verified)"
  fi
  exit 1
fi

if [ "$TOOL_NAME" = sf ]; then
  INSTALLER=$(type -P npm 2>/dev/null || true)
  INSTALL_ARGS=(install @salesforce/cli --global)
  PREREQUISITE=npm
else
  INSTALLER=$(type -P brew 2>/dev/null || true)
  INSTALL_ARGS=(install "$TOOL_NAME")
  PREREQUISITE=brew
fi

if [ -z "$INSTALLER" ]; then
  echo "${STATUS_PREFIX}_UNAVAILABLE (${PREREQUISITE} prerequisite missing)"
  exit 1
fi

MKTEMP_EXE=$(type -P mktemp 2>/dev/null || true)
if [ -z "$MKTEMP_EXE" ] || [ ! -x /bin/rm ]; then
  echo "${STATUS_PREFIX}_UNAVAILABLE (private install log unavailable)"
  exit 1
fi
INSTALL_LOG=$("$MKTEMP_EXE" "${TMPDIR:-/tmp}/scout-${TOOL_NAME}-install.XXXXXX") || {
  echo "${STATUS_PREFIX}_UNAVAILABLE (private install log unavailable)"
  exit 1
}
cleanup() {
  /bin/rm -f -- "$INSTALL_LOG"
}
trap cleanup EXIT

echo "INSTALLING_${STATUS_PREFIX}"
"$INSTALLER" "${INSTALL_ARGS[@]}" >"$INSTALL_LOG" 2>&1
INSTALL_RC=$?
if [ "$INSTALL_RC" -ne 0 ]; then
  echo "${STATUS_PREFIX}_INSTALL_FAILED (installer exit $INSTALL_RC)"
  exit 1
fi

hash -r
TOOL_PATH=$(type -P "$TOOL_NAME" 2>/dev/null || true)
if [ -z "$TOOL_PATH" ]; then
  echo "${STATUS_PREFIX}_UNVERIFIED (installer exited 0; selected executable missing)"
  exit 1
fi
probe_tool "$TOOL_PATH"
if [ "$PROBE_STATE" != valid ]; then
  echo "${STATUS_PREFIX}_UNVERIFIED (installer exited 0; selected executable version could not be verified)"
  exit 1
fi
echo "${STATUS_PREFIX}_INSTALLED ($PROBE_VERSION)"
