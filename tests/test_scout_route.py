"""Static route contracts; native compliance belongs to the architect's trials."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMMAND = ROOT / 'commands/scout.md'


class ScoutRouteTests(unittest.TestCase):
    def setUp(self):
        self.command = COMMAND.read_text()
        self.discovery = (ROOT / 'prompts/scout/discovery.md').read_text()
        self.history = (ROOT / 'prompts/scout/history.md').read_text()

    def phrases(self, text, *phrases):
        for phrase in phrases:
            self.assertIn(phrase, text)

    def test_budget_and_every_concrete_plugin_reference_exists(self):
        optional = list((ROOT / 'prompts/scout').glob('*'))
        caps = {'scout.md': 2100, 'history.md': 900, 'discovery.md': 1100}
        for path in [COMMAND, *optional]:
            self.assertLessEqual(len(path.read_text().split()), caps[path.name], path.name)
        text = '\n'.join(p.read_text() for p in [COMMAND, *optional])
        paths = re.findall(r'(?:\$\{CLAUDE_PLUGIN_ROOT\}|\[PLUGIN_ROOT_ABS\])/([^`\s]+)', text)
        self.assertGreater(len(paths), 10)
        for relative in paths:
            self.assertTrue((ROOT / relative).exists(), relative)
        self.assertEqual(self.command.count('/CLAUDE.md'), 1)

    def test_every_quoted_section_exists(self):
        count = 0
        for path in [COMMAND, *(ROOT / 'prompts/scout').glob('*.md')]:
            current = None
            for token in re.finditer(r'\$\{CLAUDE_PLUGIN_ROOT\}/([^`\s]+)|§"([^"]+)"', path.read_text()):
                if token[1]:
                    current = ROOT / token[1]
                else:
                    self.assertIsNotNone(current, token[0])
                    source = current.read_text()
                    self.assertRegex(source, r'(?m)^(?:#{1,6} ' + re.escape(token[2]) +
                                     r'|\*\*' + re.escape(token[2]) + r'\*\*)$', str(current))
                    count += 1
        self.assertGreaterEqual(count, 5)

    def test_structured_history_record_checkpoint_and_gate(self):
        history = (ROOT / 'prompts/scout/history.md').read_text()
        for phrase in ('fenced `scout-items` JSON block', '"schema":1', '"depends_on":[]', '"components":[]',
                       '"readback":""', '"grounding":', '"attempts":[]', '"proposed_entries":[]',
                       'new per-task change log before the first checkpoint',
                       '### PENDING — component repair · attempt <ID> · <YYYY-MM-DD HH:MM>',
                       '- **Outcome: <disposition>.** <evidence>', 'Run items in `depends_on` order',
                       'Send the handover only after exit 0', 'fix and recheck up to twice', 'History incomplete:'):
            self.assertIn(phrase, self.command)
        self.assertLess(self.command.index('After the last disposition'), self.command.index('/prompts/scout/history.md'))
        self.assertGreater(self.command.index('/prompts/scout/history.md'), self.command.index('Assign exactly one disposition'))
        for phrase in ('Run `resolve --task [T]`, then `check --task [T]`', 'Verified — Applied This Build',
                       'Verified — Already Satisfied Before This Build', 'AWAITING_QA', 'SKIPPED',
                       'FAILED, BLOCKED, INCOMPLETE (unverified)', 'FINISHED_WITH_EXCEPTIONS',
                       "Each settled attempt's heading comes from its own", 'Missing/conflicting outcomes stay PENDING'):
            self.assertIn(phrase, history)

    def test_history_map_ownership_precedence_and_reoffer(self):
        history = (ROOT / 'prompts/scout/history.md').read_text()
        for phrase in ('Create a map only when this task established a story', 'audience and moment',
                       'map unchanged', 'one line at most 320 characters',
                       'Every SE-authored/non-template section stays byte-identical, in place',
                       'overrides deleting legacy banners', 'per-task log rule overrides',
                       "outcome heading rule overrides that file's heading rule",
                       "second author despite", 'No answer means write nothing',
                       '`pending` to re-offer next run', 'On skip, write the arc and stamps without new entries',
                       'rerun `check`, then send one truthful receipt line'):
            self.assertIn(phrase, history)
        self.assertIn('`demo-architecture.md` first', self.command)
        self.assertIn('reconcile-plan --folder', self.command)
        self.assertIn('read every `unclear` checkpoint', self.command)

    def test_k1_spine_beats_proof_challenge_and_merged_confirmation(self):
        self.phrases(self.discovery, 'at most two discovery rounds', 'Draft, not a questionnaire',
                     'name, persona, stated pain and climax', 'where KP3 contrasts visibly with KP1',
                     'record or list opened', 'never invent a KP2 metric or pain',
                     '`Proves: KP[n]` or `Supports: I[n]`', "X doesn't prove KP1–3 — keep or cut?",
                     'Record a kept exception', '`[REJECTED]` decision for a cut',
                     'Merge the spine and proposal into one message', '“Just build it” still gets proposed defaults',
                     'proof moment is required before the first write', '`se-stated` or `se-confirmed`',
                     '“Go” accepts that proposal, not an unstated moment')

    def test_k2_demo_day_data_and_claim_acceptance(self):
        self.phrases(self.command, 'Before seeding, describe every object', 'required fields, picklists, record-type DeveloperNames',
                     '§"Procedure per object"', 'Capture `errorCode` on failure', 'dates relative to seed day',
                     'state the validity window', 'at-risk/stale/overdue records',
                     'Dress each hero record with contacts and relative-dated activities',
                     'Stage live flips in before-state with a reset', 'idempotent, re-runnable script that never deletes',
                     '`--pilot-only` against the bound org', 'Every on-screen claim is an acceptance criterion',
                     'exact `readback` query: verify it yourself, including the proof moment',
                     'Drop unbacked claims from Demo Story', 'missed post-write claim is `failed`')
        self.phrases(self.history, 'seed pilot, refresh and reset commands', 'How to Verify and Script Deliverables')

    def test_k3_baseline_cartridge_and_preflight(self):
        self.phrases(self.discovery, 'installed managed namespaces and industry cloud',
                     'apps/objects matching the domain nouns', 'Account record types and folder history',
                     'Step 1 — Discover enabled, selected cartridges (cheap; always runs)',
                     "Step 2 — Match the audited industry against each cartridge's Coverage",
                     'Step 3 — Consult the matched cartridge (proactive, read-only)',
                     'Announce the consult in one line', '`skill` grounding in the task and proposal',
                     "hub worker follows the command's model-mirroring rule")
        self.phrases(self.command, 'full audit runs only on request', 'Step 0 — Object Capability Pre-Flight',
                     'Step 0b — Docs Follow-Up for Restricted Objects')

    def test_k4_delta_conflict_and_conditional_demo_moment(self):
        self.phrases(self.discovery, 'Delta Conflict Check', 'Agent source evidence gate',
                     'flows sharing an object, field-name collisions, layout crowding, permission overlaps',
                     'weak foundation', 'revived `[REJECTED]` decisions',
                     'only when adding a demo-facing capability and neither request nor map names its moment',
                     'Ask inside confirmation; pure repairs skip it',
                     'keeps the item without a moment, build it and propose a decision entry',
                     'exact error text and when it fires')
        self.phrases(self.command, 'In folders with history', '§"Delta Conflict Check"', '§"Symptom Follow-up (fix intent only)"')

    def test_k5_demo_story_follows_outcome_with_verified_claims(self):
        self.phrases(self.discovery, 'After the outcome sections', '§"Demo Story"',
                     'persona, click path, record, KP, verified claims and climax',
                     'mark the proof moment', 'Label unfulfilled beats planned/unverified',
                     "map's Narrative Arc")
        self.phrases(self.command, 'Send one outcome-first message',
                     'Then the Demo Story (bounded: one line naming the beat served) and history block')

    def test_k6_lessons_require_yes_and_skip_extra_offers(self):
        self.phrases(self.history, 'propose 1–3 lessons', 'yes, edit or skip', 'Write only on yes or edit',
                     '§"Propose Lessons (building)"', '§"Append Format"', '§"Routing — which topic file"',
                     '§"Per-Topic Review (replaces the old global 25-line trim)"',
                     'Step 1: Ensure the lessons directory + INDEX exist (idempotent)',
                     'Skip Slack Upstream and Legacy Drain offers')
        self.assertNotIn('Afterward, if a repeatable trap occurred, append', self.command)

    def test_k7_docs_floor_both_halves_fetch_errors_and_degraded_mode(self):
        self.phrases(self.command, 'Every item records grounding', 'Gated/Docs-gated types',
                     'flows, Apex, LWC, Agentforce, Email-to-Case, dashboards and unknown types',
                     'Claim mechanisms require Docs unless plain field values',
                     '§"When to Consult — YES"', '§"When to Consult — NO"', '§"How to Cite"', '§"Degraded Mode"',
                     "Fetch before deciding; snippets aren't evidence", 'Before proposals: industry model',
                     'While building: consult Docs before first writes', 'new metadata types and ungrounded assumptions',
                     'Agentforce always', 'search the verbatim error before retry or `failed`',
                     'Workers return grounding; fetch disposition-deciding pages yourself',
                     'if unavailable, say so in this first SE-facing message',
                     'ask once on open-ended work whether to proceed ungrounded',
                     'record `Docs unavailable` entries and handover risks, never fake URLs')
        self.phrases(self.discovery, "release-gated features against this org's release",
                     'Name every Docs finding that changed the design')
        self.phrases(self.history, 'every Docs URL/question/verdict, grouped by item')

    def test_k8_presales_lens_and_corrected_label_scope(self):
        self.phrases(self.discovery, 'Apply what a top SE would; at minimum', 'building the end state',
                     'person who must say yes', 'Every beat answers a stated pain and names a persona',
                     'vision demo emphasizes breadth and story', 'proof demo uses their scenario and language',
                     'at least one live flip', 'working session favors fewer, deeper beats',
                     'one beat per three to four minutes, 2–6 total', 'leaving room for questions',
                     'Ask slot length or demo type only if it changes beat count', 'Say only what verified data shows',
                     'automate the hand-off into it', 'object, tab and field labels as org-wide',
                     'surface and its scope grounded in Docs', "wider relabel needs the SE's explicit yes",
                     'Use their named stages', "audience's existing app", 'ground that limitation in Docs',
                     'Record the app choice as a decision', 'customer appetite and trusted data', 'human-in-the-loop')
        for path in [COMMAND, *(ROOT / 'prompts/scout').glob('*.md')]:
            self.assertNotRegex(path.read_text(), r'(?i)tab label[^.\n]*(?:app-local|for (?:one|that) app only)')

    def test_k9_structured_inputs_and_fragment_read_order(self):
        self.phrases(self.command, 'Treat a supplied demo plan, requirements or discovery notes as the brief',
                     'beats, personas, cuts, hero records and on-screen claims become items, criteria and story fields',
                     'inputs are leads, not evidence; confirmation still applies', 'Write no spec',
                     'Before the first SE-facing question', 'on open-ended work',
                     'when adding a demo-facing capability to a folder with history',
                     'Neither discovery.md nor history.md loads before the first message on a complete brief')
        self.assertGreater(self.command.index('/prompts/scout/history.md'), self.command.index('After the last disposition'))
        self.phrases(self.discovery, 'Read the referenced sections only as needed',
                     'not their stage numbers, questionnaires, acknowledgement stops, audit modes, spec writes or model choices')

    def test_complete_brief_startup_budget_and_report_checkpoint_adapter(self):
        startup = [COMMAND, ROOT / 'prompts/host-runtime.md', ROOT / 'prompts/workspace-bootstrap.md']
        self.assertLessEqual(sum(len(p.read_text().split()) for p in startup), 3000)
        self.phrases(self.command, 'log explicitly as `--change-log`',
                     'marked receipt block fenced and its evidence unchanged')

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
