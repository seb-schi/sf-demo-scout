"""scout_sf_argv.py prints the command that runs the Salesforce CLI without its batch launcher (2.4.1).

On Windows, the host contract tells the model to rerun a call that failed with "'C:\\Program' is not recognized"
through this argv, so it gets the same CLI Scout's own helpers run, a self-updated one included.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stand_ins  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "scout_sf_argv.py"


class SfArgvTests(unittest.TestCase):
    def run_script(self, environment: dict) -> subprocess.CompletedProcess:
        env = stand_ins.keep(dict(environment, PYTHONDONTWRITEBYTECODE="1"))
        return subprocess.run([sys.executable, "-B", str(SCRIPT)], env=env, capture_output=True, text=True,
                              timeout=60, check=False)

    def test_it_prints_the_argv_scouts_helpers_use(self) -> None:
        stand_ins.require_node()
        with tempfile.TemporaryDirectory(prefix="scout-sf-argv-") as folder:
            cli = stand_ins.salesforce_cli(folder, "print('cli')\n")
            result = self.run_script(stand_ins.cli_environment(folder))
            self.assertEqual(result.returncode, 0, result.stderr)
            argv = json.loads(result.stdout)
            self.assertIsInstance(argv, list)
            if stand_ins.WINDOWS:
                # node.exe and the CLI's run script, never the batch launcher cmd.exe would re-read.
                self.assertEqual(len(argv), 2)
                self.assertTrue(argv[1].endswith("run.js"), argv)
                self.assertFalse(any(part.lower().endswith((".cmd", ".bat")) for part in argv))
            else:
                self.assertEqual([os.path.realpath(part) for part in argv], [os.path.realpath(cli)])
            # The printed command runs the CLI.
            ran = subprocess.run(argv, env=stand_ins.keep(stand_ins.cli_environment(folder)), capture_output=True,
                                 text=True, timeout=60, check=False)
            self.assertEqual(ran.stdout.strip(), "cli", ran.stderr)

    def test_an_unresolvable_launcher_on_windows_fails_rather_than_printing_itself(self) -> None:
        # A launcher whose Node script can't be found would only fail the same way again.
        import importlib.util
        from unittest import mock
        spec = importlib.util.spec_from_file_location("scout_sf_argv_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix="scout-sf-argv-") as folder:
            launcher = Path(folder) / "Program Files" / "sf" / "bin" / "sf.cmd"
            launcher.parent.mkdir(parents=True)
            launcher.write_text("@echo off\r\nC:\\elsewhere\\sf.exe %*\r\n")
            with mock.patch.object(module.scout_portable, "PLATFORM", "win32"), \
                    mock.patch.object(module.scout_portable, "shell_which", return_value=str(launcher)), \
                    mock.patch("sys.stdout") as out, mock.patch("sys.stderr") as err:
                self.assertEqual(module.main([]), 2)
            self.assertFalse(out.write.called)
            self.assertIn("couldn't find the Node script", "".join(c.args[0] for c in err.write.call_args_list))

    def test_no_cli_on_the_path_is_said_plainly(self) -> None:
        with tempfile.TemporaryDirectory(prefix="scout-sf-argv-") as folder:
            result = self.run_script({"PATH": folder})
            self.assertEqual(result.returncode, 1)
            self.assertIn("no `sf` on this PATH", result.stderr)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
