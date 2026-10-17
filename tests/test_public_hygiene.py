"""The public repository holds no personal paths, real org IDs, demo-org usernames or credentials.

Allowed, and only where listed: the fixtures' all-zero fake org IDs and the tokens built on them, under `tests/`,
and the synthetic JWT in the metadata-experts fixtures. Generic protective patterns such as the workspace template's
`rm -rf /Users/*` deny rule never match, because they name no user. This file scans itself too; its seeded leaks are
assembled at runtime.
"""
import base64
import binascii
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PERSONAL_PATH = re.compile(r'/(?:Users|home)/[A-Za-z][\w.-]*/|/private/(?:tmp|var/folders)/')
ORG_ID = re.compile(r'\b00D[0-9A-Za-z]{12}(?:[0-9A-Za-z]{3})?\b')
ACCESS_TOKEN = re.compile(r'\b(00D[0-9A-Za-z]{12,15})![0-9A-Za-z._]{20,}')
JWT = re.compile(r'\beyJ[\w-]{8,}\.(eyJ[\w-]{8,})\.')
SECRET = re.compile(
    r'force:/{2}\S+@'                                # an SFDX auth URL
    r'|\bxox[abprs]-[0-9A-Za-z-]{10,}'               # a Slack token
    r'|\bgh[pousr]_[0-9A-Za-z]{20,}'                 # a classic GitHub token
    r'|\bgithub_pat_[0-9A-Za-z_]{20,}'               # a fine-grained GitHub token
    r'|\bsk-[0-9A-Za-z]{20,}')                       # an API key
DEMO_USERNAME = re.compile(r'[\w.+-]+@(?:[\w-]+\.demo|salesforce\.com)\b')
FAKE_ORG_ID = re.compile(r'00D0{6,}[0-9]{1,6}[A-Z]{0,3}')
FIXTURE_JWT_FILES = {'tests/test_scout_metadata_experts.py'}


def tracked_files(root=ROOT):
    try:
        listing = subprocess.run(['git', 'ls-files', '-z'], cwd=root, capture_output=True, check=True).stdout
        paths = [root / name for name in listing.decode().split('\0') if name]
    except (OSError, subprocess.CalledProcessError):
        paths = [path for path in root.rglob('*') if path.is_file() and '.git' not in path.parts]
    return [(path, path.relative_to(root).as_posix()) for path in paths if path.is_file()]


def synthetic_jwt(payload):
    try:
        return b'synthetic' in base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4))
    except (ValueError, binascii.Error):
        return False


def findings(files):
    found = []
    for path, name in files:
        try:
            text = path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        fixture = name.startswith('tests/')
        for number, line in enumerate(text.splitlines(), 1):
            hits = [m.group(0) for m in PERSONAL_PATH.finditer(line)]
            hits += [m.group(0) for m in ORG_ID.finditer(line)
                     if not (fixture and FAKE_ORG_ID.fullmatch(m.group(0)))]
            hits += [m.group(0) for m in ACCESS_TOKEN.finditer(line)
                     if not (fixture and FAKE_ORG_ID.fullmatch(m.group(1)))]
            hits += [m.group(0) for m in JWT.finditer(line)
                     if not (name in FIXTURE_JWT_FILES and synthetic_jwt(m.group(1)))]
            hits += [m.group(0) for m in SECRET.finditer(line)]
            hits += [m.group(0) for m in DEMO_USERNAME.finditer(line)]
            found += ['%s:%d: %s' % (name, number, hit) for hit in hits]
    return found


class PublicHygieneTests(unittest.TestCase):
    def test_tracked_tree_is_clean(self):
        self.assertEqual(findings(tracked_files()), [])

    def test_every_detector_fires_in_a_tracked_tree_and_exceptions_stay_scoped(self):
        def jwt(payload):
            return 'ey' + 'JhbGciOiJIUzI1NiJ9.' + base64.urlsafe_b64encode(payload).decode().rstrip('=') + '.'
        token = '00D' + 'Kx0000012AbC!' + 'AQ0AQRealLookingToken12345'
        synthetic = jwt(b'{"sub":"synthetic"}')
        leaks = ['/' + 'Users/someone/claude-projects/x', '/' + 'home/someone/x', '/private/' + 'tmp/abc',
                 '/private/' + 'var/folders/ab/T', '00D' + 'Kx0000012AbC', token, jwt(b'{"sub":"someone-real"}'),
                 synthetic,                                  # a synthetic JWT outside its one allowed file still counts
                 'force:' + '//PlatformCLI::abc@example.my', 'xox' + 'b-1234567890-abcdef',
                 'gh' + 'p_' + 'a' * 24, 'github' + '_pat_' + 'B' * 24, 's' + 'k-' + 'c' * 24,
                 'admin' + '@acme.demo', 'someone' + '@salesforce.com',
                 '00D' + '000000000001EAA']                 # a fake ID outside tests/ still counts
        allowed = ['Bash(rm -rf /' + 'Users/*)', 'user@example.com', 'git@github.com']
        fixtures = ['00D' + '000000000001EAA', '00D' + '000000000001!' + 'AQ0AQExampleTokenValue123']
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'tests').mkdir()
            (root / 'leaks.txt').write_text('\n'.join(leaks))
            (root / 'allowed.txt').write_text('\n'.join(allowed))
            (root / 'tests/fixtures.py').write_text('\n'.join(fixtures))
            (root / 'tests/test_scout_metadata_experts.py').write_text(synthetic)
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            subprocess.run(['git', 'add', '.'], cwd=root, check=True)
            found = findings(tracked_files(root))
        flagged = {int(f.split(':')[1]) for f in found if f.startswith('leaks.txt:')}
        self.assertEqual(flagged, set(range(1, len(leaks) + 1)), found)
        self.assertIn('leaks.txt:%d: %s' % (leaks.index(token) + 1, token), found)  # the token detector, not just its org ID
        self.assertEqual([f for f in found if not f.startswith('leaks.txt:')], [])


if __name__ == '__main__':
    unittest.main()
