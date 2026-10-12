#!/usr/bin/env python3
"""Read-only target binding for /scout; never change authentication or defaults."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess

try:
    from scout_report_repair import LIMIT, RepairError, decode, org_id, text
except ImportError:
    print(json.dumps({"reason": "target helper dependencies unavailable"}))
    raise SystemExit(4)

TIMEOUT = 75


class Unverified(Exception):
    pass


class Mismatch(Exception):
    pass


def query_cli(executable, args):
    try:
        result = subprocess.run([executable, *args, "--json"], stdin=subprocess.DEVNULL,
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


def bind(selector, expected=None):
    executable = shutil.which("sf")
    if not executable:
        raise Unverified("Salesforce CLI unavailable")
    raw = query_cli(executable, ["org", "display", "--target-org", selector])
    try:
        target = {"selector": selector, "username": text(raw.get("username"), "username", 255),
                  "org_id": org_id(raw.get("id"))}
    except RepairError as error:
        raise Unverified("identity response lacks valid fields") from error
    if expected and target["username"] != expected["username"]:
        raise Mismatch("selector now resolves to another username")
    if expected and target["org_id"] != expected["org_id"]:
        raise Mismatch("selector now resolves to another org")
    raw = query_cli(executable, ["data", "query", "--target-org", target["username"],
                                 "--query", "SELECT Id FROM Organization"])
    try:
        rows = raw.get("records")
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise RepairError("invalid rows")
        authenticated = org_id(rows[0].get("Id"))
    except RepairError as error:
        raise Unverified("Organization query lacks one valid identity row") from error
    if authenticated != target["org_id"]:
        raise Mismatch("authenticated org differs")
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
    print(json.dumps(dict(result, reason="identity verified"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
