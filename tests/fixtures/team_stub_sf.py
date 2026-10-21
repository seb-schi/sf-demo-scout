#!/usr/bin/env python3
"""A stand-in `sf` for the team-mode tests. Orgs are folders of source files (STUB_ROOT/orgs/<target>/<path under
main/default>); `sf mp` is emulated just closely enough for scout_team.py's orchestration: baselines, the retrieve
outcomes, a checked deploy, the journal and reconcile. sf-mp itself has its own suite against real SDR."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from scout_team import SOURCE, component_of  # noqa: E402

ROOT = Path(os.environ["STUB_ROOT"])
STATE = ROOT / "sf-state.json"


def state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def save(data):
    STATE.write_text(json.dumps(data, indent=1))


def log(args):
    with open(ROOT / "sf-calls.log", "a") as handle:
        handle.write(json.dumps(args) + "\n")


def done(result=None, code=0, **error):
    body = {"status": code, "result": result} if not error else dict({"status": code, "exitCode": code}, **error)
    print(json.dumps(body))
    sys.exit(code)


def flag(args, name, many=False):
    values = [args[i + 1] for i, a in enumerate(args) if a == name and i + 1 < len(args)]
    return values if many else (values[0] if values else None)


def org_dir(target):
    return ROOT / "orgs" / target


def org_components(target, keys):
    found = {}
    base = org_dir(target)
    for path in sorted(base.rglob("*")) if base.exists() else []:
        if path.is_file():
            rel = SOURCE + path.relative_to(base).as_posix()
            key = component_of(rel)
            if key in keys:
                found.setdefault(key, {})[rel] = path.read_bytes()
    return found


def local_components(cwd, keys):
    found = {}
    for path in sorted((cwd / SOURCE).rglob("*")) if (cwd / SOURCE).exists() else []:
        if path.is_file():
            rel = path.relative_to(cwd).as_posix()
            key = component_of(rel)
            if key in keys:
                found.setdefault(key, {})[rel] = path.read_bytes()
    return found


def digest(files):
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode() + b"\0" + files[rel].replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest() if files else None


def baselines(cwd):
    try:
        return json.loads((cwd / ".mp" / "stub-baselines.json").read_text())
    except (OSError, ValueError):
        return {}


def save_baselines(cwd, data):
    (cwd / ".mp").mkdir(exist_ok=True)
    (cwd / ".mp" / "stub-baselines.json").write_text(json.dumps(data, indent=1))


# What sf mp prints for a deploy or reconcile is its describeRecord summary (packages/sf-mp/src/command.mjs), not the
# journal's whole record: no candidate revision, no timestamps. The journal file keeps the whole record.
DESCRIBE_KEYS = ("opId", "state", "checkOnly", "steward", "verified", "components", "jobId", "result", "readback", "note")


def describe(record):
    summary = {key: record.get(key) for key in DESCRIBE_KEYS}
    summary["steward"] = bool(record.get("steward"))
    if record.get("verified") is None:
        summary["verified"] = record.get("state") in ("settled-success", "reconciled-success") and not record.get("checkOnly")
    return summary


def org_id_of(target):
    return json.loads((ROOT / "orgs.json").read_text())[target]["id"]


def head_of(cwd):
    return subprocess.run(["git", "-C", str(cwd), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def during(step):
    """Runs a test's other process while this step works (once): another helper, or a teammate's machine."""
    plan = ROOT / f"during-{step}.json"
    if not plan.exists():
        return
    spec = json.loads(plan.read_text())
    plan.unlink()
    result = subprocess.run(spec["argv"], env=dict(os.environ, **spec.get("env", {})), capture_output=True, text=True)
    (ROOT / f"during-{step}-result.json").write_text(json.dumps({"code": result.returncode, "stdout": result.stdout,
                                                                 "stderr": result.stderr[-2000:]}))


def main():
    args = sys.argv[1:]
    log(args)
    cwd = Path.cwd()
    if args[:2] == ["org", "display"]:
        orgs = json.loads((ROOT / "orgs.json").read_text())
        target = flag(args, "--target-org")
        if target not in orgs:
            done(None, 1, name="NoOrgFound", message=f"No authorization information found for {target}.")
        done(dict(orgs[target], username=orgs[target].get("username", target), connectedStatus="Connected"))
    if args[:1] == ["plugins"] and len(args) >= 2 and args[1] == "install":
        data = state()
        manifest = Path(__file__).resolve().parents[2] / "packages" / "sf-mp" / "package.json"
        data["guard"] = json.loads(manifest.read_text())["version"] if Path(args[2][5:]).exists() else "?"
        save(data)
        print("installed")
        sys.exit(0)
    if args[:1] == ["plugins"]:
        version = state().get("guard") or os.environ.get("STUB_GUARD")
        print(json.dumps([{"name": "sf-mp", "version": version, "type": "user"}] if version else []))
        sys.exit(0)
    if args[:2] == ["project", "retrieve"]:
        during("project-retrieve")
        target = flag(args, "--target-org")
        keys = flag(args, "--metadata", many=True)
        outdir = cwd / flag(args, "--output-dir")
        held = org_components(target, set(keys))
        files = []
        for key in keys:
            if key not in held:
                files.append({"type": key.split(":")[0], "fullName": key.split(":", 1)[1], "state": "Failed",
                              "error": f"Entity of type '{key.split(':')[0]}' named '{key.split(':', 1)[1]}' cannot be found"})
                continue
            for rel, data in held[key].items():
                target_path = outdir / rel[len(SOURCE):]
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_bytes(data)
                files.append({"type": key.split(":")[0], "fullName": key.split(":", 1)[1], "state": "Created",
                              "filePath": str(target_path)})
        done({"files": files})
    if args[:2] == ["project", "deploy"]:
        target = flag(args, "--target-org")
        source = cwd / flag(args, "--source-dir") / "main" / "default"
        for path in sorted(source.rglob("*")):
            if path.is_file():
                dest = org_dir(target) / path.relative_to(source)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, dest)
        done({"status": "Succeeded"})
    if args[:2] == ["mp", "init"]:
        mp = cwd / ".mp"
        mp.mkdir(exist_ok=True)
        if "--guard-only" in args:
            config = json.loads((mp / "config.json").read_text())
            data = state()
            data.setdefault("guards", []).append(config["commonOrgId"])
            save(data)
            done({"role": "guard", "commonOrgId": config["commonOrgId"], "session": config["session"]})
        target = flag(args, "--target-org")
        config = {"schema": 1, "commonOrgId": org_id_of(target), "session": str(uuid.uuid4()), "authority": "lane",
                  "testLevel": "NoTestRun", "createdAt": "2026-10-18T00:00:00Z"}
        (mp / "config.json").write_text(json.dumps(config, indent=2))
        (mp / "owners.yaml").write_text("components: {}\n")
        (mp / ".gitignore").write_text("journal/\nbaselines/\nmerge/\nbackups/\nstub-baselines.json\n")
        data = state()
        data["lane"] = str(cwd)
        save(data)
        done({"session": config["session"], "testLevel": "NoTestRun", "commonOrgId": config["commonOrgId"], "role": "lane",
              "warnings": []})
    if args[:2] == ["mp", "status"]:
        data = state()
        done({"thisCheckoutIsTheLane": data.get("lane") == str(cwd), "open": data.get("open", [])})
    if args[:2] == ["mp", "retrieve"]:
        during("retrieve")
        target = flag(args, "--target-org")
        keys = flag(args, "--metadata", many=True)
        org_hold = org_components(target, set(keys))
        mine = local_components(cwd, set(keys))
        bases = baselines(cwd)
        report = []
        for key in keys:
            org, local, before = org_hold.get(key), mine.get(key), bases.get(key)
            saved = cwd / ".mp" / "merge" / key.replace(":", "_")
            if "--merged" in args:
                if not (saved / "meta.json").exists():
                    report.append({"component": key, "outcome": "refused", "detail": "no saved copy"})
                    continue
                bases[key] = json.loads((saved / "meta.json").read_text())["hash"]
                report.append({"component": key, "outcome": "merged", "detail": "recorded"})
                continue
            if not org:
                bases[key] = None
                report.append({"component": key, "outcome": "absent", "detail": "not in the org"})
            elif not local:
                for rel, data in org.items():
                    (cwd / rel).parent.mkdir(parents=True, exist_ok=True)
                    (cwd / rel).write_bytes(data)
                bases[key] = digest(org)
                report.append({"component": key, "outcome": "written", "files": sorted(org)})
            elif digest(local) == digest(org):
                bases[key] = digest(org)
                report.append({"component": key, "outcome": "matches", "detail": "your copy matches the org"})
            elif key in bases and bases[key] == digest(org):
                report.append({"component": key, "outcome": "unchanged", "detail": "the org hasn't changed"})
            else:
                anchor = next(r for r in sorted(local) if r.endswith("-meta.xml")).rsplit("/", 1)[0]
                (saved / "files").mkdir(parents=True, exist_ok=True)
                for rel, data in org.items():
                    dest = saved / "files" / rel[len(anchor) + 1:]
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
                (saved / "meta.json").write_text(json.dumps({"hash": digest(org)}))
                report.append({"component": key, "outcome": "conflict", "files": sorted(local), "saved": str(saved),
                               "detail": "your copy differs from the org's (last changed by Setup User)"})
        save_baselines(cwd, bases)
        if os.environ.get("STUB_RETRIEVE") == "drop":  # an answer that leaves a requested component out
            report = report[:-1]
        elif os.environ.get("STUB_RETRIEVE") == "odd":  # an outcome this version of Scout doesn't know
            report = [dict(r, outcome="surprise") for r in report]
        done({"orgId": org_id_of(target), "components": report}, 1 if any(r["outcome"] == "conflict" for r in report) else 0)
    if args[:2] == ["mp", "deploy"]:
        target = flag(args, "--target-org")
        keys = flag(args, "--metadata", many=True)
        mode = os.environ.get("STUB_DEPLOY", "")
        op = "op-" + uuid.uuid4().hex[:8]
        org_hold = org_components(target, set(keys))
        bases = baselines(cwd)
        stale = [k for k in keys if bases.get(k, "missing") == "missing" or bases.get(k) != digest(org_hold.get(k, {}))]
        during("deploy")
        revision = head_of(cwd)
        if mode in ("other-revision", "lost-answer-other"):  # as if HEAD had moved under sf mp before the deploy
            revision = subprocess.run(["git", "-C", str(cwd), "rev-parse", "HEAD~1"], capture_output=True, text=True).stdout.strip()
        try:
            started = json.loads((cwd / ".git" / "scout-delivery.json").read_text())["started_at"]
        except (OSError, ValueError, KeyError):
            started = "2026-10-18T00:00:00Z"
        # sf-mp's own shape: milliseconds, here within the receipt's second, the edge whole-second text misses.
        record = {"opId": op, "kind": "deploy", "components": keys, "checkOnly": "--dry-run" in args,
                  "steward": "--steward" in args, "jobId": "0Af000000000001AAA", "readback": None, "note": None,
                  "candidate": {"revision": revision}, "createdAt": started[:-1] + ".250Z",
                  "approvals": flag(args, "--approved-by", many=True)}
        if mode == "failed":
            stale = stale or ["(the stub's failure)"]
        if stale:
            record.update(state="settled-failed", result={"reasons": [f"{k} changed in the org since your baseline" for k in stale]})
        elif mode == "crash":
            data = state()
            data["open"] = [{"opId": op, "state": "dispatched"}]
            data["pending_op"] = dict(record, state="reconciled-success", readback={k: {"matches": True} for k in keys})
            save(data)
            print("killed", file=sys.stderr)
            sys.exit(137)
        elif mode == "unverified":
            record.update(state="reconciled-success", verified=False)
        elif mode == "partial-readback":  # settled, but the read-back covers only the first component
            head = local_components(cwd, set(keys))
            for key in keys:
                for rel, data in head.get(key, {}).items():
                    dest = org_dir(target) / rel[len(SOURCE):]
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
            record.update(state="settled-success", readback={keys[0]: {"matches": True}})
        elif mode == "unverified-landed":  # settled by hand without a read-back, though the deploy did land
            for key, files in local_components(cwd, set(keys)).items():
                for rel, data in files.items():
                    dest = org_dir(target) / rel[len(SOURCE):]
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
            record.update(state="reconciled-success", verified=False)
        elif mode in ("lost-answer", "lost-answer-other"):  # it deployed and settled, then the process ended unanswered
            head = local_components(cwd, set(keys))
            for key in keys:
                for rel, data in head.get(key, {}).items():
                    dest = org_dir(target) / rel[len(SOURCE):]
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
                bases[key] = digest(head.get(key, {}))
            save_baselines(cwd, bases)
            record.update(state="settled-success", readback={k: {"matches": True} for k in keys})
            journal = cwd / ".mp" / "journal"
            journal.mkdir(parents=True, exist_ok=True)
            (journal / f"{op}.json").write_text(json.dumps(record))
            print("killed", file=sys.stderr)
            sys.exit(137)
        else:
            if not record["checkOnly"]:
                head = local_components(cwd, set(keys))
                for key in keys:
                    for rel, data in head.get(key, {}).items():
                        dest = org_dir(target) / rel[len(SOURCE):]
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(data)
                    bases[key] = digest(head.get(key, {}))
                save_baselines(cwd, bases)
            record.update(state="settled-success", readback={k: {"matches": True} for k in keys} if not record["checkOnly"] else None)
        journal = cwd / ".mp" / "journal"
        journal.mkdir(parents=True, exist_ok=True)
        (journal / f"{op}.json").write_text(json.dumps(record))
        done(describe(record), 0 if record["state"] == "settled-success" else 2)
    if args[:2] == ["mp", "reconcile"]:
        data = state()
        record = data.pop("pending_op", None)
        data["open"] = []
        save(data)
        if record:
            journal = cwd / ".mp" / "journal"
            journal.mkdir(parents=True, exist_ok=True)
            (journal / f"{record['opId']}.json").write_text(json.dumps(record))
            if record["state"] == "reconciled-success":
                bases = baselines(cwd)
                head = local_components(cwd, set(record["components"]))
                for key in record["components"]:
                    for rel, data_ in head.get(key, {}).items():
                        dest = org_dir(flag(args, "--target-org")) / rel[len(SOURCE):]
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(data_)
                    bases[key] = digest(head.get(key, {}))
                save_baselines(cwd, bases)
        done({"outcome": record["state"] if record else "nothing open", "record": describe(record) if record else None})
    done(None, 1, name="Unstubbed", message="not stubbed: " + " ".join(args))


if __name__ == "__main__":
    main()
