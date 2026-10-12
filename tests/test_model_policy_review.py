"""Regressions for W2 review: provenance, host identity, cache and dispatch."""
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_model_policy as fixtures

CLIENT, PIN, REPORT, ROOT = fixtures.CLIENT, fixtures.PIN, fixtures.REPORT, fixtures.ROOT


class ReviewTests(unittest.TestCase):
    setUp = fixtures.PolicyTests.setUp
    script = fixtures.PolicyTests.script
    collect = fixtures.PolicyTests.collect

    def test_environment_distinct_value_and_real_source_duplicates(self):
        path = self.home / '.claude/settings.json'
        path.parent.mkdir()
        path.write_text(json.dumps({'env': {PIN: 'claude-sonnet-4-6'}}))
        (self.home / '.zshrc').write_text(f'export {PIN}=claude-sonnet-4-6\n')
        os.environ[PIN] = 'claude-sonnet-4-6'
        rows, provider, failed = self.collect(self.home)
        self.assertEqual(len([r for r in rows if r['key'] == PIN]), 2)
        self.assertNotIn('session environment', '\n'.join(REPORT.report(rows, provider, failed)))
        os.environ[PIN] = 'claude-sonnet-4-5'
        rows, provider, failed = self.collect(self.home)
        self.assertEqual(len([r for r in rows if r['key'] == PIN]), 3)
        text = '\n'.join(REPORT.report(rows, provider, failed))
        self.assertIn('set outside the files Scout read (shell profile, launch agent or host app)', text)
        self.assertIn('Remove it at this source first', text)

    def test_observed_entrypoints_and_host_parity(self):
        running = self.script('running', 'echo 2.1.280\n')
        os.environ['CLAUDE_CODE_EXECPATH'] = str(running)
        for entry, kind, remedy in [('claude-vscode', 'IDE', 'extension in your IDE'),
                                   ('claude-jetbrains', 'IDE', 'extension in your IDE'),
                                   ('claude-desktop-3p', 'desktop', 'desktop app'),
                                   ('cli', 'terminal', 'installer/updater'),
                                   ('unexpected', 'Claude Code', 'this Claude Code client')]:
            with self.subTest(entry=entry):
                os.environ['CLAUDE_CODE_ENTRYPOINT'] = entry
                observation = CLIENT.observe()
                self.assertEqual(observation['kind'], kind)
                self.assertIn(remedy, CLIENT.floor_line(observation))
        detector = runpy.run_path(str(ROOT / 'scripts/setup-mcp-status.py'))['active_host']
        for explicit in (None, '', 'claude', 'codex', 'other'):
            for claude in ('', '1'):
                for codex in ('', 'synthetic'):
                    env = {'CLAUDECODE': claude, 'CODEX_THREAD_ID': codex}
                    if explicit is not None:
                        env['SCOUT_HOST'] = explicit
                    with patch.dict(os.environ, env, clear=True):
                        self.assertEqual(CLIENT.active_host(), detector())

    def test_cache_hit_miss_change_corruption_and_failed_io(self):
        calls = self.base / 'calls'
        running = self.script('running', f'echo call >> "{calls}"\necho 2.1.280\n')
        data = self.home / 'data'
        os.environ.update(CLAUDE_CODE_EXECPATH=str(running), CLAUDE_CODE_ENTRYPOINT='claude-vscode',
                          CLAUDE_PLUGIN_DATA=str(data))
        cache = data / 'scout-client-versions.txt'
        self.assertEqual(CLIENT.observe()['version'], '2.1.280')
        self.assertEqual(len(calls.read_text().splitlines()), 1)
        self.assertEqual(CLIENT.observe()['version'], '2.1.280')
        self.assertEqual(len(calls.read_text().splitlines()), 1)
        self.script('running', f'echo changed >> "{calls}"\necho 2.1.296\n')
        self.assertEqual(CLIENT.observe()['version'], '2.1.296')
        self.assertEqual(len(calls.read_text().splitlines()), 2)
        cache.write_text('{broken')
        self.assertEqual(CLIENT.observe()['version'], '2.1.296')
        self.assertEqual(len(calls.read_text().splitlines()), 3)
        original_open = os.open
        def unreadable_cache(path, *args, **kwargs):
            if str(path) == str(cache):
                raise PermissionError('fixture unreadable')
            return original_open(path, *args, **kwargs)
        with patch.object(CLIENT.os, 'open', side_effect=unreadable_cache):
            self.assertEqual(CLIENT.observe()['version'], '2.1.296')
        self.assertEqual(len(calls.read_text().splitlines()), 4)
        data_file = self.home / 'not-a-directory'
        data_file.write_text('keep')
        os.environ['CLAUDE_PLUGIN_DATA'] = str(data_file)
        self.assertEqual(CLIENT.observe()['version'], '2.1.296')
        self.assertEqual(len(calls.read_text().splitlines()), 5)
        self.assertEqual(data_file.read_text(), 'keep')
        os.environ['CLAUDE_PLUGIN_DATA'] = str(data)
        cache.unlink()
        with patch.object(CLIENT.os, 'replace', side_effect=PermissionError('fixture unwritable')):
            self.assertEqual(CLIENT.observe()['version'], '2.1.296')
        self.assertEqual(list(data.iterdir()), [])

    def test_cache_bounded_symlink_fifo_and_changed_during_probe(self):
        data = self.home / 'data'
        data.mkdir()
        cache = data / 'scout-client-versions.txt'
        os.environ['CLAUDE_PLUGIN_DATA'] = str(data)
        for n in range(20):
            running = self.script(f'running-{n}', 'echo 2.1.280\n')
            os.environ['CLAUDE_CODE_EXECPATH'] = str(running)
            self.assertEqual(CLIENT.observe()['version'], '2.1.280')
        self.assertEqual(len(CLIENT.read_cache(str(cache))), 16)
        self.assertLessEqual(cache.stat().st_size, 16384)
        outside = self.home / 'outside'
        outside.write_text('unchanged')
        cache.unlink()
        cache.symlink_to(outside)
        self.assertEqual(CLIENT.observe()['version'], '2.1.280')
        self.assertEqual(outside.read_text(), 'unchanged')
        cache.unlink()
        os.mkfifo(cache)
        self.assertEqual(CLIENT.read_cache(str(cache)), [])

        cache.unlink()
        # A replacement during --version must not cache the earlier key.
        original = CLIENT.fingerprint(str(running))
        with patch.object(CLIENT, 'fingerprint', side_effect=[original, [original[0], 1, 2]]):
            self.assertEqual(CLIENT.observe()['version'], '2.1.280')
        self.assertFalse(cache.exists())
        cache.write_text('x' * 16385)
        self.assertEqual(CLIENT.read_cache(str(cache)), [])

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS stat fast path; other hosts use Python')
    def test_shell_fast_path_checks_full_fingerprint_and_rejects_bad_cache(self):
        running = self.script('current client', 'echo 2.1.296\n')
        os.environ.update(CLAUDE_CODE_EXECPATH=str(running), CLAUDE_PLUGIN_DATA=str(self.home / 'data'))
        def fast():
            return subprocess.run(['/bin/bash', '-c', 'source "$1"; scout_current_client_cached',
                                   'fixture', str(ROOT / 'scripts/client-cache.sh')], capture_output=True).returncode
        self.assertEqual(fast(), 1)
        self.assertEqual(CLIENT.observe()['version'], '2.1.296')
        self.assertEqual(fast(), 0)
        cache = Path(CLIENT.cache_path())
        content = cache.read_bytes()
        cache.write_bytes(content + b'/bad\n0\n0\nnot-a-version\n')
        self.assertEqual(fast(), 1)  # Even corruption after a matching entry fails open.
        cache.write_bytes(content)
        info = running.stat()
        os.utime(running, ns=(info.st_atime_ns, info.st_mtime_ns + 1000))
        self.assertEqual(fast(), 1)
        CLIENT.observe()
        self.assertEqual(fast(), 0)
        with patch.dict(os.environ, SCOUT_HOST='codex'):
            self.assertEqual(fast(), 1)
        running.write_text('#!/bin/bash\necho 2.1.280\n')
        self.assertEqual(fast(), 1)
        CLIENT.observe()
        self.assertEqual(fast(), 1)  # Below-floor hits use cached Python rendering.

    def test_advisory_and_every_dispatch_contract(self):
        for provider, wizard in [('bedrock', '/setup-bedrock'), ('vertex', '/setup-vertex')]:
            for value in (None, 'claude-sonnet-4-6', 'claude-sonnet-5-5', 'sonnet', 'unrecognized'):
                rows = [] if value is None else [dict(key=PIN, value=value, kind='user', surface='fixture')]
                output = '\n'.join(REPORT.report(rows, provider))
                self.assertEqual('Model routing advisory:' in output, value is None)
                if value is None:
                    self.assertIn(wizard, output)
                    self.assertIn('pin Sonnet 5.5', output)
        for provider in ('api', 'aws', 'foundry', 'unknown'):
            self.assertNotIn('Model routing advisory:', '\n'.join(REPORT.report([], provider)))
        for relative in ('commands/scout-building.md', 'commands/scout-sparring.md',
                         'prompts/sparring/audit-orchestration.md', 'prompts/sparring/knowledge-cartridge.md'):
            self.assertIn('prompts/host-runtime.md#worker-model-mirroring', (ROOT / relative).read_text())
        audit = (ROOT / 'prompts/sparring/audit-orchestration.md').read_text()
        self.assertIn('prelude, all\n   three audit worker calls, and every redispatch', audit)
        contract = (ROOT / 'prompts/host-runtime.md').read_text()
        for phrase in ('per-call `model`', "orchestrator's own model family", 'omit `model`',
                       'CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1', 'Codex keeps'):
            self.assertIn(phrase, contract)

