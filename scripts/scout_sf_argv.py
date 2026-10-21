#!/usr/bin/env python3
"""Print how to run the Salesforce CLI without its batch launcher: the argv prefix Scout's own helpers use.

On Windows the CLI's `sf` is a batch file, and cmd.exe cuts the launcher's path at a space when another argument is
quoted, so a call fails with "'C:\\Program' is not recognized". This prints, as one JSON list, the node.exe and run
script that launcher would start, an update the CLI installed under %LOCALAPPDATA%\\sf\\client first, as the launcher
itself does, so a caller can run them with its own arguments. Elsewhere it prints the `sf` it found. When it can't
find that script on Windows, it says so and exits 2 rather than print the launcher back. It runs nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scout_portable  # noqa: E402  (ships beside this helper)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Print, as one JSON list, the argv prefix that runs the Salesforce "
                                                 "CLI the way Scout's own helpers do, without its batch launcher.")
    parser.parse_args(argv)
    found = scout_portable.shell_which("sf")
    if found is None:
        print("no `sf` on this PATH", file=sys.stderr)
        return 1
    command = scout_portable.sf_argv(found)
    if scout_portable.windows() and command[0].lower().endswith(scout_portable.BATCH_SUFFIXES):
        # Printing the launcher back would only meet the same failure again.
        print("couldn't find the Node script behind %s, so a rerun would hit the same launcher" % command[0],
              file=sys.stderr)
        return 2
    print(json.dumps(command))
    return 0


if __name__ == "__main__":
    scout_portable.utf8_output()
    raise SystemExit(main())
