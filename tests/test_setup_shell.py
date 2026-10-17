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
        self.assertEqual(count, 41)  # every shipped fence; update when a prompt adds or removes one

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
            'SCOUT_MCP_CACHE_BASH': (['PRE_CACHING_MCP', 'MCP_CACHED'], ['PRE_CACHING_MCP', 'MCP_CACHE_UNAVAILABLE'], 0),
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
                            for tool in ('python3', 'npx'):
                                stub = tools / tool
                                stub.write_text('''#!/bin/bash
printf '%s\n' "$0" >> "$SCOUT_CALLS"
case "$*" in
  *setup-workspace.py*verify*) echo WORKSPACE_VALID ;;
  *setup-workspace.py*setup*) echo WORKSPACE_READY ;;
  *json-pins*) echo PINS_NONE ;;
  *vscode-pins*) echo VSCODE_PINS_NONE ;;
  *aisuite-hooks*) echo AISUITE_HOOKS_NONE ;;
esac
''')
                                stub.chmod(0o700)
                        prelude = ''
                        if mode != 'plain':
                            prelude = 'shopt -s expand_aliases\n' if shell == '/bin/bash' else ''
                            for tool in ('python3', 'npx'):
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

    def test_native_layout_is_proved_without_npm_and_other_paths_stay_unknown(self):
        native_line = 'CLAUDE_CLI_NOT_NPM_OWNED (native install updates itself; Scout left it alone)'
        for case in ('native', 'native-npm', 'direct', 'unknown', 'prefix', 'escape', 'broken', 'sf'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as raw:
                home = Path(raw).resolve(); tools = home / 'bin'; tools.mkdir()
                for name, target in [('python3', sys.executable), ('dirname', '/usr/bin/dirname')]:
                    (tools / name).symlink_to(target)
                cli = 'sf' if case == 'sf' else 'claude'
                directory = home / '.local/share/claude/versions'
                if case == 'unknown': directory = home / 'other'
                if case == 'prefix': directory = home / '.local/share/claude/versions-other'
                directory.mkdir(parents=True)
                binary = directory / '2.1.296'
                binary.write_text('#!/bin/bash\necho "2.1.296 (Claude Code)"\n'); binary.chmod(0o700)
                if case == 'escape':
                    outside = home / 'outside'; binary.rename(outside); binary.symlink_to(outside)
                if case == 'broken': binary.unlink()
                if case == 'direct': binary.rename(directory / cli)
                else: (tools / cli).symlink_to(binary)
                if case == 'native-npm':
                    npm = tools / 'npm'
                    npm.write_text('#!/bin/bash\necho called > "$HOME/npm-called"\nexit 99\n'); npm.chmod(0o700)
                env = dict(HOME=str(home), CLAUDE_CONFIG_DIR=str(home / '.claude'), SCOUT_HOST='claude',
                           PATH=str(directory) + ':' + str(tools) if case == 'direct' else str(tools),
                           CLAUDE_CODE_EXECPATH=str(directory / cli if case == 'direct' else tools / cli),
                           CLAUDE_CODE_ENTRYPOINT='claude-desktop',
                           PYTHONDONTWRITEBYTECODE='1')
                result = subprocess.run(['/bin/bash', str(ROOT / 'scripts/setup-cli-refresh.sh'), cli],
                                        env=env, text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                if case in ('native', 'native-npm', 'direct'):
                    self.assertIn(native_line, result.stdout)
                    self.assertNotIn('OWNERSHIP_UNVERIFIED', result.stdout)
                    self.assertIn('Running Claude client binary: 2.1.296', result.stdout)
                else:
                    self.assertIn(cli.upper() + '_CLI_OWNERSHIP_UNVERIFIED', result.stdout)
                    self.assertNotIn('native install', result.stdout)
                self.assertNotIn('UPDATING_', result.stdout)
                self.assertFalse((home / 'npm-called').exists())
        done = (ROOT / 'prompts/setup/done.md').read_text()
        self.assertIn(native_line, done)
        self.assertIn('Claude Code uses the native install, which updates itself; Scout left it alone.', done)
        self.assertIn('OWNERSHIP_UNVERIFIED', done)
        self.assertIn('Pass every outcome line from steps a and b to the done step unchanged',
                      (ROOT / 'prompts/setup/refresh.md').read_text())


if __name__ == '__main__':
    unittest.main()
