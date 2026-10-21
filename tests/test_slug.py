"""Historical slug and customer-folder regressions against shipped code."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest

from test_startup import SLUGIFY


class SlugTests(unittest.TestCase):
    """The 17 slug assertions from historical B4."""

    def slug(self, value: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(SLUGIFY), value],
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            capture_output=True,
            check=False,
        )

    def test_named_transliterations(self) -> None:
        examples = (
            ("Nordlicht Fachpflege", "nordlicht-fachpflege"),
            ("L'Étoile", "l-etoile"),
            ("A&Z", "a-z"),
            ("Example CPQ", "example-cpq"),
            ("7K", "7k"),
            ("ExampleCare_DPA", "examplecare-dpa"),
            ("Müller", "muller"),
            ("Straße", "strasse"),
            ("Søren", "soren"),
        )
        for source, expected in examples:
            with self.subTest(source=source):
                result = self.slug(source)
                self.assertTrue(
                    result.returncode == 0 and result.stdout.strip() == expected
                )

    def test_empty_and_glob_characters(self) -> None:
        empty = self.slug("")
        self.assertTrue(empty.returncode == 1 and empty.stdout.strip() == "")
        glob = self.slug("a*?[b]")
        self.assertEqual(glob.stdout.strip(), "a-b")

    def test_exact_truncation_boundaries(self) -> None:
        cases = (
            ("a" * 20 + "-" + "b" * 19 + "-c", "a" * 20 + "-" + "b" * 19),
            ("a" * 19 + "-" + "b" * 20, "a" * 19 + "-" + "b" * 20),
            ("a" * 20 + "-" + "b" * 19 + "-" + "c" * 5, "a" * 20 + "-" + "b" * 19),
            ("a" * 10 + "-" + "b" * 40, "a" * 10),
            ("a" * 45, "a" * 40),
            ("a" * 39 + "-bc", "a" * 39),
        )
        for source, expected in cases:
            with self.subTest(source_length=len(source), expected_length=len(expected)):
                result = self.slug(source)
                self.assertTrue(
                    result.returncode == 0 and result.stdout.strip() == expected
                )


class DeveloperNameTests(unittest.TestCase):
    """The Custom Metadata DeveloperName rule phase 1 runs, the same as the official skill's sanitize script."""

    def test_labels_become_valid_developer_names(self):
        import subprocess, sys
        script = Path(__file__).resolve().parents[1] / "scripts" / "slugify.py"
        for label, expected in (("United States", "United_States"), ("United-States", "United_States"),
                                ("9 Lives", "X9_Lives"), ("  __x__  ", "x"), ("A" * 45 + "_b", "A" * 40),
                                ("Hello, World! 2026", "Hello_World_2026")):
            with self.subTest(label=label):
                result = subprocess.run([sys.executable, "-B", str(script), "--developer-name", label],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual((result.returncode, result.stdout.strip()), (0, expected))
        result = subprocess.run([sys.executable, "-B", str(script), "--developer-name", "---"], capture_output=True,
                                text=True, timeout=30)
        self.assertEqual((result.returncode, result.stdout), (1, ""))


if __name__ == "__main__":
    unittest.main()
