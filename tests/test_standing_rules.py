"""Standing-rule delivery, using offline fixture hosts only."""
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
BULLETS = ('- Delete existing metadata or records', '- Modify existing profiles or permission sets',
           '- Touch anything prefixed `sb_` or `managed__`')
QUALIFIER = "Get the SE's explicit confirmation before:"


class StandingRulesTests(unittest.TestCase):
    setUp = fixtures.PolicyTests.setUp
    script = fixtures.PolicyTests.script

    def fixture(self, name='startup'):
        case = self.base / name
        case.mkdir()
        fx = fixtures.STARTUP.StartupFixture(case)
        run = fx.run
        fx.run = lambda **kwargs: run(plugin_root=os.environ.get('CLAUDE_PLUGIN_ROOT', ''), **kwargs)
        return fx

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
                         'prompts/building/direct-repair.md', 'append-only', 'incumbent active Paths',
                         'When developing Scout itself in this repository', 'the SE requests',
                         'Report every no-signal artifact as deployed, not as working',
                         'This is the only hard decline', 'not capability gates',
                         'have the SE confirm', 'manual/`BLOCKED` unless the SE explicitly approves',
                         'folder that contains this file', 'assignment of new or existing',
                         'Simple demo-specific LWC', 'never batch unrelated changes',
                         'Before a multi-step loop', 'orgs/lessons/INDEX.md', '`sf org display --target-org [name]`',
                         'only explicitly enabled', 'App Builder provides a live preview'):
            self.assertIn(required, text)
        command = (ROOT / 'commands/scout.md').read_text()
        host = command.index('Read `${CLAUDE_PLUGIN_ROOT}/prompts/host-runtime.md`')
        bootstrap = command.index('`${CLAUDE_PLUGIN_ROOT}/prompts/workspace-bootstrap.md`')
        rules = command.index('`${CLAUDE_PLUGIN_ROOT}/AGENTS.md`')
        self.assertLess(host, bootstrap)
        self.assertLess(bootstrap, rules)

    def test_all_worker_envelopes_carry_same_qualified_block(self):
        template = ('Scout is installed. Before any Salesforce org change, including a quick fix outside a Scout command, '
                    'read "[PLUGIN_ROOT_ABS]/AGENTS.md" and follow it.\n' + QUALIFIER + '\n' + '\n'.join(BULLETS))
        for name, copies in [('prompts/sparring/audit-orchestration.md', 2),
                             ('prompts/sparring/knowledge-cartridge.md', 1),
                             ('skills/demo-deployment-rules/SKILL.md', 1)]:
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
