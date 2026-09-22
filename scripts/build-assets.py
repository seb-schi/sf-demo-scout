#!/usr/bin/env python3
"""Prepare owned metadata projects and preserve, verify, and stage source snapshots."""

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Mapping, Sequence, Set, Tuple


RECEIPT_VERSION = 1
VALID_KINDS = {"imports", "agent-recovery", "agent-preedit", "component-preedit"}
BUNDLE_TYPES = {"lwc", "aura", "aiAuthoringBundles", "genAiPlannerBundles"}
COMPANION_TYPES = {"classes": ".cls", "triggers": ".trigger"}
WORKSPACE_RECEIPT_VERSION = 1


class AssetError(Exception):
    """A validation or integrity failure suitable for CLI output."""


def _is_within(path: Path, base: Path) -> bool:
    try:
        return os.path.commonpath((str(path), str(base))) == str(base)
    except ValueError:
        return False


def _paths_overlap(first: Path, second: Path) -> bool:
    return _is_within(first, second) or _is_within(second, first)


def _absolute_path(value: str, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise AssetError("{} must be an absolute path".format(label))
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or str(path) != value:
        raise AssetError("{} must be a normalized absolute path".format(label))
    _reject_symlink_ancestors(path, label)
    return path


def _safe_relative(value: str, label: str = "path") -> PurePosixPath:
    if not isinstance(value, str) or len(value) == 0:
        raise AssetError("{} must be a non-empty relative path".format(label))
    if "\\" in value:
        raise AssetError("{} must use forward slashes".format(label))
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix():
        raise AssetError("{} is not a normalized relative path: {}".format(label, value))
    if len(path.parts) == 0 or any(part in ("", ".", "..") for part in path.parts):
        raise AssetError("{} is unsafe: {}".format(label, value))
    return path


def _lstat(path: Path) -> os.stat_result:
    try:
        return path.lstat()
    except OSError as exc:
        raise AssetError("cannot inspect {}: {}".format(path, exc)) from exc


def _require_plain_directory(path: Path, label: str) -> None:
    info = _lstat(path)
    if stat.S_ISLNK(info.st_mode):
        raise AssetError("{} must not be a symlink: {}".format(label, path))
    if not stat.S_ISDIR(info.st_mode):
        raise AssetError("{} must be a directory: {}".format(label, path))


def _require_plain_file(path: Path, label: str) -> None:
    info = _lstat(path)
    if stat.S_ISLNK(info.st_mode):
        raise AssetError("{} must not be a symlink: {}".format(label, path))
    if not stat.S_ISREG(info.st_mode):
        raise AssetError("{} must be a regular file: {}".format(label, path))


def _reject_symlink_ancestors(path: Path, label: str) -> None:
    """Reject symlinks in the user-spelled path, aside from macOS system aliases."""
    candidate = path if path.is_absolute() else Path.cwd() / path
    current = Path(candidate.anchor)
    allowed_system_aliases = {Path("/tmp"), Path("/var")}
    for part in candidate.parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise AssetError("cannot inspect {} {}: {}".format(label, current, exc)) from exc
        if stat.S_ISLNK(info.st_mode):
            if sys.platform == "darwin" and current in allowed_system_aliases:
                continue
            raise AssetError("{} contains a symlink: {}".format(label, current))


def _existing_chain_has_symlink(
    base: Path, relative: PurePosixPath, label: str = "path"
) -> None:
    current = base
    for part in relative.parts:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise AssetError("cannot inspect {} {}: {}".format(label, current, exc)) from exc
        if stat.S_ISLNK(info.st_mode):
            raise AssetError("{} contains a symlink: {}".format(label, current))


def hash_file(path: Path) -> str:
    """Return a file's SHA-256 digest (a public seam for fault injection)."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_file(source: Path, destination: Path) -> None:
    """Atomically copy one file with owner-only permissions."""
    fd, temporary_name = tempfile.mkstemp(prefix=".asset-copy-", dir=str(destination.parent))
    temporary = Path(temporary_name)
    try:
        with source.open("rb") as input_stream, os.fdopen(fd, "wb") as output_stream:
            fd = -1
            shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        os.chmod(str(temporary), 0o600)
        os.replace(str(temporary), str(destination))
    except Exception:
        if fd >= 0:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def write_receipt(path: Path, receipt: Mapping[str, object]) -> None:
    """Atomically write a receipt (a public seam for fault injection)."""
    fd, temporary_name = tempfile.mkstemp(prefix=".receipt-", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            fd = -1
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(str(temporary), 0o600)
        os.replace(str(temporary), str(path))
    except Exception:
        if fd >= 0:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _read_json_file(path: Path, label: str) -> object:
    _require_plain_file(path, label)
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AssetError("cannot read {}: {}".format(label, exc)) from exc


def _workspace_context(workspace_value: str, customer_value: str) -> Tuple[Path, Path, dict]:
    workspace = _resolved_existing_directory(workspace_value, "workspace root")
    customer = _resolved_existing_directory(customer_value, "customer directory")
    if customer.parent != workspace / "orgs":
        raise AssetError("customer directory must be a direct child of workspace_root/orgs")
    config = _read_json_file(workspace / "sfdx-project.json", "workspace project config")
    if not isinstance(config, dict):
        raise AssetError("workspace project config must be a JSON object")
    packages = config.get("packageDirectories")
    if not isinstance(packages, list) or not any(
        isinstance(entry, dict) and entry.get("path") == "force-app" for entry in packages
    ):
        raise AssetError("workspace packageDirectories must include force-app")
    api_version = config.get("sourceApiVersion")
    if not isinstance(api_version, str) or re.fullmatch(r"[1-9][0-9]*\.0", api_version) is None:
        raise AssetError("workspace sourceApiVersion must be an explicit API version such as 66.0")
    minimal = {
        "packageDirectories": [{"path": "force-app", "default": True}],
        "sourceApiVersion": api_version,
    }
    if "namespace" in config:
        namespace = config["namespace"]
        if not isinstance(namespace, str) or (
            namespace != "" and re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,14}", namespace) is None
        ):
            raise AssetError("workspace namespace must be empty or a valid namespace prefix")
        minimal["namespace"] = namespace
    return workspace, customer, minimal


def _validate_writer(writer: str) -> None:
    if not isinstance(writer, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", writer) is None:
        raise AssetError("writer must be 1-64 letters, digits, underscores or hyphens")


def _owned_paths(workspace: Path, customer: Path, project: Path, writer: str) -> dict:
    return {
        "version": WORKSPACE_RECEIPT_VERSION,
        "writer": writer,
        "workspace_root": str(workspace),
        "customer_dir": str(customer),
        "project_root": str(project),
        "source_root": str(project / "force-app/main/default"),
        "rollback_dir": str(customer / "rollback"),
        "ownership_receipt": str(project / "ownership.json"),
    }


def prepare_workspace(workspace_value: str, customer_value: str, writer: str) -> dict:
    """Create a fresh retained project; preservation remains a separate required gate.

    No existing project is reused, cleared, or copied. The receipt records path
    ownership, not authorization to edit an incumbent or proof of its preservation.
    """
    _validate_writer(writer)
    workspace, customer, config = _workspace_context(workspace_value, customer_value)
    staging = customer / ".scout-work"
    rollback = customer / "rollback"
    for path in (staging, rollback):
        _reject_symlink_ancestors(path, "owned workspace directory")
        if path.exists():
            _require_plain_directory(path, "owned workspace directory")
    _make_directory(staging)
    _make_directory(rollback)
    project = Path(tempfile.mkdtemp(prefix=writer + "-", dir=str(staging)))
    # A failed preparation is retained for inspection, with no success response.
    result = _owned_paths(workspace, customer, project, writer)
    try:
        _make_directory_chain(project, PurePosixPath("force-app/main/default"))
        project_config = project / "sfdx-project.json"
        write_receipt(project_config, config)
        receipt = dict(result, project_config_sha256=hash_file(project_config))
        write_receipt(Path(result["ownership_receipt"]), receipt)
        return verify_workspace(str(project))
    except (OSError, AssetError) as exc:
        raise AssetError("workspace preparation failed; retained {}: {}".format(project, exc)) from exc


def verify_workspace(project_value: str) -> dict:
    """Read-only check of a project's exact recorded boundary and initial config."""
    project = _resolved_existing_directory(project_value, "project root")
    receipt = _read_json_file(project / "ownership.json", "ownership receipt")
    expected_keys = {
        "version", "writer", "workspace_root", "customer_dir", "project_root",
        "source_root", "rollback_dir", "ownership_receipt", "project_config_sha256",
    }
    if not isinstance(receipt, dict) or set(receipt) != expected_keys:
        raise AssetError("ownership receipt has an invalid schema")
    if type(receipt["version"]) is not int or receipt["version"] != WORKSPACE_RECEIPT_VERSION:
        raise AssetError("unsupported ownership receipt version")
    writer = receipt["writer"]
    _validate_writer(writer)
    workspace, customer, _ = _workspace_context(receipt["workspace_root"], receipt["customer_dir"])
    if project.parent != customer / ".scout-work" or not project.name.startswith(writer + "-"):
        raise AssetError("project root is outside its recorded writer/customer boundary")
    expected = _owned_paths(workspace, customer, project, writer)
    if any(receipt[key] != value for key, value in expected.items()):
        raise AssetError("ownership receipt paths do not match their exact derived locations")
    for key in ("source_root", "rollback_dir"):
        _resolved_existing_directory(expected[key], key)
    config_path = project / "sfdx-project.json"
    _require_plain_file(config_path, "owned project config")
    if receipt["project_config_sha256"] != hash_file(config_path):
        raise AssetError("owned project config does not match the ownership receipt")
    return expected


def _scan_tree(root: Path) -> Tuple[Set[str], Dict[str, str]]:
    """Return complete descendant directory and regular-file manifests."""
    _require_plain_directory(root, "tree root")
    directories: Set[str] = set()
    files: Dict[str, str] = {}

    def visit(directory: Path, relative: PurePosixPath) -> None:
        try:
            entries = list(os.scandir(str(directory)))
        except OSError as exc:
            raise AssetError("cannot list {}: {}".format(directory, exc)) from exc
        for entry in entries:
            child_relative = relative / entry.name
            relative_name = child_relative.as_posix()
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise AssetError("cannot inspect {}: {}".format(entry.path, exc)) from exc
            if stat.S_ISLNK(info.st_mode):
                raise AssetError("symlinks are not allowed: {}".format(entry.path))
            if stat.S_ISDIR(info.st_mode):
                directories.add(relative_name)
                visit(Path(entry.path), child_relative)
            elif stat.S_ISREG(info.st_mode):
                try:
                    files[relative_name] = hash_file(Path(entry.path))
                except OSError as exc:
                    raise AssetError("cannot hash {}: {}".format(entry.path, exc)) from exc
            else:
                raise AssetError("special files are not allowed: {}".format(entry.path))

    visit(root, PurePosixPath())
    return directories, files


def _manifest_for_selections(
    root: Path, selections: Sequence[PurePosixPath]
) -> Tuple[Set[str], Dict[str, str]]:
    directories: Set[str] = set()
    files: Dict[str, str] = {}
    for selection in selections:
        _existing_chain_has_symlink(root, selection, "source selection")
        selected = root.joinpath(*selection.parts)
        _require_plain_directory(selected, "source selection")
        child_directories, child_files = _scan_tree(selected)
        if len(child_files) == 0:
            raise AssetError("source selection contains no files: {}".format(selection.as_posix()))
        for parent in reversed(selection.parents):
            if len(parent.parts) > 0:
                directories.add(parent.as_posix())
        directories.add(selection.as_posix())
        directories.update(
            (selection / PurePosixPath(item)).as_posix() for item in child_directories
        )
        files.update(
            {
                (selection / PurePosixPath(name)).as_posix(): digest
                for name, digest in child_files.items()
            }
        )
    return directories, files


def _make_directory(path: Path) -> None:
    created = False
    try:
        path.mkdir(mode=0o700)
        created = True
    except FileExistsError:
        _require_plain_directory(path, "destination directory")
    if created:
        os.chmod(str(path), 0o700)


def _make_directory_chain(base: Path, relative: PurePosixPath) -> None:
    current = base
    for part in relative.parts:
        current = current / part
        _make_directory(current)


def _create_directory_path(path: Path, label: str) -> Path:
    """Create a canonical directory path while rejecting a symlink at its leaf."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        info = None
    except OSError as exc:
        raise AssetError("cannot inspect {} {}: {}".format(label, path, exc)) from exc
    if info is not None and stat.S_ISLNK(info.st_mode):
        raise AssetError("{} must not be a symlink: {}".format(label, path))
    try:
        resolved = path.resolve(strict=False)
        resolved.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise AssetError("cannot create {} {}: {}".format(label, path, exc)) from exc
    _require_plain_directory(resolved, label)
    return resolved


def _copy_manifest(
    source_root: Path,
    destination_root: Path,
    directories: Iterable[str],
    files: Mapping[str, str],
) -> None:
    for name in sorted(directories, key=lambda item: (len(PurePosixPath(item).parts), item)):
        _make_directory_chain(destination_root, PurePosixPath(name))
    for name in sorted(files):
        relative = PurePosixPath(name)
        _make_directory_chain(destination_root, relative.parent)
        try:
            copy_file(
                source_root.joinpath(*relative.parts),
                destination_root.joinpath(*relative.parts),
            )
        except (OSError, AssetError) as exc:
            raise AssetError("failed to copy {}: {}".format(name, exc)) from exc


def _validate_preserve_selections(kind: str, values: Sequence[str]) -> List[PurePosixPath]:
    if kind not in VALID_KINDS:
        raise AssetError("unsupported snapshot kind")
    if len(values) == 0:
        raise AssetError("at least one --path is required")
    selections = [_safe_relative(value, "selection") for value in values]
    if len({item.as_posix() for item in selections}) != len(selections):
        raise AssetError("duplicate selections are not allowed")
    for selection in selections:
        if kind == "agent-recovery" and (
            len(selection.parts) != 2 or selection.parts[0] != "aiAuthoringBundles"
        ):
            raise AssetError(
                "agent recovery requires aiAuthoringBundles/<agent-name> directories"
            )
        if kind == "agent-preedit" and (
            len(selection.parts) != 2
            or selection.parts[0] not in {"aiAuthoringBundles", "genAiPlannerBundles"}
        ):
            raise AssetError(
                "agent pre-edit snapshots require exact authoring/planner bundle directories"
            )
        if kind == "component-preedit":
            if len(selection.parts) < 2:
                raise AssetError(
                    "component pre-edit snapshots require an exact component below its type folder"
                )
            metadata_type = selection.parts[0]
            if metadata_type in BUNDLE_TYPES and len(selection.parts) != 2:
                raise AssetError(
                    "component pre-edit snapshots require a whole {} member directory".format(
                        metadata_type
                    )
                )
            if metadata_type in COMPANION_TYPES:
                suffix = COMPANION_TYPES[metadata_type]
                if len(selection.parts) != 2 or not (
                    selection.name.endswith(suffix)
                    or selection.name.endswith(suffix + "-meta.xml")
                ):
                    raise AssetError(
                        "component pre-edit snapshots require an exact {} component".format(
                            metadata_type
                        )
                    )
    return selections


def _manifest_for_components(
    root: Path, selections: Sequence[PurePosixPath]
) -> Tuple[Set[str], Dict[str, str]]:
    """Build a complete manifest for exact component selectors."""
    directories: Set[str] = set()
    files: Dict[str, str] = {}
    for selection in selections:
        _existing_chain_has_symlink(root, selection, "component selection")
        metadata_type = selection.parts[0]
        selected = root.joinpath(*selection.parts)
        if metadata_type not in BUNDLE_TYPES:
            try:
                info = selected.lstat()
            except OSError as exc:
                raise AssetError(
                    "cannot inspect component selection {}: {}".format(selection, exc)
                ) from exc
            if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise AssetError(
                    "component selection must name one complete file or bundle: {}".format(
                        selection
                    )
                )
        selected_files, selected_directories = _expand_stage_selection(root, selection)
        for relative in selected_directories:
            directories.add(relative.as_posix())
        for relative in selected_files:
            try:
                files[relative.as_posix()] = hash_file(root.joinpath(*relative.parts))
            except OSError as exc:
                raise AssetError("cannot hash {}: {}".format(relative, exc)) from exc
        for relative in [*selected_files, *selected_directories]:
            for parent in relative.parents:
                if len(parent.parts) > 0:
                    directories.add(parent.as_posix())
    return directories, files


def _resolved_existing_directory(value: str, label: str) -> Path:
    path = _absolute_path(value, label)
    _require_plain_directory(path, label)
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise AssetError("cannot resolve {} {}: {}".format(label, path, exc)) from exc


def preserve(source_root_value: str, rollback_dir_value: str, kind: str, values: Sequence[str]) -> dict:
    selections = _validate_preserve_selections(kind, values)
    source_root = _resolved_existing_directory(source_root_value, "source root")

    rollback_dir = _absolute_path(rollback_dir_value, "rollback directory")
    try:
        candidate_rollback_dir = rollback_dir.resolve(strict=False)
    except OSError as exc:
        raise AssetError("cannot resolve rollback directory: {}".format(exc)) from exc
    kind_dir = candidate_rollback_dir / kind
    if _is_within(kind_dir, source_root):
        raise AssetError("rollback destination must be outside the source root")
    if "force-app" in kind_dir.parts:
        raise AssetError("rollback destination must be outside every force-app tree")

    rollback_dir = _create_directory_path(rollback_dir, "rollback directory")
    _make_directory_chain(rollback_dir, PurePosixPath(kind))
    manifest = (
        _manifest_for_components
        if kind == "component-preedit"
        else _manifest_for_selections
    )
    source_directories, source_files = manifest(source_root, selections)

    try:
        artifact = Path(tempfile.mkdtemp(prefix="snapshot-", dir=str(kind_dir))).resolve(strict=True)
    except OSError as exc:
        raise AssetError("cannot create snapshot directory: {}".format(exc)) from exc
    os.chmod(str(artifact), 0o700)
    snapshot_source = artifact / "source"
    _make_directory(snapshot_source)

    _copy_manifest(source_root, snapshot_source, source_directories, source_files)
    current_source_directories, current_source_files = manifest(source_root, selections)
    snapshot_directories, snapshot_files = _scan_tree(snapshot_source)
    if (source_directories, source_files) != (
        current_source_directories,
        current_source_files,
    ):
        raise AssetError("source changed while it was being preserved")
    if (current_source_directories, current_source_files) != (
        snapshot_directories,
        snapshot_files,
    ):
        raise AssetError("snapshot verification failed after copying")

    receipt = {
        "version": RECEIPT_VERSION,
        "kind": kind,
        "paths": [selection.as_posix() for selection in selections],
        "original_source_root": str(source_root),
        "directories": sorted(snapshot_directories),
        "files": dict(sorted(snapshot_files.items())),
    }
    try:
        write_receipt(artifact / "receipt.json", receipt)
    except (OSError, AssetError) as exc:
        raise AssetError("failed to write snapshot receipt: {}".format(exc)) from exc
    return {
        "artifact": str(artifact),
        "source": str(snapshot_source),
        "kind": kind,
        "paths": receipt["paths"],
    }


def _validate_receipt(receipt: object) -> dict:
    if not isinstance(receipt, dict):
        raise AssetError("receipt must be a JSON object")
    expected_keys = {
        "version",
        "kind",
        "paths",
        "original_source_root",
        "directories",
        "files",
    }
    if set(receipt) != expected_keys:
        raise AssetError("receipt has an invalid schema")
    if type(receipt["version"]) is not int or receipt["version"] != RECEIPT_VERSION:
        raise AssetError("unsupported receipt version")
    kind = receipt["kind"]
    if not isinstance(kind, str) or kind not in VALID_KINDS:
        raise AssetError("receipt has an invalid kind")
    path_values = receipt["paths"]
    if not isinstance(path_values, list) or len(path_values) == 0:
        raise AssetError("receipt paths must be a non-empty list")
    if not all(isinstance(value, str) for value in path_values):
        raise AssetError("receipt paths must contain strings")
    paths = _validate_preserve_selections(kind, path_values)

    original_root = receipt["original_source_root"]
    if not isinstance(original_root, str) or not Path(original_root).is_absolute():
        raise AssetError("receipt original_source_root must be absolute")

    directory_values = receipt["directories"]
    if not isinstance(directory_values, list) or not all(
        isinstance(value, str) for value in directory_values
    ):
        raise AssetError("receipt directories must be a list of strings")
    directories = [_safe_relative(value, "receipt directory") for value in directory_values]
    directory_names = [value.as_posix() for value in directories]
    if len(set(directory_names)) != len(directory_names):
        raise AssetError("receipt contains duplicate directories")

    file_values = receipt["files"]
    if not isinstance(file_values, dict) or len(file_values) == 0 or not all(
        isinstance(name, str) and isinstance(digest, str)
        for name, digest in file_values.items()
    ):
        raise AssetError("receipt files must map paths to hashes")
    files: Dict[str, str] = {}
    for name, digest in file_values.items():
        relative = _safe_relative(name, "receipt file").as_posix()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise AssetError("receipt has an invalid SHA-256 digest for {}".format(name))
        files[relative] = digest

    if set(directory_names) & set(files):
        raise AssetError("receipt path is both a file and a directory")
    selected_names = {path.as_posix() for path in paths}
    if kind == "component-preedit":
        if not selected_names.issubset(set(directory_names) | set(files)):
            raise AssetError("receipt does not contain every selected component")
    elif not selected_names.issubset(set(directory_names)):
        raise AssetError("receipt does not contain every selected directory")
    for name in directory_names:
        relative = PurePosixPath(name)
        if not any(
            relative == selected
            or selected in relative.parents
            or relative in selected.parents
            for selected in paths
        ):
            raise AssetError("receipt directory falls outside its selected paths: {}".format(name))
    for name in files:
        relative = PurePosixPath(name)
        covered = any(relative == selected or selected in relative.parents for selected in paths)
        if kind == "component-preedit" and not covered:
            for selected in paths:
                metadata_type = selected.parts[0]
                if metadata_type not in COMPANION_TYPES:
                    continue
                suffix = COMPANION_TYPES[metadata_type]
                selected_name = selected.name
                if selected_name.endswith(suffix + "-meta.xml"):
                    selected_name = selected_name[: -len("-meta.xml")]
                companion_names = {
                    (PurePosixPath(metadata_type) / selected_name).as_posix(),
                    (PurePosixPath(metadata_type) / (selected_name + "-meta.xml")).as_posix(),
                }
                if relative.as_posix() in companion_names:
                    covered = True
                    break
        if not covered:
            raise AssetError("receipt file falls outside its selected paths: {}".format(name))
    if kind == "component-preedit":
        for selected in paths:
            metadata_type = selected.parts[0]
            selected_name = selected.as_posix()
            if metadata_type in BUNDLE_TYPES:
                if selected_name not in set(directory_names) or not any(
                    selected in PurePosixPath(name).parents for name in files
                ):
                    raise AssetError(
                        "receipt does not contain the complete selected bundle: {}".format(
                            selected
                        )
                    )
            elif metadata_type in COMPANION_TYPES:
                suffix = COMPANION_TYPES[metadata_type]
                base_name = selected.name
                if base_name.endswith(suffix + "-meta.xml"):
                    base_name = base_name[: -len("-meta.xml")]
                required = {
                    (PurePosixPath(metadata_type) / base_name).as_posix(),
                    (PurePosixPath(metadata_type) / (base_name + "-meta.xml")).as_posix(),
                }
                if not required.issubset(set(files)):
                    raise AssetError(
                        "receipt does not contain the complete selected component: {}".format(
                            selected
                        )
                    )
            elif selected_name not in files:
                raise AssetError(
                    "receipt does not contain the selected component file: {}".format(selected)
                )
    return {
        "kind": kind,
        "paths": path_values,
        "directories": set(directory_names),
        "files": files,
    }


def verify_artifact(artifact_value: str) -> Tuple[dict, dict]:
    artifact_path = _absolute_path(artifact_value, "artifact")
    _require_plain_directory(artifact_path, "artifact")
    try:
        artifact = artifact_path.resolve(strict=True)
    except OSError as exc:
        raise AssetError("cannot resolve artifact: {}".format(exc)) from exc
    receipt_path = artifact / "receipt.json"
    source = artifact / "source"
    _require_plain_file(receipt_path, "receipt")
    _require_plain_directory(source, "snapshot source")

    root_entries = {entry.name for entry in os.scandir(str(artifact))}
    if root_entries != {"receipt.json", "source"}:
        raise AssetError("artifact contains unexpected root entries")
    try:
        with receipt_path.open("r", encoding="utf-8") as stream:
            receipt_value = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AssetError("cannot read receipt: {}".format(exc)) from exc
    receipt = _validate_receipt(receipt_value)
    directories, files = _scan_tree(source)
    if directories != receipt["directories"]:
        raise AssetError("snapshot directory set does not match the receipt")
    if set(files) != set(receipt["files"]):
        raise AssetError("snapshot file set does not match the receipt")
    changed = [name for name, digest in files.items() if digest != receipt["files"][name]]
    if changed:
        raise AssetError("snapshot file hash mismatch: {}".format(", ".join(sorted(changed))))
    result = {
        "artifact": str(artifact),
        "source": str(source),
        "kind": receipt["kind"],
        "paths": receipt["paths"],
    }
    return result, receipt


def _expand_stage_selection(
    source_root: Path, selection: PurePosixPath
) -> Tuple[List[PurePosixPath], List[PurePosixPath]]:
    if len(selection.parts) < 2:
        raise AssetError("stage selection must name a component below its type folder")
    metadata_type = selection.parts[0]
    selected = source_root.joinpath(*selection.parts)

    if metadata_type in BUNDLE_TYPES:
        if len(selection.parts) != 2:
            raise AssetError("{} requires a whole member directory".format(metadata_type))
        _require_plain_directory(selected, "bundle selection")
        directories, files = _scan_tree(selected)
        if len(files) == 0:
            raise AssetError("bundle selection contains no files: {}".format(selection.as_posix()))
        selected_directories = [selection]
        selected_directories.extend(
            selection / PurePosixPath(name) for name in sorted(directories)
        )
        return (
            [selection / PurePosixPath(name) for name in sorted(files)],
            selected_directories,
        )

    if metadata_type in COMPANION_TYPES:
        suffix = COMPANION_TYPES[metadata_type]
        name = selection.name
        if len(selection.parts) != 2:
            raise AssetError("{} selectors must name one component file".format(metadata_type))
        if name.endswith(suffix + "-meta.xml"):
            base_name = name[: -len("-meta.xml")]
        elif name.endswith(suffix):
            base_name = name
        else:
            raise AssetError("invalid {} component selector: {}".format(metadata_type, selection))
        source_file = PurePosixPath(metadata_type) / base_name
        companion = PurePosixPath(metadata_type) / (base_name + "-meta.xml")
        _require_plain_file(source_root.joinpath(*source_file.parts), "component source")
        _require_plain_file(source_root.joinpath(*companion.parts), "metadata companion")
        return [source_file, companion], []

    try:
        info = selected.lstat()
    except OSError as exc:
        raise AssetError("cannot inspect stage selection {}: {}".format(selection, exc)) from exc
    if stat.S_ISLNK(info.st_mode):
        raise AssetError("stage selection must not be a symlink: {}".format(selection))
    if stat.S_ISREG(info.st_mode):
        return [selection], []
    if stat.S_ISDIR(info.st_mode):
        directories, files = _scan_tree(selected)
        if len(files) == 0:
            raise AssetError("stage selection contains no files: {}".format(selection))
        selected_directories = [selection]
        selected_directories.extend(
            selection / PurePosixPath(name) for name in sorted(directories)
        )
        return (
            [selection / PurePosixPath(name) for name in sorted(files)],
            selected_directories,
        )
    raise AssetError("stage selection must be a file or directory: {}".format(selection))


def _validate_stage_destinations(
    project_root: Path,
    artifact: Path,
    relative_files: Sequence[PurePosixPath],
    relative_directories: Sequence[PurePosixPath],
) -> Path:
    _reject_symlink_ancestors(project_root, "project root")
    _require_plain_directory(project_root, "project root")
    project_root = project_root.resolve(strict=True)
    destination_root = project_root / "force-app" / "main" / "default"
    if _paths_overlap(destination_root, artifact):
        raise AssetError("stage destination must not overlap the snapshot artifact")
    root_relative = PurePosixPath("force-app/main/default")
    _existing_chain_has_symlink(project_root, root_relative)
    for relative in relative_directories:
        destination = destination_root.joinpath(*relative.parts)
        _existing_chain_has_symlink(destination_root, relative, "destination path")
        try:
            info = destination.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise AssetError("cannot inspect destination {}: {}".format(destination, exc)) from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise AssetError("destination is not a directory: {}".format(destination))
    for relative in relative_files:
        destination = destination_root.joinpath(*relative.parts)
        if not _is_within(destination, destination_root):
            raise AssetError("stage destination escapes force-app/main/default")
        _existing_chain_has_symlink(destination_root, relative)
        current = destination_root
        for part in relative.parts[:-1]:
            current = current / part
            try:
                info = current.lstat()
            except FileNotFoundError:
                break
            except OSError as exc:
                raise AssetError("cannot inspect destination {}: {}".format(current, exc)) from exc
            if not stat.S_ISDIR(info.st_mode):
                raise AssetError("destination parent is not a directory: {}".format(current))
        try:
            info = destination.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise AssetError("cannot inspect destination {}: {}".format(destination, exc)) from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise AssetError("destination is not a regular file: {}".format(destination))
    return destination_root


def stage(artifact_value: str, project_root_value: str, values: Sequence[str]) -> dict:
    """Stage complete selected components; generic metadata completeness is caller-owned."""
    verified, receipt = verify_artifact(artifact_value)
    if verified["kind"] not in {"imports", "component-preedit"}:
        raise AssetError("only import and component pre-edit snapshots can be staged")
    if len(values) == 0:
        raise AssetError("at least one --path is required")
    selections = [_safe_relative(value, "stage selection") for value in values]
    if len({item.as_posix() for item in selections}) != len(selections):
        raise AssetError("duplicate stage selections are not allowed")
    if verified["kind"] == "component-preedit":
        preserved_selections = set(receipt["paths"])
        unexpected = [
            selection.as_posix()
            for selection in selections
            if selection.as_posix() not in preserved_selections
        ]
        if unexpected:
            raise AssetError(
                "component restore must use exact receipt selections: {}".format(
                    ", ".join(sorted(unexpected))
                )
            )

    source_root = Path(verified["source"])
    relative_files: List[PurePosixPath] = []
    relative_directories: List[PurePosixPath] = []
    for selection in selections:
        selection_files, selection_directories = _expand_stage_selection(
            source_root, selection
        )
        relative_files.extend(selection_files)
        relative_directories.extend(selection_directories)
    unique_files = sorted(set(relative_files), key=lambda value: value.as_posix())
    unique_directories = sorted(
        set(relative_directories), key=lambda value: (len(value.parts), value.as_posix())
    )
    if len(unique_files) == 0:
        raise AssetError("stage selection contains no files")
    receipt_files = set(receipt["files"])
    for relative in unique_files:
        if relative.as_posix() not in receipt_files:
            raise AssetError("stage selection is not covered by the snapshot: {}".format(relative))

    project_root = _absolute_path(project_root_value, "project root")
    destination_root = _validate_stage_destinations(
        project_root,
        Path(verified["artifact"]),
        unique_files,
        unique_directories,
    )
    _make_directory_chain(project_root.resolve(strict=True), PurePosixPath("force-app/main/default"))
    for relative in unique_directories:
        _make_directory_chain(destination_root, relative)
    for relative in unique_files:
        destination = destination_root.joinpath(*relative.parts)
        _make_directory_chain(destination_root, relative.parent)
        source = source_root.joinpath(*relative.parts)
        try:
            copy_file(source, destination)
        except (OSError, AssetError) as exc:
            raise AssetError("failed to stage {}: {}".format(relative, exc)) from exc
        try:
            if hash_file(source) != hash_file(destination):
                raise AssetError("staged byte verification failed for {}".format(relative))
        except OSError as exc:
            raise AssetError("cannot verify staged file {}: {}".format(relative, exc)) from exc

    verify_artifact(verified["artifact"])
    result = dict(verified)
    result["staged"] = [relative.as_posix() for relative in unique_files]
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    workspace_parser = subparsers.add_parser("prepare-workspace", help="create a retained owned project")
    workspace_parser.add_argument("--workspace-root", required=True)
    workspace_parser.add_argument("--customer-dir", required=True)
    workspace_parser.add_argument("--writer", required=True)

    owned_verify_parser = subparsers.add_parser("verify-workspace", help="verify an owned project")
    owned_verify_parser.add_argument("--project-root", required=True)

    preserve_parser = subparsers.add_parser("preserve", help="create a durable snapshot")
    preserve_parser.add_argument("--source-root", required=True)
    preserve_parser.add_argument("--rollback-dir", required=True)
    preserve_parser.add_argument("--kind", choices=sorted(VALID_KINDS), required=True)
    preserve_parser.add_argument("--path", action="append", required=True)

    verify_parser = subparsers.add_parser("verify", help="verify a snapshot receipt")
    verify_parser.add_argument("--artifact", required=True)

    stage_parser = subparsers.add_parser("stage", help="stage explicit import components")
    stage_parser.add_argument("--artifact", required=True)
    stage_parser.add_argument("--project-root", required=True)
    stage_parser.add_argument("--path", action="append", required=True)
    return parser


def main(argv: Sequence[str] = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "prepare-workspace":
            result = prepare_workspace(arguments.workspace_root, arguments.customer_dir, arguments.writer)
        elif arguments.command == "verify-workspace":
            result = verify_workspace(arguments.project_root)
        elif arguments.command == "preserve":
            result = preserve(
                arguments.source_root,
                arguments.rollback_dir,
                arguments.kind,
                arguments.path,
            )
        elif arguments.command == "verify":
            result, _ = verify_artifact(arguments.artifact)
        else:
            result = stage(arguments.artifact, arguments.project_root, arguments.path)
    except Exception as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
