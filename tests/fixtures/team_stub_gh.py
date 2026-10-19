#!/usr/bin/env python3
"""A stand-in `gh` for the team-mode tests: it logs every call and answers the few the helper makes."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ["STUB_ROOT"])
args = sys.argv[1:]
with open(ROOT / "gh-calls.log", "a") as handle:
    handle.write(json.dumps(args) + "\n")
if " ".join(args[:2]) in os.environ.get("STUB_GH_FAIL", "").split(","):
    print("HTTP 502: Bad Gateway", file=sys.stderr)
    sys.exit(1)
if args[:2] == ["api", "user"]:
    print("stub-login\tUser")
elif args[:2] == ["repo", "create"]:
    print(f"https://github.com/{args[2] if '/' in args[2] else 'stub-login/' + args[2]}")
elif args[:2] == ["repo", "view"]:
    print(json.dumps({"url": f"https://github.com/{args[2]}", "nameWithOwner": args[2], "visibility": "PRIVATE"}))
elif args[:2] == ["pr", "create"]:
    count = len((ROOT / "gh-calls.log").read_text().split('"pr", "create"')) - 1
    print(f"https://github.com/stub-login/team/pull/{count}")
elif args[:2] == ["pr", "view"]:
    print((ROOT / f"pr-{args[2]}.json").read_text())
elif args[:2] == ["api", "/user/repository_invitations"]:
    print("[]")
elif args[:1] == ["api"] and "PUT" in args:
    print("HTTP/2.0 201 Created")
