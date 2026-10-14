"""Scout 2.0 (2026-10-14): the classic commands are thin trampolines into /scout; their old bodies sit inert."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
GATE = ("On Claude, when this session identifies its model as an Opus, Sonnet or Haiku model older than 5.5, send only "
        "“Heads-up: this is a Classic command, and Scout 2.0 is built for Opus 5.5 and later. Pick Opus 5.5 (model picker or `/model`), "
        "then run `/scout` with your {}. Details in #sf-demo-scout.” and stop.")


def frontmatter(text):
    return text.split('---')[1]


def tools(text):
    return set(re.search(r'^allowed-tools: (.+)$', frontmatter(text), re.M)[1].split(', '))


class ClassicTrampolineTests(unittest.TestCase):
    def setUp(self):
        self.scout = (ROOT / 'commands/scout.md').read_text()
        self.shells = {name: (ROOT / 'commands' / f'{name}.md').read_text() for name in ('scout-sparring', 'scout-building')}

    def test_shells_carry_scouts_exact_tools_and_no_dx_mcp(self):
        for name, text in self.shells.items():
            with self.subTest(name=name):
                self.assertEqual(tools(text), tools(self.scout))
                self.assertNotIn('Salesforce_DX', text)
                self.assertRegex(frontmatter(text), rf'(?m)^name: {name}$')

    def test_shells_gate_old_models_then_note_and_follow_scout(self):
        for name, noun in (('scout-sparring', 'request'), ('scout-building', 'spec')):
            text = self.shells[name]
            with self.subTest(name=name):
                self.assertEqual(text.count(GATE.format(noun)), 1)
                self.assertIn('$ARGUMENTS', text)
                self.assertIn(f'“Heads-up: `/{name}` is a Classic command. Scout 2.0 replaces it, so I\'m starting `/scout`', text)
                host = text.index('${CLAUDE_PLUGIN_ROOT}/prompts/host-runtime.md')
                scout = text.index('read `commands/scout.md` from that root and follow it exactly')
                self.assertLess(text.index(GATE.format(noun)), host)
                self.assertLess(host, scout)
                self.assertLessEqual(len(text.split()), 220)

    def test_building_hands_its_spec_to_scout_as_the_brief(self):
        text = self.shells['scout-building']
        for phrase in ('with your spec as the brief', 'the newest `demo-spec-*.md` in the customer folder you settle on',
                       'The spec is a supplied plan', 'confirmation still applies'):
            self.assertIn(phrase, text)
        self.assertIn('Treat a supplied demo plan, requirements or discovery notes as the brief', self.scout)

    def test_classic_bodies_are_inert(self):
        for name in self.shells:
            body = ROOT / 'prompts/classic' / f'{name}.md'
            self.assertTrue(body.is_file(), body)
            self.assertIn('kept inert, unreferenced, for a quick rollback until 2.1 removes it', body.read_text())
        for path in [*(ROOT / 'commands').glob('*.md'), *(ROOT / 'hooks').glob('*'), ROOT / 'AGENTS.md']:
            with self.subTest(path=path.name):
                self.assertNotIn('prompts/classic/', path.read_text())


if __name__ == '__main__':
    unittest.main()
