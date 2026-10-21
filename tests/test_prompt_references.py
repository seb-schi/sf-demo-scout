"""Every plugin-root path that Scout's prompts, commands, skills, hooks and standing rules name exists in the tree.

Deleting a prompt or helper must not leave a pointer the model would try to follow. A path is checked when it is
written after one of the root tokens Scout uses (`${CLAUDE_PLUGIN_ROOT}`, `[PLUGIN_ROOT_ABS]`, `[PLUGIN_ROOT]`,
`[SCOUT_ROOT]`). Paths with a placeholder in them, such as `<helper>` or `{name}`, name a family, not a file, and are
skipped.
"""
import os
import re
import unittest
from pathlib import Path

ROOT = Path(os.environ.get('SCOUT_REFERENCE_ROOT') or Path(__file__).resolve().parents[1])
SOURCES = ('prompts', 'commands', 'skills', 'hooks')
TOKEN = re.compile(r'(?:\$\{CLAUDE_PLUGIN_ROOT\}|\[PLUGIN_ROOT_ABS\]|\[PLUGIN_ROOT\]|\[SCOUT_ROOT\])/([^\s`"\'()<>|,;\]\\]+)')
PLACEHOLDER = re.compile(r'[<{\[*]')


def referenced_paths(root=ROOT):
    files = [root / 'AGENTS.md'] + [path for folder in SOURCES for path in sorted((root / folder).rglob('*'))
                                    if path.is_file() and path.suffix in {'.md', '.sh', '.py', '.json'}]
    for path in files:
        try:
            text = path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for match in TOKEN.finditer(line):
                target = match.group(1).split('#', 1)[0].split('§', 1)[0].rstrip('.:*')
                if target and not PLACEHOLDER.search(target):
                    yield path.relative_to(root).as_posix(), number, target


class PromptReferenceTests(unittest.TestCase):
    def test_every_named_plugin_path_exists(self):
        missing = ['%s:%d: %s' % (name, number, target) for name, number, target in referenced_paths()
                   if not (ROOT / target).exists()]
        self.assertEqual(missing, [])

    def test_the_scanner_sees_references(self):
        self.assertGreater(len(list(referenced_paths())), 50)


if __name__ == '__main__':
    unittest.main()
