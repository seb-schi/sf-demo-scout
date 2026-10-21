"""Every helper the model runs prints UTF-8, whatever the console's code page.

Before Python 3.15, Windows encodes a pipe with the ANSI code page (cp1252 and the like), where printing →, ★, ✓ or ✗,
or a user folder such as C:\\Users\\Łukasz, raises UnicodeEncodeError. PYTHONIOENCODING=cp1252 gives any machine that
pipe, so these tests run on every platform.
"""
from __future__ import annotations

import ast
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import stand_ins

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True
import scout_portable  # noqa: E402

# Each entry point's call here prints text and changes nothing: --help for every argparse helper (the default), and
# for the others their cheapest call that prints. Two read-only calls print paths under the home folder, whose name
# here has letters cp1252 lacks, as a Windows user's folder can; before the helpers switched to UTF-8, both failed.
# Skipped: none. Every entry point has a call without side effects.
CALLS = {
    "scout_install.py": (["status", "--host", "cursor"], 0),  # read-only: what's in place, under the home folder
    "scout_uninstall.py": (["--dry-run"], 0),  # the plan only, under the home folder
    "setup-cli-owner.py": (["sf", "npm", "sf"], 0),  # relative paths prove nothing: prints "unavailable", runs nothing
    "setup_bootstrap.py": ([], 64),  # its usage line
    "setup_cli_refresh.py": ([], 64),  # its usage line
    "slugify.py": (["Łódź Café"], 0),  # the slug
}
PRINTS_THE_HOME = ("scout_install.py", "scout_uninstall.py")


def entry_points() -> list[Path]:
    """Every helper with a __main__ block."""
    main = re.compile(r"""^if __name__ == ["']__main__["']:""", re.M)
    return sorted(path for path in SCRIPTS.glob("*.py") if main.search(path.read_text(encoding="utf-8")))


class ConsoleEncodingTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="scout-cp1252-")
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name).resolve() / "Łukasz 東京"  # a user folder the ANSI code page can't spell
        self.home.mkdir()
        environment = {name: value for name, value in os.environ.items()
                       if name not in ("PYTHONUTF8", "PYTHONIOENCODING", "PYTHONPATH")}
        environment.update(stand_ins.home(self.home), PYTHONIOENCODING="cp1252", PYTHONDONTWRITEBYTECODE="1")
        self.environment = environment

    def test_every_entry_point_prints_under_the_ansi_code_page(self) -> None:
        scripts = entry_points()
        self.assertGreater(len(scripts), 20)
        self.assertEqual(sorted(set(CALLS) - {path.name for path in scripts}), [])  # no stale entry
        for script in scripts:
            arguments, expected = CALLS.get(script.name, (["--help"], 0))
            with self.subTest(script=script.name):
                result = subprocess.run([sys.executable, "-B", str(script), *arguments], env=self.environment,
                                        cwd=str(self.home), capture_output=True, timeout=120, check=False)
                stderr = result.stderr.decode("utf-8", "replace")
                self.assertNotIn("UnicodeEncodeError", stderr)
                self.assertNotIn("Traceback", stderr)
                self.assertEqual(result.returncode, expected, stderr)
                self.assertTrue((result.stdout + result.stderr).strip(), "the call prints text")
                stdout = result.stdout.decode("utf-8")  # UTF-8, not the code page
                if script.name in PRINTS_THE_HOME:
                    self.assertIn(str(self.home), stdout)
        self.assertEqual(list(self.home.iterdir()), [])  # and nothing was written

    def test_every_entry_point_switches_to_utf8_before_anything_else(self) -> None:
        for script in entry_points():
            with self.subTest(script=script.name):
                tree = ast.parse(script.read_text(encoding="utf-8"))
                block, = [node for node in tree.body if isinstance(node, ast.If)
                          and ast.unparse(node.test) == "__name__ == '__main__'"]
                self.assertEqual(ast.unparse(block.body[0]), "scout_portable.utf8_output()")


class Utf8OutputTests(unittest.TestCase):
    @staticmethod
    def stream(errors: str) -> io.TextIOWrapper:
        return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors=errors, newline=None)

    def test_both_streams_take_utf8_and_lf_and_keep_their_error_handling(self) -> None:
        stdout, stderr = self.stream("strict"), self.stream("backslashreplace")
        with mock.patch.object(sys, "stdout", stdout), mock.patch.object(sys, "stderr", stderr):
            scout_portable.utf8_output()
        for stream, errors in ((stdout, "strict"), (stderr, "backslashreplace")):
            self.assertEqual((stream.encoding, stream.errors), ("utf-8", errors))
            stream.write("→ ★ ✓ ✗\n")
            stream.flush()
            self.assertEqual(stream.buffer.getvalue(), "→ ★ ✓ ✗\n".encode("utf-8"))  # LF on Windows too

    def test_a_stream_it_cant_reconfigure_stays_as_it_is(self) -> None:
        for replaced in (io.StringIO(), None):
            with self.subTest(stream=type(replaced).__name__), mock.patch.object(sys, "stdout", replaced), \
                    mock.patch.object(sys, "stderr", replaced):
                scout_portable.utf8_output()
                self.assertIs(sys.stdout, replaced)


if __name__ == "__main__":
    unittest.main()
