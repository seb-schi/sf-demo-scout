#!/usr/bin/env python3
"""Salesforce's hosted metadata-experts server for /scout: a model-free status check, a confirmed
activation, and Flow generation through the official salesforce-development plugin's own proxy,
pinned to the bound org. Never deploys, never holds or prints a token, never changes defaults.

Activation writes the Tooling API's McpServerAccess record, which Setup's Activate button creates but which
Salesforce doesn't document; every activation is read back. The proxy's org binding was verified against
salesforce-development 2.3.0–2.5.0; receipts record the version and digest actually used."""
from __future__ import annotations

import argparse
import decimal
import hashlib
import html
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ElementTree

sys.dont_write_bytecode = True
try:
    from scout_report_repair import LIMIT, RepairError, decode, org_id, text
    from scout_target import Mismatch, Unverified, bind, query_cli
    import scout_official
    import scout_portable
except ImportError:
    print(json.dumps({"reason": "metadata-experts helper dependencies unavailable"}))
    raise SystemExit(4)

SERVER = "metadata-experts"  # the hosted server's slug, kept in one place in case Salesforce renames it
DEVELOPER_NAME, LABEL, TOOL = "platform_metadata_experts", "metadata-experts", "execute_metadata_action"
PLUGIN = "salesforce-development"
PROXY = Path("scripts/sf-mcp-proxy.bundled.js")
PROBE_SECONDS, WAIT_SECONDS, POLL_SECONDS, CANDIDATE_SECONDS, CALL_SECONDS = 60, 180, 15, 600, 180
MAX_GENERATION_CALLS, GRACE_SECONDS = 40, 2
NS = "{http://soap.sforce.com/2006/04/metadata}"
QUERY = "SELECT Id, DeveloperName, Active FROM McpServerAccess WHERE DeveloperName = '%s'" % DEVELOPER_NAME
NO_TOOL = "the official proxy listed no generation tool (often a sign-in problem)"
NO_PLUGIN = "official salesforce-development plugin not installed"
SIDECARS = "could not remove the official proxy's diagnostic files from Scout's cache"
EXIT = {"active": 0, "ready": 0, "complete": 0, "accepted": 0, "clear": 0, "absent": 2, "activation-needed": 2,
        "inactive": 2, "unknown": 4, "unavailable": 4, "unverified": 4, "rejected": 4, "mismatch": 3,
        "no-official-plugin": 5, "refused": 6, "conflict": 7}


class ProxyError(Exception):
    def __init__(self, state, reason, code=None):
        super().__init__(reason)
        self.state, self.reason, self.code = state, reason, code

    def result(self):
        return {"state": self.state, "reason": self.reason, **({"code": self.code} if self.code is not None else {})}


class Interrupted(Exception):
    """A catchable termination signal; raising it unwinds every proxy context so its cleanup runs."""


def interrupted(*_):
    raise Interrupted()


def record_id(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?", value) is not None


def lookup(sf, username):
    """absent (a successful empty query), present (exact Id, DeveloperName and Active), or Unverified (unknown)."""
    raw = query_cli(sf, ["data", "query", "--use-tooling-api", "--target-org", username, "--query", QUERY])
    rows = raw.get("records")
    if not isinstance(rows, list) or len(rows) > 1:
        raise Unverified("activation lookup returned no usable rows")
    if not rows:
        return {"state": "absent"}
    row = rows[0]
    if (not isinstance(row, dict) or row.get("DeveloperName") != DEVELOPER_NAME
            or type(row.get("Active")) is not bool or not record_id(row.get("Id"))):
        raise Unverified("activation lookup returned no usable rows")
    return {"state": "present", "id": row["Id"], "developer_name": DEVELOPER_NAME, "active": row["Active"]}


def activate(sf, username):
    """Create, update or leave the record, then read it back by exact Id. Only a positive read-back settles a
    write: a lost response or a failed read-back stays unverified, because the write may still land."""
    before = lookup(sf, username)
    if before["state"] == "present" and before["active"]:
        return {"state": "active", "action": "none", "before": before, "after": before}
    action, created = ("update" if before["state"] == "present" else "create"), None
    evidence = {"action": action, "mutation": "unknown", "before": before}
    try:
        if action == "update":
            query_cli(sf, ["data", "update", "record", "--use-tooling-api", "--target-org", username,
                           "--sobject", "McpServerAccess", "--record-id", before["id"], "--values", "Active=true"])
        else:
            result = query_cli(sf, ["data", "create", "record", "--use-tooling-api", "--target-org", username,
                                    "--sobject", "McpServerAccess", "--values",
                                    "DeveloperName=%s MasterLabel=%s Active=true" % (DEVELOPER_NAME, LABEL)])
            created = result.get("id") if record_id(result.get("id")) else None
        evidence["mutation"] = "ok"
    except Unverified:
        evidence["mutation"] = "lost"
    except Interrupted:  # the write may still land; keep what's known
        return dict(evidence, state="unverified", after={"state": "unknown"}, interrupted=True)
    try:
        after = lookup(sf, username)
    except (Unverified, Interrupted) as error:
        return dict(evidence, state="unverified", after={"state": "unknown"},
                    **({"interrupted": True} if isinstance(error, Interrupted) else {}))
    expected = before.get("id") or created
    if after["state"] == "present" and after["active"] and (expected is None or after["id"] == expected):
        return dict(evidence, state="active", after=after)
    return dict(evidence, state="unverified", after=after)


def official(host, explicit=None):
    """The official plugin's proxy, version and provider: an explicit root, or scout_official's one resolver (the
    installation from Salesforce's GitHub marketplace, never Anthropic's copy). Another host's registry is never read."""
    if explicit:
        root, version, provider = Path(explicit).expanduser().resolve(), None, "explicit"
    else:
        found = scout_official.installation(PLUGIN, host)
        if found is None:
            return None
        root, version, provider = Path(found["root"]), found["version"], found["provider"]
    try:
        if not (root / PROXY).is_file():
            return None
        digest = hashlib.sha256((root / PROXY).read_bytes()).hexdigest()
    except OSError:
        return None
    return {"proxy": root / PROXY, "root": str(root), "version": version, "provider": provider, "proxy_sha256": digest}


def capable(plugin):
    """Local capability comes first: without the plugin or Node, never offer activation or generation."""
    if plugin is None:
        return {"state": "no-official-plugin", "reason": NO_PLUGIN}
    if not shutil.which("node"):
        return {"state": "no-official-plugin", "reason": "node unavailable"}
    return None


def coexistence(sf, host, explicit, launch_dir):
    """scout_official's coexistence check, as this helper's earlier issue names. An explicit root counts as installed."""
    issues, _ = scout_official.coexistence(sf, host, launch_dir, installed=True if explicit else None)
    return [item["issue"] for item in issues]


def cache_root():
    return Path(os.environ.get("SCOUT_CACHE_DIR") or Path.home() / ".cache" / "sf-demo-scout")


class Proxy:
    """The official proxy as Scout's own subprocess, bound to the org through its environment."""

    def __init__(self, script, username, org, deadline):
        self.folder = cache_root() / "metadata-experts" / org  # a Scout-owned helper folder, never an SE project
        (self.folder / ".sf").mkdir(parents=True, exist_ok=True)
        (self.folder / "sfdx-project.json").write_text('{"packageDirectories":[{"path":"force-app","default":true}]}\n')
        # The environment binds the proxy (it reads it first); the private config only backs that up.
        (self.folder / ".sf" / "config.json").write_text(json.dumps({"target-org": username}) + "\n")
        env = {k: v for k, v in os.environ.items() if k not in ("SF_TARGET_ORG", "SFDX_TARGET_ORG", "SFDX_DEFAULTUSERNAME")}
        env.update(SF_TARGET_ORG=username, SFDX_TARGET_ORG=username, SF_LOG_LEVEL="fatal", SFDX_LOG_LEVEL="fatal",
                   SF_DISABLE_LOG_FILE="true")
        self.deadline, self.counter, self.lines, self.writer, self.sidecars_left = deadline, 0, queue.Queue(), None, False
        try:
            self.process = subprocess.Popen([shutil.which("node") or "node", str(script), SERVER], cwd=self.folder,
                                            env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0,
                                            stderr=subprocess.DEVNULL, **scout_portable.process_group_options())
        except OSError as error:
            raise ProxyError("unavailable", "proxy could not start") from error
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.process.stdout:
            self.lines.put(line if len(line) <= LIMIT else b"")
        self.lines.put(None)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        """On every exit path, end the proxy together with everything it started, then remove its sidecars.

        On macOS and Linux its input closes first and it gets a moment to finish; then its process group ends, which
        reaches a descendant even after the proxy itself has exited. Windows has no process groups: taskkill finds the
        descendants only through the proxy, so there the tree ends first, while the proxy still runs, and its input
        closes after. What stays open there: a proxy that already exited on its own before this point, such as one
        that crashed, can leave a descendant that nothing finds."""
        windows = scout_portable.windows()
        if windows:
            scout_portable.kill_tree(self.process, grace=GRACE_SECONDS)
        if self.writer is None or not self.writer.is_alive():  # a blocked write must not delay termination
            try:
                self.process.stdin.close()
                if not windows:
                    self.process.wait(timeout=GRACE_SECONDS)
            except (OSError, subprocess.TimeoutExpired):
                pass
        if not windows:
            scout_portable.kill_tree(self.process, grace=GRACE_SECONDS)
        sidecars = self.folder / ".sf" / "mcp-health"
        shutil.rmtree(sidecars, ignore_errors=True)
        self.sidecars_left = sidecars.exists()

    def _write(self, data):
        try:
            view = memoryview(data)
            while view:
                view = view[self.process.stdin.write(view):]
        except (OSError, ValueError):
            pass  # the reader reports the exit

    def send(self, message):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ProxyError("unavailable", "timed out")
        self.writer = threading.Thread(target=self._write, args=(json.dumps(message).encode() + b"\n",), daemon=True)
        self.writer.start()
        self.writer.join(timeout=min(remaining, CALL_SECONDS))
        if self.writer.is_alive():
            raise ProxyError("unavailable", "timed out")

    def call(self, method, params, seconds):
        self.counter += 1
        ident = self.counter
        end = min(self.deadline, time.monotonic() + seconds)
        self.send({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                raise ProxyError("unavailable", "timed out")
            try:
                line = self.lines.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                continue
            if line is None:
                raise ProxyError("unavailable", "proxy exited")
            try:
                reply = decode(line)
            except (ValueError, UnicodeError, TypeError, RecursionError, RepairError):
                continue  # not JSON-RPC, such as a stray log line
            if not isinstance(reply, dict) or reply.get("id") != ident:
                continue  # a notification or another call's reply
            if "error" in reply:
                error = reply["error"] if isinstance(reply["error"], dict) else {}
                code = error.get("code") if type(error.get("code")) is int else None
                note = error.get("message") if isinstance(error.get("message"), str) else ""
                if code == -32603 and re.search(r"not activated", note, re.I):
                    raise ProxyError("inactive", "server not activated in this org")
                raise ProxyError("unavailable", "server error", code)
            if not isinstance(reply.get("result"), dict):
                raise ProxyError("unavailable", "unusable reply")
            return reply["result"]

    def start(self):
        self.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "sf-demo-scout", "version": "1"}}, PROBE_SECONDS)
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = self.call("tools/list", {}, PROBE_SECONDS).get("tools")
        if not isinstance(tools, list) or TOOL not in [t.get("name") for t in tools if isinstance(t, dict)]:
            raise ProxyError("unavailable", NO_TOOL)  # the proxy's answer when its own sign-in or mint failed

    def action(self, name, parameters):
        result = self.call("tools/call", {"name": TOOL, "arguments": {
            "metadataType": "Flow", "actionName": name, "parameters": parameters}}, CALL_SECONDS)
        content = result.get("content")
        texts = [c["text"] for c in content if isinstance(c, dict) and c.get("type") == "text"
                 and isinstance(c.get("text"), str)] if isinstance(content, list) else []
        try:
            if result.get("isError") is True:
                raise ValueError()
            inner = decode(decode("".join(texts))["defaultExc"])
            if inner.get("success") is not True or inner.get("errors") or not isinstance(inner.get("outputValues"), dict):
                raise ValueError()
        except (ValueError, UnicodeError, TypeError, KeyError, AttributeError, RecursionError, RepairError) as error:
            raise ProxyError("unavailable", "action failed: " + name) from error
        return inner["outputValues"]


def ready(plugin, target, deadline=None):
    blocked = capable(plugin)
    if blocked:
        return blocked
    deadline, proxy = min(deadline or float("inf"), time.monotonic() + PROBE_SECONDS), None
    try:
        proxy = Proxy(plugin["proxy"], target["username"], target["org_id"], deadline)
        with proxy:
            proxy.start()
        result = {"state": "ready", "reason": "initialize and tools/list succeeded"}
    except ProxyError as error:
        result = error.result()
    if proxy is not None and proxy.sidecars_left:  # never continue silently past the proxy's diagnostic files
        return {"state": "unavailable", "reason": SIDECARS, "sidecars_left": True}
    return result


def flow_xml(raw):
    """Transport decoding only: a reply that arrives entity-encoded is decoded once; raw XML stays byte-identical."""
    if not isinstance(raw, str) or not raw.strip() or len(raw) > LIMIT:
        raise ValueError("empty or oversized Flow XML")
    if raw.lstrip().startswith("&lt;"):
        raw = html.unescape(raw)
    if ElementTree.fromstring(raw.encode()).tag != NS + "Flow":
        raise ValueError("not Flow metadata")
    return raw


def publish(folder, files):
    """Publish a candidate's files together, never over an earlier one: stage each, then link them all, or none.
    Each file's content is bytes, written as they are, so a receipt's digest names the published file."""
    staged, linked = [], []
    try:
        for name, content in files:
            descriptor, temporary = tempfile.mkstemp(prefix=".candidate-", dir=folder)
            staged.append((temporary, folder / name))  # registered before writing, so a full disk can't strand it
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
        for temporary, final in staged:
            os.link(temporary, final)
            linked.append(final)
    except OSError:
        for final in linked:
            final.unlink(missing_ok=True)
        raise
    finally:
        for temporary, _ in staged:
            Path(temporary).unlink(missing_ok=True)


def generate(plugin, target, prompt, folder, candidate):
    names = ("candidate-%d.flow-meta.xml" % candidate, "candidate-%d.receipt.json" % candidate)
    if any((folder / name).exists() for name in names):  # refuse before any hosted call
        return {"state": "unknown", "reason": "candidate %d already exists; use the next one" % candidate}
    actions = {"grounding": 0, "selection": 0, "generation": 0}
    receipt = {"candidate": candidate, "org_id": target["org_id"], "started": time.time(),
               "official": {k: v for k, v in (plugin or {}).items() if k != "proxy"}}
    outcome, xml, proxy = capable(plugin) or {"state": "unknown", "reason": "generation did not complete"}, None, None
    deadline = time.monotonic() + CANDIDATE_SECONDS

    def act(step, name, parameters):
        """One action; a server error (a JSON-RPC error with a code) gets one retry per candidate after a short
        wait: a live run met a transient one right after activation. Envelope failures and timeouts don't."""
        actions[step] += 1
        try:
            return proxy.action(name, parameters)
        except ProxyError as error:
            if error.state != "unavailable" or error.code is None or "retried" in receipt:
                raise
            receipt["retried"] = name
            time.sleep(max(0.0, min(POLL_SECONDS, deadline - time.monotonic() - CALL_SECONDS)))
            actions[step] += 1
            return proxy.action(name, parameters)

    if outcome["state"] != "no-official-plugin":
        try:
            with Proxy(plugin["proxy"], target["username"], target["org_id"], deadline) as proxy:
                proxy.start()
                grounding = act("grounding", "fetchGroundedObjectMetadata", {"userPrompt": prompt, "inflightMetadata": []})
                if not isinstance(grounding.get("groundingMetadata"), str) or not grounding["groundingMetadata"]:
                    raise ProxyError("unavailable", "no grounding metadata")
                selection = act("selection", "flowElementSelection", {"userPrompt": prompt, "operationId": "",
                                                                      "groundingMetadata": grounding["groundingMetadata"]})
                operation = selection.get("operationId")
                if not isinstance(operation, str) or not operation:
                    raise ProxyError("unavailable", "no operation ID")
                receipt["operation_id"] = operation
                while actions["generation"] < MAX_GENERATION_CALLS:
                    step = act("generation", "flowElementGeneration", {"operationId": operation, "requestSource": "A4V"})
                    if step.get("isComplete") is True:
                        try:
                            xml = flow_xml(step.get("result"))
                        except (ValueError, ElementTree.ParseError):
                            raise ProxyError("unavailable", "generated XML is empty or invalid")
                        outcome = {"state": "complete", "reason": "Flow XML generated", "xml": str(folder / names[0])}
                        break
                    if step.get("isComplete") not in (False, None):
                        raise ProxyError("unavailable", "unusable completion flag")
                else:
                    outcome = {"state": "unavailable", "reason": "generation call budget exhausted"}
        except ProxyError as error:
            outcome = error.result()
        except Interrupted:
            outcome = {"state": "unknown", "reason": "interrupted; the proxy was stopped"}
    # Client RPC requests only; the proxy's internal replays and Salesforce's billable units aren't visible here.
    receipt["client_rpc_calls"] = dict(actions, total=proxy.counter if proxy else 0)
    receipt.update(outcome={k: v for k, v in outcome.items() if k != "xml"}, finished=time.time(),
                   sidecars_left=bool(proxy and proxy.sidecars_left))
    if receipt["sidecars_left"]:
        outcome = dict(outcome, sidecars_left=True, sidecars_reason=SIDECARS)
    content = xml.encode("utf-8") if xml is not None else None  # encoded once: these bytes are hashed and published
    if content is not None:
        receipt.update(xml=names[0], sha256=hashlib.sha256(content).hexdigest())
    files = (([(names[0], content)] if content is not None else [])
             + [(names[1], (json.dumps(receipt, sort_keys=True, indent=1) + "\n").encode("utf-8"))])
    try:
        publish(folder, files)
    except OSError:
        return {"state": "unknown", "reason": "could not publish the candidate and its receipt", "generated": xml is not None}
    return outcome


def typed(value_element=None, spec_value=None):
    """A comparable (type, value) for a Flow filter value, from the XML or from the spec."""
    if value_element is not None:
        child = next(iter(value_element), None)
        kind, raw = (child.tag.replace(NS, ""), (child.text or "")) if child is not None else ("none", "")
    elif isinstance(spec_value, dict) and len(spec_value) == 1:  # the XML's own form, {"stringValue": "Closed Won"}
        kind, inner = next(iter(spec_value.items()))
        raw = ("true" if inner else "false") if isinstance(inner, bool) else "" if inner is None else str(inner)
    elif isinstance(spec_value, bool):
        kind, raw = "booleanValue", "true" if spec_value else "false"
    elif isinstance(spec_value, (int, float)):
        kind, raw = "numberValue", str(spec_value)
    else:
        kind, raw = "stringValue", "" if spec_value is None else str(spec_value)
    if kind == "numberValue":
        try:
            raw = format(decimal.Decimal(raw).normalize(), "f")
        except decimal.InvalidOperation:
            pass
    return kind, raw.strip().lower() if kind == "booleanValue" else raw


def logic_form(value, count):
    """Filter logic in a comparable form: a plain chain of all conditions in order ("1", "1 AND 2", "1 OR 2 OR 3")
    means the same as "and" or "or"; anything else stays as written, and its numbers refer to positions."""
    text = " ".join((value or "and").lower().replace("(", " ( ").replace(")", " ) ").split())
    if text in ("and", "or"):
        return text
    tokens = text.split()
    numbers, operators = tokens[0::2], set(tokens[1::2])
    if numbers == [str(i) for i in range(1, count + 1)] and len(operators) <= 1 and operators <= {"and", "or"}:
        return operators.pop() if operators else "and"
    return text


def check(xml, spec):
    """Static candidate checks against the approved spec; the dry-run deploy and the frozen FlowTests still decide.
    The API name is the source filename, so it isn't checked here, and the generator's label is reported, not
    rejected: live tests showed it rarely keeps a requested label, and hosted XML is never edited."""
    root = ElementTree.fromstring(xml.encode())
    start = root.find(NS + "start")
    found = lambda parent, tag: (parent.findtext(NS + tag) if parent is not None else None)
    problems = []
    if found(root, "status") != "Draft":
        problems.append("status is not Draft")
    try:
        if float(found(root, "apiVersion")) > float(spec["max_api_version"]):
            problems.append("API version is newer than Scout's")
    except (TypeError, ValueError):
        problems.append("API version missing")
    for tag, key in (("object", "object"), ("triggerType", "trigger_type"), ("recordTriggerType", "record_trigger_type")):
        if spec.get(key) and found(start, tag) != spec[key]:
            problems.append("%s differs from the spec" % tag)
    if "filters" in spec:
        wanted = [(f["field"], f["operator"], typed(spec_value=f.get("value"))) for f in spec["filters"]]
        actual = [(f.findtext(NS + "field"), f.findtext(NS + "operator"), typed(value_element=f.find(NS + "value")))
                  for f in (start.findall(NS + "filters") if start is not None else [])]
        wanted_logic = logic_form(spec.get("filter_logic"), len(wanted))
        actual_logic = logic_form(found(start, "filterLogic"), len(actual))
        numbered = any(ch.isdigit() for ch in wanted_logic + actual_logic)  # numbered logic refers to positions
        if wanted_logic != actual_logic or (wanted != actual if numbered else sorted(wanted) != sorted(actual)):
            problems.append("entry conditions differ from the spec")
    if "requires_change" in spec:
        change_only = found(start, "doesRequireRecordChangedToMeetCriteria") == "true"
        if spec["requires_change"] is True and not change_only:
            problems.append("fires on every qualifying edit, not only when the record changes to meet the criteria")
        if spec["requires_change"] is False and change_only:
            problems.append("fires only when the record changes to meet the criteria, not on every qualifying edit")
    return problems


def main(argv=None):
    signals = [sig for sig in (signal.SIGTERM, getattr(signal, "SIGHUP", None), signal.SIGINT) if sig]  # no SIGHUP on Windows
    previous = {sig: signal.signal(sig, interrupted) for sig in signals}
    try:
        return dispatch(argv)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def dispatch(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "activate", "flow", "coexistence"):
        sub = commands.add_parser(name)
        sub.add_argument("--host", required=True, choices=("claude", "codex", "cursor", "unknown"))
        sub.add_argument("--official-root", default=os.environ.get("SCOUT_OFFICIAL_PLUGIN_ROOT"),
                         help="an explicitly selected official plugin root (default: $SCOUT_OFFICIAL_PLUGIN_ROOT)")
        if name == "coexistence":
            sub.add_argument("--launch-dir", type=Path, default=Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()),
                             help="the folder the session started in, where the official hooks run")
            for flag in ("--selector", "--username", "--org-id"):
                sub.add_argument(flag, help="accepted for a uniform invocation; coexistence makes no bound-org call")
            continue
        sub.add_argument("--selector", required=True)
        sub.add_argument("--username", required=True)
        sub.add_argument("--org-id", required=True)
        if name == "status":
            sub.add_argument("--probe", action="store_true")
        if name == "activate":
            sub.add_argument("--confirmed", action="store_true")
        if name == "flow":
            sub.add_argument("--prompt-file", required=True, type=Path)
            sub.add_argument("--out-dir", required=True, type=Path)
            sub.add_argument("--candidate", required=True, type=int, choices=(1, 2))
    sub = commands.add_parser("check")
    sub.add_argument("--xml", required=True, type=Path)
    sub.add_argument("--spec", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result, code = run(parser, args)
    except Interrupted:
        result, code = {"state": "unknown", "reason": "interrupted; the proxy was stopped"}, EXIT["unknown"]
    print(json.dumps(result, sort_keys=True))
    return code


def run(parser, args):
    if args.command == "check":
        try:
            problems = check(args.xml.read_text(encoding="utf-8"), decode(args.spec.read_bytes()))
        except (OSError, ValueError, UnicodeError, KeyError, TypeError, AttributeError, RepairError, ElementTree.ParseError):
            problems = ["candidate or spec unreadable"]
        result = {"state": "rejected" if problems else "accepted", "problems": problems}
        try:
            label = ElementTree.fromstring(args.xml.read_bytes()).findtext(NS + "label")
            result["label"] = label  # the generator's own label, for the handover
        except (OSError, ElementTree.ParseError):
            pass
        return result, EXIT[result["state"]]
    if args.command == "coexistence":
        issues = coexistence(shutil.which("sf") or "sf", args.host, args.official_root, args.launch_dir)
        result = {"state": "conflict" if issues else "clear", "issues": issues}
        return result, EXIT[result["state"]]
    if args.command == "activate" and not args.confirmed:
        result = {"state": "refused", "reason": "activation needs the SE's explicit yes (--confirmed)"}
        return result, EXIT["refused"]
    plugin = official(args.host, args.official_root)
    if args.command in ("activate", "flow") or getattr(args, "probe", False):
        blocked = capable(plugin)  # no org call, and no org-wide write, when the hosted route can't run anyway
        if blocked:
            return blocked, EXIT[blocked["state"]]
    try:
        expected = {"username": text(args.username, "username", 255), "org_id": org_id(args.org_id)}
        target = bind(text(args.selector, "selector"), expected)
    except RepairError:
        parser.error("invalid binding arguments")
    except Mismatch as error:
        return {"state": "mismatch", "reason": str(error)}, EXIT["mismatch"]
    except Unverified as error:
        return {"state": "unknown", "reason": str(error)}, EXIT["unknown"]
    sf = shutil.which("sf")
    try:
        if args.command == "status":
            record = lookup(sf, target["username"])
            active = record["state"] == "present" and record["active"]
            if not args.probe:  # exit by record state: present 0, absent 2, unknown 4
                result, code = {"state": record["state"], "record": record}, 0 if record["state"] == "present" else 2
            elif not active:
                result = {"state": "activation-needed", "record": record}
                code = EXIT[result["state"]]
            else:
                result = dict(ready(plugin, target), record=record)
                code = EXIT.get(result["state"], 4)
        elif args.command == "activate":
            result = activate(sf, target["username"])
            if result["state"] == "active":
                end, readiness = time.monotonic() + WAIT_SECONDS, {"state": "interrupted"}  # Scout's own budget
                try:
                    readiness = ready(plugin, target, end)
                    while readiness["state"] == "inactive" and time.monotonic() + POLL_SECONDS + PROBE_SECONDS <= end:
                        time.sleep(POLL_SECONDS)  # a new probe starts only when a whole one still fits the budget
                        readiness = ready(plugin, target, end)
                except Interrupted:
                    readiness = {"state": "interrupted"}  # the activation itself is verified; keep its evidence
                result["readiness"] = readiness["state"]
                if readiness.get("sidecars_left"):
                    result.update(sidecars_left=True, sidecars_reason=SIDECARS)
            code = EXIT.get(result["state"], 4)
        else:
            args.out_dir.mkdir(parents=True, exist_ok=True)
            result = generate(plugin, target, text(args.prompt_file.read_text(encoding="utf-8"), "prompt", 20000),
                              args.out_dir, args.candidate)
            code = EXIT.get(result["state"], 4)
    except Unverified as error:
        result, code = {"state": "unknown", "reason": str(error)}, EXIT["unknown"]
    except (OSError, RepairError, UnicodeError):
        result, code = {"state": "unknown", "reason": "local files unreadable or unwritable"}, EXIT["unknown"]
    result.update(org_id=target["org_id"], username=target["username"])
    if plugin:
        result["official"] = {k: v for k, v in plugin.items() if k != "proxy"}
    return result, code


if __name__ == "__main__":
    raise SystemExit(main())
