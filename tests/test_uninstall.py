"""The user-facing uninstall removes only Scout's own folders, never follows links, and changes nothing on a dry run."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import stand_ins

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'scout_uninstall.py'


class UninstallTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix='scout-uninstall-'))
        self.config = self.home / '.config' / 'sf-demo-scout'
        self.cache = self.home / '.cache' / 'sf-demo-scout'
        self.workspace = self.home / 'claude-projects' / 'sf-demo-scout'
        for folder in (self.config, self.cache, self.workspace / 'orgs' / 'acme'):
            folder.mkdir(parents=True)
            (folder / 'note.txt').write_text('x')
        self.make_workspace(self.workspace)
        self.name_workspace(self.workspace)

    def make_workspace(self, folder, claude=True):
        """A workspace as Scout's setup leaves it; Claude's project settings only on Claude."""
        (folder / 'orgs' / 'lessons').mkdir(parents=True, exist_ok=True)
        (folder / 'orgs' / 'lessons' / 'INDEX.md').write_text('# Lessons Index\n\nTopic-clustered lessons from ...\n')
        (folder / 'sfdx-project.json').write_text('{}')
        if claude:
            (folder / '.claude').mkdir(exist_ok=True)
            (folder / '.claude' / 'settings.json').write_text('{}')

    def name_workspace(self, folder):
        (self.config / 'config.json').write_text(json.dumps({'workspace_path': str(folder)}))

    def run_script(self, *arguments, **environment):
        env = {key: value for key, value in os.environ.items() if key != 'SCOUT_WORKSPACE'}
        env.update(HOME=str(self.home), USERPROFILE=str(self.home), PYTHONDONTWRITEBYTECODE='1', **environment)
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *arguments], capture_output=True, text=True,
                              env=env, timeout=30)

    def test_a_dry_run_lists_the_plan_and_removes_nothing(self):
        result = self.run_script('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('UNINSTALL_PLAN %s' % self.config, result.stdout)
        self.assertIn('UNINSTALL_PLAN %s' % self.cache, result.stdout)
        self.assertNotIn(str(self.workspace), result.stdout)
        self.assertTrue(self.config.exists() and self.cache.exists() and self.workspace.exists())

    def test_a_real_run_needs_an_explicit_mode(self):
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.config.exists())

    def test_yes_removes_config_and_cache_and_keeps_the_workspace(self):
        result = self.run_script('--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.config.exists())
        self.assertFalse(self.cache.exists())
        self.assertTrue((self.workspace / 'orgs' / 'acme' / 'note.txt').exists())

    def test_the_workspace_goes_only_when_asked_and_the_plan_comes_first(self):
        preview = self.run_script('--workspace', '--dry-run')
        self.assertIn('UNINSTALL_PLAN %s' % self.workspace, preview.stdout)
        result = self.run_script('--workspace', '--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[:3], preview.stdout.splitlines())  # the same plan, shown before anything goes
        self.assertTrue(all(line.startswith('UNINSTALL_REMOVED') for line in lines[3:]), lines)
        self.assertIn('UNINSTALL_REMOVED %s' % self.workspace, result.stdout)
        self.assertFalse(self.workspace.exists())

    def test_a_custom_workspace_named_by_the_configuration_is_the_one_removed(self):
        custom = self.home / 'work' / 'scout'
        self.make_workspace(custom)
        self.name_workspace(custom)
        result = self.run_script('--workspace', '--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(custom.exists())
        self.assertTrue((self.workspace / 'orgs' / 'acme' / 'note.txt').exists())

    def test_codex_workspaces_and_overrides_without_configuration_are_recognised(self):
        codex = self.home / 'codex-workspace'
        self.make_workspace(codex, claude=False)
        (self.config / 'config.json').unlink()
        result = self.run_script('--workspace', '--yes', SCOUT_WORKSPACE=str(codex))
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(codex.exists())

    def test_an_ordinary_project_with_the_usual_files_is_never_removed(self):
        project = self.home / 'dx-project'
        for folder in ('orgs/exports', '.claude'):
            (project / folder).mkdir(parents=True)
        (project / 'sfdx-project.json').write_text('{}')
        (project / '.claude' / 'settings.json').write_text('{}')
        (project / 'orgs' / 'lessons').mkdir()
        (project / 'orgs' / 'lessons' / 'INDEX.md').write_text('# Our team notes\n')
        (self.config / 'config.json').unlink()
        result = self.run_script('--workspace', '--yes', SCOUT_WORKSPACE=str(project))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not recognisably Scout's workspace", result.stdout)
        self.assertTrue((project / 'sfdx-project.json').exists())
        self.assertTrue(self.config.parent.exists() and self.cache.exists())

    def test_the_standing_rule_settles_the_workspace_before_anything_is_removed(self):
        rules = (Path(__file__).resolve().parents[1] / 'AGENTS.md').read_text()
        rule = rules[rules.index('## Uninstall'):]
        self.assertLess(rule.index('--workspace'), rule.index('--yes'))  # one decision, one preview, one run

    def test_a_mistaken_parent_folder_is_never_removed(self):
        other = self.home / 'claude-projects' / 'other-project'
        other.mkdir()
        (other / 'keep.txt').write_text('keep')
        parent = self.home / 'claude-projects'
        for config in (True, False):
            with self.subTest(configuration_names_the_workspace=config):
                if not config:
                    (self.config / 'config.json').unlink()
                result = self.run_script('--workspace', '--yes', SCOUT_WORKSPACE=str(parent))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('UNINSTALL_REFUSED %s' % (self.workspace if config else parent), result.stdout)
                self.assertNotIn('UNINSTALL_REMOVED', result.stdout)  # a refused plan removes nothing at all
                self.assertTrue((other / 'keep.txt').exists())
                self.assertTrue((self.workspace / 'orgs' / 'acme' / 'note.txt').exists())
                self.assertTrue(self.cache.exists())

    @stand_ins.needs_symlinks
    def test_a_linked_folder_loses_only_its_link(self):
        elsewhere = self.home / 'elsewhere'
        elsewhere.mkdir()
        (elsewhere / 'keep.txt').write_text('keep')
        for path in self.cache.iterdir():
            path.unlink()
        self.cache.rmdir()
        self.cache.symlink_to(elsewhere, target_is_directory=True)
        result = self.run_script('--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.lexists(self.cache))
        self.assertTrue((elsewhere / 'keep.txt').exists())

    def test_a_workspace_outside_the_home_folder_is_refused(self):
        outside = Path(tempfile.mkdtemp(prefix='scout-outside-'))
        (self.config / 'config.json').unlink()  # so the override is the only workspace named
        result = self.run_script('--workspace', '--yes', SCOUT_WORKSPACE=str(outside))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('UNINSTALL_REFUSED %s' % outside, result.stdout)
        self.assertTrue(outside.exists())

    def test_absent_folders_are_reported_not_failed(self):
        self.run_script('--yes')
        result = self.run_script('--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('UNINSTALL_ABSENT %s' % self.config, result.stdout)


if __name__ == '__main__':
    unittest.main()
