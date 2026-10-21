#!/usr/bin/env python3
"""A stand-in `sf` for Lifecycle Center mode's tests (tests/test_scout_lc.py).

It answers in the shapes recorded live (tests/fixtures/lc_cli_shapes.json, which a test ties it to), quirks included:
an 18-character work-item ID crashes `promotion complete`; the first validation after a merge can miss the sync
(ALREADY_MERGED); a merged work item's sync is an inspection that a validation starts; a promotion records the merge
(MergeRemoteReference), failed ones too, and a successful one closes the work item; with the option `empty_set`, the
default mode resolves no components (a fault measured live) while `--deploy-all` deploys everything on main; the
org rewrites what it saves (Apex loses its trailing newline, a layout's Custom Links section gains empty columns).

Orgs are folders of source files (STUB_ROOT/orgs/<target>/<path under force-app/main/default>). The hub's records
live in STUB_ROOT/lc-state.json. "GitHub" is the local bare repository STUB_REMOTE, with pull requests in
STUB_ROOT/lc-gh.json (shared with lc_stub_gh.py). sf-mp's registry is per person (SCOUT_TEAMS_FILE names one), as
each person's machine has its own.
"""
import fnmatch
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from scout_team import SOURCE, component_of  # noqa: E402

ROOT = Path(os.environ["STUB_ROOT"])
REMOTE = Path(os.environ.get("STUB_REMOTE", ROOT / "remote.git"))
STATE, GH, MP = ROOT / "lc-state.json", ROOT / "lc-gh.json", ROOT / "mp-registry.json"
CHECKSUM = "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"
PROJECT, PIPELINE, STAGE, ENVIRONMENT = "1Qg000000000001", "1PJ000000000001", "1QV000000000001", "1Qe000000000001"
RUNNING = ("NEW", "IN_PROGRESS", "FINALIZING")


def load(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def save(path, data):
    path.write_text(json.dumps(data, indent=1))


def stamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def moment(text):
    return datetime.fromisoformat(str(text).replace("+0000", "+00:00").replace("Z", "+00:00"))


def log(args):
    with open(ROOT / "sf-calls.log", "a") as handle:
        handle.write(json.dumps(args) + "\n")


def flag(args, name, many=False):
    values = [args[i + 1] for i, a in enumerate(args) if a == name and i + 1 < len(args)]
    return values if many else (values[0] if values else None)


def ok(result):
    print(json.dumps({"status": 0, "result": result, "warnings": []}))
    sys.exit(0)


def error(message, name="Error", data=None, context="Stub"):
    body = {"name": name, "message": message, "exitCode": 1, "context": context, "status": 1, "warnings": []}
    if data:
        body["data"] = data
    print(json.dumps(body))
    sys.exit(1)


def id18(id15):
    return id15 + "".join(CHECKSUM[sum(1 << i for i, c in enumerate(id15[k:k + 5]) if c.isupper())] for k in (0, 5, 10))


def bare(*args, check=True):
    result = subprocess.run(["git", "-C", str(REMOTE), *args], capture_output=True, text=True)
    if check and result.returncode:
        raise SystemExit(f"stub git {args[0]} failed: {result.stderr}")
    return result.stdout.strip()


def state():
    return load(STATE, {"items": {}, "next": 1, "lists": [], "promotions": [], "suites": [], "options": {}})


def item_by(data, name=None, id_=None):
    for wi in data["items"].values():
        if wi["name"] == name or (id_ and wi["id"][:15] == id_[:15]):
            return wi
    return None


def prs():
    return load(GH, {"prs": [], "comments": []})


def pr_for(branch):
    return next((p for p in reversed(prs()["prs"]) if p["head"] == branch), None)


def common_id():
    return load(ROOT / "orgs.json", {}).get(os.environ.get("STUB_COMMON", "common"), {}).get("id", "")


# ---- the org's side ----

def org_dir(target):
    return ROOT / "orgs" / target


def on_save(rel, data):
    """What the platform does to a file it saves."""
    if rel.endswith(".cls"):
        return data.rstrip(b" \t\n")
    if rel.endswith(".layout-meta.xml") and b"<style>CustomLinks</style>" in data and b"<layoutColumns/>\n" not in data:
        return data.replace(b"<style>CustomLinks</style>", b"<layoutColumns/>\n        <layoutColumns/>\n        <style>CustomLinks</style>", 1)
    return data


def deploy_files(target, files):
    for rel, data in files.items():
        dest = org_dir(target) / rel[len(SOURCE):]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(on_save(rel, data))


def files_at(ref, keys):
    found = {}
    for path in bare("ls-tree", "-r", "--name-only", ref, "--", SOURCE.rstrip("/"), check=False).splitlines():
        key = component_of(path)
        if key in keys:
            found[path] = subprocess.run(["git", "-C", str(REMOTE), "show", f"{ref}:{path}"], capture_output=True).stdout
    return found


def retrieve(args):
    target, outdir = flag(args, "--target-org"), Path.cwd() / flag(args, "--output-dir")
    keys = flag(args, "--metadata", many=True)
    files = []
    held = {}
    base = org_dir(target)
    for path in sorted(base.rglob("*")) if base.exists() else []:
        if path.is_file():
            rel = SOURCE + path.relative_to(base).as_posix()
            held.setdefault(component_of(rel), []).append((rel, path))
    unreadable = state()["options"].get("retrieve_unreadable") or []
    for key in keys:
        kind, name = key.split(":", 1)
        if key in unreadable:  # the platform answers, but not with the component
            files.append({"fullName": name, "type": kind, "state": "Failed", "error": "UNKNOWN_EXCEPTION: An unexpected error occurred"})
            continue
        if key not in held:
            files.append({"fullName": name, "type": kind, "state": "Failed",
                          "error": f"Entity of type '{kind}' named '{name}' cannot be found"})
            continue
        for rel, path in held[key]:
            dest = outdir / rel[len(SOURCE):]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(path.read_bytes())
            files.append({"fullName": name, "type": kind, "state": "Changed", "filePath": str(dest)})
    ok({"done": True, "status": "Succeeded", "success": True, "files": files})


# ---- the hub's side: sf devops ----

EMPTY = ('{"errorType":"DEPLOYMENT_FAILURE","errorMessage":"No components to deploy \u2014 the resolved component set was '
         'empty. Verify that the changed metadata entries match files in the project directory."}')


def deploy_branch(target, ref):
    """--deploy-all, as the platform runs it: every file in the stage branch's package directories, less the
    repository's .forceignore, whatever Scout's own mapper makes of it (so a test sees what Scout didn't check)."""
    try:
        dirs = [d["path"].strip("/") for d in json.loads(bare("show", f"{ref}:sfdx-project.json"))["packageDirectories"]]
    except (ValueError, KeyError, TypeError):
        dirs = ["force-app"]
    ignore = [line.strip() for line in bare("show", f"{ref}:.forceignore", check=False).splitlines()
              if line.strip() and not line.startswith("#")]
    for path in bare("ls-tree", "-r", "--name-only", ref, "--", *dirs, check=False).splitlines():
        if any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(path.rsplit("/", 1)[-1], p.removeprefix("**/")) for p in ignore):
            continue
        rel = path.split("/main/default/", 1)[1] if "/main/default/" in path else path.split("/", 1)[-1]
        data = subprocess.run(["git", "-C", str(REMOTE), "show", f"{ref}:{path}"], capture_output=True).stdout
        dest = org_dir(target) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(on_save(SOURCE + rel, data))


def merge_record(data, wi, pr, deploy_all=False):
    """The promotion record the platform makes when it takes a merge in (measured: 18–20 s after each merge, with or
    without a `complete`): it names the merge and has neither a status nor a request until a promotion fills it in."""
    merge = pr["mergeCommit"]["oid"]
    left = next((p for p in data["promotions"] if p["wi"] == wi["id"] and p["merge"] == merge and not p["status"]
                 and not p["token"]), None)
    if not left:
        left = {"wi": wi["id"], "name": wi["name"], "token": None, "status": None, "id": f"1Pp{len(data['promotions']) + 1:012d}",
                "at": stamp(), "error": None, "merge": merge, "deploy_all": deploy_all}
        data["promotions"].append(left)
    return left


def promote(data, wi, wid, deploy_all=False):
    """`promotion complete`, as the platform runs it: the work item's merge deploys (with --deploy-all, everything on
    main), and the merge's record gets the promotion's status and request."""
    options = data["options"]
    if len(wid) == 18:
        error("Pre-flight validation failed. Error type: UNEXPECTED. Details: Unexpected error during validation: "
              "common.exception.SfdcSqlException: ERROR: value with length 18 too long for type character varying(15)",
              context="DevopsPromotionComplete")
    if options.get("stage_busy") or any(p["status"] in RUNNING for p in data["promotions"]):
        error("Pre-flight validation failed. Error type: PROMOTION_IN_PROGRESS. Details: A promotion is already in "
              "progress on this pipeline. Wait for it to finish before promoting.", context="DevopsPromotionComplete")
    pr = pr_for(wi["name"])
    refuse = options.get("refuse_complete", 0) > data.get("refused", 0)
    if not pr or pr["state"] != "MERGED" or wi.get("inspected_merge") != pr["mergeCommit"]["oid"] or refuse:
        data["refused"] = data.get("refused", 0) + 1
        if pr and pr.get("mergeCommit"):
            merge_record(data, wi, pr, deploy_all)
        save(STATE, data)
        error(f"Pre-flight validation failed. Error type: EXTERNAL_MERGES_DETECTED. Details: Merges detected for {wi['id']}",
              context="DevopsPromotionComplete")
    number = len(data["promotions"]) + 1
    empty = bool(options.get("empty_set")) and not deploy_all
    status = "ERROR" if options.get("promotion_fails") or empty else "SUCCESS"
    merge = pr["mergeCommit"]["oid"]
    promotion = {"wi": wi["id"], "name": wi["name"], "token": str(uuid.uuid4()), "status": status, "id": f"1Pp{number:012d}",
                 "at": stamp(), "error": (EMPTY if empty else "Deploy failed: injected") if status == "ERROR" else None,
                 "merge": merge, "deploy_all": deploy_all, "late": options.get("status_late", 0)}
    if status == "SUCCESS":
        if deploy_all:
            deploy_branch(os.environ.get("STUB_COMMON", "common"), "main")
        else:
            keys = {component_of(p) for p in bare("diff", "--name-only", f"{merge}^", merge).splitlines() if component_of(p)}
            deploy_files(os.environ.get("STUB_COMMON", "common"), files_at(merge, keys))
        wi.update(status="CLOSED", modified=stamp())
    left = next((p for p in data["promotions"] if p["wi"] == wi["id"] and p["merge"] == merge and not p["status"]
                 and not p["token"]), None)
    if left:  # the merge's record, filled in (measured, 19 Oct)
        left.update(promotion, id=left["id"])
        return left
    data["promotions"].append(promotion)
    return promotion


def devops(args):
    data = state()
    options = data["options"]
    what = args[1:3]
    if what == ["pipeline", "get"]:
        gh_repo = os.environ.get("STUB_REPO", "acme/team").split("/")
        ok({"id": id18(PIPELINE), "name": "Example project", "description": None, "isActive": True, "stages": [{
            "id": id18(STAGE), "name": "Common org", "nextStageId": None, "branchName": options.get("stage_branch", "main"),
            "repositoryName": gh_repo[1], "repositoryOwner": gh_repo[0],
            "environment": {"id": id18(ENVIRONMENT), "name": "common-org"}}],
            "connectedProjects": [{"id": id18(PROJECT), "name": "Example project"}]})
    if what == ["work-item", "create"]:
        number = data["next"]
        data["next"] += 1
        name = f"WI-{number:06d}"
        id15 = f"1fk{number:012d}"
        data["items"][name] = {"name": name, "id": id18(id15), "subject": flag(args, "--subject"),
                               "description": flag(args, "--description") or "", "status": "NEW", "modified": stamp()}
        save(STATE, data)
        ok({"success": True, "workItemId": id15, "workItemName": name, "subject": flag(args, "--subject")})
    if what == ["work-item", "update"]:
        wi = item_by(data, flag(args, "--work-item-name"))
        status = flag(args, "--status")
        if status == "In Progress":
            if wi["status"] == "NEW":
                bare("branch", wi["name"], "main", check=False)
            wi["status"] = "IN_PROGRESS"
        elif status == "Ready to Promote":
            if wi["status"] != "IN_REVIEW":
                error(f"Work item {wi['name']} can't move to Ready to Promote from {wi['status']}")
            wi["status"] = "READY_TO_PROMOTE"
        for field in ("description", "subject"):
            if flag(args, f"--{field}") is not None:
                wi[field] = flag(args, f"--{field}")
        wi["modified"] = stamp()
        save(STATE, data)
        ok({"success": True, "workItemId": wi["id"], "status": "IN_PROGRESS"})  # the measured answer, whatever the status
    if what == ["review", "create"]:
        wi = item_by(data, flag(args, "--work-item-name"))
        gh = prs()
        number = len(gh["prs"]) + 1
        gh["prs"].append({"number": number, "head": wi["name"], "base": "main", "state": "OPEN", "title":
                          f"[DevOps Center] Merge {wi['name']} to main", "mergeCommit": None, "updatedAt": stamp()[:19] + "Z",
                          "author": "stub-builder"})
        save(GH, gh)
        if options.get("list_at_review"):
            head = bare("rev-parse", f"refs/heads/{wi['name']}", check=False)
            if head:
                data["lists"].append({"wi": wi["id"], "commit": head, "name": f"WICL-{len(data['lists']) + 1:09d}"})
        wi.update(status="IN_REVIEW", modified=stamp())
        save(STATE, data)
        ok({"success": True, "url": f"https://github.com/{os.environ.get('STUB_REPO', 'acme/team')}/pull/{number}"})
    if what == ["promotion", "validate"]:
        wi = item_by(data, id_=flag(args, "--work-item-id"))
        pr = pr_for(wi["name"])
        if pr and pr["state"] == "MERGED":
            misses = options.get("sync_misses", 1)
            wi["validations"] = wi.get("validations", 0) + 1
            if wi["validations"] <= misses:
                save(STATE, data)
                error(f"Validation failed (CHANGE_REQUEST_VALIDATION): {wi['name']}: ALREADY_MERGED", context="DevopsPromotionValidate")
            if wi.get("inspected_merge") != pr["mergeCommit"]["oid"]:  # this answer starts the merge's inspection
                if not any(l["wi"] == wi["id"] and l["commit"] == pr["headRefOid"] for l in data["lists"]):
                    data["lists"].append({"wi": wi["id"], "commit": pr["headRefOid"], "name": f"WICL-{len(data['lists']) + 1:09d}"})
                wi["inspected_merge"] = pr["mergeCommit"]["oid"]
                merge_record(data, wi, pr)
                save(STATE, data)
                error(f"Validation failed (EXTERNAL_MERGES_DETECTED): Merges detected for {wi['id']}", context="DevopsPromotionValidate")
            save(STATE, data)
        ok({"success": True})
    if what == ["promotion", "complete"]:
        wid = flag(args, "--work-item-id") or ""
        wi = item_by(data, id_=wid)
        if options.get("complete_unanswered", 0) > data.get("unanswered", 0):  # lost before it reached the server
            data["unanswered"] = data.get("unanswered", 0) + 1
            save(STATE, data)
            error("socket hang up", name="Error")
        promotion = promote(data, wi, wid, deploy_all="--deploy-all" in args)
        save(STATE, data)
        if options.get("complete_crash_once") and not data.get("crashed"):  # submitted and deployed, but the answer is lost
            data["crashed"] = True
            save(STATE, data)
            error("socket hang up", name="Error")
        ok({"requestId": promotion["token"], "status": "SUBMITTED", "message": "Submitted for promotion",
            "promotedWorkitemIds": [wi["id"]], "undeployedWorkitemIds": [wid]})
    if what == ["request", "status"]:
        if options.get("request_status_fails", 0) > data.get("status_fails", 0):  # a read that fails for a while
            data["status_fails"] = data.get("status_fails", 0) + 1
            save(STATE, data)
            error("Request failed with status 503", name="Error")
        token = flag(args, "--request-token")
        promotion = next((p for p in data["promotions"] if p["token"] == token), None)
        if not promotion:
            error("The requested resource does not exist", name="NOT_FOUND")
        ok({"id": "8Mw000000000001AAA", "status": promotion["status"], "message": "Deployment completed successfully"
            if promotion["status"] == "SUCCESS" else "Deployment failed", "errorDetails": promotion["error"],
            "requestToken": token, "requestCompletionDate": promotion["at"]})
    error("not stubbed: sf " + " ".join(args), name="Unstubbed")


# ---- the hub's side: SOQL ----

def where(soql, field):
    match = re.search(rf"(?<![\w.]){re.escape(field)}\s*=\s*'([^']*)'", soql)
    return match[1] if match else None


def since(soql, field):
    match = re.search(rf"{re.escape(field)}\s*>=\s*(\S+Z)", soql)
    return moment(match[1]) if match else None


def promotion_rows(soql, data):
    """A refusal's record has neither a status nor a request (measured); with the option status_late, a submitted
    promotion shows its request but no status yet for its first reads."""
    rows = []
    if data["options"].get("rows_hidden", 0) > data.get("hidden_reads", 0):  # submitted, not visible to a query yet
        data["hidden_reads"] = data.get("hidden_reads", 0) + 1
        save(STATE, data)
        return []
    for number, p in enumerate(data["promotions"], 1):
        status = None if p.get("late") else p["status"]
        if p.get("late"):
            p["late"] -= 1
            save(STATE, data)
        info = {"RequestToken": p["token"], "Status": status, "ErrorDetails": p["error"]} if p["token"] else None
        rows.append({"Id": f"1Pw{number:012d}AAA", "DevopsPipelnStgPromId": id18(p["id"]), "CreatedDate": p["at"],
                     "MergeRemoteReference": p["merge"], "WorkItem": {"Name": p["name"]}, "wi": p["wi"],
                     "DevopsPipelnStgProm": {"Status": status, "LastModifiedDate": p["at"], "PipelineStageId": id18(STAGE),
                                             "CompletionDate": p["at"], "RequestInfoId": "8Mw000000000001AAA" if info else None,
                                             "RequestInfo": info}})
    hide_from = data["options"].get("hide_from")  # promotions from this one on aren't visible yet: their records lag
    if hide_from is not None:
        rows = rows[:hide_from]
    wi = where(soql, "WorkItemId")
    if wi:
        rows = [r for r in rows if r["wi"] == wi]
    if "(DevopsPipelnStgProm.Status != null OR DevopsPipelnStgProm.RequestInfoId != null)" in soql:
        rows = [r for r in rows if r["DevopsPipelnStgProm"]["Status"] or r["DevopsPipelnStgProm"]["RequestInfoId"]]
    elif "DevopsPipelnStgProm.Status != null" in soql:
        rows = [r for r in rows if r["DevopsPipelnStgProm"]["Status"]]
    elif "DevopsPipelnStgProm.RequestInfoId != null" in soql:
        rows = [r for r in rows if r["DevopsPipelnStgProm"]["RequestInfoId"]]
    if "DevopsPipelnStgProm.Status = 'SUCCESS'" in soql:
        rows = [r for r in rows if r["DevopsPipelnStgProm"]["Status"] == "SUCCESS"]
    if "MergeRemoteReference != null" in soql:
        rows = [r for r in rows if r["MergeRemoteReference"]]
    after = since(soql, "DevopsPipelnStgProm.LastModifiedDate")
    if after:
        rows = [r for r in rows if moment(r["DevopsPipelnStgProm"]["LastModifiedDate"]) >= after]
    if "ORDER BY CreatedDate DESC" in soql:
        rows = list(reversed(rows))
    if "LIMIT 1" in soql:
        rows = rows[:1]
    return [{k: v for k, v in r.items() if k != "wi"} for r in rows]


def query(args):
    soql, data = flag(args, "--query"), state()
    options = data["options"]
    if any(part in soql for part in options.get("silent_queries") or []):  # a success that leaves the records out
        ok({"done": True, "totalSize": 0})
    if "--use-tooling-api" in args:
        if "FROM TestSuiteMembership" not in soql:
            error("not stubbed (tooling): " + soql, name="Unstubbed")
        suite = where(soql, "ApexTestSuite.TestSuiteName")
        rows = [{"ApexClass": {"Name": c}} for c in (data.get("org_suites") or {}).get(suite, [])]
    elif "FROM DevopsEnvironment" in soql:
        rows = [{"OrgIdentifier": options.get("stage_org", common_id())}] if where(soql, "Id") == id18(ENVIRONMENT) else []
    elif "FROM WorkItemComponentList" in soql:
        wi, commit = where(soql, "WorkItemId"), where(soql, "CommitReference")
        rows = [{"Id": f"0Kf{i:015d}", "Name": l["name"], "CommitReference": l["commit"]}
                for i, l in enumerate(data["lists"]) if l["wi"] == wi and (not commit or l["commit"] == commit)]
    elif "FROM DevopsPipelnStgPromWkItem" in soql:
        rows = promotion_rows(soql, data)
    elif "FROM DevopsPipelnStgProm " in soql:
        rows = [{"Id": "1Pp000000000099AAA"}] if options.get("stage_busy") else \
            [{"Id": id18(p["id"])} for p in data["promotions"] if p["status"] in RUNNING]
    elif "FROM AsyncApexJob" in soql:  # a run lives in its org only
        run = (data.get("test_runs") or {}).get(where(soql, "Id"))
        here = run and run["org"] == orgs_id(flag(args, "--target-org"))
        status = run["status"] if here else None
        if here and run.get("going"):  # a run that takes a while
            run["going"] -= 1
            status = "Processing"
            save(STATE, data)
        rows = [{"Status": status, "CreatedDate": run["created"]}] if here else []
    elif "FROM ApexTestResult" in soql:
        run = (data.get("test_runs") or {}).get(where(soql, "AsyncApexJobId"))
        here = run and run["org"] == orgs_id(flag(args, "--target-org"))
        rows = list(run["results"]) if here and not options.get("tests_no_results") else []
    elif "FROM DevopsTestSuiteStage" in soql:
        rows = [{"TestSuite": {"Name": name}} for name in data.get("suites", [])]
    elif "FROM WorkItem" in soql:
        name = where(soql, "Name")
        items = list(data["items"].values())
        if name:
            items = [w for w in items if w["name"] == name]
        statuses = re.search(r"Status IN \(([^)]*)\)", soql)
        if statuses:
            wanted = re.findall(r"'([^']+)'", statuses[1])
            items = [w for w in items if w["status"] in wanted]
        after = since(soql, "LastModifiedDate")
        if after:
            items = sorted((w for w in items if moment(w["modified"]) >= after), key=lambda w: w["modified"])
        rows = [{"Id": w["id"], "Name": w["name"], "Subject": w["subject"], "Description": w["description"],
                 "Status": w["status"], "LastModifiedDate": w["modified"], "LastModifiedBy": {"Name": "Stub Captain"}}
                for w in items]
    else:
        error("not stubbed: " + soql, name="Unstubbed")
    ok({"records": rows, "totalSize": len(rows), "done": True})


# ---- sf-mp, per person ----

def mp(args):
    orgs = load(ROOT / "orgs.json", {})
    person = os.environ.get("SCOUT_TEAMS_FILE", "default")
    registry = load(MP, {})
    if args[:2] == ["mp", "init"]:
        org = orgs[flag(args, "--target-org")]["id"][:15]
        registry.setdefault(person, {})[org] = {"role": "guard", "lifecycleCaptain": "--lifecycle-captain" in args}
        save(MP, registry)
        if os.environ.get("SF_DATA_DIR"):  # sf-mp's own record of what it guards on this machine, in its real shape
            bound = Path(os.environ["SF_DATA_DIR"]) / "sf-mp" / "bound-orgs.json"
            record = load(bound, {"orgs": {}})
            record["orgs"][org] = {"role": "guard", "checkout": str(Path.cwd()), "boundAt": stamp(),
                                   **({"lifecycleCaptain": True} if "--lifecycle-captain" in args else {})}
            bound.parent.mkdir(parents=True, exist_ok=True)
            save(bound, record)
        ok({"role": "guard", "commonOrgId": org, "lifecycleCaptain": "--lifecycle-captain" in args, "warnings": []})
    target = flag(args, "--target-org")
    if not (registry.get(person) or {}).get(orgs[target]["id"][:15], {}).get("lifecycleCaptain"):
        error(f"only a Lifecycle Center team's captain validates against {target}", name="Refused")
    options = state()["options"]
    calls = load(ROOT / "validations.json", [])
    tests = flag(args, "--tests", many=True)
    calls.append({"tests": tests, "no_tests": "--no-tests" in args, "files": sorted(
        p.relative_to(Path.cwd()).as_posix() for p in Path.cwd().rglob("*") if p.is_file())})
    save(ROOT / "validations.json", calls)
    if options.get("validate_silent"):  # the process ends without an answer
        sys.exit(0)
    if options.get("validate_fails"):
        print(json.dumps({"status": 1, "result": {"validated": False, "testsRun": 1, "failures": ["InvoiceTest.run: injected"]}}))
        sys.exit(1)
    if options.get("deploy_runs_no_tests") and tests:  # measured 19 Oct: compiled, tests enabled, none run, no failure
        print(json.dumps({"status": 1, "result": {"validated": False, "ranNone": True, "checkOnly": True, "tests": tests,
                                                   "testsRun": 0, "jobId": "0Af000000000010AAA",
                                                   "failures": ["the platform ran none of the named tests"]}}))
        sys.exit(1)
    ok({"validated": True, "checkOnly": True, "tests": tests, "testsRun": len(tests), "jobId": "0Af000000000009AAA", "failures": []})


def run_tests(args):
    """`sf apex run test`, as the CLI answers it: one run of whole classes in the org named. Without --wait or
    --synchronous it's asynchronous: the answer is the run's ID alone, exit 0, as documented. With a wait, the summary,
    and exit 100 when a test fails. Options: tests_fail_after (classes that fail), tests_dont_start, tests_edit_org (an
    admin's edit of Invoice.cls in that org while the run goes), tests_running_reads (the run shows Processing for that
    many reads of AsyncApexJob)."""
    data = state()
    options = data["options"]
    if options.get("tests_dont_start"):
        error("The test run couldn't be started: injected", name="ApexTestRunError")
    target = flag(args, "--target-org")
    classes = flag(args, "--class-names", many=True) or flag(args, "--tests", many=True)
    failing = set(options.get("tests_fail_after") or [])
    runs = data.setdefault("test_runs", {})
    run_id = f"707{len(runs) + 1:012d}"
    results = [{"ApexClass": {"Name": c}, "MethodName": "run", "Outcome": "Fail" if c in failing else "Pass",
                "Message": "System.AssertException: injected" if c in failing else None} for c in classes]
    runs[run_id] = {"org": orgs_id(target), "status": "Completed", "created": stamp(), "results": results,
                    "going": options.get("tests_running_reads", 0)}
    save(STATE, data)
    if options.get("tests_edit_org"):
        path = org_dir(target) / "classes/Invoice.cls"
        path.write_bytes(path.read_bytes() + b"// an admin's edit during the run\n")
    if "--wait" not in args and "--synchronous" not in args:
        ok({"testRunId": run_id})
    outcome = "Failed" if any(r["Outcome"] != "Pass" for r in results) else "Passed"
    print(json.dumps({"status": 100 if outcome == "Failed" else 0, "result": {
        "summary": {"testRunId": run_id, "outcome": outcome, "testsRan": len(results)},
        "tests": [{"FullName": f"{r['ApexClass']['Name']}.run", "Outcome": r["Outcome"]} for r in results]}}))
    sys.exit(100 if outcome == "Failed" else 0)


def orgs_id(target):
    """The org a target names now (the option rebind maps a target to another org)."""
    rebound = (state()["options"].get("rebind") or {}).get(target)
    return rebound or load(ROOT / "orgs.json", {}).get(target, {}).get("id", "")


def main():
    args = sys.argv[1:]
    log(args)
    if args and args[-1] == "--json":
        args = args[:-1]
    if args[:2] == ["org", "display"]:
        orgs = load(ROOT / "orgs.json", {})
        target = flag(args, "--target-org")
        if target not in orgs:
            error(f"No authorization information found for {target}.", name="NoOrgFound")
        ok(dict(orgs[target], id=orgs_id(target), connectedStatus="Connected"))
    person = os.environ.get("SCOUT_TEAMS_FILE", "default")  # each person's machine has its own sf CLI and plugins
    if args[:2] == ["plugins", "install"]:
        installed = load(ROOT / "plugins.json", {})
        installed[person] = json.loads((Path(__file__).resolve().parents[2] / "packages" / "sf-mp" / "package.json")
                                       .read_text())["version"] if Path(args[2][5:]).exists() else "?"
        save(ROOT / "plugins.json", installed)
        print("installed")
        sys.exit(0)
    if args[:1] == ["plugins"] and os.environ.get("STUB_PLUGINS") == "fail":  # the CLI couldn't list its plugins
        print("Error: the plugin list couldn't be read", file=sys.stderr)
        sys.exit(1)
    if args[:1] == ["plugins"] and os.environ.get("STUB_PLUGINS") == "garbage":  # an answer that isn't a list
        print("{\"status\": 1}")
        sys.exit(0)
    if args[:1] == ["plugins"]:
        version = load(ROOT / "plugins.json", {}).get(person) or os.environ.get("STUB_GUARD")
        print(json.dumps([{"name": "sf-mp", "version": version, "type": "user"}] if version else []))
        sys.exit(0)
    if args[:2] in (["mp", "init"], ["mp", "validate"]):
        mp(args)
    if args[:2] == ["project", "retrieve"]:
        retrieve(args)
    if args[:2] == ["data", "query"]:
        query(args)
    if args[:3] == ["apex", "run", "test"]:
        run_tests(args)
    if args[:1] == ["devops"]:
        devops(args)
    error("not stubbed: sf " + " ".join(args), name="Unstubbed")


if __name__ == "__main__":
    main()
