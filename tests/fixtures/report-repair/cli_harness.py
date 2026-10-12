"""Keep the subprocess test's read-only deploy-cache lookup in its fixture tree."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, os.environ['SCOUT_REPORT_SCRIPTS'])
import scout_report_repair

with patch.object(Path, 'home', return_value=Path(os.environ['SCOUT_REPORT_TEST_STATE']).parent):
    raise SystemExit(scout_report_repair.main())
