"""Lifecycle Center mode (scripts/scout_lc.py): adopting a pipeline as a team, package start, check and hand-over, and
the captain's delivery (its checks, the revision and org copies a yes binds to, the test gate, the sync, resume and
recovery), back-flow and updates. Real Git against a local bare repository; `sf` and `gh` are stand-ins
(tests/fixtures/lc_stub_*.py) that answer in the shapes recorded live (tests/fixtures/lc_cli_shapes.json). Dana is a
builder without Scout: her own clone, plain Git and the official CLI."""
import contextlib
import io
import json
import os
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


def sh(*args, cwd=None):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(f"{' '.join(map(str, args))} failed: {result.stderr.strip()}")
    return result.stdout.strip()


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
               "STUB_GUARD": team.sf_mp_version(), "SCOUT_TEAM_WATCH_OFF": ""}
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
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer), mock.patch.object(lc, "SYNC_WAIT", 0), mock.patch.object(lc, "STATUS_WAIT", 0):
                code = lc.main([str(a) for a in args])
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
                               "--build-org", "bob-sbx", "--yes")
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
        code, done = self.call("ana", "deliver", "--wi", wi, "--resume")
        self.assertEqual((code, done.get("outcome")), (0, "verified"), done)
        self.assertEqual([p["status"] for p in self.hub()["promotions"]], ["SUCCESS"])

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


if __name__ == "__main__":
    unittest.main()
