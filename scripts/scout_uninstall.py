#!/usr/bin/env python3
"""Remove Scout's own files from this machine, and nothing else.

By default it removes Scout's configuration (`~/.config/sf-demo-scout`) and cache (`~/.cache/sf-demo-scout`).
`--workspace` also removes the workspace, which holds the per-org histories, change logs and lessons; pass it only
on the user's own, separate yes. The workspace is the one Scout's configuration names, or `$SCOUT_WORKSPACE`, or
`~/claude-projects/sf-demo-scout`. It's removed only when it is recognisably Scout's: it holds the lessons index
Scout's setup writes into every workspace, on every host, and no other setting names a different folder.
Otherwise it's left for the user to remove by hand.

It never touches the plugin itself (remove that with the host's own uninstall), another tool's settings, shell
files or Salesforce logins. It never follows a symbolic link: a linked folder loses only its link.

`--dry-run` prints the plan and changes nothing. A real run needs `--yes`, so nothing is removed by accident, and
it prints the whole plan before it removes anything; when it refuses any part of the plan, it removes nothing.
Every line it prints starts with a token: UNINSTALL_PLAN,
UNINSTALL_REMOVED, UNINSTALL_ABSENT, UNINSTALL_FAILED or UNINSTALL_REFUSED.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
LESSONS_INDEX = Path('orgs') / 'lessons' / 'INDEX.md'
LESSONS_HEADER = '# Lessons Index'  # the first line Scout's setup has written since the lessons moved there


def scouts_workspace(path: Path) -> bool:
    try:
        with open(path / LESSONS_INDEX, encoding='utf-8') as stream:
            return stream.readline().strip() == LESSONS_HEADER
    except (OSError, UnicodeError):
        return False


def configured_workspace(config_folder: Path) -> str | None:
    """The workspace Scout's configuration names, or None when there's no readable one."""
    try:
        value = json.loads((config_folder / 'config.json').read_text(encoding='utf-8')).get('workspace_path')
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, str) and value else None


def workspace(home: Path, config_folder: Path) -> tuple[Path, str | None]:
    """The workspace to remove, and a reason to refuse it: conflicting settings, or a folder that isn't Scout's."""
    named = [Path(value).expanduser() for value in (configured_workspace(config_folder),
                                                    os.environ.get('SCOUT_WORKSPACE')) if value]
    path = named[0] if named else home / 'claude-projects' / 'sf-demo-scout'
    if len({resolved(candidate) for candidate in named}) > 1:
        return path, 'Scout\'s configuration and SCOUT_WORKSPACE name different folders; remove it by hand'
    if path.is_symlink() or not path.exists():
        return path, None  # a link loses only its link; an absent folder is reported as absent
    if not scouts_workspace(path):
        return path, 'not recognisably Scout\'s workspace (no Scout lessons index at %s); remove it by hand' % LESSONS_INDEX
    return path, None


def resolved(path: Path) -> Path:
    try:
        return path.parent.resolve() / path.name
    except OSError:
        return path


def targets(include_workspace: bool) -> list[tuple[Path, str | None]]:
    home = Path.home()
    config = home / '.config' / 'sf-demo-scout'
    paths = [(config, None), (home / '.cache' / 'sf-demo-scout', None)]
    if include_workspace:
        paths.append(workspace(home, config))  # read before the configuration goes
    return [(path, reason or refusal(path)) for path, reason in paths]


def refusal(path: Path) -> str | None:
    """A reason to leave this path alone: anything outside the home folder, the home folder itself, or a root."""
    try:
        target = path.parent.resolve() / path.name
    except OSError as error:
        return 'unresolvable: %s' % error
    home = Path.home().resolve()
    if target == home or target == Path(target.anchor) or home not in target.parents:
        return 'outside the home folder or too broad'
    return None


def remove(path: Path) -> str:
    if not os.path.lexists(path):
        return 'UNINSTALL_ABSENT %s' % path
    try:
        if path.is_symlink() or not path.is_dir():
            path.unlink()
        else:
            shutil.rmtree(path)
    except OSError as error:
        return 'UNINSTALL_FAILED %s: %s' % (path, error.strerror or error)
    return 'UNINSTALL_REMOVED %s' % path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--workspace', action='store_true', help="also remove the workspace and its org histories")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true', help='print the plan and change nothing')
    mode.add_argument('--yes', action='store_true', help='print the plan, then remove the planned paths')
    arguments = parser.parse_args(argv)
    plan = targets(arguments.workspace)
    failed = False
    for path, reason in plan:
        if reason:
            print('UNINSTALL_REFUSED %s: %s' % (path, reason))
            failed = True
        else:
            print('UNINSTALL_PLAN %s%s' % (path, '' if os.path.lexists(path) else ' (absent)'))
    if arguments.yes and not failed:
        for path, reason in plan:
            if not reason:
                line = remove(path)
                failed = failed or line.startswith('UNINSTALL_FAILED')
                print(line)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
