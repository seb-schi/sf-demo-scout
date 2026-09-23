#!/usr/bin/env python3
"""Normalize the small evidence subset used by the Scout startup banner.

Raw CLI responses are read from stdin and are never written by this helper.
The shell hook owns bounded command execution and atomic cache publication.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import re
import sys
import time
from typing import Any


SCHEMA_VERSION = 1
MAX_INPUT_BYTES = 4 * 1024 * 1024
PROVENANCE = {
    "config": "sf config get target-org --json",
    "list": "sf org list --json",
    "display": "sf org display --json",
    "mcp": "claude mcp list",
}
FIELDS = {
    "config": {"state", "target", "collected_at", "collected_at_utc", "provenance"},
    "list": {"org_count", "collected_at", "collected_at_utc", "provenance"},
    "display": {
        "state",
        "connected_status",
        "username",
        "org_id",
        "instance_url",
        "collected_at",
        "collected_at_utc",
        "provenance",
    },
    "mcp": {"state", "collected_at", "collected_at_utc", "provenance"},
}


class EvidenceError(ValueError):
    """Raised when CLI or cached evidence does not satisfy the strict schema."""


def fail(message: str) -> "NoReturn":
    print(message, file=sys.stderr)
    raise SystemExit(65)


def read_stdin() -> str:
    data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise EvidenceError("evidence exceeds size limit")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EvidenceError("evidence is not UTF-8") from error


def safe_text(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise EvidenceError(f"{field} must be a string")
    if (not allow_empty and len(value) == 0) or len(value) > 4096:
        raise EvidenceError(f"{field} has invalid length")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise EvidenceError(f"{field} contains control characters")
    return value


def parse_json(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise EvidenceError("malformed JSON") from error
    if not isinstance(value, dict):
        raise EvidenceError("top-level evidence must be an object")
    return value


def require_success(payload: dict[str, Any]) -> Any:
    status = payload.get("status")
    if type(status) is not int or status != 0:
        raise EvidenceError("CLI JSON status is not successful")
    if "result" not in payload:
        raise EvidenceError("CLI JSON result is missing")
    return payload["result"]


def metadata(kind: str, collected_date: str, provenance: str) -> dict[str, Any]:
    try:
        parsed_date = date.fromisoformat(collected_date)
    except ValueError as error:
        raise EvidenceError("collection date is invalid") from error
    if parsed_date.isoformat() != collected_date:
        raise EvidenceError("collection date is not canonical")
    if provenance != PROVENANCE[kind]:
        raise EvidenceError("provenance is not recognized")
    collected_at = int(time.time())
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "collected_at": collected_at,
        "collected_at_utc": datetime.fromtimestamp(
            collected_at, tz=timezone.utc
        ).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "collected_date": collected_date,
        "provenance": provenance,
    }


def normalize_config(result: Any, base: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, list):
        raise EvidenceError("config result must be a list")
    if any(not isinstance(row, dict) for row in result):
        raise EvidenceError("config entries must be objects")
    matches = [
        row for row in result if row.get("name") == "target-org"
    ]
    if len(matches) > 1:
        raise EvidenceError("config result has duplicate target-org entries")
    if len(matches) == 0:
        if len(result) != 0:
            raise EvidenceError("config result does not describe target-org")
        return {**base, "state": "absent"}
    if matches[0].get("value") is None:
        return {**base, "state": "absent"}
    target = safe_text(matches[0].get("value"), "target-org")
    return {**base, "state": "present", "target": target}


def normalize_list(result: Any, base: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise EvidenceError("org list result must be an object")
    identifiers: list[str] = []
    org_count = 0
    saw_collection = False
    for collection in ("nonScratchOrgs", "scratchOrgs"):
        if collection not in result:
            continue
        saw_collection = True
        rows = result[collection]
        if not isinstance(rows, list):
            raise EvidenceError(f"{collection} must be a list")
        for row in rows:
            if not isinstance(row, dict):
                raise EvidenceError("org list entries must be objects")
            org_count += 1
            for field in ("alias", "username"):
                value = row.get(field)
                if value is None:
                    continue
                identifier = safe_text(value, field)
                if identifier not in identifiers:
                    identifiers.append(identifier)
    if not saw_collection:
        raise EvidenceError("org list collections are missing")
    return {**base, "org_count": org_count, "identifiers": identifiers}


def normalize_display(
    result: Any, base: dict[str, Any], target: str | None
) -> dict[str, Any]:
    if target is None:
        raise EvidenceError("display target is required")
    target = safe_text(target, "target")
    if not isinstance(result, dict):
        raise EvidenceError("org display result must be an object")
    connected_status = safe_text(result.get("connectedStatus"), "connectedStatus")
    normalized = {
        **base,
        "target": target,
        "connected_status": connected_status,
    }
    if connected_status != "Connected":
        return {**normalized, "state": "not_connected"}
    return {
        **normalized,
        "state": "connected",
        "username": safe_text(result.get("username"), "username"),
        "org_id": safe_text(result.get("id"), "id"),
        "instance_url": safe_text(result.get("instanceUrl"), "instanceUrl"),
    }


def normalize_mcp(raw: str, base: dict[str, Any]) -> dict[str, Any]:
    slack_lines = []
    for line in raw.splitlines():
        if ": " not in line.strip():
            continue
        name, details = line.strip().split(": ", 1)
        if name.rsplit(":", 1)[-1].lower() == "slack" or (
            name.lower().startswith("plugin_") and name.lower().endswith("_slack")
        ):
            slack_lines.append(details)
    if len(slack_lines) == 0:
        return {**base, "state": "not_observed"}
    if len(slack_lines) > 1:
        raise EvidenceError("duplicate Slack MCP rows")
    suffix = slack_lines[0].rsplit(" - ", 1)[-1].strip().lower()
    suffix = re.sub(r"^[✔✓✘✗!⏸⊘]\s*", "", suffix).strip()
    state = "unknown"
    if suffix == "connected":
        state = "connected"
    elif suffix in {"authentication required", "needs authentication"}:
        state = "authentication_required"
    elif suffix.startswith("disabled"):
        state = "disabled"
    elif suffix.startswith(("failed", "error")):
        state = "failed"
    elif suffix in {"pending", "checking"} or suffix.startswith("pending approval"):
        state = "pending"
    return {**base, "state": state}


def normalize(args: argparse.Namespace) -> None:
    raw = read_stdin()
    base = metadata(args.kind, args.collected_date, args.provenance)
    if args.kind == "mcp":
        result = normalize_mcp(raw, base)
    else:
        payload = parse_json(raw)
        cli_result = require_success(payload)
        if args.kind == "config":
            result = normalize_config(cli_result, base)
        elif args.kind == "list":
            result = normalize_list(cli_result, base)
        else:
            result = normalize_display(cli_result, base, args.target)
    json.dump(result, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")


def validate_common(
    payload: dict[str, Any], kind: str, collected_date: str, target: str | None
) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("kind") != kind:
        raise EvidenceError("cache schema or kind mismatch")
    if payload.get("collected_date") != collected_date:
        raise EvidenceError("cache is not from today")
    timestamp = payload.get("collected_at")
    if type(timestamp) is not int or timestamp < 0 or timestamp > int(time.time()) + 60:
        raise EvidenceError("cache timestamp is invalid")
    expected_utc = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    if payload.get("collected_at_utc") != expected_utc:
        raise EvidenceError("cache UTC timestamp is invalid")
    if datetime.fromtimestamp(timestamp).date().isoformat() != payload.get(
        "collected_date"
    ):
        raise EvidenceError("cache date does not match its timestamp")
    if payload.get("provenance") != PROVENANCE[kind]:
        raise EvidenceError("cache provenance is invalid")
    if kind == "display" and payload.get("target") != target:
        raise EvidenceError("cache target mismatch")


def validate_payload(
    payload: dict[str, Any], kind: str, collected_date: str, target: str | None
) -> None:
    validate_common(payload, kind, collected_date, target)
    common_keys = {
        "schema_version",
        "kind",
        "collected_at",
        "collected_at_utc",
        "collected_date",
        "provenance",
    }
    if kind == "config":
        state = payload.get("state")
        if state not in {"present", "absent"}:
            raise EvidenceError("config cache state is invalid")
        if state == "present":
            safe_text(payload.get("target"), "target")
            allowed_keys = common_keys | {"state", "target"}
        else:
            allowed_keys = common_keys | {"state"}
    elif kind == "list":
        count = payload.get("org_count")
        identifiers = payload.get("identifiers")
        if type(count) is not int or count < 0 or not isinstance(identifiers, list):
            raise EvidenceError("org list cache fields are invalid")
        for identifier in identifiers:
            safe_text(identifier, "identifier")
        allowed_keys = common_keys | {"org_count", "identifiers"}
    elif kind == "display":
        safe_text(payload.get("target"), "target")
        state = payload.get("state")
        safe_text(payload.get("connected_status"), "connected_status")
        if state == "connected" and payload.get("connected_status") == "Connected":
            safe_text(payload.get("username"), "username")
            safe_text(payload.get("org_id"), "org_id")
            safe_text(payload.get("instance_url"), "instance_url")
            allowed_keys = common_keys | {
                "target",
                "state",
                "connected_status",
                "username",
                "org_id",
                "instance_url",
            }
        elif state == "not_connected" and payload.get("connected_status") != "Connected":
            allowed_keys = common_keys | {"target", "state", "connected_status"}
        else:
            raise EvidenceError("org display cache state is invalid")
    else:
        if payload.get("state") not in {
            "connected", "authentication_required", "disabled", "failed",
            "pending", "unknown", "not_observed",
        }:
            raise EvidenceError("MCP cache state is invalid")
        allowed_keys = common_keys | {"state"}
    if set(payload) != allowed_keys:
        raise EvidenceError("cache contains unexpected or missing fields")


def cached_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = parse_json(read_stdin())
    validate_payload(payload, args.kind, args.collected_date, args.target)
    return payload


def validate(args: argparse.Namespace) -> None:
    cached_payload(args)


def field(args: argparse.Namespace) -> None:
    if args.field not in FIELDS[args.kind]:
        raise EvidenceError("field is not available for this evidence kind")
    payload = cached_payload(args)
    value = payload.get(args.field, "")
    if isinstance(value, str):
        safe_text(value, args.field, allow_empty=True)
    elif type(value) is not int:
        raise EvidenceError("field value has an invalid type")
    print(value)


def contains(args: argparse.Namespace) -> None:
    payload = cached_payload(args)
    if args.target is None:
        raise EvidenceError("membership target is required")
    print("found" if args.target in payload["identifiers"] else "missing")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    key_parser = subparsers.add_parser("key")
    key_parser.add_argument("target")

    for command in ("normalize", "validate", "field", "contains"):
        child = subparsers.add_parser(command)
        if command == "contains":
            child.add_argument("kind", choices=("list",))
        else:
            child.add_argument("kind", choices=tuple(PROVENANCE))
        child.add_argument("--collected-date", required=True)
        child.add_argument("--target")
        if command == "normalize":
            child.add_argument("--provenance", required=True)
        if command == "field":
            child.add_argument("--field", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        if args.command == "key":
            target = safe_text(args.target, "target")
            print(hashlib.sha256(target.encode("utf-8")).hexdigest())
        elif args.command == "normalize":
            normalize(args)
        elif args.command == "validate":
            validate(args)
        elif args.command == "field":
            field(args)
        else:
            contains(args)
    except EvidenceError as error:
        fail(str(error))


if __name__ == "__main__":
    main()
