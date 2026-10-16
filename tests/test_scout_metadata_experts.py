"""metadata-experts helper tested through a fake CLI and a fake official proxy, never an org or a network."""
import contextlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import scout_metadata_experts as experts

HELPER = Path(__file__).resolve().parents[1] / 'scripts/scout_metadata_experts.py'
ORG = '00D000000000001EAA'
USER = 'maple@example.test'
SECRET = 'SYNTHETIC-SECRET-DO-NOT-PRINT'
JWT = 'eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJzeW50aGV0aWMifQ.c2lnbmF0dXJl'
RECORD = '1fz000000000001AAA'
NEW = '1fz000000000002AAA'
BINDING = ('--host', 'claude', '--selector', 'maple', '--username', USER, '--org-id', ORG)
FLOW = ('<?xml version="1.0"?><Flow xmlns="http://soap.sforce.com/2006/04/metadata"><apiVersion>65</apiVersion>'
        '<label>Negotiation Follow-up</label><processMetadataValues><name>CanvasMode</name></processMetadataValues>'
        '<processType>AutoLaunchedFlow</processType><description>Q&amp;A follow-up</description><start>'
        '<filters><field>StageName</field><operator>EqualTo</operator><value><stringValue>Negotiation</stringValue>'
        '</value></filters><object>Opportunity</object>'
        '<recordTriggerType>Update</recordTriggerType><triggerType>RecordAfterSave</triggerType>'
        '<doesRequireRecordChangedToMeetCriteria>false</doesRequireRecordChangedToMeetCriteria></start>'
        '<status>Draft</status></Flow>')

FAKE_SF = r'''
import json, os, sys
from pathlib import Path
path = Path(os.environ['MX_STATE'])
state = json.loads(path.read_text())
args = sys.argv[1:]
with open(os.environ['MX_CALLS'], 'a') as f:
    f.write(json.dumps({'sf': args, 'cwd': os.getcwd()}) + '\n')
print('SYNTHETIC-SECRET-DO-NOT-PRINT', file=sys.stderr)
def reply(result, status=0, code=0):
    result = dict(result, accessToken='SYNTHETIC-SECRET-DO-NOT-PRINT') if isinstance(result, dict) else result
    print(json.dumps({'status': status, 'result': result})); sys.exit(code)
if args[:2] == ['org', 'display']:
    if args[args.index('--target-org') + 1] in state.get('broken', []):
        sys.exit(1)
    reply({'id': state['org'], 'username': state['username']})
if args[:3] == ['config', 'get', 'target-org']:
    reply([{'name': 'target-org', 'key': 'target-org', 'value': state.get('default'), 'success': True}])
assert args[args.index('--target-org') + 1] == state['username'], args
if args[:2] == ['data', 'query'] and '--use-tooling-api' not in args:
    reply({'records': [{'Id': state['org']}]})
if args[:2] == ['data', 'query']:
    if state.get('lookup') == 'error' or (state.get('lookup_after_write') == 'error' and state.get('written')):
        print('SYNTHETIC-SECRET-DO-NOT-PRINT'); sys.exit(1)
    reply({'records': state.get('rows', [])})
if args[:3] in (['data', 'create', 'record'], ['data', 'update', 'record']):
    mode = state.get('write', 'ok')
    if mode in ('ok', 'lost-landed'):
        row = {'Id': state.get('new_id', 'NEW'), 'DeveloperName': 'platform_metadata_experts', 'Active': True}
        if args[1] == 'update':
            row['Id'] = args[args.index('--record-id') + 1]
        state['rows'] = [row]
    state['written'] = True
    path.write_text(json.dumps(state))
    if mode == 'ok':
        reply({'id': state['rows'][0]['Id'], 'success': True, 'errors': []})
    print('SYNTHETIC-SECRET-DO-NOT-PRINT'); sys.exit(1)
sys.exit(9)
'''

FAKE_NODE = r'''
import json, os, subprocess, sys, time
state = json.loads(open(os.environ['MX_STATE']).read())
probes = os.environ['MX_STATE'] + '.probes'
starts = int(open(probes).read()) + 1 if os.path.exists(probes) else 1
open(probes, 'w').write(str(starts))
child = subprocess.Popen(['sleep', '60']) if state.get('child') else None
with open(os.environ['MX_CALLS'], 'a') as f:
    f.write(json.dumps({'proxy': sys.argv[1:], 'cwd': os.getcwd(), 'target': os.environ.get('SF_TARGET_ORG'),
                        'pid': os.getpid(), 'child': child.pid if child else None,
                        'log': [os.environ.get(k) for k in ('SF_LOG_LEVEL', 'SF_DISABLE_LOG_FILE')],
                        'sfdx_target': os.environ.get('SFDX_TARGET_ORG'),
                        'config': open('.sf/config.json').read()}) + '\n')
print('SYNTHETIC-SECRET-DO-NOT-PRINT ' + state['jwt'], file=sys.stderr, flush=True)
os.makedirs('.sf/mcp-health', exist_ok=True)
open('.sf/mcp-health/metadata-experts.json', 'w').write(json.dumps({'detail': state['jwt']}))
if state.get('lock_sidecars'):
    os.chmod('.sf', 0o555)
mode, pipe = state.get('proxy', 'ready'), state.get('pipeline', {})
if mode == 'inactive-then-ready':
    mode = 'inactive' if starts <= state.get('inactive_probes', 1) else 'ready'
generation = [0]
def send(message):
    if state.get('noise'):
        print('proxy log line ' + state['jwt'], flush=True)
        print(json.dumps({'jsonrpc': '2.0', 'method': 'notifications/message', 'params': {'jwt': state['jwt']}}), flush=True)
        if 'id' in message:
            print(json.dumps({'jsonrpc': '2.0', 'id': message['id'] + 1000, 'result': {'late': True}}), flush=True)
    print(json.dumps(message), flush=True)
def envelope(values, success=True):
    inner = json.dumps({'success': success, 'errors': [] if success else ['x'], 'outputValues': values})
    return {'content': [{'type': 'text', 'text': json.dumps({'defaultExc': inner, 'responseCode': 200})}], 'isError': False}
for line in sys.stdin:
    message = json.loads(line)
    if 'id' not in message:
        continue
    ident, method = message['id'], message['method']
    if mode == 'stall':
        time.sleep(60)
    if mode == 'trickle':
        while True:
            print(json.dumps({'jsonrpc': '2.0', 'method': 'notifications/progress'}), flush=True); time.sleep(0.1)
    if mode == 'inactive':
        send({'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32603, 'message':
              'Server not activated in this org — activate it in Salesforce Setup, then retry'}}); continue
    if method == 'initialize':
        send({'jsonrpc': '2.0', 'id': ident, 'result': {'serverInfo': {'name': 'metadata-experts'}}}); continue
    if method == 'tools/list':
        tools = [] if mode == 'no-tool' else [{'name': 'execute_metadata_action'}]
        send({'jsonrpc': '2.0', 'id': ident, 'result': {'tools': tools}}); continue
    action = message['params']['arguments']['actionName']
    if pipe.get('flaky', 0) > 0:
        pipe['flaky'] -= 1
        send({'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32603, 'message': 'upstream ' + state['jwt']}}); continue
    step = {'fetchGroundedObjectMetadata': 'grounding', 'flowElementSelection': 'selection'}.get(action, 'generation')
    if pipe.get('fail') == step:
        kind = pipe.get('kind', 'success-false')
        if kind == 'rpc-error':
            send({'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32000, 'message': state['jwt']}}); continue
        if kind == 'isError':
            send({'jsonrpc': '2.0', 'id': ident, 'result': dict(envelope({}), isError=True)}); continue
        send({'jsonrpc': '2.0', 'id': ident, 'result': envelope({'detail': state['jwt']}, success=False)}); continue
    if step == 'grounding':
        send({'jsonrpc': '2.0', 'id': ident, 'result': envelope({'groundingMetadata': '{"objects":[]}'})}); continue
    if step == 'selection':
        send({'jsonrpc': '2.0', 'id': ident, 'result': envelope({'operationId': 'op-1'})}); continue
    generation[0] += 1
    if generation[0] <= pipe.get('incomplete', 0) or pipe.get('complete') == 'never':
        send({'jsonrpc': '2.0', 'id': ident, 'result': envelope({'isComplete': False})}); continue
    complete = pipe.get('complete', 'xml')
    values = {'isComplete': 'true' if complete == 'string' else True, 'result': '' if complete == 'empty' else state['xml']}
    send({'jsonrpc': '2.0', 'id': ident, 'result': envelope(values)})
'''


class MetadataExpertsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='scout-mx-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for name, body in (('sf', FAKE_SF), ('node', FAKE_NODE)):
            binary = self.bin / name
            binary.write_text('#!' + sys.executable + '\n' + body)
            binary.chmod(0o700)
        (self.bin / 'sleep').symlink_to('/bin/sleep')
        self.plugin = self.root / 'official'
        (self.plugin / 'scripts').mkdir(parents=True)
        (self.plugin / 'scripts/sf-mcp-proxy.bundled.js').write_text('// stand-in; the fake node ignores it\n')
        self.config = self.root / 'claude'
        (self.config / 'plugins').mkdir(parents=True)
        self.install()
        self.state, self.calls = self.root / 'state.json', self.root / 'calls.jsonl'
        self.project = self.root / 'workspace'
        self.project.mkdir()
        self.env = dict(HOME=str(self.root), PATH=str(self.bin), MX_STATE=str(self.state), MX_CALLS=str(self.calls),
                        CLAUDE_CONFIG_DIR=str(self.config), SCOUT_CACHE_DIR=str(self.root / 'cache'),
                        CLAUDE_PROJECT_DIR=str(self.project), PYTHONDONTWRITEBYTECODE='1')
        patcher = patch.dict(os.environ, self.env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name, value in (('PROBE_SECONDS', 5), ('CALL_SECONDS', 5), ('CANDIDATE_SECONDS', 10),
                            ('WAIT_SECONDS', 1), ('POLL_SECONDS', 0.2), ('GRACE_SECONDS', 0.5)):
            patcher = patch.object(experts, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.configure()

    def install(self, records=None):
        """The official plugin as setup leaves it: Salesforce's GitHub marketplace, installed and switched on."""
        records = [{'scope': 'user', 'installPath': str(self.plugin), 'version': '2.4.0'}] if records is None else records
        registry = {'version': 2, 'plugins': {'salesforce-development@salesforce': records} if records else {}}
        (self.config / 'plugins/installed_plugins.json').write_text(json.dumps(registry))
        (self.config / 'plugins/known_marketplaces.json').write_text(json.dumps(
            {'salesforce': {'source': {'source': 'git', 'url': 'https://github.com/forcedotcom/sf-skills.git'}}}))
        (self.config / 'settings.json').write_text(json.dumps({'enabledPlugins': {'salesforce-development@salesforce': True}}))

    def configure(self, **kwargs):
        self.state.write_text(json.dumps(dict(dict(org=ORG, username=USER, jwt=JWT, xml=FLOW, new_id=NEW), **kwargs)))
        Path(str(self.state) + '.probes').unlink(missing_ok=True)

    def run_helper(self, *args):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            try:
                code = experts.main(list(args))
            except SystemExit as exc:
                code = exc.code
        for stream in (output.getvalue(), error.getvalue()):
            for secret in (SECRET, JWT, 'accessToken', 'Traceback'):
                self.assertNotIn(secret, stream)
        return code, json.loads(output.getvalue()) if output.getvalue() else {}

    def log(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def sf_calls(self):
        return [row['sf'] for row in self.log() if 'sf' in row]

    def proxy_calls(self):
        return [row for row in self.log() if 'proxy' in row]

    def row(self, active):
        return {'Id': RECORD, 'DeveloperName': 'platform_metadata_experts', 'Active': active}

    def assert_reaped(self):
        for row in self.proxy_calls():
            for pid in (row['pid'], row['child']):
                if pid:
                    with self.assertRaises(ProcessLookupError):
                        os.kill(pid, 0)

    def assert_no_sidecars(self):
        self.assertEqual(list((self.root / 'cache').rglob('mcp-health')), [])

    def test_status_reports_the_record_contract(self):
        for rows, state, active, code in (([], 'absent', None, 2), ([self.row(False)], 'present', False, 0),
                                          ([self.row(True)], 'present', True, 0)):
            with self.subTest(rows=rows):
                self.configure(rows=rows)
                code_, data = self.run_helper('status', *BINDING)
                self.assertEqual((code_, data['state'], data['record'].get('active')), (code, state, active))
                if rows:
                    self.assertEqual((data['record']['id'], data['record']['developer_name']), (RECORD, 'platform_metadata_experts'))
        for case in (dict(lookup='error'), dict(rows=[self.row(True), self.row(True)]),
                     dict(rows=[{'Id': 'bad', 'DeveloperName': 'platform_metadata_experts', 'Active': True}]),
                     dict(rows=[dict(self.row(True), Active='true')])):
            with self.subTest(case=case):
                self.configure(**case)
                code, data = self.run_helper('status', *BINDING)
                self.assertEqual((code, data['state']), (4, 'unknown'))
        for args in self.sf_calls():
            if args[:2] != ['org', 'display']:
                self.assertEqual(args[args.index('--target-org') + 1], USER)

    def test_probe_readiness_pins_the_proxy_and_cleans_up(self):
        self.configure(rows=[self.row(True)], noise=True, child=True)
        code, data = self.run_helper('status', *BINDING, '--probe')
        self.assertEqual((code, data['state'], data['record']['active']), (0, 'ready', True))
        proxy = self.proxy_calls()[-1]
        self.assertEqual(proxy['proxy'], [str(self.plugin / 'scripts/sf-mcp-proxy.bundled.js'), 'metadata-experts'])
        self.assertEqual((proxy['target'], proxy['sfdx_target'], proxy['log']), (USER, USER, ['fatal', 'true']))
        self.assertEqual(Path(proxy['cwd']), self.root / 'cache/metadata-experts' / ORG)
        self.assertEqual(json.loads(proxy['config']), {'target-org': USER})
        self.assertFalse((self.project / '.sf').exists())
        self.assertEqual((data['official']['root'], data['official']['version'], len(data['official']['proxy_sha256'])),
                         (str(self.plugin), '2.4.0', 64))
        self.assert_reaped()
        self.assert_no_sidecars()

    def test_probe_states(self):
        for rows, proxy, state, code in (([], 'ready', 'activation-needed', 2), ([self.row(False)], 'ready', 'activation-needed', 2),
                                         ([self.row(True)], 'inactive', 'inactive', 2),
                                         ([self.row(True)], 'no-tool', 'unavailable', 4),
                                         ([self.row(True)], 'stall', 'unavailable', 4)):
            with self.subTest(proxy=proxy, rows=rows):
                self.configure(rows=rows, proxy=proxy, child=True)
                with patch.object(experts, 'PROBE_SECONDS', 1):
                    code_, data = self.run_helper('status', *BINDING, '--probe')
                self.assertEqual((code_, data['state']), (code, state))
                if proxy == 'no-tool':
                    self.assertEqual(data['reason'], experts.NO_TOOL)
        self.assert_reaped()

    def test_local_capability_comes_before_any_org_call(self):
        self.configure(rows=[])
        (self.bin / 'node').rename(self.bin / 'node-away')
        for args in (('status', *BINDING, '--probe'), ('activate', *BINDING, '--confirmed'),
                     ('flow', *BINDING, '--prompt-file', str(self.write_prompt()), '--out-dir', str(self.root / 'o'),
                      '--candidate', '1')):
            code, data = self.run_helper(*args)
            self.assertEqual((code, data['state'], data['reason']), (5, 'no-official-plugin', 'node unavailable'))
        (self.bin / 'node-away').rename(self.bin / 'node')
        self.install(records=[])
        code, data = self.run_helper('status', *BINDING, '--probe')
        self.assertEqual((code, data['reason']), (5, experts.NO_PLUGIN))
        self.assertEqual(self.log(), [])

    def test_registry_uses_only_the_user_scope_and_absolute_explicit_roots(self):
        self.configure(rows=[self.row(True)])
        self.install(records=[{'scope': 'project', 'projectPath': '/other-project', 'installPath': str(self.plugin)}])
        self.assertEqual(self.run_helper('status', *BINDING, '--probe')[1]['state'], 'no-official-plugin')
        codex = ('--host', 'codex') + BINDING[2:]
        self.install()
        self.assertEqual(self.run_helper('status', *codex, '--probe')[1]['state'], 'no-official-plugin')
        previous = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        code, data = self.run_helper('status', *codex, '--official-root', 'official', '--probe')
        self.assertEqual((code, data['state'], data['official']['root']), (0, 'ready', str(self.plugin)))
        with patch.dict(os.environ, {'SCOUT_OFFICIAL_PLUGIN_ROOT': str(self.plugin)}):
            self.assertEqual(self.run_helper('status', *codex, '--probe')[1]['official']['root'], str(self.plugin))
        (self.config / 'plugins/installed_plugins.json').unlink()
        self.assertEqual(self.run_helper('status', *BINDING, '--probe')[1]['state'], 'no-official-plugin')

    def test_activation_needs_confirmation_before_any_call(self):
        code, data = self.run_helper('activate', *BINDING)
        self.assertEqual((code, data['state']), (6, 'refused'))
        self.assertEqual(self.log(), [])

    def test_activation_create_update_noop_with_full_evidence(self):
        self.configure(rows=[])
        code, data = self.run_helper('activate', *BINDING, '--confirmed')
        self.assertEqual((code, data['state'], data['action'], data['after']['id'], data['readiness']),
                         (0, 'active', 'create', NEW, 'ready'))
        self.assertEqual((data['before'], data['mutation']), ({'state': 'absent'}, 'ok'))
        create = [c for c in self.sf_calls() if c[:3] == ['data', 'create', 'record']][0]
        self.assertEqual(create[create.index('--values') + 1],
                         'DeveloperName=platform_metadata_experts MasterLabel=metadata-experts Active=true')
        self.assertIn('--use-tooling-api', create)
        self.configure(rows=[self.row(False)])
        code, data = self.run_helper('activate', *BINDING, '--confirmed')
        self.assertEqual((code, data['state'], data['action'], data['before']['active'], data['after']['active']),
                         (0, 'active', 'update', False, True))
        self.configure(rows=[self.row(True)])
        calls = len(self.sf_calls())
        self.assertEqual(self.run_helper('activate', *BINDING, '--confirmed')[1]['action'], 'none')
        self.assertFalse(any(c[:2] == ['data', 'update'] for c in self.sf_calls()[calls:]))

    def test_uncertain_activation_writes_stay_unverified(self):
        for case, state in ((dict(rows=[], write='lost-landed'), 'active'), (dict(rows=[], write='lost'), 'unverified'),
                            (dict(rows=[self.row(False)], lookup_after_write='error'), 'unverified')):
            with self.subTest(case=case):
                self.configure(**case)
                code, data = self.run_helper('activate', *BINDING, '--confirmed')
                self.assertEqual((data['state'], code), (state, 0 if state == 'active' else 4))
                self.assertIn('before', data)
                if case['rows']:
                    self.assertEqual(data['before']['id'], RECORD)

    def test_activation_wait_polls_until_ready_within_its_budget(self):
        self.configure(rows=[self.row(False)], proxy='inactive-then-ready', inactive_probes=2)
        with patch.object(experts, 'WAIT_SECONDS', 6), patch.object(experts, 'PROBE_SECONDS', 1):
            started = time.monotonic()
            code, data = self.run_helper('activate', *BINDING, '--confirmed')
            elapsed = time.monotonic() - started
        self.assertEqual((code, data['state'], data['readiness']), (0, 'active', 'ready'))
        self.assertEqual(len(self.proxy_calls()), 3)
        self.assertLess(elapsed, 6 + 1)
        self.configure(rows=[self.row(False)], proxy='inactive')
        with patch.object(experts, 'WAIT_SECONDS', 2), patch.object(experts, 'PROBE_SECONDS', 1):
            started = time.monotonic()
            code, data = self.run_helper('activate', *BINDING, '--confirmed')
            self.assertLess(time.monotonic() - started, 2 + 1)
        self.assertEqual((code, data['state'], data['readiness']), (0, 'active', 'inactive'))

    def write_prompt(self):
        prompt = self.root / 'prompt.txt'
        prompt.write_text('When an Opportunity moves into Negotiation, create a follow-up Task.')
        return prompt

    def generate(self, candidate='1', out='out'):
        return self.run_helper('flow', *BINDING, '--prompt-file', str(self.write_prompt()),
                               '--out-dir', str(self.root / out), '--candidate', candidate)

    def test_flow_generation_publishes_xml_and_a_receipt_together(self):
        self.configure(pipeline={'incomplete': 2}, noise=True, child=True)
        code, data = self.generate()
        self.assertEqual((code, data['state']), (0, 'complete'))
        self.assertEqual(Path(data['xml']).read_text(), FLOW)
        receipt_file = self.root / 'out/candidate-1.receipt.json'
        receipt = json.loads(receipt_file.read_text())
        self.assertEqual(receipt['client_rpc_calls'], {'grounding': 1, 'selection': 1, 'generation': 3, 'total': 7})
        self.assertEqual((receipt['outcome']['state'], receipt['official']['version'], receipt['sidecars_left']),
                         ('complete', '2.4.0', False))
        self.assertNotIn(JWT, receipt_file.read_text())
        self.assertEqual(sorted(p.name for p in (self.root / 'out').iterdir()),
                         ['candidate-1.flow-meta.xml', 'candidate-1.receipt.json'])
        self.assert_reaped()
        self.assert_no_sidecars()

    def test_one_server_error_is_retried_once(self):
        self.configure(pipeline={'flaky': 1})
        with patch.object(experts, 'POLL_SECONDS', 0.1):
            code, data = self.generate()
        receipt = json.loads((self.root / 'out/candidate-1.receipt.json').read_text())
        self.assertEqual((code, data['state'], receipt['retried'], receipt['client_rpc_calls']['grounding']),
                         (0, 'complete', 'fetchGroundedObjectMetadata', 2))
        self.configure(pipeline={'flaky': 2})
        with patch.object(experts, 'POLL_SECONDS', 0.1):
            code, data = self.generate(out='out-2')
        self.assertEqual((code, data['state'], data['code']), (4, 'unavailable', -32603))

    def test_flow_failures_at_every_layer_publish_no_xml(self):
        cases = [dict(pipeline={'fail': step, 'kind': kind}) for step in ('grounding', 'selection', 'generation')
                 for kind in ('success-false', 'isError', 'rpc-error')]
        cases += [dict(pipeline={'complete': 'string'}), dict(pipeline={'complete': 'empty'}),
                  dict(xml='<NotAFlow/>'), dict(xml='<Flow'), dict(proxy='inactive')]
        for index, case in enumerate(cases):
            with self.subTest(case=case):
                self.configure(**case)
                code, data = self.generate(out='out-%d' % index)
                self.assertIn(data['state'], ('unavailable', 'inactive'))
                self.assertNotEqual(code, 0)
                folder = self.root / ('out-%d' % index)
                self.assertFalse((folder / 'candidate-1.flow-meta.xml').exists())
                self.assertTrue((folder / 'candidate-1.receipt.json').exists())

    def test_budget_existing_candidates_and_the_overall_deadline(self):
        self.configure(pipeline={'complete': 'never'})
        with patch.object(experts, 'MAX_GENERATION_CALLS', 3):
            code, data = self.generate()
        self.assertEqual((code, data['state'], data['reason']), (4, 'unavailable', 'generation call budget exhausted'))
        self.configure()
        calls = len(self.proxy_calls())
        code, data = self.generate()  # candidate 1's receipt already exists: refused before any hosted call
        self.assertEqual((code, data['state']), (4, 'unknown'))
        self.assertEqual(len(self.proxy_calls()), calls)
        self.assertFalse((self.root / 'out/candidate-1.flow-meta.xml').exists())
        self.configure(proxy='trickle', child=True)
        with patch.object(experts, 'CANDIDATE_SECONDS', 2):
            started = time.monotonic()
            code, data = self.generate('2')
            self.assertLess(time.monotonic() - started, 2 + 3)
        self.assertEqual((code, data['state'], data['reason']), (4, 'unavailable', 'timed out'))
        self.assert_reaped()

    def test_sigterm_reaps_the_proxy_and_removes_its_sidecars(self):
        self.configure(proxy='stall', child=True)
        command = [sys.executable, '-B', str(HELPER), 'flow', *BINDING, '--prompt-file', str(self.write_prompt()),
                   '--out-dir', str(self.root / 'out'), '--candidate', '1']
        process = subprocess.Popen(command, env=dict(self.env), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(100):
            if self.proxy_calls():
                break
            time.sleep(0.1)
        time.sleep(0.5)
        process.send_signal(signal.SIGTERM)
        out, err = process.communicate(timeout=20)
        self.assertEqual(json.loads(out)['reason'], 'interrupted; the proxy was stopped')
        self.assertNotIn('Traceback', err)
        receipt = json.loads((self.root / 'out/candidate-1.receipt.json').read_text())
        self.assertEqual((receipt['outcome']['reason'], receipt['client_rpc_calls']['total']),
                         ('interrupted; the proxy was stopped', 1))
        self.assert_reaped()
        self.assert_no_sidecars()

    def test_sigterm_during_the_readiness_wait_keeps_the_verified_activation(self):
        self.configure(rows=[self.row(False)], proxy='stall', child=True)
        command = [sys.executable, '-B', str(HELPER), 'activate', *BINDING, '--confirmed']
        process = subprocess.Popen(command, env=dict(self.env), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(100):
            if self.proxy_calls():
                break
            time.sleep(0.1)
        time.sleep(0.5)
        process.send_signal(signal.SIGTERM)
        out, err = process.communicate(timeout=20)
        data = json.loads(out)
        self.assertEqual((process.returncode, data['state'], data['readiness'], data['action'], data['before']['id'],
                          data['after']['active']), (0, 'active', 'interrupted', 'update', RECORD, True))
        self.assertNotIn('Traceback', err)
        self.assert_reaped()

    def test_a_failed_sidecar_cleanup_is_reported_not_hidden(self):
        self.configure(rows=[self.row(True)], lock_sidecars=True)
        folder = self.root / 'cache/metadata-experts' / ORG / '.sf'
        self.addCleanup(lambda: folder.exists() and folder.chmod(0o755))
        code, data = self.run_helper('status', *BINDING, '--probe')
        self.assertEqual((code, data['state'], data['reason'], data['sidecars_left']), (4, 'unavailable', experts.SIDECARS, True))

    def test_a_full_disk_while_staging_leaves_no_temporary_file(self):
        folder = self.root / 'staging'
        folder.mkdir()
        real = os.fdopen
        def failing(descriptor, *args, **kwargs):
            stream = real(descriptor, *args, **kwargs)
            def write(_):
                raise OSError(28, 'No space left on device')
            stream.write = write
            return stream
        with patch.object(experts.os, 'fdopen', failing), self.assertRaises(OSError):
            experts.publish(folder, [('candidate-1.flow-meta.xml', FLOW), ('candidate-1.receipt.json', '{}')])
        self.assertEqual(list(folder.iterdir()), [])

    def test_flow_without_the_official_plugin(self):
        self.install(records=[])
        code, data = self.generate()
        self.assertEqual((code, data['state']), (5, 'no-official-plugin'))
        self.assertEqual(self.proxy_calls(), [])

    def test_xml_transport_decoding_never_double_unescapes(self):
        self.assertEqual(experts.flow_xml(FLOW), FLOW)
        encoded = FLOW.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        self.assertEqual(experts.flow_xml(encoded), FLOW)
        self.assertIn('Q&amp;A', experts.flow_xml(encoded))

    def test_candidate_checks(self):
        spec = {'max_api_version': '66.0', 'label': 'Negotiation Follow-up', 'object': 'Opportunity',
                'trigger_type': 'RecordAfterSave', 'record_trigger_type': 'Update', 'requires_change': False}
        self.assertEqual(experts.check(FLOW, spec), [])
        every_edit = 'fires on every qualifying edit, not only when the record changes to meet the criteria'
        self.assertEqual(experts.check(FLOW, dict(spec, requires_change=True)), [every_edit])
        unused_prior = FLOW.replace('</start>', '</start><formulas><expression>$Record__Prior.StageName</expression></formulas>')
        self.assertEqual(experts.check(unused_prior, dict(spec, requires_change=True)), [every_edit])
        change_only = FLOW.replace('Criteria>false<', 'Criteria>true<')
        self.assertEqual(experts.check(change_only, dict(spec, requires_change=True)), [])
        self.assertEqual(experts.check(change_only, spec),
                         ['fires only when the record changes to meet the criteria, not on every qualifying edit'])
        stage = [{'field': 'StageName', 'operator': 'EqualTo', 'value': 'Negotiation'}]
        self.assertEqual(experts.check(FLOW, dict(spec, filters=stage)), [])
        xml_form = [{'field': 'StageName', 'operator': 'EqualTo', 'value': {'stringValue': 'Negotiation'}}]
        self.assertEqual(experts.check(FLOW, dict(spec, filters=xml_form)), [])  # the XML's own typed form
        self.assertEqual(experts.check(FLOW, dict(spec, filters=[dict(xml_form[0], value={'numberValue': 'Negotiation'})])),
                         ['entry conditions differ from the spec'])  # the type still counts
        prefix = stage + [{'field': 'Name', 'operator': 'StartsWith', 'value': 'Demo'}]
        self.assertEqual(experts.check(FLOW, dict(spec, filters=prefix)), ['entry conditions differ from the spec'])
        broken = FLOW.replace('Draft', 'Active').replace('<apiVersion>65', '<apiVersion>67').replace('Update<', 'Create<')
        self.assertEqual(len(experts.check(broken, dict(spec, label='Other'))), 3)  # status, API version, record trigger
        self.assertEqual(experts.check(FLOW, dict(spec, label='Another label')), [])  # the label is reported, not rejected

    def test_entry_conditions_compare_typed_values_and_numbered_logic_order(self):
        def filters(*items, logic=None):
            body = ''.join('<filters><field>%s</field><operator>EqualTo</operator><value><%s>%s</%s></value></filters>'
                           % (field, kind, value, kind) for field, kind, value in items)
            if logic:
                body += '<filterLogic>%s</filterLogic>' % logic
            return FLOW.replace('<filters><field>StageName</field><operator>EqualTo</operator><value><stringValue>'
                                'Negotiation</stringValue></value></filters>', body)
        spec = {'max_api_version': '66.0'}
        a, b, c = ('A__c', 'booleanValue', 'true'), ('B__c', 'numberValue', '500000.0'), ('C__c', 'stringValue', 'x')
        wanted = [{'field': 'A__c', 'operator': 'EqualTo', 'value': True},
                  {'field': 'B__c', 'operator': 'EqualTo', 'value': 500000},
                  {'field': 'C__c', 'operator': 'EqualTo', 'value': 'x'}]
        self.assertEqual(experts.check(filters(a, b, c), dict(spec, filters=wanted)), [])
        self.assertEqual(experts.check(filters(b, a, c), dict(spec, filters=wanted)), [])  # plain AND: any order
        numbered = dict(spec, filters=wanted, filter_logic='1 AND (2 OR 3)')
        self.assertEqual(experts.check(filters(a, b, c, logic='1 AND (2 OR 3)'), numbered), [])
        self.assertEqual(experts.check(filters(b, a, c, logic='1 AND (2 OR 3)'), numbered), ['entry conditions differ from the spec'])
        self.assertEqual(experts.check(filters(a, b, c, logic='1 OR 2 OR 3'), numbered), ['entry conditions differ from the spec'])
        plain = dict(spec, filters=wanted)  # plain chains of every condition mean the same as and/or (seen in a live run)
        self.assertEqual(experts.check(filters(b, a, c, logic='1 AND 2 AND 3'), plain), [])
        self.assertEqual(experts.check(filters(a, logic='1'), dict(spec, filters=wanted[:1])), [])
        self.assertEqual(experts.check(filters(a, b, c, logic='1 OR 2 OR 3'), dict(plain, filter_logic='or')), [])
        self.assertEqual(experts.check(filters(a, b, c, logic='1 OR 2 OR 3'), plain), ['entry conditions differ from the spec'])
        self.assertEqual(experts.check(filters(a, b, c, logic='1 AND 2 OR 3'), plain), ['entry conditions differ from the spec'])
        self.assertEqual(experts.check(filters(('A__c', 'stringValue', 'true'), b, c), dict(spec, filters=wanted)),
                         ['entry conditions differ from the spec'])
        xml, spec_file = self.root / 'c.xml', self.root / 'spec.json'
        xml.write_text(FLOW)
        spec_file.write_text(json.dumps(dict(spec, object='Opportunity')))
        self.assertEqual(self.run_helper('check', '--xml', str(xml), '--spec', str(spec_file)),
                         (0, {'state': 'accepted', 'problems': [], 'label': 'Negotiation Follow-up'}))
        xml.write_text('<Flow')
        self.assertEqual(self.run_helper('check', '--xml', str(xml), '--spec', str(spec_file))[0], 4)

    def test_coexistence_reports_the_official_recommender(self):
        self.configure(default='someone@example.test')
        self.assertEqual(self.run_helper('coexistence', '--host', 'claude')[1]['issues'], [])  # it only fires in a project
        (self.project / 'sfdx-project.json').write_text('{}')
        self.assertEqual(self.run_helper('coexistence', '--host', 'claude')[1]['issues'], ['recommender'])
        saved = self.root / '.sf/plugin-recommendations'
        saved.mkdir(parents=True)
        (saved / 'config.json').write_text('{"sensitivity":"off"}')
        self.assertEqual(self.run_helper('coexistence', '--host', 'claude')[1]['issues'], [])
        (saved / 'config.json').write_text('{"sensitivity":"high"}')
        with patch.dict(os.environ, {'SF_PLUGIN_MATCH_SENSITIVITY': 'off'}):
            self.assertEqual(self.run_helper('coexistence', '--host', 'claude')[1]['issues'], [])
        self.assertEqual(self.run_helper('coexistence', '--host', 'claude')[1]['issues'], ['recommender'])

    def test_coexistence_reports_auto_deploy_and_the_official_deploy_gate(self):
        os.environ['SF_DISABLE_PLUGIN_MATCH'] = '1'  # this test is about the other two checks
        self.configure(default=None)
        code, data = self.run_helper('coexistence', '--host', 'claude')
        self.assertEqual((code, data['issues']), (7, ['deploy-gate']))
        self.assertEqual(Path(self.log()[-1]['cwd']), self.project)
        self.configure(default='someone@example.test')
        self.assertEqual(self.run_helper('coexistence', '--host', 'claude'), (0, {'state': 'clear', 'issues': []}))
        self.assertEqual(self.run_helper('coexistence', *BINDING)[0], 0)  # the uniform invocation is accepted
        self.configure(default='someone@example.test', broken=['someone@example.test'])
        self.assertEqual(self.run_helper('coexistence', '--host', 'claude')[1]['issues'], ['deploy-gate'])
        elsewhere = self.root / 'launched-here'
        elsewhere.mkdir()
        self.run_helper('coexistence', '--host', 'claude', '--launch-dir', str(elsewhere))
        self.assertEqual(Path(self.log()[-2]['cwd']), elsewhere)
        with patch.dict(os.environ, {'SFDX_AUTO_DEPLOY': '1'}):
            self.assertEqual(self.run_helper('coexistence', '--host', 'claude')[1]['issues'], ['auto-deploy', 'deploy-gate'])
        with patch.dict(os.environ, {'SF_TARGET_ORG': USER}):
            self.assertEqual(self.run_helper('coexistence', '--host', 'claude')[1]['issues'], [])
        self.configure(broken=['stale@example.test'])
        with patch.dict(os.environ, {'SFDX_TARGET_ORG': 'stale@example.test'}):
            self.assertEqual(self.run_helper('coexistence', '--host', 'claude')[1]['issues'], ['deploy-gate'])
        self.install(records=[])
        self.assertEqual(self.run_helper('coexistence', '--host', 'claude')[1]['issues'], [])
        # W20: the official plugins and their hooks exist only on Claude, whatever root is named.
        self.assertEqual(self.run_helper('coexistence', '--host', 'codex', '--official-root', str(self.plugin))[1]['issues'], [])


if __name__ == '__main__':
    unittest.main()
