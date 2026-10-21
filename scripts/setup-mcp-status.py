#!/usr/bin/env python3
"""Report conservative, secret-free MCP registration and transport status."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urlsplit


ALIASES = {
    "salesforce-docs": {"salesforce-docs", "salesforce_docs"},
}

ENDPOINTS = {
    "salesforce-docs": (
        "salesforce-docs-76258744c9d7.herokuapp.com",
        "/api/mcp",
    ),
}


HOSTS = ("claude", "codex", "cursor")


def active_host(explicit: str | None = None) -> str:
    """Use host context, never the presence of a CLI on PATH."""
    selected = explicit if explicit is not None else os.environ.get("SCOUT_HOST")
    if selected is not None:
        return selected if selected in HOSTS else "unknown"
    signals = {"codex": bool(os.environ.get("CODEX_THREAD_ID")), "claude": os.environ.get("CLAUDECODE") == "1",
               "cursor": bool(os.environ.get("CURSOR_AGENT"))}
    found = [host for host, present in signals.items() if present]
    return found[0] if len(found) == 1 else "unknown"


def matches_name(name: str, provider: str) -> bool:
    name = name.lower()
    return name.rsplit(":", 1)[-1] in ALIASES[provider] or (
        name.startswith("plugin_")
        and any(name.endswith("_" + alias) for alias in ALIASES[provider])
    )


def matches_endpoint(endpoint: str, provider: str) -> bool:
    if provider not in ENDPOINTS:
        return False
    host, path = ENDPOINTS[provider]
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError:
        return False
    return bool(
        parsed.scheme == "https"
        and parsed.hostname == host
        and port in (None, 443)
        and parsed.username is None
        and parsed.password is None
        and parsed.path.rstrip("/") == path.rstrip("/")
        and not parsed.query
        and not parsed.fragment
    )

def matches_provider(line: str, provider: str) -> bool:
    stripped = line.strip()
    if ": " not in stripped:
        return False
    entry_name, details = stripped.split(": ", 1)
    if matches_name(entry_name, provider):
        return True
    endpoint = details.split(None, 1)[0].rstrip(".\"',")
    return matches_endpoint(endpoint, provider)


def transport_state(line: str) -> str:
    lowered = line.lower().strip()
    if " - " in lowered:
        lowered = lowered.rsplit(" - ", 1)[1].strip()
    elif ": " in lowered:
        lowered = lowered.rsplit(": ", 1)[1].strip()
    lowered = re.sub(r"^[✔✓✘✗!⏸⊘]\s*", "", lowered).strip()
    if lowered in {"authentication required", "needs authentication"}:
        return "authentication_required"
    if lowered.startswith("failed") or lowered.startswith("error"):
        return "failed"
    if lowered == "disabled" or lowered.startswith("disabled for this project"):
        return "disabled"
    if lowered in {"pending", "checking"} or lowered.startswith("pending approval"):
        return "pending"
    if lowered == "connected":
        return "connected"
    return "unknown"


def unknown_status(provider: str, host: str, reason: str) -> dict[str, str]:
    return {
        "provider": provider,
        "registration": "unknown",
        "transport": "unknown",
        "host": host,
        "policy": "unknown",
        "reason": reason,
        "tools": "unknown",
    }


def claude_status(raw: str, status: dict[str, str]) -> dict[str, str]:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    entries = [line for line in lines if ":" in line]
    if not entries:
        return {**status, "reason": "unrecognized_listing"}
    matches = [line for line in entries if matches_provider(line, status["provider"])]
    if not matches:
        return {**status, "registration": "not_observed", "reason": "not_observed"}
    if len(matches) > 1:
        return {**status, "registration": "ambiguous", "reason": "multiple_matches"}
    return {
        **status, "registration": "registered",
        "transport": transport_state(matches[0]), "reason": "listed",
    }


def codex_matches(row: dict, provider: str) -> bool:
    if matches_name(row["name"], provider):
        return True
    transport = row.get("transport")
    if not isinstance(transport, dict):
        return False
    url = transport.get("url")
    if isinstance(url, str) and matches_endpoint(url, provider):
        return True
    return False


def codex_status(raw: str, status: dict[str, str]) -> dict[str, str]:
    try:
        rows = json.loads(raw)
    except (ValueError, RecursionError):
        return {**status, "reason": "malformed_listing"}
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) or not isinstance(row.get("name"), str)
        for row in rows
    ):
        return {**status, "reason": "malformed_listing"}
    matches = [row for row in rows if codex_matches(row, status["provider"])]
    if not matches:
        return {**status, "registration": "not_observed", "reason": "not_observed"}
    if len(matches) > 1:
        return {**status, "registration": "ambiguous", "reason": "multiple_matches"}
    row = matches[0]
    status = {**status, "registration": "registered"}
    enabled, disabled = row.get("enabled"), row.get("disabled_reason")
    if type(enabled) is not bool or (disabled is not None and not isinstance(disabled, str)):
        return {**status, "reason": "malformed_listing"}
    if enabled and disabled is None:
        # The listing is configuration evidence, not a transport health check.
        valid_name = re.fullmatch(r"[a-zA-Z0-9_:@/.-]+", row["name"])
        reason = "enabled" if valid_name else "invalid_server_name"
        return {**status, "policy": "permitted", "reason": reason}
    if not enabled:
        status = {**status, "transport": "disabled"}
        if isinstance(disabled, str) and (
            disabled == "requirements" or disabled.startswith("requirements (")
        ):
            status.update(policy="blocked", reason="managed_requirements")
            # Retain the policy identifier, never arbitrary reason text, headers,
            # arguments, auth status, or environment values from the raw listing.
            policy_id = re.search(
                r"\(([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})\)",
                disabled,
            )
            if policy_id:
                status["policy_id"] = policy_id.group(1)
            return status
        if disabled in ("user", "config"):
            return {**status, "reason": "user_disabled"}
        return {**status, "reason": "disabled_unknown"}
    return {**status, "reason": "malformed_listing"}


def cursor_status(status: dict[str, str], project: Path | None = None) -> dict[str, str]:
    """Cursor has no listing command: read its user and project `mcp.json` files. Registration only; Cursor itself
    reports the connection."""
    files = [Path.home() / ".cursor" / "mcp.json", (project or Path.cwd()) / ".cursor" / "mcp.json"]
    rows = []
    for path in dict.fromkeys(p.resolve() for p in files):  # a session started in the home folder reads it once
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            return {**status, "reason": "malformed_listing"}
        servers = data.get("mcpServers", {}) if isinstance(data, dict) else None
        if not isinstance(servers, dict):
            return {**status, "reason": "malformed_listing"}
        rows += [(name, entry) for name, entry in servers.items() if isinstance(entry, dict)]
    matches = [name for name, entry in rows if matches_name(name, status["provider"])
               or (isinstance(entry.get("url"), str) and matches_endpoint(entry["url"], status["provider"]))]
    if not matches:
        return {**status, "registration": "not_observed", "reason": "not_observed"}
    if len(matches) > 1:
        return {**status, "registration": "ambiguous", "reason": "multiple_matches"}
    return {**status, "registration": "registered", "reason": "listed"}


def report(provider: str, host: str | None = None) -> dict[str, str]:
    host = active_host(host)
    status = unknown_status(provider, host, "unknown_host")
    if host == "unknown":
        return status
    if host == "cursor":
        return cursor_status(status)
    executable = shutil.which(host)
    if not executable:
        return {**status, "reason": "missing_cli"}
    command = [executable, "mcp", "list"]
    if host == "codex":
        command.append("--json")
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return {**status, "reason": "probe_failed"}
    if result.returncode != 0:
        return {**status, "reason": "probe_failed"}
    return (codex_status if host == "codex" else claude_status)(result.stdout, status)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", nargs="?", choices=tuple(ALIASES))
    parser.add_argument("--host", choices=(*HOSTS, "unknown"))
    parser.add_argument("--detect-host", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.detect_host:
        print(active_host(args.host))
        return 0
    if args.provider is None:
        parser.error("provider is required")
    status = report(args.provider, args.host)
    if args.json:
        print(json.dumps(status, sort_keys=True))
    else:
        print("MCP_STATUS " + " ".join(f"{key}={value}" for key, value in status.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
