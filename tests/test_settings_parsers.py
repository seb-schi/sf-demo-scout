"""The settings helper's parsers, which setup's marketplace step and the read-only model report still use: strict
JSON for Claude's settings, JSONC for VS Code's. A file they can't parse safely is reported and left byte-identical."""

from __future__ import annotations

import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest

import stand_ins


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "setup-settings.py"
HELPER = runpy.run_path(str(SCRIPT))


class StrictJsonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="scout-parsers-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()

    def autoupdate(self, settings: Path) -> str:
        environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "marketplace-autoupdate", "--settings", str(settings)],
                                capture_output=True, text=True, env=environment, timeout=60, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_unsafe_json_is_reported_and_left_byte_identical_without_a_backup(self) -> None:
        entry = b'"extraKnownMarketplaces":{"salesforce":{"source":{}}}'
        for name, body in (
            ("duplicate", b'{' + entry + b',"extraKnownMarketplaces":{}}\n'),
            ("nonfinite", b'{' + entry + b',"values":[NaN,Infinity,-Infinity]}\n'),
            ("overflow", b'{' + entry + b',"unrelated":1e999}\n'),
            ("malformed", b'{' + entry + b',}\n'),
        ):
            with self.subTest(name=name):
                settings = self.base / f"{name}.json"
                settings.write_bytes(body)
                self.assertTrue(self.autoupdate(settings).startswith(f"AUTOUPDATE_PARSE_ERROR[{name}.json]"))
                self.assertEqual(settings.read_bytes(), body)
                self.assertEqual([path.name for path in self.base.iterdir() if path.name.startswith(name)],
                                 [f"{name}.json"])  # no backup, no staged copy

    @stand_ins.needs_symlinks
    def test_linked_settings_and_linked_folders_are_refused(self) -> None:
        real_dir = self.base / "real-dir"
        real_dir.mkdir()
        real = real_dir / "settings.json"
        original = b'{"extraKnownMarketplaces":{"salesforce":{"source":{}}}}\n'
        real.write_bytes(original)
        direct = self.base / "direct.json"
        direct.symlink_to(real)
        linked_dir = self.base / "linked-dir"
        linked_dir.symlink_to(real_dir, target_is_directory=True)
        for name, path in (("direct", direct), ("ancestor", linked_dir / "settings.json")):
            with self.subTest(name=name):
                self.assertIn("AUTOUPDATE_UNSAFE_FILE", self.autoupdate(path))
        self.assertEqual(real.read_bytes(), original)


class JsoncTests(unittest.TestCase):
    def test_comments_and_trailing_commas_parse(self) -> None:
        _, node = HELPER["parse_jsonc"](b'{ // a comment\n "claudeCode.environmentVariables": [\n'
                                        b'  {"name": "A", "value": "b"}, /* another */\n ],\n}\n')
        self.assertEqual(node.value, {"claudeCode.environmentVariables": [{"name": "A", "value": "b"}]})

    def test_malformed_and_duplicate_jsonc_raise_a_settings_error(self) -> None:
        for name, body in (
            ("malformed", b'{"claudeCode.environmentVariables": [}'),
            ("duplicate", b'{"claudeCode.environmentVariables": [], "claudeCode.environmentVariables": []}\n'),
            ("unterminated comment", b'{"a": 1 /* never closed\n'),
        ):
            with self.subTest(name=name):
                with self.assertRaises(HELPER["SettingsError"]):
                    HELPER["parse_jsonc"](body)


if __name__ == "__main__":
    unittest.main()
