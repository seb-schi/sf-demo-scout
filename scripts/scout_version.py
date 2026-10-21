#!/usr/bin/env python3
"""Which Scout this is, and whether a newer release is out.

`--root` confirms that this file sits in a Scout install and prints `SCOUT_ROOT <root> VERSION <version>`; it exits 2
when the folder isn't one, and so does the update check, with `SCOUT_ROOT_INVALID`. The update check compares this
copy's version with the plugin manifest on Scout's `main` branch and prints one `SCOUT_UPDATE` line with this host's
way to update, or nothing when this copy is current, the check is off (`SCOUT_NO_UPDATE_CHECK=1`) or the answer is
unknown (offline, rate-limited, unreadable) and no earlier answer named a release. It sends no token or data beyond the
request itself, waits at most three seconds, and asks GitHub at most once a day, a failed attempt included; a failed
attempt keeps the release the last good answer named.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import urllib.request

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scout_portable  # noqa: E402  (ships beside this helper)

ROOT = Path(__file__).resolve().parents[1]
LATEST_URL = "https://raw.githubusercontent.com/seb-schi/sf-demo-scout/main/.claude-plugin/plugin.json"
DAY = 24 * 60 * 60
SEMVER = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def installed(root: Path = ROOT) -> str | None:
    try:
        manifest = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    if not isinstance(manifest, dict) or manifest.get("name") != "sf-demo-scout":
        return None
    version = manifest.get("version")
    return version if isinstance(version, str) else None


def parse(version: str | None):
    match = SEMVER.fullmatch(version or "")
    return tuple(int(part) for part in match.groups()) if match else None


def cache_file() -> Path:
    return Path.home() / ".cache" / "sf-demo-scout" / "latest-version.json"


def fetch() -> str | None:
    request = urllib.request.Request(LATEST_URL, headers={"User-Agent": "sf-demo-scout-update-check"})
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            manifest = json.loads(response.read(65536).decode("utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    version = manifest.get("version") if isinstance(manifest, dict) else None
    return version if isinstance(version, str) and parse(version) else None


def read_cache(path: Path) -> tuple[str | None, float | None]:
    """The cached release, when it's a strict version, and when it was last asked for; None for what's unreadable."""
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None, None
    if not isinstance(cached, dict):
        return None, None
    version = cached.get("version")
    try:
        checked = float(cached["checked"])
    except (KeyError, TypeError, ValueError, OverflowError):
        checked = None
    return (version if isinstance(version, str) and parse(version) else None), checked


def latest(now: float | None = None) -> str | None:
    """The newest release, from a cache under a day old or from GitHub; None when unknown.

    An answer that isn't a strict version (offline, a proxy's sign-in page, a manifest without one) keeps the release
    the cache already knew, so a newer release that's known stays announced."""
    now = time.time() if now is None else now
    path = cache_file()
    known, checked = read_cache(path)
    if checked is not None and now - checked < DAY:
        return known
    version = fetch()
    if not parse(version):
        version = known
    try:  # a failed attempt counts too, so an offline machine waits a day rather than three seconds every time
        path.parent.mkdir(parents=True, exist_ok=True)
        write_cache(path, {"version": version, "checked": now})
    except OSError:
        pass  # a read-only cache only means asking again next time
    return version


def write_cache(path: Path, record: dict) -> None:
    """Write the cache beside itself, then swap it in: a disk that fills mid-write leaves the old cache, and with it
    the last known release, as it was."""
    descriptor, temporary = tempfile.mkstemp(prefix=".update-check-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(record))
        scout_portable.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def advice(host: str, root: Path = ROOT) -> str:
    if host == "claude":
        return ("Claude Code installs it with auto-update; to update now, run `claude plugin marketplace update scout` and "
                "`claude plugin update sf-demo-scout@scout` in a terminal, then open a new Claude Code session.")
    if host == "codex":
        return "Restart Codex to update it (or run `codex plugin marketplace upgrade scout`), then start a new chat."
    if (root / ".git").exists():
        return ("Scout can update its folder with `git -C \"%s\" pull --ff-only` on your yes, and Salesforce's skills "
                "clone the same way, then start a new chat." % root)
    if host == "cursor":
        return "Cursor updates plugins from its own marketplace on its own schedule; this check reads Scout's GitHub."
    return "Update it the way you installed it."


def update_line(host: str, root: Path = ROOT, now: float | None = None) -> str | None:
    if os.environ.get("SCOUT_NO_UPDATE_CHECK") == "1":
        return None
    mine, newest = installed(root), None
    if parse(mine):
        newest = latest(now)
    if not (parse(mine) and parse(newest) and parse(newest) > parse(mine)):
        return None
    return "SCOUT_UPDATE Scout %s is installed; %s is out. %s" % (mine, newest, advice(host, root))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", action="store_true", help="confirm this is a Scout install and print its root")
    parser.add_argument("--host", default="unknown", choices=("claude", "codex", "cursor", "unknown"))
    args = parser.parse_args(argv)
    version = installed()
    if version is None:
        print("SCOUT_ROOT_INVALID %s: no Scout plugin manifest here" % ROOT)
        return 2
    if args.root:
        print("SCOUT_ROOT %s VERSION %s" % (ROOT, version))
        return 0
    line = update_line(args.host)
    if line:
        print(line)
    return 0


if __name__ == "__main__":
    scout_portable.utf8_output()
    sys.exit(main())
