#!/usr/bin/env python3
"""Scout's Lifecycle Center mode: a team on Salesforce's next-generation DevOps Center, driven by Scout.

A team is a Lifecycle Center project and pipeline whose one stage is the common org, on `main` of the team's GitHub
repository. The official dx-devops skills set the project and pipeline up; `start` and `join` make a checkout of it a
Scout team. Builders work in their own sandboxes and hand over through work items (`WI-…` branches) and reviews (pull
requests), with Salesforce's official skills or with Scout. Only the captain delivers: Scout's checks, the merge on
GitHub, a validation (which makes Lifecycle Center sync the merge), then `promotion complete`, which deploys it.

Scout adds what nothing official covers: the scope, base and effect checks on the pull request; the direct-edit check
against the copy the platform last delivered; the tests, as a check-only validation before the merge; the read-back;
and teammates' updates. A delivery resumes from what GitHub and the server show, and a merge Scout didn't check is
checked as it stands on main before anything deploys.

Commands print one JSON object (the hook prints text). Exit codes: 0 done; 2 refused, nothing changed; 3 stopped for
a decision (the JSON says which); 1 failed (the JSON says what is left).
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import fnmatch
import hashlib
import html
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

if os.name != "nt":  # Windows has no fcntl; team mode comes there later, and main() refuses before any step
    import fcntl

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scout_team as team  # noqa: E402  the lane's helpers: processes, registry, cache, components, normalization
import scout_portable  # noqa: E402  (ships beside this helper)

Stop, refused, failed, decide = team.Stop, team.refused, team.failed, team.decide
git, out, sf, gh, now = team.git, team.out, team.sf, team.gh, team.now

MODE = "lifecycle"
ON_WINDOWS = "building one demo org together runs on macOS for now; on Windows it comes in a later release"
ROOT = Path(__file__).resolve().parents[1]
EFFECTS = ROOT / "packages" / "sf-mp" / "scripts" / "effects.mjs"
LC_PROMPT = ROOT / "prompts" / "scout" / "team-lifecycle.md"
CHECKSUM = "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"
SFID = re.compile(r"[0-9A-Za-z]{15}(?:[0-9A-Za-z]{3})?")
WI_NAME = re.compile(r"^WI-\d{6}$")
CHECKED = re.compile(r"(?im)^[ \t]*checked:[ \t]*`?([0-9a-f]{7,40})\b")  # the builder's checked base on a work item
CHECKED_LINE = re.compile(r"(?im)^[ \t]*checked:.*(?:\n|$)")
SYNC_TRIES, SYNC_WAIT = 10, 15                   # the first validation after a merge can miss the sync
STATUS_WAIT, STATUS_DEADLINE = 5, 1800           # a promotion that runs longer is reported, never resubmitted
RUNNING = ("NEW", "IN_PROGRESS", "FINALIZING")   # a stage promotion before it ends (the measured picklist)
TERMINAL = {"SUCCESS", "ERROR", "CANCELLED", "INTERRUPTED"}
HISTORY = 30                                     # how far back a component's history is searched for its delivered copy
FETCH_EVERY = 90                                 # the prompt hook's cache of hub and GitHub events
REPORT_LIMIT = 12
PAGES, PER_PAGE = 5, 100                         # GitHub comments per refresh; the rest wait for the next one
CLEAN = {"same", "new", "new-to-main"}           # a sandbox copy that can't be older than main's
EMPTY_SET = re.compile(r"resolved component set was empty|No components to deploy", re.I)  # a measured platform fault
FULL_CEILING = 300                               # a full promotion checks every component on main against the org
MERGED_LIMIT = 200                               # merged pull requests read at once; older ones are looked up by name
TEST_WAIT = 20                                   # minutes the owed tests' run may take before Scout says it's still going
KEPT_OUT = [p for p in team.FORCEIGNORE.splitlines() if p]  # what the .forceignore Scout writes keeps out of a deploy
RULES_START, RULES_END = "<!-- scout:team-rules -->", "<!-- /scout:team-rules -->"
AGENTS_MD = """# How this team works

This repository is a Salesforce DX project on Salesforce's Lifecycle Center (next-generation DevOps Center). The
pipeline's one stage is the team's common org, on `main`. Every change reaches that org through a work item and a
review, and only the captain promotes. These rules are for every builder and every AI agent working here (Cursor,
Agentforce Vibes, Claude Code, Scout).

1. **Build in your own sandbox.** Never deploy, validate or delete in the common org, by any route.
2. **Start from `main`'s copy.** Before you edit a component, run `git fetch` and compare your sandbox's copy with
   `origin/main`'s. If they differ and the difference isn't yours, deploy `main`'s copy into your sandbox first, so
   you never hand back an old copy. Then add a line `Checked: <commit>` to the work item's description, naming the
   `origin/main` commit you compared with (keep its other lines). After you merge `main` into your branch, deploy
   the branch's copy into your sandbox and change the line to the `main` commit you merged.
3. **One work item per change.** Its description names the components it changes on a line `Components: Type:Name, …`.
   Commit only those components' files, on the work item's `WI-…` branch. Commit a new component's files together
   (a class with its `-meta.xml`): Lifecycle Center can't promote a new component whose files came in separate commits.
4. **Open the review as soon as you've pushed** (`sf devops review create`). Don't wait for Lifecycle Center to record
   the commit: the captain's promotion syncs it.
5. **Name every org with `--target-org`.** Never change the CLI's default org, aliases or logins.
6. **Never commit your AI tool's own files** (`.agents/`, `.claude/`, `.cursor/`): they're in `.gitignore`.
7. **When an official deploy skill fails,** deploy to your own sandbox with
   `sf project deploy start --target-org <your sandbox>`, never to the common org.
8. **A new custom object ships with its tab** and a permission set that makes the tab visible; without them it stays
   out of the App Launcher.
9. **Tests that insert records of a new record type** create their own user and grant the record type through a
   permission set, outside `System.runAs`; they insert those records as that user, inside it. From API 67.0, a
   test that inserts them on the deploying admin's own access fails with `INVALID_CROSS_REFERENCE_KEY`, "this ID
   value isn't valid for the user": grant the record type first, to the test's user or to the admin.
"""
GITIGNORE_LINES = [".agents/", ".claude/", ".cursor/", ".sf/", ".sfdx/", ".scout/"]
ATTRIBUTES_LINE = "* text=auto eol=lf"  # Git stores LF, so a Windows checkout's line endings never widen a delivery
RULES_BRANCH = "scout/team-rules"       # where the rules wait for review when main is protected
MEMBERS_BRANCH = "scout/members"        # one record per member who joined with Scout: who, and whether their guard is on
LC_GUARD = (team.GUARD_WHAT + " It's optional here: Lifecycle Center mode works without it, the captain's checks stay "
            "the same, and the captain's status shows whose guard is off.")


# ---- IDs: the platform answers both lengths, and promotion complete crashes on the long one ----

def id15(value):
    value = str(value or "")
    if not SFID.fullmatch(value):
        raise refused(f"{value or 'an empty ID'} isn't a Salesforce record ID")
    return value[:15]


def id18(value):
    base = id15(value)
    return base + "".join(CHECKSUM[sum(1 << i for i, c in enumerate(base[k:k + 5]) if c.isupper())] for k in (0, 5, 10))


def quoted(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


# ---- the DevOps Center CLI: every answer's body is read, since some failures come back with status 0 ----

KINDS = [  # (kind, pattern in the answer's message), in the order they're tested
    ("external-merges", re.compile(r"EXTERNAL_MERGES_DETECTED")),
    ("already-merged", re.compile(r"ALREADY_MERGED")),
    ("merge-conflict", re.compile(r"MERGE_CONFLICT")),
    ("in-progress", re.compile(r"PROMOTION_IN_PROGRESS")),
    ("no-review", re.compile(r"PR_DOES_NOT_EXIST|PR_NOT_MERGED|BRANCH_NOT_FOUND")),
    ("long-id", re.compile(r"too long for type character varying\(15\)")),
    ("not-found", re.compile(r"The requested resource does not exist|NOT_FOUND")),
]


def message_of(body):
    if not isinstance(body, dict):
        return ""
    return html.unescape(str(body.get("message") or body.get("errorDetails") or ""))


def kind_of(code, body):
    """What an `sf devops` answer means: ok, or the first known kind its message names, or other."""
    text = message_of(body)
    for kind, pattern in KINDS:
        if pattern.search(text):
            return kind
    if code == 0 and isinstance(body, dict) and str(body.get("success", True)).lower() != "false":
        return "ok"
    return "other"


def progress(name, step, text, safe=True):
    """One line per step on stderr, while the JSON answer waits for stdout, so a model watching a background run sees
    where the delivery is. Whether stopping is safe is code: a stop while a change is in flight is never safe."""
    note = {True: "nothing in flight: scout_lc.py stop ends it at the next safe point, and --resume picks up",
            False: "a change is in flight: never kill the helper now; a stop request waits until it lands",
            None: "the helper ends here; its answer follows"}[safe]
    print(f"scout_lc {time.strftime('%H:%M:%SZ', time.gmtime())} {name} {step}: {text} ({note})", file=sys.stderr,
          flush=True)


def devops(args, hub, cwd, timeout=600):
    """Runs `sf devops <args> --target-org <hub> --json`: (code, body, kind)."""
    code, body = sf(["devops", *args, "--target-org", hub], cwd, timeout=timeout)
    return code, body, kind_of(code, body)


def query(soql, org, cwd, timeout=120, tooling=False):
    code, body = sf(["data", "query", *(["--use-tooling-api"] if tooling else []), "--target-org", org, "--query", soql],
                    cwd, timeout=timeout)
    if code or not isinstance(body, dict):
        raise failed(f"a query on {org} failed: {message_of(body)[:300]}")
    records = body.get("records")
    if not isinstance(records, list):  # an answer without its records is a missing input, never "none"
        raise failed(f"a query on {org} answered without its records, so Scout can't tell what's there "
                     f"({soql[:120]})")
    return records


# ---- the team record and its work items ----

def pick(team_name=None):
    team_id, entry = team.pick(team_name)
    if entry.get("mode") != MODE:
        raise refused(f"{entry.get('name', team_id)} is a lane team; its steps are scout_team.py's")
    return team_id, entry


def where(entry):
    return Path(entry["checkout"])


def fetch(repo):
    git(repo, "fetch", "--quiet", "--prune", "origin", timeout=120)
    return out(repo, "rev-parse", "refs/remotes/origin/main")


def gh_json(args, cwd=None):
    code, stdout, stderr = gh(args, cwd=cwd)
    if code:
        raise failed(f"gh {' '.join(args[:2])} failed: {(stderr or stdout)[-300:]}")
    try:
        return json.loads(stdout or "null")
    except ValueError:
        raise failed(f"gh {' '.join(args[:2])} returned unreadable output")


def gh_list(args, cwd=None):
    """A GitHub list call's answer, which must be a list: an empty or other answer is a missing input, never "none"."""
    found = gh_json(args, cwd)
    if not isinstance(found, list):
        raise failed(f"gh {' '.join(args[:2])} answered without a list, so Scout can't tell what's there")
    return found


def pull_requests(entry, branch, state="all"):
    return gh_list(["pr", "list", "--repo", entry["repo"], "--head", branch, "--state", state, "--json",
                    "number,state,headRefOid,mergeCommit,mergeable,baseRefName,url,title"])


def work_item(entry, name, cwd):
    if not WI_NAME.match(str(name or "")):
        raise refused(f"{name} isn't a work item name like WI-000012")
    rows = query(f"SELECT Id, Name, Subject, Description, Status FROM WorkItem WHERE Name = {quoted(name)} "
                 f"AND DevopsProjectId = {quoted(id18(entry['project_id']))}", entry["hub"], cwd)
    if not rows:
        raise refused(f"{name} isn't a work item of this team's project")
    row = rows[0]
    return {"id": id18(row["Id"]), "name": row["Name"], "subject": row.get("Subject") or "",
            "description": row.get("Description") or "", "status": row.get("Status") or "", "branch": row["Name"]}


def update_item(entry, name, cwd, **fields):
    """`sf devops work-item update`: status ("In Progress", "Ready to Promote") or description."""
    args = ["work-item", "update", "--work-item-name", name]
    for flag, value in fields.items():
        args += [f"--{flag}", value]
    code, body, kind = devops(args, entry["hub"], cwd)
    if kind != "ok":
        raise failed(f"Lifecycle Center didn't update {name}: {message_of(body)[:300]}", work_item=name)
    return body


def declared(item):
    """The work item's own scope: its description's `Components:` line, or nothing (the captain approves the list)."""
    line = re.search(r"(?im)^\s*components:\s*(.+)$", item.get("description") or "")
    return sorted(set(team.components_in(line[1]))) if line else []


def describe_components(components):
    return "Components: " + ", ".join(f"`{c}`" for c in components)


# ---- comparison: the org's own copy, normalized only for the rewrites measured on save ----

CUSTOM_LINKS = re.compile(rb"<layoutSections>(?:(?!</layoutSections>).)*?<style>CustomLinks</style>(?:(?!</layoutSections>).)*?</layoutSections>", re.S)


def norm(data, path):
    data = team.normalized(data, path)  # Apex: the org drops trailing whitespace
    if path.endswith(".layout-meta.xml"):  # the org adds empty columns to a layout's Custom Links section
        data = CUSTOM_LINKS.sub(lambda m: re.sub(rb"\s*<layoutColumns/>", b"", m.group(0)), data)
    return data


def same(a, b):
    return set(a) == set(b) and all(norm(a[p], p) == norm(b[p], p) for p in a)


def digest(files):
    h = hashlib.sha256()
    for path in sorted(files):
        h.update(path.encode() + b"\0" + hashlib.sha256(norm(files[path], path)).digest())
    return h.hexdigest()[:16]


def diff_lines(reference, current, limit=8):
    lines = []
    for path in sorted(set(reference) | set(current)):
        a = norm(reference.get(path, b""), path).decode("utf-8", "replace").splitlines()
        b = norm(current.get(path, b""), path).decode("utf-8", "replace").splitlines()
        if a != b:
            lines += [f"{path}: + {x}" for x in b if x not in a][:limit // 2] + [f"{path}: - {x}" for x in a if x not in b][:limit // 2]
    return lines[:limit]


def compare(main_files, found):
    """A sandbox's copy against main's: same, new (neither has it), new-to-main (only the sandbox has it), missing
    (only main has it), differs, or unreadable."""
    if found["state"] == "unknown":
        return "unreadable"
    if not main_files:
        return "new" if found["state"] == "absent" else "new-to-main"
    if found["state"] != "present":
        return "missing"
    return "same" if same(main_files, found["files"]) else "differs"


# ---- what the common org should hold: the platform's record of what it delivered, and the read-back's baselines ----

def baseline_file(team_id, component):
    return team.cache_dir(team_id) / "baselines" / (team.slug(component.replace(":", "-"), "c") + "-" +
                                                     hashlib.sha256(component.encode()).hexdigest()[:8] + ".json")


def read_baseline(team_id, component):
    try:
        data = json.loads(baseline_file(team_id, component).read_text())
        return dict(data, files={p: base64.b64decode(b) for p, b in data["files"].items()})
    except (OSError, ValueError, KeyError):
        return None


def save_baseline(team_id, entry, component, merge, files):
    team.write_json_atomic(baseline_file(team_id, component), {
        "component": component, "org": entry["common_org_id"], "stage": entry["stage_id"], "merge": merge, "at": now(),
        "files": {p: base64.b64encode(b).decode() for p, b in files.items()}})


def paths_of(repo, refs, components):
    """The source paths that map to these components at any of these revisions, so a file deleted at one of them
    still counts."""
    found = set()
    for ref in refs:
        listing = out(repo, "ls-tree", "-r", "--name-only", ref, "--", team.SOURCE.rstrip("/"), check=False)
        found |= {p for p in listing.splitlines() if team.component_of(p) in components}
    return sorted(found)


def promoted_merges(entry, cwd):
    """{commit: work item} for the stage's successful promotions: the platform records the merge it delivered."""
    rows = query("SELECT MergeRemoteReference, WorkItem.Name FROM DevopsPipelnStgPromWkItem WHERE "
                 f"DevopsPipelnStgProm.PipelineStageId = {quoted(id18(entry['stage_id']))} AND "
                 "DevopsPipelnStgProm.Status = 'SUCCESS' AND MergeRemoteReference != null", entry["hub"], cwd)
    return {r["MergeRemoteReference"]: (r.get("WorkItem") or {}).get("Name") for r in rows if r.get("MergeRemoteReference")}


def reference_for(team_id, entry, repo, base, component, promoted, snapshot=None):
    """What the common org should hold for a component, with `base` main before this delivery: the read-back's copy
    after a delivery, or main's copy at the newest change a promotion delivered. Main's newer changes to it that no
    promotion delivered come back as `later`. {files (None: absent), why, commit, later}"""
    if snapshot is not None:
        return {"files": snapshot, "why": "the back-flow's captured copy", "commit": None, "later": []}
    paths = paths_of(repo, [base], {component})
    if not paths:
        return {"files": None, "why": "not in main", "commit": None, "later": []}
    # main's own history: a two-parent merge is a commit of main, which path-limited history would simplify away
    history = out(repo, "log", "--first-parent", f"-{HISTORY}", "--format=%H", base, "--", *paths).splitlines()
    held = read_baseline(team_id, component)
    if held and (held.get("org"), held.get("stage")) != (entry["common_org_id"], entry["stage_id"]):
        held = None
    later = []
    for commit in history:
        if held and held.get("merge") == commit:
            return {"files": held["files"], "why": f"the org's copy after {commit[:12]}", "commit": commit, "later": later}
        if commit in promoted:
            return {"files": team.files_at(repo, commit, {component}).get(component) or {}, "commit": commit,
                    "why": f"main's copy at {commit[:12]} ({promoted[commit] or 'a promotion'} delivered it)", "later": later}
        later.append(commit)
    return {"files": team.files_at(repo, history[0], {component}).get(component) or {}, "commit": history[0], "later": [],
            "why": f"main's copy at {history[0][:12]}; no promotion on record delivered it"}


def read_org(entry, repo, components):
    return team.org_files(entry["common_org"]["target"], sorted(components), team.source_api(repo))


def direct_edits(team_id, entry, repo, base, components, org, promoted, snapshots=None):
    """{component: {state, reference, lines, digest, later}} against one retrieve (`org`). States: same; changed (the
    org doesn't hold the delivered copy); main-ahead (it does, but main holds changes no promotion delivered); created,
    deleted, unreadable. The digest is the org copy's, so an approval binds to exactly the copy that was seen."""
    snapshots = snapshots or {}
    report = {}
    for component in sorted(components):
        ref = reference_for(team_id, entry, repo, base, component, promoted, snapshots.get(component))
        found = org[component]
        row = {"reference": ref["why"], "lines": [], "later": [c[:12] for c in ref["later"]],
               "digest": digest(found["files"]) if found["state"] == "present" else found["state"]}
        if found["state"] == "unknown":
            row.update(state="unreadable", lines=[str(found.get("problem"))])
        elif ref["files"] is None:
            row.update(state="same" if found["state"] == "absent" else "created")
        elif found["state"] == "absent":
            row.update(state="deleted")
        elif not same(ref["files"], found["files"]):
            row.update(state="changed", lines=diff_lines(ref["files"], found["files"]))
        else:
            row.update(state="main-ahead" if ref["later"] else "same")
            if ref["commit"] and not ref["why"].startswith("the org's copy"):  # a confirmed match becomes the baseline
                save_baseline(team_id, entry, component, ref["commit"], found["files"])
        report[component] = row
    return report


# ---- what a pull request changes: its scope, its base and its effects ----

def package_dirs(repo, ref):
    shown = git(repo, "show", f"{ref}:sfdx-project.json", check=False)
    try:
        dirs = [str(d.get("path", "")).strip("/") for d in json.loads(shown.stdout).get("packageDirectories") or []]
    except (ValueError, AttributeError):
        dirs = []
    return [d for d in dirs if d] or ["force-app"]


def deployable(repo, ref):
    """The paths whose changes change what a full promotion deploys."""
    return [*package_dirs(repo, ref), "sfdx-project.json", ".forceignore"]


def kept_out(path):
    """Whether the .forceignore Scout writes for every team keeps this file out of a deploy."""
    parts = path.split("/")
    for pattern in KEPT_OUT:
        bare = pattern.removeprefix("**/")
        if bare.endswith("/**"):
            if any(fnmatch.fnmatch(part, bare[:-3]) for part in parts[:-1]):
                return True
        elif fnmatch.fnmatch(parts[-1], bare):
            return True
    return False


def full_payload(repo, ref):
    """What a full promotion deploys: every file in the stage branch's package directories. Scout checks only the
    components it maps, so the rest comes back as `unchecked`, apart from what its .forceignore keeps out."""
    listing = out(repo, "ls-tree", "-r", "--name-only", ref, "--", *package_dirs(repo, ref), check=False).splitlines()
    mapped = {p: team.component_of(p) for p in listing}
    return {"components": sorted({c for c in mapped.values() if c}),
            "unchecked": [p for p, c in mapped.items() if not c and not kept_out(p)]}


def split_new(repo, base, head, components):
    """New components whose files the branch added in more than one commit. Lifecycle Center's default promotion
    resolved no components for that shape (the source file, then its meta file in a later commit; measured 19 Oct),
    so such a delivery needs the full promotion."""
    joined = out(repo, "merge-base", base, head)
    found = []
    for component in components:
        paths = paths_of(repo, [head], {component})
        if not paths or paths_of(repo, [joined], {component}):
            continue
        adders = set()
        for path in paths:
            commits = out(repo, "log", "--format=%H", "--diff-filter=A", f"{joined}..{head}", "--", path).splitlines()
            adders.update(commits[-1:])
        if len(adders) > 1:
            found.append(component)
    return found


def scope_of(repo, base, tree, item):
    """Every path the merge changes: components Scout maps, other metadata (refused) and other files (shown)."""
    paths = [p for p in out(repo, "diff", "--name-only", "--no-renames", base, tree).splitlines() if p]
    source = [p for p in paths if p.startswith(team.SOURCE)]
    dirs = sorted(set(package_dirs(repo, base)) | set(package_dirs(repo, tree)))  # a removed directory still counts
    outside = [p for p in paths if not p.startswith(team.SOURCE)]
    elsewhere = [p for p in outside if any(p == d or p.startswith(d + "/") for d in dirs)]
    changed = sorted({team.component_of(p) for p in source if team.component_of(p)})
    named = declared(item)
    return {"components": changed, "declared": named, "unrecognized": [p for p in source if not team.component_of(p)],
            "outside": sorted(set(changed) - set(named)) if named else [], "metadata_elsewhere": elsewhere,
            "other_files": [p for p in outside if p not in elsewhere]}


def base_evidence(repo, base, head, item, components):
    """The builder's checked base: the `Checked: <commit>` line names the main commit their sandbox's copy matched
    before they edited. Main's changes to the components after it, up to where the branch joins main, are what an
    older copy would undo: the branch's diff counts from the join, and git merges only what came after it."""
    match = CHECKED.search(item.get("description") or "")
    if not match:
        return {"state": "unchecked", "detail": f"{item['name']} has no Checked line"}
    checked = git(repo, "rev-parse", "--verify", "--quiet", f"{match[1]}^{{commit}}", check=False).stdout.strip()
    if not checked or not team.is_ancestor(repo, checked, base):
        return {"state": "unchecked", "detail": f"its Checked line names {match[1]}, which isn't a commit of main"}
    joined = out(repo, "merge-base", head, base)
    later = []
    for component in components:
        paths = paths_of(repo, [checked, joined, head], {component})  # a file deleted in between, then restored, too
        for row in (out(repo, "log", "--format=%H %s", f"{checked}..{joined}", "--", *paths).splitlines() if paths else []):
            commit, _, subject = row.partition(" ")
            later.append({"component": component, "commit": commit[:12], "subject": subject[:100]})
    return {"state": "stale" if later else "checked", "checked": checked[:12], "later": later}


def bundle_key(path, component):
    kind, name = component.split(":", 1)
    folder = {"LightningComponentBundle": "lwc", "AuraDefinitionBundle": "aura"}.get(kind)
    marker = f"/{folder}/{name}/" if folder else None
    return path.split(marker, 1)[1] if marker and marker in path else Path(path).name


def overlap(text, seconds=1):
    """A GitHub cursor moved back a second: its filters are strict, and what's seen twice is deduplicated."""
    moment = team.moment(text)
    return (moment - timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ") if moment else text


def soql_time(text):
    """A platform timestamp (…000+0000) or one of Scout's (…Z) as a SOQL datetime literal."""
    moment = team.moment(str(text).replace("+0000", "+00:00"))
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ") if moment else team.now()


def effect_problems(candidate, components, org):
    """sf-mp's effect checks (page assignments, flow activation, files a bundle would drop) through its bridge."""
    def files(found):
        return [{"key": bundle_key(p, component), "b64": base64.b64encode(b).decode()} for p, b in sorted(found.items())]
    items = []
    for component in components:
        theirs = org[component]["files"] if org[component]["state"] == "present" else None
        items.append({"key": component, "candidate": files(candidate.get(component) or {}),
                      "org": files(theirs) if theirs is not None else None})
    result = team.run([team.tool("node"), str(EFFECTS)], input=json.dumps(items), timeout=120)
    if result.returncode:
        raise failed("the effect checks didn't run", detail=(result.stderr or "")[-300:])
    try:
        report = json.loads(result.stdout)
    except ValueError:
        report = None
    if not isinstance(report, dict):  # an empty or unreadable answer is never "no problems"
        raise failed("the effect checks gave no answer Scout can read, so they didn't count",
                     detail=((result.stdout or "") + (result.stderr or ""))[-300:])
    return {component: problems for component, problems in report.items() if problems}


def trial_merge(repo, base, head):
    """The candidate: head merged onto base, as a tree, without touching the checkout. None on a conflict."""
    result = git(repo, "merge-tree", "--write-tree", "--name-only", base, head, check=False)
    lines = result.stdout.strip().splitlines()
    if result.returncode == 0 and lines:
        return lines[0], []
    if result.returncode == 1:
        return None, [l for l in lines[1:] if l and not l.startswith(("Auto-merging", "CONFLICT"))][:20]
    raise failed("git merge-tree failed", detail=(result.stderr or "")[-300:])


# ---- the test gate: a check-only validation of the candidate against the common org ----

def suite_classes(entry, repo, tree, cwd):
    """The Apex classes of the stage's Pre-Promote suites: each suite's file in the candidate, else the common org's
    own suite. ([classes], [suites], [suites that resolve to none]); the Default Suite runs every test in the org,
    so it never resolves."""
    rows = query("SELECT TestSuite.Name FROM DevopsTestSuiteStage WHERE "
                 f"DevopsPipelineStageTrigger.RelatedRecordId = {quoted(id18(entry['stage_id']))} "
                 "AND DevopsPipelineStageTrigger.TriggerType = 'Pre-Promote'", entry["hub"], cwd)
    names = sorted({(r.get("TestSuite") or {}).get("Name") for r in rows} - {None})
    classes, missing = set(), []
    if any(not (r.get("TestSuite") or {}).get("Name") for r in rows):  # a suite Scout can't name can't stand for none
        missing.append("a stage suite the hub returned without its name")
    for name in names:
        found = set()
        if name != "Default Suite":
            shown = git(repo, "show", f"{tree}:{team.SOURCE}testSuites/{name}.testSuite-meta.xml", check=False)
            if shown.returncode == 0:
                found = set(re.findall(r"<testClassName>\s*([^<\s]+)\s*</testClassName>", shown.stdout))
            if not found:
                found = {(r.get("ApexClass") or {}).get("Name") for r in query(
                    f"SELECT ApexClass.Name FROM TestSuiteMembership WHERE ApexTestSuite.TestSuiteName = {quoted(name)}",
                    entry["common_org"]["target"], cwd, tooling=True)} - {None}
        if found:
            classes |= found
        else:
            missing.append(name)
    return sorted(classes), names, missing


def package_tests(candidate, components):
    tests = []
    for component in components:
        if component.startswith("ApexClass:"):
            for path, data in (candidate.get(component) or {}).items():
                if path.endswith(".cls") and re.search(rb"(?i)@istest\b", data):
                    tests.append(component.split(":", 1)[1])
    return sorted(set(tests))


def validate(team_id, entry, repo, tree, candidate, components, wi_name, cwd):
    classes, suites, missing = suite_classes(entry, repo, tree, cwd)
    if missing:
        return {"validated": False, "stop": "missing-suite", "suites": suites, "missing_suites": missing,
                "detail": "the stage's Pre-Promote suites " + ", ".join(missing) + " don't resolve to test classes "
                          "(neither the candidate nor the common org has them, or it's the Default Suite, which runs "
                          "every test in the org); assign a named suite that exists (dx-devops-test-suite-assignments-"
                          "configure), then deliver again"}
    tests = sorted(set(classes) | set(package_tests(candidate, components)))
    if any(c.startswith(("ApexClass:", "ApexTrigger:")) for c in components) and not tests:
        return {"validated": False, "stop": "no-tests", "suites": suites,
                "detail": "the delivery holds Apex, but neither the stage's suites nor the package name a test class"}
    staging = team.cache_dir(team_id) / "candidate" / wi_name
    shutil.rmtree(staging, ignore_errors=True)
    for component in components:
        for path, data in (candidate.get(component) or {}).items():
            target = staging / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    (staging / "sfdx-project.json").write_text(json.dumps(dict(team.SFDX_PROJECT_TEMPLATE, sourceApiVersion=team.source_api(repo))))
    args = ["mp", "validate", "--source-dir", "force-app", "--target-org", entry["common_org"]["target"]]
    args += [x for t in tests for x in ("--tests", t)] if tests else ["--no-tests"]
    code, body = sf(args, cwd=staging, timeout=3600)
    result = body if isinstance(body, dict) else {}
    return {"validated": bool(code == 0 and result.get("validated")), "tests": tests, "suites": suites,
            "missing_suites": [], "testsRun": result.get("testsRun"), "jobId": result.get("jobId"),
            "ran_none": bool(result.get("ranNone")),
            "failures": result.get("failures") or ([message_of(body)] if code else [])}


# ---- the stage on the server ----

def pipeline_shape(hub, pipeline_id, cwd):
    """The pipeline as Lifecycle Center shows it: one active stage on main, one project, and the org the stage's
    environment deploys to."""
    code, body, kind = devops(["pipeline", "get", "--pipeline-id", id18(pipeline_id)], hub, cwd)
    if kind != "ok":
        raise refused(f"Lifecycle Center doesn't show pipeline {pipeline_id} on {hub}: {message_of(body)[:200]}")
    stages = body.get("stages") or []
    if len(stages) != 1:
        raise refused(f"the pipeline has {len(stages)} stages; Scout's Lifecycle Center mode supports one, the common org")
    projects = body.get("connectedProjects") or []
    if len(projects) != 1:
        raise refused("the pipeline needs exactly one connected project")
    if not body.get("isActive"):
        raise refused("the pipeline isn't active yet; activate it first (dx-devops-pipeline-manage)")
    stage = stages[0]
    if stage.get("branchName") != "main":  # a branch the answer doesn't name is never taken for main
        raise refused(f"the stage's branch is {stage.get('branchName') or 'not named in the answer'}; Scout's Lifecycle "
                      "Center mode supports a stage on main")
    environment = (stage.get("environment") or {}).get("id")
    rows = query(f"SELECT OrgIdentifier FROM DevopsEnvironment WHERE Id = {quoted(id18(environment))}", hub, cwd) if environment else []
    return {"pipeline_id": id15(body["id"]), "project_id": id15(projects[0]["id"]), "stage_id": id15(stage["id"]),
            "stage_branch": "main", "repo": f"{stage['repositoryOwner']}/{stage['repositoryName']}",
            "environment": (stage.get("environment") or {}).get("name"), "name": body.get("name"),
            "stage_org_id": (rows[0].get("OrgIdentifier") or "")[:15] or None if rows else None}


def check_stage(entry, cwd):
    """At each delivery: the pipeline still has the team's stage, and the stage still deploys to the team's common
    org, the one Scout checks and validates against."""
    shape = pipeline_shape(entry["hub"], entry["pipeline_id"], cwd)
    if (shape["stage_id"], shape["project_id"], shape["repo"].lower()) != (entry["stage_id"], entry["project_id"], entry["repo"].lower()):
        raise refused("the pipeline's stage, project or repository changed since the team started; start the team again")
    if shape["stage_org_id"] != entry["common_org_id"]:
        raise refused(f"the pipeline's stage now deploys to {shape['stage_org_id'] or 'no org'}, not the team's common org "
                      f"{entry['common_org_id']}, so Scout would check one org while the promotion writes another. Fix "
                      "the stage's environment, or start the team again")


def promotion_for(entry, item, cwd):
    """The work item's latest promotion on the team's stage."""
    rows = query("SELECT CreatedDate, MergeRemoteReference, DevopsPipelnStgProm.Status, DevopsPipelnStgProm.CompletionDate, "
                 "DevopsPipelnStgProm.RequestInfo.RequestToken, DevopsPipelnStgProm.RequestInfo.Status, "
                 "DevopsPipelnStgProm.RequestInfo.ErrorDetails FROM DevopsPipelnStgPromWkItem WHERE WorkItemId = "
                 f"{quoted(item['id'])} AND DevopsPipelnStgProm.PipelineStageId = {quoted(id18(entry['stage_id']))} "
                 # a refused complete leaves a record with neither a status nor a request (measured); a submitted
                 # promotion is never skipped, whatever its status says yet
                 "AND (DevopsPipelnStgProm.Status != null OR DevopsPipelnStgProm.RequestInfoId != null) "
                 "ORDER BY CreatedDate DESC LIMIT 1", entry["hub"], cwd)
    if not rows:
        return None
    prom = rows[0].get("DevopsPipelnStgProm") or {}
    info = prom.get("RequestInfo") or {}
    return {"token": info.get("RequestToken"), "status": (info.get("Status") or prom.get("Status") or "").upper(),
            "error": info.get("ErrorDetails"), "at": rows[0].get("CreatedDate"), "completed": prom.get("CompletionDate"),
            "merge": rows[0].get("MergeRemoteReference")}


def visible_tokens(entry, item, cwd):
    """Every request the stage shows for the work item, Scout's or one completed in Lifecycle Center's UI."""
    rows = query("SELECT DevopsPipelnStgProm.RequestInfo.RequestToken FROM DevopsPipelnStgPromWkItem WHERE WorkItemId = "
                 f"{quoted(item['id'])} AND DevopsPipelnStgProm.PipelineStageId = {quoted(id18(entry['stage_id']))} "
                 "AND DevopsPipelnStgProm.RequestInfoId != null", entry["hub"], cwd)
    return {((r.get("DevopsPipelnStgProm") or {}).get("RequestInfo") or {}).get("RequestToken") for r in rows} - {None}


def synced(entry, item, head, cwd):
    rows = query(f"SELECT Id FROM WorkItemComponentList WHERE WorkItemId = {quoted(item['id'])} "
                 f"AND CommitReference = {quoted(head)}", entry["hub"], cwd)
    return bool(rows)


def stage_busy(entry, cwd):
    return bool(query("SELECT Id FROM DevopsPipelnStgProm WHERE PipelineStageId = "
                      f"{quoted(id18(entry['stage_id']))} AND Status IN ({', '.join(map(quoted, RUNNING))})", entry["hub"], cwd))


def undeployed(entry, cwd, exclude=None):
    """Work items merged into main whose promotion hasn't succeeded: no later delivery may pass them."""
    rows = query("SELECT Name FROM WorkItem WHERE DevopsProjectId = "
                 f"{quoted(id18(entry['project_id']))} AND Status IN ('IN_REVIEW', 'READY_TO_PROMOTE')", entry["hub"], cwd)
    names = {r["Name"] for r in rows} - {exclude}
    if not names:
        return []
    merged = gh_list(["pr", "list", "--repo", entry["repo"], "--state", "merged", "--base", entry["stage_branch"],
                      "--limit", str(MERGED_LIMIT), "--json", "number,headRefName,mergeCommit"])
    if len(merged) >= MERGED_LIMIT:  # the newest merges may not reach back to an older one: look the rest up by branch
        seen = {p.get("headRefName") for p in merged}
        merged += [dict(p, headRefName=name) for name in sorted(names - seen)
                   for p in pull_requests(entry, name, "merged") if p.get("baseRefName") == entry["stage_branch"]]
    return [{"name": p["headRefName"], "pr": p["number"], "merge": (p.get("mergeCommit") or {}).get("oid")}
            for p in merged if p.get("headRefName") in names]


def blocked_text(other):
    return (f"{other['name']} (#{other['pr']}) is merged into main but not deployed; deliver it first (deliver --wi "
            f"{other['name']} --resume, with --retry after a failed promotion), or complete it in Lifecycle Center")


# ---- a delivery's local record (resume trusts the server; the record holds the captain's approved plan) ----

def record_path(team_id, wi_name):
    return team.cache_dir(team_id) / "deliveries" / f"{wi_name}.json"


def read_record(team_id, wi_name):
    try:
        return json.loads(record_path(team_id, wi_name).read_text())
    except (OSError, ValueError):
        return {}


def write_record(team_id, wi_name, fresh=False, **changes):
    record = {} if fresh else read_record(team_id, wi_name)
    record.update(changes, at=now())
    team.write_json_atomic(record_path(team_id, wi_name), record)
    return record


@contextlib.contextmanager
def file_lock(path, wait=10.0):
    """A short exclusive lock for a read-modify-write two Scout processes could interleave (a comment's send, the
    events cache). Yields False when another holds it past the wait, and the caller then leaves things as they are."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as handle:
        deadline = time.time() + wait
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() > deadline:
                    yield False
                    return
                time.sleep(0.05)
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def stop_file(team_id, wi_name):
    return team.cache_dir(team_id) / "deliveries" / f"{wi_name}.stop"


def stop_point(team_id, name, where):
    """A safe point, where nothing is in flight: when the captain asked this delivery to stop (scout_lc.py stop), it
    ends here, and --resume picks up. A stop never interrupts a call that changes something."""
    path = stop_file(team_id, name)
    if path.exists():
        path.unlink(missing_ok=True)
        raise failed(f"{name} stopped at the captain's request, {where}; nothing was in flight. deliver --wi {name} "
                     "--resume picks up from here", pending=True, resume=True, work_item=name, stopped=where)


def plan_id(head, base, tree, components, seen=None):
    return hashlib.sha256(json.dumps([head, base, tree, sorted(components), sorted((seen or {}).items())]).encode()).hexdigest()[:12]


def save_backup(team_id, wi_name, org, approved):
    """The org's copies the captain approved replacing (component → digest), from the retrieve the plan showed."""
    folder = team.cache_dir(team_id) / "backups" / f"{wi_name}-{int(time.time())}"
    for component in approved:
        for path, data in (org.get(component) or {}).get("files", {}).items():
            target = folder / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return {"folder": str(folder), "digests": dict(approved), "at": now()}


# ---- start and join: a checkout of an existing Lifecycle Center pipeline becomes a Scout team ----

def clone(repo_name, checkout):
    checkout = Path(checkout)
    if (checkout / ".git").exists():
        return checkout
    checkout.parent.mkdir(parents=True, exist_ok=True)
    result = team.run([team.tool("git"), "clone", "--quiet", f"https://github.com/{repo_name}.git", str(checkout)], timeout=600)
    if result.returncode:
        raise failed(f"cloning {repo_name} failed", detail=(result.stderr or "")[-300:])
    return checkout


def rules_files(agents, ignore, attributes):
    """{path: text} of what main still needs, from its AGENTS.md, .gitignore and .gitattributes (empty when absent):
    Scout's block in AGENTS.md, which every builder's agent reads, added or brought up to date with the team's own
    text kept; the .gitignore lines; and LF line endings, as the first line of .gitattributes, so the team's own
    lines can still override it. Text from a Windows checkout (CRLF) reads the same, so it never rewrites in a loop."""
    agents, ignore, attributes = (str(text or "").replace("\r\n", "\n") for text in (agents, ignore, attributes))
    block = f"{RULES_START}\n{AGENTS_MD}{RULES_END}\n"
    if RULES_START in agents and RULES_END in agents.split(RULES_START, 1)[1]:
        before, rest = agents.split(RULES_START, 1)
        after = rest.split(RULES_END, 1)[1].lstrip("\n")
        wanted = before + block + ("\n" + after if after else "")
    else:
        wanted = (agents.rstrip("\n") + "\n\n" if agents.strip() else "") + block
    files = {"AGENTS.md": wanted} if wanted != agents else {}
    missing = [line for line in GITIGNORE_LINES if line not in ignore.splitlines()]
    if missing:
        files[".gitignore"] = (ignore.rstrip("\n") + "\n" if ignore.strip() else "") + "\n".join(missing) + "\n"
    if ATTRIBUTES_LINE not in [" ".join(line.split()) for line in attributes.splitlines()]:
        files[".gitattributes"] = ATTRIBUTES_LINE + "\n" + attributes
    return files


def team_rules(repo, base):
    """{path: text} for main: the team's rules (rules_files) against main's own files at base."""
    def shown(path):
        result = git(repo, "show", f"{base}:{path}", check=False)
        return result.stdout if result.returncode == 0 else ""
    return rules_files(shown("AGENTS.md"), shown(".gitignore"), shown(".gitattributes"))


def propose_rules(repo, repo_name, commit, base, files, crlf=None):
    """main refused the rules (it's protected: a pull request or reviews required, or a ruleset), so they wait on one
    of Scout's own branches, as one commit on main, with a pull request when gh is there. Raises the stop: the team
    merges the pull request, then the captain runs start again. An outstanding proposal is never replaced: Scout reuses
    it as it is, and when it differs from what Scout would write now (a reviewer's edit, or an earlier start's), says
    so and keeps it. A merged one stays as it is too, so a new proposal goes out under a branch name not used yet."""
    fetch(repo)
    branches = rules_branches(repo)
    live = None
    for branch in reversed(branches):  # the newest proposal first
        state, tip, pr = proposal_state(repo, repo_name, branch, base)
        if state == "outstanding":
            live = (branch, tip, pr)
            break
    if live:
        branch, tip, pr = live
        ours = all(git(repo, "show", f"{tip}:{path}", check=False).stdout == text for path, text in files.items())
    else:
        branch, ours = next_rules_branch(branches), True
        push = git(repo, "push", "--porcelain", "origin", f"{commit}:refs/heads/{branch}", check=False, timeout=120)
        if push.returncode:
            raise failed(f"main refused the team's rules, and so did the branch {branch}; ask the repository's admin to "
                         "let the captain push either one", detail=(push.stdout + push.stderr)[-300:], files=sorted(files))
        pr = None
    problem = None
    if not pr and ours:
        pr, problem = rules_pull_request(repo_name, branch)
    compare = f"https://github.com/{repo_name}/compare/main...{branch}?expand=1"
    found = {"branch": branch, "compare": compare, "files": sorted(files), "pull_request": pr,
             **({"active_branches": BRANCHES_WAIT} if ".gitattributes" in files else {}),
             **({"earlier": [b for b in branches if b != branch]} if len(branches) > (1 if live else 0) else {}),
             **({"crlf": crlf} if crlf else {})}
    if not ours:
        where = f"pull request #{pr.get('number')} ({pr.get('url')})" if pr else f"the branch {branch} ({compare})"
        raise decide(f"main is protected, and {where} holds a proposal for the team's rules that differs from what Scout "
                     "would write now (a reviewer's edit, or an earlier start's), so Scout keeps it as it is. Review and "
                     "merge it (or close it and delete the branch), then run start again", needs="rules-review",
                     kept=True, **found)
    if pr:
        raise decide(f"main is protected, so the team's rules ({', '.join(sorted(files))}) wait in pull request "
                     f"#{pr.get('number')} ({pr.get('url')}), on the branch {branch}: merge the pull request, then run "
                     "start again", needs="rules-review", **found)
    raise decide(f"main is protected, so the team's rules ({', '.join(sorted(files))}) wait on the branch {branch}, and "
                 f"gh couldn't open the pull request here ({problem}). Open it at {compare}: merge the pull request, "
                 "then run start again", needs="rules-review", gh=problem, **found)


RULE_PATHS = ("AGENTS.md", ".gitignore", ".gitattributes")


def rules_branches(repo):
    """Scout's rule-proposal branches on origin, in the order they were made: scout/team-rules, then -2, -3, …"""
    found = []
    for name in out(repo, "for-each-ref", "--format=%(refname:lstrip=3)", "refs/remotes/origin/scout/",
                    check=False).splitlines():
        match = re.fullmatch(re.escape(RULES_BRANCH) + r"(?:-(\d+))?", name)
        if match:
            found.append((int(match[1] or 1), name))
    return [name for _, name in sorted(found)]


def next_rules_branch(branches):
    """A rules branch name not used yet: scout/team-rules first, then the next number after the last one."""
    if not branches:
        return RULES_BRANCH
    last = re.fullmatch(re.escape(RULES_BRANCH) + r"(?:-(\d+))?", branches[-1])
    return f"{RULES_BRANCH}-{int(last[1] or 1) + 1}"


def proposal_state(repo, repo_name, branch, base):
    """("outstanding" | "spent", tip, its open pull request or None). An open pull request means outstanding. Spent:
    its commit is in main, main holds its rules files (a squash merge keeps no ancestry), or GitHub shows a pull request
    merged from this very commit; one merged from an earlier branch of the same name proves nothing about this one.
    Anything else is outstanding, so a proposal nobody merged is never taken for spent."""
    tip = out(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}^{{commit}}", check=False)
    prs = branch_prs(repo_name, branch)
    open_pr = next((p for p in prs or [] if str(p.get("state")).upper() == "OPEN"), None)
    if open_pr:
        return "outstanding", tip, {"number": open_pr.get("number"), "url": open_pr.get("url")}
    merged_here = any(str(p.get("state")).upper() == "MERGED" and p.get("headRefOid") == tip for p in prs or [])
    if team.is_ancestor(repo, tip, base) or merged_here or all(
            git(repo, "show", f"{tip}:{path}", check=False).stdout == git(repo, "show", f"{base}:{path}", check=False).stdout
            for path in RULE_PATHS):
        return "spent", tip, None
    return "outstanding", tip, None


def branch_prs(repo_name, branch):
    """The branch's pull requests as GitHub shows them ([{number, url, state, headRefOid}]), or None when gh can't
    say. A deleted branch's name can come back, so each one's head commit says which branch it was."""
    try:
        code, stdout, _ = gh(["pr", "list", "--repo", repo_name, "--head", branch, "--state", "all", "--json",
                              "number,url,state,headRefOid"])
        found = json.loads(stdout) if code == 0 else None
    except (Stop, ValueError):
        return None
    return found if isinstance(found, list) else None


def rules_pull_request(repo_name, branch):
    """The rules branch's open pull request, else a new one: ({number, url}, None), or (None, why gh couldn't)."""
    try:
        code, stdout, stderr = gh(["pr", "list", "--repo", repo_name, "--head", branch, "--state", "open",
                                   "--json", "number,url"])
        if code:
            return None, (stderr or stdout or "no answer")[-200:]
        found = json.loads(stdout)
        if not isinstance(found, list):  # an empty or odd answer never counts as "no pull request yet"
            return None, "gh's answer was unreadable"
        if found:
            return {"number": found[0].get("number"), "url": found[0].get("url")}, None
        code, stdout, stderr = gh(["pr", "create", "--repo", repo_name, "--base", "main", "--head", branch,
                                   "--title", "Scout's team rules for every builder and agent", "--body",
                                   "Scout's team start adds the team's rules to `main`: Scout's block in `AGENTS.md`, "
                                   "the `.gitignore` lines and LF line endings in `.gitattributes`. `main` is protected, "
                                   "so they come as this pull request. Merge it, then the captain runs Scout's team "
                                   "start again."])
        if code:
            return None, (stderr or stdout or "no answer")[-200:]
        url = (stdout.strip().splitlines() or [""])[-1]
        number = re.search(r"/pull/(\d+)", url)
        return {"number": int(number[1]) if number else None, "url": url}, None
    except Stop as stop:  # gh isn't installed here, or it hung
        return None, str(stop.data.get("reason"))[:200]
    except (ValueError, AttributeError, IndexError, KeyError, TypeError):
        return None, "gh's answer was unreadable"


def lf_rule_at(repo, ref):
    """Whether .gitattributes at ref carries Scout's LF rule."""
    shown = git(repo, "show", f"{ref}:.gitattributes", check=False)
    return shown.returncode == 0 and ATTRIBUTES_LINE in [" ".join(line.split()) for line in shown.stdout.splitlines()]


def sync_main(repo, base):
    """The captain's checkout on main at origin's main, by fast-forward only, and the commit it was at before.
    Uncommitted work, or commits on the local main that origin's main doesn't have, stop the start and stay as they
    are: it never resets."""
    dirty = out(repo, "status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise refused("the team checkout has uncommitted changes, so start leaves it as it is: " +
                      "; ".join(dirty.splitlines()[:5]) + ". Commit or move them, then run start again", checkout=str(repo))
    if out(repo, "rev-parse", "--abbrev-ref", "HEAD") != "main":
        git(repo, "checkout", "--quiet", "main")
    local = out(repo, "rev-parse", "main")
    if local != base and not team.is_ancestor(repo, local, base):
        ahead = out(repo, "log", "--format=%h %s", f"{base}..{local}").splitlines()
        raise refused("the team checkout's main has commits origin's main doesn't (" + "; ".join(ahead[:5]) + "), so start "
                      "leaves them as they are: bring them in through a work item, or move them to a branch, then run "
                      "start again", checkout=str(repo), ahead=ahead[:20])
    if local != base:
        git(repo, "merge", "--quiet", "--ff-only", base)
    return local


CRLF_NEXT = ("These files are stored with CRLF line endings, which Git keeps until they're renormalized, so an editor's "
             "LF save would later show as a change and widen a delivery. Normalize them in a work item of their own: "
             "start it for every component in `components`, run `git add --renormalize .` on its branch, commit only "
             "that, push and open its review, and the captain delivers it like any other, never inside the rules' pull "
             "request. If that's more than one work item should carry, split them: each names its own components and "
             "renormalizes only their files (`git add --renormalize -- <its files>`). Once they're delivered, open "
             "work items' branches merge main again, as for the rules.")
# Whenever start brings in the LF rule, whatever main's line endings: branches cut earlier don't have it yet.
BRANCHES_STEP = ("builders whose work items were opened before then bring the rules onto their branches: they fetch "
                 "origin and merge main into their branch (`git fetch origin`, then `git merge origin/main`) before their "
                 "next commit, deploy the branch's copy into their sandbox, and update the work item's Checked line, as "
                 "AGENTS.md says.")
BRANCHES_WAIT = "Once the rules' pull request is merged, and not before, " + BRANCHES_STEP  # main doesn't have them yet
BRANCHES_NOW = "The rules are on main now: " + BRANCHES_STEP


def crlf_report(repo):
    """Files main already stores with CRLF line endings (the checkout's index, at main), with the documented way to
    normalize them; None when there are none. Reported, never changed by start."""
    files = []
    for line in out(repo, "ls-files", "--eol", check=False).splitlines():
        info, _, path = line.partition("\t")
        if path and info.split()[:1] and info.split()[0] in ("i/crlf", "i/mixed"):
            files.append(path)
    if not files:
        return None
    # The whole lists define the step, so they're never cut; only the preview is.
    return {"count": len(files), "files": files, "components": sorted({team.component_of(p) for p in files} - {None}),
            "other_files": [p for p in files if not team.component_of(p)], "preview": files[:10], "next": CRLF_NEXT}


def guard_here(repo, common, yes, captain):
    """Scout's guard on this machine, bound to the common org; a captain's binding also lets sf mp validate run."""
    installed = team.ensure_guard(yes)
    code, body = sf(["mp", "init", "--guard-only", "--target-org", common, *(["--lifecycle-captain"] if captain else [])],
                    cwd=repo, timeout=300)
    if code:
        raise failed("sf mp init --guard-only failed", detail=body)
    return dict(installed, guards=(body or {}).get("commonOrgId"), captain=bool((body or {}).get("lifecycleCaptain")))


GUARD_NOTES = {
    "off": "Scout's guard isn't on this machine for this team, by your choice: nothing here stops this machine's sf "
           "CLI from deploying to the common org, so build only in your own sandbox. The captain's status shows your "
           "guard is off",
    "on": "you chose no guard, but a guard from an earlier join still guards the common org on this machine, and "
          "Scout leaves it as it is: the team's record says so, and the captain's status shows it on. Taking it off "
          "is a step of its own: scout_lc.py unguard --team lc-{team}",
    "unknown": "you chose no guard, and Scout can't tell whether an earlier join's guard still guards the common "
               "org on this machine ({why}), so the team's record says unknown",
}


def sf_mp_registry():
    """sf-mp's own record of the orgs it guards on this machine, in the sf CLI's data folder."""
    # The folder as oclif resolves the CLI's dataDir: scopedEnvVar("DATA_DIR"), whose keys are the binary's name and
    # then its aliases, else the data home (@oclif/core, lib/config/config.js: dataDir, scopedEnvVarKeys, dir).
    # @salesforce/cli's package.json names sfdx as its alias (oclif.binAliases), so SF_DATA_DIR, then SFDX_DATA_DIR.
    data = os.environ.get("SF_DATA_DIR") or os.environ.get("SFDX_DATA_DIR")
    if not data:
        home = Path.home()
        data = (Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local") / "sf" if os.name == "nt" else
                Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "sf")
    return Path(data) / "sf-mp" / "bound-orgs.json"


def sf_mp_plugin():
    """What this machine's sf CLI says about sf-mp: ("installed", version), ("absent", None), or ("unknown", why).
    Only a successful, readable plugin list without sf-mp proves it's absent."""
    try:
        result = team.run([team.tool("sf"), "plugins", "--json"], cwd=os.getcwd(), timeout=120)
    except Stop as stop:
        return "unknown", str(stop.data.get("reason"))[:160]
    if result.returncode:
        return "unknown", "sf plugins failed: " + (result.stderr or result.stdout or "no answer").strip()[-160:]
    try:
        plugins = json.loads(result.stdout)
    except ValueError:
        return "unknown", "sf plugins answered unreadably"
    if not isinstance(plugins, list):
        return "unknown", "sf plugins answered without a list"
    found = next((p for p in plugins if isinstance(p, dict) and p.get("name") == "sf-mp"), None)
    return ("installed", found.get("version")) if found else ("absent", None)


def guard_binding(org_id):
    """Whether sf-mp guards this org on this machine now, as its own record says: ("on" | "off" | "unknown", why). A
    plugin list that failed or can't be read proves nothing, so it's unknown, never off."""
    plugin, why = sf_mp_plugin()
    if plugin == "unknown":
        return "unknown", why
    if plugin == "absent":
        return "off", "sf-mp isn't installed in this machine's sf CLI"
    try:
        data = json.loads(sf_mp_registry().read_text())
    except FileNotFoundError:
        return "off", None
    except (OSError, ValueError) as error:
        return "unknown", f"sf-mp's record of the orgs it guards is unreadable: {str(error)[:120]}"
    orgs = data.get("orgs") if isinstance(data, dict) else None
    if not isinstance(orgs, dict):
        return "unknown", "sf-mp's record of the orgs it guards is unreadable"
    return ("on" if org_id in orgs else "off"), None


def release_guard(org_id):
    """Removes this one org's guard binding from sf-mp's record, under sf-mp's own lock. Only a builder's guard
    binding goes: a lane's, or a Lifecycle Center captain's, stays. True when one was removed."""
    path = sf_mp_registry()
    lock = Path(str(path) + ".lock")
    for _ in range(50):
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            break
        except FileExistsError:
            time.sleep(0.1)
    else:  # waiting can't help a lock whose owner is gone, so the answer says whose it is and how to clear it
        try:
            owner = json.loads(lock.read_text())
        except (OSError, ValueError):
            owner = None
        held = (f"process {owner.get('pid')} on {owner.get('host')}, since {owner.get('at')}" if isinstance(owner, dict)
                else "an owner its lock file doesn't name")
        raise failed(f"sf-mp's record of the orgs it guards stays locked by {held} ({lock}); nothing changed. If that "
                     "process is still running, let it finish; once it's gone (`ps -p <pid>` shows nothing on that "
                     "machine), delete the lock file, then run unguard again", lock=str(lock), owner=owner)
    try:
        os.write(handle, json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "at": now()}).encode())
        os.close(handle)
        data = json.loads(path.read_text())
        found = data["orgs"].get(org_id)
        if found is None:
            return False
        if found.get("role") != "guard" or found.get("lifecycleCaptain"):
            raise refused("this machine's binding for the common org is a lane's or a captain's, so Scout leaves it")
        del data["orgs"][org_id]
        team.write_json_atomic(path, data, mode=0o644)
        return True
    except (OSError, ValueError, KeyError, AttributeError, TypeError) as error:
        raise failed(f"Scout couldn't change sf-mp's record ({str(error)[:160]}); nothing changed")
    finally:
        lock.unlink(missing_ok=True)


def cmd_unguard(a):
    """Takes Scout's guard off this machine for this team's common org: a step of its own, never part of a join, and
    only on the builder's yes. Only that org's binding goes; sf-mp stays for other orgs, and a captain's machine, or another
    team here that relies on the guard, keeps it."""
    team_id, entry = pick(a.team)
    org = entry["common_org_id"]
    if entry.get("role") == "captain":
        raise refused("the captain's machine keeps Scout's guard: the checks before every merge validate through it")
    others = [e.get("name", t) for t, e in team.load_registry()["teams"].items() if t != team_id and
              e.get("common_org_id") == org and (e.get("mode") != MODE or e.get("role") == "captain" or e.get("guard") != "off")]
    if others:
        raise refused("another team on this machine relies on this common org's guard (" + ", ".join(others) + "), so "
                      "Scout leaves it", teams=others)
    binding, why = guard_binding(org)
    if binding == "unknown":
        raise failed(f"Scout can't tell whether the guard is on here ({why}); nothing changed")
    if binding == "on" and not a.yes:
        raise decide("taking Scout's guard off this machine for the team's common org: from then on nothing here stops "
                     "this machine's sf CLI from deploying to it, and the captain's status shows your guard off",
                     needs="unguard-yes", org=org)
    removed = release_guard(org) if binding == "on" else False
    entry.update(guard="off", guard_choice="no")
    team.save_team(team_id, entry)
    problem = share_member(where(entry), entry.get("role"), "off", (entry.get("build_org") or {}).get("label"), "no")
    return {"team": team_id, "guard": "off", "removed": removed,
            "member_record": f"on {MEMBERS_BRANCH}" if not problem else {"problem": problem}}


def members(repo):
    """{id: record} from the members branch, as this checkout last fetched it. An unreadable record still shows."""
    tip = out(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{MEMBERS_BRANCH}^{{commit}}", check=False)
    found = {}
    for path, data in (team.tree_files(repo, tip) if tip else {}).items():
        if not re.fullmatch(r"members/[a-z0-9-]+\.json", path):
            continue
        try:
            item = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            item = None
        found[path[8:-5]] = item if isinstance(item, dict) else {"name": path[8:-5], "guard": "unknown", "problem": "unreadable"}
    return found


def share_member(repo, role, guard, build_label, choice=None):
    """This member's record on the members branch, written with Git plumbing (the checkout is untouched) as a
    compare-and-swap: a push someone else beat is tried again on their tip. None once it's there, else what went wrong."""
    try:
        ident = team.identity(repo)
    except Stop as stop:
        return str(stop.data.get("reason"))[:200]
    member_id = team.slug(ident["email"], "member")
    ref = "refs/heads/" + MEMBERS_BRANCH
    for attempt in range(4):
        try:
            fetch(repo)
            tip = out(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{MEMBERS_BRANCH}^{{commit}}",
                      check=False) or None
            files = team.tree_files(repo, tip)
            earlier = members(repo).get(member_id) or {}
            files[f"members/{member_id}.json"] = team.render({
                "schema": 1, "id": member_id, "name": ident["name"], "git_email": ident["email"], "role": role,
                "guard": guard, "guard_choice": choice or earlier.get("guard_choice"), "build_org": build_label,
                "scout": True, "joined_at": earlier.get("joined_at") or now(), "updated_at": now()})
            commit = team.make_commit(repo, tip, files, f"{ident['name']}, {role}: the guard is {guard} on their machine", ident)
            push = git(repo, "push", "--porcelain", "origin", f"{commit}:{ref}", check=False, timeout=60)
        except Stop as stop:
            return str(stop.data.get("reason"))[:200]
        if push.returncode == 0:
            git(repo, "update-ref", f"refs/remotes/origin/{MEMBERS_BRANCH}", commit)
            return None
        if not re.search(r"\[rejected\]|non-fast-forward|fetch first|stale info", push.stdout + push.stderr):
            return (push.stderr or push.stdout).strip()[-200:] or "the push was refused"
        time.sleep(0.3 * (attempt + 1))
    return "the members branch kept changing; join again"


def roster(entry):
    """The captain's view of the members: each record on the members branch, and whose guard is off."""
    repo, problem = where(entry), None
    try:
        fetch(repo)
    except Stop as stop:  # the copy fetched last still shows, and the answer says it may be old
        problem = str(stop.data.get("reason"))[:200]
    shown = [{"name": m.get("name"), "role": m.get("role"), "guard": m.get("guard") or "unknown",
              "choice": m.get("guard_choice"), "builds_in": m.get("build_org"), "joined_at": m.get("joined_at")}
             for m in sorted(members(repo).values(), key=lambda m: str(m.get("joined_at") or ""))]
    return {"members": shown, "guard_off": [m["name"] for m in shown if m["guard"] != "on"],
            **({"members_note": f"GitHub didn't answer, so this is the copy fetched last: {problem}"} if problem else {})}


def cmd_start(a, role="captain"):
    cwd = Path.cwd()
    if a.yes_guard and a.no_guard:
        raise refused("choose one: --yes-guard or --no-guard")
    if role == "captain" and a.no_guard:
        raise refused("the captain's machine needs Scout's guard: the checks before every merge validate through it")
    hub = team.org_info(a.hub)
    common = team.org_info(a.common_org)
    shape = pipeline_shape(a.hub, a.pipeline_id, cwd)
    if shape["stage_org_id"] != common["org_id"]:
        raise refused(f"the pipeline's stage deploys to {shape['stage_org_id'] or 'no org yet'}, not {common['label']} "
                      f"({common['org_id']}); name the stage's org with --common-org, or bind the stage first "
                      "(dx-devops-pipeline-manage)")
    checkout = Path(a.checkout or team.workspace() / "teams" / team.slug(shape["repo"].split("/")[-1])).expanduser()
    build = team.org_info(a.build_org) if getattr(a, "build_org", None) else None
    if build and build["org_id"] == common["org_id"]:  # whatever the guard choice: nothing here may build in the common org
        raise refused(f"{build['label']} is the team's common org ({common['org_id']}); your build org must be your own "
                      "sandbox, never the common org. Name your sandbox with --build-org", build_org=build["label"])
    plan = {"team": shape["name"], "repository": shape["repo"], "checkout": str(checkout), "hub": hub["label"],
            "common_org": common["label"], "role": role, "build_org": build["label"] if build else None}
    if not a.yes:
        if role == "captain":
            raise decide("one yes for the team set-up on this machine: clone the repository, install Scout's guard if "
                         "it's missing, guard the common org here, and add Scout's team rules (AGENTS.md, .gitignore "
                         "and .gitattributes lines) on main", needs="start-yes", plan=plan)
        raise decide("one yes for joining on this machine: clone the repository and register the team here; and the "
                     f"builder's yes or no for Scout's guard. {LC_GUARD}", needs="start-yes", plan=plan, guard=LC_GUARD,
                     choices=["join with the guard: --yes --yes-guard", "or join without it: --yes --no-guard"])
    if role == "builder" and not (a.yes_guard or a.no_guard):
        raise decide(LC_GUARD, needs="guard-choice", plan=plan, guard=LC_GUARD,
                     choices=["with the guard: --yes-guard", "or without it: --no-guard"])
    repo = clone(shape["repo"], checkout)
    base = fetch(repo)
    written, crlf, branches_next = [], None, None
    if role == "captain":
        before = sync_main(repo, base)  # the checkout follows main forward, so it holds what main holds
        if lf_rule_at(repo, base) and not lf_rule_at(repo, before):
            branches_next = BRANCHES_NOW  # the rules' pull request was merged: the LF rule arrives with this start
        crlf = crlf_report(repo)
        files = team_rules(repo, base)
        if files:
            git(repo, "checkout", "--quiet", "--detach")  # the rules commit is made off main, so main only moves forward
            for path, text in files.items():
                (repo / path).write_bytes(text.encode("utf-8"))
            git(repo, "add", "--", *files)
            git(repo, "commit", "--quiet", "-m", f"The team's rules for every builder and agent ({', '.join(sorted(files))})")
            commit = out(repo, "rev-parse", "HEAD")
            push = git(repo, "push", "--porcelain", "origin", f"{commit}:refs/heads/main", check=False, timeout=120)
            git(repo, "checkout", "--quiet", "main")
            if push.returncode:
                if "[remote rejected]" not in push.stdout + push.stderr:  # not a protected main: the network, say
                    raise failed("pushing the team's rules to main failed", detail=(push.stderr or push.stdout)[-300:])
                propose_rules(repo, shape["repo"], commit, base, files, crlf)  # stops: merge it, then start again
            git(repo, "merge", "--quiet", "--ff-only", commit)
            written = sorted(files)
            branches_next = BRANCHES_NOW if ".gitattributes" in files else branches_next
    guarded = role == "captain" or a.yes_guard
    if guarded:
        guard = dict(guard_here(repo, common["target"], True, captain=role == "captain"), choice="yes", binding="on")
    else:  # the builder's no puts nothing on; what's bound already (an earlier join's guard, say) stays, and is said
        binding, why = guard_binding(common["org_id"])
        guard = {"guard": binding, "binding": binding, "choice": "no", "note": GUARD_NOTES[binding].format(
            why=why, team=team.slug(shape["repo"]))}
    me = a.me or out(repo, "config", "user.name", check=False) or os.environ.get("USER", "me")
    team_id = f"lc-{team.slug(shape['repo'])}"
    entry = {"mode": MODE, "name": shape["name"], "slug": team.slug(shape["name"]), "checkout": str(repo),
             "repo": shape["repo"], "hub": hub["target"], "hub_org_id": hub["org_id"], "common_org": common,
             "common_org_id": common["org_id"], "project_id": shape["project_id"], "pipeline_id": shape["pipeline_id"],
             "stage_id": shape["stage_id"], "stage_branch": shape["stage_branch"], "role": role, "me": me,
             "guard": guard["binding"], "guard_choice": guard["choice"], "joined_at": now()}
    if build:
        entry.update(build_org=build, build_org_id=build["org_id"])
    team.save_team(team_id, entry)
    result = {"team": team_id, "role": role, "checkout": str(repo), "written_on_main": written, "guard": guard,
              "prompt": str(LC_PROMPT), **({"crlf": crlf} if crlf else {}),
              **({"active_branches": branches_next} if branches_next else {})}
    if role == "builder":
        problem = share_member(repo, role, guard["binding"], build["label"] if build else None, guard["choice"])
        result["member_record"] = f"on {MEMBERS_BRANCH}, where the captain's status reads it" if not problem else {
            "problem": problem, "next": "the captain's status can't show this member yet: tell the captain whether "
                                        "your guard is on, and join again once the push works"}
    return result


def cmd_join(a):
    if not a.build_org:
        raise refused("name your own sandbox with --build-org; you build there, never in the common org")
    return cmd_start(a, role="builder")


# ---- package start and check, and hand-over (Scout builders; the captain starts work items for others) ----

def build_org_of(entry, cwd):
    """This machine's build org for the team, checked before each piece of work with it: never the common org, as the
    registration names it or as its selector resolves now (an alias can be rebound), and still the org it joined with.
    None when this machine builds nowhere (a captain who starts work items for others)."""
    build = entry.get("build_org")
    if not build:
        return None
    common = entry.get("common_org_id")
    if common in (entry.get("build_org_id"), build.get("org_id")):
        raise refused("this machine's team registration names the common org as its build org, so Scout won't build or "
                      "read a sandbox with it. Join again with your own sandbox (--build-org)")
    now = team.org_info(build["target"], cwd)
    if now["org_id"] == common:
        raise refused(f"{build['target']} now names the team's common org, not your sandbox; reconnect your sandbox under "
                      "that name, or join again with --build-org")
    if now["org_id"] != build.get("org_id"):
        raise refused(f"{build['target']} now names org {now['org_id']}, not the sandbox you joined with "
                      f"({build.get('org_id')}); reconnect it, or join again with --build-org")
    return build


def base_check(entry, repo, base, components):
    """The builder's sandbox copy of each component against main's (see compare)."""
    build = build_org_of(entry, Path.cwd())
    if not build:
        return {}
    org = team.org_files(build["target"], sorted(components), team.source_api(repo))
    mine = team.files_at(repo, base, set(components))
    return {c: compare(mine.get(c), org[c]) for c in sorted(components)}


def cmd_package(a):
    team_id, entry = pick(a.team)
    if a.action == "check":
        return package_check(entry, a)
    repo, cwd = where(entry), Path.cwd()
    components = sorted(set(team.components_of(a.components or [])))
    if not a.title or not components:
        raise refused("package start needs --title and the components it changes (--components Type:Name …)")
    base = fetch(repo)
    report = base_check(entry, repo, base, components)
    clean = bool(report) and all(v in CLEAN for v in report.values())
    lines = [describe_components(components)] + ([f"Builder: {a.owner}"] if a.owner else []) + ([f"Checked: {base}"] if clean else [])
    code, body, kind = devops(["work-item", "create", "--project-id", id18(entry["project_id"]), "--subject", a.title,
                               "--description", "\n".join(lines)], entry["hub"], cwd)
    if kind != "ok" or not body.get("workItemName"):
        raise failed(f"Lifecycle Center didn't create the work item: {message_of(body)[:300]}")
    name = body["workItemName"]
    update_item(entry, name, cwd, status="In Progress")
    overlaps, unread = [], None
    try:  # the work item exists now, so an unreadable list says so rather than failing the start
        for pr in gh_list(["pr", "list", "--repo", entry["repo"], "--state", "open", "--json", "number,headRefName,files"]):
            touched = {team.component_of(f.get("path", "")) for f in pr.get("files") or []}
            for component in sorted(touched & set(components)):
                overlaps.append({"component": component, "pr": pr["number"], "branch": pr.get("headRefName")})
    except Stop as stop:
        unread = str(stop.data.get("reason"))[:200]
    result = {"work_item": name, "branch": name, "components": components, "base": base[:12], "base_check": report,
              "checked": base[:12] if clean else None, "overlaps": overlaps if unread is None else {"unread": unread}}
    if report and not clean:
        result["next"] = (f"deploy main's copy of what differs into your sandbox, then run package check --wi {name} "
                          "before you edit")
    elif not report:
        result["next"] = (f"its builder records their checked base before editing: package check --wi {name} on their "
                          "machine, or a Checked line as AGENTS.md says")
    return result


def package_check(entry, a):
    """Records the builder's checked base on the work item, when their sandbox holds main's copy of its components.
    Only main counts: a sandbox that matches its own branch proves nothing about the branch's base. After a builder
    merged main into their branch, the captain confirms the base at delivery instead."""
    repo, cwd = where(entry), Path.cwd()
    build = build_org_of(entry, cwd)
    if not build:
        raise refused("this machine has no build org in the team; the check compares your own sandbox with main")
    if not a.wi:
        raise refused("name the work item: package check --wi WI-…")
    item = work_item(entry, a.wi, cwd)
    components = declared(item)
    if not components:
        raise refused(f"{item['name']} names no components on a `Components:` line")
    base = fetch(repo)
    org = team.org_files(build["target"], components, team.source_api(repo))
    files = team.files_at(repo, base, set(components))
    report = {c: compare(files.get(c), org[c]) for c in components}
    if not all(v in CLEAN for v in report.values()):
        raise refused("your sandbox's copy doesn't match main's: deploy main's copy into your sandbox, re-apply your "
                      "change there if it's lost, then check again. If you merged main into your branch instead, tell "
                      "the captain, who confirms the base at delivery", report=report)
    kept = CHECKED_LINE.sub("", item["description"]).rstrip("\n")
    update_item(entry, item["name"], cwd, description=(kept + "\n" if kept else "") + f"Checked: {base}")
    return {"work_item": item["name"], "checked": base[:12], "against": "main"}


def cmd_handover(a):
    team_id, entry = pick(a.team)
    repo, cwd = where(entry), Path.cwd()
    build = build_org_of(entry, cwd)
    if not build:
        raise refused("this machine has no build org in the team; hand-over retrieves from your own sandbox")
    item = work_item(entry, a.wi, cwd)
    components = declared(item)
    if not components:
        raise refused(f"{item['name']} names no components on a `Components:` line; Scout commits only what it names")
    checked = CHECKED.search(item["description"])
    if not checked and not a.unchecked:
        raise refused(f"{item['name']} has no Checked line, so nothing shows your sandbox's copy started from main's. "
                      f"Bring your sandbox to main's copy (and re-apply your change), run package check --wi "
                      f"{item['name']}, then hand over; or hand over with --unchecked, and the captain asks you at delivery")
    with team.CheckoutLock(repo):
        team.require_clean(repo)
        fetch(repo)
        if not team.remote_branch(repo, item["branch"]):
            raise refused(f"{item['branch']} isn't on GitHub yet; set {item['name']} In Progress first")
        git(repo, "checkout", "--quiet", "-B", item["branch"], f"refs/remotes/origin/{item['branch']}")
        org = team.org_files(build["target"], components, team.source_api(repo))
        unreadable = [c for c in components if org[c]["state"] != "present"]
        if unreadable:
            team.back_to_main(repo)
            raise refused("these aren't in your sandbox: " + ", ".join(unreadable))
        paths = []
        for component in components:  # a file the sandbox no longer has stays on the branch: v1 never deletes
            for path, data in org[component]["files"].items():
                target = repo / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                paths.append(path)
        git(repo, "add", "--", *paths)
        if not out(repo, "diff", "--cached", "--name-only"):
            team.back_to_main(repo)
            return {"work_item": item["name"], "handed_over": False, "note": "your sandbox's copies equal the branch's; nothing to hand over"}
        git(repo, "commit", "--quiet", "-m", f"{item['name']}: {item['subject']}")
        head = out(repo, "rev-parse", "HEAD")
        push = git(repo, "push", "--quiet", "origin", item["branch"], check=False, timeout=120)
        team.back_to_main(repo)
        if push.returncode:
            raise failed("the push to GitHub failed", detail=(push.stderr or "")[-300:], work_item=item["name"])
    code, body, kind = devops(["review", "create", "--work-item-name", item["name"]], entry["hub"], cwd)
    if kind != "ok":
        prs = pull_requests(entry, item["branch"], "open")
        if not prs:
            raise failed(f"the review wasn't created: {message_of(body)[:300]}", work_item=item["name"], head=head[:12])
        body = {"url": prs[0]["url"]}
    return {"work_item": item["name"], "handed_over": True, "head": head[:12], "components": components,
            "review": body.get("url"), "checked": checked[1][:12] if checked else None}


# ---- the captain's delivery: checks, the yes, the merge, then everything from the server's state ----

def cmd_deliver(a):
    started = time.time()
    team_id, entry = pick(a.team)
    repo, cwd = where(entry), Path.cwd()
    if entry.get("role") != "captain":
        raise refused("only the team's captain delivers")
    try:
        check_stage(entry, cwd)
        resend_comments(team_id, entry)
        item = work_item(entry, a.wi, cwd)
        stale = stop_file(team_id, item["name"])
        if stale.exists() and stale.stat().st_mtime < started:  # a request from before this run isn't for it
            stale.unlink(missing_ok=True)
        with team.CheckoutLock(repo):
            if a.resume or a.retry or a.full:
                return resume(team_id, entry, repo, item, a, cwd)
            return plan_and_merge(team_id, entry, repo, item, a, cwd)
    except Stop as stop:
        raise known_phase(team_id, a.wi, stop)


AFTER_MERGE = {"merging", "merged", "syncing", "recheck", "completing", "promoting", "tests-running", "tests-failed",
               "failed", "unverified"}  # a delivery's steps once its merge was asked for


def known_phase(team_id, wi_name, stop):
    """A failure once this delivery's merge or promotion is under way says where the delivery stands and to resume,
    whatever the step that failed could tell: the record keeps the phase and the request. A failure that already
    says how to go on is left as it is."""
    if stop.code != 1 or any(stop.data.get(k) for k in ("resume", "retry", "choices")) or not WI_NAME.match(str(wi_name)):
        return stop
    record = read_record(team_id, wi_name)
    step, token = record.get("step"), record.get("token")
    if step not in AFTER_MERGE:
        return stop
    stop.data.update(resume=True, pending=True, phase=step, **({"token": token} if token else {}))
    stop.data["reason"] = (f"{stop.data.get('reason')}. {wi_name} is past its merge ({step}" +
                           (f", request {token}" if token else "") + f"), so deliver --wi {wi_name} --resume picks up "
                           "from there")
    return stop


def checks(team_id, entry, repo, item, head, base, tree, pr, a, cwd, merged=False):
    """Scout's checks on a candidate (head merged onto base, as `tree`), in order; each problem stops before the yes.
    Returns the plan the yes binds to (the revision, its components, the org copies seen) and what the checks found."""
    after = ("; it's on main already, so Scout won't deploy it: complete it in Lifecycle Center if it's wanted, then "
             "deliver --resume reads it back") if merged else ""
    progress(item["name"], "checking", "the scope, the builder's base, the effects and the common org's copies")
    scope = scope_of(repo, base, tree, item)
    candidate = team.files_at(repo, tree, set(scope["components"]))
    problems = []
    if scope["unrecognized"]:
        problems.append("files Scout can't map to a component: " + ", ".join(scope["unrecognized"][:8]))
    if scope["metadata_elsewhere"]:
        problems.append("metadata outside force-app/main/default, which Scout's Lifecycle Center mode doesn't deliver: "
                        + ", ".join(scope["metadata_elsewhere"][:8]))
    if scope["outside"]:
        problems.append(f"components {item['name']} doesn't name on its Components line: " + ", ".join(scope["outside"]))
    deleted = [c for c in scope["components"] if not candidate.get(c)]
    if deleted:
        problems.append("it deletes " + ", ".join(deleted) + ", and Scout's Lifecycle Center mode doesn't deliver deletions")
    if problems:
        raise refused("; ".join(problems) + after, work_item=item["name"])
    components = scope["components"]
    if not components:
        raise refused(f"{item['name']} changes no components against main" + after)
    plan = {"work_item": item["name"], "pull_request": pr, "head": head[:12], "main": base[:12],
            "components": components, "declared": scope["declared"]}
    split = split_new(repo, base, head, components)
    if split:  # the default promotion is known to resolve none of these; the full promotion is the way
        plan["split_new"] = split
    if scope["other_files"] and not a.confirm_other:
        raise decide("the merge also changes files that aren't the org's metadata; they go into main, never the org",
                     needs="other-files", files=scope["other_files"][:20],
                     choices=["confirm them: --confirm-other", "or ask the builder to take them off the branch"], **plan)
    evidence = base_evidence(repo, base, head, item, components)
    if evidence["state"] == "unchecked" and not a.confirm_base:
        raise decide(f"nothing shows that the builder's copy started from main's ({evidence['detail']}), so it could be "
                     "an old copy that undoes a delivered change", needs="unchecked-base", choices=[
                         "the builder checks: Scout's package check, or a Checked line as AGENTS.md says",
                         "or confirm it on the builder's word: --confirm-base"], **plan)
    if evidence["state"] == "stale" and not a.confirm_base:
        raise decide("main changed these components between the builder's checked base and where their branch starts, "
                     "so their older copy could undo that change", needs="stale-base", checked=evidence["checked"],
                     later=evidence["later"], choices=[
                         "the builder brings their sandbox to main's copy, re-applies their change and hands over again",
                         "or confirm their copy already holds that change: --confirm-base"], **plan)
    org = read_org(entry, repo, components)
    effects = effect_problems(candidate, components, org)
    if effects:
        raise refused("the effect checks stop it: " + "; ".join(p for ps in effects.values() for p in ps) + after, **plan)
    edits = direct_edits(team_id, entry, repo, base, components, org, promoted_merges(entry, cwd),
                         backflow_snapshots(team_id, item["name"]))
    unreadable = {c: r for c, r in edits.items() if r["state"] == "unreadable"}
    if unreadable:
        raise refused("Scout couldn't read the common org's copy of " + ", ".join(unreadable) + ", so it can't compare "
                      "or back it up, and nothing changed; deliver again, and if it persists, look at it in the org",
                      edits=unreadable, **plan)
    changed = {c: r for c, r in edits.items() if r["state"] != "same"}
    if changed and not a.overwrite:
        raise decide("the common org doesn't hold the copy the pipeline last delivered (changed), or main holds changes "
                     "no promotion delivered (main-ahead)", needs="direct-edit", edits=changed, choices=(
                         ["overwrite it: deliver --resume --overwrite; Scout backs up the org's copy first"] if merged else
                         ["back-flow the org's copy first (scout_lc.py backflow), and deliver that work item before this one",
                          "or overwrite it: --overwrite; Scout backs up the org's copy first, and the yes binds to the copy shown"]),
                     **plan)
    progress(item["name"], "validating", "a check-only validation against the common org")
    validation = validate(team_id, entry, repo, tree, candidate, components, item["name"], cwd)
    outcome = "passed" if validation["validated"] else \
        "compiled, but ran none of the tests asked for" if validation.get("ran_none") else "didn't pass"
    progress(item["name"], "validated", f"job {validation.get('jobId')}: {outcome}, {validation.get('testsRun')} tests run")
    after = []
    if not validation["validated"]:
        if not validation.get("ran_none"):  # the strict gate: a failure, or anything the platform didn't prove
            raise decide("the check-only validation didn't pass, so nothing " + ("deploys" if merged else "is merged"),
                         needs="tests", validation=validation, **plan)
        if not a.tests_after:
            raise decide("the common org compiled the delivery, but ran none of the tests Scout asked for: some orgs run "
                         "no tests during a deploy, at any test level (measured 19 Oct). With the captain's yes, Scout "
                         + ("promotes it" if merged else "merges and promotes it") + ", then these tests run in the common "
                         "org right after the promotion, and only a passing run says verified", needs="tests-after",
                         tests=validation["tests"], validation=validation, choices=[
                             "test after the promotion: the same command with --tests-after",
                             "or stop here: nothing " + ("deploys" if merged else "is merged")], **plan)
        after = list(validation["tests"])
    plan["plan_id"] = plan_id(head, base, tree, components, {c: r["digest"] for c, r in edits.items()})
    tests = {k: validation.get(k) for k in ("tests", "suites", "testsRun", "jobId")}
    if after:
        tests["after"] = plan["tests_after"] = after
    summary = {"scope": "ok" if scope["declared"] else "not declared: the work item has no Components line, so the "
               "captain's yes approves this list", "other_files": scope["other_files"], "effects": "ok", "direct_edits": edits,
               "base": dict(evidence, confirmed=evidence["state"] != "checked"), "overwrite": sorted(changed), "tests": tests}
    return plan, {"org": org, "overwrite": {c: r["digest"] for c, r in changed.items()}, "validated": tests,
                  "tests_after": after, "summary": summary}


def plan_and_merge(team_id, entry, repo, item, a, cwd):
    prs = pull_requests(entry, item["branch"])
    if any(p.get("state") == "MERGED" for p in prs):
        raise refused(f"{item['name']} is merged already; deliver --wi {item['name']} --resume continues its delivery")
    prs = [p for p in prs if p.get("state") == "OPEN"]
    if not prs:
        raise refused(f"{item['name']} has no open review; its builder opens one (sf devops review create)")
    pr = prs[0]
    if pr.get("baseRefName") != entry["stage_branch"]:
        raise refused(f"pull request #{pr['number']} targets {pr.get('baseRefName')}, not {entry['stage_branch']}")
    if stage_busy(entry, cwd):
        raise refused("a promotion is running on this stage; deliver when it has finished")
    waiting = undeployed(entry, cwd, exclude=item["name"])
    if waiting:
        raise refused("the stage has unresolved work: " + "; ".join(blocked_text(w) for w in waiting))
    base = fetch(repo)
    head = pr["headRefOid"]
    tree, conflicts = trial_merge(repo, base, head)
    if tree is None:
        raise decide(f"{item['name']} conflicts with main in " + ", ".join(conflicts or ["some files"]) +
                     "; its owner resolves it with the official conflict skill's Git track, then pushes",
                     needs="conflict", work_item=item["name"], files=conflicts)
    plan, found = checks(team_id, entry, repo, item, head, base, tree, pr["number"], a, cwd)
    subject = f"{item['name']}: {item['subject']} (#{pr['number']})"
    if not a.yes or a.plan_id != plan["plan_id"]:
        why = "the plan changed since you saw it" if a.yes and a.plan_id else "the captain's yes, in plain words"
        raise decide(f"{why}: this merges pull request #{pr['number']} into main as one commit, then deploys "
                     f"{len(plan['components'])} components to the common org", needs="deliver-yes", subject=subject,
                     checks=found["summary"], **plan)
    backup = save_backup(team_id, item["name"], found["org"], found["overwrite"]) if found["overwrite"] else None
    write_record(team_id, item["name"], fresh=True, pr=pr["number"], head=head, base=base, tree=tree,
                 components=plan["components"], plan_id=plan["plan_id"], approved=now(), validated=found["validated"],
                 tests_after=found["tests_after"], overwrite=found["overwrite"], backups=[backup] if backup else [],
                 step="planned")
    stop_point(team_id, item["name"], "before the merge")
    write_record(team_id, item["name"], step="merging")
    progress(item["name"], "merging", f"pull request #{pr['number']} into main", safe=False)
    code, stdout, stderr = gh(["pr", "merge", str(pr["number"]), "--repo", entry["repo"], "--squash", "--subject", subject,
                               "--match-head-commit", head])
    if code and not any(p.get("state") == "MERGED" for p in pull_requests(entry, item["branch"])):
        write_record(team_id, item["name"], step="planned")
        raise failed(f"GitHub didn't merge #{pr['number']}: {(stderr or stdout)[-300:]}; nothing changed", **plan)
    return resume(team_id, entry, repo, item, a, cwd)


def resume(team_id, entry, repo, item, a, cwd):
    """Continues a delivery from what GitHub and the server show. A merge without the captain's approved plan for
    exactly that revision (merged elsewhere, a lost record, or main moved before GitHub merged) is checked as it
    stands on main, and nothing deploys without a yes for it."""
    name = item["name"]
    record = read_record(team_id, name)
    progress(name, "continuing", "from what GitHub and Lifecycle Center show")
    if record.get("step") == "verified":
        sent = send_comment(team_id, entry, name)
        return {"work_item": name, "outcome": "verified", "merge": str(record.get("verified"))[:12],
                "comment": "sent" if sent else "pending", "note": "this delivery finished earlier"}
    if record.get("step") == "tests-running":
        return run_owed_tests(team_id, entry, repo, item, cwd)
    if record.get("step") == "tests-failed" and not record.get("promoted_at") and record.get("test_run") and \
            record.get("tests_failed") == ["the run didn't start after the promotion"]:
        write_record(team_id, name, step="tests-running")  # only the missing time failed it: the same run, judged again
        return run_owed_tests(team_id, entry, repo, item, cwd)
    if record.get("step") == "tests-failed":
        if record.get("pr") and not str((record.get("comment") or {}).get("body") or "").startswith("Not verified: "):
            set_comment(team_id, name,
                        f"Not verified: {name} (pull request #{record['pr']}): tests failed in the common org after the "
                        f"promotion (run {record.get('test_run')}): " + "; ".join((record.get("tests_failed") or [])[:6]) +
                        ". Its changes are in the common org; the fix goes on a new work item, or a revert work item undoes "
                        "them.")
        send_comment(team_id, entry, name)
        if a.retry:
            write_record(team_id, name, step="tests-running", test_run=None)
            return run_owed_tests(team_id, entry, repo, item, cwd)
        raise failed(record.get("tests_failed_text") or "not verified: tests failed in the common org after the promotion",
                     work_item=name, test_run=record.get("test_run"), tests_failed=record.get("tests_failed") or [],
                     choices=failure_choices(record))
    main = fetch(repo)
    prs = pull_requests(entry, item["branch"])
    merged = [p for p in prs if p.get("state") == "MERGED"]
    if not merged:
        if any(p.get("state") == "OPEN" for p in prs):
            return plan_and_merge(team_id, entry, repo, item, a, cwd)
        raise refused(f"{name} has no open or merged review")
    pr = merged[0]
    merge, head = (pr.get("mergeCommit") or {}).get("oid"), pr.get("headRefOid")
    if not merge or not team.is_ancestor(repo, merge, main):
        raise failed(f"GitHub reports #{pr['number']} merged, but main doesn't hold it yet; resume in a minute",
                     pending=True, resume=True)
    base, tree = out(repo, "rev-parse", f"{merge}^"), out(repo, "rev-parse", f"{merge}^{{tree}}")
    planned = bool(record.get("plan_id") and record.get("validated")) and \
        (record.get("head"), record.get("base"), record.get("tree")) == (head, base, tree)
    state = {"pr": pr["number"], "merge": merge, "head": head, "base": base, "tree": tree,
             "components": record["components"] if planned else scope_of(repo, base, tree, item)["components"]}
    full = a.full or bool(planned and record.get("full"))  # a full promotion deploys, and is read back, in full
    if planned and record.get("full") and record.get("full_main") and not a.full:
        state.update(components=record["components_all"], target=record["full_main"])  # main as Scout checked it
    if planned and record.get("merge") != merge:
        record = write_record(team_id, name, merge=merge, step="merged")
    promotion = promotion_for(entry, item, cwd)
    earlier = set(record.get("earlier_tokens") or []) | set(record.get("tokens") or [])
    if promotion and record.get("step") == "completing" and promotion.get("token") in earlier:
        promotion = None  # an earlier attempt's record; this attempt's answer is the one that's unknown
    if promotion and record.get("step") == "promoting" and record.get("token") and \
            promotion.get("token") != record["token"] and promotion.get("token") in earlier:
        promotion = None  # an earlier attempt's record; the saved request is this attempt's
    deployed = bool(promotion and promotion["status"] == "SUCCESS" and not promotion.get("error"))
    running = bool(promotion and promotion["status"] not in TERMINAL)
    if a.full and (deployed or running):
        state.update(full_scope(repo, main, name))  # completed in Lifecycle Center's UI too: main as it stands
    if deployed:
        return read_back(team_id, entry, repo, item, state, cwd)  # deployed: by Scout, or in Lifecycle Center
    if running:
        return watch_promotion(team_id, entry, repo, item, state, promotion.get("token"), cwd)
    if not promotion and record.get("step") == "promoting" and record.get("token"):  # submitted, its record not visible
        return watch_promotion(team_id, entry, repo, item, state, record["token"], cwd)
    if not promotion and record.get("step") == "completing" and not a.retry:
        raise failed(f"Scout submitted {name}'s promotion but got no answer it could read, and Lifecycle Center shows no "
                     "promotion for it yet, so Scout won't submit another on its own. Wait a minute and resume; if "
                     "Lifecycle Center still shows none, deliver --resume --retry submits again", pending=True, resume=True,
                     work_item=name)
    if not planned:
        record = replan(team_id, entry, repo, item, state, record, a, cwd)
        state["components"] = record["components"]
    if promotion and not (a.retry or a.full):
        write_record(team_id, name, step="failed")
        raise failed(promotion_failed(name, promotion), promotion=promotion, retry=True, full=empty_set(promotion))
    if full:  # --full, or a retry after a full promotion failed: never quietly back to the default mode
        return promote_all(team_id, entry, repo, item, state, record, promotion, a, cwd)
    return promote(team_id, entry, repo, item, state, record, promotion, a, cwd)


def full_scope(repo, ref, name):
    """A full read-back's scope: every component on main at ref, when Scout can check all of what was deployed."""
    payload = full_payload(repo, ref)
    if payload["unchecked"]:
        raise refused("a full promotion deploys everything in the stage branch, and Scout can't check these files: "
                      + ", ".join(payload["unchecked"][:8]) + f". Look at them in the common org; deliver --wi {name} "
                      f"--resume, without --full, reads back {name}'s own components", work_item=name,
                      unchecked=payload["unchecked"][:50])
    if len(payload["components"]) > FULL_CEILING:
        raise refused(f"main holds {len(payload['components'])} components, more than a full promotion's check covers "
                      f"({FULL_CEILING}); check the org yourself, or deliver --wi {name} --resume, without --full, reads "
                      f"back {name}'s own components", work_item=name)
    return {"components": payload["components"], "target": ref}


def replan(team_id, entry, repo, item, state, record, a, cwd):
    """A merge without an approved plan for its revision: the same checks on the merged revision, then the yes."""
    why = ("the merge on main isn't the revision Scout checked (main moved before GitHub merged it, or the branch was "
           "pushed again)" if record.get("plan_id") else "Scout has no approved plan for this merge (merged on GitHub "
           "or on another machine, or the record is gone)")
    plan, found = checks(team_id, entry, repo, item, state["head"], state["base"], state["tree"], state["pr"], a, cwd, merged=True)
    if not a.yes or a.plan_id != plan["plan_id"]:
        raise decide(f"{why}. Scout checked the merged revision; nothing deploys without the captain's yes for it",
                     needs="deliver-yes", resume=True, checks=found["summary"], **plan)
    backup = save_backup(team_id, item["name"], found["org"], found["overwrite"]) if found["overwrite"] else None
    return write_record(team_id, item["name"], fresh=True, pr=state["pr"], merge=state["merge"], head=state["head"],
                        base=state["base"], tree=state["tree"], components=plan["components"], plan_id=plan["plan_id"],
                        approved=now(), validated=found["validated"], tests_after=found["tests_after"],
                        overwrite=found["overwrite"], backups=[backup] if backup else [], step="merged")


def promote(team_id, entry, repo, item, state, record, previous, a, cwd):
    """For a merge with an approved plan: ready, sync, recheck, then one promotion, polled and read back."""
    name, components = item["name"], state["components"]
    paths = paths_of(repo, [state["merge"], "refs/remotes/origin/main"], set(components))
    later = out(repo, "log", "--format=%h %s", f"{state['merge']}..refs/remotes/origin/main", "--", *paths).splitlines() if paths else []
    if later:
        raise failed("main changed this delivery's components after its merge (" + "; ".join(later[:5]) + "), so the "
                     "promotion could deploy more than was checked. Complete the promotions in Lifecycle Center in merge "
                     "order, then deliver --resume reads each back", pending=True)
    if stage_busy(entry, cwd):
        raise failed("a promotion is running on this stage; resume when it has finished", pending=True, resume=True)
    ahead = [w for w in undeployed(entry, cwd, exclude=name) if w["merge"] and team.is_ancestor(repo, w["merge"], state["merge"])]
    if ahead:
        raise refused("work merged before this one isn't deployed: " + "; ".join(blocked_text(w) for w in ahead))
    item = ready(entry, item, cwd)
    sync(team_id, entry, item, state["head"], cwd)
    recheck(team_id, entry, repo, item, state, record, a, cwd)
    token = complete(team_id, entry, item, previous, cwd, head=state["head"])
    return watch_promotion(team_id, entry, repo, item, state, token, cwd)


def promote_all(team_id, entry, repo, item, state, record, previous, a, cwd):
    """A full promotion (`promotion complete --deploy-all`): everything in the stage branch goes to the org, not only
    this work item's components. It's the way past a promotion that resolves no components. It's safe only while the
    rest matches what the pipeline delivered and main holds still, so Scout refuses what it can't check, checks every
    component on main against the org, binds the yes to all of their copies, and looks at main again right before it
    deploys and before it says verified."""
    name, merge = item["name"], state["merge"]
    write_record(team_id, name, full=True)  # a stop before the submit resumes in full, never quietly in the default mode
    own = record.get("components") or state["components"]
    main = out(repo, "rev-parse", "refs/remotes/origin/main")
    later = out(repo, "log", "--format=%h %s", f"{merge}..{main}", "--", *deployable(repo, main)).splitlines()
    if later:
        waiting = [w["name"] for w in undeployed(entry, cwd, exclude=name)
                   if w["merge"] and w["merge"] != merge and team.is_ancestor(repo, merge, w["merge"])]
        together = " and ".join([name, *waiting]) if waiting else name
        raise refused("main has commits after this merge that change what a full promotion deploys ("
                      + "; ".join(later[:5]) + "), so it would deploy them unchecked. Scout won't, and the merge order "
                      "holds back " + (", ".join(waiting) if waiting else "the work merged after it") + ". The way out: "
                      f"ask the team to hold merges into main; in Lifecycle Center, complete {together} together with "
                      "Promotion Options → All changes in the stage branch, which overwrites what the common org holds "
                      f"for every component on main; then deliver --wi {name} --resume --full reads everything back",
                      work_item=name, waiting=waiting, later=later[:20])
    payload = full_payload(repo, main)
    if payload["unchecked"]:
        raise refused("a full promotion deploys everything in the stage branch, and Scout can't check these files: "
                      + ", ".join(payload["unchecked"][:8]) + ". Complete it in Lifecycle Center after checking them "
                      f"yourself, then deliver --wi {name} --resume --full reads back what Scout can", work_item=name,
                      unchecked=payload["unchecked"][:50])
    everything = payload["components"]
    if len(everything) > FULL_CEILING:
        raise refused(f"main holds {len(everything)} components, more than a full promotion's check covers "
                      f"({FULL_CEILING}); check the org yourself, then complete it in Lifecycle Center", work_item=name)
    if stage_busy(entry, cwd):
        raise failed("a promotion is running on this stage; resume when it has finished", pending=True, resume=True)
    ahead = [w for w in undeployed(entry, cwd, exclude=name) if w["merge"] and team.is_ancestor(repo, w["merge"], merge)]
    if ahead:
        raise refused("work merged before this one isn't deployed: " + "; ".join(blocked_text(w) for w in ahead))
    item = ready(entry, item, cwd)
    sync(team_id, entry, item, state["head"], cwd)
    org = read_org(entry, repo, everything)
    edits = direct_edits(team_id, entry, repo, state["base"], everything, org, promoted_merges(entry, cwd),
                         backflow_snapshots(team_id, name))
    unreadable = {c: r for c, r in edits.items() if r["state"] == "unreadable"}
    if unreadable:
        raise failed("Scout couldn't read the common org's copy of " + ", ".join(unreadable) + "; nothing was "
                     "deployed. Resume when the org reads again", pending=True, resume=True, work_item=name, edits=unreadable)
    approved = record.get("overwrite") or {}
    moved = {c: r for c, r in edits.items() if r["state"] != "same" and approved.get(c) != r["digest"]}
    if moved and not a.overwrite:
        write_record(team_id, name, step="recheck")
        raise decide("a full promotion deploys every component on main, and for these the common org doesn't hold the "
                     "copy the pipeline last delivered (changed), or main holds changes no promotion delivered "
                     "(main-ahead)", needs="direct-edit", resume=True, work_item=name, edits=moved, choices=[
                         "deploy main's copy over them too: deliver --resume --full --overwrite; Scout backs up the org's "
                         "copies first, and the yes binds to the copies shown",
                         "or complete the promotion in Lifecycle Center, then deliver --resume --full reads it back"])
    pid = plan_id(state["head"], merge, state["tree"], everything, {c: r["digest"] for c, r in edits.items()})
    if not a.yes or a.plan_id != pid:
        raise decide(f"the captain's yes for a full promotion: it deploys all {len(everything)} components on main at "
                     f"{main[:12]}, not only {name}'s {len(own)}. Scout checked every one against the org. Ask the team "
                     "to hold merges into main until it has finished: Scout looks at main again right before it deploys, "
                     "but can't lock it", needs="full-yes", resume=True, work_item=name, plan_id=pid,
                     components=everything, overwrite=sorted(moved))
    if fetch(repo) != main and out(repo, "log", "--format=%h", f"{main}..refs/remotes/origin/main", "--",
                                   *deployable(repo, "refs/remotes/origin/main")):
        write_record(team_id, name, step="recheck")
        raise failed("main moved while Scout checked the org, so nothing was deployed; once merges hold, deliver --wi "
                     f"{name} --resume --full checks it again", pending=True, resume=True, work_item=name)
    if moved:
        taken = {c: r["digest"] for c, r in moved.items()}
        backup = save_backup(team_id, name, org, taken)
        write_record(team_id, name, overwrite=dict(approved, **taken), backups=(record.get("backups") or []) + [backup])
    write_record(team_id, name, full=True, components_all=everything, full_main=main)
    token = complete(team_id, entry, item, previous, cwd, full=True, head=state["head"])
    return watch_promotion(team_id, entry, repo, item, dict(state, components=everything, target=main), token, cwd)


def ready(entry, item, cwd):
    if item["status"] == "IN_REVIEW":
        try:
            update_item(entry, item["name"], cwd, status="Ready to Promote")
        except Stop as stop:
            stop.data["resume"] = True
            raise
        item = work_item(entry, item["name"], cwd)
    if item["status"] != "READY_TO_PROMOTE":
        raise failed(f"{item['name']} is {item['status']} on the server, which a merged item waiting for its promotion "
                     "shouldn't be; look at it in Lifecycle Center, then resume", pending=True, resume=True,
                     status=item["status"])
    return item


def sync(team_id, entry, item, head, cwd):
    """Lifecycle Center records an outside merge when a validation inspects it. The proof is a validation that passes
    with the component list for the merged head in place. A list alone isn't: the hub can make one before the merge
    (measured: WI-000026's, two hours before), and then `complete` is refused."""
    write_record(team_id, item["name"], step="syncing")
    for attempt in range(SYNC_TRIES):
        stop_point(team_id, item["name"], "while syncing the merge")
        code, body, kind = devops(["promotion", "validate", "--target-stage-id", id18(entry["stage_id"]),
                                   "--work-item-id", id15(item["id"])], entry["hub"], cwd)
        progress(item["name"], "syncing", f"validation {attempt + 1} of {SYNC_TRIES} answered {kind}")
        if kind not in ("external-merges", "already-merged", "ok"):
            raise failed(f"the validation answered something unexpected: {message_of(body)[:300]}", resume=True)
        if kind == "ok" and synced(entry, item, head, cwd):
            return
        time.sleep(SYNC_WAIT)
    raise failed(f"Lifecycle Center hasn't synced {item['name']}'s merge yet; nothing was deployed. Resume later with "
                 "deliver --resume", pending=True, resume=True)


def recheck(team_id, entry, repo, item, state, record, a, cwd):
    """Just before the promotion: the org still holds the copy the pipeline delivered, or exactly the copy the captain
    approved replacing. Anything newer needs a new decision."""
    name, components = item["name"], state["components"]
    org = read_org(entry, repo, components)
    edits = direct_edits(team_id, entry, repo, state["base"], components, org, promoted_merges(entry, cwd),
                         backflow_snapshots(team_id, name))
    unreadable = {c: r for c, r in edits.items() if r["state"] == "unreadable"}
    if unreadable:
        write_record(team_id, name, step="recheck")
        raise failed("Scout couldn't read the common org's copy of " + ", ".join(unreadable) + " just before the "
                     "promotion; nothing was deployed. Resume when the org reads again", pending=True, resume=True,
                     work_item=name, edits=unreadable)
    approved = record.get("overwrite") or {}
    moved = {c: r for c, r in edits.items() if r["state"] != "same" and approved.get(c) != r["digest"]}
    if not moved:
        return
    if not a.overwrite:
        write_record(team_id, name, step="recheck")
        raise decide("the common org changed while the delivery waited; the merge stands, nothing was deployed",
                     needs="direct-edit", resume=True, work_item=name, edits=moved, choices=[
                         "overwrite it: deliver --resume --overwrite; Scout backs up the org's copy first, and a new "
                         "work item can bring the edit back from the backup",
                         "or complete the promotion in Lifecycle Center, then deliver --resume reads it back"])
    pid = plan_id(state["head"], state["merge"], state["tree"], components, {c: r["digest"] for c, r in edits.items()})
    if not a.yes or a.plan_id != pid:
        raise decide("the captain's yes to overwrite: the promotion replaces these copies in the common org, after "
                     "Scout backs them up", needs="overwrite-yes", resume=True, work_item=name, plan_id=pid, edits=moved)
    taken = {c: r["digest"] for c, r in moved.items()}
    backup = save_backup(team_id, name, org, taken)
    write_record(team_id, name, overwrite=dict(approved, **taken), backups=(record.get("backups") or []) + [backup])


def complete(team_id, entry, item, previous, cwd, full=False, head=None):
    """Submits the promotion once. An answer that's lost is looked up on the server, never resubmitted. A refusal
    submitted nothing: after EXTERNAL_MERGES_DETECTED (the merge isn't inspected yet), Scout syncs and tries once more.
    Any other answer (a timeout, a lost or unknown one) can't prove that, so the record stays at completing."""
    name = item["name"]
    for attempt in (1, 2):
        stop_point(team_id, name, "before submitting the promotion")
        known = set(read_record(team_id, name).get("tokens") or []) | visible_tokens(entry, item, cwd) | \
            ({(previous or {}).get("token")} - {None})
        write_record(team_id, name, step="completing", earlier_tokens=sorted(known))  # this attempt's history, first
        progress(name, "completing", "submitting the promotion" + (" of everything on main" if full else ""), safe=False)
        code, body, kind = devops(["promotion", "complete", "--target-stage-id", id18(entry["stage_id"]),
                                   "--work-item-id", id15(item["id"]), "--test-level", "NoTestRun",
                                   *(["--deploy-all"] if full else [])], entry["hub"], cwd)
        token = body.get("requestId") if kind == "ok" and isinstance(body, dict) else None
        if token:
            break
        found = promotion_for(entry, item, cwd)
        if found and found.get("token") and found["token"] not in known:
            token = found["token"]  # submitted, though the answer didn't say so; an earlier attempt's never counts
            break
        if kind in ("ok", "other") and "Pre-flight validation failed" not in message_of(body):
            raise failed(f"promotion complete didn't start: {message_of(body)[:300]}; resume looks at the server again",
                         resume=True)
        write_record(team_id, name, step="merged")  # refused: nothing was submitted, so nothing is waited for
        if kind == "external-merges" and attempt == 1 and head:
            sync(team_id, entry, item, head, cwd)
            continue
        if kind == "in-progress":
            raise failed("another promotion is running on this stage; resume when it has finished", pending=True, resume=True)
        raise failed(f"Lifecycle Center refused the promotion ({message_of(body)[:300]}); nothing was submitted. Resume to "
                     "try again", pending=True, resume=True)
    write_record(team_id, name, token=token, tokens=(read_record(team_id, name).get("tokens") or []) + [token], step="promoting")
    progress(name, "promoting", f"submitted as request {token}")
    return token


def watch_promotion(team_id, entry, repo, item, state, token, cwd):
    promotion = poll_promotion(team_id, entry, item, token, cwd)
    if promotion["status"] != "SUCCESS" or promotion.get("error"):
        write_record(team_id, item["name"], step="failed")
        raise failed(promotion_failed(item["name"], promotion), promotion=promotion, retry=True, full=empty_set(promotion))
    return read_back(team_id, entry, repo, item, dict(state, promoted_at=promotion.get("completed")), cwd)


def empty_set(promotion):
    return bool(EMPTY_SET.search(str((promotion or {}).get("error") or "")))


def promotion_failed(name, promotion):
    if empty_set(promotion):
        return (f"the promotion resolved no components to deploy, although {name}'s files are on main (a Lifecycle "
                "Center fault, measured for a new component whose files came in separate commits, in its UI too); a "
                "plain retry fails the same way. The stage stays blocked. A full promotion deploys everything in the "
                f"stage branch: deliver --wi {name} --resume --full checks it all against the org first, then asks for "
                "the yes")
    return (f"the promotion failed after the merge ({str(promotion.get('error') or promotion.get('status'))[:300]}); main "
            f"is ahead of the org, and the stage stays blocked. Fix the cause the error names, then deliver --wi {name} "
            f"--resume --retry; or complete the promotion in Lifecycle Center, then deliver --wi {name} --resume reads it back")


def poll_promotion(team_id, entry, item, token, cwd):
    deadline, last = time.time() + STATUS_DEADLINE, object()
    while True:
        promotion = promotion_for(entry, item, cwd) or {}
        if token and promotion.get("token") != token:
            code, body, kind = devops(["request", "status", "--request-token", token], entry["hub"], cwd)
            if kind == "ok":
                promotion = {"token": token, "status": str(body.get("status") or "").upper(), "error": body.get("errorDetails"),
                             "completed": body.get("requestCompletionDate")}
            else:  # this request can't be read just now; another attempt's record never answers for it
                promotion = {"token": token, "status": None}
        if promotion.get("status") != last:
            last = promotion.get("status")
            progress(item["name"], "promoting", f"request {token or promotion.get('token')}: {last or 'no status yet'}")
        if promotion.get("status") in TERMINAL:
            return promotion
        if time.time() > deadline:
            raise failed("the promotion hasn't finished within 30 minutes; it's never resubmitted. Resume later",
                         pending=True, resume=True, promotion=promotion)
        stop_point(team_id, item["name"], f"while request {token} ran (it goes on in Lifecycle Center)")
        time.sleep(STATUS_WAIT)


def read_back(team_id, entry, repo, item, state, cwd):
    """The org's copies against the merge: only this says verified. Then the baselines, and the pull request's
    comment, kept until GitHub takes it."""
    name, merge, components = item["name"], state["merge"], state["components"]
    if not components:  # nothing mapped is nothing read back, so never verified
        write_record(team_id, name, step="unverified")
        raise failed("the promotion finished, but Scout maps none of the merge's files to components, so there's "
                     "nothing to read back and it isn't verified. Look at the common org yourself", merge=merge[:12],
                     work_item=name)
    progress(name, "reading back", f"{len(components)} components from the common org")
    target = state.get("target") or merge  # after a full promotion: main as Scout checked it, or as it stands
    expected = team.files_at(repo, target, set(components))
    org = read_org(entry, repo, components)
    if state.get("target"):  # a full promotion deploys the stage branch as it is when it runs, so main must hold still
        drift = out(repo, "log", "--format=%h %s", f"{target}..{fetch(repo)}", "--", *deployable(repo, target)).splitlines()
        if drift:
            write_record(team_id, name, step="unverified")
            raise failed("the full promotion finished, but main moved while it ran (" + "; ".join(drift[:5]) + "), so "
                         f"Scout can't tell which copies went out. Once merges hold, deliver --wi {name} --resume --full "
                         "reads everything back against main as it stands", merge=merge[:12])
    mismatched = [c for c in components if org[c]["state"] != "present" or not same(expected.get(c) or {}, org[c]["files"])]
    if mismatched:
        write_record(team_id, name, step="unverified")
        raise failed("the platform reports success, but the org's copies don't match "
                     + ("main" if state.get("target") else "the merge") + ": " + ", ".join(mismatched), merge=merge[:12])
    for component in components:
        save_baseline(team_id, entry, component, merge, org[component]["files"])
    shown = f"all {len(components)} components on main, after a full promotion" if state.get("target") else ", ".join(components)
    warnings = tab_warnings(repo, state.get("base"), target, components)
    body = f"Verified in the common org at {target}: {shown} (Scout's read-back)." + (
        " Warning: " + "; ".join(warnings) + "." if warnings else "")
    record = read_record(team_id, name)
    owed = owed_tests(entry, repo, state, record, components, cwd)
    if owed:  # the platform ran none of them at deploy time, or nothing shows it ran them: Scout runs them now
        promotion = promotion_for(entry, item, cwd) or {}
        write_record(team_id, name, step="tests-running", promoted=merge, read_back=body, pr=state["pr"],
                     checked_against=target, checked_components=components, tests_after=owed, test_run=None,
                     warnings=warnings,
                     promoted_at=state.get("promoted_at") or promotion.get("completed") or promotion.get("at"))
        return run_owed_tests(team_id, entry, repo, item, cwd)
    write_record(team_id, name, pr=state["pr"], warnings=warnings)
    set_comment(team_id, name, body, step="verified", verified=merge)
    clear_backflow(team_id, name)
    sent = send_comment(team_id, entry, name)
    return {"work_item": name, "outcome": "verified", "merge": merge[:12], "components": components,
            "comment": "sent" if sent else "pending: GitHub didn't take it; Scout sends it again at the next team step",
            **({"warnings": warnings, "presenter": entry["common_org"].get("username")} if warnings else {})}


TAB_SETTING = re.compile(rb"<tabSettings>(.*?)</tabSettings>", re.S)


def tab_warnings(repo, base, target, components):
    """A warning for each new custom object the delivery brings (custom settings need no tab). Scout reads Git only:
    it can tell whether main gives the object a tab and a permission set that makes the tab visible, never whether
    the user who presents can see it, so until a read-back shows that, the warning asks for the permission set to be
    assigned to that user in the common org (by default the captain's user). Warnings, never a failure."""
    objects = sorted(c for c in components if c.startswith("CustomObject:") and c.endswith("__c"))
    known = {team.component_of(p) for p in paths_of(repo, [base], set(objects))} if objects and base else set()
    current = team.files_at(repo, target, set(objects) - known) if objects else {}
    new = [c for c in objects if c not in known and current.get(c)
           and not any(b"<customSettingsType>" in data for data in current[c].values())]
    if not new:
        return []
    listing = out(repo, "ls-tree", "-r", "--name-only", target, "--", team.SOURCE + "tabs",
                  team.SOURCE + "permissionsets", check=False).splitlines()
    tabs, visible = {team.component_of(p) for p in listing}, {}
    for path in listing:
        component = team.component_of(path) or ""
        if component.startswith("PermissionSet:"):
            for setting in TAB_SETTING.findall(git(repo, "show", f"{target}:{path}", binary=True).stdout):
                tab = re.search(rb"<tab>\s*([^<\s]+)\s*</tab>", setting)
                if tab and re.search(rb"<visibility>\s*(?:Visible|Available)\s*</visibility>", setting):
                    visible.setdefault(tab[1].decode("utf-8", "replace"), set()).add(component.split(":", 1)[1])
    who = "the user who presents (the captain's user, unless the team names others)"
    warnings = []  # Git shows what main holds, never who can see what: the org may hold a tab or access Git doesn't
    for component in new:
        name = component.split(":", 1)[1]
        if f"CustomTab:{name}" not in tabs:
            warnings.append(f"Git holds no tab for the new object {name}, so whether it shows in the App Launcher is "
                            f"unverified: {who} checks there, and if it's missing, the team delivers its tab and a "
                            "permission set that makes the tab visible, assigned to that user in the common org")
        elif name not in visible:
            warnings.append(f"Git holds no permission set that makes the new object {name}'s tab visible, so its "
                            f"visibility is unverified: {who} checks the App Launcher, and if it's missing, the team "
                            "delivers one, assigned to that user in the common org")
        else:
            warnings.append(f"Git gives the new object {name} a tab and a permission set that makes it visible "
                            f"({', '.join(sorted(visible[name]))}), but Scout checked Git only, not who can see it: assign "
                            f"that permission set in the common org to {who}, then check the App Launcher as that user")
    return warnings


TEST_RUN = re.compile(r"707[0-9A-Za-z]{12}(?:[0-9A-Za-z]{3})?")
RUN_GOING = {"Queued", "Preparing", "Processing", "Holding"}


def owed_tests(entry, repo, state, record, components, cwd):
    """The tests a delivery owes after its promotion: the ones the platform skipped at deploy time, or, when no record
    shows a validation that ran tests (a lost record, say), the ones a validation would have asked for. A record's
    tests count only for the revision its plan checked: a merge Scout didn't plan, merged and promoted elsewhere after
    a plan for another revision, owes the tests a validation of it would have asked for."""
    planned = bool(record.get("plan_id")) and \
        (record.get("head"), record.get("base"), record.get("tree")) == (state.get("head"), state.get("base"), state.get("tree"))
    if planned and record.get("tests_passed"):
        return []
    if planned and record.get("tests_after"):
        return list(record["tests_after"])
    if planned and (record.get("validated") or {}).get("testsRun"):
        return []
    if not any(c.startswith(("ApexClass:", "ApexTrigger:")) for c in components):
        return []
    tree = state.get("target") or state["merge"]
    classes, _, missing = suite_classes(entry, repo, tree, cwd)
    tests = sorted(set(classes) | set(package_tests(team.files_at(repo, tree, set(components)), components)))
    if missing or not tests:
        raise failed("nothing shows the tests of this Apex delivery ran, and Scout can't tell which tests it owes ("
                     + (", ".join(missing) + " don't resolve" if missing else "no suite or test class names them")
                     + "), so it isn't verified", work_item=state.get("work_item"))
    return tests


def common_still(entry, cwd):
    """The common org's selector still names the team's common org (an alias can be rebound to another org)."""
    info = team.org_info(entry["common_org"]["target"], cwd)
    if info["org_id"] != entry["common_org_id"]:
        raise refused(f"{entry['common_org']['target']} now names org {info['org_id']}, not the team's common org "
                      f"{entry['common_org_id']}; Scout won't run or read the tests there. Reconnect the common org, then resume")


def sf_time(text):
    """A Salesforce timestamp (2026-10-19T11:30:00.000+0000) as a time."""
    return team.moment(re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", str(text or "")))


def failure_choices(record):
    merge = str(record.get("promoted"))[:12]
    return ["a fix: the builder fixes it on a new work item, which the captain delivers next",
            f"or a revert: a new work item that reverts {merge} on main, delivered next",
            "or run the tests again, if the failure looks passing: deliver --resume --retry"]


def run_owed_tests(team_id, entry, repo, item, cwd):
    """The owed tests, run by Scout in the common org right after the promotion: whole classes, one asynchronous run
    with a wait, its ID recorded before anything else. Only that run counts."""
    name, record = item["name"], read_record(team_id, item["name"])
    common_still(entry, cwd)
    record = settle_promotion_time(team_id, entry, item, record, cwd)
    run_id = record.get("test_run")
    if not run_id:
        progress(name, "testing", "starting " + ", ".join(record.get("tests_after") or []) + " in the common org", safe=False)
        args = ["apex", "run", "test", "--target-org", entry["common_org"]["target"], "--test-level", "RunSpecifiedTests"]
        for test in record.get("tests_after") or []:
            args += ["--class-names", test]
        code, body = sf(args, cwd, timeout=300)  # asynchronous: the CLI answers with the run's ID at once
        body = body if isinstance(body, dict) else {}
        run_id = str(body.get("testRunId") or (body.get("summary") or {}).get("testRunId") or "")
        if not TEST_RUN.fullmatch(run_id):
            raise failed("the tests owed after the promotion didn't start in the common org (" + message_of(body)[:200]
                         + "), so it isn't verified; resume to start them again", pending=True, resume=True, work_item=name)
        record = write_record(team_id, name, test_run=run_id)
        progress(name, "testing", f"run {run_id} started")
    wait_for_run(team_id, entry, name, run_id, cwd)
    return check_test_run(team_id, entry, repo, item, record, run_id, cwd)


def settle_promotion_time(team_id, entry, item, record, cwd):
    """When the promotion finished, which a run of the owed tests must start after: from the record, else the hub's
    promotion record, else the saved request. Unknown, it stays pending: a run can't be judged against a missing time."""
    if record.get("promoted_at"):
        return record
    found = promotion_for(entry, item, cwd) or {}
    when = found.get("completed") if found.get("token") in ({record.get("token")} - {None}) or not record.get("token") else None
    if not when and record.get("token"):
        code, body, kind = devops(["request", "status", "--request-token", record["token"]], entry["hub"], cwd)
        when = body.get("requestCompletionDate") if kind == "ok" and isinstance(body, dict) else None
    if not when:
        raise failed(f"Lifecycle Center doesn't show when {item['name']}'s promotion finished yet, so a run of the owed "
                     "tests can't be judged against it; resume reads it again", pending=True, resume=True, work_item=item["name"])
    return write_record(team_id, item["name"], promoted_at=when)


def wait_for_run(team_id, entry, name, run_id, cwd):
    """Waits on Scout's own run, up to TEST_WAIT minutes. A stop request ends the wait, and --resume reads the same run."""
    deadline, last = time.time() + TEST_WAIT * 60, object()
    while True:
        jobs = query(f"SELECT Status FROM AsyncApexJob WHERE Id = {quoted(run_id)}", entry["common_org"]["target"], cwd)
        status = (jobs[0] if jobs else {}).get("Status")
        if status != last:
            last = status
            progress(name, "testing", f"run {run_id} is {status or 'not visible yet'}")
        if status not in RUN_GOING or time.time() > deadline:
            return
        stop_point(team_id, name, f"while test run {run_id} ran (it goes on in the common org)")
        time.sleep(STATUS_WAIT)


def check_test_run(team_id, entry, repo, item, record, run_id, cwd):
    """Scout's own run of the owed tests, read from the common org: only a finished run that started after the
    promotion and passed every owed class, with the org's copies still those it read back, says verified. Anything
    else says plainly that it isn't."""
    name, wanted, target = item["name"], list(record.get("tests_after") or []), entry["common_org"]["target"]
    common_still(entry, cwd)
    if not wanted:  # a run judged against no owed test proves nothing
        raise failed(f"not verified: {name}'s delivery record names no tests it owes, so run {run_id} can't prove it; "
                     "look at the run in the common org", work_item=name, test_run=run_id)
    jobs = query(f"SELECT Status, CreatedDate FROM AsyncApexJob WHERE Id = {quoted(run_id)}", target, cwd)
    if not jobs:
        raise failed(f"the common org has no test run {run_id}, so it isn't verified; resume to read it again", pending=True,
                     resume=True, work_item=name)
    job = jobs[0]
    if job.get("Status") in RUN_GOING:
        raise failed(f"the owed tests are still running in the common org (run {run_id}); it isn't verified yet. Resume to "
                     "read their results", pending=True, resume=True, work_item=name)
    started, promoted = sf_time(job.get("CreatedDate")), sf_time(record.get("promoted_at"))
    rows = query("SELECT ApexClass.Name, MethodName, Outcome, Message FROM ApexTestResult WHERE AsyncApexJobId = "
                 f"{quoted(run_id)}", target, cwd)
    ran = {(r.get("ApexClass") or {}).get("Name") for r in rows}
    problems = [f"{(r.get('ApexClass') or {}).get('Name')}.{r.get('MethodName')}: {str(r.get('Message') or r.get('Outcome'))[:160]}"
                for r in rows if r.get("Outcome") != "Pass"]
    problems += [f"{t} didn't run" for t in wanted if t not in ran]
    if job.get("Status") != "Completed":
        problems.append(f"the run ended {job.get('Status')}")
    if not started or not promoted or started < promoted:
        problems.append("the run didn't start after the promotion")
    if problems:
        text = ("not verified: tests failed in the common org after the promotion (" + "; ".join(problems[:6]) + f"). "
                f"{name}'s changes are in the common org")
        body = (f"Not verified: {name} (pull request #{record.get('pr')}): tests failed in the common org after the "
                f"promotion (run {run_id}): " + "; ".join(problems[:6]) + ". Its changes are in the common org; the fix goes "
                "on a new work item, or a revert work item undoes them.")
        set_comment(team_id, name, body, step="tests-failed", tests_failed=problems[:20], tests_failed_text=text)
        raise failed(text, work_item=name, test_run=run_id, tests_failed=problems[:20], choices=failure_choices(record),
                     comment=comment_state(team_id, entry, name))
    components = record.get("checked_components") or record.get("components") or []
    against = record.get("checked_against") or record.get("promoted")
    if not components or not against:  # copies Scout can't name can't be read again, so the run proves nothing
        write_record(team_id, name, step="unverified")
        raise failed(f"not verified: the tests passed (run {run_id}), but {name}'s delivery record doesn't say which "
                     f"copies Scout read back, so the run doesn't prove this delivery. deliver --wi {name} --resume reads "
                     "them back and runs the owed tests again", work_item=name, test_run=run_id)
    expected = team.files_at(repo, against, set(components))
    org = read_org(entry, repo, components)
    moved = [c for c in components if org[c]["state"] != "present" or not same(expected.get(c) or {}, org[c]["files"])]
    if moved:  # the run tested other copies than the ones read back
        body = (f"Not verified: {name} (pull request #{record.get('pr')}): the tests passed in the common org (run {run_id}), "
                "but its copies of " + ", ".join(moved[:8]) + " changed after Scout's read-back, so the run doesn't prove "
                "this delivery. The next delivery's checks show what changed.")
        set_comment(team_id, name, body, step="unverified", tests_moved=moved)
        raise failed("not verified: the tests passed, but the common org's copies of " + ", ".join(moved[:8]) + " changed "
                     "after the read-back, so the run doesn't prove this delivery. Look at what changed (a direct edit, or "
                     "another delivery); the next delivery's checks show it", work_item=name, test_run=run_id,
                     comment=comment_state(team_id, entry, name))
    body = (record.get("read_back") or f"Verified in the common org at {record.get('promoted')}.") + \
        f" Tests passed in the common org after the promotion: {', '.join(wanted)} (run {run_id})."
    set_comment(team_id, name, body, step="verified", verified=record.get("promoted"), tests_passed=run_id)
    clear_backflow(team_id, name)
    sent = send_comment(team_id, entry, name)
    return {"work_item": name, "outcome": "verified", "merge": str(record.get("promoted"))[:12], "tests": wanted,
            "test_run": run_id, "comment": "sent" if sent else "pending: GitHub didn't take it; Scout sends it again at the next team step",
            **({"warnings": record["warnings"], "presenter": entry["common_org"].get("username")}
               if record.get("warnings") else {})}


def next_comment(record, body):
    """The record's next comment. A Not verified report GitHub hasn't taken yet travels along in full, so a retry,
    failed or passing, never loses one (the reports are bounded where they're made)."""
    earlier = record.get("comment") or {}
    if str(earlier.get("body") or "").startswith("Not verified: ") and not earlier.get("sent"):
        body += "\n\nEarlier, and not on the pull request yet: " + earlier["body"]
    return {"pr": record["pr"], "body": body} if record.get("pr") else None


COMMENT_WAIT = 600  # seconds a comment's writer waits for a sender (two GitHub calls, 30 s each) to finish


def comment_lock(team_id, wi_name, wait=120.0):
    return file_lock(record_path(team_id, wi_name).with_suffix(".comment.lock"), wait=wait)


def set_comment(team_id, wi_name, body, **changes):
    """Writes the record's next comment, with the record's other changes, under the sender's lock, so a sender's
    acknowledgement never lands on a newer comment."""
    with comment_lock(team_id, wi_name, wait=COMMENT_WAIT) as held:
        if not held:  # nothing written: the record stays where it was, and --resume works the outcome out again
            raise failed(f"another Scout process held {wi_name}'s pull request comment for {COMMENT_WAIT // 60} minutes, "
                         "so Scout wrote nothing yet; deliver --resume finishes it from the same run", pending=True,
                         resume=True, work_item=wi_name)
        comment = next_comment(read_record(team_id, wi_name), body)
        return write_record(team_id, wi_name, **changes, **({"comment": comment} if comment else {}))


def comment_state(team_id, entry, wi_name):
    if not (read_record(team_id, wi_name).get("comment") or {}).get("pr"):
        return "none: the record names no pull request"
    return "sent" if send_comment(team_id, entry, wi_name) else \
        "pending: GitHub didn't take it; Scout sends it again at the next deliver or status"


def send_comment(team_id, entry, wi_name):
    """A delivery's verification comment on its pull request, posted once: the pull request is read first, and the
    comment goes only when that read works and doesn't find it. Anything else keeps it for the next team step."""
    with comment_lock(team_id, wi_name, wait=10.0) as held:
        if not held:  # another Scout process is sending it, or writing a newer one; it stays pending
            return False
        try:
            return post_comment(team_id, entry, wi_name)
        except Stop as stop:  # GitHub timed out or broke: the comment stays pending, the answer around it stands
            note_comment(team_id, wi_name, (read_record(team_id, wi_name).get("comment") or {}).get("body"),
                         problem=str(stop.data.get("reason"))[:200])
            return False


def note_comment(team_id, wi_name, body, **marks):
    """Marks the record's comment (sent, or its problem) only when it's still the one with this body."""
    current = read_record(team_id, wi_name).get("comment") or {}
    if body is not None and current.get("body") == body:
        write_record(team_id, wi_name, comment=dict(current, **marks))


def post_comment(team_id, entry, wi_name):
    record = read_record(team_id, wi_name)
    comment = record.get("comment")
    if not comment or comment.get("sent"):
        return True
    code, stdout, stderr = gh(["pr", "view", str(comment["pr"]), "--repo", entry["repo"], "--json", "comments"], timeout=30)
    try:  # an empty or odd answer is no read: the comment waits rather than risk a second copy
        shown = json.loads(stdout) if code == 0 else None
        bodies = [c.get("body") for c in shown["comments"]] if isinstance((shown or {}).get("comments"), list) else None
    except (ValueError, AttributeError, TypeError):
        bodies = None
    if bodies is None:
        note_comment(team_id, wi_name, comment["body"], problem=f"couldn't read #{comment['pr']}: {(stderr or stdout)[-160:]}")
        return False
    if comment["body"] not in bodies:
        code, stdout, stderr = gh(["pr", "comment", str(comment["pr"]), "--repo", entry["repo"], "--body", comment["body"]], timeout=30)
        if code:
            note_comment(team_id, wi_name, comment["body"], problem=(stderr or stdout)[-200:] or "no answer")
            return False
    note_comment(team_id, wi_name, comment["body"], sent=now())
    return True


def resend_comments(team_id, entry):
    """Verification comments GitHub didn't take earlier, oldest first, stopping at the first that still fails."""
    folder = team.cache_dir(team_id) / "deliveries"
    for path in sorted(folder.glob("WI-*.json")) if folder.exists() else []:
        try:
            comment = json.loads(path.read_text()).get("comment") or {}
        except (OSError, ValueError):
            continue
        if comment and not comment.get("sent") and not send_comment(team_id, entry, path.stem):
            return False
    return True


def unsent_comments(team_id):
    folder = team.cache_dir(team_id) / "deliveries"
    unsent = []
    for path in sorted(folder.glob("WI-*.json")) if folder.exists() else []:
        try:
            comment = json.loads(path.read_text()).get("comment") or {}
        except (OSError, ValueError):
            continue
        if comment and not comment.get("sent"):
            unsent.append({"work_item": path.stem, "pr": comment.get("pr"), "problem": comment.get("problem")})
    return unsent


# ---- back-flow: the org's copy into main, through an ordinary work item ----

def backflow_file(team_id, wi_name):
    return team.cache_dir(team_id) / "backflows" / f"{wi_name}.json"


def backflow_snapshots(team_id, wi_name):
    try:
        data = json.loads(backflow_file(team_id, wi_name).read_text())
        return {c: {p: base64.b64decode(b) for p, b in files.items()} for c, files in data["components"].items()}
    except (OSError, ValueError, KeyError):
        return {}


def clear_backflow(team_id, wi_name):
    backflow_file(team_id, wi_name).unlink(missing_ok=True)


def cmd_backflow(a):
    team_id, entry = pick(a.team)
    repo, cwd = where(entry), Path.cwd()
    if entry.get("role") != "captain":
        raise refused("only the captain starts a back-flow")
    waiting = undeployed(entry, cwd)
    if waiting:
        raise refused("a back-flow can't be delivered before the stage's undeployed merge: " +
                      "; ".join(blocked_text(w) for w in waiting))
    components = sorted(set(team.components_of(a.components)))
    org = read_org(entry, repo, components)
    missing = [c for c in components if org[c]["state"] != "present"]
    if missing:
        raise refused("the org doesn't hold " + ", ".join(missing))
    if not a.yes:
        raise decide("a back-flow work item: the org's current copies go into main through the pipeline",
                     needs="backflow-yes", components=components)
    base = fetch(repo)
    code, body, kind = devops(["work-item", "create", "--project-id", id18(entry["project_id"]), "--subject",
                               "Back-flow: the common org's copy of " + ", ".join(components), "--description",
                               describe_components(components) + f"\nBack-flow of the org's copy.\nChecked: {base}"],
                              entry["hub"], cwd)
    if kind != "ok":
        raise failed(f"the back-flow work item wasn't created: {message_of(body)[:300]}")
    name = body["workItemName"]
    update_item(entry, name, cwd, status="In Progress")
    team.write_json_atomic(backflow_file(team_id, name), {"components": {
        c: {p: base64.b64encode(b).decode() for p, b in org[c]["files"].items()} for c in components}})
    with team.CheckoutLock(repo):
        team.require_clean(repo)
        fetch(repo)
        git(repo, "checkout", "--quiet", "-B", name, f"refs/remotes/origin/{name}")
        paths = []
        for component in components:
            for path, data in org[component]["files"].items():
                (repo / path).parent.mkdir(parents=True, exist_ok=True)
                (repo / path).write_bytes(data)
                paths.append(path)
        git(repo, "add", "--", *paths)
        git(repo, "commit", "--quiet", "-m", f"{name}: back-flow of the common org's copy")
        push = git(repo, "push", "--quiet", "origin", name, check=False, timeout=120)
        team.back_to_main(repo)
        if push.returncode:
            raise failed("the back-flow's push failed", detail=(push.stderr or "")[-300:], work_item=name)
    code, body, kind = devops(["review", "create", "--work-item-name", name], entry["hub"], cwd)
    return {"work_item": name, "components": components, "review": (body or {}).get("url"),
            "next": f"deliver --wi {name}"}


# ---- status and teammates' updates ----

PEEK_RECORD = ("step", "at", "pr", "merge", "head", "plan_id", "approved", "full", "token", "tokens", "promoted",
               "promoted_at", "verified", "test_run", "tests_after", "tests_passed", "tests_failed")


def cmd_peek(a):
    """What a delivery is waiting on, as its record, the hub, the common org and GitHub show it now, with nothing
    changed: no record, status, promotion or comment is written. Each source answers for itself, so one failing read
    hides nothing else. What it means is the reader's call."""
    team_id, entry = pick(a.team)
    cwd = Path.cwd()
    record = read_record(team_id, a.wi)
    comment = record.get("comment") or {}
    out = {"work_item": a.wi, "reads_only": True,
           "record": dict({k: record[k] for k in PEEK_RECORD if record.get(k) is not None},
                          comment={k: comment.get(k) for k in ("pr", "sent", "problem")} if comment else None,
                          source="this machine's delivery record: a delivery run elsewhere, or an older team on the same "
                                 "repository, can differ from what the hub shows")}

    def look(key, read):
        try:
            out[key] = read()
        except Stop as stop:
            out[key] = {"error": str(stop.data.get("reason"))[:300]}
        except Exception as error:  # a read that broke says so; the others still answer
            out[key] = {"error": f"{type(error).__name__}: {str(error)[:200]}"}

    item = {}

    def hub():
        item.update(work_item(entry, a.wi, cwd))
        rows = query("SELECT CreatedDate, MergeRemoteReference, DevopsPipelnStgProm.Status, DevopsPipelnStgProm.CompletionDate, "
                     "DevopsPipelnStgProm.RequestInfoId, DevopsPipelnStgProm.RequestInfo.RequestToken, "
                     "DevopsPipelnStgProm.RequestInfo.Status FROM DevopsPipelnStgPromWkItem WHERE WorkItemId = "
                     f"{quoted(item['id'])} AND DevopsPipelnStgProm.PipelineStageId = {quoted(id18(entry['stage_id']))} "
                     "ORDER BY CreatedDate DESC LIMIT 1", entry["hub"], cwd)
        prom = (rows[0].get("DevopsPipelnStgProm") or {}) if rows else {}
        info = prom.get("RequestInfo") or {}
        latest = {"created": rows[0].get("CreatedDate"), "merge": rows[0].get("MergeRemoteReference"),
                  "status": prom.get("Status"), "completed": prom.get("CompletionDate"), "request": bool(prom.get("RequestInfoId")),
                  "token": info.get("RequestToken"), "request_status": info.get("Status")} if rows else None
        return {"work_item_status": item["status"], "stage_busy": stage_busy(entry, cwd),
                "latest_row": latest, "selected_promotion": promotion_for(entry, item, cwd),
                "note": "latest_row is the newest record as stored; a merge's record has neither a status nor a request "
                        "until a promotion fills it in (measured). selected_promotion is the one deliver acts on"}
    look("hub", hub)
    shown = out.get("hub") or {}
    sources = {}
    for source, token in (("record", record.get("token")), ("selected_promotion", (shown.get("selected_promotion") or {}).get("token")),
                          ("latest_row", (shown.get("latest_row") or {}).get("token"))):
        if token:
            sources.setdefault(token, []).append(source)
    out["requests"] = []

    def request(token, found_in):
        code, body, kind = devops(["request", "status", "--request-token", token], entry["hub"], cwd)
        body = body if isinstance(body, dict) else {}
        return {"token": token, "from": found_in, "kind": kind, "status": body.get("status"),
                "message": message_of(body)[:300] or None, "completed": body.get("requestCompletionDate")}
    for token, found_in in sources.items():
        try:
            out["requests"].append(request(token, found_in))
        except Stop as stop:
            out["requests"].append({"token": token, "from": found_in, "error": str(stop.data.get("reason"))[:300]})

    def tests():
        run_id, target = record["test_run"], entry["common_org"]["target"]
        jobs = query(f"SELECT Status, CreatedDate FROM AsyncApexJob WHERE Id = {quoted(run_id)}", target, cwd)
        rows = query("SELECT ApexClass.Name, MethodName, Outcome, Message FROM ApexTestResult WHERE AsyncApexJobId = "
                     f"{quoted(run_id)}", target, cwd)
        failures = [f"{(r.get('ApexClass') or {}).get('Name')}.{r.get('MethodName')}: {str(r.get('Message') or r.get('Outcome'))[:160]}"
                    for r in rows if r.get("Outcome") != "Pass"]
        return {"run": run_id, "status": (jobs[0] if jobs else {}).get("Status"), "created": (jobs[0] if jobs else {}).get("CreatedDate"),
                "results": len(rows), "passed": len(rows) - len(failures), "failures": failures[:10]}
    if record.get("test_run"):
        look("tests", tests)

    def pull_request():
        prs = pull_requests(entry, a.wi)
        pr = next((p for p in prs if p.get("number") == record.get("pr")), prs[0] if prs else None)
        if not pr:
            return None
        shown = gh_json(["pr", "view", str(pr["number"]), "--repo", entry["repo"], "--json", "comments"]) or {}
        bodies = [c.get("body") or "" for c in shown.get("comments") or []]
        return {"number": pr["number"], "state": pr.get("state"), "merge": (pr.get("mergeCommit") or {}).get("oid"),
                "scouts_comment": next((b[:200] for b in reversed(bodies) if b.startswith(("Verified in the common org at ",
                                                                                          "Not verified: "))), None)}
    look("pull_request", pull_request)
    return out


def cmd_stop(a):
    """Asks a running delivery to end at its next safe point. It never interrupts a call that changes something, and
    writes only this machine's request, which the delivery clears when it stops (or the next deliver, when none ran)."""
    team_id, entry = pick(a.team)
    if not WI_NAME.match(str(a.wi or "")):
        raise refused(f"{a.wi} isn't a work item name like WI-000012")
    path = stop_file(team_id, a.wi)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(now() + "\n")
    return {"work_item": a.wi, "stop": "requested", "note": "a running delivery ends at its next safe point and says so; "
            "deliver --resume then picks up"}


def cmd_status(a):
    team_id, entry = pick(a.team)
    cwd = Path.cwd()
    resend_comments(team_id, entry)
    rows = query("SELECT Name, Subject, Status, LastModifiedDate, LastModifiedBy.Name FROM WorkItem WHERE DevopsProjectId = "
                 f"{quoted(id18(entry['project_id']))} ORDER BY Name DESC LIMIT 25", entry["hub"], cwd)
    deliveries = []
    folder = team.cache_dir(team_id) / "deliveries"
    for path in sorted(folder.glob("WI-*.json"))[-5:] if folder.exists() else []:
        record = json.loads(path.read_text())
        deliveries.append({"work_item": path.stem, "step": record.get("step"), "merge": (record.get("merge") or "")[:12],
                           "at": record.get("at")})
    return {"team": team_id, "name": entry.get("name"), "role": entry.get("role"), "me": entry.get("me"),
            "common_org": entry["common_org"]["label"],
            "work_items": [{"name": r["Name"], "subject": r.get("Subject"), "status": r.get("Status"),
                            "by": (r.get("LastModifiedBy") or {}).get("Name"), "at": r.get("LastModifiedDate")} for r in rows],
            "deliveries": deliveries, "unsent_comments": unsent_comments(team_id), **roster(entry)}


def events_file(team_id):
    return team.cache_dir(team_id) / "lc-events.json"


def events_lock(team_id):
    return file_lock(team.cache_dir(team_id) / "lc-events.lock", wait=3.0)


def read_events(team_id):
    try:
        data = json.loads(events_file(team_id).read_text())
    except (OSError, ValueError):
        data = {}
    for key, empty in (("seen", []), ("pending", []), ("cursor", {}), ("statuses", {}), ("promotions", {}), ("prs", {}),
                       ("fetched_at", 0), ("next", 0), ("watched", 0)):
        data.setdefault(key, empty)
    return data


def wi_event(row):
    status = str(row.get("Status"))
    text = (f"{(row.get('LastModifiedBy') or {}).get('Name') or 'someone'}: {row['Name']} ({row.get('Subject')}) is now "
            f"{status.replace('_', ' ').lower()}")
    if status == "CLOSED":
        text += " (the platform finished its promotion; Scout's read-back reports verification)"
    return {"key": f"wi:{row['Name']}:{status}:{row.get('LastModifiedDate')}", "at": row.get("LastModifiedDate"), "text": text}


def promotion_event(row):
    prom = row.get("DevopsPipelnStgProm") or {}
    status, wi = str(prom.get("Status")), (row.get("WorkItem") or {}).get("Name") or "a work item"
    error = str((prom.get("RequestInfo") or {}).get("ErrorDetails") or "")[:150]
    if status == "SUCCESS":
        text = f"{wi}: the platform reports its promotion finished (Scout's read-back reports verification)"
    elif status in TERMINAL:
        text = (f"{wi}: its promotion ended {status.lower()}" + (f" ({error})" if error else "") +
                "; the stage stays blocked until the captain retries it or completes it in Lifecycle Center")
    else:
        text = f"{wi}: its promotion is running"
    return {"key": f"promotion:{row.get('DevopsPipelnStgPromId')}:{status}", "at": prom.get("LastModifiedDate"), "text": text}


def pr_event(pr):
    words = {"OPEN": "is open", "MERGED": "is merged into main", "CLOSED": "was closed without merging"}
    by = (pr.get("author") or {}).get("login") or "someone"
    return {"key": f"pr:{pr['number']}:{pr['state']}:{pr.get('updatedAt')}", "at": pr.get("updatedAt"),
            "text": f"{by}: pull request #{pr['number']} ({pr.get('headRefName')}) {words.get(pr['state'], pr['state'].lower())}: "
                    f"{str(pr.get('title'))[:120]}"}


def cmd_fetch(a):
    """Refreshes the events cache from the hub and GitHub, each source from its own cursor; the prompt hook only ever
    reads the cache. An event is a change: a work item's or a promotion's status, a pull request's state, or a
    verification comment, Verified or Not verified, which only the captain's delivery writes."""
    team_id, entry = pick(a.team)
    cwd = Path.cwd()
    data = read_events(team_id)
    cursor, joined = dict(data["cursor"]), entry.get("joined_at") or now()
    statuses, promotions, prs = dict(data["statuses"]), dict(data["promotions"]), dict(data["prs"])
    events = []
    rows = query("SELECT Name, Subject, Status, LastModifiedDate, LastModifiedBy.Name FROM WorkItem WHERE "
                 f"DevopsProjectId = {quoted(id18(entry['project_id']))} AND LastModifiedDate >= "
                 f"{soql_time(cursor.get('hub') or joined)} ORDER BY LastModifiedDate LIMIT 200", entry["hub"], cwd, timeout=60)
    for row in rows:
        if statuses.get(row["Name"]) != row.get("Status"):
            statuses[row["Name"]] = row.get("Status")
            events.append(wi_event(row))
    if rows:
        cursor["hub"] = rows[-1]["LastModifiedDate"]
    rows = query("SELECT DevopsPipelnStgPromId, WorkItem.Name, DevopsPipelnStgProm.Status, "
                 "DevopsPipelnStgProm.LastModifiedDate, DevopsPipelnStgProm.RequestInfo.ErrorDetails FROM "
                 f"DevopsPipelnStgPromWkItem WHERE DevopsPipelnStgProm.PipelineStageId = {quoted(id18(entry['stage_id']))} "
                 f"AND DevopsPipelnStgProm.LastModifiedDate >= {soql_time(cursor.get('promotions') or joined)} "
                 "ORDER BY DevopsPipelnStgProm.LastModifiedDate LIMIT 200", entry["hub"], cwd, timeout=60)
    for row in rows:
        status = (row.get("DevopsPipelnStgProm") or {}).get("Status")
        if promotions.get(str(row.get("DevopsPipelnStgPromId"))) != status:
            promotions[str(row.get("DevopsPipelnStgPromId"))] = status
            events.append(promotion_event(row))
    if rows:
        cursor["promotions"] = (rows[-1].get("DevopsPipelnStgProm") or {}).get("LastModifiedDate") or cursor.get("promotions")
    for pr in sorted(gh_list(["pr", "list", "--repo", entry["repo"], "--state", "all", "--limit", "50", "--search",
                              f"updated:>={overlap(cursor.get('prs') or joined)} sort:updated-asc", "--json",
                              "number,title,state,headRefName,updatedAt,author"]), key=lambda p: str(p.get("updatedAt"))):
        if prs.get(str(pr["number"])) != pr["state"]:
            prs[str(pr["number"])] = pr["state"]
            events.append(pr_event(pr))
        cursor["prs"] = pr.get("updatedAt") or cursor.get("prs")
    since = overlap(cursor.get("comments") or joined)  # GitHub's `since` is strict: a second's overlap, deduplicated
    for page in range(1, PAGES + 1):
        batch = gh_json(["api", f"repos/{entry['repo']}/issues/comments?since={since}&sort=updated&direction=asc"
                                f"&per_page={PER_PAGE}&page={page}"]) or []
        for comment in batch:
            body = comment.get("body") or ""
            if body.startswith(("Verified in the common org at ", "Not verified: ")):
                kind = "verified" if body.startswith("Verified") else "not-verified"
                events.append({"key": f"{kind}:{comment.get('id')}", "at": comment.get("updated_at"),
                               "text": f"{(comment.get('user') or {}).get('login')}: {body[:300]}"})
            cursor["comments"] = comment.get("updated_at") or cursor.get("comments")
        if len(batch) < PER_PAGE:
            break
    with events_lock(team_id) as held:
        if not held:  # another writer holds the cache; this refresh's events come again with the next one
            return {"fresh": 0, "pending": None, "note": "the events cache was busy; the next refresh brings these"}
        latest = read_events(team_id)  # the hook or a watcher may have changed it meanwhile
        seen = set(latest["seen"])
        fresh = [e for e in events if e["key"] not in seen]
        for event in fresh:
            latest["next"] += 1
            event["seq"] = latest["next"]
        latest["pending"] += fresh
        latest["seen"] = (latest["seen"] + [e["key"] for e in fresh])[-1000:]
        latest.update(cursor=cursor, statuses=statuses, promotions=promotions, prs=prs, fetched_at=time.time())
        team.write_json_atomic(events_file(team_id), latest)
    return {"fresh": len(fresh), "pending": len(latest["pending"])}


def spawn_fetch(team_id):
    subprocess.run(["/bin/sh", "-c", '"$0" "$@" </dev/null >/dev/null 2>&1 &', sys.executable, "-B",
                    str(Path(__file__).resolve()), "fetch", "--team", team_id], stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, timeout=10)


def cmd_updates(a):
    """The prompt hook's form reads only the cache, and starts a detached refresh when it's old. What it shows has
    reached the session, so it leaves the cache."""
    payload = {}
    if a.hook and not sys.stdin.isatty():
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except ValueError:
            payload = {}
    try:
        teams = team.load_registry()["teams"]
    except Stop:
        return None
    texts = []
    for team_id, entry in teams.items():
        if entry.get("mode") != MODE or (a.team and a.team not in (team_id, entry.get("slug"), entry.get("name"))):
            continue
        if a.hook and not team.in_scope(payload.get("cwd") or os.getcwd(), entry):
            continue
        data = read_events(team_id)
        if time.time() - float(data.get("fetched_at") or 0) > FETCH_EVERY:
            try:
                spawn_fetch(team_id)
            except (OSError, subprocess.SubprocessError):
                pass
        with events_lock(team_id) as held:
            if not held:  # a refresh is writing; these show at the next prompt
                continue
            latest = read_events(team_id)
            shown, rest = latest["pending"][:REPORT_LIMIT], latest["pending"][REPORT_LIMIT:]
            first = bool(payload.get("session_id")) and payload.get("session_id") != latest.get("session")
            unwatched = first and not team.watcher_alive(team_id)  # said once per session, as before
            if unwatched:
                latest["session"] = payload.get("session_id")
            latest["pending"] = rest
            team.write_json_atomic(events_file(team_id), latest)
        if unwatched:
            texts.append(f"No watcher is running for the {entry.get('name')} team in the background.")
        if shown:
            texts.append(f"From the {entry.get('name')} team (Lifecycle Center and GitHub), new since this machine "
                         "last showed it. Scout shows teammates' updates to the builder before its answer:\n" +
                         "\n".join("- " + e["text"] for e in shown) +
                         (f"\n({len(rest)} more follow at the next prompt.)" if rest else ""))
    if a.hook:
        if texts:
            print("\n\n".join(texts))
        return None
    return {"updates": texts}


def cmd_watch(a):
    """Blocks until the team has news, prints it and exits, so a background run wakes Scout. The events stay pending
    until Scout acknowledges them after relaying (ack), so an interrupted relay shows them again at the next prompt."""
    team_id, entry = pick(a.team)
    if os.environ.get("SCOUT_TEAM_WATCH_OFF"):  # a headless session would wait for it
        print("The team watcher is off in this session (SCOUT_TEAM_WATCH_OFF); updates arrive at each prompt instead.")
        return None
    marker = team.cache_dir(team_id) / "watcher.json"
    team.write_json_atomic(marker, {"pid": os.getpid(), "started_at": now()})
    deadline = time.time() + a.max_hours * 3600
    try:
        while time.time() < deadline:
            try:
                cmd_fetch(a)
            except Stop:
                pass
            data = read_events(team_id)
            fresh = [e for e in data["pending"] if int(e.get("seq") or 0) > int(data["watched"])][:REPORT_LIMIT]
            if fresh:
                upto = max(int(e["seq"]) for e in fresh)
                with events_lock(team_id) as held:
                    if not held:
                        time.sleep(a.interval)
                        continue
                    latest = read_events(team_id)
                    latest["watched"] = max(int(latest["watched"]), upto)
                    team.write_json_atomic(events_file(team_id), latest)
                print(f"From the {entry.get('name')} team (the background watcher):\n" +
                      "\n".join("- " + e["text"] for e in fresh) +
                      f"\nAfter relaying this to the builder, Scout runs `scout_lc.py ack --team {team_id} --upto {upto}` "
                      "and starts one new watcher.")
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


def cmd_ack(a):
    """Scout relayed a watcher's report: those events needn't show again."""
    team_id, entry = pick(a.team)
    with events_lock(team_id) as held:
        if not held:
            raise failed("the team's events cache is busy; acknowledge again in a moment", pending=True)
        latest = read_events(team_id)
        before = len(latest["pending"])
        latest["pending"] = [e for e in latest["pending"] if int(e.get("seq") or 0) > a.upto]
        team.write_json_atomic(events_file(team_id), latest)
    return {"acknowledged": before - len(latest["pending"]), "pending": len(latest["pending"])}


# ---- the command line ----

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "join"):
        p = commands.add_parser(name)
        p.add_argument("--hub", required=True)
        p.add_argument("--pipeline-id", required=True)
        p.add_argument("--common-org", required=True)
        p.add_argument("--build-org")
        p.add_argument("--checkout")
        p.add_argument("--me")
        p.add_argument("--yes", action="store_true")
        p.add_argument("--yes-guard", action="store_true", help="a joining builder's yes to Scout's guard on this machine")
        p.add_argument("--no-guard", action="store_true", help="a joining builder's no: Lifecycle Center mode works without it")
    p = commands.add_parser("package")
    p.add_argument("action", choices=["start", "check"])
    p.add_argument("--team")
    p.add_argument("--title")
    p.add_argument("--components", nargs="+")
    p.add_argument("--owner")
    p.add_argument("--wi")
    p = commands.add_parser("handover")
    p.add_argument("--team")
    p.add_argument("--wi", required=True)
    p.add_argument("--unchecked", action="store_true")
    p = commands.add_parser("deliver")
    p.add_argument("--team")
    p.add_argument("--wi", required=True)
    p.add_argument("--yes", action="store_true")
    p.add_argument("--plan-id")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--retry", action="store_true")
    p.add_argument("--full", action="store_true")
    p.add_argument("--tests-after", action="store_true")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--confirm-base", action="store_true")
    p.add_argument("--confirm-other", action="store_true")
    p = commands.add_parser("peek")
    p.add_argument("--team")
    p.add_argument("--wi", required=True)
    p = commands.add_parser("stop")
    p.add_argument("--team")
    p.add_argument("--wi", required=True)
    p = commands.add_parser("unguard")
    p.add_argument("--team")
    p.add_argument("--yes", action="store_true")
    p = commands.add_parser("backflow")
    p.add_argument("--team")
    p.add_argument("--components", nargs="+", required=True)
    p.add_argument("--yes", action="store_true")
    for name in ("status", "fetch"):
        commands.add_parser(name).add_argument("--team")
    p = commands.add_parser("updates")
    p.add_argument("--team")
    p.add_argument("--hook", action="store_true")
    p = commands.add_parser("watch")
    p.add_argument("--team")
    p.add_argument("--interval", type=int, default=120)
    p.add_argument("--max-hours", type=float, default=8)
    p = commands.add_parser("ack")
    p.add_argument("--team")
    p.add_argument("--upto", type=int, required=True)
    a = parser.parse_args(argv)
    handlers = {"start": cmd_start, "join": cmd_join, "package": cmd_package, "handover": cmd_handover,
                "deliver": cmd_deliver, "peek": cmd_peek, "stop": cmd_stop, "backflow": cmd_backflow, "status": cmd_status, "fetch": cmd_fetch,
                "unguard": cmd_unguard,
                "updates": cmd_updates, "watch": cmd_watch, "ack": cmd_ack}
    try:
        if os.name == "nt":  # team mode on Windows comes later: the locks and liveness checks here are POSIX ones
            raise refused(ON_WINDOWS)
        result = handlers[a.command](a)
    except Stop as stop:
        if a.command == "updates" and a.hook:
            return 0
        if a.command == "deliver":
            progress(a.wi, {1: "stopped", 2: "refused", 3: "waiting for a decision"}.get(stop.code, "stopped"),
                     str(stop.data.get("needs") or stop.data.get("reason"))[:160], safe=None)
        print(json.dumps(stop.data, indent=1, sort_keys=True, default=str))
        return stop.code
    if a.command == "deliver" and isinstance(result, dict):
        progress(a.wi, "done", str(result.get("outcome") or "finished"), safe=None)
    if result is not None:
        print(json.dumps(result, indent=1, default=str))
    return 0


if __name__ == "__main__":
    scout_portable.utf8_output()
    sys.exit(main())
