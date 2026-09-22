"""Read-only cartridge selection from host inventory, including shipped caller."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/knowledge-cartridges.py"
SPEC = importlib.util.spec_from_file_location("knowledge_cartridges", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class KnowledgeCartridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="scout-cartridge-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()

    def cartridge(self, relative: str) -> Path:
        path = self.base / relative
        path.mkdir(parents=True)
        for name in MODULE.CONTRACTS:
            (path / name).write_text("fixture contract\n")
        return path

    def row(self, path: Path, identity: str = "knowledge@provider", enabled: bool = True) -> dict:
        return {"id": identity, "enabled": enabled, "installPath": str(path), "scope": "user"}

    def run_helper(self, rows: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--stdin"], input=json.dumps(rows),
            text=True, capture_output=True, check=False,
        )

    def test_rollback_selects_host_root_not_newer_cached_version(self) -> None:
        selected = self.cartridge("provider/knowledge/1.0.0")
        self.cartridge("provider/knowledge/2.0.0")
        result = self.run_helper([self.row(selected)])
        self.assertEqual(result.returncode, 0, result.stderr)
        cartridges = json.loads(result.stdout)["cartridges"]
        self.assertEqual([item["root"] for item in cartridges], [str(selected)])

    def test_disabled_and_uninstalled_leftovers_are_not_read(self) -> None:
        disabled = self.cartridge("disabled/knowledge/9.0.0")
        self.cartridge("uninstalled/knowledge/99.0.0")
        # Filesystem selection must not even inspect a disabled candidate's path.
        with patch.object(MODULE.Path, "resolve", side_effect=AssertionError("disabled path inspected")):
            result = MODULE.selected_cartridges([self.row(disabled, enabled=False)])
        self.assertEqual(result["cartridges"], [])
        self.assertEqual(MODULE.selected_cartridges([])["cartridges"], [])

    def test_duplicate_basenames_preserve_provider_identity(self) -> None:
        first = self.cartridge("first/knowledge/1")
        second = self.cartridge("second/knowledge/2")
        rows = [self.row(first, "knowledge@first"), self.row(second, "knowledge@second", False)]
        selected = MODULE.selected_cartridges(rows)["cartridges"]
        self.assertEqual([(item["id"], item["root"]) for item in selected], [("knowledge@first", str(first))])
        rows[1]["enabled"] = True
        self.assertEqual({item["id"] for item in MODULE.selected_cartridges(rows)["cartridges"]},
                         {"knowledge@first", "knowledge@second"})

    def test_multiple_enabled_scopes_never_pick_first_or_highest(self) -> None:
        first = self.row(self.cartridge("user/1"))
        second = self.row(self.cartridge("project/2"))
        second["scope"] = "project"
        for rows in ([first, second], [second, first]):
            result = MODULE.selected_cartridges(rows)
            self.assertEqual(result["cartridges"], [])
            self.assertEqual(result["unavailable"][0]["reason"], "ambiguous_selection")

    def test_host_resolved_enablement_can_select_one_scope(self) -> None:
        first = self.row(self.cartridge("user/1"), enabled=False)
        second = self.row(self.cartridge("project/2"))
        second["scope"] = "project"
        result = MODULE.selected_cartridges([first, second])
        self.assertEqual(result["cartridges"][0]["root"], second["installPath"])

    def test_paths_with_spaces_and_shell_metacharacters_are_literal(self) -> None:
        selected = self.cartridge("provider/knowledge $(not-a-command)/version with spaces")
        result = self.run_helper([self.row(selected)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["cartridges"][0]["root"], str(selected))

    def test_contract_requires_both_files_at_the_selected_root(self) -> None:
        selected = self.cartridge("selected")
        (selected / "INTEGRATING.md").unlink()
        self.cartridge("newer")
        self.assertEqual(MODULE.selected_cartridges([self.row(selected)])["cartridges"], [])

    def test_contract_symlink_cannot_escape_selected_root(self) -> None:
        selected = self.cartridge("selected")
        outside = self.cartridge("outside")
        contract = selected / "INTEGRATING.md"
        contract.unlink()
        contract.symlink_to(outside / "INTEGRATING.md")
        result = MODULE.selected_cartridges([self.row(selected)])
        self.assertEqual(result["cartridges"], [])
        self.assertEqual(result["unavailable"][0]["reason"], "contract_outside_selected_root")

    def test_contract_symlink_inside_selected_root_is_allowed(self) -> None:
        selected = self.cartridge("selected")
        nested = selected / "docs"
        nested.mkdir()
        (selected / "INTEGRATING.md").rename(nested / "adoption.md")
        (selected / "INTEGRATING.md").symlink_to(nested / "adoption.md")
        self.assertEqual(len(MODULE.selected_cartridges([self.row(selected)])["cartridges"]), 1)

    def test_unknown_enablement_never_becomes_truthy_enabled(self) -> None:
        selected = self.cartridge("selected")
        for value in (None, "true", 1, [], {}):
            with self.subTest(value=value):
                row = self.row(selected)
                row["enabled"] = value
                result = MODULE.selected_cartridges([row])
                self.assertEqual(result["cartridges"], [])
                self.assertEqual(result["unavailable"][0]["reason"], "enablement_unknown")

    def test_missing_relative_and_broken_roots_do_not_trigger_cache_fallback(self) -> None:
        self.cartridge("cached/99")
        for root in (None, "relative/path", str(self.base / "missing"), "/invalid\0path"):
            with self.subTest(root=root):
                row = self.row(self.base)
                row["installPath"] = root
                self.assertEqual(MODULE.selected_cartridges([row])["cartridges"], [])

    def test_unknown_inventory_and_unqualified_ids_fail_closed(self) -> None:
        for rows in ({"available": []}, [None], [{"id": "knowledge", "enabled": True}],
                     [{"id": "knowledge@../provider", "enabled": True}]):
            with self.subTest(rows=rows):
                result = self.run_helper(rows)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(result.stdout)["cartridges"], [])

    def test_duplicate_keys_invalid_utf8_and_oversized_json_fail_closed(self) -> None:
        for raw in (b'[{"id":"a@b","enabled":true,"enabled":false}]', b'\xff',
                    b' ' * (MODULE.MAX_BYTES + 1)):
            with self.subTest(size=len(raw)):
                with self.assertRaises(MODULE.InventoryError):
                    MODULE.parse_inventory(raw)

    def test_cli_collector_is_read_only_scoped_and_redacts_failure_output(self) -> None:
        completed = subprocess.CompletedProcess([], 0, b'[]', b'')
        with patch.object(MODULE.subprocess, "run", return_value=completed) as run:
            self.assertEqual(MODULE.claude_inventory(str(self.base)), b'[]')
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["claude", "plugin", "list", "--json"])
        self.assertEqual(kwargs["cwd"], self.base)
        self.assertNotIn("shell", kwargs)
        failure = subprocess.CompletedProcess([], 1, b'PRIVATE OUTPUT', b'PRIVATE ERROR')
        with patch.object(MODULE.subprocess, "run", return_value=failure):
            with self.assertRaisesRegex(MODULE.InventoryError, "^host inventory command failed$"):
                MODULE.claude_inventory(str(self.base))

    def test_missing_cli_timeout_and_bad_directory_are_unavailable(self) -> None:
        for error in (FileNotFoundError(), subprocess.TimeoutExpired("claude", 20)):
            with patch.object(MODULE.subprocess, "run", side_effect=error):
                with self.assertRaises(MODULE.InventoryError):
                    MODULE.claude_inventory(str(self.base))
        for directory in ("relative", str(self.base / "missing"), "/invalid\0path"):
            with self.assertRaises(MODULE.InventoryError):
                MODULE.claude_inventory(directory)

    def test_shipped_caller_uses_selected_inventory_in_native_session_directory(self) -> None:
        prompt = (ROOT / "prompts/sparring/knowledge-cartridge.md").read_text()
        blocks = re.findall(r"```bash\n(.*?)\n```", prompt, re.S)
        callers = [block for block in blocks if "scripts/knowledge-cartridges.py" in block]
        self.assertEqual(len(callers), 1)
        selected = self.cartridge("provider/knowledge/1.0.0")
        self.cartridge("provider/knowledge/99.0.0")
        session = self.base / "native session"
        session.mkdir()
        binary = self.base / "bin"
        binary.mkdir()
        stub = binary / "claude"
        stub.write_text(
            '#!/bin/sh\n[ "$*" = "plugin list --json" ] || exit 97\n'
            '[ "$PWD" = "$SCOUT_EXPECTED_SESSION" ] || exit 98\n'
            'printf "%s" "$SCOUT_TEST_INVENTORY"\n'
        )
        stub.chmod(0o700)
        (binary / "python3").symlink_to(sys.executable)
        command = callers[0].replace(
            "/absolute/path/of/active/sf-demo-scout/scripts/knowledge-cartridges.py", str(SCRIPT)
        ).replace("/absolute/native/session/directory", str(session))
        result = subprocess.run(
            ["/bin/bash", "-c", command], cwd=self.base,
            env={**os.environ, "PATH": f"{binary}:/usr/bin:/bin",
                 "SCOUT_EXPECTED_SESSION": str(session),
                 "SCOUT_TEST_INVENTORY": json.dumps([self.row(selected)])},
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["cartridges"][0]["root"], str(selected))
        self.assertNotIn("sort -V", prompt)
        self.assertNotIn('find "$HOME/.claude/plugins/cache"', prompt)


if __name__ == "__main__":
    unittest.main()
