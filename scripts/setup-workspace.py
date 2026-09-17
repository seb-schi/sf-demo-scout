#!/usr/bin/env python3
"""Create and verify Scout's mandatory workspace state without clobbering files."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import NoReturn


LESSONS_INDEX = """# Lessons Index

Topic-clustered lessons from scout-sparring + scout-building sessions.
This INDEX is loaded at the start of every session; topic files are
loaded on demand based on the descriptive lines below.

Each lesson is whole — it may carry both a sparring rule and a building
backstop. Lessons are not split by phase. Add new lessons to the topic
file that best fits; create a new topic + INDEX line if none fit.

## Topics

- **agentforce.md** — Agentforce agent build + iteration: action-invocation-as-proof, GenAiPlannerBundle safety, enhanced-event-log diagnostics, pre-Agent-Script (Atlas/UI-built) agent handling, headless/Agent API recipes, agent action schema.
- **managed-packages.md** — Managed-package write/read restrictions and schema quirks (lsc4ce / LSC, Health Cloud, FSC, industry clouds): namespaced retrieve names, trigger/validation DML gates, stage-gated field locks, territory/sharing blast radius.
- **flow.md** — Flow + FlowTest: generated-flow defect patterns, FlowTest XML schema, CLI flow-run breakage, record-triggered vs screen flow gotchas.
- **data-seeding.md** — Data seeding: CLI `sf data` envelope/Bash quirks, pilot-self-test limits, pricebook/SKU gating, paired-record cleanup, idempotency.
- **metadata-deploy.md** — Org-SPECIFIC metadata deploy/parse gotchas (distinct from the org-agnostic Known Deploy-Error Patterns catalog): roll-up-summary relationship traps, permset description limits, field/picklist verification, RT-specific values.
- **discovery-and-scoping.md** — Sparring heuristics: customer-evidence gate, reuse-orgs-aggressively, booth-vs-WorldTour scoping, existing-first object/field probing, marketed-vs-shorthand product names, data-quality-before-reuse.
- **lwc-slds.md** — LWC + SLDS: internal-token hard-fails, SLDS2 utility/global-hook fixes, Code Analyzer deprecation warnings.
"""


class SetupFailure(Exception):
    """A fail-closed setup result with a stable outcome token."""

    def __init__(self, token: str, detail: str) -> None:
        super().__init__(detail)
        self.token = token
        self.detail = detail


def fail(token: str, detail: str) -> NoReturn:
    raise SetupFailure(token, detail)


def path_present(path: Path) -> bool:
    """Return true for filesystem entries, including dangling symlinks."""
    return path.exists() or path.is_symlink()


def explicit_path(value: str, label: str) -> Path:
    try:
        path = Path(value)
        if not path.is_absolute():
            fail("INVALID_ARGUMENT", f"{label} must be an absolute path")
        if path.is_symlink() and not path.exists():
            fail("INVALID_ARGUMENT", f"{label} must not be a dangling symlink")
        return path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as error:
        fail("INVALID_ARGUMENT", f"cannot resolve {label}: {error}")


def load_json_object(path: Path, token: str) -> dict[str, object]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(token, f"{path}: {error}")
    if not isinstance(value, dict):
        fail(token, f"{path}: expected a JSON object")
    return value


def validate_project(path: Path) -> dict[str, object]:
    if not path.is_file():
        fail("SFDX_PROJECT_INVALID", f"missing regular file: {path}")
    project = load_json_object(path, "SFDX_PROJECT_INVALID")
    directories = project.get("packageDirectories")
    if not isinstance(directories, list) or not any(
        isinstance(entry, dict) and entry.get("path") == "force-app"
        for entry in directories
    ):
        fail("SFDX_PROJECT_INVALID", "packageDirectories must include force-app")
    return project


def validate_settings(path: Path) -> dict[str, object]:
    if not path.is_file():
        fail("SETTINGS_INVALID", f"missing regular file: {path}")
    return load_json_object(path, "SETTINGS_INVALID")


def validate_config(path: Path, workspace: Path) -> dict[str, object]:
    if not path.is_file():
        fail("CONFIG_INVALID", f"missing regular file: {path}")
    config = load_json_object(path, "CONFIG_INVALID")
    configured_workspace = config.get("workspace_path")
    if not isinstance(configured_workspace, str):
        fail("CONFIG_INVALID", "workspace_path must be a string")
    configured_path = Path(configured_workspace)
    if not configured_path.is_absolute() or configured_path.resolve(strict=False) != workspace:
        fail("CONFIG_INVALID", "workspace_path does not match the verified workspace")
    if config.get("install_method") != "plugin":
        fail("CONFIG_INVALID", "install_method must be plugin")
    if not isinstance(config.get("plugin_version"), str) or not config["plugin_version"]:
        fail("CONFIG_INVALID", "plugin_version must be a non-empty string")
    if not isinstance(config.get("setup_completed_at"), str) or not config["setup_completed_at"]:
        fail("CONFIG_INVALID", "setup_completed_at must be a non-empty string")
    return config


def atomic_write(path: Path, content: bytes, token: str) -> None:
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as error:
        fail(token, f"{path}: {error}")
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def run_sf_scaffold(workspace: Path) -> tuple[Path, tempfile.TemporaryDirectory[str]]:
    sf_executable = shutil.which("sf")
    if sf_executable is None:
        fail("SFDX_GENERATE_FAILED", "sf executable is unavailable")
    try:
        staging = tempfile.TemporaryDirectory(
            prefix=".scout-sfdx-", dir=workspace.parent
        )
    except OSError as error:
        fail("SFDX_GENERATE_FAILED", f"cannot create staging directory: {error}")
    try:
        result = subprocess.run(
            [
                sf_executable,
                "project",
                "generate",
                "--name",
                "sf-demo-scout",
                "--template",
                "empty",
                "--output-dir",
                staging.name,
                "--json",
            ],
            cwd=staging.name,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as error:
        staging.cleanup()
        fail("SFDX_GENERATE_FAILED", str(error))
    if result.returncode != 0:
        staging.cleanup()
        fail("SFDX_GENERATE_FAILED", f"sf exited {result.returncode}")
    try:
        payload = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        staging.cleanup()
        fail("SFDX_GENERATE_UNVERIFIED", f"invalid sf JSON: {error}")
    if (
        not isinstance(payload, dict)
        or type(payload.get("status")) is not int
        or payload["status"] != 0
    ):
        staging.cleanup()
        fail("SFDX_GENERATE_UNVERIFIED", "sf JSON did not report integer status 0")
    staged_project = Path(staging.name) / "sf-demo-scout"
    try:
        validate_project(staged_project / "sfdx-project.json")
        staged_force_app = staged_project / "force-app"
        if staged_force_app.is_symlink() or not staged_force_app.is_dir():
            fail(
                "SFDX_GENERATE_UNVERIFIED",
                "generated force-app must be a real directory",
            )
        for entry in staged_force_app.rglob("*"):
            if entry.is_symlink() or not (entry.is_file() or entry.is_dir()):
                fail(
                    "SFDX_GENERATE_UNVERIFIED",
                    f"generated force-app contains an unsafe entry: {entry}",
                )
    except OSError as error:
        staging.cleanup()
        fail("SFDX_GENERATE_UNVERIFIED", str(error))
    except SetupFailure as error:
        staging.cleanup()
        fail("SFDX_GENERATE_UNVERIFIED", error.detail)
    return staged_project, staging


def install_force_app(staged_project: Path, workspace: Path) -> None:
    force_app = workspace / "force-app"
    if path_present(force_app):
        if force_app.is_symlink() or not force_app.is_dir():
            fail(
                "FORCE_APP_INVALID",
                f"existing path must be a real directory: {force_app}",
            )
        return
    try:
        with tempfile.TemporaryDirectory(
            prefix=".force-app-stage-", dir=workspace
        ) as copy_stage_name:
            copy_stage = Path(copy_stage_name) / "force-app"
            shutil.copytree(staged_project / "force-app", copy_stage)
            if path_present(force_app):
                if force_app.is_symlink() or not force_app.is_dir():
                    fail(
                        "FORCE_APP_INVALID",
                        f"existing path must be a real directory: {force_app}",
                    )
            else:
                os.replace(copy_stage, force_app)
    except SetupFailure:
        raise
    except OSError as error:
        fail("FORCE_APP_COPY_FAILED", str(error))


def install_scaffold(workspace: Path) -> None:
    project_path = workspace / "sfdx-project.json"
    force_app = workspace / "force-app"
    if path_present(force_app) and (
        force_app.is_symlink() or not force_app.is_dir()
    ):
        fail(
            "FORCE_APP_INVALID",
            f"existing path must be a real directory: {force_app}",
        )
    if path_present(project_path):
        validate_project(project_path)
        if not path_present(force_app):
            staged_project, staging = run_sf_scaffold(workspace)
            try:
                install_force_app(staged_project, workspace)
            finally:
                staging.cleanup()
            print("FORCE_APP_REPAIRED")
        print("SFDX_PRESENT")
        return

    staged_project, staging = run_sf_scaffold(workspace)
    try:
        install_force_app(staged_project, workspace)
        project_bytes = (staged_project / "sfdx-project.json").read_bytes()
        atomic_write(project_path, project_bytes, "SFDX_PROJECT_WRITE_FAILED")
    except OSError as error:
        fail("SFDX_PROJECT_WRITE_FAILED", str(error))
    finally:
        staging.cleanup()
    validate_project(project_path)
    print("SFDX_INITIALISED")


def ensure_lessons(workspace: Path) -> None:
    index = workspace / "orgs" / "lessons" / "INDEX.md"
    if path_present(index):
        if not index.is_file():
            fail("LESSONS_INVALID", f"existing path is not a regular file: {index}")
        print("LESSONS_PRESENT")
        return
    atomic_write(index, LESSONS_INDEX.encode("utf-8"), "LESSONS_WRITE_FAILED")
    print("LESSONS_WRITTEN")


def ensure_settings(workspace: Path, template: Path) -> None:
    settings = workspace / ".claude" / "settings.json"
    if path_present(settings):
        validate_settings(settings)
        print("SETTINGS_PRESENT")
        return
    if not template.is_file():
        fail("SETTINGS_TEMPLATE_INVALID", f"missing regular file: {template}")
    load_json_object(template, "SETTINGS_TEMPLATE_INVALID")
    try:
        content = template.read_bytes()
    except OSError as error:
        fail("SETTINGS_TEMPLATE_INVALID", str(error))
    atomic_write(settings, content, "SETTINGS_WRITE_FAILED")
    validate_settings(settings)
    print("SETTINGS_WRITTEN")


def ensure_config(config_path: Path, workspace: Path, plugin_version: str) -> None:
    if path_present(config_path):
        if not config_path.is_file():
            fail("CONFIG_WRITE_FAILED", f"existing path is not a regular file: {config_path}")
        validate_config(config_path, workspace)
        print("CONFIG_PRESENT")
        return
    if not plugin_version:
        fail("INVALID_ARGUMENT", "plugin-version must be non-empty")
    content = {
        "workspace_path": str(workspace),
        "install_method": "plugin",
        "plugin_version": plugin_version,
        "setup_completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    atomic_write(
        config_path,
        (json.dumps(content, indent=2) + "\n").encode("utf-8"),
        "CONFIG_WRITE_FAILED",
    )
    validate_config(config_path, workspace)
    print("CONFIG_WRITTEN")


def verify(workspace: Path, config_path: Path) -> None:
    if not workspace.is_dir():
        fail("WORKSPACE_INVALID", f"missing directory: {workspace}")
    validate_project(workspace / "sfdx-project.json")
    force_app = workspace / "force-app"
    if force_app.is_symlink() or not force_app.is_dir():
        fail("FORCE_APP_INVALID", "force-app must be a real directory")
    lessons = workspace / "orgs" / "lessons" / "INDEX.md"
    if not lessons.is_file():
        fail("LESSONS_INVALID", f"missing regular file: {lessons}")
    validate_settings(workspace / ".claude" / "settings.json")
    validate_config(config_path, workspace)


def setup(workspace: Path, config: Path, template: Path, plugin_version: str) -> None:
    try:
        workspace.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        fail("WORKSPACE_INVALID", str(error))
    if not workspace.is_dir():
        fail("WORKSPACE_INVALID", f"not a directory: {workspace}")
    install_scaffold(workspace)
    ensure_lessons(workspace)
    ensure_settings(workspace, template)
    ensure_config(config, workspace, plugin_version)
    verify(workspace, config)
    print("WORKSPACE_READY")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    setup_parser = subparsers.add_parser("setup")
    setup_parser.add_argument("--workspace", required=True)
    setup_parser.add_argument("--config", required=True)
    setup_parser.add_argument("--template", required=True)
    setup_parser.add_argument("--plugin-version", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--workspace", required=True)
    verify_parser.add_argument("--config", required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    try:
        workspace = explicit_path(arguments.workspace, "workspace")
        config = explicit_path(arguments.config, "config")
        if arguments.command == "setup":
            template = explicit_path(arguments.template, "template")
            setup(workspace, config, template, arguments.plugin_version)
        else:
            verify(workspace, config)
            print("WORKSPACE_READY")
    except SetupFailure as error:
        print(f"{error.token}: {error.detail}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
