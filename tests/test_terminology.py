"""Public Scout serves anyone who builds with it, so its shipped files call that person the builder, never the SE.

Shipped means every tracked file except CHANGELOG.md, whose history stays as written, and tests/. The check is
case-sensitive and matches only the standalone word (SE, SEs, SE's), so identifiers and data tokens such as
`se-stated` or `--keep-se-choices` never count. Text that must keep the word is listed in ALLOWED with its file and
the reason; only that exact text is exempt, and only in that file.
"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_public_hygiene import ROOT, tracked_files

WORD = re.compile(r"\bSE(?:s|['’]s)?\b")
ALLOWED = {
    # Specs written before 2.1.3 mark prose fields the builder refines this way, and validation still reads them.
    ('prompts/building/sub-agent-validation.md', '`⚠️ SE refines'),
    # Change logs written before 2.4.1 use this heading, which the history reader keeps accepting.
    ('scripts/scout_history.py', 'SE Must Do Next'),
}


def shipped(name):
    return name != 'CHANGELOG.md' and not name.startswith('tests/')


def findings(files, allowed=ALLOWED):
    found = []
    for path, name in files:
        if not shipped(name):
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        exempt = [exact for kept, exact in allowed if kept == name]
        for number, line in enumerate(text.splitlines(), 1):
            checked = line
            for exact in exempt:
                checked = checked.replace(exact, '')
            if WORD.search(checked):
                found.append('%s:%d: %s' % (name, number, line.strip()[:120]))
    return found


class TerminologyTests(unittest.TestCase):
    def test_shipped_files_call_the_person_the_builder(self):
        self.assertEqual(findings(tracked_files()), [])

    def test_every_exception_is_still_needed(self):
        for name, exact in sorted(ALLOWED):
            with self.subTest(file=name):
                path = ROOT / name
                text = path.read_text(encoding='utf-8') if path.is_file() else ''
                self.assertIn(exact, text, 'no longer in the file: drop it from ALLOWED')

    def test_every_form_fires_and_exceptions_stay_scoped(self):
        leaks = ['Ask the SE first.', 'for SEs on top', "on the SE's yes", 'on the SE’s yes',
                 'the first SE-facing message', 'SE: at the start of a line', '(SE)',
                 '`⚠️ SE refines` outside its one allowed file']
        clean = ['the builder', '`se-stated` and `se-confirmed`', '--keep-se-choices', 'SEO, USE and BASE', 'case SE_X:']
        kept = ['`⚠️ SE refines` stays', '`⚠️ SE refines` stays, but the SE does not']
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'tests').mkdir()
            (root / 'leaks.md').write_text('\n'.join(leaks), encoding='utf-8')
            (root / 'clean.md').write_text('\n'.join(clean), encoding='utf-8')
            (root / 'kept.md').write_text('\n'.join(kept), encoding='utf-8')
            (root / 'CHANGELOG.md').write_text('The SE said yes.\n', encoding='utf-8')
            (root / 'tests/test_x.py').write_text("PHRASE = 'the SE'\n", encoding='utf-8')
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            subprocess.run(['git', 'add', '.'], cwd=root, check=True)
            found = findings(tracked_files(root), allowed={('kept.md', '`⚠️ SE refines`')})
        flagged = {':'.join(f.split(':')[:2]) for f in found}
        self.assertEqual(flagged, {'leaks.md:%d' % n for n in range(1, len(leaks) + 1)} | {'kept.md:2'}, found)


if __name__ == '__main__':
    unittest.main()
