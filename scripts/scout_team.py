#!/usr/bin/env python3
"""Scout's team mode (multiplayer): every step Scout takes for a team, so SEs never type git, gh or sf mp.

A team is one Git repository. `main` holds the source the team has delivered into its common org (a kit project
bound by sf-mp). `mp/ledger` holds the team ledger (members, work packages, deliveries) as small JSON files,
written with Git plumbing and never checked out. `wp/<package>` branches carry hand-overs: each is cut from
`main` when its package starts, after the builder's own org is checked against it, so delivery is a real
three-way merge from the builder's actual base. Only the captain's machine writes to the common org, through
sf-mp's guarded lane; every other member's machine guards it.

Commands print one JSON object (the hook and the watcher print text). Exit codes: 0 done; 2 refused, nothing
changed; 3 stopped for the SE's decision (the JSON says which); 1 failed (the JSON says what is left).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
SF_MP = ROOT / "packages" / "sf-mp"
TEAM_PROMPT = ROOT / "prompts" / "scout" / "team.md"
LIFECYCLE_PROMPT = ROOT / "prompts" / "scout" / "team-lifecycle.md"  # teams on Lifecycle Center (scout_lc.py)
LEDGER = "mp/ledger"
LEDGER_REF = "refs/heads/" + LEDGER
TRACK_REF = "refs/remotes/origin/" + LEDGER
SOURCE = "force-app/main/default/"
OPEN = ("building", "handed-over", "delivering", "returned", "failed")  # returned: back with its owner to merge
LANE_TYPES = {"ApexClass", "LightningComponentBundle", "CustomField"}  # sf-mp's lane contracts; others: --steward
# sf mp retrieve's outcomes a delivery acts on: matches, unchanged and absent go on, a conflict only once accepted,
# and the rest stop it. Anything else, or no outcome at all, stops it too.
RETRIEVE_OUTCOMES = {"matches", "unchanged", "absent", "conflict", "unknown", "deleted-in-org", "refused"}
COMPONENT = re.compile(r"^[A-Za-z][A-Za-z0-9]*:[^\s*:](?:[^*]*[^\s*])?$")  # names may hold spaces (layouts)
GITHUB = re.compile(r"github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")
CONFLICT_MARKER = re.compile(rb"(?m)^(<{7}|>{7})( |\r?$)")  # a conflict's marker line, from a Windows checkout too
FETCH_EVERY = 60
REPORT_LIMIT = 12
HOOK_CHARS = 9000  # Claude Code caps a prompt hook's added context at 10,000 characters
HOOK_FETCH_SECONDS = 4.0  # all teams' first-prompt fetches together, well inside the hook's 8-second timeout
QUIET = {"package-base", "package-sync", "test"}  # the ledger's own bookkeeping, not news for teammates
SUCCESS = ("settled-success", "reconciled-success")
SFDX_PROJECT_TEMPLATE = {"packageDirectories": [{"path": "force-app", "default": True}], "namespace": ""}
FORCEIGNORE = "**/.gitkeep\n**/jsconfig.json\n**/.eslintrc.json\n**/__tests__/**\n**/tsconfig.json\npackage.xml\n"
GITIGNORE = ".sf/\n.sfdx/\n.localdevserver/\nnode_modules/\n.DS_Store\n*.log\n"
# Where the common metadata types live under force-app/main/default. A hand-over may change only files that map
# to its declared components; anything else is refused until the package is split or named.
FOLDERS = [
    (r"classes/([^/]+)\.cls(?:-meta\.xml)?", "ApexClass"),
    (r"triggers/([^/]+)\.trigger(?:-meta\.xml)?", "ApexTrigger"),
    (r"lwc/([^/]+)/.+", "LightningComponentBundle"),
    (r"aura/([^/]+)/.+", "AuraDefinitionBundle"),
    (r"objects/([^/]+)/\1\.object-meta\.xml", "CustomObject"),
    (r"objects/([^/]+)/fields/([^/]+)\.field-meta\.xml", "CustomField"),
    (r"objects/([^/]+)/listViews/([^/]+)\.listView-meta\.xml", "ListView"),
    (r"objects/([^/]+)/recordTypes/([^/]+)\.recordType-meta\.xml", "RecordType"),
    (r"objects/([^/]+)/validationRules/([^/]+)\.validationRule-meta\.xml", "ValidationRule"),
    (r"objects/([^/]+)/compactLayouts/([^/]+)\.compactLayout-meta\.xml", "CompactLayout"),
    (r"objects/([^/]+)/webLinks/([^/]+)\.webLink-meta\.xml", "WebLink"),
    (r"objects/([^/]+)/fieldSets/([^/]+)\.fieldSet-meta\.xml", "FieldSet"),
    (r"objects/([^/]+)/businessProcesses/([^/]+)\.businessProcess-meta\.xml", "BusinessProcess"),
    (r"permissionsets/([^/]+)\.permissionset-meta\.xml", "PermissionSet"),
    (r"tabs/([^/]+)\.tab-meta\.xml", "CustomTab"),
    (r"layouts/([^/]+)\.layout-meta\.xml", "Layout"),
    (r"flexipages/([^/]+)\.flexipage-meta\.xml", "FlexiPage"),
    (r"flows/([^/]+)\.flow-meta\.xml", "Flow"),
    (r"applications/([^/]+)\.app-meta\.xml", "CustomApplication"),
    (r"profiles/([^/]+)\.profile-meta\.xml", "Profile"),
    (r"labels/([^/]+)\.label-meta\.xml", "CustomLabel"),
    (r"customMetadata/([^/]+)\.md-meta\.xml", "CustomMetadata"),
    (r"quickActions/([^/]+)\.quickAction-meta\.xml", "QuickAction"),
    (r"globalValueSets/([^/]+)\.globalValueSet-meta\.xml", "GlobalValueSet"),
    (r"testSuites/([^/]+)\.testSuite-meta\.xml", "ApexTestSuite"),
]


class Stop(Exception):
    """Ends a command with an exit code and a JSON body."""

    def __init__(self, code, reason, **data):
        super().__init__(reason)
        self.code, self.data = code, dict(data, reason=reason)


def refused(reason, **data):
    return Stop(2, reason, **data)


def failed(reason, **data):
    return Stop(1, reason, **data)


def decide(reason, **data):
    return Stop(3, reason, **data)


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def moment(text):
    """A timestamp from either writer, compared as a time: whole seconds here, milliseconds from sf-mp, so a record
    made within the receipt's own second still counts as after it."""
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def slug(text, fallback="team"):
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:40].strip("-") or fallback


def org15(value):
    value = str(value or "")
    return value[:15] if re.fullmatch(r"00D[0-9A-Za-z]{12}(?:[0-9A-Za-z]{3})?", value) else None


def tool(name):
    return os.environ.get("SCOUT_TEAM_" + name.upper()) or name


def workspace():
    return Path(os.environ.get("SCOUT_WORKSPACE") or "~/claude-projects/sf-demo-scout").expanduser()


def teams_file():
    return Path(os.environ.get("SCOUT_TEAMS_FILE") or "~/.config/sf-demo-scout/teams.json").expanduser()


def cache_root():
    return Path(os.environ.get("SCOUT_TEAM_CACHE") or "~/.cache/sf-demo-scout/teams").expanduser()


def cache_dir(team_id):
    return cache_root() / slug(team_id, "team")


def normalized(data, path=""):
    data = bytes(data).replace(b"\r\n", b"\n")
    # Salesforce strips an Apex body's trailing whitespace when it saves it, and sf-mp's read-back allows for the
    # same, so an editor's final newline never reads as a stale copy. Metadata files and every other type compare
    # exactly.
    return data.rstrip(b" \t\n") if path.endswith((".cls", ".trigger")) else data


def same_files(a, b):
    return set(a) == set(b) and all(normalized(a[path], path) == normalized(b[path], path) for path in a)


def component_of(path):
    if not path.startswith(SOURCE):
        return None
    rest = path[len(SOURCE):]
    for pattern, kind in FOLDERS:
        match = re.fullmatch(pattern, rest)
        if match:
            return f"{kind}:{'.'.join(match.groups())}"
    return None


# ---- processes ----

def run(cmd, cwd=None, input=None, env=None, timeout=600, binary=False):
    try:
        return subprocess.run(cmd, cwd=cwd, input=input, env=env, capture_output=True, text=not binary,
                              timeout=timeout, stdin=None if input is not None else subprocess.DEVNULL)
    except FileNotFoundError:
        raise failed(f"{Path(cmd[0]).name} isn't installed or isn't on the PATH")
    except subprocess.TimeoutExpired:
        raise failed(f"`{' '.join(str(c) for c in cmd[:4])}` timed out after {timeout} s")


def git(repo, *args, check=True, input=None, env=None, timeout=120, binary=False):
    cmd = [tool("git"), "-C", str(repo), "-c", "gc.auto=0", "-c", "maintenance.auto=false", *args]
    result = run(cmd, input=input, env=env, timeout=timeout, binary=binary)
    if check and result.returncode:
        err = result.stderr if isinstance(result.stderr, str) else result.stderr.decode("utf-8", "replace")
        raise failed(f"git {args[0]} failed: {err.strip()[-400:]}")
    return result


def out(repo, *args, **kw):
    return git(repo, *args, **kw).stdout.strip()


def sf(args, cwd, timeout=1800, input=None):
    """Runs `sf … --json`; returns (exit code, the result or the error body)."""
    result = run([tool("sf"), *args, "--json"], cwd=cwd, input=input, timeout=timeout)
    text = result.stdout.strip()
    try:
        payload = json.loads(text[text.index("{"):]) if "{" in text else {}
    except ValueError:
        raise failed(f"sf {' '.join(args[:2])} returned unreadable output", stderr=result.stderr.strip()[-400:])
    body = payload.get("result", payload) if isinstance(payload, dict) else payload
    return result.returncode, body


def gh(args, cwd=None, timeout=120):
    result = run([tool("gh"), *args], cwd=cwd, timeout=timeout)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def org_info(target, cwd=None):
    """The org a selector names, from the local login (its token never leaves this process)."""
    code, body = sf(["org", "display", "--target-org", target], cwd or os.getcwd(), timeout=120)
    if code or not isinstance(body, dict) or not org15(body.get("id")):
        raise refused(f"{target} isn't a connected org on this machine; connect it first (Scout's connect-org step)")
    return {"target": target, "org_id": org15(body["id"]), "username": body.get("username"),
            "alias": body.get("alias"), "api": str(body.get("apiVersion") or ""), "label": body.get("alias") or target}


# ---- the machine's registry and cache ----

def load_registry():
    path = teams_file()
    if not path.exists():
        return {"schema": 1, "teams": {}}
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or not isinstance(data.get("teams"), dict):
        raise failed(f"{path} isn't a Scout teams file")
    return data


def write_json_atomic(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="." + path.name, suffix=".tmp")
    with os.fdopen(fd, "w") as handle:
        json.dump(data, handle, indent=1, sort_keys=True)
        handle.write("\n")
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def save_team(team_id, entry):
    registry = load_registry()
    registry["teams"][team_id] = entry
    write_json_atomic(teams_file(), registry)


def pick(team=None):
    teams = load_registry()["teams"]
    if team:
        for team_id, entry in teams.items():
            if team in (team_id, entry.get("slug"), entry.get("name")):
                return team_id, entry
        raise refused(f"this machine isn't in a team called {team}")
    if len(teams) == 1:
        return next(iter(teams.items()))
    raise refused("name the team: this machine is in " + (", ".join(e.get("name", t) for t, e in teams.items())
                                                          or "no team yet"))


def cache_state(team_id):
    try:
        return json.loads((cache_dir(team_id) / "state.json").read_text())
    except (OSError, ValueError):
        return {}


def save_cache(team_id, **changes):
    state = cache_state(team_id)
    state.update(changes)
    write_json_atomic(cache_dir(team_id) / "state.json", state)


def advance(repo, team_id, cursor, commit):
    """Moves a cursor forward along the ledger's history only, so a slow writer can't move it back."""
    current = cache_state(team_id).get(cursor)
    if commit and commit != current and (not current or is_ancestor(repo, current, commit)):
        save_cache(team_id, **{cursor: commit})


# ---- the ledger ----

def ledger_tip(repo):
    return out(repo, "rev-parse", "--verify", "--quiet", TRACK_REF + "^{commit}", check=False) or None


def ledger_fetch(repo, team_id=None, timeout=30):
    """Fetches mp/ledger. After the team has started, a deleted or rewritten ledger stops here."""
    before = ledger_tip(repo)
    incoming = f"refs/scout/incoming/{os.getpid()}-{uuid.uuid4().hex[:8]}"
    result = git(repo, "fetch", "--quiet", "--no-tags", "--no-write-fetch-head", "origin", f"+{LEDGER_REF}:{incoming}",
                 check=False, timeout=timeout)
    if result.returncode:
        if re.search(r"couldn'?t find remote ref|could not find remote ref", result.stderr):
            if before:
                raise failed("the team ledger branch is gone from the team repository; ask the captain before going on")
            return None
        raise failed("couldn't reach the team repository: " + result.stderr.strip()[-300:])
    try:
        tip = out(repo, "rev-parse", incoming)
        if before and tip != before and not is_ancestor(repo, before, tip):
            raise failed("the team ledger's history was rewritten in the team repository; Scout stops writing to it "
                         "until the captain has looked")
        git(repo, "update-ref", TRACK_REF, tip)
    finally:
        git(repo, "update-ref", "-d", incoming, check=False)
    if team_id:
        save_cache(team_id, fetched_at=time.time())
    return tip


def tree_files(repo, rev):
    if not rev:
        return {}
    listing = git(repo, "ls-tree", "-r", "-z", rev).stdout
    entries = [line.split("\t", 1) for line in listing.split("\0") if line]
    blobs = [(meta.split()[2], path) for meta, path in entries if meta.split()[1] == "blob"]
    if not blobs:
        return {}
    raw = git(repo, "cat-file", "--batch", input="".join(sha + "\n" for sha, _ in blobs).encode(), binary=True).stdout
    files, at = {}, 0
    for _, path in blobs:
        header_end = raw.index(b"\n", at)
        size = int(raw[at:header_end].split()[2])
        files[path] = raw[header_end + 1:header_end + 1 + size]
        at = header_end + 1 + size + 1
    return files


def ledger_state(files):
    state = {"team": None, "members": {}, "packages": {}, "deliveries": {}, "problems": []}
    for path, data in sorted(files.items()):
        if path == "README.md":
            continue
        try:
            item = json.loads(data.decode("utf-8"))
            if not isinstance(item, dict) or item.get("schema") != 1:
                raise ValueError
        except ValueError:
            state["problems"].append(path)
            continue
        if path == "team.json":
            state["team"] = item
        elif re.fullmatch(r"members/[a-z0-9-]+\.json", path):
            state["members"][item.get("id") or path[8:-5]] = item
        elif re.fullmatch(r"packages/WP-\d+\.json", path):
            state["packages"][item.get("id") or path[9:-5]] = item
        elif re.fullmatch(r"deliveries/[\w-]+\.json", path):
            state["deliveries"][path[11:-5]] = item
    return state


def read_ledger(repo, rev=None):
    return ledger_state(tree_files(repo, rev or ledger_tip(repo)))


def render(item):
    return (json.dumps(item, indent=1, sort_keys=True) + "\n").encode()


def name_of(state, member_id):
    return (state["members"].get(member_id) or {}).get("name") or member_id or "someone"


def by_number(packages):
    return sorted(packages, key=lambda p: int(p["id"].split("-")[1]))


def board(state):
    team = state["team"] or {}
    org = team.get("common_org") or {}
    lines = [f"# {team.get('name', 'Team')}: the team board",
             "Generated by Scout from this branch's files at every change; don't edit it by hand.", "",
             f"Common org: {org.get('label', '?')} (`{org.get('org_id', '?')}`). "
             f"Captain: {name_of(state, team.get('captain'))}.", "", "## Members",
             "| Member | Role | With Scout | Builds in | Joined |", "|---|---|---|---|---|"]
    for member in sorted(state["members"].values(), key=lambda m: m.get("joined_at") or ""):
        build = (member.get("build_org") or {}).get("label") or "—"
        lines.append(f"| {member.get('name')} | {member.get('role')} | {'yes' if member.get('scout', True) else 'no'} | "
                     f"{build} | {(member.get('joined_at') or '')[:10]} |")
    lines += ["", "## Work packages", "| Package | Title | Owner | Status | Components | Hand-over |", "|---|---|---|---|---|---|"]
    for package in by_number(state["packages"].values()):
        link = package.get("pr") or package.get("branch") or ""
        lines.append(f"| {package['id']} | {package.get('title', '')} | {name_of(state, package.get('owner'))} | "
                     f"{package.get('status')} | {', '.join(package.get('components') or []) or '—'} | {link} |")
    lines += ["", "## Deliveries", "| When | Package | By | Outcome | Components |", "|---|---|---|---|---|"]
    for delivery in sorted(state["deliveries"].values(), key=lambda d: d.get("at") or "", reverse=True)[:20]:
        lines.append(f"| {(delivery.get('at') or '')[:16]} | {delivery.get('package')} | {name_of(state, delivery.get('by'))} | "
                     f"{delivery.get('state')}{' (check-only)' if delivery.get('check_only') else ''} | "
                     f"{', '.join(delivery.get('components') or [])} |")
    return "\n".join(lines) + "\n"


def make_commit(repo, parent, files, message, ident):
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / "index"), GIT_AUTHOR_NAME=ident["name"],
                   GIT_AUTHOR_EMAIL=ident["email"], GIT_COMMITTER_NAME=ident["name"], GIT_COMMITTER_EMAIL=ident["email"])
        paths = sorted(files)
        staged = Path(tmp) / "files"
        staged.mkdir()
        for number, path in enumerate(paths):
            (staged / str(number)).write_bytes(files[path])
        shas = out(repo, "hash-object", "-w", "--stdin-paths",
                   input="".join(f"{staged / str(n)}\n" for n in range(len(paths)))).split()
        git(repo, "update-index", "--add", "--index-info", env=env,
            input="".join(f"100644 {sha}\t{path}\n" for sha, path in zip(shas, paths)))
        tree = out(repo, "write-tree", env=env)
        return out(repo, "commit-tree", tree, *(["-p", parent] if parent else []), "-m", message, env=env)


def push_ledger(repo, commit):
    """True when pushed, False when someone else wrote first; None when the answer was lost, a timeout included: the
    server may have taken the push."""
    try:
        result = git(repo, "push", "--porcelain", "origin", f"{commit}:{LEDGER_REF}", check=False, timeout=90)
    except Stop:
        return None
    if result.returncode == 0:
        return True
    text = result.stdout + result.stderr
    if re.search(r"\[rejected\]|non-fast-forward|fetch first|stale info|failed to update ref|cannot lock ref|"
                 r"incorrect old value", text):
        return False
    return None


def committed_write(repo, tip, key):
    """The commit carrying this write's key, if an earlier push landed after all."""
    if not tip:
        return None
    found = out(repo, "log", "--format=%H", "-n", "50", f"--grep=^MP-Write: {key}$", tip, check=False)
    return found.splitlines()[0] if found else None


def ledger_write(repo, ident, change, team_id=None, attempts=6):
    """Applies change(state) -> (updates, summary, kind, package) at the ledger's tip, as a compare-and-swap: a
    rejected push means someone wrote first, so re-read their tip and apply the change again. The change checks its
    own preconditions each time. A push whose answer was lost is recognised by its MP-Write key, never
    applied twice. Across invocations, each step's own preconditions recognise its earlier write."""
    key = uuid.uuid4().hex
    lost = False
    for attempt in range(attempts):
        try:
            tip = ledger_fetch(repo, team_id)
        except Stop as stop:
            if not lost:
                raise
            raise failed("the team repository stopped answering just after this write, so whether it landed is unknown. "
                         "Run the same step again once it answers: it reads the ledger first, so nothing is recorded "
                         "twice", detail=stop.data.get("reason"), outcome="unknown")
        landed = committed_write(repo, tip, key)
        if landed:
            git(repo, "update-ref", TRACK_REF, tip)
            return {"commit": landed, "changed": True, "state": read_ledger(repo, landed)}
        files = tree_files(repo, tip)
        result = change(ledger_state(files))
        if result is None:
            return {"commit": tip, "changed": False, "state": ledger_state(files)}
        updates, summary, kind, package = result
        for path, item in updates.items():
            if item is None:
                files.pop(path, None)
            else:
                files[path] = render(item)
        state = ledger_state(files)
        files["README.md"] = board(state).encode()
        trailers = f"\n\nMP-Event: {kind}" + (f"\nMP-Package: {package}" if package else "") + f"\nMP-Write: {key}"
        commit = make_commit(repo, tip, files, summary + trailers, ident)
        pushed = push_ledger(repo, commit)
        if pushed:
            git(repo, "update-ref", TRACK_REF, commit)
            return {"commit": commit, "changed": True, "state": state}
        lost = lost or pushed is None
        if pushed is None and attempt == attempts - 1:
            raise failed("couldn't reach the team repository to record this; nothing was written twice", outcome="unknown")
        time.sleep(0.4 * (attempt + 1))
    raise failed(f"the team ledger kept changing under this write; tried {attempts} times, nothing was lost")


def is_ancestor(repo, older, newer):
    return git(repo, "merge-base", "--is-ancestor", older, newer, check=False).returncode == 0


def ledger_events(repo, since, until, me_email, limit=40):
    """Ledger commits by others after `since`, oldest first; the recent tail if `since` is unknown."""
    if not until or since == until:
        return []
    rng = [f"{since}..{until}"] if since and is_ancestor(repo, since, until) else ["-n", str(limit), until]
    raw = git(repo, "log", "--format=%H%x1f%an%x1f%ae%x1f%aI%x1f%B%x1e", *rng).stdout
    events = []
    for record in raw.split("\x1e"):
        parts = record.strip("\n").split("\x1f")
        if len(parts) != 5:
            continue
        sha, author, email, at, body = parts
        kind = re.search(r"(?m)^MP-Event: (\S+)$", body)
        if (me_email and email.lower() == me_email.lower()) or (kind and kind[1] in QUIET):
            continue
        package = re.search(r"(?m)^MP-Package: (\S+)$", body)
        events.append({"commit": sha, "by": author, "at": at, "summary": body.strip().splitlines()[0][:300],
                       "kind": kind[1] if kind else None, "package": package[1] if package else None})
    return list(reversed(events))


# ---- identity, checkouts, components ----

def identity(repo):
    name = out(repo, "config", "user.name", check=False)
    email = out(repo, "config", "user.email", check=False)
    if not name or not email:
        raise refused("Git has no name or email for you yet; set them (git config --global user.name / user.email) "
                      "so teammates see who did what")
    return {"name": name, "email": email}


def team_context(team_id, entry):
    repo = Path(entry["checkout"])
    if not (repo / ".git").exists():
        raise failed(f"the team checkout {repo} is missing")
    resend_comments(team_id)
    return repo, identity(repo)


def require_clean(repo):
    dirty = out(repo, "status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise refused("the team checkout has uncommitted changes; Scout keeps it clean, so look at them first: "
                      + "; ".join(dirty.splitlines()[:5]), checkout=str(repo))


def github_repo(remote):
    match = GITHUB.search(remote or "")
    return f"{match[1]}/{match[2]}" if match else None


def components_of(values):
    found, bad = [], []
    for value in values or []:
        for part in re.split(r"\s*[,\n]\s*", str(value).strip()):
            if part:
                (found if COMPONENT.match(part) else bad).append(part)
    if bad:
        raise refused("name components as Type:Name, with no wildcards: " + ", ".join(bad))
    return sorted(set(found))


KNOWN_TYPES = {kind for _, kind in FOLDERS}


def components_in(text):
    """The components a pull request's description lists: `Type:Name` in backticks (names may hold spaces, as page
    layouts' do), or bare Type:Name words. Only types Scout maps to source folders, so links and prose never count
   ."""
    quoted = re.findall(r"`([A-Z][A-Za-z0-9]*:[^`\n]+)`", text or "")
    bare = re.findall(r"(?<![\w/:.-])([A-Z][A-Za-z0-9]*:[A-Za-z0-9_](?:[\w.\-]*\w)?)(?![\w/:])",
                      re.sub(r"`[^`\n]*`", " ", text or ""))
    return [c.strip() for c in quoted + bare if c.split(":", 1)[0] in KNOWN_TYPES and COMPONENT.match(c.strip())]


def criteria_from_task(path):
    """The items' criteria and read-backs from a Scout task record's scout-items block."""
    if not path:
        return []
    block = re.search(r"```scout-items\n(.*?)\n```", Path(path).read_text(), re.S)
    if not block:
        return []
    try:
        items = json.loads(block[1]).get("items") or []
    except ValueError:
        raise refused(f"{path}'s scout-items block isn't readable JSON")
    return [{"item": i.get("id"), "text": i.get("criterion") or i.get("what") or "", "readback": i.get("readback") or "",
             "components": i.get("components") or []} for i in items if isinstance(i, dict)]


def files_at(repo, ref, components=None):
    """{component: {path: bytes}} for the source files at ref, optionally only these components."""
    listing = out(repo, "ls-tree", "-r", "--name-only", ref, "--", SOURCE.rstrip("/"), check=False)
    grouped = {}
    for path in listing.splitlines():
        component = component_of(path)
        if component and (components is None or component in components):
            grouped.setdefault(component, {})[path] = git(repo, "show", f"{ref}:{path}", binary=True).stdout
    return grouped


def org_files(target, components, api):
    """Retrieves components from an org into a scratch project: {component: {state, files {path: bytes}, problem}}."""
    found = {c: {"state": "unknown", "files": {}, "problem": "nothing came back for it"} for c in components}
    if not components:
        return found
    with tempfile.TemporaryDirectory(prefix="scout-team-retrieve-") as tmp:
        project = Path(tmp)
        (project / "force-app").mkdir()
        (project / "sfdx-project.json").write_text(json.dumps(dict(SFDX_PROJECT_TEMPLATE, sourceApiVersion=api)))
        args = ["project", "retrieve", "start", "--target-org", target, "--output-dir", "out"]
        for component in components:
            args += ["--metadata", component]
        code, body = sf(args, cwd=project, timeout=1800)
        if code or not isinstance(body, dict):
            raise failed("the retrieve from your org failed", detail=body)
        outdir = (project / "out").resolve()
        for item in body.get("files") or []:
            key = f"{item.get('type')}:{item.get('fullName')}"
            if key not in found:
                continue
            if item.get("state") == "Failed":
                if found[key]["files"]:
                    continue
                absent = "cannot be found" in str(item.get("error") or "")
                found[key] = {"state": "absent" if absent else "unknown", "files": {}, "problem": item.get("error")}
                continue
            if item.get("filePath"):
                rel = Path(item["filePath"]).resolve().relative_to(outdir).as_posix()
                found[key]["state"], found[key]["problem"] = "present", None
                found[key]["files"][SOURCE + rel] = Path(item["filePath"]).read_bytes()
    return found


def source_api(repo, ref="refs/remotes/origin/main"):
    return json.loads(git(repo, "show", f"{ref}:sfdx-project.json").stdout).get("sourceApiVersion", "66.0")


def overlaps(state, package_id, components):
    found = []
    for other in state["packages"].values():
        if other["id"] == package_id or other.get("status") not in OPEN:
            continue
        for component in sorted(set(components) & set(other.get("components") or [])):
            found.append({"component": component, "package": other["id"], "owner": name_of(state, other.get("owner")),
                          "status": other.get("status")})
    return found


def next_hints(state, me, role):
    hints = []
    for package in by_number(state["packages"].values()):
        status = package.get("status")
        if role == "captain" and status == "handed-over":
            hints.append(f'say "deliver {package["id"]}" ({package.get("title", "")}, from {name_of(state, package.get("owner"))})')
        elif role == "captain" and status == "delivering":
            hints.append(f'{package["id"]}\'s delivery is still open: say "resume delivery"')
        elif package.get("owner") == me and status in ("failed", "returned"):
            hints.append(f'{package["id"]} is back with you ({(package.get("note") or "see the board")[:160]}): say "fix {package["id"]}"')
    return hints[:3]


def update_block(entry, state, events):
    lines = [f"📨 Team update: {entry.get('name')} ({len(events)} new)"] + [f"- {e['summary']}" for e in events]
    hints = next_hints(state, entry.get("me"), entry.get("role"))
    if hints:
        lines.append(f"Next for you ({entry.get('role')}): " + "; ".join(hints) + ".")
    return "\n".join(lines)


def board_lines(entry, state):
    team = state["team"] or {}
    open_packages = by_number(p for p in state["packages"].values() if p.get("status") in OPEN)
    summary = ", ".join(f"{p['id']} {name_of(state, p.get('owner'))} {p.get('status')}" for p in open_packages[:6]) or "none"
    return [f"Team {entry.get('name')}: you're {entry.get('role')} ({name_of(state, entry.get('me'))}); captain "
            f"{name_of(state, team.get('captain'))}; common org {(team.get('common_org') or {}).get('label')}.",
            f"Open packages: {summary}. Say \"team status\" for the board."]


# ---- the guard (sf-mp in the SE's sf CLI) ----

# What the guard does, said at every join before it goes in (Lifecycle Center mode reuses the first sentence).
GUARD_WHAT = ("Scout's guard (sf-mp, a Salesforce CLI plugin that isn't signed by Salesforce) stops this machine's "
              "Salesforce CLI from deploying to the team's common org outside the captain's delivery.")
LANE_GUARD = ("This team runs on Scout's own lane, which relies on the guard on every member's machine, so joining it "
              "needs the guard.")


def sf_mp_version():
    return json.loads((SF_MP / "package.json").read_text())["version"]


def installed_sf_mp(cwd=None):
    result = run([tool("sf"), "plugins", "--json"], cwd=cwd or os.getcwd(), timeout=120)
    try:
        plugins = json.loads(result.stdout)
    except ValueError:
        return None
    for plugin in plugins if isinstance(plugins, list) else []:
        if isinstance(plugin, dict) and plugin.get("name") == "sf-mp":
            return plugin.get("version")
    return None


def build_tarball(destination):
    """sf-mp as an npm package tarball, from Scout's own copy (the shipped files only)."""
    manifest = json.loads((SF_MP / "package.json").read_text())
    destination.parent.mkdir(parents=True, exist_ok=True)
    members = []
    for name in manifest.get("files", []) + ["package.json"]:
        source = SF_MP / name
        if source.is_dir():
            members += sorted(p for p in source.rglob("*") if p.is_file())
        elif source.is_file():
            members.append(source)
    with tarfile.open(destination, "w:gz") as archive:
        for source in sorted(set(members)):
            info = tarfile.TarInfo("package/" + source.relative_to(SF_MP).as_posix())
            data = source.read_bytes()
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            archive.addfile(info, io.BytesIO(data))
    return destination


def tarball_path():
    return cache_root().parent / "sf-mp" / f"sf-mp-{sf_mp_version()}.tgz"


def ensure_guard(yes):
    version, have = sf_mp_version(), installed_sf_mp()
    if have == version:
        return {"guard": "installed", "version": version}
    if not yes:
        raise decide(f"Scout's team guard (sf-mp {version}) isn't in this machine's sf CLI{' (it has ' + have + ')' if have else ''}. "
                     "It isn't signed by Salesforce, so installing it needs the SE's yes", needs="guard-install", version=version)
    tarball = build_tarball(tarball_path())
    result = run([tool("sf"), "plugins", "install", f"file:{tarball}"], input="y\n", timeout=600)
    if result.returncode or installed_sf_mp() != version:
        raise failed("the sf CLI didn't install Scout's team guard", detail=(result.stdout + result.stderr).strip()[-400:])
    return {"guard": "installed now", "version": version, "tarball": str(tarball)}


# ---- context, guard, repository, start, join ----

def cmd_context(a):
    try:
        teams = load_registry()["teams"]
    except Stop:
        return {"team": None, "problem": "the teams file is unreadable"}
    org = org15(a.org_id)
    cwd = Path(a.cwd).resolve() if a.cwd else None
    for team_id, entry in teams.items():
        role_here = ("common" if org and org == entry.get("common_org_id") else
                     "build" if org and org == entry.get("build_org_id") else None)
        inside = bool(cwd) and str(cwd).startswith(str(Path(entry["checkout"]).resolve()))
        if role_here or inside:
            return {"team": team_id, "name": entry.get("name"), "role": entry.get("role"), "org": role_here,
                    "checkout": entry["checkout"], "me": entry.get("me"), "mode": entry.get("mode", "lane"),
                    "prompt": str(LIFECYCLE_PROMPT if entry.get("mode") == "lifecycle" else TEAM_PROMPT)}
    return {"team": None}


def cmd_guard(a):
    return ensure_guard(a.yes)


def cmd_repo_create(a):
    code, stdout, stderr = gh(["api", "user", "--jq", "[.login, .type] | @tsv"])
    if code:
        raise refused("GitHub's CLI isn't signed in here; sign in (gh auth login) or give Scout an existing empty repository",
                      detail=stderr[-300:])
    login, kind = (stdout.split("\t") + [None])[:2] if stdout else (None, None)
    name = slug(a.name, "scout-team")
    full = f"{a.owner}/{name}" if a.owner else name
    code, stdout, stderr = gh(["repo", "create", full, "--private", "--description", f"Scout team: {a.name}"])
    if code:
        raise failed(f"GitHub didn't create {full} as {login}: {stderr[-300:]}. Your enterprise may not allow repositories "
                     "under your own account; name an organization you can create in, or an existing empty repository",
                     account=login, managed=managed(login))
    code, stdout, stderr = gh(["repo", "view", full, "--json", "url,nameWithOwner,visibility"])
    view = json.loads(stdout) if not code else {}
    return {"url": view.get("url"), "remote": (view.get("url") or "") + ".git", "repository": view.get("nameWithOwner"),
            "visibility": view.get("visibility"), "account": login, "account_type": kind, "managed": managed(login)}


def managed(login):
    """A managed (enterprise) user's login is handle_shortcode; ordinary GitHub logins can't hold an underscore.
    Managed users work only with their own enterprise's members."""
    return "_" in (login or "")


def cmd_invite(a):
    team_id, entry = pick(a.team)
    repository = github_repo(entry.get("remote"))
    if not repository:
        raise refused("invitations need a GitHub remote; give your teammate access to the repository yourself")
    code, stdout, stderr = gh(["api", "-X", "PUT", f"repos/{repository}/collaborators/{a.github}", "-f", "permission=push",
                               "--include"])
    status = re.search(r"HTTP/[\d.]+ (\d{3})", stdout)
    if code:
        raise failed(f"GitHub refused access for {a.github}: {stderr[-300:] or stdout[-300:]}. A managed (enterprise) account "
                     "works only with its own enterprise's members, so a managed account and an ordinary one can never "
                     "share a repository, whichever repository it is", github=a.github, managed=managed(a.github))
    return {"github": a.github, "result": "invited" if status and status[1] == "201" else "added",
            "next": f"ask them to say: /scout session join {entry.get('remote')}"}


def scaffold(repo, team_name, common, captain_name):
    project = dict(SFDX_PROJECT_TEMPLATE, name=slug(team_name), sourceApiVersion=common["api"] or "66.0")
    (repo / "sfdx-project.json").write_text(json.dumps(project, indent=2) + "\n")
    (repo / ".forceignore").write_text(FORCEIGNORE)
    (repo / ".gitignore").write_text(GITIGNORE)
    (repo / "force-app" / "main" / "default").mkdir(parents=True, exist_ok=True)
    (repo / "force-app" / "main" / "default" / ".gitkeep").write_text("")
    (repo / "AGENTS.md").write_text(
        f"# {team_name}: one common Salesforce org, built together\n"
        f"This repository delivers into one common org, {common['label']} (org ID `{common['org_id']}`), through one "
        f"guarded lane that the captain, {captain_name}, runs. Every AI tool and person working here follows these rules:\n"
        "1. Never deploy, validate, delete or run anonymous Apex against the common org. The `sf mp` guard refuses it; "
        "never work around a refusal.\n"
        "2. Build and test in your own org (your sandbox), always with an explicit `--target-org`. Look an org up with "
        "`sf org display --target-org <name>`, not `sf org list`, which refreshes every login on the machine.\n"
        "3. Before you change a component that's already in `main`, make sure your org has `main`'s version of it: "
        "deploy `main`'s copy to your org first, then edit. A stale copy would undo a teammate's work.\n"
        "4. Hand your work over: on a branch `wp/<short-name>` cut from `main`, commit only the source files of the "
        "components you changed (under `force-app/main/default/`, retrieved from your org), push it, and open a pull "
        "request into `main` whose description lists every component in backticks, one per line, as `Type:Name` "
        "(for example `ApexClass:InvoiceService` or `Layout:Account-Account Layout`). The captain delivers it and "
        "reports back on the pull request. If it comes back, merge `main` into the same branch, check it in your org, "
        "and push again.\n"
        "5. Never push to `main` or to `mp/ledger`, never merge a pull request yourself, and never force-push.\n"
        "6. Never use `--ignore-conflicts`, wildcards or whole-folder deploys against anyone else's org.\n"
        "7. Editors deploy without passing the `sf` guard: keep deploy-on-save off "
        "(`salesforcedx-vscode-core.push-or-deploy-on-save.enabled`), and keep your own org, never the common org, as "
        "this project's default org.\n"
        "See TEAM.md for setup and the team board.\n")
    version = sf_mp_version()
    (repo / "TEAM.md").write_text(
        f"# {team_name}\n"
        "Built with SF Demo Scout's team mode. The team board (members, work packages, deliveries) is the `README.md` "
        "on the `mp/ledger` branch; Scout keeps it current.\n\n"
        "## With Scout\nTell Scout: `/scout session join <this repository's URL>`. It sets everything up.\n\n"
        "## Without Scout (Cursor, Copilot, plain CLI)\n"
        "1. Clone this repository, and set your Git name and email.\n"
        f"2. Install the guard: `sf plugins install file:$(pwd)/tools/sf-mp-{version}.tgz` (answer `y`: it isn't signed by "
        "Salesforce), then run `sf mp init --guard-only` in the clone. From then on `sf` on your machine refuses writes to "
        "the common org. Fix what its warnings name: deploy-on-save in your editor goes around the guard.\n"
        "3. Make your own org this project's default (`sf config set target-org <your org>`), never the common org.\n"
        "4. Build in your own org, following `AGENTS.md`, and hand over with a `wp/<name>` branch and a pull request "
        "that lists your components in backticks as `Type:Name`.\n\n"
        "## The rules\nSee `AGENTS.md`. Only the captain's machine writes to the common org.\n")
    tools = repo / "tools"
    tools.mkdir(exist_ok=True)
    shutil.copyfile(build_tarball(tarball_path()), tools / f"sf-mp-{version}.tgz")


def build_org_record(build, label):
    return {"org_id": build["org_id"], "username": build.get("username"), "label": label or build["label"]}


def cmd_start(a):
    common = org_info(a.common_org)
    build = org_info(a.build_org) if a.build_org else None
    if build and build["org_id"] == common["org_id"]:
        raise refused("your build org must be your own sandbox, not the common org")
    ensure_guard(a.yes_guard)
    checkout = Path(a.checkout).expanduser() if a.checkout else workspace() / "teams" / slug(a.name)
    if checkout.exists() and any(checkout.iterdir()):
        raise refused(f"{checkout} already exists and isn't empty")
    checkout.parent.mkdir(parents=True, exist_ok=True)
    result = run([tool("git"), "clone", "--quiet", a.remote, str(checkout)], timeout=300)
    if result.returncode:
        raise failed("couldn't clone the team repository", detail=result.stderr.strip()[-400:])
    if out(checkout, "ls-remote", "origin", timeout=60):
        shutil.rmtree(checkout)
        raise refused("that repository isn't empty: join it instead, or start the team in a new one")
    ident = identity(checkout)
    git(checkout, "symbolic-ref", "HEAD", "refs/heads/main")
    scaffold(checkout, a.name, common, ident["name"])
    code, init = sf(["mp", "init", "--target-org", common["target"]], cwd=checkout, timeout=300)
    if code:
        raise failed("sf mp init didn't bind the common org", detail=init)
    git(checkout, "add", "-A")
    git(checkout, "commit", "--quiet", "-m", f"{a.name}: the kit project for {common['label']}")
    git(checkout, "push", "--quiet", "-u", "origin", "main", timeout=120)
    team_id = init["session"]
    me = slug(ident["name"], "captain")

    def change(state):
        if state["team"]:
            raise refused("this repository already has a team ledger")
        team = {"schema": 1, "team": team_id, "name": a.name, "created_at": now(), "captain": me, "repo": a.remote,
                "common_org": {"org_id": common["org_id"], "label": common["label"]}, "test_level": init.get("testLevel")}
        member = {"schema": 1, "id": me, "name": ident["name"], "git_email": ident["email"], "github": a.github,
                  "role": "captain", "scout": True, "joined_at": now(),
                  "build_org": build_org_record(build, a.build_label) if build else None}
        return ({"team.json": team, f"members/{me}.json": member},
                f"{ident['name']} started the team {a.name} on {common['label']}, as captain", "start", None)

    written = ledger_write(checkout, ident, change)
    save_team(team_id, {"name": a.name, "slug": slug(a.name), "checkout": str(checkout), "remote": a.remote, "me": me,
                        "role": "captain", "common_org_id": common["org_id"], "common_target": common["target"],
                        "build_org_id": build["org_id"] if build else None, "build_target": build["target"] if build else None,
                        "github": a.github, "joined_at": now()})
    save_cache(team_id, reported=written["commit"], watched=written["commit"])
    return {"team": team_id, "name": a.name, "checkout": str(checkout), "remote": a.remote, "me": me, "role": "captain",
            "common_org": common["label"], "test_level": init.get("testLevel"), "warnings": init.get("warnings", []),
            "join": f"/scout session join {a.remote}"}


def accept_invitation(repository):
    code, stdout, _ = gh(["api", "/user/repository_invitations"])
    if code:
        return "couldn't list your GitHub invitations"
    for invitation in json.loads(stdout or "[]"):
        if (invitation.get("repository") or {}).get("full_name", "").lower() == repository.lower():
            code, _, stderr = gh(["api", "-X", "PATCH", f"/user/repository_invitations/{invitation['id']}"])
            return "accepted" if not code else "couldn't accept: " + stderr[-200:]
    return "none pending"


def cmd_join(a):
    if a.no_guard:  # before anything changes: the lane can't work without it
        raise refused("this team runs on Scout's own lane, which relies on the guard on every member's machine, so it "
                      "can't be joined without it; nothing changed. A team on Lifecycle Center works without the guard",
                      guard="required")
    build = org_info(a.build_org)
    if not a.yes_guard:
        raise decide(f"{GUARD_WHAT} {LANE_GUARD}", needs="guard-install", guard="required", version=sf_mp_version(),
                     choices=["join with the guard: run join again with --yes-guard",
                              "or don't join: this team can't be joined without it"])
    invitation = None
    repository = github_repo(a.remote)
    if a.accept_invite and repository:
        invitation = accept_invitation(repository)
    name = repository.split("/")[1] if repository else Path(a.remote.rstrip("/")).stem
    checkout = Path(a.checkout).expanduser() if a.checkout else workspace() / "teams" / slug(name)
    if (checkout / ".git").exists():
        git(checkout, "fetch", "--quiet", "origin", timeout=120)
    else:
        if checkout.exists() and any(checkout.iterdir()):
            raise refused(f"{checkout} exists and isn't a clone of the team repository")
        checkout.parent.mkdir(parents=True, exist_ok=True)
        result = run([tool("git"), "clone", "--quiet", a.remote, str(checkout)], timeout=300)
        if result.returncode:
            raise refused("couldn't clone the team repository; if the captain just invited you, accept the "
                          "invitation first", detail=result.stderr.strip()[-300:], invitation=invitation)
    tip = ledger_fetch(checkout)
    state = read_ledger(checkout, tip)
    team = state["team"]
    if not team:
        raise refused("this repository has no team ledger; ask the captain to start the team with Scout")
    if build["org_id"] == (team.get("common_org") or {}).get("org_id"):
        raise refused("your build org must be your own sandbox, not the team's common org")
    ensure_guard(a.yes_guard)
    ident = identity(checkout)
    code, init = sf(["mp", "init", "--guard-only"], cwd=checkout, timeout=300)
    if code:
        raise failed("sf mp init --guard-only didn't register the common org's guard", detail=init)
    holder = {}

    def change(state):
        existing = next((m for m in state["members"].values() if (m.get("git_email") or "").lower() == ident["email"].lower()), None)
        member_id = existing["id"] if existing else slug(ident["name"], "builder")
        suffix = 2
        while not existing and member_id in state["members"]:
            member_id = f"{slug(ident['name'], 'builder')}-{suffix}"
            suffix += 1
        holder["id"] = member_id
        member = dict(existing or {}, schema=1, id=member_id, name=ident["name"], git_email=ident["email"],
                      github=a.github or (existing or {}).get("github"), role=(existing or {}).get("role", "builder"),
                      scout=True, joined_at=(existing or {}).get("joined_at") or now(),
                      build_org=build_org_record(build, a.build_label))
        return ({f"members/{member_id}.json": member},
                f"{ident['name']} joined as {member['role']} (builds in {member['build_org']['label']})", "join", None)

    written = ledger_write(checkout, ident, change, team["team"])
    me = holder["id"]
    role = written["state"]["members"][me]["role"]
    save_team(team["team"], {"name": team.get("name"), "slug": slug(team.get("name")), "checkout": str(checkout),
                             "remote": a.remote, "me": me, "role": role,
                             "common_org_id": team["common_org"]["org_id"], "build_org_id": build["org_id"],
                             "build_target": build["target"], "github": a.github, "joined_at": now()})
    save_cache(team["team"], reported=written["commit"], watched=written["commit"])
    state = written["state"]
    return {"team": team["team"], "name": team.get("name"), "checkout": str(checkout), "me": me, "role": role,
            "captain": name_of(state, team.get("captain")), "common_org": team["common_org"]["label"],
            "open_packages": [p["id"] for p in state["packages"].values() if p.get("status") in OPEN],
            "invitation": invitation, "warnings": init.get("warnings", []) if isinstance(init, dict) else []}


# ---- work packages and their base ----

def package_write(repo, ident, team_id, entry, package_id, mutate, summary, kind, allowed=None):
    """One package's transition, with its precondition re-checked at every retry."""
    def change(state):
        if f"packages/{package_id}.json" in state["problems"]:
            raise refused(f"{package_id}'s ledger file is unreadable; ask the captain to look before changing it")
        current = state["packages"].get(package_id)
        if not current:
            raise refused(f"there's no work package {package_id}")
        if allowed and current.get("status") not in allowed:
            raise refused(f"{package_id} is {current.get('status')} now, so this step doesn't apply", status=current.get("status"))
        item = mutate(dict(current), state)
        if item is None:
            return None
        item["updated_at"] = now()
        item["history"] = current.get("history", []) + [{"status": item.get("status"), "at": now(), "by": entry["me"],
                                                          **({"note": item.get("note")} if item.get("note") else {})}]
        text = summary(item, state) if callable(summary) else summary
        return {f"packages/{package_id}.json": item}, text[:280], kind, package_id

    written = ledger_write(repo, ident, change, team_id)
    advance_if_only_mine(repo, team_id, ident, written)
    return written


def advance_if_only_mine(repo, team_id, ident, written):
    """After my own write, the cursors may skip it, unless others wrote before it and haven't been shown."""
    if not written.get("changed"):
        return
    state = cache_state(team_id)
    for cursor in ("reported", "watched"):
        if not ledger_events(repo, state.get(cursor), written["commit"], ident["email"]):
            advance(repo, team_id, cursor, written["commit"])


def base_check(repo, entry, components, ref):
    """Compares the builder's own org with `ref` for each component, so a stale copy is caught before any edit:
    same | new (in neither) | base (only in the org: the team doesn't hold it yet) | stale (differs) |
    missing (only in the team's source) | unknown."""
    if not entry.get("build_target"):
        raise refused("this machine has no build org for the team; join with your own sandbox first")
    theirs = org_files(entry["build_target"], components, source_api(repo, ref))
    team = files_at(repo, ref, set(components))
    outcomes = {}
    for component in components:
        org, mine = theirs[component], team.get(component)
        if org["state"] == "unknown":
            outcomes[component] = "unknown"
        elif org["state"] == "absent":
            outcomes[component] = "missing" if mine else "new"
        elif not mine:
            outcomes[component] = "base"
        else:
            outcomes[component] = "same" if same_files(org["files"], mine) else "stale"
    return outcomes, theirs


def remote_branch(repo, branch):
    return out(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}^{{commit}}", check=False) or None


def commit_files_on(repo, branch, base_ref, files, message, remove=()):
    """Commits files onto a branch (from origin's copy, or base_ref), pushes it, and returns its new tip."""
    git(repo, "checkout", "--quiet", "-B", branch, remote_branch(repo, branch) or base_ref)
    try:
        require_clean(repo)  # just before writing: an editor may have saved while the org was read
        for path, data in files.items():
            target = repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        if remove:
            git(repo, "rm", "--quiet", "-r", "--cached", "--ignore-unmatch", "--", *remove)
            for path in remove:
                (repo / path).unlink(missing_ok=True)
        if files:
            git(repo, "add", "--", *files)
        if out(repo, "diff", "--cached", "--name-only"):
            git(repo, "commit", "--quiet", "-m", message)
        push = git(repo, "push", "--quiet", "origin", f"{branch}:refs/heads/{branch}", check=False, timeout=120)
        if push.returncode:
            raise failed(f"couldn't push {branch}", detail=push.stderr.strip()[-300:])
        return out(repo, "rev-parse", "HEAD")
    finally:
        back_to_main(repo)


def back_to_main(repo):
    """Back on main at origin's main. Never forced, so work an editor saved meanwhile is kept, and the next step's clean
    check shows it."""
    if git(repo, "checkout", "--quiet", "main", check=False).returncode == 0:
        git(repo, "merge", "--quiet", "--ff-only", "refs/remotes/origin/main", check=False)


def prepare_base(repo, ident, team_id, entry, package_id, components):
    """Fixes the package's base, so a stale sandbox copy can't undo a teammate's delivered change: its branch is cut
    from main; each component is checked against the
    builder's org; a component only the org holds is committed as the base before any edit."""
    require_clean(repo)
    git(repo, "fetch", "--quiet", "origin", timeout=120)
    branch = f"wp/{package_id}"
    tip = remote_branch(repo, branch)
    if not tip:
        tip = out(repo, "rev-parse", "refs/remotes/origin/main")
        push = git(repo, "push", "--quiet", "origin", f"{tip}:refs/heads/{branch}", check=False, timeout=120)
        if push.returncode:
            raise failed(f"couldn't create {branch}", detail=push.stderr.strip()[-300:])
        git(repo, "fetch", "--quiet", "origin", timeout=120)
    outcomes, theirs = base_check(repo, entry, components, f"refs/remotes/origin/{branch}")
    base_files = {path: data for c, o in outcomes.items() if o == "base" for path, data in theirs[c]["files"].items()}
    if base_files:
        names = ", ".join(sorted(c for c, o in outcomes.items() if o == "base"))
        tip = commit_files_on(repo, branch, tip, base_files, f"{package_id} base: {names}, as in "
                                                               f"{entry.get('build_label') or 'the builder org'} before the work")
        for component in outcomes:
            if outcomes[component] == "base":
                outcomes[component] = "same"
    stale = sorted(c for c, o in outcomes.items() if o in ("stale", "missing", "unknown"))

    def mutate(item, state):
        checked = dict((item.get("base") or {}).get("checked") or {}, **outcomes)
        item["base"] = {"commit": tip, "checked": checked}
        item["branch"] = branch
        if not stale:
            item["synced_at"] = tip
        return item

    package_write(repo, ident, team_id, entry, package_id, mutate,
                  lambda item, state: f"{ident['name']}'s {package_id} starts from main"
                                      + (f"; {', '.join(stale)} need the team's version in their org first" if stale else ""),
                  "package-base", allowed=("building", "failed", "returned", "handed-over"))
    return {"branch": branch, "base": tip, "checked": outcomes, "stale": stale}


def unchecked(package, components):
    """Components without a base check, or whose check couldn't tell (unknown). Only these are checked again: a
    recorded check stands, since after the first edit the builder's org differs from main by design."""
    checked = (package.get("base") or {}).get("checked") or {}
    return sorted(c for c in components if checked.get(c) in (None, "unknown"))


def behind(package, components):
    """Components whose base check found the builder's org without the team's version (stale or missing), or
    couldn't tell (unknown), and that package sync hasn't cleared since."""
    checked = (package.get("base") or {}).get("checked") or {}
    return sorted(c for c in components if checked.get(c) in ("stale", "missing", "unknown"))


def package_start(repo, ident, team_id, entry, a):
    me = entry["me"]
    components = components_of(a.component)
    task = Path(a.task).name if a.task else None
    holder = {}

    def change(state):
        # The same start again (after a lost answer, or from a resumed session) finds its package.
        for package in by_number(state["packages"].values()):
            if a.title and (package.get("owner"), package.get("status"), package.get("title"), package.get("task"),
                            sorted(package.get("components") or [])) == (me, "building", a.title, task, components):
                holder.update(id=package["id"], reused=True)
                return None
        number = max([int(p.split("-")[1]) for p in state["packages"]] + [0]) + 1
        holder["id"] = package_id = f"WP-{number}"
        item = {"schema": 1, "id": package_id, "title": a.title or package_id, "owner": me, "status": "building",
                "components": components, "branch": f"wp/{package_id}", "head": None, "pr": None, "base": None,
                "synced_at": None, "criteria": criteria_from_task(a.task), "task": task,
                "note": None, "created_at": now(), "updated_at": now(),
                "history": [{"status": "building", "at": now(), "by": me}]}
        listed = f": {', '.join(components)}" if components else ""
        return ({f"packages/{package_id}.json": item},
                f"{ident['name']} started {package_id} \"{item['title']}\"{listed}", "package-start", package_id)

    written = ledger_write(repo, ident, change, team_id)
    advance_if_only_mine(repo, team_id, ident, written)
    package_id = holder["id"]
    state = written["state"]
    package = state["packages"][package_id]
    result = {"package": package_id, "status": "building", "components": components,
              "overlaps": overlaps(state, package_id, components), **({"reused": True} if holder.get("reused") else {})}
    if entry.get("build_target"):
        todo = unchecked(package, components)
        prepared = prepare_base(repo, ident, team_id, entry, package_id, todo) if todo else {}
        checked = dict((package.get("base") or {}).get("checked") or {}, **prepared.get("checked", {}))
        result.update(branch=prepared.get("branch") or package.get("branch"),
                      base=prepared.get("base") or (package.get("base") or {}).get("commit"), checked=checked,
                      stale=behind({"base": {"checked": checked}}, components))
        if result["stale"]:
            raise decide("your org's copy of these differs from the team's main; bring the team's version into your "
                         "org first (package sync), so your changes build on it", needs="sync", **result)
    return result


def cmd_package(a):
    team_id, entry = pick(a.team)
    repo, ident = team_context(team_id, entry)
    me = entry["me"]
    if a.action == "start":
        with CheckoutLock(repo):
            return package_start(repo, ident, team_id, entry, a)
    if a.action == "sync":
        return package_sync(repo, ident, team_id, entry, a)
    if a.action == "accept":
        if entry.get("role") != "captain":
            raise refused("the captain records whether a delivered package passes its checks in the common org")
        result = a.result or "passed"

        def mutate(item, state):
            item["accepted"] = {"result": result, "at": now(), "by": me, "note": a.note}
            return item

        package_write(repo, ident, team_id, entry, a.id, mutate,
                      f"{ident['name']} checked {a.id} in the common org: {result}" + (f" ({a.note})" if a.note else ""),
                      "package-accept", allowed=("delivered",))
        return {"package": a.id, "accepted": result}

    def owner_or_captain(item, state):
        if item.get("owner") != me and me != (state["team"] or {}).get("captain"):
            raise refused(f"{a.id} is {name_of(state, item.get('owner'))}'s; ask them or the captain")

    if a.action == "stop":
        def mutate(item, state):
            owner_or_captain(item, state)
            item.update(status="stopped", note=a.note or "stopped")
            return item

        package_write(repo, ident, team_id, entry, a.id, mutate, f"{ident['name']} stopped {a.id}: {a.note or 'no reason given'}",
                      "package-stop", allowed=("building", "handed-over", "returned", "failed"))
        return {"package": a.id, "status": "stopped"}
    added = components_of(a.component)

    def mutate(item, state):
        owner_or_captain(item, state)
        components = (set(item.get("components") or []) | set(added)) - set(components_of(a.remove))
        item.update(components=sorted(components), title=a.title or item.get("title"))
        if a.task:
            item.update(criteria=criteria_from_task(a.task), task=Path(a.task).name)
        return item

    with CheckoutLock(repo):
        written = package_write(repo, ident, team_id, entry, a.id, mutate,
                                lambda item, state: f"{ident['name']} updated {a.id}: {', '.join(item['components']) or 'no components'}",
                                "package-update", allowed=("building", "failed", "returned", "handed-over"))
        package = written["state"]["packages"][a.id]
        result = {"package": a.id, "components": package.get("components"),
                  "overlaps": overlaps(written["state"], a.id, package.get("components") or [])}
        todo = unchecked(package, added)
        if todo and entry.get("build_target") and package.get("owner") == me:
            result.update(prepare_base(repo, ident, team_id, entry, a.id, todo))
            if result["stale"]:
                raise decide("your org's copy of these differs from the team's version; bring it into your org first "
                             "(package sync)", needs="sync", **result)
    return result


def package_sync(repo, ident, team_id, entry, a):
    """Deploys the package branch's version of components into the builder's own org, then checks again."""
    state = read_ledger(repo, ledger_fetch(repo, team_id))
    package = state["packages"].get(a.id)
    if not package or package.get("owner") != entry["me"]:
        raise refused(f"{a.id} isn't one of your packages")
    git(repo, "fetch", "--quiet", "origin", timeout=120)
    branch = package.get("branch") or f"wp/{a.id}"
    tip = remote_branch(repo, branch)
    if not tip:
        raise refused(f"{a.id} has no branch yet; start it again")
    wanted = components_of(a.component) or [c for c, o in ((package.get("base") or {}).get("checked") or {}).items()
                                            if o in ("stale", "missing")] or package.get("components") or []
    team = files_at(repo, tip, set(wanted))
    missing = sorted(set(wanted) - set(team))
    if missing:
        raise refused("the team's source has no copy of " + ", ".join(missing))
    with tempfile.TemporaryDirectory(prefix="scout-team-sync-") as tmp:
        project = Path(tmp)
        (project / "sfdx-project.json").write_text(json.dumps(dict(SFDX_PROJECT_TEMPLATE, sourceApiVersion=source_api(repo, tip))))
        for files in team.values():
            for path, data in files.items():
                (project / path).parent.mkdir(parents=True, exist_ok=True)
                (project / path).write_bytes(data)
        code, body = sf(["project", "deploy", "start", "--source-dir", "force-app", "--target-org", entry["build_target"],
                         "--test-level", "NoTestRun"], cwd=project, timeout=3600)
        if code and "does not have source tracking" in json.dumps(body):
            # The login says the sandbox tracks source but the org doesn't (for example, a sandbox created before its
            # production org turned tracking on): deploy the same files in metadata format, which needs no tracking.
            code, body = sf(["project", "convert", "source", "--root-dir", "force-app", "--output-dir", "mdapi"], cwd=project)
            if not code:
                code, body = sf(["project", "deploy", "start", "--metadata-dir", "mdapi", "--target-org", entry["build_target"],
                                 "--test-level", "NoTestRun"], cwd=project, timeout=3600)
        if code:
            raise failed("the deploy into your org failed", detail=body)
    outcomes, _ = base_check(repo, entry, wanted, tip)
    left = sorted(c for c, o in outcomes.items() if o != "same")

    def mutate(item, state):
        checked = dict((item.get("base") or {}).get("checked") or {}, **outcomes)
        item["base"] = {"commit": tip, "checked": checked}
        if not left and all(o == "same" or o == "new" for o in checked.values()):
            item["synced_at"] = tip
        return item

    package_write(repo, ident, team_id, entry, a.id, mutate,
                  f"{ident['name']} brought the team's {', '.join(wanted)} into their org for {a.id}", "package-sync",
                  allowed=("building", "failed", "returned", "handed-over"))
    if left:
        raise failed("your org still differs from the team's copy for " + ", ".join(left), checked=outcomes)
    return {"package": a.id, "synced": wanted, "base": tip}


# ---- hand-over ----

def pr_body(package, state):
    lines = [f"Work package **{package['id']}** from {name_of(state, package.get('owner'))}, handed over through Scout's team mode.",
             "", "Components:"] + [f"- `{c}`" for c in package.get("components") or []]
    criteria = [c for c in package.get("criteria") or [] if c.get("text")]
    if criteria:
        lines += ["", "Acceptance criteria:"] + [f"- {c.get('item') or '-'}: {c['text']}" for c in criteria]
    if package.get("overwrite"):
        lines += ["", "**Replaces the team's copy of:** " + ", ".join(package["overwrite"])]
    lines += ["", "The captain's Scout delivers this into the common org through the guarded lane and reports back "
                  "here; please don't merge it by hand."]
    return "\n".join(lines)


def cmd_handover(a):
    team_id, entry = pick(a.team)
    repo, ident = team_context(team_id, entry)
    if not entry.get("build_target"):
        raise refused("this machine has no build org for the team; join with your own sandbox first")
    with CheckoutLock(repo):
        return handover(repo, ident, team_id, entry, a)


def handover(repo, ident, team_id, entry, a):
    state = read_ledger(repo, ledger_fetch(repo, team_id))
    package = state["packages"].get(a.id)
    if not package:
        raise refused(f"there's no work package {a.id}")
    if package.get("owner") != entry["me"]:
        raise refused(f"{a.id} is {name_of(state, package.get('owner'))}'s to hand over")
    if package.get("status") not in ("building", "failed", "returned", "handed-over"):
        raise refused(f"{a.id} is {package.get('status')}; nothing to hand over now")
    components = components_of(a.component) or package.get("components") or []
    if not components:
        raise refused(f"{a.id} names no components yet")
    require_clean(repo)
    git(repo, "fetch", "--quiet", "origin", timeout=120)
    overwrite = sorted(set(components_of(a.overwrite)))
    if set(overwrite) - set(components):
        raise refused("--overwrite names components outside this hand-over: " + ", ".join(sorted(set(overwrite) - set(components))))
    unbased = unchecked(package, components)
    if unbased:
        prepared = prepare_base(repo, ident, team_id, entry, a.id, unbased)
        stale = sorted(set(prepared["stale"]) - set(overwrite))
        if stale:
            raise decide("these were changed in your org without a recorded base, so Scout can't tell your edits from a "
                         "stale copy. Safest: bring the team's version into your org and redo the edits (package sync). "
                         "Or hand them over as a full replacement of the team's copy (--overwrite), which the captain "
                         "sees in full", needs="base", components=stale)
        state = read_ledger(repo, ledger_fetch(repo, team_id))
        package = state["packages"][a.id]
    # A base found stale or missing when the package started holds until package sync clears it; each --overwrite
    # exempts only the component it names.
    old = sorted(set(behind(package, components)) - set(overwrite))
    if old:
        raise decide("your org didn't have the team's version of these when the package started, and package sync hasn't "
                     "brought it in since, so handing them over would undo teammates' work. Bring the team's version into "
                     "your org (package sync) and redo your edits on it; or, on the SE's explicit yes, hand them over as a "
                     "full replacement of the team's copy (--overwrite)", needs="sync", components=old)
    branch = package.get("branch") or f"wp/{a.id}"
    tip = remote_branch(repo, branch)
    synced = package.get("synced_at") or (package.get("base") or {}).get("commit")
    if tip and synced and tip != synced:
        moved = out(repo, "diff", "--name-only", synced, tip, check=False).splitlines()
        moved = sorted(({component_of(p) for p in moved} & set(components)) - set(overwrite))
        if moved:
            raise decide("the hand-over branch has changes your org doesn't (main was merged in): bring them into your "
                         "org first (package sync), check them, then hand over", needs="sync", components=moved)
    theirs = org_files(entry["build_target"], components, source_api(repo, tip or "refs/remotes/origin/main"))
    unknown = sorted(c for c, o in theirs.items() if o["state"] != "present")
    if unknown:
        raise failed("these didn't come back from your org: " + ", ".join(unknown),
                     detail={c: theirs[c]["problem"] for c in unknown})
    files = {path: data for c in components for path, data in theirs[c]["files"].items()}
    team = files_at(repo, tip, set(components)) if tip else {}
    remove = sorted(p for c in components if c.startswith("LightningComponentBundle:") or c.startswith("AuraDefinitionBundle:")
                    for p in (team.get(c) or {}) if p not in theirs[c]["files"])
    label = (state["members"].get(entry["me"]) or {}).get("build_org", {}).get("label", "their org")
    head = commit_files_on(repo, branch, tip or "refs/remotes/origin/main", files,
                           f"{a.id}: {package.get('title')}, handed over by {ident['name']} from {label}", remove)
    criteria = criteria_from_task(a.task) if a.task else package.get("criteria") or []
    pr, pr_note = package.get("pr"), None
    repository = github_repo(entry.get("remote"))
    if repository and not a.no_pr:
        draft = dict(package, components=components, criteria=criteria, overwrite=overwrite)
        if pr:
            if pr_comment(team_id, entry, pr, f"Handed over again at {head[:12]}: {', '.join(components)}.") is False:
                pr_note = UNSENT
        else:
            captain = state["members"].get((state["team"] or {}).get("captain")) or {}
            args = ["pr", "create", "--repo", repository, "--base", "main", "--head", branch,
                    "--title", f"{a.id}: {package.get('title')}", "--body", pr_body(draft, state)]
            if captain.get("github") and captain.get("github") != entry.get("github"):
                args += ["--reviewer", captain["github"], "--assignee", captain["github"]]
            code, stdout, stderr = gh(args)
            pr = stdout.splitlines()[-1] if not code and stdout else None
            pr_note = None if pr else "no pull request: " + stderr[-200:]

    def mutate(item, state):
        item.update(status="handed-over", components=components, branch=branch, head=head, pr=pr, criteria=criteria,
                    synced_at=head, overwrite=overwrite, note=None)
        return item

    link = f" ({pr})" if pr else f" (branch {branch})"
    package_write(repo, ident, team_id, entry, a.id, mutate,
                  f"{ident['name']} handed over {a.id} \"{package.get('title')}\": {', '.join(components)}{link}",
                  "handover", allowed=("building", "failed", "returned", "handed-over"))
    return {"package": a.id, "status": "handed-over", "branch": branch, "head": head, "pr": pr, "pr_note": pr_note,
            "components": components, "overwrite": overwrite}


# ---- delivery (the captain's lane) ----

def receipt_path(repo):
    return repo / ".git" / "scout-delivery.json"


def read_receipt(repo):
    """The unfinished delivery's receipt, or None when there's none. An unreadable receipt is never taken for none: it
    comes back as {"unreadable": …}, which blocks deliveries and shows as open."""
    path = receipt_path(repo)
    try:
        receipt = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        receipt = error
    if not isinstance(receipt, dict):
        return {"unreadable": f"{path}: {receipt}", "phase": "unreadable", "package": None}
    return receipt


def write_receipt(repo, **changes):
    receipt = dict(read_receipt(repo) or {}, **changes)
    write_json_atomic(receipt_path(repo), receipt, mode=0o644)
    return receipt


def unfinished(receipt):
    if receipt.get("unreadable"):
        return refused("the delivery receipt is unreadable, so Scout can't tell whether a delivery is unfinished: "
                       + receipt["unreadable"] + ". Look at it with the captain (and sf mp status) before going on",
                       outcome="unreadable", receipt=receipt)
    return refused(f"{receipt.get('package')}'s delivery from {receipt.get('started_at')} isn't finished "
                   f"({receipt.get('phase')}); say \"resume delivery\" first", receipt=receipt)


class CheckoutLock:
    """One Scout step at a time that changes the team checkout's branch or files: package start and update, hand-over,
    refresh, delivery, reconcile and back-flow, so the revision the lane verifies is the one main gets. While a
    delivery's receipt is outstanding, only
    its resumption runs."""

    def __init__(self, repo, resuming=False):
        self.repo, self.resuming = repo, resuming
        self.path = repo / ".git" / "scout-team.lock"

    def __enter__(self):
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                with os.fdopen(fd, "w") as handle:
                    json.dump({"pid": os.getpid(), "at": now()}, handle)
                break
            except FileExistsError:
                try:
                    os.kill(int(json.loads(self.path.read_text())["pid"]), 0)
                    raise refused("another Scout team step is running in this checkout; let it finish, then ask again")
                except (ProcessLookupError, ValueError, KeyError, OSError):
                    self.path.unlink(missing_ok=True)
        else:
            raise refused("couldn't take the team checkout's lock")
        receipt = read_receipt(self.repo)
        if receipt and not self.resuming:
            self.path.unlink(missing_ok=True)
            raise unfinished(receipt)
        return self

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)


def lane_status(repo):
    code, body = sf(["mp", "status"], cwd=repo, timeout=120)
    if code or not isinstance(body, dict):
        raise failed("sf mp status failed in the lane checkout", detail=body)
    return body


def journal_record(repo, op_id):
    """The lane's settled record of an operation; None when there's none. An unreadable one stops the step."""
    path = repo / ".mp" / "journal" / f"{op_id}.json"
    try:
        record = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        record = error
    if not isinstance(record, dict):
        raise failed(f"the lane's record of {op_id} is unreadable ({record}), so Scout can't tell what reached the "
                     "org: run sf mp status with the captain", outcome="open", evidence=True)
    return record


def newest_journal(repo, receipt):
    """The lane's settled record of this delivery's deploy, when the deploy's answer was lost: created after the
    receipt, for its components and its merge. Times compare as times, not text; a record that changed
    since the receipt but can't be read stops the step rather than counting as none."""
    since = moment(receipt.get("started_at"))
    journal = repo / ".mp" / "journal"
    found, unreadable, other = [], [], []
    for path in sorted(journal.glob("*.json")) if journal.exists() and since else []:
        if path.name.startswith(("open-", ".")):
            continue
        try:
            record = json.loads(path.read_text())
            if not isinstance(record, dict):
                raise ValueError("not a record")
        except (OSError, ValueError):
            if path.stat().st_mtime >= since.timestamp():
                unreadable.append(path.name)
            continue
        created = moment(record.get("createdAt"))
        if not (created and created >= since and record.get("kind", "deploy") == "deploy"):
            continue
        if (sorted(record.get("components") or []) == sorted(receipt.get("components") or [])
                and (record.get("candidate") or {}).get("revision") == receipt.get("integration")):
            found.append((created, record))
        elif set(record.get("components") or []) & set(receipt.get("components") or []):
            other.append(record.get("opId") or path.stem)
    if not found and (unreadable or other):
        raise failed("the lane's journal has records from this delivery's time that Scout can't match to it ("
                     + ", ".join(unreadable + other) + "), so it can't tell what reached the org: run sf mp status with "
                     "the captain", outcome="open", records=unreadable + other, evidence=True)
    return max(found, key=lambda pair: pair[0])[1] if found else None


def verified(record):
    """A real deploy whose read-back matched for every component it deployed; a settlement by hand counts only when it
    says so. A record without components, or a read-back missing one of them, verifies nothing."""
    if not record or record.get("checkOnly") or record.get("state") not in SUCCESS:
        return False
    if "verified" in record:
        return record["verified"] is True
    readback, components = record.get("readback") or {}, record.get("components") or []
    return bool(components) and all(isinstance(readback.get(c), dict) and readback[c].get("matches") for c in components)


def record_delivery(repo, ident, entry, team_id, package_id, record, status, note=None, allowed=("delivering",),
                    head=None, components=None, stale_ok=False):
    """The delivery record and the package's new status, in one ledger write, from an expected status and, given a
    head and components, only for that hand-over: one handed over again or changed meanwhile isn't recorded as this
    one's result. With stale_ok, a check-only result for the earlier hand-over is kept as a delivery
    record alone, and the newer hand-over stays as it is."""
    holder = {}

    def delivery(at_head):
        return {"schema": 1, "package": package_id, "by": entry["me"], "op_id": record["opId"], "state": record.get("state"),
                "check_only": bool(record.get("checkOnly")), "job_id": record.get("jobId"),
                "components": record.get("components") or [], "steward": bool(record.get("steward")),
                "verified": verified(record), "head": at_head, "at": now(), "note": note}

    def change(state):
        current = state["packages"].get(package_id)
        if not current:
            raise refused(f"there's no work package {package_id}")
        if (head and current.get("head") != head) or (
                components is not None and sorted(current.get("components") or []) != sorted(components)):
            if stale_ok and record and record.get("opId"):
                holder["stale"] = True
                if record["opId"] in state["deliveries"]:
                    return None
                return ({f"deliveries/{record['opId']}.json": delivery(head)},
                        f"{ident['name']} checked an earlier hand-over of {package_id} ({str(head)[:12]}): {note}; it has "
                        "been handed over again since"[:280], "delivery-checked", package_id)
            raise refused(f"{package_id} was handed over again, or its components changed, while this step worked on "
                          f"{str(head)[:12]}, so its result isn't recorded against the new version: deliver it again",
                          outcome="moved", head=current.get("head"), components=current.get("components"))
        if current.get("status") not in allowed:
            if current.get("status") == status:
                return None  # already recorded, for example by an earlier attempt whose answer was lost
            raise refused(f"{package_id} is {current.get('status')}, not {' or '.join(allowed)}")
        item = dict(current, status=status, note=note, updated_at=now())
        item["history"] = current.get("history", []) + [{"status": status, "at": now(), "by": entry["me"],
                                                          "op": (record or {}).get("opId"), "note": note}]
        updates = {f"packages/{package_id}.json": item}
        if record and record.get("opId"):
            updates[f"deliveries/{record['opId']}.json"] = delivery(current.get("head"))
        verb = {"delivered": "delivered", "failed": "couldn't deliver", "delivering": "is delivering",
                "handed-over": "checked", "returned": "returned"}[status]
        what = ", ".join((record or {}).get("components") or current.get("components") or [])
        summary = (f"{ident['name']} {verb} {package_id} \"{current.get('title')}\" to "
                   f"{((state['team'] or {}).get('common_org') or {}).get('label')} ({what})" + (f": {note}" if note else ""))
        return updates, summary[:280], "deliver" if status == "delivered" else "delivery-" + status, package_id

    written = ledger_write(repo, ident, change, team_id)
    advance_if_only_mine(repo, team_id, ident, written)
    return dict(written, stale=bool(holder.get("stale")))


UNSENT = "the pull request comment didn't go out; Scout sends it again at the next team step on this machine"


def unsent_file(team_id):
    return cache_dir(team_id) / "unsent-comments.json"


def unsent(team_id):
    try:
        items = json.loads(unsent_file(team_id).read_text())
    except (OSError, ValueError):
        return []
    return [c for c in items if isinstance(c, dict) and c.get("pr") and c.get("body")] if isinstance(items, list) else []


def send_comment(pr, body, timeout=60):
    """None when GitHub took the comment, else what went wrong."""
    try:
        code, _, stderr = gh(["pr", "comment", pr, "--body", body], timeout=timeout)
    except Stop as stop:
        return stop.data["reason"]
    return None if code == 0 else (stderr or "no answer")[-200:]


def pr_comment(team_id, entry, pr, body):
    """A comment on a hand-over's pull request, which is how teammates without Scout hear from the team. One GitHub
    doesn't take is kept and sent again at the next team step. True: sent; False: kept; None: no PR."""
    if not pr or not github_repo(entry.get("remote")):
        return None
    problem = send_comment(pr, body)
    if problem:
        write_json_atomic(unsent_file(team_id), unsent(team_id) + [{"pr": pr, "body": body, "at": now(), "problem": problem}])
        return False
    return True


def resend_comments(team_id):
    """Sends the comments GitHub didn't take earlier, oldest first, stopping at the first that still fails."""
    pending = unsent(team_id)
    for number, comment in enumerate(pending):
        if send_comment(comment["pr"], comment["body"], timeout=20):
            write_json_atomic(unsent_file(team_id), pending[number:])
            return len(pending) - number
    if pending:
        unsent_file(team_id).unlink(missing_ok=True)
    return 0


def mention(owner):
    return f"@{owner['github']} " if owner.get("github") else ""


def scope_problems(repo, package, base_ref):
    """Every file the hand-over changes must belong to a declared component."""
    head = package["head"]
    merge_base = out(repo, "merge-base", base_ref, head)
    changed = out(repo, "diff", "--name-only", merge_base, head).splitlines()
    declared = set(package.get("components") or [])
    stray = sorted(p for p in changed if component_of(p) not in declared and not p.endswith("/.gitkeep"))
    return stray


def empty_components(repo, head, components):
    """Declared components the hand-over carries no source for (v1 delivers no deletions)."""
    return sorted(set(components) - set(files_at(repo, head, set(components))))


def org_matches_base(repo, package, item):
    """At a conflict: does the common org still hold the version this hand-over started from (its base)?"""
    base = (package.get("base") or {}).get("commit")
    saved, files = Path(item.get("saved") or ""), item.get("files") or []
    if not base or not saved.is_dir() or not files:
        return False
    meta = next((f for f in files if f.endswith("-meta.xml")), files[0])
    anchor = meta.rsplit("/", 1)[0]
    org = {anchor + "/" + p.relative_to(saved / "files").as_posix(): p.read_bytes()
           for p in (saved / "files").rglob("*") if p.is_file()}
    at_base = files_at(repo, base, {item["component"]}).get(item["component"]) or {}
    return bool(at_base) and same_files(org, at_base)


def publish(repo, ident, entry, team_id, package, owner, receipt, record, readback=None):
    """After a verified delivery: origin's main moves to exactly the delivered merge, by fast-forward only, then the
    ledger and the pull request; the receipt goes last. Repeatable from the receipt."""
    integration = receipt["integration"]
    deployed = ((record or {}).get("candidate") or {}).get("revision")
    if record and deployed != integration:
        raise failed(f"the lane deployed {str(deployed)[:12]}, not this delivery's merge {integration[:12]}, so main doesn't "
                     "move: something changed the lane checkout during the delivery. Look at both commits with the "
                     "captain before going on", outcome="mismatch", phase=receipt.get("phase"), deployed=deployed,
                     integration=integration)
    write_receipt(repo, phase="publishing")
    git(repo, "fetch", "--quiet", "origin", timeout=120)
    main = out(repo, "rev-parse", "refs/remotes/origin/main")
    if main != integration:
        if not is_ancestor(repo, main, integration):
            raise failed("main moved since this delivery's merge (a push outside a delivery), so Scout won't publish over "
                         "it: the delivery is in the org, and main must show exactly what was deployed. Look at main's new "
                         "commits with the captain, then say \"resume delivery\"", phase="publishing", main=main,
                         integration=integration)
        push = git(repo, "push", "--quiet", "origin", f"{integration}:refs/heads/main", check=False, timeout=120)
        if push.returncode:
            raise failed("main couldn't be pushed; the delivery is in the org, and its publication waits (say \"resume "
                         "delivery\")", detail=push.stderr.strip()[-200:], phase="publishing")
        git(repo, "fetch", "--quiet", "origin", timeout=120)
    back_to_main(repo)
    readback = readback or ("deployed and read back" if record else "already in the org")
    record_delivery(repo, ident, entry, team_id, package["id"], record, "delivered", readback, head=receipt.get("head"),
                    components=receipt.get("declared"))
    notified = pr_comment(team_id, entry, package.get("pr"), mention(owner) + f"Delivered to the common org ({readback}): "
                          f"{', '.join(package.get('components') or [])}. `main` is at {integration[:12]}.")
    receipt_path(repo).unlink(missing_ok=True)
    git(repo, "branch", "-D", "mp/integrate", check=False)
    return {"outcome": "delivered", "main": integration, "package": package["id"], "readback": readback,
            **({"notified": False, "note": UNSENT} if notified is False else {})}


def settle_outcome(repo, ident, entry, team_id, package, owner, receipt, record, dry_run):
    """What a finished (or unfinished) deploy record means for the package. Each path records its result in the
    ledger before the receipt goes, so a ledger that can't be reached leaves the receipt to resume from. A
    check-only result for a hand-over replaced meanwhile is recorded against the earlier one alone."""
    head, declared = receipt.get("head"), receipt.get("declared")
    check_only = bool(dry_run or (record or {}).get("checkOnly"))
    if record and record.get("state") in SUCCESS and check_only:
        back_to_main(repo)
        written = record_delivery(repo, ident, entry, team_id, package["id"], record, "handed-over",
                                  "validated with a check-only deploy", allowed=("handed-over",), head=head,
                                  components=declared, stale_ok=True)
        receipt_path(repo).unlink(missing_ok=True)
        return {"outcome": "validated", "package": package["id"], "op": record,
                **({"note": f"this validated {str(head)[:12]}, but {package['id']} has been handed over again since: "
                            "validate the new version"} if written["stale"] else {})}
    if verified(record):
        return dict(publish(repo, ident, entry, team_id, package, owner, receipt, record), op=record)
    if record and record.get("state") in ("settled-failed", "reconciled-failed"):
        back_to_main(repo)
        reasons = (record.get("result") or {}).get("reasons") or (record.get("result") or {}).get("failures") or []
        note = ("; ".join(reasons) or record.get("note") or "the deploy failed")[:400]
        # A failed validation sends the package back too: it would fail the same way for real.
        written = record_delivery(repo, ident, entry, team_id, package["id"], record, "failed", note, head=head,
                                  components=declared, allowed=("handed-over",) if check_only else ("delivering",),
                                  stale_ok=check_only)
        receipt_path(repo).unlink(missing_ok=True)
        if written["stale"]:
            raise Stop(1, note, outcome="failed", package=package["id"], op=record,
                       stale=f"this was {str(head)[:12]}; {package['id']} has been handed over again since, and is untouched")
        notified = pr_comment(team_id, entry, package.get("pr"), mention(owner) + f"The delivery to the common org stopped: {note}")
        raise Stop(1, note, outcome="failed", package=package["id"], op=record,
                   **({"notified": False, "note": UNSENT} if notified is False else {}))
    if record and record.get("state") in SUCCESS:
        raise decide("the delivery was settled without a verified read-back, so main doesn't move. Check the org, then "
                     "either `deliver --resume --recheck`, which publishes only if a fresh read of the org matches the "
                     "delivered merge, or `deliver --resume --give-back --note \"[WHAT YOU CHECKED]\"`, which leaves main "
                     "as it is and sends the package back to its owner", outcome="unverified", op=record)
    note = ((record or {}).get("note") or "the deploy's outcome isn't settled")[:300]
    raise Stop(1, note + "; say \"resume delivery\" to reconcile it", outcome="open", package=package["id"], op=record)


def cmd_deliver(a):
    team_id, entry = pick(a.team)
    repo, ident = team_context(team_id, entry)
    if entry.get("role") != "captain":
        raise refused("only the captain's machine delivers to the common org; Scout has told the captain it's ready")
    if (a.recheck or a.give_back) and not a.resume:
        raise refused("--recheck and --give-back finish an unfinished delivery: use them with --resume")
    if a.give_back and not a.note:
        raise refused("say what you checked in the org: --give-back needs --note")
    with CheckoutLock(repo, resuming=a.resume):
        if a.resume:
            return resume_delivery(repo, ident, entry, team_id, recheck=a.recheck, give_back=a.note if a.give_back else None)
        return deliver(repo, ident, entry, team_id, a)


def deliver(repo, ident, entry, team_id, a):
    state = read_ledger(repo, ledger_fetch(repo, team_id))
    if f"packages/{a.id}.json" in state["problems"]:
        raise refused(f"{a.id}'s ledger file is unreadable; look at it before delivering")
    package = state["packages"].get(a.id)
    if not package:
        raise refused(f"there's no work package {a.id}")
    if package.get("status") != "handed-over" or not package.get("head"):
        raise refused(f"{a.id} is {package.get('status')}, not handed over")
    components = package.get("components") or []
    if not components:  # nothing named is nothing checked: never "already in the org"
        raise refused(f"{a.id} names no components, so there's nothing Scout can deliver or verify; its owner names them "
                      f"(package update --id {a.id} --component Type:Name) and hands it over again", outcome="scope")
    require_clean(repo)
    lane = lane_status(repo)
    if not lane.get("thisCheckoutIsTheLane"):
        raise refused("this checkout isn't the common org's lane on this machine (sf mp init binds it)")
    if lane.get("open"):
        raise refused("an operation is still open on the common org; say \"resume delivery\" to reconcile it", open=lane["open"])
    git(repo, "fetch", "--quiet", "origin", timeout=120)
    if git(repo, "cat-file", "-e", package["head"] + "^{commit}", check=False).returncode:
        raise refused(f"{a.id}'s handed-over commit {package['head'][:12]} isn't in the team repository")
    stray = scope_problems(repo, package, "refs/remotes/origin/main")
    if stray:
        raise refused(f"{a.id} also changes files outside its components: {', '.join(stray[:8])}; ask its owner to split "
                      "the package or name them", outcome="scope", files=stray)
    empty = empty_components(repo, package["head"], components)
    if empty:
        raise refused(f"{a.id} names components its hand-over carries no source for: {', '.join(empty)}; ask its owner "
                      "to hand them over, or take them out of the package", outcome="scope", components=empty)
    steward = sorted(c for c in components if c.split(":", 1)[0] not in LANE_TYPES)
    if steward and not a.steward:
        raise decide("these components have no tested lane contract, so they need the steward route: " + ", ".join(steward),
                     needs="steward", components=steward)
    overwrites = sorted(set(package.get("overwrite") or []))
    if overwrites and not a.accept_overwrite:
        raise decide(f"{a.id} replaces the team's copy of {', '.join(overwrites)} with its owner's whole copy, which can drop "
                     "changes others made", needs="overwrite", components=overwrites)
    owner = state["members"].get(package.get("owner")) or {}
    require_clean(repo)  # again after the network waits: an editor may have saved meanwhile
    git(repo, "checkout", "--quiet", "-B", "mp/integrate", "refs/remotes/origin/main")
    merge = git(repo, "merge", "--no-ff", "--no-edit", "-m", f"Deliver {a.id}: {package.get('title')} "
                f"({owner.get('name', package.get('owner'))})", package["head"], check=False)
    if merge.returncode:
        conflicted = out(repo, "diff", "--name-only", "--diff-filter=U", check=False).splitlines()
        git(repo, "merge", "--abort", check=False)
        back_to_main(repo)
        note = "its branch conflicts with main in " + ", ".join(conflicted[:6])
        record_delivery(repo, ident, entry, team_id, a.id, None, "returned", note, allowed=("handed-over",),
                        head=package["head"], components=components)
        notified = pr_comment(team_id, entry, package.get("pr"), mention(owner) + f"{note}. Bring main into the branch "
                              f"(Scout: \"fix {a.id}\") and hand it over again.")
        raise decide(note, outcome="git-conflict", files=conflicted,
                     **({"notified": False, "note": UNSENT} if notified is False else {}))
    integration = out(repo, "rev-parse", "HEAD")
    flags = ["--target-org", entry["common_target"]] + (["--steward"] if steward else [])
    try:
        code, retrieved = sf(["mp", "retrieve", *[x for c in components for x in ("--metadata", c)], *flags], cwd=repo,
                             timeout=1800)
        if not isinstance(retrieved, dict) or "components" not in retrieved:
            raise refused("sf mp retrieve refused", detail=retrieved)
        plan = {item.get("component"): item for item in retrieved["components"] if isinstance(item, dict)}
        # A component the read left out, or an outcome this step doesn't know, is never taken for "go on".
        odd = {c: (plan.get(c) or {}).get("outcome") for c in components
               if (plan.get(c) or {}).get("outcome") not in RETRIEVE_OUTCOMES}
        if odd:
            raise refused("sf mp retrieve gave no outcome Scout can act on for " + ", ".join(sorted(odd)) + ", so "
                          "Scout can't tell what the common org holds; nothing was sent. Deliver again, and if it "
                          "persists, run sf mp status with the captain", outcome="unreported", components=odd)
        accepted = set(components_of(a.accept_org_change))
        for item in list(plan.values()):
            if item.get("outcome") == "conflict" and item.get("component") not in accepted and org_matches_base(repo, package, item):
                accepted.add(item["component"])
                item["detail"] = "the common org still holds the version this hand-over started from"
        blocked = [item for item in plan.values() if item.get("outcome") in ("unknown", "deleted-in-org", "refused")
                   or (item.get("outcome") == "conflict" and item.get("component") not in accepted)]
        if blocked:
            write_json_atomic(cache_dir(team_id) / "last-conflict.json", {"package": a.id, "head": package["head"],
                                                                         "at": now(), "components": blocked})
            raise decide("the common org's copy differs from what the team last saw", outcome="org-changed", package=a.id,
                         components=blocked, options=["keep the org's change: take it into main (takeorg), then the owner "
                                                      "brings main in and hands over again",
                                                      "overwrite it with the hand-over (deliver again with --accept-org-change)"])
        for component in sorted(accepted & {c for c, i in plan.items() if i.get("outcome") == "conflict"}):
            code, merged = sf(["mp", "retrieve", "--metadata", component, "--merged", *flags], cwd=repo, timeout=1800)
            item = (merged.get("components") or [{}])[0] if isinstance(merged, dict) else {}
            if item.get("outcome") != "merged":
                raise failed(f"couldn't record {component}'s org version as the hand-over's base", detail=merged)
            plan[component] = dict(item, detail=plan[component].get("detail") or item.get("detail"))
        if out(repo, "rev-parse", "HEAD") != integration:
            raise failed("the lane checkout moved off this delivery's merge while the common org was read; nothing was "
                         "sent. Deliver again")
    except Stop:
        back_to_main(repo)
        raise
    deploy = [c for c in components if plan.get(c, {}).get("outcome") != "matches"]
    summary = [{"component": c, "route": "steward" if c in steward else "lane", "outcome": plan.get(c, {}).get("outcome"),
                "detail": plan.get(c, {}).get("detail")} for c in components]
    if a.plan:
        back_to_main(repo)
        return {"package": a.id, "owner": owner.get("name"), "head": package["head"], "plan": summary, "deploy": deploy,
                "already_in_org": sorted(set(components) - set(deploy)), "steward": steward, "overwrite": overwrites}
    if not deploy and a.dry_run:  # nothing to validate, and a dry run never publishes
        back_to_main(repo)
        return {"outcome": "validated", "package": a.id, "plan": summary, "deployed": [],
                "note": "every component already matches the common org: nothing to deploy, and main doesn't move"}
    receipt = write_receipt(repo, package=a.id, head=package["head"], integration=integration, phase="merged", op=None,
                            started_at=now(), dry_run=bool(a.dry_run), components=deploy, declared=components)
    if not a.dry_run:
        try:
            record_delivery(repo, ident, entry, team_id, a.id, None, "delivering",
                            "delivery started" if deploy else "already in the org", allowed=("handed-over",),
                            head=package["head"], components=components)
        except Stop as stop:
            back_to_main(repo)
            if stop.code == 2:  # refused: nothing recorded, nothing sent. A lost answer keeps the receipt to resume from.
                receipt_path(repo).unlink(missing_ok=True)
            raise
    if not deploy:
        return dict(publish(repo, ident, entry, team_id, package, owner, receipt, None), plan=summary, deployed=[])
    write_receipt(repo, phase="deploying")
    # The package owner's yes comes with the hand-over; another component owner's comes from the captain.
    approvers = ([owner["name"]] if owner.get("name") and owner.get("name") != ident["name"] else []) + list(a.approved_by)
    approvals = [x for name in dict.fromkeys(approvers) for x in ("--approved-by", name)]
    code, record = sf(["mp", "deploy", *[x for c in deploy for x in ("--metadata", c)], *flags, *approvals]
                      + (["--dry-run"] if a.dry_run else []), cwd=repo, timeout=3600)
    if not isinstance(record, dict) or "state" not in record:
        # No answer: either sf mp refused before recording anything, or its process ended mid-deploy. Only the lane
        # can tell; while it holds an operation, the receipt stays and the delivery is resumed, never resent.
        try:
            lane = lane_status(repo)
        except Stop:
            lane = {"open": ["unknown"]}
        if lane.get("open") or newest_journal(repo, receipt):
            raise Stop(1, "the deploy ended without an answer, but the lane has its operation: say \"resume delivery\"",
                       outcome="open", package=a.id)
        back_to_main(repo)
        reasons = (record or {}).get("data", {}).get("reasons") if isinstance(record, dict) else None
        note = "the lane refused, nothing was sent: " + "; ".join(reasons or [str((record or {}).get("message", "no answer"))])[:380]
        if not a.dry_run:
            record_delivery(repo, ident, entry, team_id, a.id, None, "handed-over", note, head=package["head"],
                            components=components)
        receipt_path(repo).unlink(missing_ok=True)
        raise refused(note, outcome="refused", detail=record)
    write_receipt(repo, op=record.get("opId"))
    if record.get("opId"):  # sf mp answers with a summary; the lane's journal holds the whole record, revision included
        record = journal_record(repo, record["opId"]) or record
    result = settle_outcome(repo, ident, entry, team_id, package, owner, read_receipt(repo), record, a.dry_run)
    return dict(result, plan=summary, deployed=deploy)


def this_delivery(record, receipt):
    """Is a settled lane record this delivery's own deploy?"""
    if receipt.get("op"):
        return record.get("opId") == receipt["op"]
    return ((record.get("candidate") or {}).get("revision") == receipt.get("integration")
            and sorted(record.get("components") or []) == sorted(receipt.get("components") or []))


def lane_record(repo, entry, receipt):
    """This delivery's settled lane record: the open operation reconciled first, then by its operation ID, then (when
    the deploy's answer was lost) by time, revision and components. None means it never reached the lane."""
    op, record = receipt.get("op"), None
    if lane_status(repo).get("open"):
        code, body = sf(["mp", "reconcile", "--target-org", entry["common_target"]], cwd=repo, timeout=1800)
        if not isinstance(body, dict) or not body.get("record"):
            raise Stop(1, "the lane's open operation isn't settled yet: " + str((body or {}).get("outcome") or body),
                       outcome="open", detail=body)
        settled = body["record"]
        if settled.get("opId"):  # the whole record, as the summary sf mp prints leaves its revision out
            settled = journal_record(repo, settled["opId"]) or settled
        record = settled if this_delivery(settled, receipt) else None
    if record is None and op:
        record = journal_record(repo, op)
        if record is None:
            raise failed(f"the lane has no record of operation {op}, which this delivery sent: run sf mp status with the "
                         "captain", outcome="open", evidence=True)
    return record if record is not None else newest_journal(repo, receipt)


def resume_delivery(repo, ident, entry, team_id, recheck=False, give_back=None):
    """Finishes an interrupted delivery from its receipt and the lane's journal; never redeploys. When the lane's
    evidence settles nothing, the captain decides, after checking the org: recheck (publish only if a fresh read of
    the org matches the delivered merge) or give back (main stays as it is, and the owner gets the package back)."""
    receipt = read_receipt(repo)
    if not receipt:
        return {"outcome": "nothing to resume"}
    if receipt.get("unreadable"):
        raise unfinished(receipt)
    state = read_ledger(repo, ledger_fetch(repo, team_id))
    package = state["packages"].get(receipt["package"]) or {"id": receipt["package"]}
    owner = state["members"].get(package.get("owner")) or {}
    if receipt.get("phase") == "publishing" and not give_back:
        op = receipt.get("op")
        record = journal_record(repo, op) if op else None
        if op and record is None:
            raise failed(f"the lane has no record of operation {op}, which this delivery sent: run sf mp status with the "
                         "captain", outcome="open", evidence=True)
        return publish(repo, ident, entry, team_id, package, owner, receipt, record)
    try:
        record = lane_record(repo, entry, receipt)
    except Stop as stop:
        if not (give_back and stop.data.get("evidence")):
            raise
        record = None
    if record is not None and record.get("opId") and not receipt.get("op"):
        receipt = write_receipt(repo, op=record["opId"])  # a recovered operation keeps its identity from here on
    if give_back:
        if verified(record) and (record.get("candidate") or {}).get("revision") == receipt.get("integration"):
            raise refused("this delivery is in the org and verified: say \"resume delivery\" to publish it instead")
        back_to_main(repo)
        note = f"given back by the captain: {give_back}"[:400]
        record_delivery(repo, ident, entry, team_id, package["id"], record, "failed", note, head=receipt.get("head"),
                        allowed=("delivering", "handed-over"))
        receipt_path(repo).unlink(missing_ok=True)
        notified = pr_comment(team_id, entry, package.get("pr"), mention(owner) + "The captain stopped this delivery and "
                              f"left main as it was: {give_back}")
        return {"outcome": "given back", "package": package["id"], "op": record,
                **({"notified": False, "note": UNSENT} if notified is False else {})}
    if record is None:
        back_to_main(repo)
        if package.get("status") == "delivering":
            record_delivery(repo, ident, entry, team_id, package["id"], None, "handed-over",
                            "the interrupted delivery never reached the org", head=receipt.get("head"))
        receipt_path(repo).unlink(missing_ok=True)
        return {"outcome": "never sent", "package": package["id"]}
    if recheck and record.get("state") in SUCCESS and not record.get("checkOnly") and not verified(record):
        components = receipt.get("components") or record.get("components") or []
        if not components:  # nothing to read is nothing read back: main stays as it is
            raise decide("neither the receipt nor the lane's record names the delivered components, so a recheck has "
                         "nothing to read back and main doesn't move. Check the org, then give the package back",
                         outcome="unverified", differs=[])
        theirs = org_files(entry["common_target"], components, source_api(repo, receipt["integration"]))
        ours = files_at(repo, receipt["integration"], set(components))
        differs = sorted(c for c in components
                         if theirs[c]["state"] != "present" or not same_files(theirs[c]["files"], ours.get(c) or {}))
        if differs:
            raise decide("the common org doesn't hold the delivered merge's version of these, so main doesn't move: "
                         + ", ".join(differs) + ". Check them, or give the package back", outcome="unverified",
                         differs=differs)
        return dict(publish(repo, ident, entry, team_id, package, owner, receipt, record,
                            readback="deployed, and read back afterwards by the captain's recheck"), op=record)
    return settle_outcome(repo, ident, entry, team_id, package, owner, receipt, record, receipt.get("dry_run"))


def cmd_reconcile(a):
    """The steward's settlement by hand of the lane's open operation, then the delivery's resumption."""
    team_id, entry = pick(a.team)
    repo, ident = team_context(team_id, entry)
    if entry.get("role") != "captain":
        raise refused("only the captain's machine has the lane's journal")
    with CheckoutLock(repo, resuming=True):
        args = ["mp", "reconcile", "--target-org", entry["common_target"]]
        if a.settle:
            args += ["--settle", a.settle, "--note", a.note or "settled by the captain"]
        if a.holder_stopped:
            args.append("--holder-stopped")
        code, body = sf(args, cwd=repo, timeout=1800)
        result = {"reconcile": body}
        if read_receipt(repo):
            try:
                result["delivery"] = resume_delivery(repo, ident, entry, team_id)
            except Stop as stop:
                result["delivery"] = stop.data
        return result


def cmd_takeorg(a):
    """Back-flow: the common org's current copy of components, saved by sf mp at a stopped delivery, goes into main,
    once a fresh read shows the org still holds exactly that copy. The lane's baselines are recorded only
    after main is published, so they never name a version main doesn't hold."""
    team_id, entry = pick(a.team)
    repo, ident = team_context(team_id, entry)
    if entry.get("role") != "captain":
        raise refused("only the captain takes the common org's copy into main")
    with CheckoutLock(repo):
        try:
            conflict = json.loads((cache_dir(team_id) / "last-conflict.json").read_text())
        except (OSError, ValueError):
            raise refused("there's no stopped delivery whose org copy to take; deliver again to see the org's copy")
        if conflict.get("taken_at"):
            raise refused(f"the org's copy from {conflict.get('package')}'s stopped delivery went into main at "
                          f"{conflict['taken_at']}; deliver again to see the org's copy now")
        items = {item["component"]: item for item in conflict.get("components") or []}
        wanted = sorted(set(components_of(a.component)) or set(items))
        if not wanted or set(wanted) - set(items):
            raise refused("the stopped delivery saved no org copy of " + (", ".join(sorted(set(wanted) - set(items))) or "anything"))
        require_clean(repo)
        git(repo, "fetch", "--quiet", "origin", timeout=120)
        back_to_main(repo)
        start = out(repo, "rev-parse", "HEAD")
        if start != out(repo, "rev-parse", "refs/remotes/origin/main"):
            raise refused("the lane checkout isn't on origin's main; look at it first", checkout=str(repo))
        snapshot = {}
        for component in wanted:
            saved, files = Path(items[component].get("saved") or ""), items[component].get("files") or []
            if not saved.is_dir() or not files:
                raise refused(f"there's no saved org copy for {component}; deliver again to save one")
            anchor = next((f for f in files if f.endswith("-meta.xml")), files[0]).rsplit("/", 1)[0]
            snapshot[component] = {f"{anchor}/{p.relative_to(saved / 'files').as_posix()}": p.read_bytes()
                                   for p in sorted((saved / "files").rglob("*")) if p.is_file()}
        # A plain read: sf mp retrieve would record baselines for a copy that main may never get.
        fresh = org_files(entry["common_target"], wanted, source_api(repo, "HEAD"))
        moved = sorted(c for c in wanted if fresh[c]["state"] != "present" or not same_files(fresh[c]["files"], snapshot[c]))
        if moved:
            raise decide("the common org changed again since the stopped delivery saved its copy of these, so that copy "
                         "isn't current: deliver again to see the org's copy now", outcome="org-changed-again",
                         components=moved)
        require_clean(repo)  # just before writing: an editor may have saved while the org was read
        current = files_at(repo, "HEAD", set(wanted))
        written = [path for component in wanted for path in snapshot[component]]
        removed = sorted(p for c in wanted for p in current.get(c, {}) if p not in snapshot[c])
        for component in wanted:
            for path, data in snapshot[component].items():
                (repo / path).parent.mkdir(parents=True, exist_ok=True)
                (repo / path).write_bytes(data)
        if removed:
            git(repo, "rm", "--quiet", "--", *removed)
        git(repo, "add", "--", *written)
        if out(repo, "diff", "--cached", "--name-only"):  # nothing staged: main already has it (a repeated step)
            label = ((read_ledger(repo).get("team") or {}).get("common_org") or {}).get("label", "the common org")
            git(repo, "commit", "--quiet", "-m", f"Back-flow: {label}'s current {', '.join(wanted)}, changed outside the lane")
            push = git(repo, "push", "--quiet", "origin", "main", check=False, timeout=120)
            if push.returncode:
                git(repo, "reset", "--quiet", "--keep", start, check=False)
                raise failed("main couldn't be pushed, so nothing changed: say \"take the org's copy\" again",
                             detail=push.stderr.strip()[-200:])
            git(repo, "fetch", "--quiet", "origin", timeout=120)
        write_json_atomic(cache_dir(team_id) / "last-conflict.json", dict(conflict, taken_at=now()))
        steward = any(c.split(":", 1)[0] not in LANE_TYPES for c in wanted)
        code, baselines = sf(["mp", "retrieve", *[x for c in wanted for x in ("--metadata", c)],
                              "--target-org", entry["common_target"]] + (["--steward"] if steward else []), cwd=repo,
                             timeout=1800)
    result = {"main": out(repo, "rev-parse", "HEAD"), "files": written, "removed": removed, "baselines": baselines,
              "package": conflict.get("package")}
    if conflict.get("package"):
        package_id = conflict["package"]
        record_delivery(repo, ident, entry, team_id, package_id, None, "returned",
                        f"the common org's copy of {', '.join(wanted)} is now in main: bring main in and hand over again",
                        allowed=("handed-over", "failed", "returned"))
        state = read_ledger(repo)
        package = state["packages"].get(package_id) or {}
        owner = state["members"].get(package.get("owner")) or {}
        notified = pr_comment(team_id, entry, package.get("pr"), mention(owner) +
                              f"The common org's copy of {', '.join(wanted)} was changed outside the lane, and the captain "
                              f"kept that change: it's now in `main`. Merge `main` into this branch, check it in your own "
                              f"org, and push again (with Scout: \"fix {package_id}\").")
        if notified is False:
            result.update(notified=False, note=UNSENT)
    return result


def cmd_refresh(a):
    """The owner brings main into a hand-over branch. Their org must then get the merged copy (package sync)."""
    team_id, entry = pick(a.team)
    repo, ident = team_context(team_id, entry)
    state = read_ledger(repo, ledger_fetch(repo, team_id))
    package = state["packages"].get(a.id) or {}
    if package.get("owner") != entry["me"]:
        raise refused(f"{a.id} isn't one of your packages")
    branch = package.get("branch") or f"wp/{a.id}"
    with CheckoutLock(repo):
        if a.resume:
            if out(repo, "rev-parse", "--abbrev-ref", "HEAD") != branch:
                raise refused(f"the team checkout isn't on {branch}, so there's no merge of main to finish there")
            conflicted = out(repo, "diff", "--name-only", "--diff-filter=U").splitlines()
            marked = [p for p in conflicted if CONFLICT_MARKER.search((repo / p).read_bytes())]
            if marked:
                raise refused("these files still have conflict markers to resolve: " + ", ".join(marked), files=marked)
            if conflicted:
                git(repo, "add", "--", *conflicted)
            git(repo, "commit", "--quiet", "--no-edit")
        else:
            require_clean(repo)
            git(repo, "fetch", "--quiet", "origin", timeout=120)
            require_clean(repo)
            git(repo, "checkout", "--quiet", "-B", branch, remote_branch(repo, branch) or "refs/remotes/origin/main")
            merge = git(repo, "merge", "--no-edit", "refs/remotes/origin/main", check=False)
            if merge.returncode:
                conflicted = out(repo, "diff", "--name-only", "--diff-filter=U").splitlines()
                raise decide("main conflicts with the hand-over branch in these files; resolve them with the SE, then run "
                             "refresh --continue", outcome="conflicts", files=conflicted, checkout=str(repo), branch=branch)
        push = git(repo, "push", "--quiet", "origin", f"{branch}:refs/heads/{branch}", check=False, timeout=120)
        head = out(repo, "rev-parse", "HEAD")
        back_to_main(repo)
    if push.returncode:
        raise failed("couldn't push the hand-over branch", detail=push.stderr.strip()[-200:])
    return {"package": a.id, "branch": branch, "head": head,
            "next": "bring the merged copy into your org (package sync), check it, then hand the package over again"}


def cmd_adopt(a):
    """The captain registers a hand-over from a teammate without Scout: a pushed branch, or a pull request."""
    team_id, entry = pick(a.team)
    repo, ident = team_context(team_id, entry)
    if entry.get("role") != "captain":
        raise refused("only the captain adopts hand-overs")
    title, branch, author, body, pr = a.title, a.branch, a.owner_github, "", None
    repository = github_repo(entry.get("remote"))
    if a.pr:
        if not repository:
            raise refused("pull requests need a GitHub remote; name the branch instead")
        code, stdout, stderr = gh(["pr", "view", str(a.pr), "--repo", repository, "--json", "headRefName,headRefOid,title,body,author,url"])
        if code:
            raise failed("couldn't read the pull request", detail=stderr[-200:])
        view = json.loads(stdout)
        branch, title, body = view["headRefName"], title or view["title"], view.get("body") or ""
        author, pr = author or (view.get("author") or {}).get("login"), view.get("url")
    if not branch:
        raise refused("name the hand-over branch or the pull request")
    git(repo, "fetch", "--quiet", "origin", timeout=120)
    head = remote_branch(repo, branch)
    if not head:
        raise refused(f"origin has no branch {branch}")
    components = components_of(a.component) or components_of(components_in(body))
    if not components:
        raise refused("the hand-over names no components (Type:Name); ask its author to list them, or name them here")
    stray = scope_problems(repo, {"head": head, "components": components}, "refs/remotes/origin/main")
    if stray:
        raise refused(f"the branch also changes files outside the components it names: {', '.join(stray[:8])}",
                      outcome="scope", files=stray)
    empty = empty_components(repo, head, components)
    if empty:
        raise refused(f"the branch carries no source for {', '.join(empty)}; ask its author, or name only what it changes",
                      outcome="scope", components=empty)
    # The owner: named explicitly, else the head commit's Git identity (the person who did the work), and only then
    # the pull request's login, which a shared or bot account may not identify.
    commit_name = out(repo, "log", "-1", "--format=%an", head)
    commit_email = out(repo, "log", "-1", "--format=%ae", head)
    owner_name = a.owner_name or commit_name or author or "a teammate"
    base = out(repo, "merge-base", "refs/remotes/origin/main", head)
    holder = {}

    def change(state):
        # A hand-over sent back (returned or failed) and pushed again is the same package, handed over anew.
        for package in by_number(state["packages"].values()):
            if package.get("status") not in OPEN or not (package.get("branch") == branch or (pr and package.get("pr") == pr)):
                continue
            if package.get("status") in ("building", "delivering"):
                raise refused(f"{branch} is {package['id']}'s branch, and {package['id']} is {package['status']}: "
                              + ("its owner hands it over with Scout" if package["status"] == "building" else "let that finish"),
                              package=package["id"])
            holder.update(id=package["id"], reused=True, owner=name_of(state, package.get("owner")))
            if (package.get("status"), package.get("head"), sorted(package.get("components") or [])) == ("handed-over", head, components):
                return None
            if package.get("head") and package["head"] != head and not is_ancestor(repo, package["head"], head):
                raise refused(f"{package['id']} already holds {package['head'][:12]}, which {head[:12]} doesn't build on: "
                              "either this copy of the branch is older (fetch and adopt again), or its history was "
                              "rewritten (ask its author to push a merge instead of a force-push)", package=package["id"],
                              head=package["head"])
            item = dict(package, status="handed-over", head=head, components=components, pr=pr or package.get("pr"),
                        base={"commit": base, "checked": {}}, note=None, updated_at=now())
            item["history"] = package.get("history", []) + [{"status": "handed-over", "at": now(), "by": entry["me"],
                                                              "head": head, "adopted": True}]
            return ({f"packages/{package['id']}.json": item},
                    f"{ident['name']} took {holder['owner']}'s new hand-over of {branch} in as {package['id']}: "
                    f"{', '.join(components)}", "adopt", package["id"])
        members = list(state["members"].values())
        pick_by = lambda key, value: next((m for m in members if value and (m.get(key) or "").lower() == value.lower()), None)
        member = pick_by("github", a.owner_github) or (pick_by("name", a.owner_name) if a.owner_name else None)
        if not member and not a.owner_name:
            member = pick_by("git_email", commit_email) or (None if commit_email else pick_by("github", author))
        updates = {}
        if not member:
            member_id, suffix = slug(owner_name, "guest"), 2
            while member_id in state["members"]:
                member_id, suffix = f"{slug(owner_name, 'guest')}-{suffix}", suffix + 1
            member = {"schema": 1, "id": member_id, "name": owner_name, "github": a.owner_github, "role": "builder",
                      "scout": False, "joined_at": now(), "build_org": None, "git_email": commit_email or None}
            updates[f"members/{member_id}.json"] = member
        number = max([int(p.split("-")[1]) for p in state["packages"]] + [0]) + 1
        holder.update(id=f"WP-{number}", owner=member["name"])
        package_id = holder["id"]
        updates[f"packages/{package_id}.json"] = {
            "schema": 1, "id": package_id, "title": title or branch, "owner": member["id"], "status": "handed-over",
            "components": components, "branch": branch, "head": head, "pr": pr, "criteria": [], "task": None, "note": None,
            "base": {"commit": base, "checked": {}}, "created_at": now(), "updated_at": now(),
            "history": [{"status": "handed-over", "at": now(), "by": entry["me"], "head": head, "adopted": True}]}
        return (updates, f"{ident['name']} took {member['name']}'s hand-over {branch} in as {package_id}: "
                         f"{', '.join(components)}", "adopt", package_id)

    written = ledger_write(repo, ident, change, team_id)
    advance_if_only_mine(repo, team_id, ident, written)
    return {"package": holder["id"], "branch": branch, "head": head, "components": components, "owner": holder["owner"],
            "pr": pr, **({"reused": True} if holder.get("reused") else {})}


# ---- status, updates, the watcher, prep ----

def cmd_status(a):
    team_id, entry = pick(a.team)
    repo = Path(entry["checkout"])
    try:
        tip, fresh = ledger_fetch(repo, team_id), True
    except Stop as stop:
        tip, fresh = ledger_tip(repo), stop.data["reason"]
    state = read_ledger(repo, tip)
    result = {"team": team_id, "name": entry.get("name"), "me": entry.get("me"), "role": entry.get("role"), "fresh": fresh,
              "captain": name_of(state, (state["team"] or {}).get("captain")),
              "common_org": ((state["team"] or {}).get("common_org") or {}).get("label"),
              "members": [{"name": m.get("name"), "role": m.get("role"), "scout": m.get("scout", True),
                           "builds_in": (m.get("build_org") or {}).get("label")} for m in state["members"].values()],
              "packages": [{k: p.get(k) for k in ("id", "title", "status", "components", "pr", "branch", "note", "accepted")}
                           | {"owner": name_of(state, p.get("owner"))} for p in by_number(state["packages"].values())],
              "deliveries": sorted(({k: d.get(k) for k in ("package", "state", "check_only", "components", "at", "steward",
                                                           "verified")} for d in state["deliveries"].values()),
                                   key=lambda d: d.get("at") or "", reverse=True)[:5],
              "next": next_hints(state, entry.get("me"), entry.get("role")), "problems": state["problems"]}
    if entry.get("role") == "captain":
        result["unfinished_delivery"] = read_receipt(repo)
        if a.lane:
            result["lane"] = lane_status(repo)
    if fresh is True and resend_comments(team_id):
        result["unsent_comments"] = [{"pr": c["pr"], "at": c.get("at")} for c in unsent(team_id)]
    if tip:
        advance(repo, team_id, "reported", tip)
        advance(repo, team_id, "watched", tip)
    return result


def watcher_alive(team_id):
    try:
        info = json.loads((cache_dir(team_id) / "watcher.json").read_text())
        os.kill(int(info["pid"]), 0)
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def in_scope(cwd, entry):
    if not cwd:
        return False
    here = Path(cwd).resolve()
    for root in (workspace(), Path(entry["checkout"])):
        try:
            here.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def spawn_fetch(team_id):
    """A detached fetch: its own process group, every inherited stream released, nothing waited for."""
    subprocess.run(["/bin/sh", "-c", '"$0" "$@" </dev/null >/dev/null 2>&1 &', sys.executable, "-B",
                    str(Path(__file__).resolve()), "fetch", "--team", team_id], stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, timeout=10)


def cmd_fetch(a):
    team_id, entry = pick(a.team)
    ledger_fetch(Path(entry["checkout"]), team_id, timeout=20)
    return {"fetched": True}


def cmd_ack(a):
    """Scout relayed a watcher's report: the hook needn't show those events again."""
    team_id, entry = pick(a.team)
    repo = Path(entry["checkout"])
    advance(repo, team_id, "reported", a.upto)
    return {"reported": cache_state(team_id).get("reported")}


def cmd_updates(a):
    """What teammates did since this machine last showed it. --hook: the UserPromptSubmit form, local reads only,
    within one budget across all teams for its text and its first-prompt fetches."""
    payload = {}
    if a.hook and not sys.stdin.isatty():
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except ValueError:
            payload = {}
    try:
        teams = load_registry()["teams"]
    except Stop:
        return None if a.hook else {"teams": [], "problem": "the teams file is unreadable"}
    texts, reports = [], []
    budget, fetch_until = HOOK_CHARS, time.monotonic() + HOOK_FETCH_SECONDS
    for team_id, entry in teams.items():
        if a.team and a.team not in (team_id, entry.get("slug"), entry.get("name")):
            continue
        if entry.get("mode") == "lifecycle":  # scout_lc.py reports these teams
            continue
        if a.hook and not in_scope(payload.get("cwd") or os.getcwd(), entry):
            continue
        repo = Path(entry["checkout"])
        if not (repo / ".git").exists():
            continue
        cached = cache_state(team_id)
        session = payload.get("session_id")
        first = bool(a.hook and session and session != cached.get("session"))
        try:
            if not a.hook:
                ledger_fetch(repo, team_id)
            elif first:  # a session starts with fresh news: one short, bounded fetch, then local reads only
                left = fetch_until - time.monotonic()
                if left >= 0.5:
                    try:
                        ledger_fetch(repo, team_id, timeout=min(3.0, left))
                    except Stop:
                        pass
            elif time.time() - float(cached.get("fetched_at") or 0) > FETCH_EVERY:
                spawn_fetch(team_id)
            tip = ledger_tip(repo)
            me_email = out(repo, "config", "user.email", check=False)
            events = ledger_events(repo, cached.get("reported"), tip, me_email)
            state = read_ledger(repo, tip)
        except Stop:
            continue
        extra = []
        if first:
            extra += board_lines(entry, state)
            if not watcher_alive(team_id):
                extra.append("No watcher is running for this team in the background.")
            if state["problems"]:
                extra.append("The ledger has unreadable files: " + ", ".join(state["problems"][:4]) + ".")
        age = time.time() - float(cached.get("fetched_at") or 0)

        def compose(shown):
            lines = [update_block(entry, state, shown)] if shown else []
            if len(events) > len(shown):
                lines.append(f"({len(events) - len(shown)} more updates follow at the next prompt.)")
            lines += extra
            if lines and a.hook and age > 600 and cached.get("fetched_at"):
                lines.append(f"(This copy of the team ledger is {int(age // 60)} minutes old.)")
            return (f"From the {entry.get('name')} team ledger, new since this machine last showed it. Scout shows "
                    "teammates' updates to the SE before its answer:\n" + "\n".join(lines)) if lines else ""

        shown = events[:REPORT_LIMIT]
        text = compose(shown)
        while a.hook and shown and len(text) > budget:  # whole events only, and the cursors move past those alone
            shown = shown[:-1]
            text = compose(shown)
        if a.hook and len(text) > budget:  # not even the board fits now: this team waits for the next prompt
            text, shown = "", []
        if text:
            texts.append(text)
            budget -= len(text) + 2
        reports.append({"team": team_id, "name": entry.get("name"), "events": shown, "more": len(events) - len(shown),
                        "block": update_block(entry, state, shown) if shown else None,
                        "next": next_hints(state, entry.get("me"), entry.get("role"))})
        if shown:
            advance(repo, team_id, "reported", shown[-1]["commit"])
            advance(repo, team_id, "watched", shown[-1]["commit"])
        if first and text:
            save_cache(team_id, session=session)
    if a.hook:
        if texts:
            print("\n\n".join(texts))
        return None
    return {"teams": reports}


def cmd_watch(a):
    """Blocks until a teammate writes to the ledger, prints the update and exits (so a background run wakes Scout)."""
    team_id, entry = pick(a.team)
    if os.environ.get("SCOUT_TEAM_WATCH_OFF"):  # a headless session would wait for it; trials show it interactively
        print("The team watcher is off in this session (SCOUT_TEAM_WATCH_OFF); updates arrive at each prompt instead.")
        return None
    repo = Path(entry["checkout"])
    marker = cache_dir(team_id) / "watcher.json"
    write_json_atomic(marker, {"pid": os.getpid(), "started_at": now()})
    me_email = out(repo, "config", "user.email", check=False)
    deadline = time.time() + a.max_hours * 3600
    try:
        while time.time() < deadline:
            remote = git(repo, "ls-remote", "origin", LEDGER_REF, check=False, timeout=30)
            remote_tip = remote.stdout.split()[0] if remote.returncode == 0 and remote.stdout.strip() else None
            if remote_tip and remote_tip != ledger_tip(repo):
                try:
                    ledger_fetch(repo, team_id)
                except Stop:
                    pass
            tip = ledger_tip(repo)
            cached = cache_state(team_id)
            since = cached.get("watched") or cached.get("reported")
            if cached.get("reported") and since and not is_ancestor(repo, cached["reported"], since):
                since = cached.get("reported")
            events = ledger_events(repo, since, tip, me_email)[:REPORT_LIMIT]
            if events:
                state = read_ledger(repo, tip)
                advance(repo, team_id, "watched", events[-1]["commit"])
                print(f"From the {entry.get('name')} team ledger (the background watcher):\n"
                      + update_block(entry, state, events)
                      + f"\nAfter relaying this to the SE, Scout runs `scout_team.py ack --team {team_id} --upto "
                        f"{events[-1]['commit']}` and starts one new watcher.")
                return None
            time.sleep(a.interval)
        print(f"The {entry.get('name')} team watcher ended after {a.max_hours} hours without news; it isn't restarted.")
        return None
    finally:
        try:
            if json.loads(marker.read_text()).get("pid") == os.getpid():
                marker.unlink()
        except (OSError, ValueError):
            pass


def cmd_obligations(a):
    """For /scout prep on the common org: delivered packages' criteria, plus anything still open."""
    team_id, entry = pick(a.team)
    repo = Path(entry["checkout"])
    try:
        tip, fresh = ledger_fetch(repo, team_id), True
    except Stop:
        tip, fresh = ledger_tip(repo), False
    state = read_ledger(repo, tip)
    obligations = []

    def add(key, kind, text, readback="", result=None, owner=None):
        obligations.append({"key": key, "kind": kind, "beat": "-", "required": True, "proof_moment": False, "text": text,
                            "readback": readback, "valid_until": None, "superseded_by": None, "supersession_source": None,
                            "result": result, "owner": owner})

    for package in by_number(state["packages"].values()):
        owner = name_of(state, package.get("owner"))
        status = package.get("status")
        if status in ("delivering", "returned", "failed") or (status == "handed-over" and package.get("head")):
            add(f"ledger:{package['id']}#status", "job", f"{package['id']} \"{package.get('title')}\" is {status}"
                + (f": {package.get('note')}" if package.get("note") else ""),
                result={"status": "open", "observed": status}, owner=owner)
        if status != "delivered":
            continue
        for number, criterion in enumerate(package.get("criteria") or [], 1):
            if criterion.get("text"):
                add(f"ledger:{package['id']}#{criterion.get('item') or 'C' + str(number)}", "claim", criterion["text"],
                    criterion.get("readback") or "", owner=owner)
    for path in state["problems"]:
        add(f"ledger:{path}", "checkpoint", f"the team ledger's {path} is unreadable", result={"status": "unknown"})
    receipt = read_receipt(repo) if entry.get("role") == "captain" else None
    if receipt and receipt.get("unreadable"):
        add("ledger:delivery-receipt", "job", "the lane checkout's delivery receipt is unreadable, so a delivery may be "
            "unfinished", result={"status": "unknown"})
    elif receipt:
        add(f"ledger:{receipt.get('package')}#delivery", "job", f"{receipt.get('package')}'s delivery isn't finished "
            f"({receipt.get('phase')})", result={"status": "open"})
    return {"team": team_id, "source": f"the {entry.get('name')} team ledger", "fresh": fresh, "obligations": obligations}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("context")
    p.add_argument("--org-id")
    p.add_argument("--cwd")
    p = commands.add_parser("guard")
    p.add_argument("--yes", action="store_true", help="the SE said yes to installing the unsigned plugin")
    p = commands.add_parser("repo-create")
    p.add_argument("--name", required=True)
    p.add_argument("--owner")
    p = commands.add_parser("invite")
    p.add_argument("--github", required=True)
    p.add_argument("--team")
    p = commands.add_parser("start")
    for flag in ("--name", "--remote", "--common-org"):
        p.add_argument(flag, required=True)
    for flag in ("--build-org", "--build-label", "--github", "--checkout"):
        p.add_argument(flag)
    p.add_argument("--yes-guard", action="store_true")
    p = commands.add_parser("join")
    for flag in ("--remote", "--build-org"):
        p.add_argument(flag, required=True)
    for flag in ("--build-label", "--github", "--checkout"):
        p.add_argument(flag)
    p.add_argument("--accept-invite", action="store_true")
    p.add_argument("--yes-guard", action="store_true")
    p.add_argument("--no-guard", action="store_true", help="the SE said no to the guard, which this lane needs")
    p = commands.add_parser("package")
    p.add_argument("action", choices=("start", "update", "stop", "sync", "accept"))
    for flag in ("--team", "--id", "--title", "--task", "--note"):
        p.add_argument(flag)
    p.add_argument("--result", choices=("passed", "failed"))
    p.add_argument("--component", action="append", default=[])
    p.add_argument("--remove", action="append", default=[])
    p = commands.add_parser("handover")
    p.add_argument("--id", required=True)
    for flag in ("--team", "--task"):
        p.add_argument(flag)
    p.add_argument("--component", action="append", default=[])
    p.add_argument("--overwrite", action="append", default=[])
    p.add_argument("--no-pr", action="store_true")
    p = commands.add_parser("deliver")
    p.add_argument("--id")
    p.add_argument("--team")
    for flag in ("--plan", "--dry-run", "--steward", "--accept-overwrite", "--resume", "--recheck", "--give-back"):
        p.add_argument(flag, action="store_true")
    p.add_argument("--note")
    p.add_argument("--accept-org-change", action="append", default=[])
    p.add_argument("--approved-by", action="append", default=[], help="a component owner's name, after their explicit yes")
    p = commands.add_parser("reconcile")
    p.add_argument("--team")
    p.add_argument("--settle", choices=("success", "failed"))
    p.add_argument("--note")
    p.add_argument("--holder-stopped", action="store_true")
    p = commands.add_parser("takeorg")
    p.add_argument("--team")
    p.add_argument("--component", action="append", default=[])
    p = commands.add_parser("refresh")
    p.add_argument("--id", required=True)
    p.add_argument("--team")
    p.add_argument("--continue", dest="resume", action="store_true")
    p = commands.add_parser("adopt")
    for flag in ("--team", "--branch", "--pr", "--title", "--owner-name", "--owner-github"):
        p.add_argument(flag)
    p.add_argument("--component", action="append", default=[])
    p = commands.add_parser("status")
    p.add_argument("--team")
    p.add_argument("--lane", action="store_true")
    p = commands.add_parser("updates")
    p.add_argument("--team")
    p.add_argument("--hook", action="store_true")
    p = commands.add_parser("ack")
    p.add_argument("--team")
    p.add_argument("--upto", required=True)
    p = commands.add_parser("watch")
    p.add_argument("--team")
    p.add_argument("--interval", type=float, default=60.0)
    p.add_argument("--max-hours", type=float, default=12.0)
    p = commands.add_parser("fetch")
    p.add_argument("--team")
    p = commands.add_parser("obligations")
    p.add_argument("--team")
    args = parser.parse_args(argv)
    if args.command == "deliver" and not args.resume and not args.id:
        parser.error("deliver needs --id (or --resume)")
    if args.command == "package" and args.action != "start" and not args.id:
        parser.error(f"package {args.action} needs --id")
    if args.command == "package" and args.action == "start" and not (args.title or "").strip():
        parser.error("package start needs --title: a retry finds its package by owner, title and components")
    handler = globals()["cmd_" + args.command.replace("-", "_")]
    try:
        if os.name == "nt":  # team mode on Windows comes later; there os.kill(pid, 0) would end the process it checks
            raise refused("building one demo org together runs on macOS for now; on Windows it comes in a later release")
        result = handler(args)
    except Stop as stop:
        if args.command == "updates" and args.hook:
            return 0
        print(json.dumps(stop.data, indent=1, sort_keys=True, default=str))
        return stop.code
    if result is not None:
        print(json.dumps(result, indent=1, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
