"""Independent CLI process fixture; never imports Scout implementation code."""
import json
import os
from pathlib import Path
import sys

state_file = Path(os.environ['SCOUT_REPORT_TEST_STATE'])
state = json.loads(state_file.read_text())
fixtures = Path(os.environ['SCOUT_REPORT_TEST_FIXTURES'])
args = sys.argv[1:]
state.setdefault('calls', []).append(args)
mode = state.get('mode', 'success')

def response(name):
    return json.loads((fixtures / (name + '.json')).read_text())

if args[:2] == ['org', 'display']:
    data = response('live-org-display')
    data['result']['accessToken'] = 'SYNTHETIC-SECRET-DO-NOT-SAVE'
elif args[:2] == ['data', 'query']:
    data = response('live-organization')
elif args[:3] == ['project', 'retrieve', 'start']:
    root = Path.cwd() / 'force-app/main/default/reports'
    (root / 'Sales_Reports').mkdir(parents=True, exist_ok=True)
    if mode != 'missing-report':
        (root / 'Sales_Reports/Pipeline.report-meta.xml').write_text(state['report'])
    if mode != 'missing-folder':
        (root / 'Sales_Reports.reportFolder-meta.xml').write_text(state['folder'])
    data = response('live-retrieve-missing' if mode == 'missing-report' else 'live-retrieve-success')
elif args[:3] == ['project', 'deploy', 'start']:
    if mode == 'preflight':
        data = response('synthetic-deploy-error')
    elif mode == 'no-job':
        data = {'status': 1, 'name': 'NetworkError'}
    else:
        root = Path.cwd() / 'force-app/main/default'
        files = [p.relative_to(root).as_posix() for p in root.rglob('*.xml')]
        assert files == ['reports/Sales_Reports/Pipeline.report-meta.xml'], files
        state['report'] = (root / files[0]).read_text()
        data = response('synthetic-deploy-start')
elif args[:3] == ['project', 'deploy', 'report']:
    data = response('synthetic-report-success')
else:
    raise AssertionError('unexpected CLI call: ' + str(args))
if args[:2] != ['org', 'display']:
    assert args[args.index('--target-org') + 1] == 'maple@example.test', args
state_file.write_text(json.dumps(state))
print(json.dumps(data))
sys.exit(data['status'])
