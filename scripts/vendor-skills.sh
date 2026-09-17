#!/bin/bash
# SF Demo Scout — safe skill vendoring (maintainer-only).
#
# Usage: bash scripts/vendor-skills.sh
#
# The manifest is validated in full before this command clones or changes any
# skill directory. Each replace-policy skill is staged beside skills/, checked,
# and installed with a recoverable old-tree backup. Adapted and
# frozen skills are reported and left untouched for deliberate manual review.
#
# Prerequisite: Python 3 with PyYAML (`python3 -m pip install --user pyyaml`).
# Exit 0 means every requested replacement succeeded. Exit 1 is a manifest or
# prerequisite error; exit 2 is a lock, clone, copy, publication, or recovery
# failure. Successful earlier replacements are not rolled back when a later,
# unrelated skill fails.

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="$PLUGIN_ROOT/skills-manifest.yaml"
SKILLS_DIR="$PLUGIN_ROOT/skills"

exec python3 -B - "$PLUGIN_ROOT" "$MANIFEST" "$SKILLS_DIR" <<'PYTHON'
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid

try:
    import yaml
except ImportError:
    print(
        "ERROR: python3 yaml module missing. Install: python3 -m pip install --user pyyaml",
        file=sys.stderr,
    )
    raise SystemExit(1)


PLUGIN_ROOT = Path(sys.argv[1]).resolve()
MANIFEST = Path(sys.argv[2])
SKILLS_DIR = Path(sys.argv[3])
LOCK_DIR = PLUGIN_ROOT / ".vendor-skills.lock"
SAFE_IDENTIFIER = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
POLICIES = {"replace", "adapted", "frozen"}


class ManifestError(Exception):
    pass


class VendorError(Exception):
    pass


class VendorInterrupted(BaseException):
    pass


def clean_detail(value: object) -> str:
    return " ".join(str(value).split()) or "unknown error"


def confined_relative_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ManifestError(f"{label} must be a nonempty POSIX relative path")
    path = PurePosixPath(value)
    if (
        value in {".", ".."}
        or path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ManifestError(f"{label} escapes its declared root: {value!r}")
    if any(ord(character) < 32 for character in value):
        raise ManifestError(f"{label} contains control characters")
    return value


def load_manifest() -> tuple[dict[str, dict], list[dict]]:
    if not MANIFEST.is_file():
        raise ManifestError(f"manifest not found at {MANIFEST}")
    try:
        raw = yaml.safe_load(MANIFEST.read_text())
    except (OSError, yaml.YAMLError) as error:
        raise ManifestError(f"cannot parse manifest: {clean_detail(error)}") from error
    if not isinstance(raw, dict):
        raise ManifestError("manifest root must be a mapping")

    raw_sources = raw.get("sources")
    if not isinstance(raw_sources, dict):
        raise ManifestError("sources must be a mapping")
    sources: dict[str, dict] = {}
    for source_name, source in raw_sources.items():
        if not isinstance(source_name, str) or not SAFE_IDENTIFIER.fullmatch(source_name):
            raise ManifestError(f"unsafe source name: {source_name!r}")
        if not isinstance(source, dict):
            raise ManifestError(f"source {source_name!r} must be a mapping")
        if source.get("type") != "clone":
            raise ManifestError(f"source {source_name!r} must declare type: clone")
        repo = source.get("repo")
        revision = source.get("revision")
        branch = source.get("branch")
        if (
            not isinstance(repo, str)
            or not repo.strip()
            or any(ord(character) < 32 for character in repo)
        ):
            raise ManifestError(f"source {source_name!r} has an invalid repo")
        if not isinstance(revision, str) or not FULL_SHA.fullmatch(revision):
            raise ManifestError(
                f"source {source_name!r} revision must be a lowercase 40-character SHA"
            )
        if branch is not None and (not isinstance(branch, str) or not branch.strip()):
            raise ManifestError(f"source {source_name!r} branch must be descriptive text")
        sources[source_name] = {
            "repo": repo,
            "revision": revision,
            "branch": branch or "(not declared)",
        }

    raw_skills = raw.get("skills")
    if not isinstance(raw_skills, list) or not raw_skills:
        raise ManifestError("skills must be a nonempty list")
    skills: list[dict] = []
    seen: set[str] = set()
    for index, skill in enumerate(raw_skills):
        label = f"skills[{index}]"
        if not isinstance(skill, dict):
            raise ManifestError(f"{label} must be a mapping")
        name = skill.get("name")
        if not isinstance(name, str) or not SAFE_IDENTIFIER.fullmatch(name):
            raise ManifestError(f"{label} has an unsafe name: {name!r}")
        if name in seen:
            raise ManifestError(f"duplicate skill name: {name}")
        seen.add(name)
        policy = skill.get("policy")
        if not isinstance(policy, str) or policy not in POLICIES:
            raise ManifestError(f"{name} has missing or unknown policy: {policy!r}")
        reason = skill.get("reason")
        if policy in {"adapted", "frozen"} and (
            not isinstance(reason, str) or not reason.strip()
        ):
            raise ManifestError(f"{name} policy {policy} requires a nonempty reason")

        source_name = skill.get("source")
        source_path = skill.get("path")
        has_source = source_name is not None or source_path is not None
        if has_source:
            if not isinstance(source_name, str) or source_name not in sources:
                raise ManifestError(f"{name} declares an unknown source: {source_name!r}")
            source_path = confined_relative_path(source_path, f"{name} path")
        elif policy != "frozen":
            raise ManifestError(f"{name} policy {policy} requires source and path")
        skills.append(
            {
                "name": name,
                "policy": policy,
                "reason": reason.strip() if isinstance(reason, str) else "",
                "source": source_name,
                "path": source_path,
            }
        )
    return sources, skills


def validate_skills_root(skills: list[dict]) -> None:
    expected = PLUGIN_ROOT / "skills"
    if SKILLS_DIR.name != "skills" or SKILLS_DIR.parent.resolve() != PLUGIN_ROOT:
        raise ManifestError(f"skills root is not the plugin skills directory: {SKILLS_DIR}")
    if SKILLS_DIR.is_symlink() or not SKILLS_DIR.is_dir():
        raise ManifestError(f"skills root must be an existing real directory: {SKILLS_DIR}")
    if SKILLS_DIR.resolve() != expected.resolve():
        raise ManifestError(f"skills root identity mismatch: {SKILLS_DIR}")
    for skill in skills:
        target = SKILLS_DIR / skill["name"]
        if target.is_symlink():
            raise ManifestError(f"unsafe target symlink for {skill['name']}: {target}")
        if target.exists() and not target.is_dir():
            raise ManifestError(f"skill target is not a directory for {skill['name']}: {target}")


def run_git(arguments: list[str]) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = clean_detail(completed.stderr or completed.stdout)
        raise VendorError(f"git {' '.join(arguments[:2])} failed: {detail}")
    return completed.stdout.strip()


def clone_source(source_name: str, source: dict, clone_root: Path) -> Path:
    clone_dir = clone_root / source_name
    run_git(
        [
            "clone",
            "--quiet",
            "--no-checkout",
            "--filter=blob:none",
            "--depth",
            "1",
            "--",
            source["repo"],
            str(clone_dir),
        ]
    )
    run_git(
        [
            "-C",
            str(clone_dir),
            "fetch",
            "--quiet",
            "--depth",
            "1",
            "origin",
            source["revision"],
        ]
    )
    run_git(
        [
            "-C",
            str(clone_dir),
            "checkout",
            "--quiet",
            "--detach",
            "FETCH_HEAD",
        ]
    )
    actual_revision = run_git(["-C", str(clone_dir), "rev-parse", "HEAD"])
    if actual_revision != source["revision"]:
        raise VendorError(
            f"checkout revision mismatch for {source_name}: "
            f"expected {source['revision']}, got {actual_revision or '(empty)'}"
        )
    print(
        f"CLONED={source_name} repo={source['repo']} revision={actual_revision} "
        f"branch={source['branch']}"
    )
    return clone_dir


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def validate_source_tree(source_path: Path, clone_dir: Path, skill_name: str) -> None:
    clone_real = clone_dir.resolve()
    if source_path.is_symlink() or not source_path.is_dir():
        raise VendorError(f"source path is not a real directory for {skill_name}: {source_path}")
    source_real = source_path.resolve()
    if not path_is_within(source_real, clone_real):
        raise VendorError(f"source path escapes clone for {skill_name}: {source_path}")
    current = clone_dir
    for part in source_path.relative_to(clone_dir).parts:
        current = current / part
        if current.is_symlink():
            raise VendorError(f"source path contains a symlink for {skill_name}: {current}")
    for root, directories, files in os.walk(source_path, followlinks=False):
        for entry in [*directories, *files]:
            candidate = Path(root) / entry
            if candidate.is_symlink():
                raise VendorError(f"source tree contains a symlink for {skill_name}: {candidate}")


def validate_staged_tree(staged: Path, skill_name: str) -> None:
    skill_md = staged / "SKILL.md"
    if skill_md.is_symlink() or not skill_md.is_file() or skill_md.stat().st_size == 0:
        raise VendorError(f"staged {skill_name} must contain a regular nonempty SKILL.md")


def publish_skill(source_path: Path, target: Path, skill_name: str) -> tuple[str | None, bool]:
    stage_container = Path(
        tempfile.mkdtemp(prefix=f".{skill_name}.stage-", dir=SKILLS_DIR)
    )
    os.chmod(stage_container, 0o700)
    staged = stage_container / "new"
    backup = SKILLS_DIR / f".{skill_name}.backup-{uuid.uuid4().hex}"
    had_target = target.exists()
    try:
        shutil.copytree(source_path, staged, symlinks=False)
        validate_staged_tree(staged, skill_name)
        if target.is_symlink() or (target.exists() and not target.is_dir()):
            raise VendorError(f"target became unsafe before publication: {target}")
        try:
            if had_target:
                os.replace(target, backup)
            os.replace(staged, target)
        except BaseException as publish_error:
            # A signal can arrive after os.replace completed but before it
            # returned control to Python. The filesystem state is authoritative:
            # a consumed stage plus a real target means the install committed.
            if not staged.exists() and target.is_dir() and not target.is_symlink():
                backup_detail = (
                    f"; BACKUP_PATH={backup}" if backup.exists() else ""
                )
                message = (
                    f"installed {skill_name}, but publication confirmation failed: "
                    f"{clean_detail(publish_error)}{backup_detail}"
                )
                print(message, file=sys.stderr)
                interrupted = isinstance(
                    publish_error, (KeyboardInterrupt, VendorInterrupted)
                )
                return message, interrupted
            restored = False
            if backup.exists():
                try:
                    os.replace(backup, target)
                    restored = True
                except BaseException as restore_error:
                    message = (
                        f"publication failed for {skill_name}: {clean_detail(publish_error)}; "
                        f"rollback failed: {clean_detail(restore_error)}; "
                        f"RECOVERY_PATH={backup}"
                    )
                    print(message, file=sys.stderr)
                    if isinstance(publish_error, (KeyboardInterrupt, VendorInterrupted)):
                        raise VendorInterrupted(message) from publish_error
                    raise VendorError(message) from publish_error
            suffix = "; restored previous tree" if restored else ""
            message = (
                f"publication failed for {skill_name}: {clean_detail(publish_error)}{suffix}"
            )
            print(message)
            if isinstance(publish_error, (KeyboardInterrupt, VendorInterrupted)):
                raise VendorInterrupted(message) from publish_error
            raise VendorError(message) from publish_error

        # Publication is committed once staged -> target succeeds. Backup
        # cleanup is deliberately outside the rollback window: a cleanup
        # error must not overwrite the newly installed, complete tree.
        if backup.exists():
            try:
                shutil.rmtree(backup)
            except BaseException as cleanup_error:
                message = (
                    f"installed {skill_name}, but old-backup cleanup failed: "
                    f"{clean_detail(cleanup_error)}; BACKUP_PATH={backup}"
                )
                print(message, file=sys.stderr)
                interrupted = isinstance(
                    cleanup_error, (KeyboardInterrupt, VendorInterrupted)
                )
                return message, interrupted
        return None, False
    except VendorInterrupted:
        raise
    except VendorError:
        raise
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, VendorInterrupted)):
            raise VendorInterrupted(f"interrupted while staging {skill_name}") from error
        raise VendorError(f"staging failed for {skill_name}: {clean_detail(error)}") from error
    finally:
        shutil.rmtree(stage_container, ignore_errors=True)


def print_summary(
    vendored: list[str], adapted: list[tuple[str, str]], frozen: list[tuple[str, str]], failures: list[str]
) -> None:
    print()
    print(f"VENDORED_COUNT={len(vendored)}")
    print(f"ADAPTED_COUNT={len(adapted)}")
    print(f"FROZEN_COUNT={len(frozen)}")
    print(f"PROTECTED_COUNT={len(adapted) + len(frozen)}")
    print(f"FAILED_COUNT={len(failures)}")
    for value in vendored:
        print(f"VENDORED={value}")
    for name, reason in adapted:
        print(f"ADAPTED={name} reason={reason}")
    for name, reason in frozen:
        print(f"FROZEN={name} reason={reason}")
    for failure in failures:
        print(f"FAILED={failure}")
    if vendored:
        print(f"Review the successful replacements under {SKILLS_DIR}/ before committing.")
    if failures and vendored:
        print("Partial result: successful earlier replacements remain installed.")


def interruption_handler(signum: int, _frame: object) -> None:
    raise VendorInterrupted(f"received signal {signum}")


def main() -> int:
    try:
        sources, skills = load_manifest()
        validate_skills_root(skills)
    except ManifestError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    try:
        LOCK_DIR.mkdir(mode=0o700)
    except FileExistsError:
        print(
            f"ERROR: vendoring lock already exists at {LOCK_DIR}; "
            "inspect it manually (stale locks are never deleted automatically)",
            file=sys.stderr,
        )
        return 2
    except OSError as error:
        print(f"ERROR: cannot create vendoring lock {LOCK_DIR}: {clean_detail(error)}", file=sys.stderr)
        return 2

    clone_root: Path | None = None
    vendored: list[str] = []
    adapted: list[tuple[str, str]] = []
    frozen: list[tuple[str, str]] = []
    failures: list[str] = []
    clones: dict[str, Path] = {}
    clone_failures: dict[str, str] = {}
    interrupted = False
    try:
        (LOCK_DIR / "owner").write_text(f"pid={os.getpid()}\n")
        signal.signal(signal.SIGTERM, interruption_handler)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, interruption_handler)
        clone_root = Path(tempfile.mkdtemp(prefix="sf-demo-scout-vendor-"))
        os.chmod(clone_root, 0o700)

        for skill in skills:
            name = skill["name"]
            policy = skill["policy"]
            if policy == "adapted":
                adapted.append((name, skill["reason"]))
                print(f"SKIPPED={name} policy=adapted reason={skill['reason']}")
                continue
            if policy == "frozen":
                frozen.append((name, skill["reason"]))
                print(f"SKIPPED={name} policy=frozen reason={skill['reason']}")
                continue

            source_name = skill["source"]
            source = sources[source_name]
            if source_name in clone_failures:
                failures.append(f"{name} ({clone_failures[source_name]})")
                continue
            try:
                if source_name not in clones:
                    clones[source_name] = clone_source(source_name, source, clone_root)
                clone_dir = clones[source_name]
                source_path = clone_dir.joinpath(*PurePosixPath(skill["path"]).parts)
                validate_source_tree(source_path, clone_dir, name)
                cleanup_failure, cleanup_interrupted = publish_skill(
                    source_path, SKILLS_DIR / name, name
                )
                provenance = (
                    f"{name} repo={source['repo']} revision={source['revision']} "
                    f"path={skill['path']}"
                )
                vendored.append(provenance)
                print(f"INSTALLED={provenance}")
                if cleanup_failure:
                    failures.append(f"{name} ({cleanup_failure})")
                if cleanup_interrupted:
                    interrupted = True
                    break
            except VendorInterrupted as error:
                failures.append(f"{name} ({clean_detail(error)})")
                interrupted = True
                break
            except VendorError as error:
                detail = clean_detail(error)
                if source_name not in clones:
                    clone_failures[source_name] = detail
                failures.append(f"{name} ({detail})")
    except (KeyboardInterrupt, VendorInterrupted) as error:
        failures.append(f"interrupted ({clean_detail(error)})")
        interrupted = True
    except BaseException as error:
        failures.append(f"unexpected vendoring failure ({clean_detail(error)})")
    finally:
        if clone_root is not None:
            shutil.rmtree(clone_root, ignore_errors=True)
        try:
            (LOCK_DIR / "owner").unlink(missing_ok=True)
            LOCK_DIR.rmdir()
        except OSError as error:
            failures.append(f"lock cleanup failed ({clean_detail(error)}): {LOCK_DIR}")

    print_summary(vendored, adapted, frozen, failures)
    return 2 if failures or interrupted else 0


raise SystemExit(main())
PYTHON
