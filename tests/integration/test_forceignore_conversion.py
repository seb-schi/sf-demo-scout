"""Mandatory real-Salesforce-CLI gate; run separately in a network-denied sandbox."""

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
NS = "http://soap.sforce.com/2006/04/metadata"
EXPECTED_MEMBERS = {("CustomObject", "W8_Probe__c"), ("LightningComponentBundle", "w8Probe")}
SOURCE = {
    "objects/W8_Probe__c/W8_Probe__c.object-meta.xml": (
        f'<CustomObject xmlns="{NS}"><label>W8 Probe</label><pluralLabel>W8 Probes</pluralLabel>'
        '<nameField><label>Name</label><type>Text</type></nameField>'
        '<deploymentStatus>Deployed</deploymentStatus><sharingModel>ReadWrite</sharingModel></CustomObject>'
    ),
    "lwc/w8Probe/w8Probe.js": "export default class W8Probe {}\n",
    "lwc/w8Probe/w8Probe.html": "<template>W8 probe</template>\n",
    "lwc/w8Probe/w8Probe.js-meta.xml": (
        f'<LightningComponentBundle xmlns="{NS}"><apiVersion>66.0</apiVersion>'
        '<isExposed>false</isExposed></LightningComponentBundle>'
    ),
}
EXPECTED_FILES = {
    "package.xml", "objects/W8_Probe__c.object",
    "lwc/w8Probe/w8Probe.js", "lwc/w8Probe/w8Probe.html", "lwc/w8Probe/w8Probe.js-meta.xml",
}


class ForceignoreConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sf = shutil.which("sf")
        if cls.sf is None:
            raise RuntimeError("Real sf CLI is required for this gate; no stub, install or skipped pass")
        cls.state = tempfile.TemporaryDirectory(prefix="scout-forceignore-cli-", dir="/tmp")
        cls.addClassCleanup(cls.state.cleanup)
        cls.state_root = Path(cls.state.name).resolve()
        # Allowlist, rather than inherit credentials, org selectors or CLI state overrides.
        cls.env = {"PATH": os.environ.get("PATH", os.defpath), "LANG": "en_US.UTF-8",
                   "PYTHONDONTWRITEBYTECODE": "1", "SF_DISABLE_TELEMETRY": "true",
                   "SF_AUTOUPDATE_DISABLE": "true", "SF_DISABLE_AUTOUPDATE": "true"}
        for key in ("HOME", "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME", "XDG_CACHE_HOME",
                    "XDG_DATA_HOME", "TMPDIR"):
            directory = cls.state_root / key.lower()
            directory.mkdir()
            cls.env[key] = str(directory)
        print("Isolation: " + json.dumps(cls.env, sort_keys=True), flush=True)
        result = cls.command([cls.sf, "--version"], cls.state_root)
        if result.returncode != 0:
            raise RuntimeError("sf --version failed")
        # Read the installed dependency's metadata; do not run npm or contact a registry.
        for parent in Path(cls.sf).resolve().parents:
            package = parent / "node_modules/@salesforce/source-deploy-retrieve/package.json"
            if package.is_file():
                print("SDR version: " + json.loads(package.read_text(encoding="utf-8"))["version"], flush=True)
                break
        else:
            raise RuntimeError("Cannot locate the installed CLI's SDR package.json to record its version")

    @classmethod
    def command(cls, argv, cwd):
        print("cwd=" + str(cwd) + "\n$ " + shlex.join(map(str, argv)), flush=True)
        result = subprocess.run(list(map(str, argv)), cwd=cwd, env=cls.env,
                                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                timeout=90, check=False)
        print("exit=" + str(result.returncode) + "\n" + result.stdout + result.stderr, flush=True)
        return result

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="scout-forceignore-source-", dir="/tmp")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.workspace = self.base / ".hidden parent/workspace with spaces"
        self.customer = self.workspace / "orgs/customer"
        self.customer.mkdir(parents=True)
        (self.workspace / "sfdx-project.json").write_text(json.dumps({
            "packageDirectories": [{"path": "force-app", "default": True}],
            "sourceApiVersion": "66.0", "namespace": "",
        }), encoding="utf-8")
        # An outer file is essential: without one SDR accepts all paths, even dot-paths.
        self.outer_ignore = self.workspace / ".forceignore"
        self.outer_ignore.write_text("# Outer workspace ignore boundary\n", encoding="utf-8")
        result = self.command([sys.executable, "-B", ROOT / "scripts/build-assets.py",
                               "prepare-workspace", "--workspace-root", self.workspace,
                               "--customer-dir", self.customer, "--writer", "scout"], self.base)
        self.assertEqual(result.returncode, 0)
        owned = json.loads(result.stdout)
        self.project = Path(owned["project_root"])
        self.source = Path(owned["source_root"])
        self.assertTrue((self.project / ".forceignore").is_file())
        for relative, content in SOURCE.items():
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        for relative in (
            ".hidden-root", ".hidden-dir/nested/junk.xml", "junk.dup",
            "package2-descriptor.json", "package2-manifest.json",
            "lwc/w8Probe/.hidden-file", "lwc/w8Probe/.hidden-dir/nested/junk.js",
            "lwc/w8Probe/nested/.hidden-file", "lwc/w8Probe/nested/backup.dup",
            "lwc/w8Probe/package2-descriptor.json", "lwc/w8Probe/nested/package2-manifest.json",
        ):
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("must not be converted", encoding="utf-8")
        self.sequence = 0

    def convert(self, absolute):
        self.sequence += 1
        output = self.base / ("converted-" + str(self.sequence))
        source = self.source if absolute else self.source.relative_to(self.project)
        result = self.command([self.sf, "project", "convert", "source", "--source-dir", source,
                               "--output-dir", output, "--api-version", "66.0", "--json"], self.project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], 0)
        self.assertEqual(Path(payload["result"]["location"]).resolve(), output)
        # This manifest is generated locally from synthetic fixtures, never org/user XML.
        manifest = ET.parse(output / "package.xml").getroot()
        members = {
            (entry.findtext("m:name", namespaces={"m": NS}), member.text)
            for entry in manifest.findall("m:types", {"m": NS})
            for member in entry.findall("m:members", {"m": NS})
        }
        files = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()}
        print("Manifest members: " + repr(sorted(members)) + "\nOutput files: " + repr(sorted(files)), flush=True)
        return output, members, files

    def assert_resolves(self, absolute):
        output, members, files = self.convert(absolute)
        self.assertEqual(members, EXPECTED_MEMBERS)
        self.assertEqual(files, EXPECTED_FILES)
        for relative in ("lwc/w8Probe/w8Probe.js", "lwc/w8Probe/w8Probe.html"):
            self.assertEqual((output / relative).read_text(encoding="utf-8"), SOURCE[relative])
        obj = ET.parse(output / "objects/W8_Probe__c.object").getroot()
        self.assertEqual(obj.findtext("m:label", namespaces={"m": NS}), "W8 Probe")

    def test_relative_and_absolute_source_resolve_and_exclude_junk(self):
        for absolute in (False, True):
            with self.subTest(absolute=absolute):
                self.assert_resolves(absolute)

    def test_removing_only_project_ignore_reproduces_trap_then_restore_recovers(self):
        ignore = self.project / ".forceignore"
        contents = ignore.read_bytes()
        self.assert_resolves(True)
        ignore.unlink()
        for absolute in (False, True):
            with self.subTest(absolute=absolute):
                _, members, files = self.convert(absolute)
                self.assertEqual(members, set())
                self.assertEqual(files, {"package.xml"})
        ignore.write_bytes(contents)
        self.assert_resolves(True)

    def test_defaults_still_exclude_junk_without_outer_ignore(self):
        self.outer_ignore.unlink()
        self.assert_resolves(True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
