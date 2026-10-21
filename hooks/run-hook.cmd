: << 'CMDBLOCK'
@echo off
rem Scout's hook launcher: one file that cmd.exe and sh each read their own way. To cmd.exe the first line is a
rem label, so it runs this half and stops at exit /b. To sh that line feeds everything up to CMDBLOCK to the
rem no-op command, so sh runs the half after it. Hooks only speed Scout up: when no Python 3.9 or later is
rem found, the launcher exits 0 and prints nothing. Its line endings stay LF, which cmd.exe reads correctly
rem as long as no label is jumped to, so this half has neither goto nor call.
setlocal EnableExtensions DisableDelayedExpansion
set "SCOUT_HOOK=%~1"
if /i not "%SCOUT_HOOK%"=="session_startup.py" if /i not "%SCOUT_HOOK%"=="team_updates.py" exit /b 0
if not exist "%~dp0%SCOUT_HOOK%" exit /b 0
rem Probing a Python must never make the install manager download one.
set "PYTHON_MANAGER_AUTOMATIC_INSTALL=false"
set "SCOUT_PY="
set "SCOUT_PY_ARG="
rem First py -3. Python's launcher has no Store stub, so its WindowsApps alias, from the install manager, counts.
set "SCOUT_TRY="
for %%D in ("%PATH:;=" "%") do if not defined SCOUT_TRY if exist "%%~D\py.exe" set "SCOUT_TRY=%%~D\py.exe"
if defined SCOUT_TRY ("%SCOUT_TRY%" -3 -c "import sys; sys.exit(sys.version_info < (3, 9))" <nul >nul 2>&1 && set "SCOUT_PY=%SCOUT_TRY%" && set "SCOUT_PY_ARG=-3")
rem Then python, then python3, skipping a WindowsApps folder: the copies there may be the Store's install stubs.
set "SCOUT_TRY="
if not defined SCOUT_PY for %%D in ("%PATH:;=" "%") do if not defined SCOUT_TRY for %%F in ("%%~D\python.exe") do if exist "%%~fF" for %%G in ("%%~dpF.") do if /i not "%%~nxG"=="WindowsApps" set "SCOUT_TRY=%%~fF"
if defined SCOUT_TRY ("%SCOUT_TRY%" -c "import sys; sys.exit(sys.version_info < (3, 9))" <nul >nul 2>&1 && set "SCOUT_PY=%SCOUT_TRY%")
set "SCOUT_TRY="
if not defined SCOUT_PY for %%D in ("%PATH:;=" "%") do if not defined SCOUT_TRY for %%F in ("%%~D\python3.exe") do if exist "%%~fF" for %%G in ("%%~dpF.") do if /i not "%%~nxG"=="WindowsApps" set "SCOUT_TRY=%%~fF"
if defined SCOUT_TRY ("%SCOUT_TRY%" -c "import sys; sys.exit(sys.version_info < (3, 9))" <nul >nul 2>&1 && set "SCOUT_PY=%SCOUT_TRY%")
if not defined SCOUT_PY exit /b 0
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"
"%SCOUT_PY%" %SCOUT_PY_ARG% -B "%~dp0%SCOUT_HOOK%"
exit /b 0
CMDBLOCK
# The sh half: macOS, Linux, and Git Bash on Windows. Claude Code sources this file with `.` (see
# claude-hooks.json, which does that so PowerShell can run the same command), so $0 may name the shell;
# the hook folder then comes from CLAUDE_PLUGIN_ROOT, which Claude Code sets for every hook.
scout_hook=${1-}
case $scout_hook in
  session_startup.py|team_updates.py) ;;
  *) exit 0 ;;
esac
scout_dir=
for scout_self in "$0" "${BASH_SOURCE:-}"; do
  case $scout_self in
    */run-hook.cmd) scout_dir=${scout_self%/*}; break ;;
  esac
done
if [ -z "$scout_dir" ] && [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
  scout_dir=${CLAUDE_PLUGIN_ROOT%/}/hooks
fi
[ -n "$scout_dir" ] && [ -f "$scout_dir/$scout_hook" ] || exit 0
PYTHONDONTWRITEBYTECODE=1
export PYTHONDONTWRITEBYTECODE
if [ "${OS-}" != Windows_NT ]; then
  command -v python3 >/dev/null 2>&1 || exit 0
  python3 -B "$scout_dir/$scout_hook"
  exit 0
fi
# Git Bash on Windows: the same search as the cmd.exe half, without starting a process per PATH entry.
PYTHONUTF8=1
PYTHON_MANAGER_AUTOMATIC_INSTALL=false
export PYTHONUTF8 PYTHON_MANAGER_AUTOMATIC_INSTALL
scout_probe='import sys; sys.exit(sys.version_info < (3, 9))'
scout_py=
scout_arg=
for scout_name in py python python3; do
  scout_try=
  scout_rest=$PATH:
  while [ -z "$scout_try" ] && [ -n "$scout_rest" ]; do
    scout_entry=${scout_rest%%:*}
    scout_rest=${scout_rest#*:}
    [ -n "$scout_entry" ] || continue
    case $scout_name:$scout_entry in
      python*:*/[Ww][Ii][Nn][Dd][Oo][Ww][Ss][Aa][Pp][Pp][Ss]|python*:*/[Ww][Ii][Nn][Dd][Oo][Ww][Ss][Aa][Pp][Pp][Ss]/) continue ;;
    esac
    if [ -e "$scout_entry/$scout_name.exe" ] || [ -h "$scout_entry/$scout_name.exe" ]; then
      scout_try=$scout_entry/$scout_name.exe
    fi
  done
  [ -n "$scout_try" ] || continue
  scout_flag=
  [ "$scout_name" != py ] || scout_flag=-3
  if "$scout_try" ${scout_flag:+"$scout_flag"} -c "$scout_probe" </dev/null >/dev/null 2>&1; then
    scout_py=$scout_try
    scout_arg=$scout_flag
    break
  fi
done
[ -n "$scout_py" ] || exit 0
"$scout_py" ${scout_arg:+"$scout_arg"} -B "$scout_dir/$scout_hook"
exit 0
