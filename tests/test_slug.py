"""Historical slug and customer-folder regressions against shipped code."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_startup import HELPER, HOOK, SLUGIFY, StartupFixture


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


class CustomerFolderHookTests(unittest.TestCase):
    """The 10 real-hook assertions from historical B4, using F6 seams."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="scout-folder-hook-test-")
        self.addCleanup(self.temp.cleanup)
        self.fx = StartupFixture(Path(self.temp.name).resolve())
        self.fx.write_config("ExampleCare_DPA")
        self.fx.write_list(
            [{"alias": "ExampleCare_DPA", "username": "u@example.invalid"}]
        )
        self.fx.write_display(
            "ExampleCare_DPA", username="u@example.invalid"
        )

    def seed_folder(self, suffix: str, *, audit: bool = False) -> None:
        folder = self.fx.workspace / "orgs" / f"examplecare-dpa-{suffix}"
        folder.mkdir(parents=True)
        if audit:
            (folder / "audit-2026-09-16.md").write_text("# audit")
            (folder / "changes-2026-09-16.md").write_text("# change")

    def run_hook(self, slugifier: Path = SLUGIFY) -> str:
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.update(
            PATH=f"{self.fx.bin}:/usr/bin:/bin:/usr/sbin:/sbin",
            PYTHONDONTWRITEBYTECODE="1",
            SCOUT_HOST="claude",
            SCOUT_WORKSPACE=str(self.fx.workspace),
            SCOUT_CACHE_DIR=str(self.fx.cache),
            SCOUT_RUNTIME_DIR=str(self.fx.runtime),
            SCOUT_SETTINGS_FILE=str(self.fx.settings),
            SCOUT_CONFIG_FILE=str(self.fx.scout_config),
            SCOUT_STARTUP_EVIDENCE=str(HELPER),
            SCOUT_SLUGIFY=str(slugifier),
            SCOUT_FIXTURE_DIR=str(self.fx.fixtures),
            SCOUT_FIXTURE_LOG=str(self.fx.log),
            SCOUT_NETWORK_TIMEOUT="3",
            SCOUT_HOOK_NOCACHE="1",
            PWD=str(self.fx.workspace),
        )
        result = subprocess.run(
            ["/bin/bash", str(HOOK)],
            cwd=self.fx.workspace,
            env=env,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_folder_labels_alias_and_audit_association(self) -> None:
        self.seed_folder("acme", audit=True)
        output = self.run_hook()
        self.assertIn("1 customer folder(s) for ExampleCare_DPA", output)
        self.assertIn("- acme:", output)
        self.assertIn("**Alias:** ExampleCare_DPA", output)
        self.assertTrue(
            "audit-2026-09-16.md" in output
            and "Last change log: changes-2026-09-16.md" in output
        )

    def test_two_folders(self) -> None:
        self.seed_folder("acme")
        self.seed_folder("globex")
        output = self.run_hook()
        self.assertIn("2 customer folder(s) for ExampleCare_DPA", output)
        self.assertTrue("- acme:" in output and "- globex:" in output)

    def test_no_folder_and_unavailable_helper_are_distinct(self) -> None:
        no_folder = self.run_hook()
        self.assertIn("No customer folders for ExampleCare_DPA", no_folder)
        self.assertNotIn("lookup unavailable", no_folder)

        self.seed_folder("acme")
        unavailable = self.run_hook(self.fx.base / "missing-slugify.py")
        self.assertIn("Customer-folder lookup unavailable", unavailable)
        self.assertNotIn("No customer folders", unavailable)


if __name__ == "__main__":
    unittest.main()
