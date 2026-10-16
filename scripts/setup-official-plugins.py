#!/usr/bin/env python3
"""Install and auto-update Salesforce's official Claude plugins from its own GitHub marketplace, for /scout-setup
and for a build's repair of a missing add-on.

Claude host only. Each step checks first, then acts, and prints one token line; the last line is a readiness
verdict from Scout's own resolver. It never touches logins, default orgs or aliases, switches other copies of these
plugins off only when asked (after the SE's yes), and never removes anything."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scout_official  # noqa: E402  the one resolver: source matching, states and readiness

NAME = "salesforce"
BUDGET = 570  # seconds for the whole run, inside the callers' 10-minute timeout, so a slow download ends with a reason
STARTED = time.monotonic()
SETTINGS_HELPER = Path(__file__).resolve().with_name("setup-settings.py")
CAPABILITIES = scout_official.capability_map()
SETUP = tuple(name for name, spec in CAPABILITIES["plugins"].items() if spec.get("setup"))  # all five, once; auto-update keeps them current


def parse(stdout):
    """The whole output as JSON, else its last JSON line (`--json` prints one result line last)."""
    try:
        return json.loads(stdout)
    except ValueError:
        pass
    for line in reversed(stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return None


def claude_json(claude, args):
    """One `claude` call with whatever is left of the run's budget. A timeout is reported as one, not as no result."""
    left = BUDGET - (time.monotonic() - STARTED)
    if left < 1:
        return None, {"outcome": "failed", "message": "setup ran out of time"}
    try:
        result = subprocess.run([claude, *args], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                errors="replace", timeout=left)
    except subprocess.TimeoutExpired:
        return None, {"outcome": "failed", "message": "timed out, possibly on a slow network"}
    except (OSError, subprocess.SubprocessError):
        return None, None
    return result.returncode, parse(result.stdout)


def find_claude():
    """The running client's own Claude Code binary first, then `claude` on the PATH. An SE who uses only the desktop
    app has no `claude` command, but the app's bundled binary manages the same plugins."""
    running = os.environ.get("CLAUDE_CODE_EXECPATH", "")
    if os.path.isabs(running) and os.access(running, os.X_OK):
        try:
            probe = subprocess.run([running, "--version"], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                   errors="replace", timeout=30)
            if probe.returncode == 0 and probe.stdout.strip().endswith("(Claude Code)"):  # not the node of an npm install
                return running
        except (OSError, subprocess.SubprocessError):
            pass
    return shutil.which("claude")


def succeeded(code, data):
    return code == 0 and isinstance(data, dict) and data.get("outcome") == "ok"


def find_marketplace(claude, source):
    """(The name of an already-declared marketplace for this source, under any name, or None; why listing failed, or
    None.)"""
    code, rows = claude_json(claude, ["plugin", "marketplace", "list", "--json"])
    if code != 0 or not isinstance(rows, list):
        return None, message(rows)
    wanted = scout_official.normalize(source)
    for row in rows:
        if isinstance(row, dict):
            where = row.get("url") or row.get("repo") or row.get("path") or ""
            if where and scout_official.normalize(where) == wanted:
                return row.get("name"), None
    return None, None


def user_settings():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "settings.json"


def settings_helper(*args):
    try:
        result = subprocess.run([sys.executable, "-B", str(SETTINGS_HELPER), *args], stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return "HELPER_UNAVAILABLE"
    return (result.stdout.strip().splitlines() or ["HELPER_NO_OUTPUT"])[-1]


def installed(claude):
    """User-scope plugin rows by ID, for versions; the reason as a string when the list fails. Decisions come from the
    resolver."""
    code, rows = claude_json(claude, ["plugin", "list", "--json"])
    if code != 0 or not isinstance(rows, list):
        return message(rows)
    return {row["id"]: row for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str)
            and row.get("scope", "user") == "user"}


def message(data):
    text = data.get("message") if isinstance(data, dict) else None
    return " ".join(str(text).split())[:200] if text else "no result"


def declared_source(name):
    """The registration's source as user settings declare it: Claude accepts a re-add only from exactly that form."""
    try:
        data = json.loads(user_settings().read_text())
        source = data["extraKnownMarketplaces"][name]["source"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return source if isinstance(source, dict) else None


def read_records(launch_dir=None):
    try:
        return scout_official.Records(CAPABILITIES, launch_dir)
    except scout_official.Unreadable:
        return None


def registration_ok(name, form):
    """Read back one registration after a re-add: present, the same source, and following the default branch."""
    records = read_records()
    if records is None:
        return "Claude's plugin records couldn't be read"
    entry = records.known.get(name)
    source = entry.get("source") if isinstance(entry, dict) else None
    if not isinstance(source, dict):
        return "the marketplace isn't listed"
    if (source.get("repo") or source.get("url")) != form:
        return "the marketplace's source changed"
    return "it is still fixed to %s" % records.pin(name) if records.pin(name) else None


def unpin(claude, name, approved_ref):
    """Make one registration the SE approved follow Salesforce's latest, checking every stage: unpin the settings
    entry (only while it's still fixed to the approved ref), re-add the marketplace from the same form, read the
    registration back, then update each plugin installed from it. A failed re-add restores the ref only while the
    settings still hold Scout's own change; a newer SE choice is kept. A rerun after the ref is gone still runs the
    updates. Returns token lines; takeover completion is reported apart from readiness."""
    records = read_records()
    if records is None:
        return ["OFFICIAL_UNPIN_INCOMPLETE %s Claude's plugin records couldn't be read: rerun /scout-setup" % name]
    declared = declared_source(name)
    source = declared or (records.known.get(name) or {}).get("source") or {}
    form = source.get("repo") if source.get("source") == "github" else source.get("url")
    if source.get("source") not in ("github", "git") or not form:
        return ["OFFICIAL_UNPIN_FAILED %s not a GitHub or git registration" % name]
    current = source.get("ref") if source.get("ref") not in (None, "", "main", "HEAD") else None
    if approved_ref and current and current != approved_ref:
        return ["OFFICIAL_UNPIN_SKIPPED %s now fixed to %s, not the approved %s: nothing changed" % (name, current, approved_ref)]
    affected = sorted(ident for ident in records.plugins if ident.rpartition("@")[2] == name and records.user_record(ident))
    if current or records.pin(name) or name not in records.known:
        unpinned_here = False
        if current:
            step = settings_helper("marketplace-unpin", "--settings", str(user_settings()), "--name", name,
                                   "--expect-ref", current)
            if step.startswith("UNPIN_CHANGED"):
                return ["OFFICIAL_UNPIN_SKIPPED %s its settings changed meanwhile: nothing changed" % name]
            if not step.startswith(("UNPIN_SET", "UNPIN_ALREADY")):
                return ["OFFICIAL_UNPIN_FAILED %s %s" % (name, step)]
            unpinned_here = step.startswith("UNPIN_SET")
        code, data = claude_json(claude, ["plugin", "marketplace", "add", form, "--scope", "user", "--json"])
        if not succeeded(code, data):
            if not unpinned_here:  # nothing of ours to restore
                return ["OFFICIAL_UNPIN_FAILED %s %s: rerun /scout-setup" % (name, message(data))]
            expected = {k: v for k, v in source.items() if k != "ref"}
            back = settings_helper("marketplace-repin", "--settings", str(user_settings()), "--name", name,
                                   "--ref", current, "--expect-source", json.dumps(expected))
            if back.startswith("REPIN_CHANGED"):
                outcome = "the settings changed meanwhile, so they were kept as saved; the takeover is incomplete"
            elif back.startswith(("REPIN_SET", "REPIN_ALREADY")):
                after = read_records()
                listed = after is not None and after.pin(name) == current
                outcome = ("the setting is fixed to %s again%s" % (current, "" if listed else
                           ", but the marketplace isn't listed as before: rerun /scout-setup"))
            else:
                outcome = "the setting couldn't be restored (%s): rerun /scout-setup" % back
            return ["OFFICIAL_UNPIN_FAILED %s %s; %s" % (name, message(data), outcome)]
        problem = registration_ok(name, form)
        if problem:
            return ["OFFICIAL_UNPIN_INCOMPLETE %s %s: rerun /scout-setup" % (name, problem)]
    lines, failed = [], []
    for ident in affected:
        code, data = claude_json(claude, ["plugin", "update", ident, "--scope", "user", "--json"])
        plugin = ident.rpartition("@")[0]
        if succeeded(code, data):
            old, new = data.get("oldVersion") or "?", data.get("newVersion") or "?"
            lines.append("OFFICIAL_PLUGIN_UPDATED %s %s %s" % (plugin, old, new) if old != new else
                         "OFFICIAL_PLUGIN_CURRENT %s %s" % (plugin, new))
        else:
            failed.append(plugin)
            lines.append("OFFICIAL_PLUGIN_UPDATE_FAILED %s %s" % (plugin, message(data)))
    lines.append("OFFICIAL_UNPIN_PARTIAL %s %d/%d %s" % (name, len(affected) - len(failed), len(affected), " ".join(failed))
                 if failed else "OFFICIAL_UNPINNED %s" % name)
    return lines


def selected_markets(wanted, records=None):
    """The registrations the resolver chose for these plugins (X3, D6: never an unused one)."""
    return sorted({found["ident"].rpartition("@")[2] for plugin in wanted
                   for found in (scout_official.resolve(plugin, records=records),)
                   if found.get("ident") and found["state"] in ("installed", "conflict", "disabled")})


def readiness(plugins, launch_dir=None):
    """The final verdict from Scout's own resolver, judged for the launch folder, so setup and every build agree."""
    records = read_records(launch_dir)
    states = {plugin: (scout_official.resolve(plugin, records=records)["state"] if records else "unknown")
              for plugin in plugins}
    blocked = ["%s:%s" % (plugin, state) for plugin, state in states.items() if state != "installed"]
    return "OFFICIAL_READINESS " + ("blocked " + " ".join(blocked) if blocked else "ready")


def snapshot():
    """Each supported plugin's resolved state and identity, to see what this run actually changed."""
    return {plugin: (found["state"], found.get("ident")) for plugin in CAPABILITIES["plugins"]
            for found in (scout_official.resolve(plugin),)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, choices=("claude", "codex", "unknown"))
    parser.add_argument("--source", default=scout_official.accepted_source(CAPABILITIES),
                        help="the marketplace source (default: Salesforce's GitHub repo, or SCOUT_OFFICIAL_SOURCE in trials)")
    parser.add_argument("--workspace-settings", type=Path, help="Scout's workspace settings, for the recommender switch")
    parser.add_argument("--launch-dir", type=Path, default=Path.cwd(),
                        help="the folder this session started in, whose own plugin selections count (never edited)")
    parser.add_argument("--plugins", nargs="+", choices=sorted(CAPABILITIES["plugins"]),
                        help="install only these (a build's repair of a missing add-on, after the SE's yes) instead of the setup set")
    parser.add_argument("--disable-duplicates", nargs="+", default=[], metavar="ID",
                        help="after the SE's yes, switch off exactly these other copies (they stay installed)")
    parser.add_argument("--unpin", nargs="+", default=[], metavar="NAME[:REF]",
                        help="after the SE's yes, make exactly these registrations follow Salesforce's latest")
    args = parser.parse_args(argv)
    if args.host != "claude":
        print("OFFICIAL_PLUGINS_SKIPPED host=%s (sf-skills ships no plugin for this host)" % args.host)
        print("OFFICIAL_READINESS not-applicable host=%s" % args.host)
        return 0
    wanted = tuple(args.plugins or SETUP)
    if scout_official.normalize(args.source) != scout_official.normalize(scout_official.accepted_source(CAPABILITIES)):
        # One effective source for the whole run: every build's resolver accepts only this one.
        print("OFFICIAL_SOURCE_UNSUPPORTED %s: Scout drives Salesforce's GitHub marketplace "
              "(a trial names its source with SCOUT_OFFICIAL_SOURCE)" % args.source)
        print(readiness(wanted, args.launch_dir))
        return 0
    claude = find_claude()
    if not claude:
        print("OFFICIAL_PLUGINS_UNAVAILABLE Claude Code's binary not found")
        print(readiness(wanted, args.launch_dir))
        return 0
    name, failure = find_marketplace(claude, args.source)
    if failure:
        print("OFFICIAL_MARKETPLACE_UNKNOWN could not list marketplaces: %s" % failure)
        print(readiness(wanted, args.launch_dir))
        return 0
    if name:
        print("OFFICIAL_MARKETPLACE_PRESENT %s" % name)
    else:
        code, data = claude_json(claude, ["plugin", "marketplace", "add", args.source, "--scope", "user", "--json"])
        if not succeeded(code, data):
            print("OFFICIAL_MARKETPLACE_FAILED %s" % message(data))
            print(readiness(wanted, args.launch_dir))
            return 0
        name = data.get("marketplace") or NAME
        print("OFFICIAL_MARKETPLACE_ADDED %s" % name)
    records = read_records()
    if records and records.pin(name):  # new installs go to a registration that follows the latest, when there is one
        name = next((n for n in records.github if not records.pin(n)), name)
    print("OFFICIAL_" + settings_helper("marketplace-autoupdate", "--settings", str(user_settings()), "--name", name))
    before = snapshot()
    changed = False
    done = set()
    for approval in args.unpin:  # exactly the registrations the SE approved, before anything else installs from them
        market, _, ref = approval.partition(":")
        lines = unpin(claude, market, ref or None)
        done.add(market)
        changed = changed or any(l.startswith(("OFFICIAL_PLUGIN_UPDATED", "OFFICIAL_UNPINNED", "OFFICIAL_UNPIN_PARTIAL"))
                                 for l in lines)
        print("\n".join(lines))
    for plugin in wanted:
        found = scout_official.resolve(plugin)  # the resolver's choice, so a working registration is never replaced
        if found["state"] in ("installed", "conflict"):
            print("OFFICIAL_PLUGIN_PRESENT %s %s" % (plugin, found.get("version") or "?"))
            continue
        if found["state"] == "unknown":
            print("OFFICIAL_PLUGIN_UNKNOWN %s Claude's plugin records couldn't be read" % plugin)
            continue
        if found["state"] == "disabled":
            verb, outcome = ["plugin", "enable", found["ident"], "--scope", "user", "--json"], "ENABLED"
        else:
            verb, outcome = ["plugin", "install", "%s@%s" % (plugin, name), "--scope", "user", "--json"], "INSTALLED"
        code, data = claude_json(claude, verb)
        if succeeded(code, data):
            changed = True
            print("OFFICIAL_PLUGIN_%s %s" % (outcome, plugin))
        else:
            print("OFFICIAL_PLUGIN_FAILED %s %s" % (plugin, message(data)))
    markets = selected_markets(wanted)
    for market in [m for m in markets if m != name]:  # auto-update every registration actually in use, too
        print("OFFICIAL_" + settings_helper("marketplace-autoupdate", "--settings", str(user_settings()), "--name", market))
    rows = installed(claude)  # read back versions
    if isinstance(rows, str):
        print("OFFICIAL_PLUGINS_UNKNOWN could not list plugins after installing: %s" % rows)
    else:
        for plugin in wanted:
            ident = scout_official.resolve(plugin).get("ident")
            if ident in rows and rows[ident].get("version"):
                print("OFFICIAL_PLUGIN_VERSION %s %s" % (plugin, rows[ident]["version"]))
    # The proposal comes last, so its list is final (D1): the pinned registrations Scout actually uses.
    records = read_records()
    for market in [m for m in markets if m not in done and records and records.pin(m)]:
        users = sorted(ident.rpartition("@")[0] for ident in records.plugins
                       if ident.rpartition("@")[2] == market and records.user_record(ident))
        print("OFFICIAL_PINNED %s %s %s" % (market, records.pin(market), ",".join(users) or "-"))
    # Two copies of one plugin both load, and Scout uses only its chosen one: judged for the launch folder.
    here = read_records(args.launch_dir)
    approved = set(args.disable_duplicates)
    conflicted = []
    for plugin in CAPABILITIES["plugins"]:
        found = scout_official.resolve(plugin, records=here) if here else {"state": "unknown"}
        if found["state"] != "conflict":
            continue
        for other in found.get("others", []):
            where = found.get("switched_on_in", {}).get(other)
            if where:  # the folder's own selection: the SE's to change, never Scout's
                print("OFFICIAL_PROJECT_COPY %s %s" % (other, where))
            elif other in approved:
                approved.discard(other)
                code, data = claude_json(claude, ["plugin", "disable", other, "--scope", "user", "--json"])
                if succeeded(code, data):
                    changed = True
                    print("OFFICIAL_DUPLICATE_DISABLED %s" % other)
                else:
                    print("OFFICIAL_DUPLICATE_FAILED %s %s" % (other, message(data)))
            else:
                print("OFFICIAL_DUPLICATE %s" % other)
        here = read_records(args.launch_dir)
        if here and scout_official.resolve(plugin, records=here)["state"] == "conflict":
            conflicted.append(plugin)
    for other in sorted(approved):  # approved, but no longer an extra copy: never a substitute
        print("OFFICIAL_DUPLICATE_SKIPPED %s no longer an extra copy: nothing changed" % other)
    copies = scout_official.personal_copies(args.launch_dir, here) if here else None
    if copies is None:
        print("OFFICIAL_PERSONAL_COPIES_UNKNOWN Salesforce's catalog or a skills folder couldn't be read")
    elif copies:
        print("OFFICIAL_PERSONAL_COPIES %d %s" % (len(copies), ",".join(sorted({str(Path(c["path"]).parent) for c in copies}))))
    if args.workspace_settings:
        print("OFFICIAL_RECOMMENDER_" + settings_helper("workspace-env", "--settings", str(args.workspace_settings),
                                                        "--key", "SF_DISABLE_PLUGIN_MATCH"))
    changed = changed or snapshot() != before  # also when a command failed after its records landed
    print("OFFICIAL_PLUGINS_DONE restart=%s" % ("needed" if changed else "no"))
    print(readiness(wanted + tuple(p for p in conflicted if p not in wanted), args.launch_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
