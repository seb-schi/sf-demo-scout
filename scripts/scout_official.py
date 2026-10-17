#!/usr/bin/env python3
"""Scout's one view of Salesforce's official Claude plugins: the installation from Salesforce's own GitHub
marketplace (whatever its local name; Anthropic's copy is never used), what each capability Scout routes to needs,
and the settings under which the official hooks would fight Scout's binding. Read-only: it never installs, enables
or edits anything.

The plugin records show what's on disk, not what this session loaded: Scout confirms that in the session itself,
from its skill list and `verify`. Trials may name another accepted source with SCOUT_OFFICIAL_SOURCE, such as a
local clone of the same repository; that mode tests the resolver's records, not the GitHub match, and reports
its provider as `trial-source`."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
CAPABILITIES = ROOT / "assets" / "official-capabilities.json"
# Worst first: a capability takes the worst state of the plugins it needs.
STATES = ("unknown", "unsupported-host", "setup-needed", "conflict", "disabled", "missing", "installable", "installed")
ACTIONS = {
    "unknown": "Claude's plugin records couldn't be read; ask the SE to run /scout-setup",
    "unsupported-host": "needs Claude Code, or a local sf-skills checkout named by SCOUT_OFFICIAL_SKILLS_ROOT",
    "setup-needed": "Salesforce's official plugins aren't set up from GitHub; offer to install them (official-skill-overrides.md §Missing-plugin repair)",
    "conflict": "another copy of the same plugin is switched on; /scout-setup offers to switch it off",
    "disabled": "installed but switched off; Scout can switch it on after the SE's yes",
    "missing": "the installed official plugin doesn't have this; report the item blocked",
    "installable": "not installed yet; Scout can install it after the SE's yes",
}
NAMED_LEVELS = ("off", "low", "standard", "high")  # the official recommender's own levels (sf_context.py)


class Unreadable(Exception):
    """A plugin record exists but can't be read: never proof that nothing is installed."""


def normalize(source):
    """One comparable form for a marketplace source: a GitHub repo as host/owner/name, a folder as its real path."""
    text = str(source).strip()
    github = re.match(r"(?i)^(?:https?://|ssh://git@|git@)?(?:www\.)?github\.com[/:]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$",
                      text)
    if github:
        return ("github.com/%s/%s" % github.groups()).lower()
    if re.fullmatch(r"[\w.-]+/[\w.-]+", text):
        return ("github.com/" + text.removesuffix(".git")).lower()
    return str(Path(text).expanduser().resolve())


def read_json(path, default=None):
    """The parsed file; `default` when it doesn't exist; Unreadable when it exists but won't parse."""
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default
    except (OSError, ValueError, UnicodeError) as error:
        raise Unreadable(str(path)) from error


def capability_map():
    try:
        data = read_json(CAPABILITIES)
    except Unreadable:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("capabilities"), dict):
        raise SystemExit("official capability map unreadable: %s" % CAPABILITIES)
    return data


def config_dir():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def accepted_source(data=None):
    """The marketplace source Scout accepts: Salesforce's GitHub repository, or the labelled trial source."""
    return os.environ.get("SCOUT_OFFICIAL_SOURCE") or (data or capability_map())["source"]


def source_location(entry):
    source = entry.get("source") if isinstance(entry, dict) else None
    return (source.get("url") or source.get("repo") or source.get("path")) if isinstance(source, dict) else None


class Records:
    """Claude's plugin records, read once. With a launch folder, its project and local settings and installs count
    too (the local file beats the project file, which beats user settings), because they decide what loads there;
    Scout never changes them. A present record of the wrong shape is Unreadable."""

    def __init__(self, data, launch_dir=None):
        config = config_dir()
        known = read_json(config / "plugins" / "known_marketplaces.json", {})
        registry = read_json(config / "plugins" / "installed_plugins.json", {"plugins": {}})
        settings = read_json(config / "settings.json", {})
        if not (isinstance(known, dict) and isinstance(registry, dict) and isinstance(registry.get("plugins", {}), dict)
                and isinstance(settings, dict) and isinstance(settings.get("enabledPlugins", {}), dict)):
            raise Unreadable("plugin records")
        self.known, self.plugins = known, registry.get("plugins", {})
        self.enabled = dict(settings.get("enabledPlugins", {}))
        self.folder, self.overrides = None, {}
        if launch_dir:
            self.folder = str(Path(launch_dir).expanduser().resolve())
            for name in ("settings.json", "settings.local.json"):
                path = Path(self.folder) / ".claude" / name
                local = read_json(path, {})
                plugins = local.get("enabledPlugins", {}) if isinstance(local, dict) else None
                if not isinstance(plugins, dict):
                    raise Unreadable(str(path))
                for ident, value in plugins.items():
                    self.enabled[ident], self.overrides[ident] = value, str(path)
        wanted = normalize(accepted_source(data))
        self.trial = bool(os.environ.get("SCOUT_OFFICIAL_SOURCE"))
        self.github = [name for name, entry in known.items() if (where := source_location(entry)) and normalize(where) == wanted]

    def pin(self, name):
        """The ref a registration is pinned to (a tag or branch other than the default), or None: a pinned copy never
        gets Salesforce's latest, even with auto-update on."""
        source = self.known.get(name, {}).get("source") if isinstance(self.known.get(name), dict) else None
        ref = source.get("ref") if isinstance(source, dict) else None
        return ref if isinstance(ref, str) and ref and ref not in ("main", "HEAD") else None

    def user_record(self, ident):
        """This installation's user-scope record, None when absent or stale (its folder is gone)."""
        if ident not in self.plugins:
            return None
        rows = self.plugins[ident]
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise Unreadable(ident)
        record = next((r for r in rows if r.get("scope") == "user"), None)  # never another project's installation
        if record is None:
            return None
        if not isinstance(record.get("installPath"), str):
            raise Unreadable(ident)
        return record if Path(record["installPath"]).is_dir() else None

    def folder_record(self, ident):
        """A project or local install of this plugin for the launch folder itself, which loads there too."""
        rows = self.plugins.get(ident) if self.folder else None
        for row in rows if isinstance(rows, list) else ():
            if (isinstance(row, dict) and row.get("scope") in ("project", "local") and isinstance(row.get("projectPath"), str)
                    and str(Path(row["projectPath"]).expanduser().resolve()) == self.folder
                    and isinstance(row.get("installPath"), str) and Path(row["installPath"]).is_dir()):
                return row
        return None

    def on(self, ident):
        if ident not in self.enabled:
            return False  # an installed plugin without `true` isn't loaded
        if not isinstance(self.enabled[ident], bool):
            raise Unreadable(ident)
        return self.enabled[ident]

    def enabled_copies(self, plugin):
        """Every switched-on copy of this plugin, from any marketplace, installed for the user or for the launch folder:
        their skills and hooks all load."""
        return sorted(ident for ident in self.enabled if ident.rpartition("@")[0] == plugin and self.on(ident)
                      and (self.user_record(ident) or self.folder_record(ident)))

    def roots(self, name, plugin, record):
        """Where this installation's skills may load from: its install folder and, for a folder-sourced marketplace,
        that plugin's own source folder in it (Claude loads those skills in place)."""
        roots = [record["installPath"]]
        entry = self.known.get(name)
        source = entry.get("source") if isinstance(entry, dict) else None
        if isinstance(source, dict) and source.get("source") == "directory" and isinstance(source.get("path"), str):
            base = Path(source["path"]).expanduser()
            try:
                manifest = read_json(base / ".claude-plugin" / "marketplace.json", {})
            except Unreadable:
                manifest = {}
            for row in manifest.get("plugins", []) if isinstance(manifest, dict) else ():
                if isinstance(row, dict) and row.get("name") == plugin and isinstance(row.get("source"), str):
                    roots.append(str(base / row["source"]))
        return [str(Path(r).expanduser().resolve()) for r in roots]


def resolve(plugin, host="claude", data=None, records=None):
    """One official plugin's state: {state, provider, root, roots, version, ident, reason?}."""
    data = data or capability_map()
    if host != "claude":
        local = os.environ.get("SCOUT_OFFICIAL_SKILLS_ROOT")
        if not local:
            return {"state": "unsupported-host"}  # prompts/host-runtime.md: another host's registry is never read
        root = Path(local).expanduser().resolve() / "plugins" / "builder" / plugin  # read in place, never copied
        return {"state": "installed" if root.is_dir() else "missing", "provider": "local-checkout", "root": str(root),
                "roots": [str(root)], "version": None, "ident": plugin}
    try:
        records = records or Records(data)
        if not records.github:
            return {"state": "setup-needed", "reason": "Salesforce's GitHub marketplace isn't registered"}
        provider = "trial-source" if records.trial else "salesforce-github"
        candidates = []
        for name in records.github:
            ident = "%s@%s" % (plugin, name)
            record = records.user_record(ident)
            if record is not None:
                roots = records.roots(name, plugin, record)
                local = records.folder_record(ident)  # the same plugin installed for this folder too: either may load
                if local and local["installPath"] != record["installPath"]:
                    roots += records.roots(name, plugin, local)
                candidates.append({"provider": provider, "root": record["installPath"], "version": record.get("version"),
                                   "roots": roots, "ident": ident, "on": records.on(ident),
                                   **({"pinned": records.pin(name)} if records.pin(name) else {})})
        copies = records.enabled_copies(plugin)
    except Unreadable:
        return {"state": "unknown"}
    if not candidates:  # Salesforce's marketplace is registered, so one approved install repairs it, core or not
        return {"state": "installable", "ident": "%s@%s" % (plugin, records.github[0])}
    # Prefer the switched-on copy that follows Salesforce's latest, then any switched-on one.
    chosen = next((c for c in candidates if c["on"] and not c.get("pinned")), None) or \
        next((c for c in candidates if c["on"]), candidates[0])
    found = {k: v for k, v in chosen.items() if k != "on"}
    if not chosen["on"]:
        return dict(found, state="disabled")
    others = [ident for ident in copies if ident != chosen["ident"]]
    if others:
        where = {ident: records.overrides[ident] for ident in others if ident in records.overrides}
        return dict(found, state="conflict", reason="also on: " + ", ".join(others), others=others,
                    **({"switched_on_in": where} if where else {}))
    return dict(found, state="installed")


def installation(plugin, host="claude", data=None):
    """The usable installation of one official plugin, for helpers that run its scripts, or None."""
    found = resolve(plugin, host, data)
    return found if found["state"] == "installed" else None


def check(names, host="claude", launch_dir=None):
    """Each capability's state, the worst of the plugins it needs, with what's missing and the SE-facing action. With
    a launch folder, that folder's own plugin settings and installs count too."""
    data = capability_map()
    try:
        records = Records(data, launch_dir) if host == "claude" else None
    except Unreadable:
        records = None
    report = {}
    for name in names:
        spec = data["capabilities"].get(name)
        if spec is None:
            report[name] = {"state": "unknown-capability"}
            continue
        plugins, missing = {}, []
        for entry in list(spec.get("skills", [])) + list(spec.get("assets", [])):
            plugin, _, rest = entry.partition(":")
            if plugin == "sf-demo-scout":
                continue  # Scout's own skill ships with Scout
            if plugin not in plugins:
                plugins[plugin] = resolve(plugin, host, data, records) if records or host != "claude" else {"state": "unknown"}
            found = plugins[plugin]
            if found["state"] == "installed":
                relative = ("skills/%s/SKILL.md" % rest) if entry in spec.get("skills", []) else rest
                target = Path(found["root"]) / relative
                if not (target.is_file() and os.access(target, os.R_OK)):
                    missing.append(entry)
        states = [p["state"] for p in plugins.values()] + (["missing"] if missing else [])
        state = min(states, key=STATES.index) if states else "installed"
        report[name] = {"state": state, **({"missing": missing} if missing else {}),
                        **({"action": ACTIONS[state]} if state in ACTIONS else {}),
                        "plugins": {p: {k: v for k, v in i.items() if k != "roots"} for p, i in plugins.items()}}
    return report


def verify(plugin, skill_dir, host="claude", launch_dir=None):
    """Whether a skill this session loaded comes from the resolved installation (its "Base directory"), judged with
    the launch folder's own plugin settings and installs, as inspection judges them."""
    try:
        records = Records(capability_map(), launch_dir) if host == "claude" else None
    except Unreadable:
        return {"state": "unknown"}
    found = resolve(plugin, host, None, records)
    if found["state"] != "installed":
        return {"state": found["state"], **({"action": ACTIONS[found["state"]]} if found["state"] in ACTIONS else {})}
    try:
        loaded = Path(skill_dir).expanduser().resolve()
    except (OSError, RuntimeError):
        return {"state": "unknown"}
    for root in found["roots"]:
        if Path(root) in loaded.parents:
            return {"state": "verified", "ident": found["ident"], "version": found["version"], "provider": found["provider"]}
    return {"state": "conflict", "expected": found["root"], "loaded": str(loaded), "action": ACTIONS["conflict"]}


def catalog(records):
    """Every skill name in Salesforce's marketplace as Claude installed it: its standalone `skills/` and every plugin's."""
    names = set()
    for name in records.github if records else ():
        entry = records.known.get(name)
        location = entry.get("installLocation") if isinstance(entry, dict) else None
        if not isinstance(location, str) or not Path(location).is_dir():
            continue
        for pattern in ("skills/*/SKILL.md", "plugins/*/*/skills/*/SKILL.md"):
            names.update(f.parent.name for f in Path(location).glob(pattern))
    return names


def workspace_dir():
    return Path(os.environ.get("SCOUT_WORKSPACE") or Path.home() / "claude-projects" / "sf-demo-scout").expanduser()


def personal_copies(launch_dir, records):
    """Possible personal copies of Salesforce's skills (for example from `npx skills add forcedotcom/sf-skills`): skill
    folders or links named like a skill in Salesforce's catalog, in the personal, launch-folder and Scout-workspace
    skills folders only. Report-only: many have no replacement among Scout's five plugins, and a copy may be edited or
    merely share a name. None means unknown (no catalog to compare with), never "no copies"; a renamed skill isn't
    detected."""
    names = catalog(records)
    if not names:
        return None
    folders = {Path.home() / ".claude" / "skills", Path(launch_dir).expanduser() / ".claude" / "skills",
               workspace_dir() / ".claude" / "skills"}
    found = []
    for folder in sorted(folders):
        try:
            entries = sorted(folder.iterdir()) if folder.is_dir() else []
        except OSError:
            return None  # a folder that can't be read leaves the answer unknown
        for entry in entries:
            if entry.name in names and (entry / "SKILL.md").is_file():
                found.append({"path": str(entry), "name": entry.name, "link": entry.is_symlink()})
    return found


def sensitivity(raw):
    """A recommender sensitivity as the official hook parses it: a named level or a number from 1 to 10, else None."""
    if isinstance(raw, str):
        level = raw.strip().lower()
        if level in NAMED_LEVELS:
            return level
        try:
            value = float(level)
        except ValueError:
            return None
    elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
        value = float(raw)
    else:
        return None
    return value if 1.0 <= value <= 10.0 else None


def private_text(path, max_bytes=512):
    """The saved preference as the official hook reads it: one owned regular file, no links, small, ASCII; else None."""
    import stat
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
            return None
        data = os.read(descriptor, max_bytes + 1)
        return data.decode("ascii") if len(data) <= max_bytes else None
    except (OSError, UnicodeDecodeError):
        return None
    finally:
        os.close(descriptor)


def recommender():
    """The official recommender's effective setting and its source, resolved the way its own hook does: each tier
    validated and falling through when invalid. The plugin's own userConfig option isn't visible from here."""
    if os.environ.get("SF_DISABLE_PLUGIN_MATCH"):
        return {"on": False, "setting": "off", "source": "SF_DISABLE_PLUGIN_MATCH"}
    value = sensitivity(os.environ.get("SF_PLUGIN_MATCH_SENSITIVITY"))
    if value is not None:
        return {"on": value != "off", "setting": value, "source": "SF_PLUGIN_MATCH_SENSITIVITY"}
    try:
        saved = json.loads(private_text(Path.home() / ".sf" / "plugin-recommendations" / "config.json") or "{}")
    except ValueError:
        saved = {}
    value = sensitivity(saved.get("sensitivity")) if isinstance(saved, dict) else None
    if value is not None:
        return {"on": value != "off", "setting": value, "source": "saved preference"}
    return {"on": True, "setting": "standard", "source": "default (the plugin's own option isn't visible)"}


def default_org(sf, launch_dir):
    """The org the official deploy gate checks, as it resolves it: SF_TARGET_ORG/SFDX_TARGET_ORG first, then the
    launch folder's default. Returns (org, problem, origin), the origin being `environment` (including the legacy
    SFDX_DEFAULTUSERNAME the CLI still honours), `local` or `global`. This is the one read of a session default Scout
    makes."""
    target = os.environ.get("SF_TARGET_ORG") or os.environ.get("SFDX_TARGET_ORG")
    if target:
        return target, None, "environment"
    try:
        result = subprocess.run([sf, "config", "get", "target-org", "--json"], cwd=launch_dir, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=75)
        data = json.loads(result.stdout)
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        return None, "query-failed", None
    rows = data.get("result") if isinstance(data, dict) else None
    if result.returncode != 0 or not isinstance(rows, list):
        return None, "query-failed", None
    row = next((r for r in rows if isinstance(r, dict) and r.get("name") == "target-org"), {})
    value, where = row.get("value"), str(row.get("location") or "").lower()
    origin = "environment" if where == "environment" or os.environ.get("SFDX_DEFAULTUSERNAME") else \
        where if where in ("local", "global") else None
    return (value, None, origin) if isinstance(value, str) and value else (None, "no-default", origin)


def reachable(sf, target):
    try:
        result = subprocess.run([sf, "org", "display", "--target-org", target, "--json"], stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=75)
        data = json.loads(result.stdout)
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        return False
    return (result.returncode == 0 and isinstance(data, dict) and data.get("status") == 0
            and isinstance(data.get("result"), dict) and bool(data["result"]))


def project_root(launch_dir):
    """The Salesforce project the CLI's local config belongs to: the nearest folder upward with sfdx-project.json."""
    folder = Path(launch_dir).expanduser().resolve()
    return next((d for d in (folder, *folder.parents) if (d / "sfdx-project.json").is_file()), None)


def default_scope(launch_dir, origin=None):
    """Where a fix for the deploy gate's default org would land: nowhere Scout may change when an environment setting
    decides it; else the project's local config (named, since a subfolder's launch changes the project root's
    config); else, outside any project, the computer-wide (global) config. Returns (scope, folder or None)."""
    if origin == "environment" or os.environ.get("SF_TARGET_ORG") or os.environ.get("SFDX_TARGET_ORG") \
            or os.environ.get("SFDX_DEFAULTUSERNAME"):
        return "environment", None
    root = project_root(launch_dir)
    return ("project", str(root)) if root else ("global", None)


def coexistence(sf, host, launch_dir, installed=None):
    """Settings under which the official plugin would fight Scout's binding: (issues, checks). Claude only: on any
    other host the official plugins and their hooks don't exist."""
    if host != "claude":
        return [], {}
    issues, checks = [], {}
    if os.environ.get("SFDX_AUTO_DEPLOY") == "1":
        issues.append({"issue": "auto-deploy", "detail": "the official hook deploys saved files to its own default org"})
    if installed is None:
        try:
            installed = bool(Records(capability_map(), launch_dir).enabled_copies("salesforce-development"))
        except Unreadable:
            installed = True  # unknown: predict the hooks rather than miss them
    if not installed:
        return issues, {"official-hooks": "absent"}
    setting = recommender()
    project = (Path(launch_dir) / "sfdx-project.json").is_file()  # the recommender only fires in a Salesforce project
    checks["recommender"] = dict(setting, fires_here=setting["on"] and project)
    if checks["recommender"]["fires_here"]:
        issues.append({"issue": "recommender", "detail": setting["source"]})
    target, problem, origin = default_org(sf, launch_dir)
    if problem is None and not reachable(sf, target):
        problem = "default-unreachable"
    checks["deploy-gate"] = problem or "ok"
    if problem:
        scope, folder = default_scope(launch_dir, origin)
        issues.append({"issue": "deploy-gate", "detail": problem, "scope": scope, **({"folder": folder} if folder else {}),
                       **({"default": target} if target else {})})
    return issues, checks


def inspect(report, host, launch_dir):
    """One compact answer per task: ready capabilities, blocked ones grouped by state with their action, each
    official plugin's identity, the roots workers need, and the coexistence issues and checks."""
    groups = {}
    for name, r in sorted(report.items()):
        if r["state"] != "installed":
            group = groups.setdefault(r["state"], {"state": r["state"], "capabilities": [], **(
                {"action": r["action"]} if "action" in r else {})})
            group["capabilities"].append(name)
            group.setdefault("missing", []).extend(r.get("missing", []))
    blocked = [{k: v for k, v in g.items() if v != []} for _, g in sorted(groups.items(), key=lambda x: STATES.index(x[0])
                                                                          if x[0] in STATES else -1)]
    plugins = {}
    for r in report.values():
        for plugin, found in r.get("plugins", {}).items():
            plugins[plugin] = {k: v for k, v in found.items() if v is not None}
    roots = {plugin: found["root"] for plugin, found in plugins.items() if found.get("state") == "installed"}
    issues, checks = coexistence(shutil.which("sf") or "sf", host, launch_dir)
    data = capability_map()
    optional, records = {}, None  # the other official plugins Scout may offer, one per build need, never wholesale
    if host == "claude":
        try:
            records = Records(data, launch_dir)
        except Unreadable:
            records = None
        for plugin, spec in data["plugins"].items():
            if spec.get("offer"):
                state = resolve(plugin, host, data, records)["state"] if records else "unknown"
                optional[plugin] = {"state": state, "area": spec["offer"]}
    pinned = sorted({"%s@%s" % (f["ident"].rpartition("@")[2], f["pinned"]) for f in plugins.values() if f.get("pinned")})
    copies = (personal_copies(launch_dir, records) if records else None) if host == "claude" else []
    notes = {}  # never blocking: setup can tidy the first; the second is the SE's to keep or remove
    if pinned:
        notes["pinned"] = pinned
    if copies is None:
        notes["personal_copies"] = "unknown"
    elif copies:
        notes["personal_copies"] = {"count": len(copies), "folders": sorted({str(Path(c["path"]).parent) for c in copies})}
    return {"ready": sorted(name for name, r in report.items() if r["state"] == "installed"), "blocked": blocked,
            "plugins": plugins, "roots": roots, "coexistence": issues, "checks": checks, "optional": optional,
            **({"notes": notes} if notes else {})}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "inspect"):
        sub = commands.add_parser(name)
        sub.add_argument("--host", required=True, choices=("claude", "codex", "unknown"))
        sub.add_argument("--capabilities", nargs="*", help="names from assets/official-capabilities.json (default: all)")
        if name == "inspect":
            sub.add_argument("--launch-dir", type=Path, default=Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()),
                             help="the folder this session started in, where the official hooks run")
    sub = commands.add_parser("resolve")
    sub.add_argument("--host", required=True, choices=("claude", "codex", "unknown"))
    sub.add_argument("--plugin", required=True)
    sub.add_argument("--launch-dir", type=Path, help="the folder this session started in")
    sub = commands.add_parser("verify")
    sub.add_argument("--host", required=True, choices=("claude", "codex", "unknown"))
    sub.add_argument("--plugin", required=True)
    sub.add_argument("--skill-dir", required=True, help="the loaded skill's base directory")
    sub.add_argument("--launch-dir", type=Path, help="the folder this session started in")
    args = parser.parse_args(argv)
    if args.command == "resolve":
        try:
            records = Records(capability_map(), args.launch_dir) if args.host == "claude" else None
        except Unreadable:
            records = None  # resolve reports the unreadable records itself
        found = resolve(args.plugin, args.host, None, records)
        print(json.dumps(found, sort_keys=True))
        return 0 if found["state"] == "installed" else 5
    if args.command == "verify":
        found = verify(args.plugin, args.skill_dir, args.host, args.launch_dir)
        print(json.dumps(found, sort_keys=True))
        return 0 if found["state"] == "verified" else 5
    names = args.capabilities or sorted(capability_map()["capabilities"])
    report = check(names, args.host, getattr(args, "launch_dir", None))
    if args.command == "check":
        print(json.dumps(report, sort_keys=True))
        return 0 if all(r["state"] == "installed" for r in report.values()) else 5
    print(json.dumps(inspect(report, args.host, args.launch_dir), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
