"""Hermetic regressions for Scout's bounded settings cleanup helper."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "setup-settings.py"
MODEL_KEYS = (
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
)


class SetupSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="scout-settings-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()

    def run_helper(
        self,
        command: str,
        settings: Path,
        *,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        if extra_env:
            environment.update(extra_env)
        return subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPT),
                command,
                "--settings",
                str(settings),
            ],
            env=environment,
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

    def write_json(self, path: Path, value: object) -> bytes:
        content = (json.dumps(value, indent=2) + "\n").encode()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return content

    def install_injection(self, body: str) -> dict[str, str]:
        injection = self.base / "injection"
        injection.mkdir(exist_ok=True)
        (injection / "sitecustomize.py").write_text(body)
        return {"PYTHONPATH": str(injection)}

    def test_vscode_ignores_other_extensions_model_entries(self) -> None:
        settings = self.base / "settings.json"
        before = {
            "claudeCode.environmentVariables": [
                {"name": "KEEP_ME", "value": "yes"}
            ],
            "unrelatedExtension.namedValues": [
                {"name": MODEL_KEYS[0], "value": "user-owned"},
                {"name": "OTHER", "value": "retained"},
            ],
        }
        original = self.write_json(settings, before)

        result = self.run_helper("vscode-pins", settings)

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(result.stdout.strip(), "VSCODE_PINS_NONE")
        self.assertEqual(settings.read_bytes(), original)
        self.assertFalse(Path(str(settings) + ".scout-bak").exists())

    def test_vscode_preserves_mappings_comments_modes_and_existing_backup(self) -> None:
        settings = self.base / "settings.json"
        original = b'''{
  // before property
  "claudeCode.environmentVariables": [
    // keep this comment
    { "name": "KEEP_ME", "value": "yes" },
    /* target comment */ { "value": "old", "name": "ANTHROPIC_DEFAULT_OPUS_MODEL" },
    { "name": "ANTHROPIC_DEFAULT_SONNET_MODEL", "value": "old" }, // after target
  ],
  "url": "https://example.test//kept",
  "unrelated": { "name": "ANTHROPIC_DEFAULT_HAIKU_MODEL", "value": "keep" },
}
'''
        settings.write_bytes(original)
        settings.chmod(0o640)
        backup = Path(str(settings) + ".scout-bak")
        backup.write_bytes(b"earlier recovery material")
        for _ in range(2):
            result = self.run_helper("vscode-pins", settings)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(result.stdout.strip(), "VSCODE_PINS_PRESERVED")
            self.assertEqual(settings.read_bytes(), original)
            self.assertEqual(stat.S_IMODE(settings.stat().st_mode), 0o640)
            self.assertEqual(backup.read_bytes(), b"earlier recovery material")

    def test_vscode_rejects_unsupported_target_shape(self) -> None:
        settings = self.base / "settings.json"
        original = self.write_json(
            settings,
            {
                "claudeCode.environmentVariables": [
                    {"name": MODEL_KEYS[0], "value": "old", "extra": True}
                ]
            },
        )

        result = self.run_helper("vscode-pins", settings)

        self.assertEqual(result.returncode, 0)
        self.assertIn("VSCODE_UNSUPPORTED_TARGET", result.stdout)
        self.assertEqual(settings.read_bytes(), original)
        self.assertFalse(Path(str(settings) + ".scout-bak").exists())

    def test_vscode_preserves_repeated_mapping_entries(self) -> None:
        settings = self.base / "settings.json"
        original = self.write_json(
            settings,
            {
                "claudeCode.environmentVariables": [
                    {"name": MODEL_KEYS[0], "value": "first"},
                    {"name": "KEEP", "value": "yes"},
                    {"name": MODEL_KEYS[0], "value": "second"},
                ],
                "outside": {"name": MODEL_KEYS[0], "value": "keep"},
            },
        )

        result = self.run_helper("vscode-pins", settings)

        self.assertEqual(result.stdout.strip(), "VSCODE_PINS_PRESERVED")
        self.assertEqual(settings.read_bytes(), original)
        self.assertFalse(Path(str(settings) + ".scout-bak").exists())

    def test_vscode_rejects_malformed_and_duplicate_jsonc(self) -> None:
        for name, body in (
            ("malformed", b'{"claudeCode.environmentVariables": [}'),
            (
                "duplicate",
                b'{"claudeCode.environmentVariables": [], '
                b'"claudeCode.environmentVariables": []}\n',
            ),
        ):
            with self.subTest(name=name):
                settings = self.base / f"{name}.json"
                settings.write_bytes(body)
                result = self.run_helper("vscode-pins", settings)
                self.assertEqual(result.returncode, 0)
                self.assertIn("VSCODE_UNPARSEABLE", result.stdout)
                self.assertEqual(settings.read_bytes(), body)
                self.assertFalse(Path(str(settings) + ".scout-bak").exists())

    def test_noop_preserves_bytes_and_existing_backup(self) -> None:
        settings = self.base / "settings.json"
        original = b'{ // clean\n "claudeCode.environmentVariables": [],\n}\n'
        settings.write_bytes(original)
        backup = Path(str(settings) + ".scout-bak")
        backup.write_bytes(b"older recovery material\n")

        first = self.run_helper("vscode-pins", settings)
        second = self.run_helper("vscode-pins", settings)

        self.assertEqual(first.stdout.strip(), "VSCODE_PINS_NONE")
        self.assertEqual(second.stdout.strip(), "VSCODE_PINS_NONE")
        self.assertEqual(settings.read_bytes(), original)
        self.assertEqual(backup.read_bytes(), b"older recovery material\n")

    def test_settings_and_ancestor_symlinks_are_rejected(self) -> None:
        real = self.base / "real.json"
        original = self.write_json(
            real,
            {"claudeCode.environmentVariables": [{"name": MODEL_KEYS[0], "value": "x"}]},
        )
        direct = self.base / "direct.json"
        direct.symlink_to(real)
        real_dir = self.base / "real-dir"
        real_dir.mkdir()
        nested = real_dir / "settings.json"
        nested_original = self.write_json(
            nested,
            {"claudeCode.environmentVariables": [{"name": MODEL_KEYS[1], "value": "x"}]},
        )
        linked_dir = self.base / "linked-dir"
        linked_dir.symlink_to(real_dir, target_is_directory=True)

        for name, path in (("direct", direct), ("ancestor", linked_dir / "settings.json")):
            with self.subTest(name=name):
                result = self.run_helper("vscode-pins", path)
                self.assertEqual(result.returncode, 0)
                self.assertIn("VSCODE_UNSAFE_FILE", result.stdout)
        self.assertEqual(real.read_bytes(), original)
        self.assertEqual(nested.read_bytes(), nested_original)

    def test_backup_collision_and_symlink_are_not_overwritten(self) -> None:
        for name, symlink in (("collision", False), ("symlink", True)):
            with self.subTest(name=name):
                case = self.base / name
                case.mkdir()
                settings = case / "settings.json"
                original = self.write_json(
                    settings,
                    {"env": {"MAX_THINKING_TOKENS": "100"}},
                )
                backup = Path(str(settings) + ".scout-bak-modelpins")
                collision = case / "collision-target"
                collision.write_bytes(b"keep backup target\n")
                if symlink:
                    backup.symlink_to(collision)
                else:
                    backup.write_bytes(b"keep old backup\n")
                result = self.run_helper("json-pins", settings)
                self.assertEqual(result.returncode, 0)
                self.assertIn("PINS_BACKUP_FAILED", result.stdout)
                self.assertEqual(settings.read_bytes(), original)
                if symlink:
                    self.assertTrue(backup.is_symlink())
                    self.assertEqual(collision.read_bytes(), b"keep backup target\n")
                else:
                    self.assertEqual(backup.read_bytes(), b"keep old backup\n")

    def test_backup_copy_failure_preserves_original(self) -> None:
        settings = self.base / "settings.json"
        original = self.write_json(
            settings,
            {"env": {"MAX_THINKING_TOKENS": "100"}},
        )
        environment = self.install_injection(
            """import os
import shutil
_copy2 = shutil.copy2
def fail_backup(src, dst, *args, **kwargs):
    if os.fspath(dst).endswith('.scout-bak-modelpins'):
        raise OSError('injected backup failure')
    return _copy2(src, dst, *args, **kwargs)
shutil.copy2 = fail_backup
"""
        )

        result = self.run_helper("json-pins", settings, extra_env=environment)

        self.assertIn("PINS_BACKUP_FAILED", result.stdout)
        self.assertEqual(settings.read_bytes(), original)
        self.assertFalse(Path(str(settings) + ".scout-bak-modelpins").exists())

    def test_replace_failure_preserves_original_exact_backup_and_mode(self) -> None:
        settings = self.base / "settings.json"
        original = self.write_json(
            settings,
            {"env": {"MAX_THINKING_TOKENS": "100"}},
        )
        settings.chmod(0o640)
        backup = Path(str(settings) + ".scout-bak-modelpins")
        backup.write_bytes(original)
        backup.chmod(0o640)
        environment = self.install_injection(
            """import os
_replace = os.replace
def fail_target_replace(src, dst):
    if os.fspath(dst) == os.environ.get('SCOUT_TEST_REPLACE_TARGET'):
        raise OSError('injected replace failure')
    return _replace(src, dst)
os.replace = fail_target_replace
"""
        )
        environment["SCOUT_TEST_REPLACE_TARGET"] = str(settings)

        result = self.run_helper("json-pins", settings, extra_env=environment)

        self.assertIn("PINS_WRITE_FAILED", result.stdout)
        self.assertEqual(settings.read_bytes(), original)
        self.assertEqual(backup.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(settings.stat().st_mode), 0o640)
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o640)
        self.assertEqual(list(self.base.glob(".settings.*.tmp")), [])

    def test_stage_creation_failure_preserves_original_and_exact_backup(self) -> None:
        settings = self.base / "settings.json"
        original = self.write_json(
            settings,
            {"env": {"MAX_THINKING_TOKENS": "100"}},
        )
        environment = self.install_injection(
            """import tempfile
_mkstemp = tempfile.mkstemp
def fail_settings_stage(*args, **kwargs):
    if kwargs.get('prefix') == '.settings.':
        raise OSError('injected stage creation failure')
    return _mkstemp(*args, **kwargs)
tempfile.mkstemp = fail_settings_stage
"""
        )

        result = self.run_helper("json-pins", settings, extra_env=environment)

        self.assertIn("PINS_WRITE_FAILED", result.stdout)
        self.assertEqual(settings.read_bytes(), original)
        self.assertEqual(Path(str(settings) + ".scout-bak-modelpins").read_bytes(), original)
        self.assertEqual(list(self.base.glob(".settings.*.tmp")), [])

    def test_post_replace_verification_failure_reports_recovery_backup(self) -> None:
        settings = self.base / "settings.json"
        original = self.write_json(
            settings,
            {"env": {"MAX_THINKING_TOKENS": "100"}},
        )
        environment = self.install_injection(
            """import os
from pathlib import Path
_read_bytes = Path.read_bytes
_target_reads = 0
def fail_post_replace_read(self):
    global _target_reads
    if os.fspath(self) == os.environ.get('SCOUT_TEST_POST_VERIFY_TARGET'):
        _target_reads += 1
        if _target_reads == 2:
            raise OSError('injected post-replace verification failure')
    return _read_bytes(self)
Path.read_bytes = fail_post_replace_read
"""
        )
        environment["SCOUT_TEST_POST_VERIFY_TARGET"] = str(settings)

        result = self.run_helper("json-pins", settings, extra_env=environment)

        self.assertIn("PINS_POST_WRITE_FAILED", result.stdout)
        self.assertNotEqual(settings.read_bytes(), original)
        self.assertEqual(Path(str(settings) + ".scout-bak-modelpins").read_bytes(), original)

    def test_json_pins_remove_exact_scope_and_preserve_flags(self) -> None:
        settings = self.base / "settings.json"
        before = {
            "env": {
                MODEL_KEYS[0]: "old",
                "MAX_THINKING_TOKENS": "100",
                "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "200",
                "ANTHROPIC_AUTH_TOKEN": "keep",
            },
            "modelOverrides": {"opus": "live-profile"},
        }
        original = self.write_json(settings, before)
        settings.chmod(0o600)

        result = self.run_helper("json-pins", settings)

        self.assertIn("PINS_REMOVED[settings.json]", result.stdout)
        self.assertIn("FLAGS[modelOverrides,modelMappings]", result.stdout)
        after = json.loads(settings.read_text())
        self.assertEqual(after["env"], {MODEL_KEYS[0]: "old", "ANTHROPIC_AUTH_TOKEN": "keep"})
        self.assertEqual(after["modelOverrides"], {"opus": "live-profile"})
        backup = Path(str(settings) + ".scout-bak-modelpins")
        self.assertEqual(backup.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(settings.stat().st_mode), 0o600)

    def test_json_model_mappings_alone_are_byte_identical_and_not_logged(self) -> None:
        settings = self.base / "settings.json"
        before = {"env": {key: "provider-private-route" for key in MODEL_KEYS}}
        original = self.write_json(settings, before)
        inode = settings.stat().st_ino
        for _ in range(2):
            result = self.run_helper("json-pins", settings)
            self.assertIn("PINS_NONE[settings.json] FLAGS[modelMappings]", result.stdout)
            self.assertNotIn("provider-private-route", result.stdout)
            self.assertEqual(settings.read_bytes(), original)
            self.assertEqual(settings.stat().st_ino, inode)
        self.assertFalse(Path(str(settings) + ".scout-bak-modelpins").exists())

    def test_json_pins_reject_duplicate_keys(self) -> None:
        settings = self.base / "settings.json"
        original = b'{"env":{"ANTHROPIC_DEFAULT_OPUS_MODEL":"a"},"env":{}}\n'
        settings.write_bytes(original)

        result = self.run_helper("json-pins", settings)

        self.assertIn("PINS_PARSE_ERROR[settings.json]", result.stdout)
        self.assertEqual(settings.read_bytes(), original)

    def test_json_pins_reject_nonfinite_constants(self) -> None:
        settings = self.base / "settings.json"
        original = (
            b'{"env":{"ANTHROPIC_DEFAULT_OPUS_MODEL":"old"},'
            b'"values":[NaN,Infinity,-Infinity]}\n'
        )
        settings.write_bytes(original)

        result = self.run_helper("json-pins", settings)

        self.assertIn("PINS_PARSE_ERROR[settings.json]", result.stdout)
        self.assertEqual(settings.read_bytes(), original)
        self.assertFalse(Path(str(settings) + ".scout-bak-modelpins").exists())

    def test_json_pins_reject_float_overflow_before_backup(self) -> None:
        settings = self.base / "settings.json"
        original = (
            b'{"env":{"ANTHROPIC_DEFAULT_OPUS_MODEL":"old"},'
            b'"unrelated":1e999}\n'
        )
        settings.write_bytes(original)

        result = self.run_helper("json-pins", settings)

        self.assertIn("PINS_PARSE_ERROR[settings.json]", result.stdout)
        self.assertEqual(settings.read_bytes(), original)
        self.assertFalse(Path(str(settings) + ".scout-bak-modelpins").exists())

    def test_aisuite_quoted_live_direct_hook_is_preserved(self) -> None:
        script = self.base / ".aisuite/hooks/stop hook.sh"
        script.parent.mkdir(parents=True)
        script.write_text("#!/bin/sh\nexit 0\n")
        settings = self.base / "settings.json"
        original = self.write_json(
            settings,
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": f'"{script}"'}]}]}},
        )

        result = self.run_helper("aisuite-hooks", settings)

        self.assertEqual(result.stdout.strip(), "AISUITE_HOOKS_NONE[settings.json]")
        self.assertEqual(settings.read_bytes(), original)
        self.assertFalse(Path(str(settings) + ".scout-bak-aisuite").exists())

    def test_aisuite_missing_direct_hook_is_removed_without_pruning_containers(self) -> None:
        missing = self.base / ".aisuite/hooks/missing.sh"
        settings = self.base / "settings.json"
        before = {
            "hooks": {
                "Stop": [
                    {"matcher": "keep metadata", "hooks": [{"type": "command", "command": f'"{missing}"'}]},
                    {"matcher": "empty stays", "hooks": []},
                ],
                "ExistingEmptyEvent": [],
            }
        }
        original = self.write_json(settings, before)
        settings.chmod(0o640)

        result = self.run_helper("aisuite-hooks", settings)

        self.assertIn("AISUITE_HOOKS_REMOVED[settings.json]: Stop:missing.sh", result.stdout)
        after = json.loads(settings.read_text())
        self.assertEqual(after["hooks"]["Stop"][0], {"matcher": "keep metadata", "hooks": []})
        self.assertEqual(after["hooks"]["Stop"][1], {"matcher": "empty stays", "hooks": []})
        self.assertEqual(after["hooks"]["ExistingEmptyEvent"], [])
        backup = Path(str(settings) + ".scout-bak-aisuite")
        self.assertEqual(backup.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(settings.stat().st_mode), 0o640)

    def test_aisuite_recognized_wrappers_remove_only_missing_scripts(self) -> None:
        live = self.base / ".aisuite/hooks/live.py"
        live.parent.mkdir(parents=True)
        live.write_text("print('live')\n")
        missing = self.base / ".aisuite/hooks/missing.py"
        settings = self.base / "settings.json"
        self.write_json(
            settings,
            {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {"type": "command", "command": f'python3 "{live}"'},
                                {"type": "command", "command": f'/usr/bin/python3 "{missing}" --quiet'},
                            ]
                        }
                    ]
                }
            },
        )

        result = self.run_helper("aisuite-hooks", settings)

        self.assertIn("Stop:missing.py", result.stdout)
        commands = [
            hook["command"]
            for hook in json.loads(settings.read_text())["hooks"]["Stop"][0]["hooks"]
        ]
        self.assertEqual(commands, [f'python3 "{live}"'])

    def test_aisuite_unsupported_command_forms_are_preserved(self) -> None:
        missing = self.base / ".aisuite/hooks/missing.sh"
        commands = [
            f'echo "{missing}"',
            f'bash -c "{missing}"',
            f'"$HOME/.aisuite/hooks/missing.sh"',
            f'"{missing}" && echo done',
            f'env bash "{missing}"',
            f'"{missing}" "{self.base / ".aisuite/hooks/second.sh"}"',
            f'"{missing}"\necho second-command',
        ]
        settings = self.base / "settings.json"
        original = self.write_json(
            settings,
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": c} for c in commands]}]}},
        )

        result = self.run_helper("aisuite-hooks", settings)

        self.assertIn("AISUITE_HOOKS_NONE[settings.json]", result.stdout)
        self.assertIn("UNSUPPORTED[7]", result.stdout)
        self.assertEqual(settings.read_bytes(), original)

    def test_aisuite_unknown_or_missing_hook_type_is_unsupported(self) -> None:
        missing = self.base / ".aisuite/hooks/missing.sh"
        hooks = [
            {"type": "future-hook-kind", "command": str(missing)},
            {"command": str(missing)},
        ]
        settings = self.base / "settings.json"
        original = self.write_json(
            settings,
            {"hooks": {"Stop": [{"hooks": hooks}]}},
        )

        result = self.run_helper("aisuite-hooks", settings)

        self.assertIn("AISUITE_HOOKS_NONE[settings.json]", result.stdout)
        self.assertIn("UNSUPPORTED[2]", result.stdout)
        self.assertEqual(settings.read_bytes(), original)

    def test_aisuite_uncertain_target_kinds_are_unsupported(self) -> None:
        directory = self.base / ".aisuite/hooks/directory-target"
        directory.mkdir(parents=True)
        inaccessible = self.base / ".aisuite/hooks/inaccessible.sh"
        settings = self.base / "settings.json"
        original = self.write_json(
            settings,
            {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {"type": "command", "command": str(directory)},
                                {"type": "command", "command": str(inaccessible)},
                            ]
                        }
                    ]
                }
            },
        )
        environment = self.install_injection(
            """import os
from pathlib import Path
_stat = Path.stat
def deny_target(self, *args, **kwargs):
    if os.fspath(self) == os.environ.get('SCOUT_TEST_INACCESSIBLE_TARGET'):
        raise PermissionError('injected target permission error')
    return _stat(self, *args, **kwargs)
Path.stat = deny_target
"""
        )
        environment["SCOUT_TEST_INACCESSIBLE_TARGET"] = str(inaccessible)

        result = self.run_helper("aisuite-hooks", settings, extra_env=environment)

        self.assertIn("AISUITE_HOOKS_NONE[settings.json]", result.stdout)
        self.assertIn("UNSUPPORTED[2]", result.stdout)
        self.assertEqual(settings.read_bytes(), original)

    def test_aisuite_unknown_tilde_user_is_unsupported_without_traceback(self) -> None:
        command = "~scout_user_that_must_not_exist/.aisuite/hooks/missing.sh"
        settings = self.base / "settings.json"
        original = self.write_json(
            settings,
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": command}]}]}},
        )

        result = self.run_helper("aisuite-hooks", settings)

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("AISUITE_HOOKS_NONE[settings.json]", result.stdout)
        self.assertIn("UNSUPPORTED[1]", result.stdout)
        self.assertEqual(settings.read_bytes(), original)

    def test_aisuite_flags_are_reported_and_untouched(self) -> None:
        missing = self.base / ".aisuite/hooks/missing.sh"
        before = {
            "hooks": {"Stop": [{"hooks": [{"type": "command", "command": str(missing)}]}]},
            "env": {"NODE_EXTRA_CA_CERTS": str(self.base / ".aisuite/cert.pem")},
            "extraKnownMarketplaces": {"aisuite": {"source": "keep"}},
            "enabledPlugins": {"thing@aisuite": True},
        }
        settings = self.base / "settings.json"
        self.write_json(settings, before)

        result = self.run_helper("aisuite-hooks", settings)

        self.assertIn("FLAGS[cert:NODE_EXTRA_CA_CERTS,marketplace:aisuite,plugins:@aisuite]", result.stdout)
        after = json.loads(settings.read_text())
        self.assertEqual(after["env"], before["env"])
        self.assertEqual(after["extraKnownMarketplaces"], before["extraKnownMarketplaces"])
        self.assertEqual(after["enabledPlugins"], before["enabledPlugins"])

    def test_retired_allow_removes_only_scouts_exact_dx_rules(self) -> None:
        settings = self.base / "settings.json"
        before = {
            "permissions": {
                "allow": ["Bash", "mcp__plugin_sf-demo-scout_Salesforce_DX__*", "mcp__salesforce-docs__*",
                          "mcp__Salesforce_DX__*", "mcp__plugin_sf-demo-scout_Salesforce_DX__run_soql_query"],
                "deny": ["mcp__plugin_sf-demo-scout_Salesforce_DX__*"],
            },
            "env": {"KEEP_ME": "yes"},
        }
        original = self.write_json(settings, before)

        result = self.run_helper("retired-allow", settings)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "RETIRED_ALLOW_SET[settings.json]")
        after = json.loads(settings.read_text())
        self.assertEqual(after["permissions"]["allow"],  # an SE's own narrower entry stays
                         ["Bash", "mcp__salesforce-docs__*", "mcp__plugin_sf-demo-scout_Salesforce_DX__run_soql_query"])
        self.assertEqual(after["permissions"]["deny"], before["permissions"]["deny"])  # Scout never shipped a deny
        self.assertEqual(after["env"], before["env"])
        self.assertEqual([b.read_bytes() for b in self.base.glob("settings.json.scout-bak-allow-*")], [original])

        again = self.run_helper("retired-allow", settings)
        self.assertEqual(again.stdout.strip(), "RETIRED_ALLOW_NONE[settings.json]")
        self.assertEqual(len(list(self.base.glob("settings.json.scout-bak-allow-*"))), 1)

    def test_a_retired_allow_post_write_failure_is_never_reported_as_unchanged(self) -> None:
        guide = " ".join((ROOT / "prompts/setup/model-pin-strip.md").read_text().split())
        post = guide.split("`RETIRED_ALLOW_POST_WRITE_FAILED[...]`:", 1)[1].split("Any other `RETIRED_ALLOW_` result", 1)[0]
        for phrase in ("the write landed but its read-back failed", "original restored, or left as found",
                       "the backup's name", "don't call the file unchanged"):
            self.assertIn(phrase, post)
        self.assertIn("ends support for `@salesforce/mcp` on 2026-11-02", guide)

    def test_retired_allow_leaves_absent_unparsable_and_unexpected_files_unchanged(self) -> None:
        absent = self.run_helper("retired-allow", self.base / "absent.json")
        self.assertEqual(absent.stdout.strip(), "RETIRED_ALLOW_ABSENT[absent.json]")
        cases = (
            ("none.json", b'{"permissions": {"allow": ["Bash"]}}\n', "RETIRED_ALLOW_NONE[none.json]"),
            ("empty.json", b"{}\n", "RETIRED_ALLOW_NONE[empty.json]"),
            ("duplicate.json", b'{"permissions": {}, "permissions": {}}\n', "RETIRED_ALLOW_PARSE_ERROR[duplicate.json]"),
            ("string.json", b'{"permissions": {"allow": "mcp__Salesforce_DX__*"}}\n',
             "RETIRED_ALLOW_UNSAFE_PERMISSIONS[string.json]"),
            ("list.json", b'{"permissions": ["mcp__Salesforce_DX__*"]}\n', "RETIRED_ALLOW_UNSAFE_PERMISSIONS[list.json]"),
        )
        for name, content, expected in cases:
            with self.subTest(name=name):
                path = self.base / name
                path.write_bytes(content)
                result = self.run_helper("retired-allow", path)
                self.assertTrue(result.stdout.startswith(expected), result.stdout)
                self.assertEqual(path.read_bytes(), content)
        self.assertEqual(list(self.base.glob("*.scout-bak-allow-*")), [])


if __name__ == "__main__":
    unittest.main()
