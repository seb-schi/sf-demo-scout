#!/usr/bin/env python3
"""Report conservative, secret-free MCP registration and transport status."""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import sys
from urllib.parse import urlsplit


ALIASES = {
    "slack": {"slack"},
    "google": {"google-workspace", "google_workspace"},
    "salesforce-docs": {"salesforce-docs", "salesforce_docs"},
}

ENDPOINTS = {
    "slack": ("mcp.slack.com", "/mcp"),
    "salesforce-docs": (
        "salesforce-docs-76258744c9d7.herokuapp.com",
        "/api/mcp",
    ),
}


def matches_provider(line: str, provider: str) -> bool:
    stripped = line.strip()
    if ": " not in stripped:
        return False
    entry_name, details = stripped.split(": ", 1)
    entry_name = entry_name.lower()
    name = entry_name.rsplit(":", 1)[-1]
    aliases = ALIASES[provider]
    if name in aliases or (
        entry_name.startswith("plugin_")
        and any(entry_name.endswith("_" + alias) for alias in aliases)
    ):
        return True
    if provider == "google":
        command = details.rsplit(" - ", 1)[0]
        try:
            tokens = shlex.split(command)
        except ValueError:
            return False
        if not tokens or tokens[0].rsplit("/", 1)[-1] != "mcp-adaptor":
            return False
        return any(
            tokens[index:index + 3] == ["serve", "--server", "google_workspace"]
            for index in range(len(tokens) - 2)
        )
    host, path = ENDPOINTS[provider]
    endpoint = details.split(None, 1)[0].rstrip(".\"',")
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


def report(provider: str) -> tuple[str, str]:
    claude = shutil.which("claude")
    if not claude:
        return "unknown", "unknown"
    try:
        result = subprocess.run(
            [claude, "mcp", "list"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return "unknown", "unknown"
    if result.returncode != 0:
        return "unknown", "unknown"
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    entries = [line for line in lines if ":" in line]
    if not entries:
        return "unknown", "unknown"
    matches = [line for line in entries if matches_provider(line, provider)]
    if not matches:
        return "not_observed", "unknown"
    if len(matches) > 1:
        return "ambiguous", "unknown"
    return "registered", transport_state(matches[0])


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ALIASES:
        return 64
    provider = sys.argv[1]
    registration, transport = report(provider)
    print(
        f"MCP_STATUS provider={provider} registration={registration} "
        f"transport={transport}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
