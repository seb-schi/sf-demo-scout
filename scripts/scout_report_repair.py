"""Bounded, opt-in existing-report filter repair. No general workflow engine.

Local receipts prove input consistency, not exhaustive natural-language coverage.
The caller reviews request coverage and unresolved legacy work before inspection.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

import scout_portable
from scout_report_xml import LIMIT, RepairError, candidate, selected_value, signature, xml

ASSETS = Path(__file__).resolve().with_name("build-assets.py")
ERRORS = (RepairError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError)
RELEASED = {"applied", "already_satisfied", "not_applied", "released_unverified"}
NO_LAUNCH_ERRORS = {"NothingToDeploy", "SourceConflictError"}
RELEASE_HOLD_SECONDS = 10 * 60
# Flags Windows lacks are 0 there, where an explicit link check stands in; O_BINARY keeps its bytes exact.
NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
NONBLOCK = getattr(os, "O_NONBLOCK", 0)
BINARY = getattr(os, "O_BINARY", 0)


def code_span(value):
    """Keep interpolated receipt data in one code span, even with backticks/newlines."""
    value = str(value).replace('\r', r'\r').replace('\n', r'\n')
    delimiter = '`' * (1 + max((len(run) for run in re.findall(r'`+', value)), default=0))
    return delimiter + ' ' + value + ' ' + delimiter


def checkpoint_marker(task):
    return f"<!-- scout-repair:{task.name} -->"


def linked(part: Path) -> bool:
    """A symlink, or on Windows also a junction or another name-surrogate link, which is_symlink() doesn't report.
    A cloud file or folder, such as OneDrive's, is a reparse point too, but no link, so it counts as plain."""
    if part.is_symlink():
        return True
    if not scout_portable.windows():
        return False
    try:
        return scout_portable.is_link(os.lstat(part))
    except OSError:
        return False


def path(value: str | Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute() or ".." in candidate.parts:
        raise RepairError("use an absolute path without parent traversal")
    for part in (candidate, *candidate.parents):
        if linked(part):
            raise RepairError("symlink paths are not supported")
    return candidate


def read(file: Path) -> bytes:
    file = path(file)  # on Windows, where O_NOFOLLOW is missing, this is the link check
    try:
        descriptor = os.open(file, os.O_RDONLY | NOFOLLOW | NONBLOCK | BINARY)
    except PermissionError:
        if os.path.isdir(file):  # Windows opens no folder; elsewhere the check below refuses one
            raise RepairError("expected a bounded regular file") from None
        raise
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
            raise RepairError("expected a bounded regular file")
        chunks, size = [], 0
        while size <= LIMIT:
            chunk = os.read(descriptor, min(65536, LIMIT + 1 - size))
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
            size += len(chunk)
        raise RepairError("expected a bounded regular file")
    finally:
        os.close(descriptor)


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RepairError("duplicate JSON key")
        result[key] = value
    return result


def decode(content: bytes | str):
    return json.loads(content, object_pairs_hook=unique_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(RepairError("nonfinite JSON")))


def json_read(file: Path):
    return decode(read(file))


def write(file: Path, content: bytes, *, exclusive: bool = False) -> None:
    file = path(file)
    mode = stat.S_IMODE(file.stat().st_mode) if not exclusive and file.exists() else None
    descriptor, temporary = tempfile.mkstemp(prefix=".repair-", dir=file.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            if mode is not None:
                fchmod = getattr(os, "fchmod", None)
                if fchmod is not None:
                    fchmod(stream.fileno(), mode)
                else:
                    os.chmod(temporary, mode)  # Windows before Python 3.13 has no fchmod
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            os.link(temporary, file)  # Publish complete bytes atomically, never overwrite.
        else:
            scout_portable.replace(temporary, file)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    if scout_portable.windows():
        return  # Windows can't open a folder to fsync it, so there the file's own fsync is what there is
    directory = os.open(file.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def save(file: Path, value, *, exclusive: bool = False) -> None:
    write(file, (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(),
          exclusive=exclusive)


def text(value: str, label: str, maximum: int = 8192) -> str:
    """A non-empty, bounded string that every platform can pass on. A lone surrogate is refused here: macOS and Linux
    can't put it in a command line or a UTF-8 file, and Windows would pass it on to the next command."""
    if not isinstance(value, str) or not value or len(value) > maximum or "\x00" in value:
        raise RepairError("invalid " + label)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise RepairError("invalid " + label) from None
    return value


def org_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"00D[A-Za-z0-9]{12}(?:[A-Z0-5]{3})?", value):
        raise RepairError("identity response lacks a valid Salesforce org ID")
    short = value[:15]
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"
    suffix = "".join(alphabet[sum(1 << i for i, char in enumerate(short[start:start + 5])
                                   if char.isupper())] for start in (0, 5, 10))
    full = short + suffix
    if len(value) == 18 and value != full:
        raise RepairError("invalid org ID checksum")
    return full


def report_paths(member: str) -> tuple[str, str]:
    if not isinstance(member, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*/[A-Za-z][A-Za-z0-9_]*", member):
        raise RepairError("only an exact Folder/Report API name is supported")
    return "reports/" + member + ".report-meta.xml", "reports/" + member.split("/")[0] + ".reportFolder-meta.xml"


def assets(operation: str, **flags) -> dict:
    command = [sys.executable, "-B", str(ASSETS), operation]
    for name, value in flags.items():
        command.extend(["--" + name.replace("_", "-"), str(value)])
    result = subprocess.run(command, capture_output=True, stdin=subprocess.DEVNULL, timeout=30)
    if result.returncode != 0:
        raise RepairError("workspace/snapshot helper rejected " + operation)
    return decode(result.stdout)

class Salesforce:
    """Explicit-target CLI adapter, with durable stdout for the only write call."""

    def __init__(self, executable="sf"):
        self.executable = shutil.which(executable)
        if not self.executable:
            raise RepairError("Salesforce CLI is unavailable")

    def run(self, args, cwd, *, accept_error=False, receipt=None):
        try:  # on Windows, through the CLI's Node entry, so cmd.exe never re-parses these arguments
            command = scout_portable.sf_command(self.executable, [*args, "--json"])
        except ValueError as error:
            raise RepairError(str(error)) from error
        if receipt is None:
            result = subprocess.run(command, cwd=cwd, stdin=subprocess.DEVNULL,
                                    capture_output=True, timeout=75)
            output = result.stdout
        else:
            # The child writes directly to a private durable receipt, so a host
            # interruption after its response does not lose a returned job ID.
            descriptor = os.open(path(receipt), os.O_WRONLY | os.O_CREAT | os.O_EXCL | BINARY, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                try:
                    result = subprocess.run(command, cwd=cwd, stdin=subprocess.DEVNULL,
                                            stdout=stream, stderr=subprocess.PIPE, timeout=75)
                finally:
                    stream.flush()
                    os.fsync(stream.fileno())
            output = read(receipt)
        if len(output) > LIMIT:
            raise RepairError("CLI response exceeds the repair limit")
        try:
            envelope = decode(output)
        except ValueError as error:
            raise RepairError("CLI returned no usable JSON; inspect the saved receipt") from error
        if not isinstance(envelope, dict):
            raise RepairError("CLI returned an invalid envelope")
        if not accept_error and (result.returncode != 0 or envelope.get("status") != 0):
            # Error text can contain credentials or private data; retain the local
            # deploy receipt, but expose only a bounded error class here.
            name = str(envelope.get("name", "CLI error"))
            raise RepairError("CLI operation failed: " + (name if re.fullmatch(r"[\w:.-]{1,100}", name) else "CLI error"))
        payload = envelope.get("result")
        if not isinstance(payload, dict):
            raise RepairError("CLI response lacks its result; inspect saved launch evidence")
        return payload

    def identity(self, selector, cwd):
        raw = self.run(["org", "display", "--target-org", selector], cwd)
        target = {"org_id": org_id(raw.get("id")), "username": text(raw.get("username"), "username", 255)}
        self.check_identity(target, cwd)
        return target

    def check_identity(self, target, cwd):
        raw = self.run(["data", "query", "--target-org", target["username"],
                        "--query", "SELECT Id FROM Organization"], cwd)
        records = raw.get("records")
        if (not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict)
                or org_id(records[0].get("Id")) != target["org_id"]):
            raise RepairError("authenticated org identity differs from the binding")

    def retrieve(self, target, member, project):
        result = self.run(["project", "retrieve", "start", "--target-org", target,
                           "--metadata", "Report:" + member,
                           "--metadata", "ReportFolder:" + member.split("/")[0], "--wait", "1"], project)
        if result.get("status") != "Succeeded":
            raise RepairError("retrieval did not establish report and folder state")
        return result

    def deploy(self, target, member, project, receipt):
        raw = self.run(["project", "deploy", "start", "--target-org", target,
                        "--metadata", "Report:" + member, "--async"], project, receipt=receipt)
        return job_id(raw.get("id"))

    def report(self, target, job, project):
        # sf 2.150.6 report.js prefers the cached org over --target-org. Check
        # the exact cache entry without changing it or accepting an alias there.
        cache = Path.home() / ".sf/deploy-cache.json"
        if cache.exists():
            entries = json_read(cache.resolve())
            if not isinstance(entries, dict):
                raise RepairError("malformed deployment cache")
            for key, value in entries.items():
                if key[:15] == job[:15]:
                    if not isinstance(value, dict):
                        raise RepairError("malformed deployment cache entry")
                    if value.get("target-org") not in (None, target):
                        raise RepairError("deployment cache overrides the bound username; reconcile its provenance")
        raw = self.run(["project", "deploy", "report", "--target-org", target,
                        "--job-id", job], project, accept_error=True)
        return {k: raw.get(k) for k in ("id", "done", "success", "status", "checkOnly",
                                        "numberComponentsTotal", "details", "createdDate")}


def job_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"0Af[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?", value):
        raise RepairError("no attributable deployment job ID; reconcile before retry")
    return value


def diagnostic(error):
    if isinstance(error, RepairError):
        return str(error)
    if isinstance(error, OSError):
        return f"{type(error).__name__}: {error.filename or 'local I/O/subprocess failed'}"
    return type(error).__name__ + ": response or task evidence unavailable"


def outcome(state):
    mutation, acceptance = state["mutation"], state["acceptance"]
    if mutation == "not_applied":
        return "not_applied"
    if acceptance == "passed":
        return "applied" if mutation == "succeeded" else "already_satisfied"
    if mutation != "not_attempted":
        return "released_unverified" if state.get("release_evidence") else "unverified"
    return "blocked" if state.get("error") else "ready"


@contextmanager
def locked(file):
    try:
        with scout_portable.lock(path(file)):
            yield
    except BlockingIOError as error:
        raise RepairError("another repair process holds this lock") from error


class Repair:
    def __init__(self, adapter):
        self.adapter, self.task = adapter, None

    def workspace(self, contract):
        return assets("prepare-workspace", workspace_root=contract["workspace"],
                      customer_dir=contract["customer"], writer="scout2-repair")

    def fetch(self, contract, owned=None):
        owned = self.workspace(contract) if owned is None else owned
        self.adapter.retrieve(contract["target"]["username"], contract["member"], Path(owned["project_root"]))
        for name, relative, kind in zip(("report", "folder"), report_paths(contract["member"]), ("Report", "ReportFolder")):
            content = read(Path(owned["source_root"]) / relative)
            signature(xml(content, kind))
            owned[name + "_sha256"] = digest(content)
        return owned

    def contents(self, contract, owned):
        verified = assets("verify-workspace", project_root=owned["project_root"])
        if verified["workspace_root"] != contract["workspace"] or verified["customer_dir"] != contract["customer"]:
            raise RepairError("source ownership differs from the bound customer")
        result = tuple(read(Path(verified["source_root"]) / p) for p in report_paths(contract["member"]))
        if any(digest(content) != owned[key + "_sha256"] for key, content in zip(("report", "folder"), result)):
            raise RepairError("saved source evidence was modified")
        return result

    def same(self, contract, current, *, proposed=False):
        before = list(self.contents(contract, contract["baseline"]))
        if proposed:
            before[0], _ = candidate(before[0], contract["delta"])
        now = self.contents(contract, current)
        return all(signature(xml(a, kind)) == signature(xml(b, kind))
                   for a, b, kind in zip(before, now, ("Report", "ReportFolder")))

    def checkpoint(self, task, contract, state, *, first=False):
        state.update(outcome=outcome(state), updated_at=datetime.now(timezone.utc).isoformat())
        log = path(state["log"])
        if log.parent != task.parent.parent:
            raise RepairError("change log escaped customer directory")
        marker, end = checkpoint_marker(task), f"<!-- /scout-repair:{task.name} -->"
        final = state["outcome"] in RELEASED or (state["outcome"] == "blocked" and not (task / "launch.json").exists())
        title = state["outcome"] if final else "PENDING — component repair"
        if title == "released_unverified":
            title = "unverified — released by operator"
        pin = state.get("original", {})
        relative = report_paths(contract["member"])[0]
        remaining = ("resolved; start a new task for further changes" if state["outcome"] in RELEASED
                     else state.get("error", "verify or reconcile before deciding next steps; never replay blindly"))
        target, delta = contract["target"], contract["delta"]
        change = (f"{code_span(delta['column'])} {code_span(delta['operator'])}: "
                  f"{json.dumps(delta['before'], ensure_ascii=False)} → {json.dumps(delta['after'], ensure_ascii=False)}")
        # Status grammar is helper-owned; its pending placeholders must stay visible.
        status = lambda value: value if value == 'pending' else code_span(value)
        row = (f"{marker}\n### {title}\n"
               f"- **Attempt / org / exact component:** {code_span(task.name)}; {code_span(target['username'])} ({code_span(target['org_id'])}); {code_span('Report:' + contract['member'])}\n"
               f"- **Requested delta / exclusions:** {change}; all other report metadata and folder sharing unchanged; no defaults writes\n"
               f"- **Classification / source:** Report and ReportFolder: {'existing' if contract.get('baseline') else 'unknown'}; {code_span(contract['baseline']) if 'baseline' in contract else 'pending'}\n"
               f"- **First pre-edit artifact / source / members:** {code_span(pin['artifact']) if 'artifact' in pin else status(state['recovery'])}; {code_span(str(pin.get('artifact', '')) + '/source/' + relative)}; {code_span(relative)}; verification: {status(state['recovery'])}\n"
               f"- **Outcome / read-back:** {'blocked — not_applied (confirmed unchanged)' if title == 'not_applied' else title}; mutation={status(state['mutation'])}; acceptance={status(state['acceptance'])}; {code_span(state['readback']) if 'readback' in state else 'pending'}\n"
               f"- **Receipts / remaining action:** {code_span(task / 'result.json')}; {code_span(task / 'deploy-start.json')}; {code_span(state.get('job_id'))}; {code_span(remaining)}\n"
               + (f"- **Operator release evidence:** {code_span(state['release_evidence'])}; result remains unverified\n"
                  if state.get("release_evidence") else "") +
               f"- **Rollback:** verify the pinned component-preedit receipt, stage only {code_span(relative)}, re-bind target and read back; never restore from a later retrieve\n"
               f"{end}\n")
        with locked(log.with_suffix(log.suffix + ".lock")):
            old = read(log).decode()  # missing/moved log blocks before any launch
            starts = list(re.finditer(r'^' + re.escape(marker) + r'\r?$', old, re.M))
            ends = list(re.finditer(r'^' + re.escape(end) + r'\r?$', old, re.M))
            if starts:
                if len(starts) != 1 or len(ends) != 1 or ends[0].start() < starts[0].end():
                    raise RepairError("ambiguous repair checkpoint in change log")
                start, finish = starts[0].start(), ends[0].end()
                updated = old[:start] + row.rstrip("\n") + old[finish:]
            elif first:
                updated = old + "\n" + row
            else:
                raise RepairError("repair checkpoint missing from change log")
            write(log, updated.encode())
        save(task / "result.json", state)  # only after the mandatory human checkpoint

    def inspect(self, workspace, customer, selector, member, delta, request, reference,
                coverage_note="", history_note="", change_log=None, previous_task=None):
        workspace, customer = path(workspace), path(customer)
        report_paths(member)
        for key in ("column", "operator"):
            text(delta[key], key)
        for key in ("before", "after"):
            if not isinstance(delta[key], str) or len(delta[key]) > 8192:
                raise RepairError("invalid filter value")
        source = read(request)
        if not source.strip():
            raise RepairError("request source is empty")
        contract = {"schema_version": 2, "workspace": str(workspace), "customer": str(customer),
                    "selector": text(selector, "selector"), "target": self.adapter.identity(selector, workspace),
                    "member": member, "delta": delta, "request_sha256": digest(source),
                    "request_reference": text(reference, "reference"), "coverage_note": coverage_note,
                    "history_note": history_note, "previous_task": str(previous_task) if previous_task else None}
        owned = self.workspace(contract)
        parent = path(customer / ".scout-tasks")
        parent.mkdir(mode=0o700, exist_ok=True)
        task = self.task = Path(tempfile.mkdtemp(prefix="repair-", dir=parent))
        contract["task"] = str(task)
        logs = sorted(customer.glob("changes-*.md"))
        log = path(change_log) if change_log else (logs[-1] if logs else customer / ("changes-" + datetime.now().astimezone().strftime("%Y-%m-%d-%H%M-") + customer.name + ".md"))
        if log.parent != customer:
            raise RepairError("change log must be in the selected customer directory")
        if not log.exists():
            write(log, ("# Change Log — " + customer.name + "\n").encode(), exclusive=True)
        state = {"task": str(task), "log": str(log), "mutation": "not_attempted",
                 "acceptance": "pending", "recovery": "not_needed", "job_id": None}
        state['checkpoint_marker'] = checkpoint_marker(task)
        state['requirements'] = [f"Record the exact line {checkpoint_marker(task)} in the Scout task record before apply-report."]
        write(task / "request.md", source, exclusive=True)
        save(task / "result.json", state)
        try:
            self.checkpoint(task, contract, state, first=True)
            contract["baseline"] = self.fetch(contract, owned)
            candidate(self.contents(contract, contract["baseline"])[0], delta)
            save(task / "contract.json", contract, exclusive=True)
            state["digest"] = digest(read(task / "contract.json"))
            self.checkpoint(task, contract, state)
        except ERRORS as error:
            self.record_error(task, contract, state, error)
            raise
        return task

    def load(self, task, expected):
        task = self.task = path(task)
        if task.parent.name != ".scout-tasks":
            raise RepairError("invalid task directory")
        contract_bytes = read(task / "contract.json")
        state, contract = json_read(task / "result.json"), decode(contract_bytes)
        if not isinstance(state, dict) or not isinstance(contract, dict):
            raise RepairError("invalid task/contract shape")
        if contract.get("schema_version") != 2:
            raise RepairError("earlier preview task: retain its evidence and reconcile manually before starting a linked task")
        if (digest(contract_bytes) != expected or state.get("digest") != expected
                or contract["task"] != str(task) or state["task"] != str(task)
                or contract["customer"] != str(task.parent.parent)
                or digest(read(task / "request.md")) != contract["request_sha256"]):
            raise RepairError("stale or modified task/request contract")
        return contract, state

    def record_error(self, task, contract, state, error):
        state.pop("release_evidence", None)  # a failed finalization has not released the guard
        state["error"] = diagnostic(error)
        if (task / "launch.json").exists() and state["mutation"] == "not_attempted":
            state["mutation"] = "attempted_unknown"
        if (task / "launch.json").exists():
            state["acceptance"] = "unverified"
        state["outcome"] = outcome(state)
        try:
            self.checkpoint(task, contract, state)
        except ERRORS:
            state["log_error"] = "checkpoint could not be updated; restore the named log before continuing"
            save(task / "result.json", state)

    @contextmanager
    def component_guard(self, task, contract):
        directory = path(Path(contract["workspace"]) / ".scout-repair-locks")
        directory.mkdir(mode=0o700, exist_ok=True)
        key = contract["target"]["org_id"] + "-" + digest(contract["member"].encode())
        pointer = directory / (key + ".json")
        with locked(directory / (key + ".lock")):
            if pointer.exists():
                old = path(json_read(pointer)["task"])
                if old != task:
                    if not old.is_relative_to(Path(contract["workspace"]) / "orgs") or not old.is_dir():
                        raise RepairError("previous task evidence is missing; restore it before reconciliation")
                    if (old / "launch.json").exists():
                        resolution = json_read(old / "resolution.json") if (old / "resolution.json").exists() else {}
                        if resolution.get("outcome") not in RELEASED:
                            raise RepairError("another repair has an unresolved write; use reconcile-report, or its --release-evidence route after operator review")
            save(pointer, {"task": str(task)})
            yield

    def original(self, task, contract, *, create=False):
        pin_file = task / "original.json"
        relative = report_paths(contract["member"])[0]
        if not pin_file.exists():
            if not create:
                raise RepairError("first original is missing; never reconstruct it after a write")
            receipt = assets("preserve", source_root=contract["baseline"]["source_root"],
                             rollback_dir=contract["baseline"]["rollback_dir"], kind="component-preedit", path=relative)
            save(pin_file, {"artifact": receipt["artifact"], "sha256": contract["baseline"]["report_sha256"],
                            "receipt_sha256": digest(read(Path(receipt["artifact"]) / "receipt.json"))}, exclusive=True)
        pin = json_read(pin_file)
        artifact = path(pin["artifact"])
        if not artifact.is_relative_to(Path(contract["customer"]) / "rollback/component-preedit"):
            raise RepairError("original artifact escaped customer recovery directory")
        assets("verify", artifact=artifact)
        if (digest(read(artifact / "receipt.json")) != pin["receipt_sha256"]
                or digest(read(artifact / "source" / relative)) != pin["sha256"]):
            raise RepairError("first original changed")
        return pin

    def apply(self, task, expected):
        with locked(path(task) / ".lock"):
            contract, state = self.load(task, expected)
            with self.component_guard(task, contract):
                if (task / "launch.json").exists() or state["outcome"] != "ready":
                    raise RepairError("verify/reconcile this task; never replay a write")
                try:
                    self.adapter.check_identity(contract["target"], Path(contract["workspace"]))
                    current = self.fetch(contract)
                    if not self.same(contract, current):
                        raise RepairError("report or folder changed since inspection")
                    proposed, already = candidate(self.contents(contract, contract["baseline"])[0], contract["delta"])
                    if already:
                        state.update(acceptance="passed", readback=current)
                        self.checkpoint(task, contract, state)
                        self.resolve(task, expected, state)
                        return state
                    state.update(original=self.original(task, contract, create=True), recovery="verified")
                    owned = self.workspace(contract)
                    destination = Path(owned["source_root"]) / report_paths(contract["member"])[0]
                    destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                    write(destination, proposed, exclusive=True)
                    state["write_project"] = owned
                    self.adapter.check_identity(contract["target"], Path(contract["workspace"]))
                    assets("verify-workspace", project_root=owned["project_root"])
                    if read(destination) != proposed:
                        raise RepairError("staged report changed")
                    self.checkpoint(task, contract, state)  # fail here before durable launch intent
                    save(task / "launch.json", {"digest": expected, "started_at": datetime.now(timezone.utc).isoformat()}, exclusive=True)
                    state["mutation"] = "attempted_unknown"
                    save(task / "result.json", state)
                    state["job_id"] = self.adapter.deploy(contract["target"]["username"], contract["member"],
                                                          Path(owned["project_root"]), task / "deploy-start.json")
                    state["mutation"] = "job_recorded"
                    self.checkpoint(task, contract, state)
                    return state
                except ERRORS as error:
                    self.record_error(task, contract, state, error)
                    raise

    def resolve(self, task, expected, state):
        save(task / "resolution.json", {key: state.get(key) for key in
             ("outcome", "mutation", "acceptance", "job_id", "readback", "release_evidence")}
             | {"digest": expected}, exclusive=True)

    def reconciliation_gate(self, task, expected, release_evidence):
        contract, state = self.load(task, expected)
        if (task / "resolution.json").exists():
            resolution = json_read(task / "resolution.json")
            raise RepairError(f"resolved ({resolution['outcome']}); start a new task"
                              + ("; nothing to release" if release_evidence else ""))
        if state.get("outcome") == "released_unverified":
            # A host interruption can fall between checkpoint and resolution.
            # Only resolution releases the guard; reconcile uncertainty again.
            state.pop("release_evidence", None)
            state["outcome"] = "unverified"
        if release_evidence and not (task / "launch.json").exists() and state.get("outcome") != "unverified":
            return contract, dict(state, action="nothing to release")
        return contract, state

    def reconcile(self, task, expected, job=None, job_evidence=None, release_evidence=None):
        task = path(task)
        _, state = self.reconciliation_gate(task, expected, release_evidence)
        if state.get("action") == "nothing to release":
            return state
        with locked(path(task) / ".lock"):
            contract, state = self.reconciliation_gate(task, expected, release_evidence)
            if state.get("action") == "nothing to release":
                return state
            with self.component_guard(task, contract):
                try:
                    launch = json_read(task / "launch.json") if (task / "launch.json").exists() else None
                    if launch and launch["digest"] != expected:
                        raise RepairError("launch belongs to another contract")
                    if launch and state["mutation"] == "not_attempted":
                        state["mutation"] = "attempted_unknown"
                    self.adapter.check_identity(contract["target"], Path(contract["workspace"]))
                    try:
                        receipt = json_read(task / "deploy-start.json") if (task / "deploy-start.json").exists() else {}
                    except ValueError:
                        receipt = {}  # partial stdout proves neither success nor no launch
                    if not isinstance(receipt, dict):
                        receipt = {}
                    recorded = receipt.get("result", {}).get("id") if isinstance(receipt.get("result"), dict) else None
                    if recorded and state.get("job_id") and recorded != state["job_id"]:
                        raise RepairError("saved job ID disagrees with the launch receipt")
                    known = recorded or state.get("job_id")
                    if job:
                        job_id(job)
                        if not launch or (known and job != known) or not job_evidence:
                            raise RepairError("job association needs launch context and an exact evidence file")
                        evidence = read(path(job_evidence))
                        if not evidence.strip():
                            raise RepairError("job attribution evidence is empty")
                        known = job
                    if known:
                        job_id(known)
                        status = self.adapter.report(contract["target"]["username"], known, Path(state["write_project"]["project_root"]))
                        state["deploy_evidence"] = status
                        if status.get("id") != known:
                            raise RepairError("deploy receipt belongs to another job")
                        if job:
                            if (not status.get("createdDate") or datetime.fromisoformat(status["createdDate"].replace("Z", "+00:00"))
                                    < datetime.fromisoformat(launch["started_at"])):
                                raise RepairError("supplied job predates the recorded launch")
                            attribution = task / "job-attribution.md"
                            if not attribution.exists():
                                write(attribution, evidence, exclusive=True)
                            elif read(attribution) != evidence:
                                raise RepairError("job attribution evidence changed")
                            state["job_attribution"] = "operator-provided; inspect job-attribution.md"
                        state["job_id"] = known
                        state["mutation"] = "succeeded" if status.get("done") is True and status.get("success") is True else "job_recorded"
                    else:
                        status = {}
                    self.adapter.check_identity(contract["target"], Path(contract["workspace"]))
                    current = self.fetch(contract)
                    state.update(readback=current, acceptance="unverified")
                    no_launch = not launch or (not known and receipt.get("name") in NO_LAUNCH_ERRORS and receipt.get("status") != 0)
                    failed = status.get("done") is True and status.get("success") is False and status.get("status") in ("Failed", "Canceled")
                    if self.same(contract, current) and (no_launch or failed):
                        state.update(mutation="not_applied", acceptance="passed" if self.same(contract, current, proposed=True) else "not_met")
                    elif status.get("done") is True and status.get("success") is True:
                        details = status.get("details") or {}
                        if not isinstance(details, dict):
                            raise RepairError("malformed deployment details")
                        rows = details.get("componentSuccesses", [])
                        rows = [rows] if isinstance(rows, dict) else rows
                        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                            raise RepairError("malformed deployed member list")
                        rows = [row for row in rows if row.get("fullName") != "package.xml"]
                        exact = (status.get("status") == "Succeeded" and status.get("checkOnly") is False
                                 and type(status.get("numberComponentsTotal")) is int and status["numberComponentsTotal"] == 1
                                 and not details.get("componentFailures") and len(rows) == 1
                                 and rows[0].get("componentType") == "Report" and rows[0].get("fullName") == contract["member"]
                                 and rows[0].get("success") is True and rows[0].get("created") is False and rows[0].get("deleted") is False)
                        if exact and self.same(contract, current, proposed=True):
                            state["acceptance"] = "passed"
                    if launch:
                        try:
                            state["original"] = self.original(task, contract)
                            state["recovery"] = "verified"
                        except ERRORS as error:
                            state["recovery"] = "blocked"
                            state["recovery_error"] = str(error) if isinstance(error, RepairError) else type(error).__name__
                    state.pop("error", None)
                    if release_evidence and outcome(state) == "unverified":
                        if known and status.get("done") is not True:
                            raise RepairError("cannot release a known job until done is true")
                        if not known:
                            started = datetime.fromisoformat(launch["started_at"])
                            if started.tzinfo is None or (datetime.now(timezone.utc) - started).total_seconds() < RELEASE_HOLD_SECONDS:
                                raise RepairError("cannot release without a job ID until 10 minutes after launch.started_at")
                        evidence = read(path(release_evidence))
                        if not evidence.strip():
                            raise RepairError("release evidence is empty")
                        release = task / "release-evidence.md"
                        if not release.exists():
                            write(release, evidence, exclusive=True)
                        elif read(release) != evidence:
                            raise RepairError("release evidence changed")
                        state["release_evidence"] = str(release)
                    self.checkpoint(task, contract, state)
                    if state["outcome"] in RELEASED:
                        self.resolve(task, expected, state)
                    if release_evidence and state["outcome"] != "released_unverified":
                        state = dict(state, action="nothing to release")
                    return state
                except ERRORS as error:
                    self.record_error(task, contract, state, error)
                    raise

    verify = reconcile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sf-executable", default="sf")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect-report")
    for name in ("workspace-root", "customer-dir", "target-org", "report", "column", "operator", "before", "after", "request-file", "request-reference"):
        inspect.add_argument("--" + name, required=True)
    for name in ("coverage-note", "history-note", "change-log", "previous-task"):
        inspect.add_argument("--" + name)
    for operation in ("apply-report", "verify-report", "reconcile-report", "status"):
        sub = commands.add_parser(operation)
        sub.add_argument("--task-dir", required=True)
        if operation != "status":
            sub.add_argument("--contract-digest", required=True)
        if operation == "reconcile-report":
            sub.add_argument("--job-id")
            sub.add_argument("--job-evidence")
            sub.add_argument("--release-evidence")
    args = parser.parse_args()
    engine = None
    try:
        if args.command == "status":
            result = json_read(path(args.task_dir) / "result.json")
        else:
            engine = Repair(Salesforce(args.sf_executable))
            if args.command == "inspect-report":
                task = engine.inspect(args.workspace_root, args.customer_dir, args.target_org, args.report,
                                      {k: getattr(args, k) for k in ("column", "operator", "before", "after")}, path(args.request_file),
                                      args.request_reference, args.coverage_note, args.history_note, args.change_log, args.previous_task)
                result = json_read(task / "result.json")
            else:
                method = engine.apply if args.command == "apply-report" else engine.reconcile
                kwargs = {"job": args.job_id, "job_evidence": args.job_evidence,
                          "release_evidence": args.release_evidence} if args.command == "reconcile-report" else {}
                result = method(path(args.task_dir), args.contract_digest, **kwargs)
        print(json.dumps(result, sort_keys=True))
        return 0
    except ERRORS as error:
        task = engine.task if engine else None
        terminal_refusal = isinstance(error, RepairError) and str(error).startswith("resolved (")
        result = {"outcome": "blocked", "error": diagnostic(error)}
        if task:
            result["task"] = str(task)
            try:
                saved = json_read(task / "result.json")
                result.update({k: saved[k] for k in ("mutation", "acceptance", "recovery", "log", "checkpoint_marker", "requirements") if k in saved})
                result["saved_outcome"] = saved.get("outcome")
                if terminal_refusal:
                    result["outcome"] = json_read(task / "resolution.json")["outcome"]
                elif (task / "launch.json").exists():
                    result["outcome"] = "unverified"
            except ERRORS:
                pass
        result["action"] = "inspect the named evidence; use reconcile-report for an attempted write"
        if terminal_refusal:
            result["action"] = "start a new task; the recorded resolution is unchanged"
        print(json.dumps(result, sort_keys=True))
        return 1


if __name__ == "__main__":
    scout_portable.utf8_output()
    raise SystemExit(main())
