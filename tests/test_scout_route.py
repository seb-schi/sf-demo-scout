"""Static route contracts; native compliance belongs to the architect's trials."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMMAND = ROOT / 'commands/scout.md'


class ScoutRouteTests(unittest.TestCase):
    def setUp(self):
        self.command = COMMAND.read_text()

    def test_budget_and_every_concrete_plugin_reference_exists(self):
        optional = list((ROOT / 'prompts/scout').glob('*'))
        self.assertLessEqual(sum(len(p.read_text().split()) for p in [COMMAND, *optional]), 2000)
        paths = re.findall(r'(?:\$\{CLAUDE_PLUGIN_ROOT\}|\[PLUGIN_ROOT_ABS\])/([^`\s]+)', self.command)
        self.assertGreater(len(paths), 10)
        for relative in paths:
            self.assertTrue((ROOT / relative).exists(), relative)
        self.assertEqual(self.command.count('/CLAUDE.md'), 1)

    def test_never_bullets_remain_qualified_and_byte_identical(self):
        bullets = ['- Delete existing metadata or records',
                   '- Modify existing profiles or permission sets',
                   '- Touch anything prefixed `sb_` or `managed__`']
        for bullet in bullets:
            self.assertIn(bullet, (ROOT / 'CLAUDE.md').read_text())
        self.assertIn('Get explicit SE confirmation before any of these actions:\n' + '\n'.join(bullets), self.command)
        self.assertIn('An explicit SE request naming the item and action counts', self.command)
        self.assertIn('three qualified confirmation bullets above', self.command)

    def test_dispositions_are_defined_and_repair_uncertainty_is_retained(self):
        meanings = {'applied': 'post-write read-back meets the criterion',
                    'already_satisfied': 'Pre-write read-back met the criterion; nothing was written',
                    'failed': 'name remaining state and whether rollback occurred',
                    'blocked': 'Not attempted; name the gate or precondition',
                    'unverified': 'A write happened or may have happened, and no read-back settles it',
                    'omitted': 'docs-confirmed UI-only with citation and manual-checklist entry'}
        for label, meaning in meanings.items():
            rows = re.findall(r'^\| `' + label + r'` \| (.+) \|$', self.command, re.M)
            self.assertEqual(len(rows), 1, label)
            self.assertIn(meaning, rows[0])
        self.assertIn('both `unverified` and `released_unverified` to `unverified`', self.command)
        self.assertIn('Green deploy alone is not read-back', self.command)
        self.assertIn('metadata read-back only', self.command)

    def test_client_notice_worker_mirror_and_allowed_tools(self):
        notice = 'Scout is built for the 5.5 models. Run `/model` to switch.'
        self.assertEqual(self.command.count(notice), 1)
        self.assertEqual(self.command.count('passes `model` set to the alias of the orchestrator'), 1)
        self.assertIn('if that family is unknown, omit the argument', self.command)
        self.assertIn('CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1', self.command)
        self.assertNotRegex(self.command, r'(?i)sonnet|opus|haiku|model\s*=\s*["\']')
        frontmatter = self.command.split('---')[1]
        tools = re.search(r'^allowed-tools: (.+)$', frontmatter, re.M)[1].split(', ')
        self.assertEqual(set(tools), {'Read','Grep','Glob','Write','Edit','Bash','Agent','AskUserQuestion',
            'mcp__salesforce-docs__salesforce_docs_search','mcp__salesforce-docs__salesforce_docs_fetch'})

    def test_unconditional_cli_binding_fresh_evidence_and_folder_identity(self):
        rule = ("Never call Salesforce DX MCP org tools, even when the bound org is the default. "
                "Wherever a file says MCP, the active or default org, `sf config get target-org`, "
                "or to omit `--target-org`, use `sf … --target-org [BOUND_USERNAME]`.")
        self.assertEqual(self.command.count(rule), 2)
        self.assertIn('rule copied verbatim into every worker brief', self.command)
        for phrase in ('Every disposition rests on a read-back you ran yourself, after a passing `check`',
                       'Audits and worker reports are leads, not evidence',
                       'only if its change logs or task records name the bound username or org ID, otherwise ask',
                       'across `orgs/*/` by the bound org ID',
                       'including every checkpoint marker and attempt ID in the task record',
                       'reconcile only the checkpoint markers and attempt IDs recorded in this task',
                       'default-org confirmation names the bound username and org ID'):
            self.assertIn(phrase, self.command)

    def test_target_resume_and_recovery_boundaries(self):
        for forbidden in ('switch-org.md', 'sf config set', 'sf alias set', 'sf org login', '--set-default'):
            self.assertNotIn(forbidden, self.command)
        for instruction in ('Before every write and every read-back supporting a disposition',
                            'stop writing', 'any item with an attempted write is `unverified`, never `blocked`',
                            'never in `audit-*.md`', 'PENDING — component repair',
                            'without resolving, cleaning or relabelling',
                            'Record in-flight writes before dispatch',
                            'check its recorded target first', 'do not replay it',
                            'Read back every delegated write yourself', 'share no component',
                            'WRITER=scout'):
            self.assertIn(instruction, self.command)


if __name__ == '__main__':
    unittest.main()
