#!/usr/bin/env python3
"""Read-only target binding for /scout; never change authentication or defaults.

Binding also classifies the org, with the official deploy gate's buckets in its order, from the live Organization
record: scratch, sandbox, trial (a future expiry date, a Developer Edition, or a trial host), production, or unknown
when the record doesn't say. Scout writes only to scratch, sandbox and trial orgs; `check --write` refuses the rest."""
from __future__ import annotations

import argparse
import datetime
import json
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
try:
    from scout_report_repair import LIMIT, RepairError, decode, org_id, text
    import scout_portable
except ImportError:
    print(json.dumps({"reason": "target helper dependencies unavailable"}))
    raise SystemExit(4)

TIMEOUT = 75
ORGANIZATION = "SELECT Id, IsSandbox, OrganizationType, TrialExpirationDate FROM Organization"
# The official gate's trial and developer host markers: trials or Developer Editions even without an expiry date.
TRIAL_HOSTS = ("orgfarm-", ".pc-rnd.", ".develop.my.salesforce.com", ".scratch.my.salesforce.com")
WRITABLE = ("scratch", "sandbox", "trial")


class Unverified(Exception):
    pass


class Mismatch(Exception):
    pass


def query_cli(executable, args):
    try:  # on Windows, through the CLI's Node entry, so cmd.exe never re-reads a selector such as R&D
        command = scout_portable.sf_command(executable, [*args, "--json"])
    except ValueError as error:
        raise Unverified(str(error)) from error
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=TIMEOUT)
    except (OSError, UnicodeError, subprocess.SubprocessError) as error:
        raise Unverified("CLI unavailable or timed out") from error
    if result.returncode:
        raise Unverified("CLI operation failed")
    if len(result.stdout) > LIMIT:
        raise Unverified("CLI response exceeds the limit")
    try:
        envelope = decode(result.stdout)
        if (not isinstance(envelope, dict) or type(envelope.get("status")) is not int
                or envelope["status"] != 0 or not isinstance(envelope.get("result"), dict)):
            raise ValueError()
    except (ValueError, UnicodeError, TypeError, RecursionError) as error:
        raise Unverified("CLI returned unusable JSON") from error
    return envelope["result"]


def classify(instance_url, organization, today=None, scratch=False):
    """The org's class: scratch, sandbox, trial, production, or unknown when the record lacks what decides it.
    `scratch` is the CLI's own scratch flag, when its record carries one."""
    if not isinstance(organization, dict) or not isinstance(organization.get("IsSandbox"), bool):
        return "unknown"
    host = instance_url.lower() if isinstance(instance_url, str) else ""
    if scratch is True or ".scratch.my.salesforce.com" in host:
        return "scratch"
    if (organization["IsSandbox"] or "--" in host or "test.salesforce.com" in host
            or ".sandbox.my.salesforce.com" in host):
        return "sandbox"
    today = today or datetime.datetime.now(datetime.timezone.utc).date()
    expiry = organization.get("TrialExpirationDate")
    try:
        future = isinstance(expiry, str) and datetime.date.fromisoformat(expiry[:10]) >= today
    except ValueError:
        future = False  # a stale or unreadable date is no proof of a trial
    edition = organization.get("OrganizationType")
    if future or edition == "Developer Edition" or any(marker in host for marker in TRIAL_HOSTS):
        return "trial"
    if not host or not isinstance(edition, str):
        return "unknown"
    return "production"


def bind(selector, expected=None):
    executable = shutil.which("sf")
    if not executable:
        raise Unverified("Salesforce CLI unavailable")
    raw = query_cli(executable, ["org", "display", "--target-org", selector])
    try:
        target = {"selector": selector, "username": text(raw.get("username"), "username", 255),
                  "org_id": org_id(raw.get("id"))}
        instance_url, scratch = raw.get("instanceUrl"), raw.get("isScratch") is True
    except RepairError as error:
        raise Unverified("identity response lacks valid fields") from error
    if expected and target["username"] != expected["username"]:
        raise Mismatch("selector now resolves to another username")
    if expected and target["org_id"] != expected["org_id"]:
        raise Mismatch("selector now resolves to another org")
    try:
        raw = query_cli(executable, ["data", "query", "--target-org", target["username"], "--query", ORGANIZATION])
    except Unverified:  # the type fields failed, not necessarily the identity: bind read-only if the identity holds
        raw, instance_url = query_cli(executable, ["data", "query", "--target-org", target["username"],
                                                   "--query", "SELECT Id FROM Organization"]), None
    try:
        rows = raw.get("records")
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise RepairError("invalid rows")
        authenticated = org_id(rows[0].get("Id"))
    except RepairError as error:
        raise Unverified("Organization query lacks one valid identity row") from error
    if authenticated != target["org_id"]:
        raise Mismatch("authenticated org differs")
    target["class"] = classify(instance_url, rows[0], scratch=scratch) if instance_url is not None else "unknown"
    target["writes"] = "allowed" if target["class"] in WRITABLE else "read-only"
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for operation in ("bind", "check"):
        sub = commands.add_parser(operation)
        sub.add_argument("--selector", required=True)
        if operation == "check":
            sub.add_argument("--username", required=True)
            sub.add_argument("--org-id", required=True)
            sub.add_argument("--write", action="store_true", help="refuse an org Scout doesn't write to (exit 5)")
    args = parser.parse_args(argv)
    try:
        selector = text(args.selector, "selector")
        expected = ({"username": text(args.username, "username", 255), "org_id": org_id(args.org_id)}
                    if args.command == "check" else None)
    except RepairError:
        parser.error("invalid binding arguments")
    try:
        result = bind(selector, expected)
    except (Unverified, Mismatch) as error:
        print(json.dumps({"reason": str(error)}))
        return 3 if isinstance(error, Mismatch) else 4
    if getattr(args, "write", False) and result["writes"] != "allowed":
        print(json.dumps(dict(result, reason="read-only org (%s): Scout doesn't write here" % result["class"]),
                         sort_keys=True))
        return 5
    print(json.dumps(dict(result, reason="identity verified"), sort_keys=True))
    return 0


if __name__ == "__main__":
    scout_portable.utf8_output()
    raise SystemExit(main())
