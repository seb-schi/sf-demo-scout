#!/usr/bin/env python3
"""Install Scout from a clone into Cursor, whose managed installs often refuse third-party plugins. It writes only
its own files, prints what it would do with --dry-run, and changes
nothing without --yes.

Commands:
  skills          the thin `scout` and `scout-setup` skills in Cursor's user skills folder; each names this
                  clone and hands over to the clone's own entry skill
  docs-mcp        Cursor only: the public Salesforce Docs MCP entry in ~/.cursor/mcp.json, merged, never replacing
  official-skills a clone of Salesforce's public sf-skills repository, read in place for the official skills
  uninstall       removes the thin skills this installer wrote, and nothing else
  status          what's in place, read-only

Every line it prints starts with a token: INSTALL_PLAN, INSTALL_WROTE, INSTALL_KEPT, INSTALL_REFUSED,
INSTALL_FAILED, INSTALL_NOTE or INSTALL_STATUS.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scout_portable  # noqa: E402  (ships beside this helper)

ROOT = Path(__file__).resolve().parents[1]
MARKER = "<!-- Written by Scout's installer (scripts/scout_install.py); it may replace this file. -->"
DOCS_NAME = "salesforce-docs"
DOCS_URL = "https://salesforce-docs-76258744c9d7.herokuapp.com/api/mcp"
OFFICIAL_REPO = "https://github.com/forcedotcom/sf-skills.git"
SKILLS = ("scout", "scout-setup")  # their descriptions and invocation rules come from the clone's own entry skills


def home() -> Path:
    return Path.home()


def skills_folder(host: str) -> Path:
    return {"cursor": home() / ".cursor" / "skills"}[host]  # Claude Code and Codex install Scout as a plugin


def config_folder() -> Path:
    return home() / ".config" / "sf-demo-scout"


def frontmatter(name: str) -> tuple[str, bool]:
    """The clone's own entry skill's description (one line, or a folded block's indented lines) and whether only the
    user may invoke it."""
    lines = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8").split("\n")
    head = lines[1:lines.index("---", 1)] if lines and lines[0] == "---" and "---" in lines[1:] else []
    description, user_only = name, False
    for index, line in enumerate(head):
        if line.startswith("description:"):
            value = line[len("description:"):].strip()
            if value[:1] in (">", "|"):
                block = []
                for continuation in head[index + 1:]:
                    if not continuation.startswith((" ", "\t")):
                        break
                    block.append(continuation.strip())
                value = " ".join(block)
            description = value.strip("\"'") or name
        elif line.strip() == "disable-model-invocation: true":
            user_only = True
    return description, user_only


def thin_skill(name: str) -> str:
    description, user_only = frontmatter(name)
    lines = ["---", "name: %s" % name, "description: %s" % json.dumps(description)]
    if user_only:
        lines.append("disable-model-invocation: true")
    lines += ["---", MARKER, "",
              "Scout lives in the folder `%s`; that is Scout's root (`PLUGIN_ROOT_ABS`) for this whole task." % ROOT,
              "Read `%s` now and follow it exactly, with the request the SE sent with this skill."
              % (ROOT / "skills" / name / "SKILL.md"),
              "If that file is missing, say Scout's folder moved or was removed, and stop.", ""]
    return "\n".join(lines)


def ours(path: Path) -> bool:
    try:
        return MARKER in path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".%s." % path.name, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        scout_portable.replace(temporary, path)  # closed first; on Windows a brief scanner hold is ridden out
    except OSError:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def claude_has_scout() -> bool | None:
    """Whether Claude Code has Scout installed, from its own record; None when the record can't be read."""
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR") or home() / ".claude")
    try:
        record = json.loads((config / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False
    except (OSError, ValueError, UnicodeError):
        return None
    plugins = record.get("plugins") if isinstance(record, dict) else None
    return any(str(ident).startswith("sf-demo-scout@") for ident in plugins) if isinstance(plugins, dict) else None


def duplicate_note(host: str) -> None:
    installed = claude_has_scout() if host == "cursor" else False
    if installed:
        print("INSTALL_NOTE Claude Code has Scout installed too, and Cursor can import Claude Code's plugins, so "
              "Scout may show up twice in Cursor. Use one: this clone's skills, or the imported plugin.")
    elif installed is None:
        print("INSTALL_NOTE Claude Code's plugin record couldn't be read; if Claude Code has Scout too, Cursor may "
              "show it twice.")


def command_skills(host: str, apply: bool) -> int:
    failed = False
    for name in SKILLS:
        target = skills_folder(host) / name / "SKILL.md"
        if target.exists() and not ours(target):
            print("INSTALL_REFUSED %s: a skill of that name that Scout's installer didn't write; left as it is" % target)
            failed = True
            continue
        if not apply:
            print("INSTALL_PLAN write %s" % target)
            continue
        try:
            atomic_write(target, thin_skill(name))
        except OSError as error:
            print("INSTALL_FAILED %s: %s" % (target, error.strerror or error))
            failed = True
            continue
        print("INSTALL_WROTE %s" % target)
    duplicate_note(host)
    return 1 if failed else 0


def command_docs_mcp(apply: bool) -> int:
    path = home() / ".cursor" / "mcp.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError, UnicodeError):
        print("INSTALL_REFUSED %s: not readable JSON; left as it is" % path)
        return 1
    servers = data.get("mcpServers", {}) if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        print("INSTALL_REFUSED %s: unexpected shape; left as it is" % path)
        return 1
    if DOCS_NAME in servers:
        print("INSTALL_KEPT %s: a %s entry exists; left as it is" % (path, DOCS_NAME))
        return 0
    if not apply:
        print("INSTALL_PLAN add %s (%s) to %s" % (DOCS_NAME, DOCS_URL, path))
        return 0
    servers[DOCS_NAME] = {"url": DOCS_URL}
    data["mcpServers"] = servers
    try:
        if path.exists():
            shutil.copy2(path, path.with_name(path.name + ".scout-bak"))
        atomic_write(path, json.dumps(data, indent=2) + "\n")
    except OSError as error:
        print("INSTALL_FAILED %s: %s" % (path, error.strerror or error))
        return 1
    print("INSTALL_WROTE %s: added %s; reload Cursor to connect it" % (path, DOCS_NAME))
    return 0


def official_record() -> Path:
    return config_folder() / "official-skills.json"


def git_output(git: str, folder: Path, *args: str) -> str | None:
    try:
        result = subprocess.run([git, "-C", str(folder), *args], stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def official_clone_problem(git: str, folder: Path) -> str | None:
    """Why this folder isn't a clone of Salesforce's repository Scout can read, or None."""
    origin = git_output(git, folder, "remote", "get-url", "origin") or ""
    if not re.search(r"github\.com[/:]forcedotcom/sf-skills(?:\.git)?/?$", origin, re.IGNORECASE):
        return "its origin isn't github.com/forcedotcom/sf-skills"
    if not (folder / "plugins" / "builder" / "salesforce-development" / "skills").is_dir():
        return "it has no plugins/builder/salesforce-development/skills"
    return None


def command_official_skills(destination: str | None, apply: bool) -> int:
    target = Path(destination).expanduser() if destination else ROOT.parent / "sf-skills"
    git = shutil.which("git")
    if not git:
        print("INSTALL_FAILED git isn't on PATH; install Git, then run this again")
        return 1
    existing = (target / ".git").exists()
    if existing:
        problem = official_clone_problem(git, target)
        if problem:
            print("INSTALL_REFUSED %s: %s; name another folder with --dest" % (target, problem))
            return 1
        print("INSTALL_KEPT %s: already a clone of Salesforce's skills; Scout's update check offers to update it" % target)
    elif target.exists():
        print("INSTALL_REFUSED %s: exists and isn't a clone; name another folder with --dest" % target)
        return 1
    elif not apply:
        print("INSTALL_PLAN clone %s into %s" % (OFFICIAL_REPO, target))
    else:
        # Long paths: Salesforce's repository has deep sample paths; this setting stays in that clone only.
        try:
            result = subprocess.run([git, "clone", "--depth", "1", "-c", "core.longpaths=true", OFFICIAL_REPO, str(target)],
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=900)
        except (OSError, subprocess.SubprocessError) as error:
            print("INSTALL_FAILED clone into %s: %s; a partial folder may be left there" % (target, error))
            return 1
        if result.returncode:
            print("INSTALL_FAILED clone into %s: %s" % (target, (result.stderr.strip().splitlines() or ["git failed"])[-1]))
            return 1
        print("INSTALL_WROTE %s" % target)
    if not apply:
        print("INSTALL_PLAN record it in %s" % official_record())
        return 0
    revision = git_output(git, target, "rev-parse", "HEAD")
    try:
        atomic_write(official_record(), json.dumps({"root": str(target.resolve()), "revision": revision}, indent=2) + "\n")
    except OSError as error:
        print("INSTALL_FAILED %s: %s" % (official_record(), error.strerror or error))
        return 1
    print("INSTALL_WROTE %s (revision %s)" % (official_record(), revision or "unknown"))
    return 0


def command_uninstall(host: str, apply: bool) -> int:
    failed = False
    for name in SKILLS:
        target = skills_folder(host) / name / "SKILL.md"
        if not target.exists():
            continue
        if not ours(target):
            print("INSTALL_KEPT %s: not written by Scout's installer" % target)
        elif not apply:
            print("INSTALL_PLAN remove %s" % target.parent)
        else:
            try:
                target.unlink()
                if not any(target.parent.iterdir()):
                    target.parent.rmdir()
            except OSError as error:
                print("INSTALL_FAILED %s: %s" % (target, error.strerror or error))
                failed = True
                continue
            print("INSTALL_WROTE removed %s" % target.parent)
    return 1 if failed else 0


def command_status(host: str) -> int:
    for name in SKILLS:
        target = skills_folder(host) / name / "SKILL.md"
        state = "ours" if target.exists() and ours(target) else ("other" if target.exists() else "absent")
        print("INSTALL_STATUS skill %s %s %s" % (name, state, target))
    record = official_record()
    try:
        root = json.loads(record.read_text(encoding="utf-8")).get("root") if record.exists() else None
    except (OSError, ValueError, UnicodeError, AttributeError):
        root = None
    root = root if isinstance(root, str) and root else None
    print("INSTALL_STATUS official-skills %s" % (root if root and Path(root, "plugins").is_dir() else "absent"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("skills", "docs-mcp", "official-skills", "uninstall", "status"):
        sub = commands.add_parser(name)
        if name in ("skills", "uninstall", "status"):
            sub.add_argument("--host", required=True, choices=("cursor",))
        if name == "official-skills":
            sub.add_argument("--dest", help="where to clone (default: next to this Scout clone)")
        if name != "status":
            mode = sub.add_mutually_exclusive_group(required=True)
            mode.add_argument("--dry-run", action="store_true")
            mode.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "skills":
        return command_skills(args.host, args.yes)
    if args.command == "docs-mcp":
        return command_docs_mcp(args.yes)
    if args.command == "official-skills":
        return command_official_skills(args.dest, args.yes)
    if args.command == "uninstall":
        return command_uninstall(args.host, args.yes)
    return command_status(args.host)


if __name__ == "__main__":
    sys.exit(main())
