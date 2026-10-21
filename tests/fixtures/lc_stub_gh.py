#!/usr/bin/env python3
"""A stand-in `gh` for Lifecycle Center mode's tests: pull requests on the local bare repository STUB_REMOTE, with
their state in STUB_ROOT/lc-gh.json (shared with lc_stub_sf.py, whose `review create` opens them). A merge is a real
squash merge onto main (or, with `--merge`, a two-parent merge commit), refused when the head moved
(`--match-head-commit`), as GitHub refuses it. A squash's subject is `--subject`, else GitHub's default: a single
commit's own subject, or the pull request's title, with " (#N)". `pr list` orders and limits as gh does (newest first,
`--limit`, or a search's `updated:>=` and `sort:updated-asc`). Comments page and filter as GitHub's REST API documents
(a strict `since`, sort, direction, per_page, page)."""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(os.environ["STUB_ROOT"])
REMOTE = Path(os.environ.get("STUB_REMOTE", ROOT / "remote.git"))
GH, STATE = ROOT / "lc-gh.json", ROOT / "lc-state.json"


def load(path=GH, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default if default is not None else {"prs": [], "comments": []}


def save(data):
    GH.write_text(json.dumps(data, indent=1))


def stamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bare(*args):
    result = subprocess.run(["git", "-C", str(REMOTE), *args], capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def tip(branch):
    return bare("rev-parse", f"refs/heads/{branch}")[1]


def flag(args, name):
    return args[args.index(name) + 1] if name in args else None


def view(pr):
    head = tip(pr["head"]) if pr["state"] == "OPEN" else pr.get("headRefOid")
    mergeable = "UNKNOWN"
    if pr["state"] == "OPEN":
        code, _, _ = bare("merge-tree", "--write-tree", "main", head)
        mergeable = "MERGEABLE" if code == 0 else "CONFLICTING"
    files = [{"path": p} for p in bare("diff", "--name-only", f"main...{head}")[1].splitlines() if p] if pr["state"] == "OPEN" else []
    return {"number": pr["number"], "state": pr["state"], "headRefName": pr["head"], "headRefOid": head,
            "baseRefName": pr["base"], "mergeCommit": pr.get("mergeCommit"), "mergeable": mergeable, "title": pr["title"],
            "url": f"https://github.com/{os.environ.get('STUB_REPO', 'acme/team')}/pull/{pr['number']}", "files": files,
            "updatedAt": pr.get("updatedAt"), "author": {"login": pr.get("author", "stub-builder")}}


def merge(data, args):
    pr = next(p for p in data["prs"] if p["number"] == int(args[2]))
    head = tip(pr["head"])
    if flag(args, "--match-head-commit") and flag(args, "--match-head-commit") != head:
        print("GraphQL: Head branch was modified. Review and try the merge again.", file=sys.stderr)
        return 1
    code, tree, err = bare("merge-tree", "--write-tree", "main", head)
    if code:
        print("Pull request is not mergeable: the merge commit cannot be cleanly created.", file=sys.stderr)
        return 1
    main_tip = tip("main")
    if "--merge" in args:  # GitHub's "Create a merge commit"
        _, merged, _ = bare("commit-tree", tree.splitlines()[0], "-p", main_tip, "-p", head, "-m",
                            f"Merge pull request #{pr['number']} from acme/{pr['head']}")
    else:
        subject = flag(args, "--subject")
        if not subject:
            commits = bare("log", "--format=%s", f"{main_tip}..{head}")[1].splitlines()
            subject = f"{commits[0] if len(commits) == 1 else pr['title']} (#{pr['number']})"
        _, merged, _ = bare("commit-tree", tree.splitlines()[0], "-p", main_tip, "-m", subject)
    bare("update-ref", "refs/heads/main", merged, main_tip)
    pr.update(state="MERGED", headRefOid=head, mergeCommit={"oid": merged}, updatedAt=stamp())
    save(data)
    return 0


def comments_page(data, path):
    """GET repos/{repo}/issues/comments: `since` keeps comments updated at or after it; pages of `per_page`."""
    query = parse_qs(urlsplit(path).query)
    rows = list(data["comments"])
    if query.get("since"):  # "only results last updated after the given time"
        rows = [c for c in rows if c["updated_at"] > query["since"][0]]
    if query.get("sort", [""])[0] == "updated":
        rows.sort(key=lambda c: (c["updated_at"], c["id"]), reverse=query.get("direction", ["asc"])[0] == "desc")
    size, page = int(query.get("per_page", ["30"])[0]), int(query.get("page", ["1"])[0])
    return rows[(page - 1) * size:page * size]


def main():
    args = sys.argv[1:]
    with open(ROOT / "gh-calls.log", "a") as handle:
        handle.write(json.dumps(args) + "\n")
    data = load()
    options = load(STATE, {}).get("options", {})
    if any(part in " ".join(args) for part in options.get("gh_silent") or []):  # a success that says nothing
        return 0
    if args[:2] == ["pr", "list"]:
        head, state = flag(args, "--head"), (flag(args, "--state") or "open").upper()
        prs = [p for p in data["prs"] if (not head or p["head"] == head) and (state == "ALL" or p["state"] == state)]
        search = flag(args, "--search") or ""
        if "sort:updated-asc" in search:
            after = search.split("updated:>=", 1)[1].split()[0] if "updated:>=" in search else ""
            prs = sorted((p for p in prs if str(p.get("updatedAt")) >= after), key=lambda p: (str(p.get("updatedAt")), p["number"]))
        else:
            prs = sorted(prs, key=lambda p: -p["number"])  # newest first, as gh lists
        print(json.dumps([view(p) for p in prs[:int(flag(args, "--limit") or 30)]]))
        return 0
    if args[:2] == ["pr", "view"]:
        if data.get("refused_views", 0) < options.get("pr_view_fails", 0):
            data["refused_views"] = data.get("refused_views", 0) + 1
            save(data)
            print("HTTP 502: Bad Gateway", file=sys.stderr)
            return 1
        number = int(args[2])
        print(json.dumps({"comments": [{"body": c["body"]} for c in data["comments"] if c.get("pr") == number]}))
        return 0
    if args[:2] == ["pr", "merge"]:
        return merge(data, args)
    if args[:2] == ["pr", "create"]:  # Scout's own pull requests (the team's rules on a protected main)
        head = flag(args, "--head")
        if not tip(head):
            print(f"pull request create failed: GraphQL: Head sha can't be blank, No commits between main and {head}",
                  file=sys.stderr)
            return 1
        number = len(data["prs"]) + 1
        data["prs"].append({"number": number, "head": head, "base": flag(args, "--base") or "main", "state": "OPEN",
                            "title": flag(args, "--title"), "mergeCommit": None, "updatedAt": stamp(),
                            "author": "stub-captain"})
        save(data)
        print(f"https://github.com/{os.environ.get('STUB_REPO', 'acme/team')}/pull/{number}")
        return 0
    if args[:2] == ["pr", "comment"]:
        if data.get("refused_comments", 0) < options.get("comment_fails", 0):
            data["refused_comments"] = data.get("refused_comments", 0) + 1
            save(data)
            print("error connecting to api.github.com", file=sys.stderr)
            return 1
        at = stamp()
        data["comments"].append({"id": len(data["comments"]) + 1, "pr": int(args[2]), "body": flag(args, "--body"),
                                 "user": {"login": "stub-captain"}, "created_at": at, "updated_at": at})
        lost = data.get("lost_answers", 0) < options.get("comment_answer_lost", 0)  # posted, but the answer never came
        data["lost_answers"] = data.get("lost_answers", 0) + (1 if lost else 0)
        save(data)
        if lost:
            print("stream error: stream ID 3; INTERNAL_ERROR", file=sys.stderr)
            return 1
        return 0
    if args[:1] == ["api"] and "/issues/comments" in args[1]:
        print(json.dumps(comments_page(data, args[1])))
        return 0
    print("not stubbed: gh " + " ".join(args), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
