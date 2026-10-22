"""The clone installer writes only its own files, plans before it acts, and never replaces what it didn't write."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("scout_install", ROOT / "scripts" / "scout_install.py")
INSTALL = importlib.util.module_from_spec(spec)
spec.loader.exec_module(INSTALL)


class InstallTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="scout-install-")
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name).resolve()
        patcher = mock.patch.object(INSTALL, "home", return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)
        environment = mock.patch.dict(os.environ, {}, clear=False)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("CLAUDE_CONFIG_DIR", None)  # Claude Code's folder is the stand-in's ~/.claude unless a test sets it

    def run_install(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = INSTALL.main(list(args))
        return code, output.getvalue().splitlines()

    def test_thin_skills_plan_then_write_and_hand_over_to_this_clone(self):
        code, lines = self.run_install("skills", "--host", "cursor", "--dry-run")
        self.assertEqual(code, 0)
        self.assertTrue(all(line.startswith("INSTALL_PLAN") for line in lines), lines)
        self.assertFalse((self.home / ".cursor" / "skills").exists())
        code, lines = self.run_install("skills", "--host", "cursor", "--yes")
        self.assertEqual(code, 0, lines)
        scout = (self.home / ".cursor" / "skills" / "scout" / "SKILL.md").read_text()
        self.assertIn("name: scout\n", scout)
        self.assertIn("disable-model-invocation: true", scout)
        self.assertIn(str(ROOT / "skills" / "scout" / "SKILL.md"), scout)
        setup = (self.home / ".cursor" / "skills" / "scout-setup" / "SKILL.md").read_text()
        self.assertNotIn("disable-model-invocation", setup)  # Scout runs its own setup to repair itself
        self.assertEqual(self.run_install("skills", "--host", "cursor", "--yes")[0], 0)  # rerun replaces its own

    def test_a_skill_it_didnt_write_is_never_replaced(self):
        foreign = self.home / ".cursor" / "skills" / "scout" / "SKILL.md"
        foreign.parent.mkdir(parents=True)
        foreign.write_text("---\nname: scout\n---\nsomeone else's\n")
        code, lines = self.run_install("skills", "--host", "cursor", "--yes")
        self.assertEqual(code, 1)
        self.assertTrue(any(line.startswith("INSTALL_REFUSED %s" % foreign) for line in lines), lines)
        self.assertEqual(foreign.read_text(), "---\nname: scout\n---\nsomeone else's\n")
        self.run_install("uninstall", "--host", "cursor", "--yes")
        self.assertTrue(foreign.exists())
        self.assertFalse((self.home / ".cursor" / "skills" / "scout-setup").exists())  # its own went

    def test_uninstall_removes_only_its_own_skills(self):
        self.run_install("skills", "--host", "cursor", "--yes")
        other = self.home / ".cursor" / "skills" / "mine" / "SKILL.md"
        other.parent.mkdir(parents=True)
        other.write_text("mine")
        code, lines = self.run_install("uninstall", "--host", "cursor", "--yes")
        self.assertEqual(code, 0)
        self.assertFalse((self.home / ".cursor" / "skills" / "scout").exists())
        self.assertTrue(other.exists())

    def test_the_docs_entry_is_merged_and_an_existing_one_is_kept(self):
        path = self.home / ".cursor" / "mcp.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "keep": 1}))
        self.assertEqual(self.run_install("docs-mcp", "--dry-run")[0], 0)
        self.assertNotIn("salesforce-docs", path.read_text())
        code, lines = self.run_install("docs-mcp", "--yes")
        self.assertEqual(code, 0, lines)
        data = json.loads(path.read_text())
        self.assertEqual(data["mcpServers"]["salesforce-docs"], {"url": INSTALL.DOCS_URL})
        self.assertEqual((data["mcpServers"]["other"], data["keep"]), ({"command": "x"}, 1))
        self.assertTrue((self.home / ".cursor" / "mcp.json.scout-bak").exists())
        data["mcpServers"]["salesforce-docs"] = {"url": "https://example.test/own"}
        path.write_text(json.dumps(data))
        code, lines = self.run_install("docs-mcp", "--yes")
        self.assertTrue(lines[0].startswith("INSTALL_KEPT"), lines)
        self.assertEqual(json.loads(path.read_text())["mcpServers"]["salesforce-docs"]["url"], "https://example.test/own")

    def test_an_unreadable_mcp_file_is_left_alone(self):
        path = self.home / ".cursor" / "mcp.json"
        path.parent.mkdir(parents=True)
        for body in ("{not json", json.dumps({"mcpServers": []})):
            with self.subTest(body=body):
                path.write_text(body)
                code, lines = self.run_install("docs-mcp", "--yes")
                self.assertEqual(code, 1)
                self.assertEqual(path.read_text(), body)

    def test_official_skills_clone_in_place_and_are_recorded(self):
        source = self.home / "source"
        (source / "plugins" / "builder").mkdir(parents=True)
        (source / "plugins" / "builder" / "README.md").write_text("x")
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "add", "."], check=True)
        subprocess.run(["git", "-C", str(source), "-c", "user.name=t", "-c", "user.email=t@example.test",
                        "commit", "-qm", "x"], check=True)
        target = self.home / "sf-skills"
        with mock.patch.object(INSTALL, "OFFICIAL_REPO", "file://%s" % source):
            code, lines = self.run_install("official-skills", "--dest", str(target), "--dry-run")
            self.assertEqual(code, 0)
            self.assertFalse(target.exists())
            code, lines = self.run_install("official-skills", "--dest", str(target), "--yes")
        self.assertEqual(code, 0, lines)
        self.assertTrue((target / "plugins" / "builder").is_dir())
        record = json.loads((self.home / ".config" / "sf-demo-scout" / "official-skills.json").read_text())
        self.assertEqual(record["root"], str(target.resolve()))
        self.assertRegex(record["revision"], r"^[0-9a-f]{40}$")  # the revision qualified, for the record
        code, lines = self.run_install("status", "--host", "cursor")
        self.assertIn("INSTALL_STATUS official-skills %s" % target.resolve(), lines)
        # An existing clone is adopted only when it's Salesforce's repository with the plugins' layout.
        (target / "plugins" / "builder" / "salesforce-development" / "skills").mkdir(parents=True)
        code, lines = self.run_install("official-skills", "--dest", str(target), "--yes")
        self.assertEqual(code, 1)
        self.assertIn("origin isn't github.com/forcedotcom/sf-skills", lines[0])
        subprocess.run(["git", "-C", str(target), "remote", "set-url", "origin", "https://github.com/forcedotcom/sf-skills.git"],
                       check=True)
        code, lines = self.run_install("official-skills", "--dest", str(target), "--dry-run")
        self.assertEqual([line.split()[0] for line in lines], ["INSTALL_KEPT", "INSTALL_PLAN"])  # the record write is shown
        self.assertTrue(self.run_install("official-skills", "--dest", str(target), "--yes")[1][0].startswith("INSTALL_KEPT"))
        occupied = self.home / "occupied"
        occupied.mkdir()
        self.assertEqual(self.run_install("official-skills", "--dest", str(occupied), "--yes")[0], 1)

    def test_a_cursor_with_claude_codes_scout_hears_about_the_duplicate(self):
        # Claude Code keeps its record in ~/.claude, or in CLAUDE_CONFIG_DIR's folder once that's set; the second pass
        # also checks that the Scout the first pass left in ~/.claude no longer counts
        for config in (self.home / ".claude", self.home / "claude-config"):
            if config.name != ".claude":
                os.environ["CLAUDE_CONFIG_DIR"] = str(config)
            record = config / "plugins" / "installed_plugins.json"
            record.parent.mkdir(parents=True)
            for plugins, warned in (({}, False), ({"sf-demo-scout@scout": [{"scope": "user"}]}, True),
                                    ({"sf-demo-scout@my-scout": [{"scope": "user"}]}, True)):
                with self.subTest(config=config.name, plugins=plugins):
                    record.write_text(json.dumps({"version": 2, "plugins": plugins}))
                    code, lines = self.run_install("skills", "--host", "cursor", "--dry-run")
                    self.assertEqual(any(line.startswith("INSTALL_NOTE") and "twice" in line for line in lines), warned, lines)

    def test_the_thin_skills_take_their_descriptions_from_the_clone(self):
        self.run_install("skills", "--host", "cursor", "--yes")
        for name, user_only in (("scout", True), ("scout-setup", False)):
            with self.subTest(name=name):
                thin = (self.home / ".cursor" / "skills" / name / "SKILL.md").read_text()
                description = json.loads(next(line for line in thin.splitlines() if line.startswith("description:"))
                                         [len("description:"):].strip())
                self.assertEqual(description, INSTALL.frontmatter(name)[0])
                self.assertNotIn("allowed-tools", description)  # only the description, never the next field
                self.assertNotIn("argument-hint", description)
                self.assertEqual("disable-model-invocation: true" in thin, user_only)
        self.assertIn("when the builder asks to set up or update Scout", INSTALL.frontmatter("scout-setup")[0])
        self.assertEqual(INSTALL.frontmatter("scout")[0],
                         "Build, repair or prep demo items in a named Salesforce org, with targeted inspection and read-back.")


if __name__ == "__main__":
    unittest.main()
