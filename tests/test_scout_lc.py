"""Lifecycle Center mode (scripts/scout_lc.py): adopting a pipeline as a team, package start, check and hand-over, and
the captain's delivery (its checks, the revision and org copies a yes binds to, the test gate, the sync, resume and
recovery), back-flow and updates. Real Git against a local bare repository; `sf` and `gh` are stand-ins
(tests/fixtures/lc_stub_*.py) that answer in the shapes recorded live (tests/fixtures/lc_cli_shapes.json). Dana is a
builder without Scout: her own clone, plain Git and the official CLI."""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.dont_write_bytecode = True
import scout_lc as lc  # noqa: E402
import scout_team as team  # noqa: E402

SF_STUB = ROOT / "tests" / "fixtures" / "lc_stub_sf.py"
GH_STUB = ROOT / "tests" / "fixtures" / "lc_stub_gh.py"
SHAPES = json.loads((ROOT / "tests" / "fixtures" / "lc_cli_shapes.json").read_text())
COMMON, BOB_ORG, ELSEWHERE = "00D000000000042EAC", "00D000000000044EAC", "00D000000000099EAC"
REMOTE_URL = "https://github.com/acme/team.git"
TEAM_ID = "lc-acme-team"
STAGE18 = "1QV000000000001AAA"
CLS = "force-app/main/default/classes/Invoice.cls"
CLASS = "public with sharing class Invoice {{\n    public static Integer total() {{ return {n}; }}\n    // one\n    // two\n}}\n"
META = '<?xml version="1.0" encoding="UTF-8"?>\n<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">\n    <apiVersion>64.0</apiVersion>\n    <status>Active</status>\n</ApexClass>\n'
TEST = "@IsTest\nprivate class InvoiceTest {\n    @IsTest static void totals() { System.assert(Invoice.total() >= 0); }\n}\n"
LAYOUT_PATH = "force-app/main/default/layouts/Probe__c-Probe Layout.layout-meta.xml"
LAYOUT = ('<?xml version="1.0" encoding="UTF-8"?>\n<Layout xmlns="http://soap.sforce.com/2006/04/metadata">\n'
          '    <layoutSections>\n        <label>Info</label>\n        <style>OneColumn</style>\n    </layoutSections>\n'
          '    <layoutSections>\n        <layoutColumns/>\n        <style>CustomLinks</style>\n    </layoutSections>\n'
          '    <showHighlightsPanel>false</showHighlightsPanel>\n</Layout>\n')
NO_EFFECTS = "#!/bin/sh\ncat >/dev/null\nprintf '{}'\n"
TEST_PATH = "force-app/main/default/classes/InvoiceTest.cls"
SUITE_PATH = "force-app/main/default/testSuites/InvoiceSuite.testSuite-meta.xml"
SUITE = ('<?xml version="1.0" encoding="UTF-8"?>\n<ApexTestSuite xmlns="http://soap.sforce.com/2006/04/metadata">\n'
         '    <testClassName>InvoiceTest</testClassName>\n</ApexTestSuite>\n')
OWN_AGENTS = "# Our own rules\n\nBe kind to the org.\n"
OBJECT = ('<?xml version="1.0" encoding="UTF-8"?>\n<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">\n'
          '    <label>{label}</label>\n    <pluralLabel>{label}s</pluralLabel>\n    <deploymentStatus>Deployed</deploymentStatus>\n'
          '    <sharingModel>ReadWrite</sharingModel>\n</CustomObject>\n')
TAB = ('<?xml version="1.0" encoding="UTF-8"?>\n<CustomTab xmlns="http://soap.sforce.com/2006/04/metadata">\n'
       '    <customObject>true</customObject>\n    <motif>Custom20: Airplane</motif>\n</CustomTab>\n')
PERMSET = ('<?xml version="1.0" encoding="UTF-8"?>\n<PermissionSet xmlns="http://soap.sforce.com/2006/04/metadata">\n'
           '    <label>{label}</label>\n    <tabSettings>\n        <tab>{tab}</tab>\n        <visibility>{visibility}</visibility>\n'
           '    </tabSettings>\n</PermissionSet>\n')
JOIN = ["join", "--hub", "common", "--pipeline-id", "1PJ000000000001", "--common-org", "common", "--build-org", "bob-sbx"]
START = ["start", "--hub", "common", "--pipeline-id", "1PJ000000000001", "--common-org", "common"]


def object_path(name):
    return f"force-app/main/default/objects/{name}/{name}.object-meta.xml"


def tab_path(name):
    return f"force-app/main/default/tabs/{name}.tab-meta.xml"


def permset_path(name):
    return f"force-app/main/default/permissionsets/{name}.permissionset-meta.xml"


def sh(*args, cwd=None):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(f"{' '.join(map(str, args))} failed: {result.stderr.strip()}")
    return result.stdout.strip()


@unittest.skipIf(os.name == "nt", "team mode on Windows comes later; these fixtures are POSIX shell stand-ins")
class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="scout-lc-test-")).resolve()
        self.stub = self.tmp / "stub"
        (self.stub / "orgs").mkdir(parents=True)
        (self.stub / "orgs.json").write_text(json.dumps({
            "common": {"id": COMMON, "username": "admin@common.example", "alias": "common", "apiVersion": "64.0"},
            "bob-sbx": {"id": BOB_ORG, "username": "admin@common.example.bob", "alias": "bob-sbx", "apiVersion": "64.0"}}))
        self.remote = self.tmp / "remote.git"
        sh("git", "init", "--quiet", "--bare", "--initial-branch=main", str(self.remote))
        for who, name in (("ana", "Ana Captain"), ("bob", "Bob Builder"), ("dana", "Dana Builder"), ("seed", "Seed")):
            home = self.tmp / who
            (home / "ws").mkdir(parents=True)
            (home / "gitconfig").write_text(f"[user]\n\tname = {name}\n\temail = {who}@example.com\n"
                                            "[commit]\n\tgpgsign = false\n[init]\n\tdefaultBranch = main\n"
                                            f'[url "{self.remote}"]\n\tinsteadOf = {REMOTE_URL}\n')
        node = self.tmp / "node-stub"
        node.write_text(NO_EFFECTS)
        node.chmod(0o755)
        self.node = node
        self._env = dict(os.environ)
        self.seed()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        subprocess.run(["rm", "-rf", str(self.tmp)])

    # ---- the world: GitHub, the org, the hub ----

    def env(self, who, **extra):
        home = self.tmp / who
        env = {"SCOUT_TEAMS_FILE": str(home / "teams.json"), "SCOUT_TEAM_CACHE": str(home / "cache" / "teams"),
               "SCOUT_WORKSPACE": str(home / "ws"), "GIT_CONFIG_GLOBAL": str(home / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1",
               "SCOUT_TEAM_SF": str(SF_STUB), "SCOUT_TEAM_GH": str(GH_STUB), "SCOUT_TEAM_NODE": str(self.node),
               "STUB_ROOT": str(self.stub), "STUB_REMOTE": str(self.remote), "STUB_REPO": "acme/team",
               "STUB_GUARD": team.sf_mp_version(), "SCOUT_TEAM_WATCH_OFF": "", "SF_DATA_DIR": str(home / "sf-data")}
        env.update(extra)
        return env

    def seed(self):
        work = self.tmp / "seed" / "repo"
        env = dict(os.environ, **self.env("seed"))
        sh("git", "clone", "--quiet", str(self.remote), str(work))
        (work / "sfdx-project.json").write_text(json.dumps({"packageDirectories": [{"path": "force-app", "default": True}],
                                                            "sourceApiVersion": "64.0"}))
        self.write(work, "AGENTS.md", OWN_AGENTS)
        self.write(work, CLS, CLASS.format(n=1))
        self.write(work, CLS + "-meta.xml", META)
        self.write(work, LAYOUT_PATH, LAYOUT)
        self.write(work, TEST_PATH, TEST)
        self.write(work, TEST_PATH + "-meta.xml", META)
        self.write(work, SUITE_PATH, SUITE)
        subprocess.run(["git", "-C", str(work), "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", str(work), "commit", "--quiet", "-m", "start"], check=True, env=env)
        subprocess.run(["git", "-C", str(work), "push", "--quiet", "origin", "main"], check=True, env=env)
        for rel in (CLS, CLS + "-meta.xml", LAYOUT_PATH, TEST_PATH, TEST_PATH + "-meta.xml", SUITE_PATH):  # the org holds main
            self.org_write("common", rel, (work / rel).read_text(), saved=True)
            self.org_write("bob-sbx", rel, (work / rel).read_text())
        self.suites(["InvoiceSuite"])  # the stage's Pre-Promote suite

    def push_to_main(self, files, message, orgs=(), remove=()):
        """A commit straight onto main, outside the pipeline (and, with orgs, the same files in those orgs)."""
        work = self.tmp / "seed" / "repo"
        env = dict(os.environ, **self.env("seed"))
        subprocess.run(["git", "-C", str(work), "pull", "--quiet", "--ff-only", "origin", "main"], check=True, env=env)
        for rel, text in files.items():
            self.write(work, rel, text)
            for org in orgs:
                self.org_write(org, rel, text, saved=org == "common")
        for rel in remove:
            subprocess.run(["git", "-C", str(work), "rm", "--quiet", rel], check=True, env=env)
            for org in orgs:
                (self.stub / "orgs" / org / rel[len(team.SOURCE):]).unlink(missing_ok=True)
        subprocess.run(["git", "-C", str(work), "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", str(work), "commit", "--quiet", "-m", message], check=True, env=env)
        subprocess.run(["git", "-C", str(work), "push", "--quiet", "origin", "main"], check=True, env=env)
        return sh("git", "-C", str(self.remote), "rev-parse", "main")

    def suites(self, names, org_suites=None):
        data = self.hub() or {"items": {}, "next": 1, "lists": [], "promotions": [], "suites": [], "options": {}}
        data["suites"] = names
        if org_suites is not None:
            data["org_suites"] = org_suites
        (self.stub / "lc-state.json").write_text(json.dumps(data))

    def write(self, root, rel, text):
        path = Path(root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def org_write(self, org, rel, text, saved=False):
        data = text.encode()
        if saved:
            sys.path.insert(0, str(SF_STUB.parent))
            with mock.patch.dict(os.environ, {"STUB_ROOT": str(self.stub)}):
                import importlib
                stub = importlib.import_module("lc_stub_sf")
                data = stub.on_save(rel, data)
        path = self.stub / "orgs" / org / rel[len(team.SOURCE):]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def org_read(self, org, rel):
        return (self.stub / "orgs" / org / rel[len(team.SOURCE):]).read_text()

    def main_text(self, rel, ref="main"):
        return sh("git", "-C", str(self.remote), "show", f"{ref}:{rel}") + "\n"

    def main_sha(self, ref="main"):
        return sh("git", "-C", str(self.remote), "rev-parse", ref)

    def sync_sandbox(self, *rels):
        """Bob deploys main's copy into his sandbox."""
        for rel in rels:
            self.org_write("bob-sbx", rel, self.main_text(rel))

    def hub(self):
        return json.loads((self.stub / "lc-state.json").read_text()) if (self.stub / "lc-state.json").exists() else {}

    def submitted(self):
        """The promotions submitted: a merge's record has neither a status nor a request until one fills it in."""
        return [p for p in self.hub().get("promotions", []) if p["status"] or p["token"]]

    def github(self):
        path = self.stub / "lc-gh.json"
        return json.loads(path.read_text()) if path.exists() else {"prs": [], "comments": []}

    def options(self, **values):
        data = self.hub() or {"items": {}, "next": 1, "lists": [], "promotions": [], "suites": [], "options": {}}
        data["options"].update(values)
        (self.stub / "lc-state.json").write_text(json.dumps(data))

    def call(self, who, *args, **extra):
        saved = dict(os.environ)
        os.environ.update(self.env(who, **extra))
        try:
            buffer, errors = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(errors), \
                    mock.patch.object(lc, "SYNC_WAIT", 0), mock.patch.object(lc, "STATUS_WAIT", 0):
                code = lc.main([str(a) for a in args])
            self.stderr = errors.getvalue()  # the progress lines of this call
            text = buffer.getvalue().strip()
            return code, (json.loads(text) if text.startswith("{") else text)
        finally:
            os.environ.clear()
            os.environ.update(saved)

    def hook(self, who):
        saved = dict(os.environ)
        os.environ.update(self.env(who))
        try:
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer), mock.patch.object(lc, "spawn_fetch", lambda team_id: None), \
                    mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"cwd": str(self.tmp / who / "ws")}))):
                lc.main(["updates", "--hook"])
            return buffer.getvalue()
        finally:
            os.environ.clear()
            os.environ.update(saved)

    def git_as(self, who, *args):
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True,
                              env=dict(os.environ, **self.env(who))).stdout.strip()

    def sf_stub(self, *args, who="ana"):
        result = subprocess.run([str(SF_STUB), *args, "--json"], capture_output=True, text=True,
                                env=dict(os.environ, **self.env(who)), cwd=self.tmp)
        return json.loads(result.stdout)

    def gh_stub(self, *args, who="ana"):
        return subprocess.run([str(GH_STUB), *args], capture_output=True, text=True, env=dict(os.environ, **self.env(who)),
                              cwd=self.tmp)

    def cache(self, who="ana"):
        return self.tmp / who / "cache" / "teams" / TEAM_ID

    # ---- the team and its builders ----

    def team_up(self):
        code, body = self.call("ana", "start", "--hub", "common", "--pipeline-id", "1PJ000000000001", "--common-org", "common", "--yes")
        self.assertEqual(code, 0, body)
        code, body = self.call("bob", "join", "--hub", "common", "--pipeline-id", "1PJ000000000001", "--common-org", "common",
                               "--build-org", "bob-sbx", "--yes", "--yes-guard")
        self.assertEqual(code, 0, body)
        self.ana = Path(json.loads((self.tmp / "ana" / "teams.json").read_text())["teams"][TEAM_ID]["checkout"])
        self.bob = Path(json.loads((self.tmp / "bob" / "teams.json").read_text())["teams"][TEAM_ID]["checkout"])

    def package(self, title, *components, who="bob", owner=None):
        code, body = self.call(who, "package", "start", "--title", title, "--components", *components,
                               *(["--owner", owner] if owner else []))
        self.assertEqual(code, 0, body)
        return body["work_item"]

    def build(self, n, extra_test=False):
        self.org_write("bob-sbx", CLS, CLASS.format(n=n))
        if extra_test:
            self.org_write("bob-sbx", TEST_PATH, TEST.replace("private class InvoiceTest {", f"private class InvoiceTest {{\n    // covers total {n}"))
            self.org_write("bob-sbx", TEST_PATH + "-meta.xml", META)

    def handover(self, wi, *extra):
        code, body = self.call("bob", "handover", "--wi", wi, *extra)
        self.assertEqual(code, 0, body)
        return body

    def deliver(self, wi, *extra):
        code, plan = self.call("ana", "deliver", "--wi", wi, *extra)
        if code != 3 or plan.get("needs") != "deliver-yes":
            return code, plan
        return self.call("ana", "deliver", "--wi", wi, "--yes", "--plan-id", plan["plan_id"], *extra)

    def dana_commits(self, wi, files, message, remove=()):
        """Dana, without Scout: her own clone, a commit on the work item's branch, a push."""
        work = self.tmp / "dana" / "repo"
        if not (work / ".git").exists():
            self.git_as("dana", "clone", "--quiet", REMOTE_URL, str(work))
        self.git_as("dana", "-C", str(work), "fetch", "--quiet", "origin")
        self.git_as("dana", "-C", str(work), "checkout", "--quiet", "-B", wi, f"origin/{wi}")
        for rel, text in files.items():
            self.write(work, rel, text)
        for rel in remove:
            self.git_as("dana", "-C", str(work), "rm", "--quiet", rel)
        self.git_as("dana", "-C", str(work), "add", "-A")
        self.git_as("dana", "-C", str(work), "commit", "--quiet", "-m", message)
        self.git_as("dana", "-C", str(work), "push", "--quiet", "origin", wi)
        return self.git_as("dana", "-C", str(work), "rev-parse", "HEAD")

    def describe(self, wi, text):
        """A builder's own `sf devops work-item update --description`."""
        return self.sf_stub("devops", "work-item", "update", "--work-item-name", wi, "--description", text, who="dana")

    def review(self, wi):
        return self.sf_stub("devops", "review", "create", "--work-item-name", wi, who="dana")

    def pr_number(self, wi):
        return next(p["number"] for p in self.github()["prs"] if p["head"] == wi)

    def item(self, wi):
        return self.hub()["items"][wi]

    # ---- the stub, the IDs and the team ----

    def test_the_stub_answers_in_the_recorded_shapes(self):
        """A stub that answers in a richer shape than the real CLI hides bugs. Every recorded answer's
        keys must be the stub's keys for the same call."""
        self.team_up()
        wi = self.package("Shapes", "ApexClass:Invoice")
        data = self.hub()
        def keys(answer):
            body = answer.get("result", answer) if isinstance(answer, dict) else answer
            return sorted(body.keys()) if isinstance(body, dict) else None
        create = self.sf_stub("devops", "work-item", "create", "--project-id", "1Qg000000000001AAA", "--subject", "x")
        self.assertEqual(keys(create), keys(SHAPES["work-item-create"]["answer"]))
        self.assertEqual(len(create["result"]["workItemId"]), 15)
        update = self.sf_stub("devops", "work-item", "update", "--work-item-name", create["result"]["workItemName"], "--status", "In Progress")
        self.assertEqual(keys(update), keys(SHAPES["work-item-update"]["answer"]))
        self.assertEqual(len(update["result"]["workItemId"]), 18)
        review = self.sf_stub("devops", "review", "create", "--work-item-name", wi)
        self.assertEqual(keys(review), keys(SHAPES["review-create"]["answer"]))
        crash = self.sf_stub("devops", "promotion", "complete", "--target-stage-id", STAGE18, "--work-item-id",
                             data["items"][wi]["id"])
        self.assertEqual(lc.kind_of(1, crash), "long-id")
        self.assertEqual(lc.kind_of(1, SHAPES["complete-18-character-crash"]["answer"]), "long-id")
        for name in ("validate-external-merges", "validate-already-merged", "validate-merge-conflict", "complete-in-progress",
                     "complete-pr-does-not-exist", "complete-first-stage-no-item"):
            self.assertNotEqual(lc.kind_of(1, SHAPES[name]["answer"]), "ok", name)
        self.assertEqual(lc.kind_of(0, SHAPES["complete-submitted"]["answer"]["result"]), "ok")
        status_keys = sorted(SHAPES["request-status-success"]["answer"]["result"])
        self.assertIn("errorDetails", status_keys)

    def test_ids_have_both_lengths_and_the_platforms_checksum(self):
        # Salesforce's documented example of turning a 15-character ID into its 18-character form
        self.assertEqual(lc.id18("001A0000006Vm9r"), "001A0000006Vm9rIAC")
        self.assertEqual(lc.id18("001A0000006Vm9rIAC"), "001A0000006Vm9rIAC")
        self.assertEqual(lc.id15("001A0000006Vm9rIAC"), "001A0000006Vm9r")
        self.assertEqual(lc.id18("000000000000000"), "000000000000000AAA")
        self.assertEqual(lc.id18("AAAAAaaaaaAAAAA"), "AAAAAaaaaaAAAAA5A5")
        with self.assertRaises(team.Stop):
            lc.id15("not an id")

    def test_start_adopts_the_pipeline_keeps_the_teams_own_rules_and_binds_only_the_captain(self):
        code, body = self.call("ana", "start", "--hub", "common", "--pipeline-id", "1PJ000000000001", "--common-org", "common")
        self.assertEqual(code, 3, body)
        self.assertEqual(body["needs"], "start-yes")
        self.team_up()
        agents = self.main_text("AGENTS.md")
        self.assertTrue(agents.startswith(OWN_AGENTS), "the team's own AGENTS.md keeps its text")
        self.assertIn(lc.RULES_START, agents)
        self.assertIn("Checked: <commit>", agents)
        ignore = self.main_text(".gitignore")
        for line in (".agents/", ".claude/", ".cursor/"):
            self.assertIn(line, ignore)
        code, again = self.call("ana", "start", "--hub", "common", "--pipeline-id", "1PJ000000000001", "--common-org", "common", "--yes")
        self.assertEqual((code, again["written_on_main"]), (0, []), "a second start writes nothing")
        self.assertEqual(self.main_text("AGENTS.md").count(lc.RULES_START), 1)
        entry = json.loads((self.tmp / "ana" / "teams.json").read_text())["teams"][TEAM_ID]
        self.assertEqual((entry["mode"], entry["role"], entry["common_org_id"]), ("lifecycle", "captain", COMMON[:15]))
        inits = [json.loads(l) for l in (self.stub / "sf-calls.log").read_text().splitlines() if '"mp", "init"' in l]
        self.assertTrue(all("--target-org" in c and "--set-default" not in c for c in inits))
        registry = json.loads((self.stub / "mp-registry.json").read_text())
        self.assertTrue(registry[str(self.tmp / "ana" / "teams.json")][COMMON[:15]]["lifecycleCaptain"])
        self.assertFalse(registry[str(self.tmp / "bob" / "teams.json")][COMMON[:15]]["lifecycleCaptain"],
                         "a builder's machine can't validate against the common org")

    def test_the_stage_must_deploy_to_the_common_org_at_start_and_at_each_delivery(self):
        self.options(stage_org=ELSEWHERE)
        code, body = self.call("ana", "start", "--hub", "common", "--pipeline-id", "1PJ000000000001", "--common-org", "common", "--yes")
        self.assertEqual(code, 2, body)
        self.assertIn(f"deploys to {ELSEWHERE[:15]}", body["reason"])
        self.options(stage_org=COMMON, stage_branch="develop")
        code, body = self.call("ana", "start", "--hub", "common", "--pipeline-id", "1PJ000000000001", "--common-org", "common", "--yes")
        self.assertEqual(code, 2, body)
        self.assertIn("branch is develop", body["reason"])
        self.options(stage_branch="main")
        self.team_up()
        wi = self.package("Invoice totals 20", "ApexClass:Invoice")
        self.build(20)
        self.handover(wi)
        self.options(stage_org=ELSEWHERE)  # the stage's environment was replaced after the team started
        code, body = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual(code, 2, body)
        self.assertIn("now deploys to", body["reason"])
        self.assertFalse((self.stub / "validations.json").exists(), "nothing was validated against the wrong org")

    # ---- a delivery ----

    def test_a_delivery_end_to_end_is_bound_to_one_revision_and_verified_by_the_read_back(self):
        self.team_up()
        wi = self.package("Invoice totals 2", "ApexClass:Invoice")
        self.build(2)
        handed = self.handover(wi)
        self.assertTrue(handed["handed_over"])
        self.assertTrue(handed["checked"], "Scout's package start recorded the builder's checked base")
        code, plan = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual(code, 3, plan)
        self.assertEqual(plan["needs"], "deliver-yes")
        self.assertEqual(plan["components"], ["ApexClass:Invoice"])
        self.assertEqual(plan["checks"]["base"]["state"], "checked")
        code, body = self.call("ana", "deliver", "--wi", wi, "--yes", "--plan-id", plan["plan_id"])
        self.assertEqual(code, 0, body)
        self.assertEqual(body["outcome"], "verified")
        self.assertIn("return 2;", self.org_read("common", CLS))
        merge = self.main_sha()
        self.assertTrue(merge.startswith(body["merge"]))
        self.assertEqual(sh("git", "-C", str(self.remote), "log", "-1", "--format=%s", "main"),
                         f"{wi}: Invoice totals 2 (#{self.pr_number(wi)})", "Scout's merge names its work item")
        comments = self.github()["comments"]
        self.assertTrue(comments[-1]["body"].startswith(f"Verified in the common org at {merge}"))
        complete = [json.loads(l) for l in (self.stub / "sf-calls.log").read_text().splitlines() if '"complete"' in l]
        self.assertEqual(len(complete[-1][complete[-1].index("--work-item-id") + 1]), 15, "15-character ID to complete")
        self.assertEqual(self.hub()["promotions"][-1]["merge"], merge, "the platform recorded the merge it delivered")

    def test_a_push_after_the_plan_invalidates_the_yes(self):
        self.team_up()
        wi = self.package("Invoice totals 3", "ApexClass:Invoice")
        self.build(3)
        self.handover(wi)
        code, plan = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual(plan["needs"], "deliver-yes")
        self.build(4)
        self.handover(wi)
        code, body = self.call("ana", "deliver", "--wi", wi, "--yes", "--plan-id", plan["plan_id"])
        self.assertEqual(code, 3, body)
        self.assertIn("changed since you saw it", body["reason"])
        self.assertEqual(self.github()["prs"][0]["state"], "OPEN")

    def test_a_direct_edit_stops_the_delivery_and_a_back_flow_carries_it_into_main(self):
        self.team_up()
        wi = self.package("Invoice totals 5", "ApexClass:Invoice")
        self.build(5)
        self.handover(wi)
        self.org_write("common", CLS, CLASS.format(n=1).replace("// two", "// edited in the org"), saved=True)
        code, body = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual(code, 3, body)
        self.assertEqual(body["needs"], "direct-edit")
        self.assertEqual(body["edits"]["ApexClass:Invoice"]["state"], "changed")
        code, flow = self.call("ana", "backflow", "--components", "ApexClass:Invoice", "--yes")
        self.assertEqual(code, 0, flow)
        code, done = self.deliver(flow["work_item"])
        self.assertEqual(code, 0, done)
        self.assertIn("// edited in the org", self.main_text(CLS))

    def test_the_layouts_measured_rewrite_isnt_a_direct_edit_but_a_real_layout_change_is(self):
        self.team_up()
        wi = self.package("Layout highlights", "Layout:Probe__c-Probe Layout")
        self.org_write("bob-sbx", LAYOUT_PATH, LAYOUT.replace("<showHighlightsPanel>false", "<showHighlightsPanel>true"))
        self.handover(wi)
        code, plan = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual(plan.get("needs"), "deliver-yes", plan)  # the org's extra empty columns aren't an edit
        self.org_write("common", LAYOUT_PATH, LAYOUT.replace("<label>Info</label>", "<label>Edited</label>"), saved=True)
        code, body = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual(body.get("needs"), "direct-edit", body)

    def test_an_overwrite_is_bound_to_the_copy_seen_and_a_later_edit_needs_a_new_yes(self):
        self.team_up()
        wi = self.package("Invoice totals 15", "ApexClass:Invoice")
        self.build(15)
        self.handover(wi)
        admin = lambda note: self.org_write("common", CLS, CLASS.format(n=1).replace("// two", f"// {note}"), saved=True)
        admin("admin one")
        code, body = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual(body.get("needs"), "direct-edit", body)
        code, plan = self.call("ana", "deliver", "--wi", wi, "--overwrite")
        self.assertEqual(plan.get("needs"), "deliver-yes", plan)
        self.assertEqual(plan["checks"]["overwrite"], ["ApexClass:Invoice"])
        admin("admin two")  # before the yes: the yes was for the copy shown, not this one
        code, body = self.call("ana", "deliver", "--wi", wi, "--overwrite", "--yes", "--plan-id", plan["plan_id"])
        self.assertEqual(code, 3, body)
        self.assertIn("changed since you saw it", body["reason"])
        self.assertEqual(self.github()["prs"][0]["state"], "OPEN", "nothing merged")
        self.options(sync_misses=99)
        code, plan = self.call("ana", "deliver", "--wi", wi, "--overwrite")
        code, body = self.call("ana", "deliver", "--wi", wi, "--overwrite", "--yes", "--plan-id", plan["plan_id"])
        self.assertEqual(code, 1, body)
        self.assertTrue(body.get("pending"), "merged, waiting for the sync")
        admin("admin three")  # while the delivery waits: the approved overwrite was for "admin two" only
        self.options(sync_misses=0)
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual((code, body.get("needs")), (3, "direct-edit"), body)
        self.assertNotIn("return 15;", self.org_read("common", CLS))
        code, ask = self.call("ana", "deliver", "--wi", wi, "--resume", "--overwrite")
        self.assertEqual((code, ask.get("needs")), (3, "overwrite-yes"), ask)
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume", "--overwrite", "--yes", "--plan-id", ask["plan_id"])
        self.assertEqual(code, 0, done)
        self.assertIn("return 15;", self.org_read("common", CLS))
        backups = {p.read_text() for p in (self.cache() / "backups").rglob("Invoice.cls")}
        self.assertTrue(any("admin two" in t for t in backups) and any("admin three" in t for t in backups), backups)
        self.assertEqual(len(self.hub()["promotions"]), 1)

    # ---- the builder's base ----

    def test_a_builder_without_a_checked_base_needs_the_captains_confirmation(self):
        self.team_up()
        wi = self.package("Dana's totals", "ApexClass:Invoice", who="ana", owner="Dana")
        self.assertNotIn("Checked:", self.item(wi)["description"])
        self.dana_commits(wi, {CLS: CLASS.format(n=21)}, "fix totals")
        self.review(wi)
        code, body = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual((code, body.get("needs")), (3, "unchecked-base"), body)
        code, done = self.deliver(wi, "--confirm-base")
        self.assertEqual(code, 0, done)
        self.assertEqual(sh("git", "-C", str(self.remote), "log", "-1", "--format=%s", "main"),
                         f"{wi}: Dana's totals (#{self.pr_number(wi)})", "Scout's subject, not her plain commit title")

    def test_an_old_copy_on_a_newer_branch_stops_as_a_stale_base(self):
        """Dana compared her sandbox with an old main, then edited next to a line another delivery had removed: her
        copy restores that line, and her branch starts after that delivery, so git would let it through."""
        self.team_up()
        old_main = self.main_sha()
        first = self.package("Drop the second comment", "ApexClass:Invoice")
        self.org_write("bob-sbx", CLS, CLASS.format(n=1).replace("    // two\n", ""))
        self.handover(first)
        self.assertEqual(self.deliver(first)[0], 0)
        delivered = self.main_sha()
        wi = self.package("Dana's note", "ApexClass:Invoice", who="ana", owner="Dana")
        old_copy = CLASS.format(n=1).replace("// one", "// one, with Dana's note")  # still has "// two"
        self.dana_commits(wi, {CLS: old_copy}, "a note")
        self.describe(wi, self.item(wi)["description"] + f"\nChecked: {old_main}")
        self.review(wi)
        code, body = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual((code, body.get("needs")), (3, "stale-base"), body)
        self.assertEqual(body["later"][0]["commit"], delivered[:12])
        self.assertIn(first, body["later"][0]["subject"])
        code, plan = self.call("ana", "deliver", "--wi", wi, "--confirm-base")
        self.assertEqual(plan.get("needs"), "deliver-yes", plan)
        self.assertTrue(plan["checks"]["base"]["confirmed"])
        moved = self.package("Dana's reindent", "ApexClass:Invoice", who="ana", owner="Dana")
        self.describe(moved, self.item(moved)["description"] + f"\nChecked: {self.main_sha()}")
        current = self.main_text(CLS).replace("    // one\n", "").replace("Invoice {\n", "Invoice {\n    // one\n", 1)
        self.dana_commits(moved, {CLS: current}, "move a comment to the top")
        self.review(moved)
        code, plan = self.call("ana", "deliver", "--wi", moved)
        self.assertEqual(plan.get("needs"), "deliver-yes", "a move with a current base isn't a stale copy")

    def test_package_check_records_the_base_and_hand_over_needs_it(self):
        self.team_up()
        first = self.package("Invoice totals 16", "ApexClass:Invoice")
        self.build(16)
        self.handover(first)
        self.assertEqual(self.deliver(first)[0], 0)
        self.org_write("bob-sbx", CLS, CLASS.format(n=1))  # his sandbox went back to an old copy
        code, started = self.call("bob", "package", "start", "--title", "Invoice totals 17", "--components", "ApexClass:Invoice")
        self.assertEqual(code, 0, started)
        wi = started["work_item"]
        self.assertEqual(started["base_check"], {"ApexClass:Invoice": "differs"})
        self.assertIsNone(started["checked"])
        self.assertIn("package check", started["next"])
        self.build(17)
        code, body = self.call("bob", "handover", "--wi", wi)
        self.assertEqual(code, 2, body)
        self.assertIn("no Checked line", body["reason"])
        code, body = self.call("bob", "package", "check", "--wi", wi)
        self.assertEqual(code, 2, body)
        self.assertEqual(body["report"], {"ApexClass:Invoice": "differs"})
        self.sync_sandbox(CLS)
        code, body = self.call("bob", "package", "check", "--wi", wi)
        self.assertEqual(code, 0, body)
        self.assertEqual((body["against"], body["checked"]), ("main", self.main_sha()[:12]))
        self.assertIn(f"Checked: {self.main_sha()}", self.item(wi)["description"])
        self.assertIn("Components:", self.item(wi)["description"], "its other lines stay")
        self.build(17)
        self.assertTrue(self.handover(wi)["handed_over"])
        code, done = self.deliver(wi)
        self.assertEqual(code, 0, done)

    # ---- scope, effects and tests ----

    def test_scope_refuses_components_the_work_item_doesnt_name(self):
        self.team_up()
        wi = self.package("Invoice only", "ApexClass:Invoice")
        self.build(7)
        self.handover(wi)
        work = self.bob
        self.git_as("bob", "-C", str(work), "checkout", "--quiet", wi)
        self.write(work, LAYOUT_PATH, LAYOUT.replace("Info", "Sneaked"))
        self.git_as("bob", "-C", str(work), "commit", "--quiet", "-am", f"{wi}: and the layout")
        self.git_as("bob", "-C", str(work), "push", "--quiet", "origin", wi)
        self.git_as("bob", "-C", str(work), "checkout", "--quiet", "main")
        code, body = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual(code, 2, body)
        self.assertIn("doesn't name", body["reason"])

    def test_scope_covers_the_whole_diff(self):
        self.team_up()
        wi = self.package("Invoice and a note", "ApexClass:Invoice", who="ana", owner="Dana")
        self.describe(wi, self.item(wi)["description"] + f"\nChecked: {self.main_sha()}")
        self.dana_commits(wi, {CLS: CLASS.format(n=22), "docs/NOTES.md": "Totals now return 22.\n"}, "totals and notes")
        self.review(wi)
        code, body = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual((code, body.get("needs")), (3, "other-files"), body)
        self.assertEqual(body["files"], ["docs/NOTES.md"])
        code, done = self.deliver(wi, "--confirm-other")
        self.assertEqual(code, 0, done)
        extra = self.package("Invoice and a test folder", "ApexClass:Invoice", who="ana", owner="Dana")
        self.describe(extra, self.item(extra)["description"] + f"\nChecked: {self.main_sha()}")
        self.dana_commits(extra, {CLS: CLASS.format(n=23), "force-app/test/default/classes/Extra.cls": "public class Extra {}\n"},
                          "totals and an extra class")
        self.review(extra)
        code, body = self.call("ana", "deliver", "--wi", extra, "--confirm-other")
        self.assertEqual(code, 2, body)
        self.assertIn("metadata outside force-app/main/default", body["reason"])

    def test_the_test_gate_runs_before_the_merge(self):
        self.team_up()
        self.suites([])
        wi = self.package("Invoice without tests", "ApexClass:Invoice")
        self.build(8)
        self.handover(wi)
        code, body = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual(body.get("needs"), "tests", body)
        self.assertEqual(body["validation"]["stop"], "no-tests")
        self.sync_sandbox(CLS)
        wi2 = self.package("Invoice with its test", "ApexClass:Invoice", "ApexClass:InvoiceTest")
        self.build(9, extra_test=True)
        self.handover(wi2)
        self.options(validate_fails=True)
        code, body = self.call("ana", "deliver", "--wi", wi2)
        self.assertEqual(body.get("needs"), "tests", body)
        self.assertEqual(self.github()["prs"][-1]["state"], "OPEN", "nothing merged")
        self.options(validate_fails=False)
        code, body = self.deliver(wi2)
        self.assertEqual(code, 0, body)
        validations = json.loads((self.stub / "validations.json").read_text())
        self.assertEqual(validations[-1]["tests"], ["InvoiceTest"])
        layout_wi = self.package("Layout only", "Layout:Probe__c-Probe Layout")
        self.org_write("bob-sbx", LAYOUT_PATH, LAYOUT.replace("Info", "Details"))
        self.handover(layout_wi)
        self.assertEqual(self.deliver(layout_wi)[0], 0)
        self.assertTrue(json.loads((self.stub / "validations.json").read_text())[-1]["no_tests"])

    def test_a_stage_suite_that_resolves_to_no_classes_stops_the_delivery(self):
        self.team_up()
        self.suites(["RegressionSuite"])  # assigned to the stage, but in neither the candidate nor the org
        wi = self.package("Invoice totals 24", "ApexClass:Invoice", "ApexClass:InvoiceTest")
        self.build(24, extra_test=True)
        self.handover(wi)
        code, body = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual(body.get("needs"), "tests", body)
        self.assertEqual((body["validation"]["stop"], body["validation"]["missing_suites"]), ("missing-suite", ["RegressionSuite"]),
                         "the package's own tests never stand in for the stage's suite")
        self.suites(["RegressionSuite"], org_suites={"RegressionSuite": ["RegressionTest"]})  # the org's own suite
        code, plan = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual(plan.get("needs"), "deliver-yes", plan)
        self.assertEqual(plan["checks"]["tests"]["tests"], ["InvoiceTest", "RegressionTest"])
        self.suites(["Default Suite"])
        code, body = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual(body["validation"]["missing_suites"], ["Default Suite"], body)

    @unittest.skipUnless(shutil.which("node") and shutil.which("sf"), "the real effect bridge needs node and the sf CLI")
    def test_the_real_effect_bridge_stops_an_aura_bundle_that_drops_a_file(self):
        bundle = {f"force-app/main/default/aura/probe/{name}": f"<!-- {name} -->\n"
                  for name in ("probe.cmp", "probe.cmp-meta.xml", "probeController.js")}
        self.push_to_main(bundle, "an Aura bundle", orgs=("common", "bob-sbx"))
        self.team_up()
        wi = self.package("Aura probe", "AuraDefinitionBundle:probe", who="ana", owner="Dana")
        self.describe(wi, self.item(wi)["description"] + f"\nChecked: {self.main_sha()}")
        self.dana_commits(wi, {"force-app/main/default/aura/probe/probe.cmp": "<!-- probe.cmp, edited -->\n"}, "edit the probe",
                          remove=["force-app/main/default/aura/probe/probeController.js"])
        self.review(wi)
        code, body = self.call("ana", "deliver", "--wi", wi, SCOUT_TEAM_NODE="node")
        self.assertEqual(code, 2, body)
        self.assertIn("would drop probeController.js", body["reason"])

    # ---- sync, promotion, resume and recovery ----

    def test_the_sync_is_retried_and_a_slow_one_stays_pending_until_resumed(self):
        self.team_up()
        self.options(sync_misses=3)
        wi = self.package("Invoice totals 10", "ApexClass:Invoice")
        self.build(10)
        self.handover(wi)
        code, body = self.deliver(wi)
        self.assertEqual(code, 0, body)
        self.options(sync_misses=99)
        wi2 = self.package("Invoice totals 11", "ApexClass:Invoice")
        self.build(11)
        self.handover(wi2)
        code, body = self.deliver(wi2)
        self.assertEqual(code, 1, body)
        self.assertTrue(body.get("pending"))
        self.assertNotIn("return 11;", self.org_read("common", CLS), "nothing deployed")
        self.options(sync_misses=0)
        code, body = self.call("ana", "deliver", "--wi", wi2, "--resume")
        self.assertEqual(code, 0, body)
        self.assertIn("return 11;", self.org_read("common", CLS))

    def test_a_lost_answer_after_submission_is_found_on_the_server_and_never_resubmitted(self):
        self.team_up()
        wi = self.package("Invoice totals 12", "ApexClass:Invoice")
        self.build(12)
        self.handover(wi)
        self.options(complete_crash_once=True)
        code, body = self.deliver(wi)
        self.assertEqual(code, 0, body)
        self.assertEqual(body["outcome"], "verified")
        self.assertEqual(len(self.hub()["promotions"]), 1, "one promotion, never a second")

    def test_a_failed_promotion_blocks_the_stage_until_retried(self):
        self.team_up()
        self.options(promotion_fails=True)
        wi = self.package("Invoice totals 13", "ApexClass:Invoice")
        self.build(13)
        self.handover(wi)
        code, body = self.deliver(wi)
        self.assertEqual(code, 1, body)
        self.assertIn("stage stays blocked", body["reason"])
        self.assertTrue(body.get("retry"))
        self.options(promotion_fails=False)
        wi2 = self.package("Layout tweak", "Layout:Probe__c-Probe Layout")
        self.org_write("bob-sbx", LAYOUT_PATH, LAYOUT.replace("Info", "Tweak"))
        self.handover(wi2)
        code, body = self.call("ana", "deliver", "--wi", wi2)
        self.assertEqual(code, 2, body)
        self.assertIn("unresolved work", body["reason"])
        code, flow = self.call("ana", "backflow", "--components", "ApexClass:Invoice", "--yes")
        self.assertEqual(code, 2, flow)
        self.assertIn("undeployed merge", flow["reason"])
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual(code, 1, body)
        self.assertIn("--retry", body["reason"])
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume", "--retry")
        self.assertEqual(code, 0, body)
        self.assertIn("return 13;", self.org_read("common", CLS))
        self.assertEqual([p["status"] for p in self.hub()["promotions"]], ["ERROR", "SUCCESS"])
        self.assertEqual(self.deliver(wi2)[0], 0, "the stage is free again")

    def test_a_promotion_completed_in_lifecycle_center_is_read_back_and_its_record_is_the_reference(self):
        self.team_up()
        self.options(promotion_fails=True)
        wi = self.package("Invoice totals 25", "ApexClass:Invoice")
        self.build(25)
        self.handover(wi)
        self.assertEqual(self.deliver(wi)[0], 1)
        self.options(promotion_fails=False)
        answer = self.sf_stub("devops", "promotion", "complete", "--target-stage-id", STAGE18, "--work-item-id",
                              self.item(wi)["id"][:15], "--test-level", "NoTestRun")  # the captain's button in the UI
        self.assertEqual(answer["status"], 0, answer)
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual((code, body.get("outcome")), (0, "verified"), body)
        shutil.rmtree(self.cache() / "baselines")  # only the platform's record says what it delivered now
        wi2 = self.package("Invoice totals 26", "ApexClass:Invoice")
        self.build(26)
        self.handover(wi2)
        code, plan = self.call("ana", "deliver", "--wi", wi2)
        self.assertEqual(plan.get("needs"), "deliver-yes", plan)
        self.assertIn(f"{wi} delivered it", plan["checks"]["direct_edits"]["ApexClass:Invoice"]["reference"])

    def test_resume_checks_a_merge_scout_didnt_plan_before_anything_deploys(self):
        self.team_up()
        wi = self.package("Invoice totals 18", "ApexClass:Invoice")
        self.build(18)
        self.handover(wi)
        merged = self.gh_stub("pr", "merge", str(self.pr_number(wi)), "--repo", "acme/team", "--squash")  # GitHub's button
        self.assertEqual(merged.returncode, 0, merged.stderr)
        code, body = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual(code, 2, body)
        self.assertIn("--resume", body["reason"])
        code, plan = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual((code, plan.get("needs")), (3, "deliver-yes"), plan)
        self.assertIn("no approved plan", plan["reason"])
        self.assertTrue(plan["resume"])
        self.assertNotIn("return 18;", self.org_read("common", CLS), "nothing deployed without the yes")
        record = lc.record_path(TEAM_ID, wi)
        stale = {"plan_id": "abc", "validated": {"tests": ["InvoiceTest"]}, "head": "0" * 40, "base": "0" * 40, "tree": "0" * 40}
        path = self.cache() / "deliveries" / record.name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stale))
        code, plan = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertIn("isn't the revision Scout checked", plan["reason"])
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume", "--yes", "--plan-id", plan["plan_id"])
        self.assertEqual(code, 0, done)
        self.assertIn("return 18;", self.org_read("common", CLS))

    def test_resume_stops_on_a_work_item_state_it_doesnt_expect(self):
        self.team_up()
        wi = self.package("Invoice totals 19", "ApexClass:Invoice")
        self.build(19)
        self.handover(wi)
        self.gh_stub("pr", "merge", str(self.pr_number(wi)), "--repo", "acme/team", "--squash")
        data = self.hub()
        data["items"][wi]["status"] = "CLOSED"  # closed in Lifecycle Center without a promotion
        (self.stub / "lc-state.json").write_text(json.dumps(data))
        code, plan = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual(plan.get("needs"), "deliver-yes", plan)
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume", "--yes", "--plan-id", plan["plan_id"])
        self.assertEqual(code, 1, body)
        self.assertTrue(body.get("pending"))
        self.assertIn("CLOSED on the server", body["reason"])
        self.assertEqual(self.hub()["promotions"], [], "nothing was promoted")

    def test_changes_on_main_no_promotion_delivered_are_never_taken_for_delivered(self):
        self.team_up()
        first = self.package("Layout first", "Layout:Probe__c-Probe Layout")
        self.org_write("bob-sbx", LAYOUT_PATH, LAYOUT.replace("Info", "First"))
        self.handover(first)
        self.assertEqual(self.deliver(first)[0], 0)
        pushed = self.push_to_main({LAYOUT_PATH: self.main_text(LAYOUT_PATH).replace("First", "Pushed")}, "a layout straight onto main")
        self.sync_sandbox(LAYOUT_PATH)
        wi = self.package("Layout second", "Layout:Probe__c-Probe Layout")
        self.org_write("bob-sbx", LAYOUT_PATH, self.main_text(LAYOUT_PATH).replace("<showHighlightsPanel>false", "<showHighlightsPanel>true"))
        self.handover(wi)
        code, body = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual(body.get("needs"), "direct-edit", body)
        edit = body["edits"]["Layout:Probe__c-Probe Layout"]
        self.assertEqual((edit["state"], edit["later"]), ("main-ahead", [pushed[:12]]))

    # ---- verification, updates and the watcher ----

    def test_a_verification_comment_github_didnt_take_is_sent_once_later(self):
        self.team_up()
        self.options(comment_fails=1, comment_answer_lost=1)
        wi = self.package("Invoice totals 27", "ApexClass:Invoice")
        self.build(27)
        self.handover(wi)
        code, body = self.deliver(wi)
        self.assertEqual(code, 0, body)
        self.assertTrue(body["comment"].startswith("pending"), body)
        code, status = self.call("ana", "status")  # GitHub posts it, but its answer is lost
        self.assertEqual(len(status["unsent_comments"]), 1, status)
        code, status = self.call("ana", "status")  # found on the pull request: not posted twice
        self.assertEqual(status["unsent_comments"], [], status)
        verified = [c for c in self.github()["comments"] if c["body"].startswith("Verified in the common org at")]
        self.assertEqual(len(verified), 1)
        code, again = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual((again["outcome"], again["comment"]), ("verified", "sent"))

    def test_updates_come_from_the_cache_and_only_the_read_back_says_verified(self):
        self.team_up()
        wi = self.package("Invoice totals 14", "ApexClass:Invoice")
        self.build(14)
        self.handover(wi)
        self.assertEqual(self.deliver(wi)[0], 0)
        self.options(promotion_fails=True)
        wi2 = self.package("Layout tweak", "Layout:Probe__c-Probe Layout")
        self.org_write("bob-sbx", LAYOUT_PATH, LAYOUT.replace("Info", "Tweak"))
        self.handover(wi2)
        self.assertEqual(self.deliver(wi2)[0], 1)
        code, body = self.call("bob", "fetch")
        self.assertEqual(code, 0, body)
        self.assertGreater(body["fresh"], 0)
        text = self.hook("bob")
        self.assertIn("Verified in the common org at", text)
        self.assertIn("the platform finished its promotion", text)
        self.assertIn(f"{wi2}: its promotion ended error", text)
        self.assertIn(f"pull request #{self.pr_number(wi)} ({wi}) is merged into main", text)
        self.assertNotIn(f"{wi2}: the platform reports", text)

    def test_the_watcher_keeps_events_until_scout_acknowledges_them(self):
        self.team_up()
        wi = self.package("Invoice totals 28", "ApexClass:Invoice")
        self.build(28)
        self.handover(wi)
        self.assertEqual(self.deliver(wi)[0], 0)
        code, report = self.call("bob", "watch", "--interval", "0", "--max-hours", "0.001")
        self.assertIn("Verified in the common org at", report)
        self.assertIn("ack --team lc-acme-team --upto", report)
        upto = int(report.rsplit("--upto ", 1)[1].split("`")[0])
        events = json.loads((self.cache("bob") / "lc-events.json").read_text())
        self.assertTrue(events["pending"], "reported, not yet relayed: still pending")
        code, quiet = self.call("bob", "watch", "--interval", "0", "--max-hours", "0.0003")
        self.assertIn("without news", quiet, "a new watcher doesn't wake for what it already reported")
        code, body = self.call("bob", "ack", "--upto", upto)
        self.assertEqual(code, 0, body)
        self.assertEqual(body["pending"], 0)
        self.assertEqual(self.hook("bob").strip(), "")

    def test_comment_pages_and_independent_cursors_never_skip_a_verification(self):
        self.team_up()
        data = self.github()
        at = team.now()
        data["comments"] = [{"id": n, "pr": 99, "body": f"review note {n}", "user": {"login": "rev"}, "created_at": at,
                             "updated_at": at} for n in range(1, 121)]
        (self.stub / "lc-gh.json").write_text(json.dumps(data))
        wi = self.package("Invoice totals 29", "ApexClass:Invoice")
        self.build(29)
        self.handover(wi)
        self.assertEqual(self.deliver(wi)[0], 0)
        self.package("A later work item", "ApexClass:InvoiceTest")  # the hub moves on after the verification
        self.assertEqual(self.call("bob", "fetch")[0], 0)
        self.assertEqual(self.call("bob", "fetch")[0], 0)
        events = json.loads((self.cache("bob") / "lc-events.json").read_text())
        verified = [e for e in events["pending"] if e["key"].startswith("verified:")]
        self.assertEqual(len(verified), 1, events["pending"])
        pages = [json.loads(l) for l in (self.stub / "gh-calls.log").read_text().splitlines() if "issues/comments" in l]
        self.assertTrue(any("page=2" in c[1] for c in pages), "the second page was read")

    # ---- the final review's cases ----

    def test_an_unreadable_org_copy_is_never_approved_or_backed_up(self):
        self.team_up()
        wi = self.package("Invoice totals 30", "ApexClass:Invoice")
        self.build(30)
        self.handover(wi)
        self.options(retrieve_unreadable=["ApexClass:Invoice"])
        for extra in ((), ("--overwrite",)):
            code, body = self.call("ana", "deliver", "--wi", wi, *extra)
            self.assertEqual(code, 2, body)
            self.assertIn("couldn't read the common org's copy", body["reason"])
        self.assertEqual(self.github()["prs"][0]["state"], "OPEN", "nothing merged")
        self.options(retrieve_unreadable=[], sync_misses=99)
        code, plan = self.call("ana", "deliver", "--wi", wi)
        code, body = self.call("ana", "deliver", "--wi", wi, "--yes", "--plan-id", plan["plan_id"])
        self.assertTrue(body.get("pending"), body)
        self.options(retrieve_unreadable=["ApexClass:Invoice"], sync_misses=0)
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume", "--overwrite")
        self.assertEqual(code, 1, body)
        self.assertTrue(body.get("pending"))
        self.assertIn("just before the promotion", body["reason"])
        self.assertEqual(self.submitted(), [], "nothing promoted over a copy nobody could read")
        self.options(retrieve_unreadable=[])
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual(code, 0, done)

    def test_a_two_parent_merge_the_platform_delivered_stays_the_reference(self):
        self.team_up()
        wi = self.package("Layout by merge commit", "Layout:Probe__c-Probe Layout")
        self.org_write("bob-sbx", LAYOUT_PATH, LAYOUT.replace("Info", "Merged"))
        self.handover(wi)
        merged = self.gh_stub("pr", "merge", str(self.pr_number(wi)), "--repo", "acme/team", "--merge")  # GitHub's merge commit
        self.assertEqual(merged.returncode, 0, merged.stderr)
        merge = self.main_sha()
        self.assertEqual(len(sh("git", "-C", str(self.remote), "rev-list", "--parents", "-n", "1", merge).split()), 3)
        self.sf_stub("devops", "work-item", "update", "--work-item-name", wi, "--status", "Ready to Promote")
        self.sf_stub("devops", "promotion", "validate", "--target-stage-id", STAGE18, "--work-item-id", self.item(wi)["id"][:15])
        self.sf_stub("devops", "promotion", "validate", "--target-stage-id", STAGE18, "--work-item-id", self.item(wi)["id"][:15])
        answer = self.sf_stub("devops", "promotion", "complete", "--target-stage-id", STAGE18, "--work-item-id",
                              self.item(wi)["id"][:15], "--test-level", "NoTestRun")  # completed in Lifecycle Center
        self.assertEqual(answer["status"], 0, answer)
        self.assertEqual(self.hub()["promotions"][-1]["merge"], merge)
        pushed = self.push_to_main({LAYOUT_PATH: self.main_text(LAYOUT_PATH).replace("Merged", "Pushed")}, "a layout straight onto main")
        self.sync_sandbox(LAYOUT_PATH)
        second = self.package("Layout highlights", "Layout:Probe__c-Probe Layout")
        self.org_write("bob-sbx", LAYOUT_PATH, self.main_text(LAYOUT_PATH).replace("<showHighlightsPanel>false", "<showHighlightsPanel>true"))
        self.handover(second)
        code, body = self.call("ana", "deliver", "--wi", second)
        self.assertEqual(body.get("needs"), "direct-edit", body)
        edit = body["edits"]["Layout:Probe__c-Probe Layout"]
        self.assertEqual((edit["state"], edit["later"]), ("main-ahead", [pushed[:12]]))
        self.assertIn(f"{merge[:12]} ({wi} delivered it)", edit["reference"])

    def test_a_restored_deleted_file_is_a_stale_base(self):
        bundle = {f"force-app/main/default/aura/probe/{name}": f"<!-- {name} -->\n"
                  for name in ("probe.cmp", "probe.cmp-meta.xml", "probeHelper.js")}
        self.push_to_main(bundle, "an Aura bundle", orgs=("common", "bob-sbx"))
        old_main = self.main_sha()
        self.push_to_main({}, "the helper goes", orgs=("common",), remove=["force-app/main/default/aura/probe/probeHelper.js"])
        removed = self.main_sha()
        self.team_up()
        wi = self.package("Probe edit", "AuraDefinitionBundle:probe", who="ana", owner="Dana")
        self.describe(wi, self.item(wi)["description"] + f"\nChecked: {old_main}")
        self.dana_commits(wi, {"force-app/main/default/aura/probe/probe.cmp": "<!-- probe.cmp, edited -->\n",
                               "force-app/main/default/aura/probe/probeHelper.js": "<!-- probeHelper.js -->\n"},
                          "edit the probe (an old copy with its helper)")
        self.review(wi)
        code, body = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual((code, body.get("needs")), (3, "stale-base"), body)
        self.assertEqual(body["later"][0]["commit"], removed[:12])

    def test_package_check_never_certifies_a_base_from_the_builders_own_branch(self):
        self.team_up()
        first = self.package("Invoice totals 31", "ApexClass:Invoice")
        self.build(31)
        self.handover(first)
        self.assertEqual(self.deliver(first)[0], 0)
        wi = self.package("Invoice note", "ApexClass:Invoice")  # checked against main at its start
        self.org_write("bob-sbx", CLS, CLASS.format(n=1).replace("// one", "// one, noted"))  # an old copy, edited
        self.handover(wi)
        code, body = self.call("bob", "package", "check", "--wi", wi)  # the sandbox matches its own branch
        self.assertEqual(code, 2, body)
        self.assertEqual(body["report"], {"ApexClass:Invoice": "differs"})
        self.assertIn("tell the captain", body["reason"])
        self.assertEqual(self.item(wi)["description"].count("Checked:"), 1, "the base it had stays")

    def test_metadata_of_a_package_directory_the_merge_removes_is_still_metadata(self):
        project = {"packageDirectories": [{"path": "force-app", "default": True}, {"path": "extra"}], "sourceApiVersion": "64.0"}
        self.push_to_main({"sfdx-project.json": json.dumps(project), "extra/main/default/classes/Extra.cls": "public class Extra {}\n"},
                          "a second package directory")
        self.team_up()
        wi = self.package("Invoice and a tidy-up", "ApexClass:Invoice", who="ana", owner="Dana")
        self.describe(wi, self.item(wi)["description"] + f"\nChecked: {self.main_sha()}")
        project["packageDirectories"] = project["packageDirectories"][:1]
        self.dana_commits(wi, {CLS: CLASS.format(n=32), "sfdx-project.json": json.dumps(project)}, "drop the extra directory",
                          remove=["extra/main/default/classes/Extra.cls"])
        self.review(wi)
        code, body = self.call("ana", "deliver", "--wi", wi, "--confirm-other")
        self.assertEqual(code, 2, body)
        self.assertIn("extra/main/default/classes/Extra.cls", body["reason"])

    def test_a_comment_is_posted_only_after_the_pull_request_was_read(self):
        self.team_up()
        self.options(pr_view_fails=1)
        wi = self.package("Invoice totals 33", "ApexClass:Invoice")
        self.build(33)
        self.handover(wi)
        code, body = self.deliver(wi)
        self.assertEqual(code, 0, body)
        self.assertTrue(body["comment"].startswith("pending"), "the read failed, so nothing was posted")
        self.assertEqual([c for c in self.github()["comments"] if c["body"].startswith("Verified")], [])
        self.assertEqual(self.call("ana", "status")[1]["unsent_comments"], [])
        wi2 = self.package("Invoice totals 34", "ApexClass:Invoice")
        self.build(34)
        self.handover(wi2)
        real = lc.write_record
        def full_disk(team_id, wi_name, fresh=False, **changes):
            if (changes.get("comment") or {}).get("sent") and not getattr(full_disk, "hit", False):
                full_disk.hit = True
                raise OSError(28, "No space left on device")
            return real(team_id, wi_name, fresh=fresh, **changes)
        with mock.patch.object(lc, "write_record", full_disk), self.assertRaises(OSError):
            self.deliver(wi2)  # GitHub took the comment; recording that failed
        self.assertEqual(self.call("ana", "status")[1]["unsent_comments"], [])
        verified = [c for c in self.github()["comments"] if c["body"].startswith("Verified")]
        self.assertEqual(len(verified), 2, "one comment per delivery, never two")

    def test_a_verification_in_the_cursors_own_second_is_still_seen(self):
        self.team_up()
        data = self.github()
        data["comments"] = [{"id": 1, "pr": 99, "body": "review note", "user": {"login": "rev"},
                             "created_at": "2099-01-01T10:00:00Z", "updated_at": "2099-01-01T10:00:00Z"}]
        (self.stub / "lc-gh.json").write_text(json.dumps(data))
        self.assertEqual(self.call("bob", "fetch")[0], 0)  # the comments cursor is now 10:00:00
        data = self.github()
        data["comments"].append({"id": 2, "pr": 1, "body": "Verified in the common org at abc: ApexClass:Invoice (Scout's read-back).",
                                 "user": {"login": "stub-captain"}, "created_at": "2099-01-01T10:00:00Z", "updated_at": "2099-01-01T10:00:00Z"})
        (self.stub / "lc-gh.json").write_text(json.dumps(data))
        self.assertEqual(self.call("bob", "fetch")[0], 0)
        self.assertEqual(self.call("bob", "fetch")[0], 0)
        events = json.loads((self.cache("bob") / "lc-events.json").read_text())
        self.assertEqual([e["key"] for e in events["pending"] if e["key"].startswith("verified:")], ["verified:2"])

    def test_pull_request_updates_follow_reopens_and_older_reviews(self):
        self.team_up()
        wi = self.package("Invoice totals 35", "ApexClass:Invoice")
        self.build(35)
        self.handover(wi)
        number = self.pr_number(wi)
        self.assertEqual(self.call("bob", "fetch")[0], 0)  # it's open
        def set_state(pr_number, state, at):
            data = self.github()
            for pr in data["prs"]:
                if pr["number"] == pr_number:
                    pr.update(state=state, updatedAt=at)
            (self.stub / "lc-gh.json").write_text(json.dumps(data))
        for state, at in (("CLOSED", "2099-01-01T10:00:01Z"), ("OPEN", "2099-01-01T10:00:02Z")):
            set_state(number, state, at)
            self.assertEqual(self.call("bob", "fetch")[0], 0)
        data = self.github()
        data["prs"] += [{"number": n, "head": f"WI-9{n:05d}", "base": "main", "state": "OPEN", "title": f"busy {n}",
                         "mergeCommit": None, "updatedAt": f"2099-01-01T10:01:{n - 100:02d}Z", "author": "rev"} for n in range(100, 156)]
        (self.stub / "lc-gh.json").write_text(json.dumps(data))
        self.assertEqual(self.call("bob", "fetch")[0], 0)
        set_state(number, "MERGED", "2099-01-01T10:02:00Z")  # the oldest review completes after 56 newer ones
        self.assertEqual(self.call("bob", "fetch")[0], 0)
        self.assertEqual(self.call("bob", "fetch")[0], 0)
        events = json.loads((self.cache("bob") / "lc-events.json").read_text())
        mine = [e["key"].split(":")[2] for e in events["pending"] if e["key"].startswith(f"pr:{number}:")]
        self.assertEqual(mine, ["OPEN", "CLOSED", "OPEN", "MERGED"], events["pending"])

    def test_a_promotion_that_resolves_no_components_recovers_with_a_checked_full_promotion(self):
        """A fault measured live: the default mode resolves no components for a merged item whose files are on main,
        in the UI too, and a retry fails the same way. A full promotion (--deploy-all) deploys everything on main, so
        every component there is checked against the org first, and the yes binds to all of them."""
        self.team_up()
        self.options(empty_set=True)
        wi = self.package("Invoice totals 40", "ApexClass:Invoice")
        self.build(40)
        self.handover(wi)
        code, body = self.deliver(wi)
        self.assertEqual(code, 1, body)
        self.assertTrue(body.get("full"), body)
        self.assertIn("--resume --full", body["reason"])
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume", "--retry")
        self.assertEqual(code, 1, body)
        self.assertIn("resolved no components", body["reason"])
        self.org_write("common", LAYOUT_PATH, LAYOUT.replace("<label>Info</label>", "<label>Edited</label>"), saved=True)
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume", "--full")
        self.assertEqual((code, body.get("needs")), (3, "direct-edit"), body)
        self.assertEqual(list(body["edits"]), ["Layout:Probe__c-Probe Layout"], "a component this work item doesn't touch")
        self.org_write("common", LAYOUT_PATH, LAYOUT, saved=True)
        code, ask = self.call("ana", "deliver", "--wi", wi, "--resume", "--full")
        self.assertEqual((code, ask.get("needs")), (3, "full-yes"), ask)
        self.assertTrue({"ApexClass:Invoice", "Layout:Probe__c-Probe Layout"} <= set(ask["components"]), ask["components"])
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume", "--full", "--yes", "--plan-id", ask["plan_id"])
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertIn("return 40;", self.org_read("common", CLS))
        self.assertTrue(self.hub()["promotions"][-1]["deploy_all"])
        self.assertIn("ApexClass:InvoiceTest", done["components"], "the read-back covers everything it deployed")
        self.assertEqual([p["status"] for p in self.hub()["promotions"]], ["ERROR", "ERROR", "SUCCESS"])

    def test_a_full_promotion_refuses_when_main_moved_after_the_merge(self):
        self.team_up()
        self.options(empty_set=True)
        wi = self.package("Invoice totals 41", "ApexClass:Invoice")
        self.build(41)
        self.handover(wi)
        self.assertEqual(self.deliver(wi)[0], 1)
        self.push_to_main({LAYOUT_PATH: LAYOUT.replace("Info", "Later")}, "a later layout change")
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume", "--full")
        self.assertEqual(code, 2, body)
        self.assertIn("after this merge", body["reason"])
        self.assertEqual(len(self.hub()["promotions"]), 1, "nothing promoted")

    def empty_set_item(self, n):
        """A delivery whose default-mode promotion resolved no components, waiting for the full promotion."""
        self.team_up()
        self.options(empty_set=True)
        wi = self.package(f"Invoice totals {n}", "ApexClass:Invoice")
        self.build(n)
        self.handover(wi)
        code, body = self.deliver(wi)
        self.assertEqual((code, body.get("full")), (1, True), body)
        return wi

    def full_ask(self, wi, *extra):
        code, ask = self.call("ana", "deliver", "--wi", wi, "--resume", "--full", *extra)
        self.assertEqual((code, ask.get("needs")), (3, "full-yes"), ask)
        return ask

    def test_a_full_promotion_stops_when_main_moves_during_the_final_call(self):
        """A teammate merges on GitHub while the captain's final call reads the org: the full promotion would deploy
        that merge unchecked, so nothing is submitted."""
        wi = self.empty_set_item(42)
        ask = self.full_ask(wi)
        extra = "force-app/main/default/classes/Teammate.cls"
        original, pushed = lc.read_org, []
        def merge_while_reading(*args, **kwargs):
            found = original(*args, **kwargs)
            if not pushed:
                pushed.append(self.push_to_main({extra: "public class Teammate {}\n", extra + "-meta.xml": META}, "a teammate"))
            return found
        with mock.patch.object(lc, "read_org", side_effect=merge_while_reading):
            code, body = self.call("ana", "deliver", "--wi", wi, "--resume", "--full", "--yes", "--plan-id", ask["plan_id"])
        self.assertEqual(code, 1, body)
        self.assertIn("main moved while Scout checked", body["reason"])
        self.assertEqual([p["deploy_all"] for p in self.hub()["promotions"]], [False], "nothing more was submitted")
        self.assertFalse((self.stub / "orgs" / "common" / "classes" / "Teammate.cls").exists())

    def test_a_full_promotion_isnt_verified_when_main_moved_while_it_ran(self):
        wi = self.empty_set_item(43)
        ask = self.full_ask(wi)
        extra = "force-app/main/default/classes/Teammate.cls"
        original, calls = lc.read_org, []
        def merge_during_the_read_back(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:  # the check, then the read-back
                self.push_to_main({extra: "public class Teammate {}\n", extra + "-meta.xml": META}, "a teammate")
            return original(*args, **kwargs)
        with mock.patch.object(lc, "read_org", side_effect=merge_during_the_read_back):
            code, body = self.call("ana", "deliver", "--wi", wi, "--resume", "--full", "--yes", "--plan-id", ask["plan_id"])
        self.assertEqual(code, 1, body)
        self.assertIn("main moved while it ran", body["reason"])
        self.assertEqual([p["deploy_all"] for p in self.hub()["promotions"]], [False, True])

    def test_a_full_promotion_refuses_files_scout_cant_check(self):
        """A second package directory and an unmapped type both go out with --deploy-all; Scout can't check them."""
        project = {"packageDirectories": [{"path": "force-app", "default": True}, {"path": "other-app"}], "sourceApiVersion": "64.0"}
        self.push_to_main({"sfdx-project.json": json.dumps(project),
                           "other-app/main/default/classes/Other.cls": "public class Other {}\n",
                           "other-app/main/default/classes/Other.cls-meta.xml": META,
                           "force-app/main/default/staticresources/Logo.resource": "image bytes\n",
                           "force-app/main/default/staticresources/Logo.resource-meta.xml": "<StaticResource/>\n"}, "more metadata")
        wi = self.empty_set_item(44)
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume", "--full")
        self.assertEqual(code, 2, body)
        self.assertIn("can't check these files", body["reason"])
        self.assertTrue({"other-app/main/default/classes/Other.cls",
                         "force-app/main/default/staticresources/Logo.resource"} <= set(body["unchecked"]), body["unchecked"])
        self.assertEqual(len(self.hub()["promotions"]), 1, "nothing more was submitted")

    def test_a_failed_full_promotion_retries_in_full(self):
        wi = self.empty_set_item(45)
        ask = self.full_ask(wi)
        self.options(promotion_fails=True)
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume", "--full", "--yes", "--plan-id", ask["plan_id"])
        self.assertEqual(code, 1, body)
        self.assertIn("--resume --retry", body["reason"])
        self.options(promotion_fails=False)
        code, again = self.call("ana", "deliver", "--wi", wi, "--resume", "--retry")
        self.assertEqual((code, again.get("needs")), (3, "full-yes"), "the retry keeps the full mode and asks again")
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume", "--retry", "--yes", "--plan-id", again["plan_id"])
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertEqual([p["deploy_all"] for p in self.hub()["promotions"]], [False, True, True])

    def test_two_merged_items_get_one_way_out_of_the_full_promotion(self):
        """The first waits for a full promotion while a teammate merges the second on GitHub: the full promotion won't
        carry the second unchecked, and the merge order holds the second back, so the answer names the way out."""
        self.team_up()
        self.options(empty_set=True)
        wi = self.package("Invoice first", "ApexClass:Invoice")
        self.build(46)
        self.handover(wi)
        later = self.package("Layout second", "Layout:Probe__c-Probe Layout")
        self.org_write("bob-sbx", LAYOUT_PATH, LAYOUT.replace("Info", "Later"))
        self.handover(later)
        self.assertEqual(self.deliver(wi)[0], 1)
        merged = self.gh_stub("pr", "merge", str(self.pr_number(later)), "--repo", "acme/team", "--squash")
        self.assertEqual(merged.returncode, 0, merged.stderr)
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume", "--full")
        self.assertEqual(code, 2, body)
        self.assertEqual(body["waiting"], [later])
        self.assertIn("All changes in the stage branch", body["reason"])
        self.assertNotIn("deliver those first", body["reason"])
        self.assertEqual(len(self.hub()["promotions"]), 1)

    def test_resume_full_after_a_full_promotion_in_the_ui_reads_everything_back(self):
        wi = self.empty_set_item(47)
        self.sf_stub("devops", "promotion", "complete", "--target-stage-id", "1QV000000000001AAA",
                     "--work-item-id", self.item(wi)["id"][:15], "--deploy-all", "--test-level", "NoTestRun")
        self.org_write("common", LAYOUT_PATH, LAYOUT.replace("Info", "Edited after"), saved=True)
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume", "--full")
        self.assertEqual(code, 1, body)
        self.assertIn("don't match main", body["reason"])
        self.assertIn("Layout:Probe__c-Probe Layout", body["reason"])
        self.org_write("common", LAYOUT_PATH, LAYOUT, saved=True)
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume", "--full")
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertIn("Layout:Probe__c-Probe Layout", done["components"], "everything on main, not only the work item")

    def test_a_new_component_added_in_separate_commits_is_flagged_before_the_merge(self):
        """Measured 19 Oct: Lifecycle Center's default promotion resolves no components for a new component whose files
        came in separate commits (the class, then its meta file); one commit with both deploys. The plan says so."""
        self.team_up()
        split = "force-app/main/default/classes/Split.cls"
        wi = self.package("A new class in two commits", "ApexClass:Split", who="ana", owner="Dana")
        self.dana_commits(wi, {split: "public with sharing class Split {}\n"}, "the class")
        self.dana_commits(wi, {split + "-meta.xml": META}, "its meta file")
        self.review(wi)
        code, body = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual(code, 3, body)
        self.assertEqual(body.get("split_new"), ["ApexClass:Split"], body)
        whole = "force-app/main/default/classes/Whole.cls"
        together = self.package("A new class in one commit", "ApexClass:Whole", who="ana", owner="Dana")
        self.dana_commits(together, {whole: "public with sharing class Whole {}\n", whole + "-meta.xml": META}, "the class")
        self.review(together)
        code, body = self.call("ana", "deliver", "--wi", together)
        self.assertEqual(code, 3, body)
        self.assertNotIn("split_new", body)

    def skipped_tests_delivery(self, n, **options):
        """A delivery whose check-only validation compiled but ran none of its tests (measured 19 Oct), merged and
        promoted on the captain's explicit --tests-after yes; Scout then runs the owed tests itself. Returns the work
        item and the last answer."""
        self.team_up()
        self.options(deploy_runs_no_tests=True, **options)
        wi = self.package(f"Invoice totals {n}", "ApexClass:Invoice")
        self.build(n)
        self.handover(wi)
        code, body = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual((code, body.get("needs")), (3, "tests-after"), body)
        self.assertEqual(body["tests"], ["InvoiceTest"])
        code, plan = self.call("ana", "deliver", "--wi", wi, "--tests-after")
        self.assertEqual((code, plan.get("needs")), (3, "deliver-yes"), plan)
        self.assertEqual(plan["tests_after"], ["InvoiceTest"])
        return wi, self.call("ana", "deliver", "--wi", wi, "--tests-after", "--yes", "--plan-id", plan["plan_id"])

    def verified_comments(self):
        return [c["body"] for c in self.github()["comments"] if "Verified" in c.get("body", "")]

    def test_tests_the_platform_skipped_at_deploy_time_run_after_the_promotion(self):
        wi, (code, done) = self.skipped_tests_delivery(48)
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertEqual(done["tests"], ["InvoiceTest"])
        self.assertIn("return 48;", self.org_read("common", CLS), "promoted")
        runs = self.hub()["test_runs"]
        self.assertEqual([r["results"][0]["ApexClass"]["Name"] for r in runs.values()], ["InvoiceTest"], "Scout's own run")
        comments = self.verified_comments()
        self.assertEqual(len(comments), 1, comments)
        self.assertIn("Tests passed in the common org after the promotion: InvoiceTest", comments[0])

    def test_a_test_that_fails_after_the_promotion_says_not_verified(self):
        wi, (code, body) = self.skipped_tests_delivery(49, tests_fail_after=["InvoiceTest"])
        self.assertEqual(code, 1, body)
        self.assertTrue(body["reason"].startswith("not verified: tests failed"), body["reason"])
        self.assertIn("InvoiceTest.run", body["reason"])
        self.assertTrue(any(c.startswith("a fix") for c in body["choices"]) and any("revert" in c for c in body["choices"]), body)
        self.assertEqual(self.verified_comments(), [], "nothing claimed")
        code, again = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual((code, again["reason"]), (1, body["reason"]), "a fresh session hears the same failure")
        self.assertEqual(again["choices"][:2], body["choices"][:2])
        self.options(tests_fail_after=[])
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume", "--retry")
        self.assertEqual((code, done.get("outcome")), (0, "verified"), "a new run of the whole classes")
        self.assertEqual(len(self.hub()["test_runs"]), 2)

    def test_a_lost_record_still_owes_its_tests(self):
        wi, (code, body) = self.skipped_tests_delivery(50, tests_dont_start=True)
        self.assertEqual((code, body.get("pending")), (1, True), body)
        (self.cache() / "deliveries" / f"{wi}.json").unlink()
        self.options(tests_dont_start=False)
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertEqual(done["tests"], ["InvoiceTest"], "rebuilt from the suite and the package")
        self.assertEqual(len(self.hub()["test_runs"]), 1, "and actually run")

    def test_the_tests_dont_count_when_the_org_changed_during_the_run(self):
        wi, (code, body) = self.skipped_tests_delivery(51, tests_edit_org=True)
        self.assertEqual(code, 1, body)
        self.assertTrue(body["reason"].startswith("not verified: the tests passed, but"), body["reason"])
        self.assertIn("ApexClass:Invoice", body["reason"])
        self.assertEqual(self.verified_comments(), [])

    def test_a_rebound_common_org_alias_stops_the_test_run(self):
        wi, (code, body) = self.skipped_tests_delivery(52, tests_dont_start=True)
        self.assertEqual(code, 1, body)
        self.options(tests_dont_start=False, rebind={"common": "00D000000000009"})
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual(code, 2, body)
        self.assertIn("now names org 00D000000000009", body["reason"])
        self.assertNotIn("test_runs", self.hub(), "no test ran in the other org")
        self.assertEqual(self.verified_comments(), [])

    def test_the_strict_test_gate_stays_unless_the_validation_proves_the_tests_were_skipped(self):
        self.team_up()
        self.options(validate_fails=True)
        wi = self.package("Invoice totals 53", "ApexClass:Invoice")
        self.build(53)
        self.handover(wi)
        for extra in ([], ["--tests-after"]):
            code, body = self.call("ana", "deliver", "--wi", wi, *extra)
            self.assertEqual((code, body.get("needs")), (3, "tests"), body)
        self.assertEqual(self.hub()["promotions"], [], "nothing merged or promoted")

    def plain_delivery(self, n):
        self.team_up()
        wi = self.package(f"Invoice totals {n}", "ApexClass:Invoice")
        self.build(n)
        self.handover(wi)
        return wi

    def test_a_component_list_from_before_the_merge_still_gets_a_sync_after_it(self):
        """Measured 19 Oct (WI-000026): the hub can make the head's component list before the merge, and `complete`
        is refused until a validation inspects the merge itself."""
        self.options(list_at_review=True)
        wi = self.plain_delivery(54)
        self.assertTrue(self.hub()["lists"], "a list from before the merge")
        code, done = self.deliver(wi)
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertEqual([p["status"] for p in self.hub()["promotions"]], ["SUCCESS"], "never refused")

    def test_a_refused_promotion_is_synced_and_tried_once_more(self):
        self.options(refuse_complete=1)
        wi = self.plain_delivery(55)
        code, done = self.deliver(wi)
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertEqual([p["status"] for p in self.hub()["promotions"]], ["SUCCESS"], "the merge's record, filled in")

    def test_a_promotion_refused_twice_leaves_nothing_to_wait_for(self):
        """The merge's record has no status until a promotion fills it in; it isn't a running promotion, so a resume
        doesn't wait it out."""
        self.options(refuse_complete=2)
        wi = self.plain_delivery(56)
        code, body = self.deliver(wi)
        self.assertEqual((code, body.get("pending")), (1, True), body)
        self.assertIn("Lifecycle Center refused the promotion", body["reason"])
        self.assertEqual([(p["status"], p["token"]) for p in self.hub()["promotions"]], [(None, None)])
        with mock.patch.object(lc, "STATUS_DEADLINE", 5):  # a regression fails fast instead of waiting 30 minutes
            code, done = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertEqual([p["status"] for p in self.hub()["promotions"]], ["SUCCESS"], "the merge's record, filled in")

    def test_a_submitted_promotion_without_a_status_yet_is_followed_not_submitted_again(self):
        """Only a record with neither a status nor a request is a refusal's: a lost answer's promotion is found by its
        request even before the platform gives it a status."""
        self.options(complete_crash_once=True, status_late=1)
        wi = self.plain_delivery(57)
        code, done = self.deliver(wi)
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertEqual(len(self.hub()["promotions"]), 1, "one promotion, never a second")

    def test_a_lost_answer_with_nothing_on_the_server_never_says_nothing_was_submitted(self):
        """Only the platform's own refusal proves nothing was submitted; after a lost answer, resume looks again."""
        self.options(complete_unanswered=1)
        wi = self.plain_delivery(58)
        code, body = self.deliver(wi)
        self.assertEqual(code, 1, body)
        self.assertIn("resume looks at the server again", body["reason"])
        self.assertNotIn("nothing was submitted", body["reason"])
        self.assertEqual(self.submitted(), [])
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual((code, body.get("pending")), (1, True), body)
        self.assertIn("won't submit another on its own", body["reason"])
        self.assertEqual(self.submitted(), [], "an unanswered submit is never resubmitted without --retry")
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume", "--retry")
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertEqual([p["status"] for p in self.hub()["promotions"]], ["SUCCESS"])

    def progress_steps(self):
        """(step, line) for each progress line of the last call: `scout_lc <time> <WI> <step>: <text> (<note>)`."""
        return [(line.split(" ", 3)[3].split(":", 1)[0], line) for line in self.stderr.splitlines()
                if line.startswith("scout_lc ")]

    def hub_reset(self, *flags):
        """Clears the stub's one-time flags (a crash already spent, say) so an option applies again."""
        data = self.hub()
        for flag in flags:
            data.pop(flag, None)
        (self.stub / "lc-state.json").write_text(json.dumps(data))

    def not_verified_comments(self):
        return [c["body"] for c in self.github()["comments"] if c.get("body", "").startswith("Not verified: ")]

    def unchanged_state(self):
        """What a read-only command must leave as it was: both stubs' state and every delivery record."""
        files = [self.stub / "lc-state.json", self.stub / "lc-gh.json", *sorted(self.tmp.rglob("deliveries/WI-*.json"))]
        return {str(f): f.read_bytes() for f in files if f.exists()}

    def test_a_delivery_says_each_step_on_stderr_and_when_a_stop_is_safe(self):
        """A long wait isn't a black box. stdout keeps its one JSON answer; stderr says each step, and whether
        stopping now is safe, which it isn't while a change is in flight."""
        wi = self.plain_delivery(60)
        code, done = self.deliver(wi)
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        steps = self.progress_steps()
        names = [step for step, _ in steps]
        for step in ("checking", "validating", "validated", "merging", "continuing", "syncing", "completing", "promoting",
                     "reading back", "done"):
            self.assertIn(step, names, self.stderr)
        self.assertLess(names.index("merging"), names.index("completing"))
        self.assertLess(names.index("completing"), names.index("reading back"))
        self.assertEqual(names[-1], "done")
        for step, line in steps:
            note = "never kill the helper" if step in ("merging", "completing") else \
                "the helper ends here" if step == "done" else "nothing in flight"
            self.assertIn(note, line)
        self.assertTrue(any("submitted as request" in line for _, line in steps), self.stderr)
        self.assertTrue(any(re.search(r"promoting: request \S+: SUCCESS", line) for _, line in steps), self.stderr)

    def test_the_tests_run_after_the_promotion_show_on_stderr(self):
        wi, (code, done) = self.skipped_tests_delivery(61)
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        steps = self.progress_steps()
        self.assertTrue(any(step == "testing" and "starting InvoiceTest" in line and "never kill" in line
                            for step, line in steps), self.stderr)
        self.assertTrue(any(re.search(r"testing: run 707\w+ started", line) for _, line in steps), self.stderr)
        self.assertTrue(any(re.search(r"testing: run 707\w+ is Completed", line) for _, line in steps), self.stderr)

    def test_a_stop_for_a_decision_ends_with_a_line_that_says_so(self):
        wi = self.plain_delivery(62)
        code, plan = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual((code, plan.get("needs")), (3, "deliver-yes"), plan)
        step, line = self.progress_steps()[-1]
        self.assertEqual(step, "waiting for a decision")
        self.assertIn("deliver-yes", line)

    def test_peek_shows_where_a_delivery_stands_and_changes_nothing(self):
        wi, (code, body) = self.skipped_tests_delivery(63, tests_fail_after=["InvoiceTest"])
        self.assertEqual(code, 1, body)
        before = self.unchanged_state()
        logs = {name: (self.stub / name).read_text() for name in ("sf-calls.log", "gh-calls.log")}
        code, peek = self.call("ana", "peek", "--wi", wi)
        self.assertEqual(code, 0, peek)
        self.assertEqual(self.unchanged_state(), before, "peek changed nothing")
        sf_calls = [json.loads(line) for line in (self.stub / "sf-calls.log").read_text()[len(logs["sf-calls.log"]):].splitlines()]
        gh_calls = [json.loads(line) for line in (self.stub / "gh-calls.log").read_text()[len(logs["gh-calls.log"]):].splitlines()]
        writes = {("devops", "work-item", "update"), ("devops", "promotion", "validate"), ("devops", "promotion", "complete"),
                  ("devops", "review", "create"), ("project", "deploy", "start"), ("project", "deploy", "validate"),
                  ("apex", "run", "test"), ("mp", "validate", "--source-dir")}
        self.assertFalse([c for c in sf_calls if tuple(c[:3]) in writes], sf_calls)
        self.assertFalse([c for c in gh_calls if c[:2] in (["pr", "merge"], ["pr", "comment"]) or "POST" in c], gh_calls)
        self.assertTrue(peek["reads_only"])
        self.assertEqual(peek["record"]["step"], "tests-failed")
        self.assertEqual(peek["hub"]["work_item_status"], "CLOSED")
        self.assertEqual(peek["hub"]["selected_promotion"]["status"], "SUCCESS")
        self.assertEqual(peek["hub"]["latest_row"]["status"], "SUCCESS")
        self.assertEqual([(r["token"], r["status"]) for r in peek["requests"]], [(peek["record"]["token"], "SUCCESS")])
        self.assertEqual(peek["requests"][0]["from"], ["record", "selected_promotion", "latest_row"])
        self.assertEqual(peek["tests"]["run"], peek["record"]["test_run"])
        self.assertTrue(peek["tests"]["failures"], peek["tests"])
        self.assertEqual(peek["pull_request"]["state"], "MERGED")
        self.assertTrue(peek["pull_request"]["scouts_comment"].startswith("Not verified: "), peek["pull_request"])

    def test_peek_says_which_read_failed_and_still_shows_the_rest(self):
        wi = self.plain_delivery(64)
        code, done = self.deliver(wi)
        self.assertEqual(code, 0, done)
        self.options(pr_view_fails=5)
        code, peek = self.call("ana", "peek", "--wi", wi)
        self.assertEqual(code, 0, peek)
        self.assertIn("error", peek["pull_request"])
        self.assertEqual(peek["hub"]["selected_promotion"]["status"], "SUCCESS")
        self.assertEqual(peek["record"]["step"], "verified")

    def test_a_failed_test_run_says_not_verified_on_the_pull_request_once(self):
        """Lifecycle Center closes the work item once the promotion succeeds, so the pull request says it."""
        wi, (code, body) = self.skipped_tests_delivery(65, tests_fail_after=["InvoiceTest"])
        self.assertEqual(code, 1, body)
        self.assertEqual(body["comment"], "sent")
        comments = self.not_verified_comments()
        self.assertEqual(len(comments), 1, comments)
        self.assertTrue(comments[0].startswith(f"Not verified: {wi} (pull request #{self.pr_number(wi)}): tests failed"),
                        comments[0])
        self.assertIn(body["test_run"], comments[0])
        self.assertIn("InvoiceTest", comments[0])
        self.assertIn("a revert work item undoes them", comments[0])
        self.assertEqual(self.verified_comments(), [])
        code, again = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual(code, 1, again)
        self.assertEqual(len(self.not_verified_comments()), 1, "said once")

    def test_a_failure_comment_github_refused_goes_at_the_next_team_step(self):
        wi, (code, body) = self.skipped_tests_delivery(66, tests_fail_after=["InvoiceTest"], comment_fails=1)
        self.assertEqual(code, 1, body)
        self.assertTrue(body["comment"].startswith("pending"), body)
        self.assertEqual(self.not_verified_comments(), [])
        self.assertEqual(self.call("ana", "status")[0], 0)
        self.assertEqual(len(self.not_verified_comments()), 1)

    def test_a_passing_retry_after_a_failure_adds_the_verified_comment(self):
        wi, (code, body) = self.skipped_tests_delivery(67, tests_fail_after=["InvoiceTest"])
        self.assertEqual(code, 1, body)
        self.options(tests_fail_after=[])
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume", "--retry")
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertEqual((len(self.not_verified_comments()), len(self.verified_comments())), (1, 1))

    def test_copies_changed_during_the_run_say_not_verified_on_the_pull_request(self):
        wi, (code, body) = self.skipped_tests_delivery(68, tests_edit_org=True)
        self.assertEqual(code, 1, body)
        self.assertEqual(body["comment"], "sent")
        comments = self.not_verified_comments()
        self.assertEqual(len(comments), 1, comments)
        self.assertIn("ApexClass:Invoice", comments[0])
        self.assertEqual(self.verified_comments(), [])

    def test_teammates_see_a_not_verified_comment_in_their_updates(self):
        wi, (code, body) = self.skipped_tests_delivery(69, tests_fail_after=["InvoiceTest"])
        self.assertEqual(code, 1, body)
        self.assertEqual(self.call("bob", "fetch")[0], 0)
        text = self.hook("bob")
        self.assertIn(f"Not verified: {wi} (pull request #", text)
        self.assertIn("tests failed in the common org after the promotion", text)

    @contextlib.contextmanager
    def as_who(self, who):
        """Direct calls into the helper as `who`'s machine: its registry, cache and stubbed tools."""
        saved = dict(os.environ)
        os.environ.update(self.env(who))
        try:
            yield
        finally:
            os.environ.clear()
            os.environ.update(saved)

    def team_id(self, who):
        with self.as_who(who):
            return lc.pick(None)[0]

    def call_quiet(self, who, *args):
        """A call made while another runs (a stop request mid-delivery); it leaves the outer call's stderr alone."""
        outer = getattr(self, "stderr", "")
        try:
            return self.call(who, *args)
        finally:
            self.stderr = outer

    def github_drop_comments(self):
        data = self.github()
        data["comments"] = []
        (self.stub / "lc-gh.json").write_text(json.dumps(data))

    def test_a_stop_request_ends_the_wait_at_a_safe_point_and_resume_reads_the_same_run(self):
        """The test run's ID is recorded before any wait; a stop request (scout_lc.py stop) ends the wait
        at its next safe point, never mid-call; --resume reads that same run rather than starting another."""
        def ask_once(_seconds):
            if sys._getframe(1).f_code.co_name == "wait_for_run" and not getattr(ask_once, "done", False):
                ask_once.done = True
                self.assertEqual(self.call_quiet("ana", "stop", "--wi", wi)[0], 0)
        self.team_up()
        self.options(deploy_runs_no_tests=True, tests_running_reads=3)
        wi = self.package("Invoice totals 70", "ApexClass:Invoice")
        self.build(70)
        self.handover(wi)
        self.assertEqual(self.call("ana", "deliver", "--wi", wi)[1].get("needs"), "tests-after")
        code, plan = self.call("ana", "deliver", "--wi", wi, "--tests-after")
        with mock.patch.object(lc.time, "sleep", ask_once):
            code, body = self.call("ana", "deliver", "--wi", wi, "--tests-after", "--yes", "--plan-id", plan["plan_id"])
        self.assertEqual((code, body.get("pending")), (1, True), body)
        self.assertIn("stopped at the captain's request, while test run", body["reason"])
        run = body["reason"].split("test run ", 1)[1].split(" ", 1)[0]
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual((code, done.get("outcome"), done.get("test_run")), (0, "verified", run), done)
        self.assertEqual(len(self.hub()["test_runs"]), 1, "one run, never a second")

    def test_a_stale_stop_request_doesnt_stop_the_next_delivery(self):
        wi = self.plain_delivery(71)
        self.assertEqual(self.call("ana", "stop", "--wi", wi)[0], 0)
        code, done = self.deliver(wi)
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)

    def test_a_submitted_promotion_not_yet_visible_is_never_submitted_again(self):
        """The answer was lost and the platform's record isn't visible yet: resume waits, and only --retry
        submits again; once the record shows, resume follows it."""
        self.options(complete_crash_once=True, rows_hidden=100)
        wi = self.plain_delivery(72)
        code, body = self.deliver(wi)
        self.assertEqual(code, 1, body)
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual((code, body.get("pending")), (1, True), body)
        self.assertIn("won't submit another on its own", body["reason"])
        self.assertEqual(len(self.submitted()), 1)
        self.options(rows_hidden=0)
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertEqual(len(self.submitted()), 1, "one promotion, never a second")

    def test_a_saved_request_is_followed_when_its_record_isnt_visible(self):
        """A stop while the promotion ran left its request token in the record; resume follows that request."""
        def ask_once(_seconds):
            if sys._getframe(1).f_code.co_name == "poll_promotion" and not getattr(ask_once, "done", False):
                ask_once.done = True
                self.assertEqual(self.call_quiet("ana", "stop", "--wi", wi)[0], 0)
        self.options(status_late=3)
        wi = self.plain_delivery(73)
        code, plan = self.call("ana", "deliver", "--wi", wi)
        with mock.patch.object(lc.time, "sleep", ask_once):
            code, body = self.call("ana", "deliver", "--wi", wi, "--yes", "--plan-id", plan["plan_id"])
        self.assertIn("stopped at the captain's request, while request", body.get("reason", ""), body)
        self.options(rows_hidden=50)
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertEqual(len(self.submitted()), 1)

    def test_a_full_promotion_asked_for_once_stays_full_on_a_plain_retry(self):
        """The full mode is on record from the first --full, so a later --retry never falls back to the default
        mode, which is known to fail here."""
        self.team_up()
        self.options(empty_set=True)
        wi = self.package("Invoice totals 74", "ApexClass:Invoice")
        self.build(74)
        self.handover(wi)
        code, body = self.deliver(wi)
        self.assertTrue(body.get("full"), body)
        code, ask = self.call("ana", "deliver", "--wi", wi, "--resume", "--full")
        self.assertEqual((code, ask.get("needs")), (3, "full-yes"), ask)
        code, again = self.call("ana", "deliver", "--wi", wi, "--resume", "--retry")
        self.assertEqual((code, again.get("needs")), (3, "full-yes"), again)
        self.assertEqual([p["status"] for p in self.hub()["promotions"]], ["ERROR"], "no second default attempt")

    def test_one_sender_at_a_time_and_a_held_lock_keeps_the_comment_pending(self):
        """Two Scout processes never post the same comment twice."""
        wi, (code, body) = self.skipped_tests_delivery(75, tests_fail_after=["InvoiceTest"], comment_fails=1)
        self.assertTrue(body["comment"].startswith("pending"), body)
        with self.as_who("ana"):
            team_id, entry = lc.pick(None)
            with lc.file_lock(lc.record_path(team_id, wi).with_suffix(".comment.lock")):
                self.assertFalse(lc.send_comment(team_id, entry, wi), "another sender holds it")
            self.assertEqual(self.not_verified_comments(), [])
            self.assertTrue(lc.send_comment(team_id, entry, wi))
            self.assertTrue(lc.send_comment(team_id, entry, wi))
        self.assertEqual(len(self.not_verified_comments()), 1)

    def test_a_github_timeout_keeps_the_failure_answer_and_the_comment_pending(self):
        """GitHub hanging while Scout reports a failed run never hides the failure."""
        real = lc.gh

        def hang(args, **kwargs):
            if args[:2] == ["pr", "view"]:
                raise lc.failed("`gh pr view` timed out after 30 s")
            return real(args, **kwargs)
        with mock.patch.object(lc, "gh", hang):
            wi, (code, body) = self.skipped_tests_delivery(76, tests_fail_after=["InvoiceTest"])
        self.assertEqual(code, 1, body)
        self.assertTrue(body["reason"].startswith("not verified: tests failed"), body)
        self.assertTrue(body["comment"].startswith("pending"), body)
        self.assertEqual(self.call("ana", "status")[0], 0)
        self.assertEqual(len(self.not_verified_comments()), 1)

    def test_the_hook_leaves_the_events_alone_while_another_writer_holds_them(self):
        """One writer at a time; an update held back shows at the next prompt, never twice and never lost."""
        wi, (code, body) = self.skipped_tests_delivery(77, tests_fail_after=["InvoiceTest"])
        self.assertEqual(self.call("bob", "fetch")[0], 0)
        team_id = self.team_id("bob")
        with self.as_who("bob"), lc.events_lock(team_id):
            with mock.patch.object(lc, "events_lock", lambda tid: lc.file_lock(
                    lc.team.cache_dir(tid) / "lc-events.lock", wait=0.1)):
                self.assertEqual(self.hook("bob").strip(), "")
        text = self.hook("bob")
        self.assertIn(f"Not verified: {wi}", text)
        self.assertEqual(self.hook("bob").strip(), "", "shown once")

    def test_a_failure_recorded_before_this_version_gets_its_comment_when_resumed(self):
        """Upgrading over a failed delivery: its resume posts the Not verified comment the older version didn't."""
        wi, (code, body) = self.skipped_tests_delivery(78, tests_fail_after=["InvoiceTest"])
        team_id = self.team_id("ana")
        with self.as_who("ana"):
            record = lc.read_record(team_id, wi)
            record.pop("comment", None)
            lc.team.write_json_atomic(lc.record_path(team_id, wi), record)
        self.github_drop_comments()
        code, again = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual(code, 1, again)
        self.assertEqual(len(self.not_verified_comments()), 1)

    def test_an_earlier_failed_record_never_settles_a_newer_unanswered_submit(self):
        """A retry's answer was lost and its record lags behind an earlier failed one: neither --resume nor --resume
        --full submits again on its own."""
        self.options(promotion_fails=True)
        wi = self.plain_delivery(80)
        code, body = self.deliver(wi)
        self.assertEqual(code, 1, body)
        self.options(promotion_fails=False, complete_crash_once=True, hide_from=1)
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume", "--retry")
        self.assertEqual(code, 1, body)
        for extra in ((), ("--full",)):
            code, body = self.call("ana", "deliver", "--wi", wi, "--resume", *extra)
            self.assertEqual((code, body.get("pending")), (1, True), body)
            self.assertIn("won't submit another on its own", body["reason"])
        self.assertEqual(len(self.submitted()), 2, "the failed one and the retry, never a third")
        self.options(hide_from=None)
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertEqual(len(self.submitted()), 2)

    def test_a_promotion_known_only_from_its_request_still_times_the_owed_tests(self):
        """The request's completion time comes along when its record isn't visible, so a passing run isn't failed for a
        missing time."""
        def ask_once(_seconds):
            if sys._getframe(1).f_code.co_name == "poll_promotion" and not getattr(ask_once, "done", False):
                ask_once.done = True
                self.assertEqual(self.call_quiet("ana", "stop", "--wi", wi)[0], 0)
        self.team_up()
        self.options(deploy_runs_no_tests=True, status_late=3)
        wi = self.package("Invoice totals 81", "ApexClass:Invoice")
        self.build(81)
        self.handover(wi)
        self.assertEqual(self.call("ana", "deliver", "--wi", wi)[1].get("needs"), "tests-after")
        code, plan = self.call("ana", "deliver", "--wi", wi, "--tests-after")
        with mock.patch.object(lc.time, "sleep", ask_once):
            code, body = self.call("ana", "deliver", "--wi", wi, "--tests-after", "--yes", "--plan-id", plan["plan_id"])
        self.assertIn("while request", body.get("reason", ""), body)
        self.options(rows_hidden=100)
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)

    def test_every_unsent_failure_report_reaches_the_pull_request(self):
        """Fail, fail again and pass while GitHub refuses comments: both failed runs end up on the pull request."""
        wi, (code, body) = self.skipped_tests_delivery(82, tests_fail_after=["InvoiceTest"], comment_fails=3)
        self.assertTrue(body["comment"].startswith("pending"), body)
        first = body["test_run"]
        code, again = self.call("ana", "deliver", "--wi", wi, "--resume", "--retry")
        self.assertEqual(code, 1, again)
        second = again["test_run"]
        self.assertNotEqual(first, second)
        self.options(tests_fail_after=[])
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume", "--retry")
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertEqual(self.call("ana", "status")[0], 0)
        bodies = " ".join(c["body"] for c in self.github()["comments"])
        self.assertIn(first, bodies)
        self.assertIn(second, bodies)
        self.assertEqual(len(self.verified_comments()), 1)

    def test_a_late_acknowledgement_never_lands_on_a_newer_comment(self):
        wi, (code, body) = self.skipped_tests_delivery(83, tests_fail_after=["InvoiceTest"], comment_fails=1)
        self.assertTrue(body["comment"].startswith("pending"), body)
        team_id = self.team_id("ana")
        real = lc.gh

        def replaced_meanwhile(args, **kwargs):
            answer = real(args, **kwargs)
            if args[:2] == ["pr", "comment"]:  # another session's newer comment lands while this one posts
                pr = lc.read_record(team_id, wi)["comment"]["pr"]
                lc.write_record(team_id, wi, comment={"pr": pr, "body": "Verified in the common org at abc: newer"})
            return answer
        with self.as_who("ana"), mock.patch.object(lc, "gh", replaced_meanwhile):
            self.assertTrue(lc.send_comment(team_id, lc.pick(None)[1], wi))
            record = lc.read_record(team_id, wi)
        self.assertEqual(record["comment"]["body"], "Verified in the common org at abc: newer")
        self.assertFalse(record["comment"].get("sent"), "the newer comment is still to send")

    def test_a_stop_request_made_as_the_delivery_starts_is_kept(self):
        wi = self.plain_delivery(84)
        code, plan = self.call("ana", "deliver", "--wi", wi)
        team_id = self.team_id("ana")
        with self.as_who("ana"):
            path = lc.stop_file(team_id, wi)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("now\n")
            later = time.time() + 30
            os.utime(path, (later, later))
        code, body = self.call("ana", "deliver", "--wi", wi, "--yes", "--plan-id", plan["plan_id"])
        self.assertEqual((code, body.get("stopped")), (1, "before the merge"), body)

    def test_a_failure_only_from_a_missing_promotion_time_is_judged_again(self):
        wi, (code, done) = self.skipped_tests_delivery(85)
        self.assertEqual(code, 0, done)
        team_id = self.team_id("ana")
        with self.as_who("ana"):
            record = lc.read_record(team_id, wi)
            record.update(step="tests-failed", promoted_at=None, tests_failed=["the run didn't start after the promotion"])
            record.pop("comment", None)
            lc.team.write_json_atomic(lc.record_path(team_id, wi), record)
        code, again = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual((code, again.get("outcome"), again.get("test_run")), (0, "verified", done["test_run"]), again)
        self.assertEqual(len(self.hub()["test_runs"]), 1, "the same run, judged again")

    def test_a_failed_promotion_from_the_ui_never_settles_scouts_unanswered_retry(self):
        """A promotion completed in Lifecycle Center's UI failed; Scout's retry lost its answer while its record lags.
        The UI attempt was on record before Scout submitted, so neither --resume nor --resume --full submits again."""
        self.options(promotion_fails=True)
        wi = self.plain_delivery(90)
        code, plan = self.call("ana", "deliver", "--wi", wi)
        self.options(complete_crash_once=True, rows_hidden=100)  # Scout's own first submit: lost, and not visible
        code, body = self.call("ana", "deliver", "--wi", wi, "--yes", "--plan-id", plan["plan_id"])
        self.assertEqual(code, 1, body)
        self.options(rows_hidden=0)
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual(code, 1, body)  # its attempt shows now, and it failed (the stub's promotion_fails)
        self.sf_stub("devops", "promotion", "complete", "--target-stage-id", "1QV000000000001AAA",
                     "--work-item-id", self.item(wi)["id"][:15], "--test-level", "NoTestRun")  # the UI's attempt, failed too
        self.options(promotion_fails=False, complete_crash_once=True, hide_from=2)  # the retry's record lags
        self.hub_reset("crashed")
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume", "--retry")
        self.assertEqual(code, 1, body)
        for extra in ((), ("--full",)):
            code, body = self.call("ana", "deliver", "--wi", wi, "--resume", *extra)
            self.assertEqual((code, body.get("pending")), (1, True), body)
            self.assertIn("won't submit another on its own", body["reason"])
        self.assertEqual(len(self.submitted()), 3, "Scout's first, the UI's and the retry, never a fourth")

    def test_the_request_being_followed_is_never_answered_by_another_attempts_record(self):
        """While the current request can't be read, an earlier attempt's failed record doesn't stand in for it."""
        self.options(promotion_fails=True)
        wi = self.plain_delivery(91)
        code, body = self.deliver(wi)
        self.assertEqual(code, 1, body)
        self.options(promotion_fails=False, hide_from=1, request_status_fails=2)
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume", "--retry")
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertEqual(len(self.submitted()), 2)

    def test_a_comment_writer_that_cant_get_the_lock_writes_nothing_and_resume_finishes(self):
        """No lock, no comment write: the delivery stays resumable, and the failure report comes from the same run."""
        self.team_up()
        self.options(deploy_runs_no_tests=True, tests_fail_after=["InvoiceTest"])
        wi = self.package("Invoice totals 92", "ApexClass:Invoice")
        self.build(92)
        self.handover(wi)
        self.assertEqual(self.call("ana", "deliver", "--wi", wi)[1].get("needs"), "tests-after")
        code, plan = self.call("ana", "deliver", "--wi", wi, "--tests-after")
        team_id = self.team_id("ana")
        with self.as_who("ana"), lc.comment_lock(team_id, wi), mock.patch.object(lc, "COMMENT_WAIT", 0.2):
            code, body = self.call("ana", "deliver", "--wi", wi, "--tests-after", "--yes", "--plan-id", plan["plan_id"])
        self.assertEqual((code, body.get("pending")), (1, True), body)
        self.assertIn("wrote nothing yet", body["reason"])
        with self.as_who("ana"):
            self.assertEqual(lc.read_record(team_id, wi)["step"], "tests-running")
        code, again = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual(code, 1, again)
        self.assertTrue(again["reason"].startswith("not verified: tests failed"), again)
        self.assertEqual(len(self.not_verified_comments()), 1)
        self.assertEqual(len(self.hub()["test_runs"]), 1, "the same run")

    def test_lane_teams_dont_see_lifecycle_teams(self):
        self.team_up()
        saved = dict(os.environ)
        os.environ.update(self.env("ana"))
        try:
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer), mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"cwd": str(self.ana)}))):
                team.main(["updates", "--hook"])
            self.assertEqual(buffer.getvalue().strip(), "")
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                team.main(["context", "--cwd", str(self.ana)])
            context = json.loads(buffer.getvalue())
        finally:
            os.environ.clear()
            os.environ.update(saved)
        self.assertEqual(context["mode"], "lifecycle")
        self.assertTrue(context["prompt"].endswith("team-lifecycle.md"))

    # ---- the guard at join: an explained choice, and Lifecycle Center mode works without it ----

    def registry(self):
        path = self.stub / "mp-registry.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def member_record(self, member_id):
        return json.loads(sh("git", "-C", str(self.remote), "show", f"{lc.MEMBERS_BRANCH}:members/{member_id}.json"))

    def sf_calls(self):
        path = self.stub / "sf-calls.log"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_a_join_explains_the_guard_and_puts_it_on_only_on_a_yes(self):
        self.assertEqual(self.call("ana", *START, "--yes")[0], 0)
        code, ask = self.call("bob", *JOIN, STUB_GUARD="")
        self.assertEqual((code, ask.get("needs")), (3, "start-yes"), ask)
        self.assertIn(team.GUARD_WHAT, ask["reason"])
        self.assertIn("stops this machine's Salesforce CLI from deploying to the team's common org outside the captain's "
                      "delivery", ask["guard"])
        self.assertEqual(len(re.findall(r"[.!?](?:\s|$)", ask["guard"])), 2, "two sentences")
        code, ask = self.call("bob", *JOIN, "--yes", STUB_GUARD="")
        self.assertEqual((code, ask.get("needs")), (3, "guard-choice"), ask)
        self.assertEqual(self.call("bob", *JOIN, "--yes", "--yes-guard", "--no-guard")[0], 2)
        self.assertFalse([c for c in self.sf_calls() if c[:2] == ["plugins", "install"]], "nothing went in before the yes")
        self.assertFalse((self.tmp / "bob" / "teams.json").exists(), "and nothing was set up")
        code, joined = self.call("bob", *JOIN, "--yes", "--yes-guard", STUB_GUARD="")
        self.assertEqual(code, 0, joined)
        self.assertEqual(joined["guard"]["guard"], "installed now")
        self.assertTrue([c for c in self.sf_calls() if c[:2] == ["plugins", "install"]])
        self.assertIn(COMMON[:15], self.registry()[str(self.tmp / "bob" / "teams.json")], "it guards the common org")
        self.assertEqual(self.member_record("bob-example-com")["guard"], "on")
        code, body = self.call("ana", *START, "--yes", "--no-guard")
        self.assertEqual(code, 2, body)
        self.assertIn("captain's machine needs Scout's guard", body["reason"])

    def test_without_the_guard_a_member_builds_and_the_captains_checks_and_view_stay(self):
        self.assertEqual(self.call("ana", *START, "--yes")[0], 0)
        code, joined = self.call("bob", *JOIN, "--yes", "--no-guard", STUB_GUARD="")
        self.assertEqual((code, joined["guard"]["guard"]), (0, "off"), joined)
        self.assertIn("build only in your own sandbox", joined["guard"]["note"])
        self.assertIn(lc.MEMBERS_BRANCH, joined["member_record"])
        self.assertFalse([c for c in self.sf_calls() if c[:2] in (["plugins", "install"], ["mp", "init"])
                          and "--lifecycle-captain" not in c], "no guard went in or was bound on his machine")
        self.assertNotIn(str(self.tmp / "bob" / "teams.json"), self.registry())
        record = self.member_record("bob-example-com")
        self.assertEqual((record["name"], record["role"], record["guard"], record["build_org"]),
                         ("Bob Builder", "builder", "off", "bob-sbx"))
        wi = self.package("Invoice totals 95", "ApexClass:Invoice")
        self.build(95)
        self.handover(wi)
        code, done = self.deliver(wi)
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertEqual(json.loads((self.stub / "validations.json").read_text())[-1]["tests"], ["InvoiceTest"],
                         "the captain's test gate ran as before")
        code, status = self.call("ana", "status")
        self.assertEqual(code, 0, status)
        self.assertEqual(status["guard_off"], ["Bob Builder"])
        self.assertEqual([(m["name"], m["guard"], m["builds_in"]) for m in status["members"]],
                         [("Bob Builder", "off", "bob-sbx")])

    # ---- a protected main: the rules come as a pull request ----

    def protect_main(self):
        hook = self.remote / "hooks" / "pre-receive"
        hook.write_text('#!/bin/sh\nwhile read old new ref; do\n  if [ "$ref" = "refs/heads/main" ]; then\n'
                        '    echo "GH006: Protected branch update failed for refs/heads/main." >&2; exit 1\n  fi\ndone\n')
        hook.chmod(0o755)

    def test_a_protected_main_gets_the_rules_through_a_pull_request_and_start_carries_on_once_merged(self):
        self.protect_main()
        before = self.main_sha()
        code, body = self.call("ana", *START, "--yes")
        self.assertEqual((code, body.get("needs")), (3, "rules-review"), body)
        self.assertIn("merge the pull request, then run start again", body["reason"])
        self.assertEqual((body["branch"], body["files"]), (lc.RULES_BRANCH, [".gitattributes", ".gitignore", "AGENTS.md"]))
        number = body["pull_request"]["number"]
        self.assertEqual(self.main_sha(), before, "main is as it was")
        proposal = sh("git", "-C", str(self.remote), "rev-parse", lc.RULES_BRANCH)
        self.assertEqual(sh("git", "-C", str(self.remote), "rev-parse", f"{proposal}^"), before, "one commit on main")
        self.assertIn(lc.RULES_START, self.main_text("AGENTS.md", ref=lc.RULES_BRANCH))
        checkout = self.tmp / "ana" / "ws" / "teams" / "team"
        self.assertEqual((sh("git", "-C", str(checkout), "rev-parse", "HEAD"),
                          sh("git", "-C", str(checkout), "status", "--porcelain")), (before, ""),
                         "the captain's checkout stays clean, at origin's main")
        self.assertFalse((self.tmp / "ana" / "teams.json").exists(), "the team isn't set up until the rules are on main")
        code, again = self.call("ana", *START, "--yes")
        self.assertEqual((code, again["pull_request"]["number"]), (3, number), again)
        self.assertEqual(sh("git", "-C", str(self.remote), "rev-parse", lc.RULES_BRANCH), proposal, "the same proposal")
        creates = [l for l in (self.stub / "gh-calls.log").read_text().splitlines() if '"pr", "create"' in l]
        self.assertEqual(len(creates), 1, "one pull request")
        self.assertEqual(self.gh_stub("pr", "merge", str(number), "--repo", "acme/team", "--squash").returncode, 0)
        code, done = self.call("ana", *START, "--yes")
        self.assertEqual((code, done.get("written_on_main")), (0, []), done)
        self.assertIn(lc.RULES_START, self.main_text("AGENTS.md"))
        self.assertTrue(self.registry()[str(self.tmp / "ana" / "teams.json")][COMMON[:15]]["lifecycleCaptain"])
        self.assertEqual((sh("git", "-C", str(checkout), "rev-parse", "HEAD"), sh("git", "-C", str(checkout), "status",
                         "--porcelain")), (self.main_sha(), ""), "the captain's checkout moved forward to the merged main")
        for name in ("AGENTS.md", ".gitignore", ".gitattributes"):
            self.assertEqual((checkout / name).read_text(), self.main_text(name), name)

    def test_without_gh_a_protected_main_names_the_branch_and_its_compare_link(self):
        self.protect_main()
        code, body = self.call("ana", *START, "--yes", SCOUT_TEAM_GH=str(self.tmp / "no-gh"))
        self.assertEqual((code, body.get("needs")), (3, "rules-review"), body)
        compare = f"https://github.com/acme/team/compare/main...{lc.RULES_BRANCH}?expand=1"
        self.assertEqual((body["compare"], body["pull_request"]), (compare, None))
        self.assertIn(compare, body["reason"])
        self.assertIn("merge the pull request, then run start again", body["reason"])
        self.assertIn("isn't installed", body["gh"])
        self.assertIn(lc.RULES_START, self.main_text("AGENTS.md", ref=lc.RULES_BRANCH))

    # ---- line endings from Windows builders ----

    def test_the_team_start_sets_lf_line_endings_first_and_keeps_the_teams_own_attributes(self):
        self.push_to_main({".gitattributes": "*.png binary\n"}, "the team's own attributes")
        self.team_up()
        self.assertEqual(self.main_text(".gitattributes"), "* text=auto eol=lf\n*.png binary\n")
        code, again = self.call("ana", *START, "--yes")
        self.assertEqual((code, again["written_on_main"]), (0, []), "a second start writes nothing")

    def test_the_rules_and_the_markers_read_the_same_from_a_windows_checkout(self):
        def crlf(text):
            return text.replace("\n", "\r\n")
        wanted = lc.rules_files(OWN_AGENTS, "", "")["AGENTS.md"]
        ignore, attributes = "\n".join(lc.GITIGNORE_LINES) + "\n", lc.ATTRIBUTES_LINE + "\n"
        self.assertEqual(lc.rules_files(crlf(wanted), crlf(ignore), crlf(attributes)), {}, "current, so nothing to write")
        older = wanted.replace("Open the review as soon as you've pushed", "Open the review once you've pushed")
        self.assertEqual(lc.rules_files(crlf(older), crlf(ignore), crlf(attributes)), {"AGENTS.md": wanted},
                         "one block, brought up to date, and the team's own text kept")
        description = crlf("Components: `ApexClass:Invoice`, `Layout:Probe__c-Probe Layout`\nChecked: abc1234def\nBuilder: Dana\n")
        self.assertEqual(lc.declared({"description": description}), ["ApexClass:Invoice", "Layout:Probe__c-Probe Layout"])
        self.assertEqual(lc.CHECKED.search(description)[1], "abc1234def")
        self.assertEqual(lc.CHECKED_LINE.sub("", description),
                         crlf("Components: `ApexClass:Invoice`, `Layout:Probe__c-Probe Layout`\nBuilder: Dana\n"))

    def test_a_windows_builders_line_endings_never_widen_a_delivery(self):
        """Her editor saved the layout with CRLF line endings only; the team's .gitattributes keeps it out of her
        commit, and the Lifecycle Center UI's CRLF line breaks in the work item still read."""
        self.team_up()
        wi = self.package("Dana on Windows", "ApexClass:Invoice", who="ana", owner="Dana")
        self.describe(wi, (self.item(wi)["description"] + f"\nChecked: {self.main_sha()}\n").replace("\n", "\r\n"))
        layout = self.main_text(LAYOUT_PATH).replace("\n", "\r\n")
        head = self.dana_commits(wi, {CLS: CLASS.format(n=96), LAYOUT_PATH: layout}, "totals 96, saved on Windows")
        self.assertEqual(sh("git", "-C", str(self.remote), "diff", "--name-only", "main", head).splitlines(), [CLS])
        self.review(wi)
        code, plan = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual((code, plan.get("needs")), (3, "deliver-yes"), plan)
        self.assertEqual((plan["components"], plan["declared"]), (["ApexClass:Invoice"], ["ApexClass:Invoice"]))
        self.assertEqual((plan["checks"]["base"]["state"], plan["checks"]["scope"]), ("checked", "ok"))

    # ---- gates whose input is missing stop, or say not verified ----

    def test_a_stage_whose_answer_names_no_branch_or_no_org_is_refused(self):
        self.options(stage_branch=None)
        code, body = self.call("ana", *START, "--yes")
        self.assertEqual(code, 2, body)
        self.assertIn("not named in the answer", body["reason"])
        self.options(stage_branch="main", stage_org="")
        code, body = self.call("ana", *START, "--yes")
        self.assertEqual(code, 2, body)
        self.assertIn("deploys to no org yet", body["reason"])

    def test_a_delivery_of_a_missing_work_item_or_review_stops(self):
        self.team_up()
        code, body = self.call("ana", "deliver", "--wi", "WI-000999")
        self.assertEqual(code, 2, body)
        self.assertIn("isn't a work item of this team's project", body["reason"])
        wi = self.package("Not reviewed yet", "ApexClass:Invoice")
        code, body = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual(code, 2, body)
        self.assertIn("has no open review", body["reason"])

    def test_a_work_item_without_a_components_line_says_so_in_the_plan(self):
        self.team_up()
        wi = self.package("Dana's undeclared change", "ApexClass:Invoice", who="ana", owner="Dana")
        self.describe(wi, f"Checked: {self.main_sha()}")  # her description lost its Components line
        self.dana_commits(wi, {CLS: CLASS.format(n=97)}, "totals 97")
        self.review(wi)
        code, plan = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual((code, plan.get("needs")), (3, "deliver-yes"), plan)
        self.assertEqual(plan["declared"], [])
        self.assertTrue(plan["checks"]["scope"].startswith("not declared"), plan["checks"])

    def test_effect_checks_without_an_answer_stop_before_the_merge(self):
        silent = self.tmp / "node-silent"
        silent.write_text("#!/bin/sh\ncat >/dev/null\n")
        silent.chmod(0o755)
        wi = self.plain_delivery(98)
        code, body = self.call("ana", "deliver", "--wi", wi, SCOUT_TEAM_NODE=str(silent))
        self.assertEqual(code, 1, body)
        self.assertIn("effect checks gave no answer", body["reason"])
        self.assertEqual(self.github()["prs"][0]["state"], "OPEN", "nothing merged")

    def test_an_unnamed_stage_suite_or_a_silent_validation_stops_the_test_gate(self):
        self.team_up()
        self.suites([None])
        wi = self.package("Invoice totals 99", "ApexClass:Invoice", "ApexClass:InvoiceTest")
        self.build(99, extra_test=True)
        self.handover(wi)
        code, body = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual((code, body.get("needs"), body["validation"].get("stop")), (3, "tests", "missing-suite"), body)
        self.assertIn("a stage suite the hub returned without its name", body["validation"]["missing_suites"])
        self.suites(["InvoiceSuite"])
        self.options(validate_silent=True)
        code, body = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual((code, body.get("needs"), body["validation"]["validated"]), (3, "tests", False), body)
        self.assertEqual(self.github()["prs"][0]["state"], "OPEN", "nothing merged")

    def test_an_undeployed_merge_older_than_the_merged_list_still_holds_the_stage(self):
        self.team_up()
        self.options(promotion_fails=True)
        first = self.package("Invoice totals 104", "ApexClass:Invoice")
        self.build(104)
        self.handover(first)
        self.assertEqual(self.deliver(first)[0], 1, "merged, and its promotion failed")
        self.options(promotion_fails=False)
        work = self.tmp / "dana" / "notes"
        self.git_as("dana", "clone", "--quiet", REMOTE_URL, str(work))
        self.git_as("dana", "-C", str(work), "checkout", "--quiet", "-b", "docs/notes")
        self.write(work, "docs/NOTES.md", "Notes.\n")
        self.git_as("dana", "-C", str(work), "add", "-A")
        self.git_as("dana", "-C", str(work), "commit", "--quiet", "-m", "notes")
        self.git_as("dana", "-C", str(work), "push", "--quiet", "origin", "docs/notes")
        self.assertEqual(self.gh_stub("pr", "create", "--repo", "acme/team", "--base", "main", "--head", "docs/notes",
                                      "--title", "Notes").returncode, 0)
        notes = next(p["number"] for p in self.github()["prs"] if p["head"] == "docs/notes")
        self.assertEqual(self.gh_stub("pr", "merge", str(notes), "--repo", "acme/team", "--squash").returncode, 0)
        later = self.package("Layout tweak", "Layout:Probe__c-Probe Layout")
        self.org_write("bob-sbx", LAYOUT_PATH, LAYOUT.replace("Info", "Tweak"))
        self.handover(later)
        with mock.patch.object(lc, "MERGED_LIMIT", 1):  # the newest merge alone is read: the notes, not the first one
            code, body = self.call("ana", "deliver", "--wi", later)
        self.assertEqual(code, 2, body)
        self.assertIn(f"{first} (#{self.pr_number(first)}) is merged into main but not deployed", body["reason"])

    def promote_in_the_ui(self, wi):
        """The merge's promotion, completed in Lifecycle Center: ready, the validations that sync it, then complete."""
        self.sf_stub("devops", "work-item", "update", "--work-item-name", wi, "--status", "Ready to Promote")
        for _ in range(2):
            self.sf_stub("devops", "promotion", "validate", "--target-stage-id", STAGE18, "--work-item-id",
                         self.item(wi)["id"][:15])
        answer = self.sf_stub("devops", "promotion", "complete", "--target-stage-id", STAGE18, "--work-item-id",
                              self.item(wi)["id"][:15], "--test-level", "NoTestRun")
        self.assertEqual(answer["status"], 0, answer)

    def test_a_read_back_with_nothing_to_read_is_never_verified(self):
        self.team_up()
        wi = self.package("Notes only", "ApexClass:Invoice", who="ana", owner="Dana")
        self.dana_commits(wi, {"docs/NOTES.md": "Notes.\n"}, "notes only")
        self.review(wi)
        self.assertEqual(self.gh_stub("pr", "merge", str(self.pr_number(wi)), "--repo", "acme/team", "--squash").returncode, 0)
        self.promote_in_the_ui(wi)
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual(code, 1, body)
        self.assertIn("nothing to read back and it isn't verified", body["reason"])
        self.assertEqual(self.verified_comments(), [])

    def test_a_merge_scout_didnt_plan_owes_its_own_tests_after_a_plan_for_another_revision(self):
        """A plan's validation ran the tests on one revision; the branch moved and was merged and promoted elsewhere.
        Those earlier tests never stand in for the revision that went out."""
        wi = self.plain_delivery(100)
        code, plan = self.call("ana", "deliver", "--wi", wi)
        self.assertEqual(plan.get("needs"), "deliver-yes", plan)
        with self.as_who("ana"):
            stop = lc.stop_file(lc.pick(None)[0], wi)
        stop.parent.mkdir(parents=True, exist_ok=True)
        stop.write_text("now\n")
        later = time.time() + 30
        os.utime(stop, (later, later))
        code, body = self.call("ana", "deliver", "--wi", wi, "--yes", "--plan-id", plan["plan_id"])
        self.assertEqual((code, body.get("stopped")), (1, "before the merge"), body)
        self.assertEqual(self.github()["prs"][0]["state"], "OPEN")
        self.dana_commits(wi, {CLS: CLASS.format(n=101)}, "another change, pushed after the plan")
        self.assertEqual(self.gh_stub("pr", "merge", str(self.pr_number(wi)), "--repo", "acme/team", "--squash").returncode, 0)
        self.promote_in_the_ui(wi)
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertEqual(done.get("tests"), ["InvoiceTest"], "the merged revision's own tests ran after the promotion")
        self.assertEqual(len(self.hub()["test_runs"]), 1)

    def test_a_test_run_without_results_is_never_verified(self):
        wi, (code, body) = self.skipped_tests_delivery(102, tests_no_results=True)
        self.assertEqual(code, 1, body)
        self.assertTrue(body["reason"].startswith("not verified: tests failed"), body)
        self.assertIn("InvoiceTest didn't run", body["reason"])
        self.assertEqual(self.verified_comments(), [])

    def test_a_run_judged_without_its_owed_tests_or_its_read_back_copies_is_never_verified(self):
        wi, (code, body) = self.skipped_tests_delivery(103, tests_dont_start=True)
        self.assertEqual((code, body.get("pending")), (1, True), body)
        team_id = self.team_id("ana")

        def edit(**changes):
            with self.as_who("ana"):
                record = lc.read_record(team_id, wi)
                for key, value in changes.items():
                    if value is None:
                        record.pop(key, None)
                    else:
                        record[key] = value
                lc.team.write_json_atomic(lc.record_path(team_id, wi), record)
        edit(checked_against=None, promoted=None)  # an older record: which copies were read back is unknown
        self.options(tests_dont_start=False)
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual(code, 1, body)
        self.assertTrue(body["reason"].startswith("not verified: the tests passed"), body)
        edit(step="tests-running", tests_after=None)  # and one that names no owed test for its run
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual(code, 1, body)
        self.assertIn("names no tests it owes", body["reason"])
        self.assertEqual(self.verified_comments(), [])
        edit(step="unverified")
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume")  # read back again, and the owed tests run again
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)

    # ---- the rules for builders without Scout, and the read-back's tab warning ----

    def test_the_rules_carry_the_lines_for_builders_without_scout(self):
        self.team_up()
        flat = " ".join(self.main_text("AGENTS.md").split())
        for line in ("**When an official deploy skill fails,** deploy to your own sandbox with `sf project deploy start "
                     "--target-org <your sandbox>`, never to the common org.",
                     "**A new custom object ships with its tab** and a permission set that makes the tab visible",
                     "**Tests that insert records of a new record type** create their own user and grant the record type "
                     "through a permission set, outside `System.runAs`"):
            self.assertIn(line, flat)
        rules = " ".join((ROOT / "skills/demo-deployment-rules/SKILL.md").read_text().split())
        note = ("Tests that insert records of a new record type create their own user and grant the record type through a "
                "permission set, outside `System.runAs`; they insert those records as that user, inside it.")
        apex = rules.split("## Apex Rules (Phase 2)", 1)[1].split(" ## ", 1)[0]
        self.assertIn(note, apex, "in the Apex section")
        self.assertEqual((rules.count("grant the record type through a permission set"), rules.count("System.runAs")),
                         (1, 1), "and nowhere else in that file")

    def test_the_read_back_warns_about_a_new_object_without_a_visible_tab(self):
        self.team_up()
        self.org_write("bob-sbx", object_path("Gadget__c"), OBJECT.format(label="Gadget"))
        wi = self.package("A gadget object", "CustomObject:Gadget__c")
        self.handover(wi)
        code, done = self.deliver(wi)
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertEqual(len(done["warnings"]), 1, done)
        self.assertTrue(done["warnings"][0].startswith("Git holds no tab for the new object Gadget__c"), done["warnings"])
        self.assertIn("Warning: Git holds no tab for the new object Gadget__c", self.verified_comments()[-1])
        self.assertEqual(done["presenter"], "admin@common.example", "the captain's user in the common org, by default")

    def test_the_tab_check_reads_git_only_and_asks_for_the_assignment_to_the_presenter(self):
        base = self.main_sha()
        objects = {name: object_path(name) for name in ("Plain__c", "Setting__c", "Shown__c", "Tabbed__c")}
        files = {path: OBJECT.format(label=name) for name, path in objects.items()}
        files[objects["Setting__c"]] = OBJECT.format(label="Setting").replace(
            "<label>", "<customSettingsType>List</customSettingsType>\n    <label>", 1)  # a custom setting has no tab
        files.update({tab_path("Tabbed__c"): TAB, tab_path("Shown__c"): TAB,
                      permset_path("Hidden_Access"): PERMSET.format(label="Hidden", tab="Tabbed__c", visibility="None"),
                      permset_path("Shown_Access"): PERMSET.format(label="Shown", tab="Shown__c",
                                                                   visibility="Available").replace("\n", "\r\n")})
        target = self.push_to_main(files, "four new objects")
        components = [f"CustomObject:{name}" for name in objects]
        warnings = lc.tab_warnings(self.remote, base, target, components)
        self.assertEqual(len(warnings), 3, warnings)
        self.assertTrue(warnings[0].startswith("Git holds no tab for the new object Plain__c, so whether it shows in the "
                                               "App Launcher is unverified"), warnings)
        self.assertIn("Git gives the new object Shown__c a tab and a permission set that makes it visible (Shown_Access), "
                      "but Scout checked Git only, not who can see it", warnings[1])
        self.assertIn("Git holds no permission set that makes the new object Tabbed__c's tab visible, so its visibility "
                      "is unverified", warnings[2])
        for warning in warnings:
            self.assertIn("the user who presents (the captain's user", warning)
            self.assertNotIn("stays out", warning, "Git alone can't say the object is hidden")
        self.assertEqual(lc.tab_warnings(self.remote, target, target, components), [], "objects main had already aren't new")

    # ---- the review's round: identities, missing answers, the rules' proposal, the checkout, the guard's state ----

    def test_a_build_org_that_is_the_common_org_is_refused_at_join_and_at_work(self):
        self.assertEqual(self.call("ana", *START, "--yes")[0], 0)
        into_common = JOIN[:-1] + ["common", "--yes"]
        for guard in ("--yes-guard", "--no-guard"):
            code, body = self.call("bob", *into_common, guard)
            self.assertEqual(code, 2, body)
            self.assertIn("never the common org", body["reason"])
        self.assertFalse((self.tmp / "bob" / "teams.json").exists(), "nothing was set up")
        code, body = self.call("ana", *START, "--yes", "--build-org", "common")
        self.assertEqual(code, 2, body)
        self.assertEqual(self.call("bob", *JOIN, "--yes", "--no-guard")[0], 0)
        self.options(rebind={"bob-sbx": COMMON})  # his sandbox's alias now names the common org
        code, body = self.call("bob", "package", "start", "--title", "Rebound", "--components", "ApexClass:Invoice")
        self.assertEqual(code, 2, body)
        self.assertIn("now names the team's common org", body["reason"])
        self.assertEqual(self.hub().get("items") or {}, {}, "no work item was created")
        self.options(rebind={})
        teams = self.tmp / "bob" / "teams.json"
        registry = json.loads(teams.read_text())
        bad = registry["teams"][TEAM_ID]
        bad["build_org"]["org_id"] = bad["build_org_id"] = COMMON[:15]  # accepted before this check existed
        teams.write_text(json.dumps(registry))
        for args in (["package", "start", "--title", "Old", "--components", "ApexClass:Invoice"],
                     ["package", "check", "--wi", "WI-000001"], ["handover", "--wi", "WI-000001"]):
            code, body = self.call("bob", *args)
            self.assertEqual(code, 2, body)
            self.assertIn("names the common org as its build org", body["reason"])

    def test_answers_without_their_records_or_list_stop_the_delivery_gates(self):
        """A success that leaves its records or its list out is a missing input, never "no suites", "stage clear" or
        "nothing waiting"; genuine empty answers still work."""
        wi = self.plain_delivery(105)
        other = self.package("Layout in review", "Layout:Probe__c-Probe Layout")
        self.org_write("bob-sbx", LAYOUT_PATH, LAYOUT.replace("Info", "Review"))
        self.handover(other)  # in review, so the unresolved-work gate asks GitHub about it
        gates = {"the stage's suites": {"silent_queries": ["FROM DevopsTestSuiteStage"]},
                 "a running promotion": {"silent_queries": ["FROM DevopsPipelnStgProm WHERE"]},
                 "unresolved work on the hub": {"silent_queries": ["Status IN ('IN_REVIEW', 'READY_TO_PROMOTE')"]},
                 "unresolved work on GitHub": {"gh_silent": ["--state merged"]},
                 "the work item's review": {"gh_silent": ["--head " + wi]}}
        for gate, option in gates.items():
            with self.subTest(gate=gate):
                self.options(**dict({"silent_queries": [], "gh_silent": []}, **option))
                code, body = self.call("ana", "deliver", "--wi", wi)
                self.assertEqual(code, 1, body)
                self.assertTrue("answered without its records" in body["reason"] or "answered without a list" in body["reason"],
                                body["reason"])
        self.assertEqual(self.github()["prs"][0]["state"], "OPEN", "nothing merged")
        self.options(silent_queries=[], gh_silent=[])
        code, done = self.deliver(wi)
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)

    def test_a_reviewers_edit_to_the_rules_proposal_is_kept(self):
        self.protect_main()
        code, body = self.call("ana", *START, "--yes")
        self.assertEqual((code, body.get("needs")), (3, "rules-review"), body)
        number = body["pull_request"]["number"]
        work = self.tmp / "dana" / "review"
        self.git_as("dana", "clone", "--quiet", REMOTE_URL, str(work))
        self.git_as("dana", "-C", str(work), "checkout", "--quiet", lc.RULES_BRANCH)
        self.write(work, "AGENTS.md", "Reviewed by the team.\n\n" + (work / "AGENTS.md").read_text())
        self.git_as("dana", "-C", str(work), "commit", "--quiet", "-am", "a reviewer's note")
        self.git_as("dana", "-C", str(work), "push", "--quiet", "origin", lc.RULES_BRANCH)
        edited = sh("git", "-C", str(self.remote), "rev-parse", lc.RULES_BRANCH)
        code, again = self.call("ana", *START, "--yes")
        self.assertEqual((code, again.get("needs"), again.get("kept")), (3, "rules-review", True), again)
        self.assertIn("keeps it as it is", again["reason"])
        self.assertEqual(again["pull_request"]["number"], number, "the same pull request")
        self.assertEqual(sh("git", "-C", str(self.remote), "rev-parse", lc.RULES_BRANCH), edited, "never replaced")
        self.assertEqual(len([l for l in (self.stub / "gh-calls.log").read_text().splitlines() if '"pr", "create"' in l]), 1)
        self.assertEqual(self.gh_stub("pr", "merge", str(number), "--repo", "acme/team", "--squash").returncode, 0)
        code, done = self.call("ana", *START, "--yes")
        self.assertEqual((code, done.get("written_on_main")), (0, []), done)
        self.assertTrue(self.main_text("AGENTS.md").startswith("Reviewed by the team.\n"), "the reviewer's edit is on main")

    def test_start_moves_the_captains_checkout_forward_but_never_over_their_work(self):
        self.team_up()
        checkout = self.ana
        newer = self.push_to_main({"docs/NOTES.md": "Notes.\n"}, "a note on main")
        self.assertEqual(self.call("ana", *START, "--yes")[0], 0)
        self.assertEqual(sh("git", "-C", str(checkout), "rev-parse", "HEAD"), newer, "fast-forwarded to origin's main")
        self.write(checkout, "docs/NOTES.md", "Notes, edited here.\n")
        code, body = self.call("ana", *START, "--yes")
        self.assertEqual(code, 2, body)
        self.assertIn("uncommitted changes", body["reason"])
        self.assertEqual((checkout / "docs/NOTES.md").read_text(), "Notes, edited here.\n", "the edit stays")
        self.git_as("ana", "-C", str(checkout), "commit", "--quiet", "-am", "a local commit on main")
        local = sh("git", "-C", str(checkout), "rev-parse", "HEAD")
        code, body = self.call("ana", *START, "--yes")
        self.assertEqual(code, 2, body)
        self.assertIn("commits origin's main doesn't", body["reason"])
        self.assertEqual(sh("git", "-C", str(checkout), "rev-parse", "main"), local, "never reset")

    def test_start_reports_crlf_already_committed_and_leaves_it_out_of_the_rules(self):
        self.push_to_main({LAYOUT_PATH: LAYOUT.replace("\n", "\r\n")}, "a layout saved on Windows")
        code, body = self.call("ana", *START, "--yes")
        self.assertEqual(code, 0, body)
        self.assertEqual((body["crlf"]["files"], body["crlf"]["components"]), ([LAYOUT_PATH], ["Layout:Probe__c-Probe Layout"]))
        self.assertIn("git add --renormalize .", body["crlf"]["next"])
        self.assertIn("never inside the rules' pull request", body["crlf"]["next"])
        changed = sh("git", "-C", str(self.remote), "show", "--name-only", "--format=", "main").splitlines()
        self.assertEqual(sorted(changed), [".gitattributes", ".gitignore", "AGENTS.md"], "nothing else swept in")
        stored = subprocess.run(["git", "-C", str(self.remote), "show", f"main:{LAYOUT_PATH}"], capture_output=True).stdout
        self.assertIn(b"\r\n", stored, "the layout stays as it was until its own work item")

    def test_a_member_who_says_no_keeps_an_earlier_guard_until_they_take_it_off(self):
        self.team_up()  # Bob joined with the guard, as every join did before it became a choice
        bound = self.tmp / "bob" / "sf-data" / "sf-mp" / "bound-orgs.json"
        self.assertIn(COMMON[:15], json.loads(bound.read_text())["orgs"])
        code, again = self.call("bob", *JOIN, "--yes", "--no-guard")
        self.assertEqual((code, again["guard"]["binding"], again["guard"]["choice"]), (0, "on", "no"), again)
        self.assertIn("still guards the common org", again["guard"]["note"])
        record = self.member_record("bob-example-com")
        self.assertEqual((record["guard"], record["guard_choice"]), ("on", "no"))
        self.assertEqual(self.call("ana", "status")[1]["guard_off"], [], "his guard is still on")
        self.assertIn(COMMON[:15], json.loads(bound.read_text())["orgs"], "the join took nothing off")
        code, ask = self.call("bob", "unguard")
        self.assertEqual((code, ask.get("needs")), (3, "unguard-yes"), ask)
        code, done = self.call("bob", "unguard", "--yes")
        self.assertEqual((code, done["guard"], done["removed"]), (0, "off", True), done)
        self.assertNotIn(COMMON[:15], json.loads(bound.read_text())["orgs"])
        self.assertEqual(self.member_record("bob-example-com")["guard"], "off")
        self.assertEqual(self.call("ana", "status")[1]["guard_off"], ["Bob Builder"])
        code, body = self.call("ana", "unguard", "--yes")
        self.assertEqual(code, 2, body)
        self.assertIn("captain's machine keeps Scout's guard", body["reason"])

    def test_a_squash_merged_rules_branch_left_in_place_never_blocks_the_next_rules_update(self):
        """GitHub's squash merge keeps no ancestry, and the merged branch can stay: the next rules update goes out on a
        branch name not used yet, and the merged one stays as it is, with gh and without."""
        self.protect_main()
        code, body = self.call("ana", *START, "--yes")
        self.assertEqual((code, body.get("branch")), (3, lc.RULES_BRANCH), body)
        self.assertEqual(self.gh_stub("pr", "merge", str(body["pull_request"]["number"]), "--repo", "acme/team",
                                      "--squash").returncode, 0)
        self.assertEqual(self.call("ana", *START, "--yes")[0], 0, "the rules are on main")
        merged = sh("git", "-C", str(self.remote), "rev-parse", lc.RULES_BRANCH)
        later = lc.AGENTS_MD + "10. **A rule a later Scout adds.**\n"
        with mock.patch.object(lc, "AGENTS_MD", later):
            code, body = self.call("ana", *START, "--yes", SCOUT_TEAM_GH=str(self.tmp / "no-gh"))
            self.assertEqual((code, body.get("needs"), body.get("kept")), (3, "rules-review", None), body)
            self.assertEqual(body["branch"], lc.RULES_BRANCH + "-2", "a new name: the merged branch stays as it is")
            self.assertEqual(body["compare"], f"https://github.com/acme/team/compare/main...{lc.RULES_BRANCH}-2?expand=1")
            self.assertEqual(body["earlier"], [lc.RULES_BRANCH])
            code, body = self.call("ana", *START, "--yes")  # with gh: the same new proposal, now with its pull request
            self.assertEqual((code, body["branch"], body["pull_request"]["number"]), (3, lc.RULES_BRANCH + "-2", 2), body)
        self.assertEqual(sh("git", "-C", str(self.remote), "rev-parse", lc.RULES_BRANCH), merged)
        self.assertIn("10. **A rule a later Scout adds.**", self.main_text("AGENTS.md", ref=lc.RULES_BRANCH + "-2"))

    def test_open_work_items_hear_how_to_take_the_lf_rule_even_when_main_is_already_lf(self):
        """On a protected main the branch step waits for the rules' pull request, fetch first, and comes again with the
        start that brings the merged rules in; only renormalizing CRLF files stays conditional."""
        self.protect_main()
        code, body = self.call("ana", *START, "--yes")
        self.assertEqual((code, body.get("needs")), (3, "rules-review"), body)
        self.assertNotIn("crlf", body, "main holds no CRLF files")
        self.assertTrue(body["active_branches"].startswith("Once the rules' pull request is merged, and not before"), body)
        self.assertIn("`git fetch origin`, then `git merge origin/main`", body["active_branches"])
        self.assertEqual(self.gh_stub("pr", "merge", str(body["pull_request"]["number"]), "--repo", "acme/team",
                                      "--squash").returncode, 0)
        code, body = self.call("ana", *START, "--yes")  # main stays protected: the merged rules arrive by fast-forward
        self.assertEqual((code, body["written_on_main"]), (0, []), body)
        self.assertTrue(body["active_branches"].startswith("The rules are on main now"), body)
        self.assertIn("`git fetch origin`, then `git merge origin/main`", body["active_branches"])
        self.assertIn("Checked line", body["active_branches"])
        code, again = self.call("ana", *START, "--yes")
        self.assertEqual((code, again.get("active_branches")), (0, None), "said when the rule comes in, not after")

    def test_a_start_that_writes_the_lf_rule_onto_main_says_the_rules_are_there(self):
        code, body = self.call("ana", *START, "--yes")
        self.assertEqual((code, body["written_on_main"]), (0, [".gitattributes", ".gitignore", "AGENTS.md"]), body)
        self.assertTrue(body["active_branches"].startswith("The rules are on main now"), body)

    def test_the_crlf_report_names_every_component_its_step_covers(self):
        """The step renormalizes every CRLF file, so the components it names are all of them, never a cut list."""
        classes = {f"force-app/main/default/classes/Legacy{n:02d}.cls": f"public class Legacy{n:02d} {{\r\n}}\r\n"
                   for n in range(55)}
        self.push_to_main(dict(classes, **{"docs/README.txt": "Notes\r\n"}), "an older project saved on Windows")
        code, body = self.call("ana", *START, "--yes")
        self.assertEqual(code, 0, body)
        report = body["crlf"]
        self.assertEqual(report["count"], 56)
        self.assertEqual(report["components"], sorted(f"ApexClass:Legacy{n:02d}" for n in range(55)), "all 55, none cut")
        self.assertEqual(sorted(report["files"]), sorted([*classes, "docs/README.txt"]))
        self.assertEqual(report["other_files"], ["docs/README.txt"])
        self.assertEqual(len(report["preview"]), 10, "only the preview is short")
        self.assertIn("git add --renormalize -- <its files>", report["next"])

    def test_a_plugin_list_that_failed_never_says_the_guard_is_off(self):
        """Only a successful, readable plugin list without sf-mp proves the guard is off; anything else is unknown,
        and unguard reports no success on it."""
        self.team_up()  # Bob's guard is bound
        bound = self.tmp / "bob" / "sf-data" / "sf-mp" / "bound-orgs.json"
        code, again = self.call("bob", *JOIN, "--yes", "--no-guard", STUB_PLUGINS="fail")
        self.assertEqual((code, again["guard"]["binding"]), (0, "unknown"), again)
        self.assertIn("can't tell", again["guard"]["note"])
        self.assertEqual(self.member_record("bob-example-com")["guard"], "unknown")
        self.assertEqual(self.call("ana", "status")[1]["guard_off"], ["Bob Builder"], "not proven on, so it's listed")
        for listing in ("fail", "garbage"):
            code, body = self.call("bob", "unguard", "--yes", STUB_PLUGINS=listing)
            self.assertEqual(code, 1, body)
            self.assertIn("can't tell whether the guard is on", body["reason"])
        self.assertIn(COMMON[:15], json.loads(bound.read_text())["orgs"], "nothing was taken off")
        self.assertEqual(self.member_record("bob-example-com")["guard"], "unknown", "and nothing claimed")

    def test_a_missing_answer_after_the_promotion_went_out_says_where_the_delivery_stands(self):
        """The adapters can't know what an earlier step changed, so they say nothing about it; once the promotion is
        submitted, the delivery's answer keeps its phase and request and says to resume."""
        def ask_once(_seconds):
            if sys._getframe(1).f_code.co_name == "poll_promotion" and not getattr(ask_once, "done", False):
                ask_once.done = True
                self.assertEqual(self.call_quiet("ana", "stop", "--wi", wi)[0], 0)
        self.options(status_late=3)
        wi = self.plain_delivery(106)
        code, plan = self.call("ana", "deliver", "--wi", wi)
        with mock.patch.object(lc.time, "sleep", ask_once):
            code, body = self.call("ana", "deliver", "--wi", wi, "--yes", "--plan-id", plan["plan_id"])
        self.assertIn("while request", body.get("reason", ""), body)
        with self.as_who("ana"):
            token = lc.read_record(self.team_id("ana"), wi)["token"]
        self.options(silent_queries=["ORDER BY CreatedDate DESC LIMIT 1"])  # the promotion's record, read without rows
        code, body = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual(code, 1, body)
        self.assertIn("answered without its records", body["reason"])
        self.assertNotIn("nothing changed", body["reason"])
        self.assertIn(f"past its merge (promoting, request {token}), so deliver --wi {wi} --resume picks up", body["reason"])
        self.assertEqual((body["resume"], body["phase"], body["token"]), (True, "promoting", token))
        self.options(silent_queries=[])
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertEqual(len(self.submitted()), 1, "one promotion, never a second")


    def test_a_merged_pull_request_from_a_deleted_branch_of_the_same_name_never_retires_a_pending_proposal(self):
        """A deleted branch's name comes back for the next proposal; the earlier pull request, merged from another
        commit, says nothing about the pending one, which is reused rather than passed over."""
        self.protect_main()
        code, body = self.call("ana", *START, "--yes")
        self.assertEqual((code, body.get("branch")), (3, lc.RULES_BRANCH), body)
        self.assertEqual(self.gh_stub("pr", "merge", str(body["pull_request"]["number"]), "--repo", "acme/team",
                                      "--squash").returncode, 0)
        sh("git", "-C", str(self.remote), "branch", "-D", lc.RULES_BRANCH)  # the team deletes merged branches
        self.assertEqual(self.call("ana", *START, "--yes")[0], 0, "the rules are on main")
        later = lc.AGENTS_MD + "10. **A rule a later Scout adds.**\n"
        with mock.patch.object(lc, "AGENTS_MD", later):
            code, body = self.call("ana", *START, "--yes", SCOUT_TEAM_GH=str(self.tmp / "no-gh"))  # no pull request yet
            self.assertEqual((code, body["branch"], body["pull_request"]), (3, lc.RULES_BRANCH, None), body)
            pending = sh("git", "-C", str(self.remote), "rev-parse", lc.RULES_BRANCH)
            code, body = self.call("ana", *START, "--yes")  # gh is back: the pending proposal gets its pull request
        self.assertEqual((code, body.get("needs"), body["branch"]), (3, "rules-review", lc.RULES_BRANCH), body)
        self.assertEqual(body["pull_request"]["number"], 2, "a pull request for the pending proposal")
        self.assertEqual(sh("git", "-C", str(self.remote), "rev-parse", lc.RULES_BRANCH), pending, "kept as it was")
        self.assertEqual(sh("git", "-C", str(self.remote), "branch", "--list", lc.RULES_BRANCH + "-*"), "",
                         "no second proposal beside it")


    def test_sf_mps_record_is_read_where_the_cli_keeps_its_data(self):
        """SF_DATA_DIR, then SFDX_DATA_DIR (the CLI's alias), then the XDG data home, then ~/.local/share."""
        home = self.tmp / "home"
        cases = [({"SF_DATA_DIR": "/data/sf", "SFDX_DATA_DIR": "/data/sfdx"}, Path("/data/sf")),
                 ({"SFDX_DATA_DIR": "/data/sfdx", "XDG_DATA_HOME": "/data/xdg"}, Path("/data/sfdx")),
                 ({"XDG_DATA_HOME": "/data/xdg"}, Path("/data/xdg/sf")),
                 ({}, home / ".local" / "share" / "sf")]
        for env, folder in cases:
            with self.subTest(env=env), mock.patch.dict(os.environ, {"HOME": str(home)}):
                for key in ("SF_DATA_DIR", "SFDX_DATA_DIR", "XDG_DATA_HOME"):
                    os.environ.pop(key, None)
                os.environ.update(env)
                self.assertEqual(lc.sf_mp_registry(), folder / "sf-mp" / "bound-orgs.json")
        legacy = self.tmp / "legacy-data"
        (legacy / "sf-mp").mkdir(parents=True)
        (legacy / "sf-mp" / "bound-orgs.json").write_text(json.dumps({"orgs": {COMMON[:15]: {"role": "guard", "checkout": "x"}}}))
        with mock.patch.dict(os.environ, {"SFDX_DATA_DIR": str(legacy)}), \
                mock.patch.object(lc, "sf_mp_plugin", lambda: ("installed", team.sf_mp_version())):
            os.environ.pop("SF_DATA_DIR", None)
            self.assertEqual(lc.guard_binding(COMMON[:15]), ("on", None), "a guard bound under the alias is found")


    def test_a_lock_left_by_a_process_that_died_is_named_with_the_way_to_clear_it(self):
        """Waiting can't free a lock whose owner is gone, so unguard says whose it is and how to clear it, and changes
        nothing until it's cleared."""
        self.team_up()  # Bob's guard is bound
        bound = self.tmp / "bob" / "sf-data" / "sf-mp" / "bound-orgs.json"
        lock = Path(str(bound) + ".lock")
        lock.write_text(json.dumps({"pid": 999999, "host": "a-builders-mac", "at": "2026-10-21T01:00:00Z"}))
        with mock.patch.object(lc.time, "sleep", lambda seconds: None):  # the retries, without their waits
            code, body = self.call("bob", "unguard", "--yes")
        self.assertEqual(code, 1, body)
        self.assertIn("process 999999 on a-builders-mac", body["reason"])
        self.assertIn(str(lock), body["reason"])
        self.assertIn("once it's gone", body["reason"])
        self.assertIn("delete the lock file, then run unguard again", body["reason"])
        self.assertEqual((body["lock"], body["owner"]["pid"]), (str(lock), 999999))
        self.assertIn(COMMON[:15], json.loads(bound.read_text())["orgs"], "nothing was taken off")
        lock.unlink()
        code, done = self.call("bob", "unguard", "--yes")
        self.assertEqual((code, done["removed"]), (0, True), done)


class LifecycleOnWindowsTests(unittest.TestCase):
    """Team mode runs on macOS for now: on Windows the Lifecycle Center helper refuses before any step, and the prompt
    hook's form stays silent. The module imports there too (it skips fcntl), so this class runs on every runner."""

    def test_the_lifecycle_helper_refuses_on_windows_before_any_step(self):
        handler = mock.Mock(side_effect=AssertionError("no team step runs on Windows"))
        out = io.StringIO()
        with mock.patch.object(lc.os, "name", "nt"), mock.patch.object(lc, "cmd_status", handler), \
                contextlib.redirect_stdout(out):
            code = lc.main(["status"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["reason"], lc.ON_WINDOWS)
        self.assertIn("runs on macOS for now; on Windows it comes in a later release", lc.ON_WINDOWS)
        handler.assert_not_called()
        quiet = io.StringIO()
        updates = mock.Mock(side_effect=AssertionError("no team step runs on Windows"))
        with mock.patch.object(lc.os, "name", "nt"), mock.patch.object(lc, "cmd_updates", updates), \
                contextlib.redirect_stdout(quiet):
            self.assertEqual(lc.main(["updates", "--hook"]), 0, "the prompt hook stays silent")
        self.assertEqual(quiet.getvalue(), "")
        updates.assert_not_called()


if __name__ == "__main__":
    unittest.main()
