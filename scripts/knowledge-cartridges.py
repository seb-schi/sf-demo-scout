#!/usr/bin/env python3
"""Find cartridge contracts only in explicitly enabled, selected plugin roots.

The host owns enablement and scope resolution. This read-only helper consumes its
inventory, never enumerates caches, and does not claim session-load attestation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


MAX_BYTES = 2 * 1024 * 1024
MAX_PLUGINS = 1000
PLUGIN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*@[A-Za-z0-9][A-Za-z0-9._-]*")
CONTRACTS = ("INTEGRATING.md", "KNOWLEDGE-INDEX.md")


class InventoryError(ValueError):
    pass


def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InventoryError("duplicate inventory key")
        result[key] = value
    return result


def parse_inventory(raw: bytes) -> list[dict[str, Any]]:
    if len(raw) > MAX_BYTES:
        raise InventoryError("inventory exceeds size limit")
    try:
        rows = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_keys)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise InventoryError("inventory is not valid JSON") from exc
    if not isinstance(rows, list) or len(rows) > MAX_PLUGINS:
        raise InventoryError("expected a bounded installed-plugin list")
    if any(not isinstance(row, dict) for row in rows):
        raise InventoryError("invalid installed-plugin entry")
    return rows


def selected_cartridges(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        identity = row.get("id")
        if not isinstance(identity, str) or len(identity) > 256 or not PLUGIN_ID.fullmatch(identity):
            raise InventoryError("plugin identity must include its provider")
        groups.setdefault(identity, []).append(row)

    cartridges = []
    unavailable = []
    for identity, entries in sorted(groups.items()):
        if any(type(entry.get("enabled")) is not bool for entry in entries):
            unavailable.append({"id": identity, "reason": "enablement_unknown"})
            continue
        enabled = [entry for entry in entries if entry["enabled"] is True]
        if not enabled:
            continue
        # More than one selected record is ambiguous even across installation scopes.
        # Let the host resolve it; never pick the highest version or first row.
        if len(enabled) != 1:
            unavailable.append({"id": identity, "reason": "ambiguous_selection"})
            continue
        entry = enabled[0]
        raw_root = entry.get("installPath")
        if not isinstance(raw_root, str) or not raw_root or not Path(raw_root).is_absolute():
            unavailable.append({"id": identity, "reason": "selected_root_unknown"})
            continue
        try:
            root = Path(raw_root).resolve(strict=True)
            if not root.is_dir():
                raise OSError("selected root is not a directory")
            paths = [root / name for name in CONTRACTS]
            # A contract symlink must not redirect adoption outside the selected root.
            if any(not path.resolve().is_relative_to(root) for path in paths):
                unavailable.append({"id": identity, "reason": "contract_outside_selected_root"})
                continue
            if not all(path.is_file() for path in paths):
                continue  # An ordinary installed plugin need not be a cartridge.
        except (OSError, RuntimeError, ValueError):
            unavailable.append({"id": identity, "reason": "selected_root_unreadable"})
            continue
        cartridges.append({
            "id": identity,
            "root": str(root),
            "integrating": str(paths[0]),
            "knowledge_index": str(paths[1]),
        })
    return {"status": "ok", "cartridges": cartridges, "unavailable": unavailable}


def claude_inventory(directory: str) -> bytes:
    path = Path(directory)
    if not path.is_absolute():
        raise InventoryError("session directory must be absolute")
    try:
        path = path.resolve(strict=True)
        if not path.is_dir():
            raise InventoryError("session directory is not a directory")
        result = subprocess.run(
            ["claude", "plugin", "list", "--json"], cwd=path,
            capture_output=True, check=False, timeout=20,
        )
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        raise InventoryError("host inventory unavailable") from exc
    if result.returncode != 0:
        # Raw host output may contain unrelated configuration; do not relay it.
        raise InventoryError("host inventory command failed")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--claude", action="store_true", help="read Claude's installed-plugin inventory")
    source.add_argument("--stdin", action="store_true", help="read an equivalent host inventory from stdin")
    parser.add_argument("--directory", help="absolute native session directory, required with --claude")
    args = parser.parse_args()
    try:
        if args.claude:
            if not args.directory:
                raise InventoryError("Claude inventory requires the native session directory")
            raw = claude_inventory(args.directory)
        else:
            if args.directory:
                raise InventoryError("directory is only used with Claude inventory")
            raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        result = selected_cartridges(parse_inventory(raw))
    except InventoryError as exc:
        print(json.dumps({"status": "unavailable", "cartridges": [], "reason": str(exc)}))
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
