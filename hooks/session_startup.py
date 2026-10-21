#!/usr/bin/env python3
"""Scout's session-start hook: standing rules, setup and official-plugin notices, and the active org.

Claude Code runs it at each session start, through run-hook.cmd. Host-specific checks never consult another host.
Outside the SE's workspace it prints only the notices that apply in every folder; inside, it adds the default
org's evidence, which it caches privately for the day. It never stops a session: a check that fails becomes a
warning line, or nothing. The SCOUT_* environment overrides are narrow test seams.
"""
from __future__ import annotations

import datetime
import errno
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Dict, List, Optional

sys.dont_write_bytecode = True
HOOK_DIR = Path(__file__).resolve().parent
SCRIPTS = HOOK_DIR.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import scout_portable  # noqa: E402  (ships with the other helpers)

INFO, WARN, OK = "ℹ️", "⚠️", "✅"  # the banner's emoji, exactly as before
DASH = "—"

# A broken setup is Scout's to repair: the session runs setup itself instead of asking the SE to (AGENTS.md, Setup).
SELF_REPAIR = ("Before the first Scout task or Salesforce change in this session, tell the SE in one line that Scout "
               "is repairing its setup, then run `/scout-setup self-repair` yourself (the `sf-demo-scout:scout-setup` "
               "skill with argument `self-repair`), once.")
CONFLICT_NOTICE = (f"## {INFO} Two copies of Salesforce's official plugin are switched on. {SELF_REPAIR} "
                   "It asks the SE before switching the extra one off.\n\n")
MISSING_NOTICE = f"## {INFO} Scout builds with Salesforce's official plugins, which aren't set up yet. {SELF_REPAIR}\n\n"
RULES_LIMIT = 600
READY = ("---\n**Ready.**\n"
         f"  /scout           {DASH} Scout 2.0: spar, build, fix or prep a demo in one session\n"
         f"  /scout-setup     {DASH} install, refresh, or repair Scout\n"
         "  (/scout-sparring and /scout-building are classic names; they now open /scout.)\n")

CLIENT_FLOOR = (2, 1, 293)
CLIENT_CACHE_HEADER = "scout-client-versions-v1"
CLIENT_CACHE_LIMIT = 16384
LEGACY_CACHES = ("org-list.????-??-??", "org-display-*.????-??-??", "mcp-list.????-??-??",
                 "org-list.json", "mcp-list.json")
DISPLAY_PROVENANCE = "sf org display --json"
CONFIG_PROVENANCE = "sf config get target-org --json"

# Claude Code gives this hook 30 seconds (claude-hooks.json); the probes share a smaller budget, so the banner is
# always printed before that. A cold Salesforce CLI start takes seconds on Windows, so its bounds are longer there.
BUDGET_SECONDS = 26.0


def bounds() -> Dict[str, float]:
    if scout_portable.windows():
        return {"official": 6.0, "network": 10.0, "client": 8.0, "version": 6.0}
    return {"official": 3.0, "network": 6.0, "client": 5.0, "version": 5.0}


class Clock:
    def __init__(self, budget: float = BUDGET_SECONDS) -> None:
        self.deadline = time.monotonic() + budget

    def bound(self, seconds: float) -> float:
        return max(0.0, min(seconds, self.deadline - time.monotonic()))


def run_bounded(seconds: float, dest: str, argv: List[str], env: Optional[dict] = None) -> int:
    """Run `argv` with stdout in the file `dest` and stderr discarded, ending its whole process tree after
    `seconds`. The status keeps the old shell timer's meanings: 124 timed out, 125 the runner failed, 127 the
    command is unavailable, 128+N ended by signal N."""
    if seconds < 0.5:
        return 124  # the budget is spent; starting a probe now would outlive the hook
    try:
        out = open(dest, "wb")
    except OSError:
        return 125
    with out:
        try:
            proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.DEVNULL, env=env,
                                    **scout_portable.process_group_options())
        except (FileNotFoundError, PermissionError, NotADirectoryError):
            return 127
        except OSError as error:
            return 127 if error.errno == errno.ENOEXEC else 125
        except (ValueError, subprocess.SubprocessError):
            return 125
        try:
            status = proc.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            scout_portable.kill_tree(proc)
            return 124
        except BaseException:
            scout_portable.kill_tree(proc)  # the hook itself is being stopped: take the probe with it
            raise
    return 128 - status if status < 0 else status


def temp_file(prefix: str, folder: Optional[str] = None) -> Optional[str]:
    try:
        descriptor, name = tempfile.mkstemp(prefix=prefix, dir=folder)
    except OSError:
        return None
    os.close(descriptor)
    return name


def unlink(path: Optional[str]) -> None:
    if path:
        try:
            os.unlink(path)
        except OSError:
            pass


def read_bounded(path: str, limit: int) -> Optional[bytes]:
    try:
        with open(path, "rb") as stream:
            return stream.read(limit + 1)
    except OSError:
        return None


def home_join(*parts: str) -> str:
    """A path under the home folder: "$HOME/..." on macOS and Linux, as the shell hook had it, and the user
    profile on Windows."""
    if scout_portable.windows():
        return os.path.join(str(Path.home()), *parts)
    return os.environ.get("HOME", "") + "/" + "/".join(parts)


def launch_dir() -> str:
    """The folder the session started in, as the shell saw it: $PWD when it names the current folder."""
    try:
        cwd = os.getcwd()
    except OSError:
        return os.environ.get("PWD", "")
    logical = os.environ.get("PWD", "")
    if os.path.isabs(logical) and not {".", ".."} & set(re.split(r"[\\/]", logical)):
        try:
            if os.path.samefile(logical, cwd):
                return logical
        except OSError:
            pass
    return cwd


def same_folder(first: str, second: str) -> bool:
    """Whether the session started in the workspace. On Windows one folder has several spellings: any letter case,
    an 8.3 short name such as RUNNER~1, a junction on the way. There the folders themselves are compared when both
    exist, else their normalised names. Elsewhere the names are compared exactly, as the shell hook did."""
    if scout_portable.windows():
        try:
            return os.path.samefile(first, second)
        except (OSError, ValueError):
            return os.path.normcase(os.path.normpath(first)) == os.path.normcase(os.path.normpath(second))
    return first == second


def private(path: str, mode: int, kind) -> bool:
    """`path` is a `kind` of its own (not a link) that only this user can use. Windows reports neither real
    permission bits nor an owner through os.stat, so there the files' place in the user's profile does it."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if not kind(info.st_mode):
        return False
    if scout_portable.windows():
        return True
    return stat.S_IMODE(info.st_mode) == mode and info.st_uid == os.getuid()


class EvidenceFailed(Exception):
    """The startup-evidence helper rejected the input, or couldn't be used."""


class Evidence:
    """startup-evidence.py's rules, applied in this process: one Python start for the whole evidence pass."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.ready = os.path.isfile(path)
        self._helper: Optional[dict] = None
        self._loaded = False

    def helper(self) -> dict:
        if not self._loaded:
            self._loaded = True
            if self.ready:
                try:
                    self._helper = runpy.run_path(self.path, run_name="scout_startup_evidence")
                except (Exception, SystemExit):  # a broken helper fails each call, as its process used to
                    self._helper = None
        if self._helper is None:
            raise EvidenceFailed()
        return self._helper

    def call(self, function, *args):
        try:
            return function(self.helper(), *args)
        except EvidenceFailed:
            raise
        except Exception as error:  # the helper exited 65, or broke: either way, no evidence
            raise EvidenceFailed() from error

    @staticmethod
    def _text(helper: dict, data: Optional[bytes]) -> str:
        if data is None or len(data) > helper["MAX_INPUT_BYTES"]:
            raise EvidenceFailed()
        return data.decode("utf-8")

    def key(self, target: str) -> str:
        return self.call(lambda h: hashlib.sha256(h["safe_text"](target, "target").encode("utf-8")).hexdigest())

    def normalize(self, kind: str, raw: Optional[bytes], today: str, provenance: str,
                  target: Optional[str] = None) -> bytes:
        def run(h):
            text = self._text(h, raw)
            base = h["metadata"](kind, today, provenance)
            result = h["require_success"](h["parse_json"](text))
            if kind == "config":
                value = h["normalize_config"](result, base)
            else:
                value = h["normalize_display"](result, base, target)
            return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        return self.call(run)

    def validate(self, kind: str, data: Optional[bytes], today: str, target: Optional[str] = None) -> dict:
        def run(h):
            payload = h["parse_json"](self._text(h, data))
            h["validate_payload"](payload, kind, today, target)
            return payload
        return self.call(run)

    def field(self, kind: str, data: Optional[bytes], today: str, name: str, target: Optional[str] = None) -> str:
        """One field of validated evidence, or "" when the evidence doesn't validate."""
        def run(h):
            if name not in h["FIELDS"][kind]:
                raise EvidenceFailed()
            value = self.validate(kind, data, today, target).get(name, "")
            if isinstance(value, str):
                h["safe_text"](value, name, allow_empty=True)
            elif type(value) is not int:
                raise EvidenceFailed()
            return str(value)
        try:
            return self.call(run)
        except EvidenceFailed:
            return ""

    def hook_output(self, floor_line: str, context: str) -> str:
        def run(h):
            self._text(h, context.encode("utf-8"))
            return json.dumps({"systemMessage": floor_line, "hookSpecificOutput": {
                "hookEventName": "SessionStart", "additionalContext": context}})
        return self.call(run)


class ProgramEvidence(Evidence):
    """Another helper named through SCOUT_STARTUP_EVIDENCE: a program, run for each call with the arguments the
    shell hook gave it, since it may not be safe to import."""

    def program(self, arguments: List[str], data: Optional[bytes]) -> bytes:
        if not self.ready or data is None:
            raise EvidenceFailed()
        try:
            result = subprocess.run([sys.executable, "-B", self.path, *arguments], input=data, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                                    timeout=30, check=False)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise EvidenceFailed() from error
        if result.returncode != 0:
            raise EvidenceFailed()
        return result.stdout

    def text(self, arguments: List[str], data: Optional[bytes]) -> str:
        # A Python program on Windows ends its lines with \r\n: one line ending, normalised here, comes off.
        return self.program(arguments, data).decode("utf-8", "replace").replace("\r\n", "\n").rstrip("\n")

    @staticmethod
    def scope(kind: str, today: str, target: Optional[str]) -> List[str]:
        return [kind, "--collected-date", today] + (["--target", target] if target else [])

    def key(self, target: str) -> str:
        return self.text(["key", target], b"")

    def normalize(self, kind: str, raw: Optional[bytes], today: str, provenance: str,
                  target: Optional[str] = None) -> bytes:
        return self.program(["normalize", *self.scope(kind, today, target), "--provenance", provenance], raw)

    def validate(self, kind: str, data: Optional[bytes], today: str, target: Optional[str] = None) -> dict:
        self.program(["validate", *self.scope(kind, today, target)], data)
        return {}

    def field(self, kind: str, data: Optional[bytes], today: str, name: str, target: Optional[str] = None) -> str:
        try:
            return self.text(["field", *self.scope(kind, today, target), "--field", name], data)
        except EvidenceFailed:
            return ""

    def hook_output(self, floor_line: str, context: str) -> str:
        return self.text(["hook-output", "--floor-line", floor_line], context.encode("utf-8"))


def evidence_for(path: str) -> Evidence:
    """The shipped helper is importable, so its rules run in this process; any other file is run as a program."""
    try:
        shipped = os.path.isfile(path) and os.path.samefile(path, SCRIPTS / "startup-evidence.py")
    except OSError:
        shipped = False
    return Evidence(path) if shipped else ProgramEvidence(path)


def current_client_cached() -> bool:
    """True when Scout's version cache shows this Claude client is current, so the version probe can be skipped.

    It reads the cache client-version.py writes, and every uncertain input means no: the probe then runs.
    """
    env = os.environ
    if "SCOUT_HOST" in env:
        if env["SCOUT_HOST"] != "claude":
            return False
    elif env.get("CLAUDECODE") != "1" or env.get("CODEX_THREAD_ID"):
        return False
    executable = env.get("CLAUDE_CODE_EXECPATH", "")
    if not executable and env.get("CLAUDE_CODE_ENTRYPOINT") == "cli":
        executable = shutil.which("claude") or ""
    data = env.get("CLAUDE_PLUGIN_DATA", "")
    if not os.path.isabs(executable) or not os.path.isabs(data):
        return False
    cache = os.path.join(data, "scout-client-versions.txt")
    try:
        cache_info = os.lstat(cache)
        if not stat.S_ISREG(cache_info.st_mode) or not os.access(cache, os.R_OK):
            return False
        resolved = os.path.realpath(executable)
        if "\n" in resolved or "\r" in resolved:
            return False
        binary_info = os.stat(resolved)
        if not stat.S_ISREG(binary_info.st_mode) or binary_info.st_mtime_ns < 0:
            return False
        if cache_info.st_size > CLIENT_CACHE_LIMIT:
            return False
        with open(cache, "rb") as stream:
            text = stream.read().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    seconds, nanoseconds = divmod(binary_info.st_mtime_ns, 10 ** 9)
    fingerprint = f"{seconds}{nanoseconds:09d} {binary_info.st_size}"
    if not text.endswith("\n"):
        return False  # each line, the last included, ends with a newline
    header, *records = text[:-1].split("\n")
    if header != CLIENT_CACHE_HEADER or len(records) % 4 or len(records) // 4 > 16:
        return False
    hit = ""
    for offset in range(0, len(records), 4):
        binary, mtime, size, version = records[offset:offset + 4]
        if (not os.path.isabs(binary) or not re.fullmatch(r"[0-9]{1,24}", mtime)
                or not re.fullmatch(r"[0-9]{1,24}", size)
                or not re.fullmatch(r"[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}", version)):
            return False  # even corruption after a matching entry fails open
        if binary == resolved and f"{mtime} {size}" == fingerprint:
            hit = version
    # Older clients still use Python's cached observation to render the notice.
    return bool(hit) and tuple(int(part) for part in hit.split(".")) >= CLIENT_FLOOR


def client_floor(clock: Clock) -> str:
    """client-version.py's floor notice for an outdated Claude client, or ""."""
    out = temp_file("scout-client.")
    if out is None:
        return ""
    try:
        status = run_bounded(clock.bound(bounds()["client"]), out,
                             [sys.executable, "-B", str(SCRIPTS / "client-version.py"), "floor"])
        data = read_bounded(out, 65536)
    finally:
        unlink(out)
    if status != 0 or data is None:
        return ""
    return data.decode("utf-8", "replace").rstrip("\n")


def rules_block(root: str) -> str:
    """The standing-rules notice, naming AGENTS.md under the plugin root: quoted for the reader, never
    evaluated. It needs an absolute root on one line, macOS or Windows form, and fits in 600 characters."""
    if not (root.startswith("/") or re.match(r"[A-Za-z]:[\\/]", root)) or "\n" in root or "\r" in root:
        return ""
    if root.endswith("/") or (root.endswith("\\") and not root.startswith("/")):
        root = root[:-1]
    path = (root + "/AGENTS.md").replace("\\", "\\\\").replace('"', '\\"')
    block = ("Scout is installed. Before any Salesforce org change, including a quick fix outside a Scout command, "
             'read "' + path + '" and follow it.\nGet the SE\'s explicit confirmation before:\n'
             "- Delete existing metadata or records\n- Modify existing profiles or permission sets\n"
             "- Touch anything prefixed `sb_` or `managed__`")
    return block if len(block) + 2 <= RULES_LIMIT else ""


def active_host() -> str:
    script = os.environ.get("SCOUT_MCP_STATUS_SCRIPT") or str(SCRIPTS / "setup-mcp-status.py")
    if not os.path.isfile(script):
        return "unknown"
    try:
        return str(runpy.run_path(script, run_name="scout_mcp_status")["active_host"]())
    except (Exception, SystemExit):
        return ""


def official_notice(host: str, clock: Clock) -> str:
    """Salesforce's official plugins, which Scout builds with (Claude only; it never blocks). A client notice, so
    it applies in every folder: an SE whose Scout updated while they work outside the workspace still gets setup
    repaired. Local reads only, but bounded anyway: a stalled config folder must never stall the session start."""
    script = os.environ.get("SCOUT_OFFICIAL_SCRIPT") or str(SCRIPTS / "scout_official.py")
    if host != "claude" or not os.path.isfile(script):
        return ""
    out = temp_file("scout-official.")
    if out is None:
        return ""
    try:
        run_bounded(clock.bound(bounds()["official"]), out,
                    [sys.executable, "-B", script, "resolve", "--host", "claude", "--plugin", "salesforce-development",
                     "--launch-dir", launch_dir()], env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        data = read_bounded(out, 4 * 1024 * 1024)
    finally:
        unlink(out)
    try:
        state = str(json.loads((data or b"").decode("utf-8"))["state"]).rstrip("\n")
    except (ValueError, KeyError, TypeError, IndexError):
        state = ""
    if state in ("installed", ""):
        return ""
    return CONFLICT_NOTICE if state == "conflict" else MISSING_NOTICE


def update_notice(host: str, clock: Clock) -> str:
    """One line when a newer Scout release is out (scripts/scout_version.py asks GitHub at most once a day, and
    never blocks: offline or unknown says nothing)."""
    script = os.environ.get("SCOUT_VERSION_SCRIPT") or str(SCRIPTS / "scout_version.py")
    if os.environ.get("SCOUT_NO_UPDATE_CHECK") == "1" or not os.path.isfile(script):
        return ""
    out = temp_file("scout-version.")
    if out is None:
        return ""
    try:
        run_bounded(clock.bound(bounds()["version"]), out,
                    [sys.executable, "-B", script, "--host", host if host in ("claude", "codex", "cursor") else "unknown"],
                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        data = read_bounded(out, 64 * 1024)
    finally:
        unlink(out)
    line = (data or b"").decode("utf-8", errors="replace").strip()
    if not line.startswith("SCOUT_UPDATE ") or "\n" in line:
        return ""
    return f"## {INFO} {line[len('SCOUT_UPDATE '):]}\n\n"


def failure_reason(status: str) -> str:
    if status == "malformed":
        return "malformed evidence"
    if status == "cache-write":
        return "cache update failed"
    if not status.startswith("exit:"):
        return "no usable evidence"
    code = status[len("exit:"):]
    if code == "124":
        return "timed out"
    if code == "125":
        return "probe runner failed"
    if code == "127":
        return "command unavailable"
    if code.isdigit() and int(code) >= 128 and not scout_portable.windows():
        return f"terminated by signal {int(code) - 128}"
    return f"exit {code}"


def sf_probe(args: List[str]) -> Optional[List[str]]:
    """The Salesforce CLI command for one probe, or None when no CLI can be run (counted as unavailable)."""
    executable = shutil.which("sf")
    if executable is None:
        return None
    return scout_portable.sf_command(executable, args)


class Startup:
    """The workspace checks: the default org's evidence, through a private cache and a private runtime folder."""

    def __init__(self, evidence: Evidence, clock: Clock) -> None:
        self.evidence, self.clock = evidence, clock
        self.cache_dir = os.environ.get("SCOUT_CACHE_DIR") or home_join(".cache", "sf-demo-scout")
        runtime = os.environ.get("SCOUT_RUNTIME_DIR") or (
            tempfile.gettempdir() if scout_portable.windows() else os.environ.get("TMPDIR") or "/tmp")
        self.runtime_base = runtime
        self.config_file = os.environ.get("SCOUT_CONFIG_FILE") or home_join(".config", "sf-demo-scout", "config.json")
        network = os.environ.get("SCOUT_NETWORK_TIMEOUT", "")
        self.network = float(network) if re.fullmatch(r"[0-9]{1,4}", network) else bounds()["network"]
        self.today = datetime.date.today().isoformat()
        self.nocache = bool(os.environ.get("SCOUT_HOOK_NOCACHE"))
        self.run_dir: Optional[str] = None
        self.cache_ready = False
        self.status: Dict[str, str] = {}

    def cache_path(self, key: str) -> str:
        return os.path.join(self.cache_dir, key + ".json")

    def prepare(self, output: List[str]) -> None:
        if not self.evidence.ready:
            output.append(f"## {WARN} Startup evidence helper unavailable; Salesforce state was not inferred.\n\n")
        if not os.path.lexists(self.cache_dir):
            try:
                os.makedirs(self.cache_dir, 0o700)
            except OSError:
                pass
        if os.path.isdir(self.cache_dir) and not os.path.islink(self.cache_dir):
            try:
                os.chmod(self.cache_dir, 0o700)
            except OSError:
                pass
            self.cache_ready = private(self.cache_dir, 0o700, stat.S_ISDIR)
        if self.cache_ready:
            self.remove_legacy_caches()
        else:
            output.append(f"## {WARN} Startup evidence cache unavailable; live state may be incomplete.\n\n")
        if not os.path.isdir(self.runtime_base) and not os.path.islink(self.runtime_base):
            try:
                os.makedirs(self.runtime_base, 0o700)
            except OSError:
                pass
        if os.path.isdir(self.runtime_base):
            # /tmp is a symlink on macOS: resolve an existing base, then make a unique private folder in it.
            try:
                self.run_dir = scout_portable.private_tempdir("scout-startup.", self.runtime_base)
            except OSError:
                self.run_dir = None
        if self.run_dir is None:
            self.cache_ready = False
            output.append(f"## {WARN} Startup evidence runtime unavailable; live state was not collected.\n\n")

    def cleanup(self) -> None:
        if self.run_dir:
            shutil.rmtree(self.run_dir, ignore_errors=True)

    def remove_legacy_caches(self) -> None:
        """Remove only Scout's known legacy cache names, including the org-list and MCP caches startup no longer
        writes; unrelated files are untouched."""
        try:
            entries = list(os.scandir(self.cache_dir))
        except OSError:
            return
        for entry in entries:
            if any(fnmatch.fnmatchcase(entry.name, pattern) for pattern in LEGACY_CACHES):
                try:
                    if entry.is_file(follow_symlinks=False):
                        os.unlink(entry.path)
                except OSError:
                    pass

    def cache_valid(self, key: str, kind: str, target: Optional[str]) -> bool:
        file = self.cache_path(key)
        if not private(file, 0o600, stat.S_ISREG):
            return False
        try:
            self.evidence.validate(kind, read_bounded(file, 4 * 1024 * 1024), self.today, target)
        except EvidenceFailed:
            return False
        return True

    def discard(self, file: str) -> None:
        if os.path.isfile(file) or os.path.islink(file):
            unlink(file)

    def probe(self, seconds: float, dest: str, args: List[str]) -> int:
        try:
            argv = sf_probe(args)
        except ValueError:
            return 125  # the CLI could only run in a way that would change these arguments
        if argv is None:
            return 127
        return run_bounded(self.clock.bound(seconds), dest, argv)

    def cache_fill(self, key: str, kind: str, provenance: str, target: str, args: List[str]) -> None:
        """Probe into the day's cache. A needed or forced refresh supersedes prior evidence before the probe, and
        evidence is normalized before it's published."""
        file = self.cache_path(key)
        if not self.nocache and self.cache_valid(key, kind, target):
            self.status[key] = "cached"
            return
        self.discard(file)
        if os.path.isdir(file) and not os.path.islink(file):
            self.status[key] = "cache-write"
            return
        raw = temp_file("raw.", self.run_dir)
        # Staged beside the destination, so the final rename stays on one file system.
        normalized = temp_file(".normalized.", self.cache_dir) if raw else None
        if raw is None or normalized is None:
            unlink(raw)
            self.status[key] = "cache-write"
            return
        code = self.probe(self.network, raw, args)
        if code != 0:
            self.status[key] = f"exit:{code}"
            unlink(raw)
            unlink(normalized)
            return
        try:
            content = self.evidence.normalize(kind, read_bounded(raw, 4 * 1024 * 1024), self.today, provenance,
                                              target)
        except EvidenceFailed:
            self.status[key] = "malformed"
            unlink(raw)
            unlink(normalized)
            return
        unlink(raw)
        try:
            with open(normalized, "wb") as stream:
                stream.write(content)
            os.chmod(normalized, 0o600)
            scout_portable.replace(normalized, file)
            published = True
        except OSError:
            published = False
        if not published or not self.cache_valid(key, kind, target):
            self.status[key] = "cache-write"
            unlink(normalized)
            self.discard(file)
            return
        self.status[key] = "fresh"

    def collect_config(self) -> Optional[bytes]:
        raw = os.path.join(self.run_dir or "", "config.raw")
        code = self.probe(self.network, raw, ["config", "get", "target-org", "--json"])
        if code != 0:
            self.status["config"] = f"exit:{code}"
            unlink(raw)
            return None
        try:
            content = self.evidence.normalize("config", read_bounded(raw, 4 * 1024 * 1024), self.today,
                                              CONFIG_PROVENANCE)
        except EvidenceFailed:
            self.status["config"] = "malformed"
            return None
        finally:
            unlink(raw)
        self.status["config"] = "fresh"
        return content

    def field(self, key: str, kind: str, name: str, target: Optional[str] = None) -> str:
        return self.evidence.field(kind, read_bounded(self.cache_path(key), 4 * 1024 * 1024), self.today, name,
                                   target)

    def age_label(self, key: str, kind: str, target: str) -> str:
        collected = self.field(key, kind, "collected_at_utc", target)
        if self.status.get(key) == "fresh":
            return f"fresh evidence collected {collected}"
        return f"cached evidence from {collected}"

    def report(self, notice: str) -> str:
        output: List[str] = []
        self.prepare(output)
        # --- 1. Salesforce's official plugins: the notice computed before the workspace gate ---
        output.append(notice)
        # --- 2. The default org's config ---
        config_status, config, state, default_org = "unavailable", None, "", ""
        if self.evidence.ready and self.cache_ready and self.run_dir:
            config = self.collect_config()
            config_status = self.status.get("config", "")
        # --- 3. Salesforce org evidence ---
        if config_status == "fresh":
            state = self.evidence.field("config", config, self.today, "state")
            if state == "present":
                default_org = self.evidence.field("config", config, self.today, "target")
        else:
            output.append(f"## {WARN} Default Salesforce org check unavailable ({failure_reason(config_status)}).\n\n")
        if config_status == "fresh" and state == "absent":
            output.append(f"## {WARN} No default Salesforce org set.\n"
                          "   Name the org in your /scout request. If it isn't connected yet, Scout offers to open "
                          "Salesforce's login page for you.\n\n")
        elif default_org:
            output.append(self.org_section(default_org))
        # --- 4. Plugin first-run nudge ---
        if not os.path.isfile(self.config_file):
            output.append(f"## {WARN} Scout setup not yet complete. {SELF_REPAIR}\n\n")
        # --- 5. Ready ---
        output.append(READY)
        return "".join(output)

    def org_section(self, org: str) -> str:
        try:
            alias_key = self.evidence.key(org)
        except EvidenceFailed:
            alias_key = ""
        key = "org-display-" + alias_key
        self.cache_fill(key, "display", DISPLAY_PROVENANCE, org, ["org", "display", "--target-org", org, "--json"])
        status = self.status.get(key, "")
        if status not in ("fresh", "cached"):
            return f"## {WARN} Org '{org}' evidence unavailable ({failure_reason(status)}).\n\n"
        evidence = self.age_label(key, "display", org)
        if self.field(key, "display", "state", org) != "connected":
            connected = self.field(key, "display", "connected_status", org)
            return f"## {WARN} Org '{org}' is not connected ({connected}; {evidence}).\n\n"
        heading = OK if status == "fresh" else INFO
        return (f"## {heading} Active Org ({evidence})\n"
                f"- **Alias:** {org}\n"
                f"- **Username:** {self.field(key, 'display', 'username', org)}\n"
                f"- **Org ID:** {self.field(key, 'display', 'org_id', org)}\n"
                f"- **Instance:** {self.field(key, 'display', 'instance_url', org)}\n"
                "To work in another org, name it in your /scout request.\n\n")


def emit(text: str, floor_line: str, evidence: Evidence) -> bool:
    """Print the context as hook JSON with the client floor notice, when there is one and the helper works."""
    if not floor_line:
        return False
    try:
        rendered = evidence.hook_output(floor_line, text)
    except EvidenceFailed:
        return False
    write(rendered + "\n")
    return True


def write(text: str) -> None:
    sys.stdout.flush()
    sys.stdout.buffer.write(text.encode("utf-8"))  # UTF-8 and LF on every platform
    sys.stdout.buffer.flush()


def finish(rules: str, legacy: str, floor_line: str, evidence: Evidence) -> None:
    context = rules + "\n\n" + legacy if rules else legacy
    if not emit(context, floor_line, evidence):
        write(context)


def stop_on_signals() -> None:
    """Let SIGTERM and SIGHUP unwind the hook, so its private files and a running probe don't outlive it."""
    def stop(signum, _frame):
        raise SystemExit(128 + signum)
    for name in ("SIGTERM", "SIGHUP"):
        number = getattr(signal, name, None)
        if number is not None:
            try:
                signal.signal(number, stop)
            except (OSError, ValueError):
                pass


def main() -> int:
    stop_on_signals()
    clock = Clock()
    evidence = evidence_for(os.environ.get("SCOUT_STARTUP_EVIDENCE") or str(SCRIPTS / "startup-evidence.py"))
    floor_line = client_floor(clock) if evidence.ready and not current_client_cached() else ""
    rules = rules_block(os.environ.get("CLAUDE_PLUGIN_ROOT", ""))
    notice = official_notice(active_host(), clock) + update_notice(active_host(), clock)
    workspace = os.environ.get("SCOUT_WORKSPACE") or home_join("claude-projects", "sf-demo-scout")
    if not same_folder(launch_dir(), workspace):
        finish(rules, notice, floor_line, evidence)
        return 0
    os.umask(0o077)
    startup = Startup(evidence, clock)
    try:
        report = startup.report(notice)
    finally:
        startup.cleanup()
    finish(rules, report + "\n", floor_line, evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
