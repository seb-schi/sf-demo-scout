"""Standing-rule delivery and context limits, using offline fixture hosts only."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_model_policy as fixtures

ROOT = fixtures.ROOT
RULES = fixtures.module('startup_rules_fixture', ROOT / 'scripts/startup-rules.py')
BULLETS = ('- Delete existing metadata or records', '- Modify existing profiles or permission sets',
           '- Touch anything prefixed `sb_` or `managed__`')
QUALIFIER = "Get the SE's explicit confirmation before:"


class StandingRulesTests(unittest.TestCase):
    setUp = fixtures.PolicyTests.setUp
    script = fixtures.PolicyTests.script

    def fixture(self, name='startup'):
        case = self.base / name
        case.mkdir()
        return fixtures.STARTUP.StartupFixture(case)

    def assert_block(self, text, root=ROOT):
        self.assertTrue(text.startswith('Scout is installed.'))
        self.assertIn(f'"{root}/AGENTS.md"', text[:600])
        self.assertIn(QUALIFIER, text[:600])
        for bullet in BULLETS:
            self.assertIn(bullet, text[:600])
        self.assertLess(text.index(QUALIFIER), text.index(BULLETS[0]))

    def test_rule_coverage_style_and_command_loading(self):
        text = (ROOT / 'AGENTS.md').read_text()
        self.assertLessEqual(len(text.split()), 1921)
        prose = re.sub(r'```.*?```|`[^`]*`', '', text, flags=re.S)
        self.assertNotRegex(prose, r'\b(?:CRITICAL|MANDATORY|IMPORTANT|MUST|NEVER|ALWAYS|DO NOT)\b')
        for bullet in BULLETS:
            self.assertEqual(text.count(bullet), 1)
        for required in ('Record-triggered flows', 'Screen flows', 'Autolaunched flows', 'subflows',
                         'Scheduled flows', 'Platform-event-triggered flows', 'Apex:', 'LWC',
                         'Agentforce', 'Email-to-Case', 'Authorable + build-time signal',
                         'Authorable + no build-time signal', 'Docs-confirmed UI-only',
                         'Companion Permission Set', 'Object CRUD', 'Field Read + Edit',
                         'RecordTypeVisibility', 'TabVisibility', 'AppVisibility',
                         'prompts/building/direct-repair.md', 'append-only', 'incumbent active Paths'):
            self.assertIn(required, text)
        for name in ('scout-sparring', 'scout-building'):
            command = (ROOT / f'commands/{name}.md').read_text()
            host = command.index('Read `${CLAUDE_PLUGIN_ROOT}/prompts/host-runtime.md`')
            rules = command.index('Read `${CLAUDE_PLUGIN_ROOT}/AGENTS.md`')
            bootstrap = command.index('Read `${CLAUDE_PLUGIN_ROOT}/prompts/workspace-bootstrap.md`')
            self.assertLess(host, rules)
            self.assertLess(rules, bootstrap)

    def test_all_worker_envelopes_carry_same_qualified_block(self):
        template = ('Scout is installed. Before any Salesforce org change, including a quick fix outside a Scout command, '
                    'read "[PLUGIN_ROOT_ABS]/AGENTS.md" and follow it.\n' + QUALIFIER + '\n' + '\n'.join(BULLETS))
        for name, copies in [('commands/scout-building.md', 1), ('commands/scout-sparring.md', 1),
                             ('prompts/sparring/audit-orchestration.md', 2),
                             ('prompts/sparring/knowledge-cartridge.md', 1)]:
            with self.subTest(file=name):
                text = (ROOT / name).read_text()
                text = '\n'.join(re.sub(r'^\s*(?:> ?)?', '', line) for line in text.splitlines())
                self.assertEqual(text.count(template), copies)
        audit = (ROOT / 'prompts/sparring/audit-orchestration.md').read_text()
        self.assertIn('redispatch the prelude envelope', audit)
        self.assertIn('auto-redispatch the envelope', audit)

    def test_global_plain_json_and_normal_context_roundtrip(self):
        fx = self.fixture()
        outside = self.base / 'outside'
        outside.mkdir()
        self.assertEqual(fx.run(cwd=outside).stdout, '')  # No root fails open.
        fx.run()  # Warm the existing org-evidence cache before comparing bytes.
        legacy = fx.run().stdout
        with patch.dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)):
            block = fx.run(cwd=outside).stdout
            self.assert_block(block)
            self.assertLessEqual(len(block), 600)
            self.assertEqual(fx.run().stdout, block + legacy)
            self.assertEqual(fx.run(cwd=outside, host='codex').stdout, block)
            running = self.script('client', 'echo 2.1.280\n')
            os.environ.update(CLAUDE_CODE_ENTRYPOINT='claude-desktop-3p', CLAUDE_CODE_EXECPATH=str(running))
            outside_json = json.loads(fx.run(cwd=outside).stdout)
            self.assertEqual(outside_json['hookSpecificOutput']['additionalContext'], block)
            self.assertIn('desktop app', outside_json['systemMessage'])
            inside = json.loads(fx.run().stdout)['hookSpecificOutput']['additionalContext']
            self.assertEqual(inside, block + legacy)
        # Outside-workspace runs never invoke org or MCP probes.
        fx.log.unlink()
        with patch.dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)):
            fx.run(cwd=outside)
        self.assertFalse(fx.log.exists())

    def test_folder_budgets_30_and_100_keep_recent_complete_entries(self):
        for count in (30, 100):
            with self.subTest(count=count):
                fx = self.fixture(str(count))
                orgs = fx.workspace / 'orgs'
                orgs.mkdir()
                for n in range(count):
                    path = orgs / ('qa-a-' + str(n).zfill(3) + '-' + 'x'*235)
                    path.mkdir()
                    os.utime(path, (1700000000+n, 1700000000+n))
                with patch.dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)):
                    text = fx.run().stdout
                    self.assert_block(text)
                    self.assertLessEqual(len(text), 10000)
                    if 'more folders' in text:
                        rows = re.findall(r'^  - (\d{3})-', text, re.M)
                        self.assertEqual(list(map(int, rows)), list(range(count-1, count-len(rows)-1, -1)))
                        self.assertIn(f'…and {count-len(rows)} more folders in `orgs/`', text)
                    running = self.script('client', 'echo 2.1.280\n')
                    with patch.dict(os.environ, CLAUDE_CODE_EXECPATH=str(running), CLAUDE_CODE_ENTRYPOINT='claude-vscode'):
                        result = fx.run()
                    context = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
                    self.assert_block(context)
                    self.assertLessEqual(len(context), 10000)

    def test_bad_roots_probe_and_json_failures_keep_fail_open_output(self):
        fx = self.fixture()
        outside = self.base / 'outside'
        outside.mkdir()
        fx.run()  # Warm the existing org-evidence cache before comparing bytes.
        legacy = fx.run().stdout
        for root in ('', 'relative', '/'+'x'*600, '/a\nnot-a-path', '/a\rnot-a-path'):
            with self.subTest(root=root[:20]), patch.dict(os.environ, CLAUDE_PLUGIN_ROOT=root):
                self.assertEqual(fx.run(cwd=outside).stdout, '')
                self.assertEqual(fx.run().stdout, legacy)
        # Quoting is literal data, never an executable interpolation.
        root = '/fixture/a"quoted\\root'
        with patch.dict(os.environ, CLAUDE_PLUGIN_ROOT=root):
            text = fx.run(cwd=outside).stdout
            self.assertIn('a\\"quoted\\\\root/AGENTS.md', text)
            self.assertLessEqual(len(text), 600)
        with patch.dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)):
            block = fx.run(cwd=outside).stdout
            running = self.script('client', 'echo 2.1.280\n')
            os.environ.update(CLAUDE_CODE_EXECPATH=str(running), CLAUDE_CODE_ENTRYPOINT='cli')
            for body in ('echo garbage', 'exit 1', 'sleep 4'):
                self.script('client', body+'\n')
                self.assertEqual(fx.run(cwd=outside).stdout, block)
            self.script('client', 'echo 2.1.280\n')
            failing = self.base / 'bad-json.py'
            failing.write_text('import sys\nsys.exit(1)\n')
            self.assertEqual(fx.run(cwd=outside, helper=failing).stdout, block)

    def test_nonfolder_overflow_and_renderer_failure_are_bounded_or_unchanged(self):
        context = 'Scout rules first\n' + 'x'*12000
        bounded = RULES.bound_context(context, self.base, '')
        self.assertTrue(bounded.startswith('Scout rules first\n'))
        self.assertEqual(len(bounded), 10000)
        self.assertIn('additional startup context omitted', bounded)
        unicode_context = 'Scout rules first\n' + '🧪'*7000
        bounded = RULES.bound_context(unicode_context, self.base, '')
        self.assertLessEqual(len(bounded.encode('utf-16-le')) // 2, 10000)
        # Exercise the new renderer's explicit failure path without deleting code.
        fx = self.fixture()
        orgs = fx.workspace / 'orgs'
        orgs.mkdir()
        for n in range(100):
            (orgs / ('qa-a-' + str(n).zfill(3) + '-' + 'x'*220)).mkdir()
        fx.run()  # Warm the existing org-evidence cache before comparing bytes.
        legacy = fx.run().stdout
        python = fx.bin / 'python3'
        python.unlink()
        python.write_text('#!/bin/bash\ncase "$*" in *startup-rules.py*) exit 1;; esac\n'
                          f'exec "{sys.executable}" "$@"\n')
        python.chmod(0o700)
        with patch.dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)):
            self.assertEqual(fx.run().stdout, legacy)
