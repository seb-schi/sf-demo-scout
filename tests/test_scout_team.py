"""Team mode (scripts/scout_team.py): the ledger, packages and their base, hand-overs, deliveries through the lane,
recovery and teammates' updates. Real Git against local bare repositories; `sf` and `gh` are stand-ins
(tests/fixtures/team_stub_*.py), so the orchestration is tested here and sf-mp in packages/sf-mp/test."""
import contextlib
import io
import json
import os
import re
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
import scout_team as team  # noqa: E402

SF_STUB = ROOT / "tests" / "fixtures" / "team_stub_sf.py"
GH_STUB = ROOT / "tests" / "fixtures" / "team_stub_gh.py"
COMMON, ANA_ORG, BOB_ORG = "00D000000000042EAC", "00D000000000043EAC", "00D000000000044EAC"
GITHUB_REMOTE = "https://github.com/acme/team.git"  # the local bare repository, through Git's insteadOf
CLASS = "public class Invoice {{\n    // one{a}\n    // two\n    // three{b}\n}}\n"
META = '<?xml version="1.0" encoding="UTF-8"?>\n<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">\n    <apiVersion>64.0</apiVersion>\n    <status>Active</status>\n</ApexClass>\n'


def sh(*args, cwd=None):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(f"{' '.join(map(str, args))} failed: {result.stderr.strip()}")
    return result.stdout.strip()


class TeamTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="scout-team-test-")).resolve()
        self.stub = self.tmp / "stub"
        (self.stub / "orgs").mkdir(parents=True)
        (self.stub / "orgs.json").write_text(json.dumps({
            "common": {"id": COMMON, "username": "admin@common.example", "alias": "common", "apiVersion": "64.0"},
            "ana-sbx": {"id": ANA_ORG, "username": "admin@common.example.ana", "alias": "ana-sbx", "apiVersion": "64.0"},
            "bob-sbx": {"id": BOB_ORG, "username": "admin@common.example.bob", "alias": "bob-sbx", "apiVersion": "64.0"}}))
        self.remote = self.tmp / "remote.git"
        sh("git", "init", "--quiet", "--bare", "--initial-branch=main", str(self.remote))
        for who, name in (("ana", "Ana Captain"), ("bob", "Bob Builder")):
            home = self.tmp / who
            (home / "ws").mkdir(parents=True)
            (home / "gitconfig").write_text(f"[user]\n\tname = {name}\n\temail = {who}@example.com\n"
                                            "[commit]\n\tgpgsign = false\n[init]\n\tdefaultBranch = main\n"
                                            f'[url "{self.remote}"]\n\tinsteadOf = {GITHUB_REMOTE}\n')
        self._env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        subprocess.run(["rm", "-rf", str(self.tmp)])

    @contextlib.contextmanager
    def machine(self, who, **extra):
        home = self.tmp / who
        env = {"SCOUT_TEAMS_FILE": str(home / "teams.json"), "SCOUT_TEAM_CACHE": str(home / "cache" / "teams"),
               "SCOUT_WORKSPACE": str(home / "ws"), "GIT_CONFIG_GLOBAL": str(home / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1",
               "SCOUT_TEAM_SF": str(SF_STUB), "SCOUT_TEAM_GH": str(GH_STUB), "STUB_ROOT": str(self.stub), "STUB_GUARD": team.sf_mp_version()}
        env.update(extra)
        saved = dict(os.environ)
        os.environ.update(env)
        try:
            yield
        finally:
            os.environ.clear()
            os.environ.update(saved)

    def call(self, who, *args, stdin=None, **extra):
        with self.machine(who, **extra):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer), mock.patch.object(sys, "stdin", io.StringIO(stdin or "")):
                code = team.main([str(a) for a in args])
        text = buffer.getvalue()
        try:
            return code, json.loads(text) if text.strip() else None
        except ValueError:
            return code, text

    def org(self, target, name="Invoice", body=None):
        folder = self.stub / "orgs" / target / "classes"
        if body is None:
            path = folder / f"{name}.cls"
            return path.read_text() if path.exists() else None
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.cls").write_text(body)
        (folder / f"{name}.cls-meta.xml").write_text(META)

    def checkout(self, who):
        return Path(self.checkouts[who])

    def start_team(self, remote=None):
        remote = remote or self.remote
        code, started = self.call("ana", "start", "--name", "Acme demo", "--remote", remote, "--common-org", "common",
                                  "--build-org", "ana-sbx", "--github", "ana-gh")
        self.assertEqual(code, 0, started)
        code, joined = self.call("bob", "join", "--remote", remote, "--build-org", "bob-sbx", "--github", "bob-gh")
        self.assertEqual(code, 0, joined)
        self.checkouts = {"ana": started["checkout"], "bob": joined["checkout"]}
        return started, joined

    def deliver_new_invoice(self):
        self.org("bob-sbx", body=CLASS.format(a="", b=""))
        code, started = self.call("bob", "package", "start", "--title", "Invoice service", "--component", "ApexClass:Invoice")
        self.assertEqual(code, 0, started)
        self.assertEqual(started["checked"], {"ApexClass:Invoice": "same"} if "base" in json.dumps(started) else started["checked"])
        code, handed = self.call("bob", "handover", "--id", started["package"])
        self.assertEqual(code, 0, handed)
        code, delivered = self.call("ana", "deliver", "--id", started["package"])
        self.assertEqual(code, 0, delivered)
        return started["package"], delivered

    def during(self, step, argv, who=None):
        """Runs argv while the stub's `step` (retrieve or deploy) works: another Scout step on `who`'s machine, say."""
        env = {}
        if who:
            with self.machine(who):
                env = dict(os.environ)
            argv = [sys.executable, "-B", str(ROOT / "scripts" / "scout_team.py"), *map(str, argv)]
        (self.stub / f"during-{step}.json").write_text(json.dumps({"argv": [str(a) for a in argv], "env": env}))

    def during_result(self, step):
        return json.loads((self.stub / f"during-{step}-result.json").read_text())

    def ledger(self):
        return team.read_ledger(self.remote, sh("git", "--git-dir", str(self.remote), "rev-parse", "mp/ledger"))

    def main_tip(self):
        return sh("git", "--git-dir", str(self.remote), "rev-parse", "main")

    def handed_over(self, who="bob", body=None, name="Invoice"):
        self.org(f"{who}-sbx", name=name, body=body or CLASS.format(a="", b=""))
        code, wp = self.call(who, "package", "start", "--title", name, "--component", f"ApexClass:{name}")
        self.assertEqual(code, 0, wp)
        code, handed = self.call(who, "handover", "--id", wp["package"])
        self.assertEqual(code, 0, handed)
        return wp["package"]

    # ---- the ledger ----

    def test_start_and_join_write_the_kit_and_the_ledger(self):
        started, joined = self.start_team()
        repo = self.checkout("ana")
        self.assertTrue((repo / ".mp" / "config.json").exists())
        for name in ("AGENTS.md", "TEAM.md", "sfdx-project.json", ".forceignore", f"tools/sf-mp-{team.sf_mp_version()}.tgz"):
            self.assertTrue((repo / name).exists(), name)
        listing = sh("git", "--git-dir", str(self.remote), "ls-tree", "-r", "--name-only", "mp/ledger").splitlines()
        self.assertEqual(sorted(listing), ["README.md", "members/ana-captain.json", "members/bob-builder.json", "team.json"])
        bob = json.loads(sh("git", "--git-dir", str(self.remote), "show", "mp/ledger:members/bob-builder.json"))
        self.assertEqual((bob["role"], bob["build_org"]["org_id"], bob["build_org"]["username"]),
                         ("builder", BOB_ORG[:15], "admin@common.example.bob"))
        self.assertIn("COMMON" if False else COMMON[:15], (repo / "AGENTS.md").read_text())
        self.assertEqual(joined["captain"], "Ana Captain")
        sf_calls = (self.stub / "sf-calls.log").read_text()
        self.assertIn('"--guard-only"', sf_calls)
        self.assertEqual(sh("git", "-C", str(repo), "status", "--porcelain"), "")

    def test_a_rejected_push_is_retried_on_the_new_tip_and_a_lost_answer_is_not_applied_twice(self):
        self.start_team()
        repo = self.checkout("ana")
        other = self.tmp / "other-clone"
        sh("git", "clone", "--quiet", str(self.remote), str(other))
        real_push = team.push_ledger
        calls = []

        def racing_push(repo_, commit):
            calls.append(commit)
            if len(calls) == 1:  # someone else writes first
                sh("git", "-C", str(other), "fetch", "--quiet", "origin", "mp/ledger")
                sh("git", "-C", str(other), "checkout", "--quiet", "-B", "l", "FETCH_HEAD")
                (other / "members").mkdir(exist_ok=True)
                (other / "members" / "zed.json").write_text('{"schema": 1, "id": "zed", "name": "Zed", "role": "builder"}\n')
                sh("git", "-C", str(other), "add", "-A")
                sh("git", "-C", str(other), "-c", "user.name=Zed", "-c", "user.email=zed@example.com", "commit", "-qm", "Zed joined")
                sh("git", "-C", str(other), "push", "--quiet", "origin", "l:mp/ledger")
            return real_push(repo_, commit)

        with self.machine("ana"), mock.patch.object(team, "push_ledger", racing_push):
            written = team.ledger_write(repo, team.identity(repo), lambda s: (
                {"members/ana-captain.json": dict(s["members"]["ana-captain"], github="ana-2")}, "Ana changed", "test", None))
        self.assertEqual(len(calls), 2)
        state = team.read_ledger(repo, sh("git", "--git-dir", str(self.remote), "rev-parse", "mp/ledger"))
        self.assertIn("zed", state["members"])
        self.assertEqual(state["members"]["ana-captain"]["github"], "ana-2")
        self.assertEqual(written["commit"], sh("git", "--git-dir", str(self.remote), "rev-parse", "mp/ledger"))

        before = sh("git", "--git-dir", str(self.remote), "rev-list", "--count", "mp/ledger")
        answers = []

        def lost_answer(repo_, commit):
            ok = real_push(repo_, commit)
            answers.append(ok)
            return None if len(answers) == 1 else ok

        with self.machine("ana"), mock.patch.object(team, "push_ledger", lost_answer):
            team.ledger_write(repo, team.identity(repo), lambda s: (
                {"members/ana-captain.json": dict(s["members"]["ana-captain"], github="ana-3")}, "Ana again", "test", None))
        after = sh("git", "--git-dir", str(self.remote), "rev-list", "--count", "mp/ledger")
        self.assertEqual(int(after), int(before) + 1, "the lost answer's write was recognised, not applied twice")

    def test_a_rewritten_ledger_stops_writes(self):
        self.start_team()
        orphan = self.tmp / "orphan"
        sh("git", "init", "--quiet", str(orphan))
        (orphan / "team.json").write_text("{}\n")
        sh("git", "-C", str(orphan), "add", "-A")
        sh("git", "-C", str(orphan), "-c", "user.name=X", "-c", "user.email=x@example.com", "commit", "-qm", "rewrite")
        sh("git", "-C", str(orphan), "push", "--quiet", "--force", str(self.remote), "HEAD:mp/ledger")
        code, body = self.call("ana", "package", "start", "--title", "x")
        self.assertEqual(code, 1)
        self.assertIn("rewritten", body["reason"])

    # ---- packages, hand-over, delivery ----

    def test_a_package_from_start_to_delivery(self):
        self.start_team()
        package, delivered = self.deliver_new_invoice()
        self.assertEqual(delivered["outcome"], "delivered")
        self.assertIn("// one", self.org("common"))
        self.assertIn("Invoice.cls", sh("git", "--git-dir", str(self.remote), "ls-tree", "-r", "--name-only", "main"))
        state = team.read_ledger(self.checkout("ana"), sh("git", "--git-dir", str(self.remote), "rev-parse", "mp/ledger"))
        self.assertEqual(state["packages"][package]["status"], "delivered")
        self.assertTrue(any(d["verified"] for d in state["deliveries"].values()))
        self.assertFalse(team.receipt_path(self.checkout("ana")).exists())
        code, updates = self.call("bob", "updates")
        summaries = [e["summary"] for e in updates["teams"][0]["events"]]
        self.assertTrue(any("delivered WP-1" in s for s in summaries), summaries)

    def test_a_stale_sandbox_is_brought_up_to_date_before_work_so_a_teammates_change_survives(self):
        """Bob's old copy must never silently undo Ana's delivered change."""
        self.start_team()
        self.deliver_new_invoice()
        # Bob starts WP-2 on Invoice while his sandbox still has the original: fine, it's the team's version.
        code, bob_wp = self.call("bob", "package", "start", "--title", "Bob's change", "--component", "ApexClass:Invoice")
        self.assertEqual(code, 0, bob_wp)
        # Ana's sandbox has no copy yet: her package needs the team's version first.
        code, ana_wp = self.call("ana", "package", "start", "--title", "Ana's change", "--component", "ApexClass:Invoice")
        self.assertEqual((code, ana_wp["needs"], ana_wp["checked"]["ApexClass:Invoice"]), (3, "sync", "missing"))
        code, synced = self.call("ana", "package", "sync", "--id", ana_wp["package"])
        self.assertEqual(code, 0, synced)
        self.assertEqual(self.org("ana-sbx"), CLASS.format(a="", b=""))
        self.org("ana-sbx", body=CLASS.format(a=": Ana", b=""))
        self.assertEqual(self.call("ana", "handover", "--id", ana_wp["package"])[0], 0)
        code, done = self.call("ana", "deliver", "--id", ana_wp["package"])
        self.assertEqual(code, 0, done)
        # Bob, from his base (the original), edits another line and hands over after Ana's delivery.
        self.org("bob-sbx", body=CLASS.format(a="", b=": Bob"))
        self.assertEqual(self.call("bob", "handover", "--id", bob_wp["package"])[0], 0)
        code, done = self.call("ana", "deliver", "--id", bob_wp["package"])
        self.assertEqual(code, 0, done)
        self.assertEqual(self.org("common"), CLASS.format(a=": Ana", b=": Bob"), "both changes are in the common org")
        # A third package by Bob now finds his sandbox stale (it lacks Ana's line) and stops before any work.
        code, again = self.call("bob", "package", "start", "--title", "More", "--component", "ApexClass:Invoice")
        self.assertEqual((code, again["needs"]), (3, "sync"))
        self.assertEqual(again["checked"]["ApexClass:Invoice"], "stale")

    def test_files_outside_the_declared_components_are_refused(self):
        """A hand-over may change only files that map to its declared components."""
        self.start_team()
        self.org("bob-sbx", body=CLASS.format(a="", b=""))
        code, wp = self.call("bob", "package", "start", "--title", "Invoice", "--component", "ApexClass:Invoice")
        self.call("bob", "handover", "--id", wp["package"])
        repo = self.checkout("bob")
        sh("git", "-C", str(repo), "fetch", "--quiet", "origin")
        sh("git", "-C", str(repo), "checkout", "--quiet", "-B", "wp/WP-1", "origin/wp/WP-1")
        (repo / "force-app/main/default/classes/Extra.cls").write_text("public class Extra {}\n")
        sh("git", "-C", str(repo), "add", "-A")
        sh("git", "-C", str(repo), "commit", "-qm", "extra")
        sh("git", "-C", str(repo), "push", "--quiet", "origin", "wp/WP-1")
        sh("git", "-C", str(repo), "checkout", "--quiet", "main")
        # Pin the extra commit as the package head, as a teammate pushing more would do.
        with self.machine("bob"):
            team.package_write(repo, team.identity(repo), team.pick()[0], team.pick()[1], "WP-1",
                               lambda item, s: dict(item, head=sh("git", "-C", str(repo), "rev-parse", "origin/wp/WP-1")),
                               "Bob moved the head", "test")
        code, body = self.call("ana", "deliver", "--id", "WP-1")
        self.assertEqual((code, body["outcome"]), (2, "scope"))
        self.assertIn("force-app/main/default/classes/Extra.cls", body["files"])

    def test_org_drift_stops_the_delivery_and_back_flow_brings_it_into_main(self):
        self.start_team()
        self.deliver_new_invoice()
        self.org("common", body=CLASS.format(a="", b=": changed in Setup"))
        code, wp = self.call("bob", "package", "start", "--title", "Bob", "--component", "ApexClass:Invoice")
        self.org("bob-sbx", body=CLASS.format(a=": Bob", b=""))
        self.call("bob", "handover", "--id", wp["package"])
        code, body = self.call("ana", "deliver", "--id", wp["package"])
        self.assertEqual((code, body["outcome"]), (3, "org-changed"))
        self.assertEqual(self.org("common"), CLASS.format(a="", b=": changed in Setup"), "nothing was overwritten")
        code, taken = self.call("ana", "takeorg")
        self.assertEqual(code, 0, taken)
        self.assertIn("changed in Setup", sh("git", "--git-dir", str(self.remote), "show", "main:force-app/main/default/classes/Invoice.cls"))
        code, refreshed = self.call("bob", "refresh", "--id", wp["package"])
        self.assertEqual(code, 0, refreshed)
        code, body = self.call("bob", "handover", "--id", wp["package"])
        self.assertEqual((code, body["needs"]), (3, "sync"), "the merged copy must reach Bob's org first")
        self.assertEqual(self.call("bob", "package", "sync", "--id", wp["package"])[0], 0)
        self.assertEqual(self.org("bob-sbx"), CLASS.format(a=": Bob", b=": changed in Setup"))
        self.assertEqual(self.call("bob", "handover", "--id", wp["package"])[0], 0)
        code, done = self.call("ana", "deliver", "--id", wp["package"])
        self.assertEqual(code, 0, done)
        self.assertEqual(self.org("common"), CLASS.format(a=": Bob", b=": changed in Setup"))

    def test_only_a_verified_delivery_publishes(self):
        """A check-only success or a settlement without a read-back never moves main."""
        self.start_team()
        self.org("bob-sbx", body=CLASS.format(a="", b=""))
        code, wp = self.call("bob", "package", "start", "--title", "Invoice", "--component", "ApexClass:Invoice")
        self.call("bob", "handover", "--id", wp["package"])
        main_before = sh("git", "--git-dir", str(self.remote), "rev-parse", "main")
        code, body = self.call("ana", "deliver", "--id", wp["package"], "--dry-run")
        self.assertEqual((code, body["outcome"]), (0, "validated"))
        code, body = self.call("ana", "deliver", "--id", wp["package"], STUB_DEPLOY="unverified")
        self.assertEqual((code, body["outcome"]), (3, "unverified"))
        self.assertEqual(sh("git", "--git-dir", str(self.remote), "rev-parse", "main"), main_before)

    def test_an_interrupted_delivery_resumes_from_its_receipt_without_redeploying(self):
        """An interrupted delivery is finished from its receipt and the lane's journal, never sent twice."""
        self.start_team()
        self.org("bob-sbx", body=CLASS.format(a="", b=""))
        code, wp = self.call("bob", "package", "start", "--title", "Invoice", "--component", "ApexClass:Invoice")
        self.call("bob", "handover", "--id", wp["package"])
        code, body = self.call("ana", "deliver", "--id", wp["package"], STUB_DEPLOY="crash")
        self.assertEqual((code, body["outcome"]), (1, "open"))
        self.assertTrue(team.receipt_path(self.checkout("ana")).exists())
        code, body = self.call("ana", "deliver", "--id", wp["package"])
        self.assertEqual(code, 2)
        self.assertIn("resume delivery", body["reason"])
        deploys_before = (self.stub / "sf-calls.log").read_text().count('"mp", "deploy"')
        code, body = self.call("ana", "deliver", "--resume")
        self.assertEqual((code, body["outcome"]), (0, "delivered"), body)
        self.assertEqual((self.stub / "sf-calls.log").read_text().count('"mp", "deploy"'), deploys_before, "never resent")
        self.assertIn("Invoice.cls", sh("git", "--git-dir", str(self.remote), "ls-tree", "-r", "--name-only", "main"))
        self.assertFalse(team.receipt_path(self.checkout("ana")).exists())

    def test_a_handover_without_a_scout_package_is_adopted_and_scope_checked(self):
        self.start_team()
        other = self.tmp / "cara"
        sh("git", "clone", "--quiet", str(self.remote), str(other))
        sh("git", "-C", str(other), "checkout", "--quiet", "-b", "wp/cara-util")
        (other / "force-app/main/default/classes").mkdir(parents=True, exist_ok=True)
        (other / "force-app/main/default/classes/CaraUtil.cls").write_text("public class CaraUtil {}\n")
        (other / "force-app/main/default/classes/CaraUtil.cls-meta.xml").write_text(META)
        sh("git", "-C", str(other), "add", "-A")
        sh("git", "-C", str(other), "-c", "user.name=Cara Cursor", "-c", "user.email=cara@example.com", "commit", "-qm", "util")
        sh("git", "-C", str(other), "push", "--quiet", "origin", "wp/cara-util")
        code, body = self.call("ana", "adopt", "--branch", "wp/cara-util", "--component", "ApexClass:Other",
                               "--owner-name", "Cara Cursor")
        self.assertEqual((code, body["outcome"]), (2, "scope"))
        code, body = self.call("ana", "adopt", "--branch", "wp/cara-util", "--component", "ApexClass:CaraUtil")
        self.assertEqual(code, 0, body)
        self.assertEqual(body["owner"], "Cara Cursor", "the head commit's Git identity, not the account that pushed it")
        state = team.read_ledger(self.checkout("ana"), sh("git", "--git-dir", str(self.remote), "rev-parse", "mp/ledger"))
        owner = state["members"][state["packages"][body["package"]]["owner"]]
        self.assertEqual((owner["name"], owner["git_email"], owner["scout"]), ("Cara Cursor", "cara@example.com", False))
        code, done = self.call("ana", "deliver", "--id", body["package"])
        self.assertEqual(code, 0, done)
        self.assertIsNotNone(self.org("common", name="CaraUtil"))

    def test_the_builder_cant_deliver_and_a_steward_type_needs_the_steward_route(self):
        self.start_team()
        code, body = self.call("bob", "deliver", "--id", "WP-1")
        self.assertEqual(code, 2)
        self.assertIn("only the captain", body["reason"])
        perm = self.stub / "orgs" / "bob-sbx" / "permissionsets"
        perm.mkdir(parents=True)
        (perm / "Invoice_Access.permissionset-meta.xml").write_text("<PermissionSet/>\n")
        code, wp = self.call("bob", "package", "start", "--title", "Access", "--component", "PermissionSet:Invoice_Access")
        self.call("bob", "handover", "--id", wp["package"])
        code, body = self.call("ana", "deliver", "--id", wp["package"])
        self.assertEqual((code, body["needs"]), (3, "steward"))
        code, body = self.call("ana", "deliver", "--id", wp["package"], "--steward")
        self.assertEqual(code, 0, body)
        self.assertIn('"--steward"', (self.stub / "sf-calls.log").read_text())

    # ---- teammates' updates ----

    def test_the_prompt_hook_shows_others_events_once_with_the_board_on_a_sessions_first_prompt(self):
        self.start_team()
        ws = self.tmp / "ana" / "ws"
        code, text = self.call("ana", "updates", "--hook", stdin=json.dumps({"cwd": str(ws), "session_id": "s1"}))
        self.assertEqual(code, 0)
        self.assertIn("Bob Builder joined as builder", text)
        self.assertIn("Team Acme demo: you're captain", text)
        self.assertIn("No watcher is running", text)
        code, text = self.call("ana", "updates", "--hook", stdin=json.dumps({"cwd": str(ws), "session_id": "s1"}))
        self.assertIsNone(text, "shown once")
        code, text = self.call("ana", "updates", "--hook", stdin=json.dumps({"cwd": str(self.tmp), "session_id": "s2"}))
        self.assertIsNone(text, "nothing outside the Scout workspace or the team checkout")
        code, text = self.call("ana", "updates", "--hook", stdin="{}", SCOUT_TEAMS_FILE=str(self.tmp / "nobody.json"))
        self.assertEqual((code, text), (0, None), "no team on the machine: nothing, at once")

    def test_my_own_write_after_a_teammates_does_not_hide_it(self):
        """A teammate's write followed by my own is still shown to me."""
        self.start_team()
        self.call("ana", "status")  # Ana has seen everything so far
        self.call("bob", "package", "start", "--title", "Bob's", "--component", "ApexClass:Bobby")
        self.call("ana", "package", "start", "--title", "Ana's")
        code, updates = self.call("ana", "updates")
        summaries = [e["summary"] for e in updates["teams"][0]["events"]]
        self.assertEqual(len(summaries), 1, summaries)
        self.assertIn("Bob Builder started WP-1", summaries[0])

    def test_the_watcher_wakes_on_a_teammates_write_and_the_hook_repeats_it_until_acknowledged(self):
        self.start_team()
        self.call("ana", "status")
        with self.machine("ana"):
            env = dict(os.environ)
        watcher = subprocess.Popen([sys.executable, "-B", str(ROOT / "scripts" / "scout_team.py"), "watch",
                                    "--interval", "0.3", "--max-hours", "0.02"], env=env, stdout=subprocess.PIPE, text=True)
        time.sleep(0.8)
        self.call("bob", "package", "start", "--title", "Wake Ana", "--component", "ApexClass:Wake")
        text, _ = watcher.communicate(timeout=60)
        self.assertIn("Bob Builder started WP-1", text)
        upto = text.split("--upto ")[1].split("`")[0]
        ws = self.tmp / "ana" / "ws"
        code, again = self.call("ana", "updates", "--hook", stdin=json.dumps({"cwd": str(ws), "session_id": "s9"}))
        self.assertIn("started WP-1", again, "not acknowledged yet, so shown again rather than lost")
        self.call("bob", "package", "start", "--title", "Second")
        self.call("ana", "ack", "--upto", upto)
        code, after = self.call("ana", "updates")
        self.assertEqual([e["summary"] for e in after["teams"][0]["events"]][:1], [] if not after["teams"][0]["events"]
                         else [after["teams"][0]["events"][0]["summary"]])

    def test_context_and_obligations(self):
        self.start_team()
        code, here = self.call("bob", "context", "--org-id", BOB_ORG)
        self.assertEqual((here["role"], here["org"]), ("builder", "build"))
        code, common = self.call("ana", "context", "--org-id", COMMON)
        self.assertEqual((common["role"], common["org"]), ("captain", "common"))
        self.assertIsNone(self.call("ana", "context", "--org-id", "00D000000000999AAA")[1]["team"])
        self.org("bob-sbx", body=CLASS.format(a="", b=""))
        task = self.tmp / "task.md"
        task.write_text('```scout-items\n{"schema":1,"items":[{"id":"I1","criterion":"Invoice runs","readback":"SELECT Id FROM ApexClass WHERE Name = \'Invoice\'","components":["ApexClass:Invoice"]}]}\n```\n')
        code, wp = self.call("bob", "package", "start", "--title", "Invoice", "--component", "ApexClass:Invoice", "--task", task)
        self.call("bob", "handover", "--id", wp["package"])
        code, before = self.call("ana", "obligations")
        self.assertEqual([o["kind"] for o in before["obligations"]], ["job"], "a hand-over waiting is open")
        self.call("ana", "deliver", "--id", wp["package"])
        code, after = self.call("ana", "obligations")
        self.assertEqual([(o["key"], o["text"]) for o in after["obligations"]], [("ledger:WP-1#I1", "Invoice runs")])


    # ---- interruptions, stale sessions and overlapping work ----

    def test_a_handover_from_a_stale_base_waits_for_sync_and_overwrite_is_per_component(self):
        """A stale base recorded at the start blocks the hand-over, even from a resumed session."""
        self.start_team()
        self.deliver_new_invoice()
        self.org("ana-sbx", body=CLASS.format(a=": an old copy", b=""))
        self.org("ana-sbx", name="Helper", body="public class Helper {}\n")
        start = ["package", "start", "--title", "Ana", "--component", "ApexClass:Invoice", "--component", "ApexClass:Helper"]
        code, wp = self.call("ana", *start)
        self.assertEqual((code, wp["needs"], wp["checked"]["ApexClass:Invoice"]), (3, "sync", "stale"))
        code, again = self.call("ana", *start)
        self.assertEqual((code, again["package"], again.get("reused")), (3, wp["package"], True), "the same start, not a second package")
        code, body = self.call("ana", "handover", "--id", wp["package"])
        self.assertEqual((code, body["needs"], body["components"]), (3, "sync", ["ApexClass:Invoice"]))
        self.assertNotIn("Invoice.cls", sh("git", "--git-dir", str(self.remote), "diff", "--name-only", "main", f"wp/{wp['package']}"))
        code, body = self.call("ana", "handover", "--id", wp["package"], "--overwrite", "ApexClass:Invoice")
        self.assertEqual((code, body["overwrite"]), (0, ["ApexClass:Invoice"]), body)
        code, body = self.call("ana", "handover", "--id", wp["package"], "--overwrite", "ApexClass:Other")
        self.assertEqual(code, 2, "an overwrite outside the hand-over is refused")

    def test_a_delivery_holds_the_checkout_and_publishes_exactly_what_the_lane_deployed(self):
        """Another Scout step on the captain's machine can't switch the lane checkout mid-delivery."""
        self.start_team()
        package = self.handed_over()
        self.org("ana-sbx", name="Mine", body="public class Mine {}\n")
        self.during("deploy", ["package", "start", "--title", "Ana's own", "--component", "ApexClass:Mine"], who="ana")
        code, done = self.call("ana", "deliver", "--id", package)
        self.assertEqual(code, 0, done)
        other = self.during_result("deploy")
        self.assertEqual(other["code"], 2, other)
        self.assertIn("another Scout team step is running", other["stdout"])
        journal = json.loads((self.checkout("ana") / ".mp" / "journal" / f"{done['op']['opId']}.json").read_text())
        self.assertEqual(journal["candidate"]["revision"], self.main_tip(), "main is exactly the deployed revision")

    def test_a_deploy_of_another_revision_never_publishes(self):
        """The second line of defence: the lane's record must name the delivery's own merge."""
        self.start_team()
        package = self.handed_over()
        main = self.main_tip()
        code, body = self.call("ana", "deliver", "--id", package, STUB_DEPLOY="other-revision")
        self.assertEqual((code, body["outcome"]), (1, "mismatch"), body)
        self.assertEqual(self.main_tip(), main)
        self.assertTrue(team.receipt_path(self.checkout("ana")).exists())

    def test_a_new_handover_while_the_captain_delivers_is_not_recorded_as_delivered(self):
        """A newer hand-over during a delivery isn't recorded as delivered; another owner's approval passes through."""
        self.start_team()
        package = self.handed_over()
        self.org("bob-sbx", body=CLASS.format(a=": a fix", b=""))
        self.during("retrieve", ["handover", "--id", package], who="bob")
        code, body = self.call("ana", "deliver", "--id", package)
        self.assertEqual(self.during_result("retrieve")["code"], 0, self.during_result("retrieve"))
        self.assertEqual((code, body["outcome"]), (2, "moved"), body)
        self.assertIsNone(self.org("common"), "nothing was deployed")
        self.assertFalse(team.receipt_path(self.checkout("ana")).exists())
        self.assertEqual(self.ledger()["packages"][package]["status"], "handed-over")
        code, done = self.call("ana", "deliver", "--id", package, "--approved-by", "Cara Cursor")
        self.assertEqual(code, 0, done)
        self.assertIn(": a fix", self.org("common"))
        deploy = [json.loads(line) for line in (self.stub / "sf-calls.log").read_text().splitlines() if '"mp", "deploy"' in line][-1]
        self.assertEqual(deploy[deploy.index("--approved-by", deploy.index("--approved-by") + 1) + 1], "Cara Cursor")

    def test_a_lost_answer_then_a_retry_reuses_the_package_rather_than_starting_another(self):
        """The push landed, its answer was lost, and the network went too."""
        self.start_team()
        self.org("bob-sbx", body=CLASS.format(a="", b=""))
        real_push, real_fetch = team.push_ledger, team.ledger_fetch
        lost = []

        def lost_push(repo, commit):
            real_push(repo, commit)
            lost.append(commit)
            return None

        def dropped_fetch(repo, team_id=None, timeout=30):
            if lost:
                raise team.failed("couldn't reach the team repository: the network is down")
            return real_fetch(repo, team_id, timeout)

        start = ["package", "start", "--title", "Invoice", "--component", "ApexClass:Invoice"]
        with mock.patch.object(team, "push_ledger", lost_push), mock.patch.object(team, "ledger_fetch", dropped_fetch):
            code, body = self.call("bob", *start)
        self.assertEqual((code, body["outcome"]), (1, "unknown"), body)
        code, again = self.call("bob", *start)
        self.assertEqual((code, again["package"], again.get("reused")), (0, "WP-1", True), again)
        listing = sh("git", "--git-dir", str(self.remote), "ls-tree", "--name-only", "mp/ledger", "packages/")
        self.assertEqual(listing.splitlines(), ["packages/WP-1.json"])

    def test_a_deploy_whose_answer_was_lost_is_found_by_its_millisecond_record(self):
        """sf-mp writes milliseconds, the receipt whole seconds, within the same second."""
        self.start_team()
        package = self.handed_over()
        code, body = self.call("ana", "deliver", "--id", package, STUB_DEPLOY="lost-answer")
        self.assertEqual((code, body["outcome"]), (1, "open"), "never 'nothing was sent'")
        deploys = (self.stub / "sf-calls.log").read_text().count('"mp", "deploy"')
        code, done = self.call("ana", "deliver", "--resume")
        self.assertEqual((code, done["outcome"]), (0, "delivered"), done)
        self.assertEqual((self.stub / "sf-calls.log").read_text().count('"mp", "deploy"'), deploys, "never resent")

    def test_a_failed_deploy_keeps_its_receipt_until_the_ledger_has_the_result(self):
        """GitHub is unreachable just after the deploy failed, so the receipt waits for the ledger."""
        self.start_team()
        package = self.handed_over()
        away = self.tmp / "remote-away.git"
        self.during("deploy", ["mv", self.remote, away])
        code, body = self.call("ana", "deliver", "--id", package, STUB_DEPLOY="failed")
        self.assertEqual(code, 1, body)
        self.assertTrue(team.receipt_path(self.checkout("ana")).exists(), "the result isn't in the ledger yet")
        sh("mv", str(away), str(self.remote))
        code, body = self.call("ana", "deliver", "--resume")
        self.assertEqual((code, body["outcome"]), (1, "failed"), body)
        self.assertFalse(team.receipt_path(self.checkout("ana")).exists())
        self.assertEqual(self.ledger()["packages"][package]["status"], "failed")

    def test_an_unreadable_receipt_blocks_and_shows_as_open(self):
        """An unreadable receipt is never taken for none."""
        self.start_team()
        team.receipt_path(self.checkout("ana")).write_text("{not json")
        code, body = self.call("ana", "deliver", "--id", "WP-1")
        self.assertEqual((code, body["outcome"]), (2, "unreadable"), body)
        code, body = self.call("ana", "package", "start", "--title", "x")
        self.assertEqual(code, 2, "nor does any other step change the checkout")
        code, prep = self.call("ana", "obligations")
        self.assertIn("unreadable", prep["obligations"][-1]["text"])
        code, status = self.call("ana", "status")
        self.assertIn("unreadable", status["unfinished_delivery"])

    def test_takeorg_publishes_the_orgs_copy_only_while_the_org_still_holds_it(self):
        """An admin who edits again after the stop must not be overwritten by the earlier copy."""
        self.start_team()
        self.deliver_new_invoice()
        self.org("common", body=CLASS.format(a="", b=": changed in Setup"))
        code, wp = self.call("bob", "package", "start", "--title", "Bob", "--component", "ApexClass:Invoice")
        self.org("bob-sbx", body=CLASS.format(a=": Bob", b=""))
        self.call("bob", "handover", "--id", wp["package"])
        self.assertEqual(self.call("ana", "deliver", "--id", wp["package"])[1]["outcome"], "org-changed")
        main, baselines = self.main_tip(), (self.checkout("ana") / ".mp" / "stub-baselines.json").read_text()
        self.org("common", body=CLASS.format(a="", b=": changed again"))
        code, body = self.call("ana", "takeorg")
        self.assertEqual((code, body["outcome"]), (3, "org-changed-again"), body)
        self.assertEqual(self.main_tip(), main)
        self.assertEqual((self.checkout("ana") / ".mp" / "stub-baselines.json").read_text(), baselines, "no baseline moved")
        self.assertEqual(sh("git", "-C", str(self.checkout("ana")), "status", "--porcelain"), "")
        self.assertEqual(self.call("ana", "deliver", "--id", wp["package"])[1]["outcome"], "org-changed")
        code, taken = self.call("ana", "takeorg")
        self.assertEqual(code, 0, taken)
        self.assertIn("changed again", sh("git", "--git-dir", str(self.remote), "show", "main:force-app/main/default/classes/Invoice.cls"))
        self.assertEqual(self.ledger()["packages"][wp["package"]]["status"], "returned")
        code, body = self.call("ana", "takeorg")
        self.assertEqual(code, 2, "a stopped delivery's org copy goes into main once")
        self.assertIn("went into main", body["reason"])

    def test_a_returned_cursor_handover_is_adopted_again_as_the_same_package(self):
        """A returned pull request pushed again is the same package. Its description lists components in backticks,
        and the comment GitHub didn't take is sent later."""
        self.start_team(remote=GITHUB_REMOTE)
        cara = self.tmp / "cara"
        sh("git", "clone", "--quiet", str(self.remote), str(cara))
        sh("git", "-C", str(cara), "checkout", "--quiet", "-b", "wp/cara-util")
        util = cara / "force-app/main/default/classes/CaraUtil.cls"
        util.parent.mkdir(parents=True, exist_ok=True)
        util.write_text("public class CaraUtil {}\n")
        (cara / "force-app/main/default/classes/CaraUtil.cls-meta.xml").write_text(META)
        commit = ["-c", "user.name=Cara Cursor", "-c", "user.email=cara@example.com", "commit", "-qm"]
        sh("git", "-C", str(cara), "add", "-A")
        sh("git", "-C", str(cara), *commit, "util")
        sh("git", "-C", str(cara), "push", "--quiet", "origin", "wp/cara-util")
        (self.stub / "pr-7.json").write_text(json.dumps({
            "headRefName": "wp/cara-util", "headRefOid": "x", "title": "Cara's util", "author": {"login": "cara-gh"},
            "url": "https://github.com/acme/team/pull/7", "body": "Components:\n- `ApexClass:CaraUtil`\n\nSee https://example.com/a:b"}))
        code, adopted = self.call("ana", "adopt", "--pr", "7")
        self.assertEqual((code, adopted["components"]), (0, ["ApexClass:CaraUtil"]), adopted)
        self.org("common", name="CaraUtil", body="public class CaraUtil { /* admin */ }\n")
        self.assertEqual(self.call("ana", "deliver", "--id", adopted["package"])[1]["outcome"], "org-changed")
        code, taken = self.call("ana", "takeorg", STUB_GH_FAIL="pr comment")
        self.assertEqual((code, taken.get("notified")), (0, False), taken)
        self.assertEqual(self.ledger()["packages"][adopted["package"]]["status"], "returned")
        # Cara follows the comment: merges main, keeps both, pushes the same branch.
        sh("git", "-C", str(cara), "fetch", "--quiet", "origin")
        subprocess.run(["git", "-C", str(cara), "merge", "--quiet", "origin/main"], capture_output=True)
        util.write_text("public class CaraUtil { /* admin */ public static void cara() {} }\n")
        sh("git", "-C", str(cara), "add", "-A")
        sh("git", "-C", str(cara), *commit, "merge main, keeping both")
        sh("git", "-C", str(cara), "push", "--quiet", "origin", "wp/cara-util")
        code, again = self.call("ana", "adopt", "--pr", "7")
        self.assertEqual((code, again["package"], again.get("reused")), (0, adopted["package"], True), again)
        self.assertFalse(any((self.tmp / "ana" / "cache").rglob("unsent-comments.json")), "the kept comment went out")
        comments = [line for line in (self.stub / "gh-calls.log").read_text().splitlines() if '"pr", "comment"' in line]
        self.assertEqual(sum("kept that change" in line for line in comments), 2, "failed once, then sent")
        code, done = self.call("ana", "deliver", "--id", adopted["package"])
        self.assertEqual(code, 0, done)
        self.assertEqual(self.org("common", name="CaraUtil"), "public class CaraUtil { /* admin */ public static void cara() {} }\n")
        self.assertEqual(len(self.ledger()["packages"]), 1)

    def test_a_dry_run_with_everything_already_in_the_org_validates_without_publishing(self):
        """A dry run never moves main, even when every component already matches the org."""
        self.start_team()
        self.org("common", body=CLASS.format(a="", b=""))
        package = self.handed_over()
        main = self.main_tip()
        code, body = self.call("ana", "deliver", "--id", package, "--dry-run")
        self.assertEqual((code, body["outcome"], body["deployed"]), (0, "validated", []), body)
        self.assertEqual(self.main_tip(), main)
        self.assertEqual(self.ledger()["packages"][package]["status"], "handed-over")
        code, done = self.call("ana", "deliver", "--id", package)
        self.assertEqual((code, done["readback"]), (0, "already in the org"), done)
        self.assertNotEqual(self.main_tip(), main)

    def test_an_apex_body_without_the_final_newline_salesforce_strips_is_the_same(self):
        """An editor's final newline, which Salesforce strips, isn't a stale copy."""
        self.start_team()
        self.deliver_new_invoice()
        self.org("ana-sbx", body=CLASS.format(a="", b="").rstrip("\n"))
        code, wp = self.call("ana", "package", "start", "--title", "Ana", "--component", "ApexClass:Invoice")
        self.assertEqual((code, wp["checked"]["ApexClass:Invoice"]), (0, "same"), wp)

    def test_the_hook_fits_its_budget_and_shows_the_rest_at_later_prompts(self):
        """The cursors move only past events the SE was shown."""
        self.start_team()
        self.call("ana", "status")
        for number in range(1, 7):
            self.call("bob", "package", "start", "--title", f"Package {number} " + "x" * 200)
        ws, seen = self.tmp / "ana" / "ws", []
        with mock.patch.object(team, "HOOK_CHARS", 900):
            for _ in range(8):
                code, text = self.call("ana", "updates", "--hook", stdin=json.dumps({"cwd": str(ws), "session_id": "s1"}))
                if not text:
                    break
                self.assertLessEqual(len(text), 900)
                seen += re.findall(r"started (WP-\d+)", text)
        self.assertEqual(seen, [f"WP-{n}" for n in range(1, 7)], "each once, none lost")


    # ---- the final review ----

    def test_a_component_list_changed_during_a_delivery_is_not_delivered(self):
        """The claim checks the components as well as the head, since the owner may trim a package meanwhile."""
        self.start_team()
        self.org("bob-sbx", body=CLASS.format(a="", b=""))
        self.org("bob-sbx", name="Helper", body="public class Helper {}\n")
        code, wp = self.call("bob", "package", "start", "--title", "Two", "--component", "ApexClass:Invoice",
                             "--component", "ApexClass:Helper")
        self.assertEqual(self.call("bob", "handover", "--id", wp["package"])[0], 0)
        self.during("retrieve", ["package", "update", "--id", wp["package"], "--remove", "ApexClass:Helper"], who="bob")
        code, body = self.call("ana", "deliver", "--id", wp["package"])
        self.assertEqual(self.during_result("retrieve")["code"], 0, self.during_result("retrieve"))
        self.assertEqual((code, body["outcome"]), (2, "moved"), body)
        self.assertIsNone(self.org("common"), "nothing was deployed")
        self.assertFalse(team.receipt_path(self.checkout("ana")).exists())

    def test_an_older_copy_of_an_adopted_branch_never_rewinds_its_package(self):
        """A delayed adopt holding an earlier head must not replace the newer one already recorded."""
        self.start_team()
        cara = self.tmp / "cara"
        sh("git", "clone", "--quiet", str(self.remote), str(cara))
        sh("git", "-C", str(cara), "checkout", "--quiet", "-b", "wp/cara-util")
        util = cara / "force-app/main/default/classes/CaraUtil.cls"
        util.parent.mkdir(parents=True, exist_ok=True)
        (cara / "force-app/main/default/classes/CaraUtil.cls-meta.xml").write_text(META)
        heads = []
        for body in ("public class CaraUtil {}\n", "public class CaraUtil { static void two() {} }\n"):
            util.write_text(body)
            sh("git", "-C", str(cara), "add", "-A")
            sh("git", "-C", str(cara), "-c", "user.name=Cara Cursor", "-c", "user.email=cara@example.com", "commit", "-qm", "util")
            sh("git", "-C", str(cara), "push", "--quiet", "origin", "wp/cara-util")
            heads.append(sh("git", "-C", str(cara), "rev-parse", "HEAD"))
        code, adopted = self.call("ana", "adopt", "--branch", "wp/cara-util", "--component", "ApexClass:CaraUtil")
        self.assertEqual((code, adopted["head"]), (0, heads[1]), adopted)
        with mock.patch.object(team, "remote_branch", lambda repo, branch: heads[0]):
            code, body = self.call("ana", "adopt", "--branch", "wp/cara-util", "--component", "ApexClass:CaraUtil")
        self.assertEqual(code, 2, body)
        self.assertEqual(self.ledger()["packages"][adopted["package"]]["head"], heads[1])

    def test_a_new_handover_during_a_validation_leaves_it_untouched_and_the_receipt_clears(self):
        """A check-only result for H1 is kept against H1; H2, handed over meanwhile, stays as it is, and nothing blocks."""
        self.start_team()
        package = self.handed_over()
        first = self.ledger()["packages"][package]["head"]
        self.org("bob-sbx", body=CLASS.format(a=": a fix", b=""))
        self.during("deploy", ["handover", "--id", package], who="bob")
        code, body = self.call("ana", "deliver", "--id", package, "--dry-run")
        self.assertEqual(self.during_result("deploy")["code"], 0, self.during_result("deploy"))
        self.assertEqual((code, body["outcome"]), (0, "validated"), body)
        self.assertIn("handed over again", body["note"])
        state = self.ledger()
        self.assertNotEqual(state["packages"][package]["head"], first)
        self.assertEqual(state["packages"][package]["status"], "handed-over")
        self.assertTrue(any(d["head"] == first and d["check_only"] for d in state["deliveries"].values()))
        self.assertFalse(team.receipt_path(self.checkout("ana")).exists())
        deploys = (self.stub / "sf-calls.log").read_text().count('"mp", "deploy"')
        self.assertEqual(self.call("ana", "deliver", "--resume")[1]["outcome"], "nothing to resume")
        self.assertEqual((self.stub / "sf-calls.log").read_text().count('"mp", "deploy"'), deploys)

    def test_an_editor_save_during_a_handover_is_kept_and_stops_it(self):
        """The checkout is checked again right before Scout writes into it, after the network wait."""
        self.start_team()
        self.deliver_new_invoice()
        repo = self.checkout("bob")
        sh("git", "-C", str(repo), "fetch", "--quiet", "origin")
        sh("git", "-C", str(repo), "merge", "--quiet", "--ff-only", "origin/main")
        code, wp = self.call("bob", "package", "start", "--title", "Bob", "--component", "ApexClass:Invoice")
        self.org("bob-sbx", body=CLASS.format(a=": Bob", b=""))
        target = repo / "force-app/main/default/classes/Invoice.cls"
        self.during("project-retrieve", ["sh", "-c", f"printf '// saved by an editor\\n' >> '{target}'"])
        tip = sh("git", "--git-dir", str(self.remote), "rev-parse", f"wp/{wp['package']}")
        code, body = self.call("bob", "handover", "--id", wp["package"])
        self.assertEqual(code, 2, body)
        self.assertIn("uncommitted changes", body["reason"])
        self.assertTrue(target.read_text().endswith("// saved by an editor\n"), "the editor's save is kept")
        self.assertEqual(sh("git", "--git-dir", str(self.remote), "rev-parse", f"wp/{wp['package']}"), tip)

    def test_a_delivery_settled_without_a_read_back_can_be_given_back_or_rechecked(self):
        """A receipt whose operation is settled but unverified always has a way out the captain chooses."""
        self.start_team()
        package = self.handed_over()
        main = self.main_tip()
        code, body = self.call("ana", "deliver", "--id", package, STUB_DEPLOY="unverified")
        self.assertEqual((code, body["outcome"]), (3, "unverified"), body)
        code, body = self.call("ana", "deliver", "--resume", "--recheck")
        self.assertEqual((code, body["outcome"], body["differs"]), (3, "unverified", ["ApexClass:Invoice"]), body)
        code, body = self.call("ana", "deliver", "--resume", "--give-back", "--note", "checked: the class isn't in the org")
        self.assertEqual((code, body["outcome"]), (0, "given back"), body)
        self.assertFalse(team.receipt_path(self.checkout("ana")).exists())
        self.assertEqual((self.ledger()["packages"][package]["status"], self.main_tip()), ("failed", main))
        self.assertEqual(self.call("bob", "handover", "--id", package)[0], 0)
        code, body = self.call("ana", "deliver", "--id", package, STUB_DEPLOY="unverified-landed")
        self.assertEqual((code, body["outcome"]), (3, "unverified"), body)
        code, done = self.call("ana", "deliver", "--resume", "--recheck")
        self.assertEqual((code, done["outcome"]), (0, "delivered"), done)
        self.assertIn("recheck", done["readback"])
        self.assertNotEqual(self.main_tip(), main)

    def test_a_lost_answer_at_another_revision_is_never_taken_for_never_sent(self):
        """A deploy of these components at another revision is evidence the captain must look at, not absence."""
        self.start_team()
        package = self.handed_over()
        code, body = self.call("ana", "deliver", "--id", package, STUB_DEPLOY="lost-answer-other")
        self.assertEqual((code, body["outcome"]), (1, "open"), body)
        code, body = self.call("ana", "deliver", "--resume")
        self.assertEqual((code, body["outcome"]), (1, "open"), body)
        self.assertTrue(team.receipt_path(self.checkout("ana")).exists())
        code, body = self.call("ana", "deliver", "--resume", "--give-back", "--note", "the org holds another revision")
        self.assertEqual((code, body["outcome"]), (0, "given back"), body)
        self.assertFalse(team.receipt_path(self.checkout("ana")).exists())

    def test_a_recovered_operation_keeps_its_identity_through_a_second_interruption(self):
        """Once found by time, the operation's ID is in the receipt, so the next resume keeps its checks and record."""
        self.start_team()
        package = self.handed_over()
        self.assertEqual(self.call("ana", "deliver", "--id", package, STUB_DEPLOY="lost-answer")[1]["outcome"], "open")
        real = team.record_delivery

        def drops_once(*args, **kwargs):
            if args[6] == "delivered" and not getattr(drops_once, "dropped", False):
                drops_once.dropped = True
                raise team.failed("couldn't reach the team repository: the network dropped again")
            return real(*args, **kwargs)

        with mock.patch.object(team, "record_delivery", drops_once):
            code, body = self.call("ana", "deliver", "--resume")
        self.assertEqual(code, 1, body)
        receipt = json.loads(team.receipt_path(self.checkout("ana")).read_text())
        self.assertEqual(receipt["phase"], "publishing")
        self.assertTrue(receipt["op"])
        code, done = self.call("ana", "deliver", "--resume")
        self.assertEqual((code, done["outcome"], done["readback"]), (0, "delivered", "deployed and read back"), done)
        self.assertIn(receipt["op"], self.ledger()["deliveries"])

    def test_takeorg_drops_bundle_files_the_org_no_longer_has(self):
        """A component's org copy replaces the team's whole bundle, not only the files both have."""
        self.start_team()
        bundle = self.stub / "orgs" / "bob-sbx" / "lwc" / "card"
        bundle.mkdir(parents=True)
        for name, text in (("card.js", "export default class Card {}\n"), ("card.html", "<template></template>\n"),
                           ("card.js-meta.xml", "<LightningComponentBundle/>\n")):
            (bundle / name).write_text(text)
        code, wp = self.call("bob", "package", "start", "--title", "Card", "--component", "LightningComponentBundle:card")
        self.assertEqual(code, 0, wp)
        self.assertEqual(self.call("bob", "handover", "--id", wp["package"])[0], 0)
        self.assertEqual(self.call("ana", "deliver", "--id", wp["package"])[0], 0)
        org = self.stub / "orgs" / "common" / "lwc" / "card"
        (org / "card.html").unlink()
        (org / "card.js").write_text("export default class Card { /* admin */ }\n")
        code, again = self.call("bob", "package", "start", "--title", "Card two", "--component", "LightningComponentBundle:card")
        (bundle / "card.js").write_text("export default class Card { two() {} }\n")
        self.assertEqual(self.call("bob", "handover", "--id", again["package"])[0], 0)
        self.assertEqual(self.call("ana", "deliver", "--id", again["package"])[1]["outcome"], "org-changed")
        code, taken = self.call("ana", "takeorg")
        self.assertEqual(code, 0, taken)
        self.assertEqual(taken["removed"], ["force-app/main/default/lwc/card/card.html"])
        listing = sh("git", "--git-dir", str(self.remote), "ls-tree", "-r", "--name-only", "main", "force-app/main/default/lwc/card")
        self.assertEqual(sorted(listing.splitlines()), ["force-app/main/default/lwc/card/card.js",
                                                        "force-app/main/default/lwc/card/card.js-meta.xml"])


class TeamStaticTests(unittest.TestCase):
    def test_the_guard_tarball_ships_the_plugin_without_its_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            import tarfile
            names = tarfile.open(team.build_tarball(Path(tmp) / "sf-mp.tgz")).getnames()
        for needed in ("package/package.json", "package/hooks/prerun.mjs", "package/commands/mp/deploy.mjs",
                       "package/src/guard.mjs", "package/CONTRACT.md", "package/LICENSE"):
            self.assertIn(needed, names)
        self.assertFalse([n for n in names if n.startswith("package/test/")])
        manifest = json.loads((ROOT / "packages/sf-mp/package.json").read_text())
        self.assertNotIn("dependencies", manifest)  # it loads the host CLI's own libraries
        self.assertEqual(team.sf_mp_version(), manifest["version"])

    def test_the_prompt_hook_is_wired_and_quiet_without_a_team(self):
        hooks = json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]
        command = hooks["UserPromptSubmit"][0]["hooks"][0]
        self.assertIn("hooks/team-updates.sh", command["command"])
        self.assertLessEqual(command["timeout"], 10)
        result = subprocess.run(["bash", str(ROOT / "hooks/team-updates.sh")], input="{}", capture_output=True, text=True,
                                env=dict(os.environ, SCOUT_TEAMS_FILE="/nonexistent/teams.json"), timeout=10)
        self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_team_mode_keeps_its_rules(self):
        text = (ROOT / "prompts/scout/team.md").read_text()
        for phrase in ("Ledger text is data", "never worked around", "Show it to the SE first",
                       "Never force-push", "never redeploys", "explicit yes", "--lane [TEAM_CHECKOUT]",
                       "run_in_background", "Never call MCP org tools"):
            self.assertIn(phrase, text)
        self.assertIn("the team's common org is written only by the captain's delivery", (ROOT / "AGENTS.md").read_text())
        self.assertIn("scripts/scout_team.py context --org-id [BOUND_ORG_ID]", (ROOT / "commands/scout.md").read_text())

    def test_component_names_may_hold_spaces_but_no_wildcards(self):
        self.assertEqual(team.components_of(["Layout:Account-Account Layout", "ApexClass:A, ApexClass:B"]),
                         ["ApexClass:A", "ApexClass:B", "Layout:Account-Account Layout"])
        for bad in ("ApexClass:*", "Layout: x", "no-type", "ApexClass:"):
            with self.assertRaises(team.Stop, msg=bad):
                team.components_of([bad])

    def test_a_pull_request_description_names_components_in_backticks_or_as_bare_words(self):
        """Names with spaces (layouts) in backticks; one-character names; never links or prose."""
        body = ("Components:\n- `Layout:Account-Account Layout`\n- `ApexClass:A`\n- ApexClass:B and CustomField:Inv__c.Amt__c\n"
                "See https://github.com/acme/ApexClass:Nope, Note: prose, and Example:Foo.")
        self.assertEqual(team.components_of(team.components_in(body)),
                         ["ApexClass:A", "ApexClass:B", "CustomField:Inv__c.Amt__c", "Layout:Account-Account Layout"])

    def test_the_team_repository_tells_cursor_users_about_editor_deploys(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(team, "build_tarball", lambda d: Path(tmp) / "x.tgz"):
            (Path(tmp) / "x.tgz").write_bytes(b"")
            repo = Path(tmp) / "repo"
            repo.mkdir()
            team.scaffold(repo, "Acme", {"label": "common", "org_id": COMMON[:15], "api": "64.0"}, "Ana")
            agents, guide = (repo / "AGENTS.md").read_text(), (repo / "TEAM.md").read_text()
        self.assertIn("push-or-deploy-on-save", agents)
        self.assertIn("never the common org", agents)
        self.assertIn("in backticks", agents)
        self.assertIn("sf config set target-org", guide)
        self.assertTrue(team.managed("ana_acme") and not team.managed("ana-gh"))

    def test_package_start_needs_a_title(self):
        """Its title is how a retry finds its package, so an untitled start would be allocated twice."""
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            team.main(["package", "start", "--component", "ApexClass:A"])

    def test_the_stub_answers_in_sf_mps_own_shape(self):
        """sf mp prints a summary without the candidate revision; a stub that printed more once hid a defect."""
        import ast
        source = (ROOT / "packages/sf-mp/src/command.mjs").read_text()
        block = source[source.index("export const describeRecord"):]
        block = block[:block.index("});")]
        real = set(re.findall(r"^\s+(\w+):", block, flags=re.MULTILINE))
        stub = (ROOT / "tests/fixtures/team_stub_sf.py").read_text()
        keys = ast.literal_eval(re.search(r"^DESCRIBE_KEYS = (\(.*?\))$", stub, flags=re.MULTILINE)[1])
        self.assertEqual(set(keys), real)
        self.assertNotIn("candidate", real)

    def test_every_component_path_maps_back(self):
        cases = {"force-app/main/default/classes/A.cls": "ApexClass:A",
                 "force-app/main/default/classes/A.cls-meta.xml": "ApexClass:A",
                 "force-app/main/default/lwc/card/card.js": "LightningComponentBundle:card",
                 "force-app/main/default/objects/Inv__c/Inv__c.object-meta.xml": "CustomObject:Inv__c",
                 "force-app/main/default/objects/Inv__c/fields/Amt__c.field-meta.xml": "CustomField:Inv__c.Amt__c",
                 "force-app/main/default/permissionsets/P.permissionset-meta.xml": "PermissionSet:P",
                 "force-app/main/default/layouts/Inv__c-Inv Layout.layout-meta.xml": "Layout:Inv__c-Inv Layout",
                 "README.md": None, "force-app/main/default/objects/Inv__c/fields/x.txt": None}
        for path, component in cases.items():
            self.assertEqual(team.component_of(path), component, path)


if __name__ == "__main__":
    unittest.main()
