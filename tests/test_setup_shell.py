"""Execute shipped setup fences against disposable homes and fake tools."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


FOLDERS = ('commands', 'prompts', 'skills/scout', 'skills/scout-setup')  # the entry skills carry setup's first fence
NEEDS_ZSH = unittest.skipUnless(Path('/bin/zsh').exists(), 'parses the fences with /bin/zsh')
NEEDS_BOTH = unittest.skipUnless(Path('/bin/bash').exists() and Path('/bin/zsh').exists(),
                                 'runs the fences in /bin/bash and /bin/zsh')


def fences():
    for folder in FOLDERS:
        for path in sorted((ROOT / folder).rglob('*.md')):
            for block in re.findall(r'^[ \t]*```bash\n(.*?)^[ \t]*```[ \t]*$', path.read_text(), re.S | re.M):
                block = block.rstrip('\n')
                wrapped = re.fullmatch(r"/bin/bash <<'([A-Z0-9_]+)'\n(.*?)\n\1", block, re.S)
                yield path, wrapped[1] if wrapped else None, wrapped[2] if wrapped else block


class SetupShellTests(unittest.TestCase):
    @NEEDS_ZSH
    def test_no_bash_only_lookup_in_markdown_and_every_fence_parses_in_zsh(self):
        count = 0
        for folder in FOLDERS:
            for path in (ROOT / folder).rglob('*.md'):
                self.assertNotIn('type -P', path.read_text(), str(path))
        for path, marker, body in fences():
            with self.subTest(path=path, marker=marker):
                # Bind literal documentation operands; never execute these org examples.
                source = re.sub(r'<(?:ORG_ALIAS|FlowName|ClassName)>', 'fixture', body)
                result = subprocess.run(['/bin/zsh', '-f', '-n'], input=source, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                count += 1
        self.assertEqual(count, 33)  # every shipped fence; update when a prompt adds or removes one

    def test_setup_command_has_one_whole_fence_rule(self):
        command = (ROOT / 'skills/scout-setup/SKILL.md').read_text()
        self.assertEqual(command.count('Run each bash fence'), 1)
        for phrase in ('every setup prompt it dispatches', 'in its own Bash call',
                       'exactly as written once placeholders are substituted',
                       "Keep any `/bin/bash <<'…'` wrapper", "don't merge fences or retype their bodies",
                       'because the tool shell may be zsh'):
            self.assertIn(phrase, command)

    def test_no_setup_fence_needs_a_bash_heredoc_any_more(self):
        # Every fence Codex and Cursor run is one command, so PowerShell and cmd.exe can run it too.
        wrapped = [(path.name, marker) for path, marker, _ in fences() if marker]
        self.assertEqual(wrapped, [])

    @NEEDS_BOTH
    def test_refresh_reports_the_running_client_without_updating_it(self):
        refresh = (ROOT / 'prompts/setup/refresh.md').read_text()
        block = next(b for _, _, b in fences() if 'client-version.py' in b)
        unverified = 'Running Claude client binary: unverified — Python or the shipped helper is unavailable\n'
        for case in ('reported', 'no-python', 'no-helper'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as raw:
                home = Path(raw).resolve(); tools = home / 'bin'; tools.mkdir()
                if case != 'no-python':
                    (tools / 'python3').symlink_to(sys.executable)
                npm = tools / 'npm'
                npm.write_text('#!/bin/bash\necho called > "$HOME/npm-called"\nexit 99\n'); npm.chmod(0o700)
                client = home / 'claude'
                client.write_text('#!/bin/bash\necho "2.1.296 (Claude Code)"\n'); client.chmod(0o700)
                root = home / 'missing-root' if case == 'no-helper' else ROOT
                env = dict(HOME=str(home), PATH=str(tools), CLAUDE_CODE_EXECPATH=str(client),
                           CLAUDE_CODE_ENTRYPOINT='claude-desktop', PYTHONDONTWRITEBYTECODE='1')
                script = block.replace('/absolute/path/of/active/sf-demo-scout', str(root))
                for shell in (['/bin/bash'], ['/bin/zsh', '-f']):
                    result = subprocess.run([*shell, '-c', script], env=env, text=True, capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    expected = ('Running Claude client binary: 2.1.296 (CLAUDE_CODE_EXECPATH)\n'
                                if case == 'reported' else unverified)
                    self.assertEqual(result.stdout, expected)
                self.assertFalse((home / 'npm-called').exists())
        done = (ROOT / 'prompts/setup/done.md').read_text()
        self.assertNotIn('CLAUDE_CLI_', done)  # Claude Code updates itself; setup reports the running client only
        self.assertIn('OWNERSHIP_UNVERIFIED', done)
        self.assertIn('Pass every outcome line from steps a and b to the done step unchanged', refresh)


if __name__ == '__main__':
    unittest.main()
