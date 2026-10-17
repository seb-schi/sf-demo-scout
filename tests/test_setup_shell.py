"""Execute shipped setup fences against disposable homes and fake tools."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def fences():
    for folder in ('commands', 'prompts'):
        for path in sorted((ROOT / folder).rglob('*.md')):
            for block in re.findall(r'^[ \t]*```bash\n(.*?)^[ \t]*```[ \t]*$', path.read_text(), re.S | re.M):
                block = block.rstrip('\n')
                wrapped = re.fullmatch(r"/bin/bash <<'([A-Z0-9_]+)'\n(.*?)\n\1", block, re.S)
                yield path, wrapped[1] if wrapped else None, wrapped[2] if wrapped else block


class SetupShellTests(unittest.TestCase):
    def test_no_bash_only_lookup_in_markdown_and_every_fence_parses_in_zsh(self):
        count = 0
        for folder in ('commands', 'prompts'):
            for path in (ROOT / folder).rglob('*.md'):
                self.assertNotIn('type -P', path.read_text(), str(path))
        for path, marker, body in fences():
            with self.subTest(path=path, marker=marker):
                # Bind literal documentation operands; never execute these org examples.
                source = re.sub(r'<(?:ORG_ALIAS|FlowName|ClassName)>', 'fixture', body)
                result = subprocess.run(['/bin/zsh', '-f', '-n'], input=source, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                count += 1
        self.assertEqual(count, 40)  # every shipped fence; update when a prompt adds or removes one

    def test_setup_command_has_one_whole_fence_rule(self):
        command = (ROOT / 'commands/scout-setup.md').read_text()
        self.assertEqual(command.count('Run each bash fence'), 1)
        for phrase in ('every setup prompt it dispatches', 'in its own Bash call',
                       'exactly as written once placeholders are substituted',
                       "Keep any `/bin/bash <<'…'` wrapper", "don't merge fences or retype their bodies",
                       'because the tool shell may be zsh'):
            self.assertIn(phrase, command)

    def test_seven_inner_bodies_match_in_bash_and_zsh_with_masked_or_missing_tools(self):
        cases = {
            'SCOUT_SETUP_STATE_BASH': (['WORKSPACE_VALID', 'STATE=REFRESH'], ['STATE=FRESH'], 0),
            'SCOUT_WORKSPACE_BOOTSTRAP_BASH': (['WORKSPACE_VALID', 'STATE=OK'], ['STATE=CHECK_FAILED'], 1),
            'SCOUT_JSON_PINS_BASH': (['PINS_NONE'] * 2, ['SETTINGS_HELPER_UNAVAILABLE'], 0),
            'SCOUT_VSCODE_PINS_BASH': (['VSCODE_PINS_NONE'], ['SETTINGS_HELPER_UNAVAILABLE'], 0),
            'SCOUT_AISUITE_SCRUB_BASH': (['AISUITE_HOOKS_NONE'] * 2, ['SETTINGS_HELPER_UNAVAILABLE'], 0),
            'SCOUT_RETIRED_ALLOW_BASH': (['RETIRED_ALLOW_NONE'] * 2, ['SETTINGS_HELPER_UNAVAILABLE'], 0),
            'SCOUT_WORKSPACE_SETUP_BASH': (['WORKSPACE_READY'], ['WORKSPACE_SETUP_FAILED'], 1),
        }
        blocks = {marker: body for _, marker, body in fences() if marker}
        self.assertEqual(set(blocks), set(cases))
        for marker, body in blocks.items():
            for mode in ('plain', 'masked', 'relative', 'missing'):
                observed = []
                for shell in ('/bin/bash', '/bin/zsh'):
                    with self.subTest(marker=marker, mode=mode, shell=shell), tempfile.TemporaryDirectory() as raw:
                        home = Path(raw).resolve()
                        workspace = home / 'claude-projects/sf-demo-scout'
                        tools = workspace / 'tools with spaces'; tools.mkdir(parents=True)
                        (tools / 'mkdir').symlink_to('/bin/mkdir')
                        plugin = home / 'plugin source'; (plugin / 'scripts').mkdir(parents=True)
                        for helper in ('setup-workspace.py', 'setup-settings.py'):
                            (plugin / 'scripts' / helper).touch()
                        calls = home / 'calls'
                        if mode != 'missing':
                            for tool in ('python3',):
                                stub = tools / tool
                                stub.write_text('''#!/bin/bash
printf '%s\n' "$0" >> "$SCOUT_CALLS"
case "$*" in
  *setup-workspace.py*verify*) echo WORKSPACE_VALID ;;
  *setup-workspace.py*setup*) echo WORKSPACE_READY ;;
  *json-pins*) echo PINS_NONE ;;
  *vscode-pins*) echo VSCODE_PINS_NONE ;;
  *aisuite-hooks*) echo AISUITE_HOOKS_NONE ;;
  *retired-allow*) echo RETIRED_ALLOW_NONE ;;
esac
''')
                                stub.chmod(0o700)
                        prelude = ''
                        if mode != 'plain':
                            prelude = 'shopt -s expand_aliases\n' if shell == '/bin/bash' else ''
                            for tool in ('python3',):
                                prelude += f"function {tool}() {{ echo WRONG_FUNCTION; }}\nalias {tool}='echo WRONG_ALIAS'\n"
                        script = body.replace('[PLUGIN_ROOT]', str(plugin)).replace('[SCOUT_HOST]', 'claude').replace('[PLUGIN_VERSION]', 'fixture')
                        env = dict(HOME=str(home), CLAUDE_CONFIG_DIR=str(home / '.claude'),
                                   PATH=tools.name if mode == 'relative' else str(tools), SCOUT_CALLS=str(calls))
                        result = subprocess.run([shell, '-f'], input=prelude + script, cwd=workspace,
                                                env=env, text=True, capture_output=True, timeout=10)
                        tokens = [line.split(' ', 1)[0] for line in result.stdout.splitlines()]
                        self.assertEqual(tokens, cases[marker][1 if mode == 'missing' else 0], result.stderr)
                        self.assertEqual(result.returncode, cases[marker][2] if mode == 'missing' else 0, result.stderr)
                        self.assertEqual(calls.exists(), mode != 'missing')
                        if calls.exists():
                            self.assertTrue(all(Path(line).is_absolute() for line in calls.read_text().splitlines()))
                        observed.append((result.returncode, tokens))
                self.assertEqual(observed[0], observed[1])

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
