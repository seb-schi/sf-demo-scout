#!/usr/bin/env python3
"""CLI entry for Scout's opt-in report repair."""
from scout_report_repair import main
import scout_portable

if __name__ == "__main__":
    scout_portable.utf8_output()
    raise SystemExit(main())
