#!/usr/bin/env python3
"""Prove that the active setup CLI is owned by the current global npm."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


CLIS = {
    "sf": ("@salesforce/cli", "sf"),
    "claude": ("@anthropic-ai/claude-code", "claude"),
}


def npm_ownership(selector: str, npm_arg: str, active_arg: str) -> str:
    package_name, bin_name = CLIS[selector]
    npm = Path(npm_arg)
    active = Path(active_arg)
    if not npm.is_absolute() or not active.is_absolute():
        return "unavailable"
    try:
        probe = subprocess.run(
            [str(npm), "root", "-g"],
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
        roots = [line.strip() for line in probe.stdout.splitlines() if line.strip()]
        if probe.returncode != 0 or len(roots) != 1:
            return "unavailable"
        root = Path(roots[0])
        if not root.is_absolute():
            return "unavailable"
        package_dir = root.joinpath(*package_name.split("/"))
        metadata = json.loads((package_dir / "package.json").read_text())
        if not isinstance(metadata, dict):
            return "unavailable"
        if metadata.get("name") != package_name:
            return "unavailable"
        bins = metadata.get("bin")
        if isinstance(bins, str):
            if bin_name != package_name.rsplit("/", 1)[-1]:
                return "unavailable"
            relative_bin = bins
        elif isinstance(bins, dict) and isinstance(bins.get(bin_name), str):
            relative_bin = bins[bin_name]
        else:
            return "unavailable"
        relative = Path(relative_bin)
        if relative.is_absolute() or ".." in relative.parts:
            return "unavailable"
        resolved_package = package_dir.resolve(strict=True)
        expected = (resolved_package / relative).resolve(strict=True)
        if resolved_package not in expected.parents:
            return "unavailable"
        if not expected.is_file() or not os.access(expected, os.X_OK):
            return "unavailable"
        return "owned" if Path(active).resolve(strict=True) == expected else "different"
    except (
        json.JSONDecodeError,
        OSError,
        subprocess.SubprocessError,
        UnicodeError,
        ValueError,
    ):
        return "unavailable"


def main() -> int:
    if len(sys.argv) != 4 or sys.argv[1] not in CLIS:
        return 64
    print(npm_ownership(sys.argv[1], sys.argv[2], sys.argv[3]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
