"""Offline tests for post-scout/install.py: the rules block, the Claude Code steps, and removing Scout.

A stub `claude` on a temporary PATH records every call and keeps its state in a JSON file; HOME is a temporary folder.
The stub is a stand-in (tests/stand_ins.py), so Windows runs it too.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import stand_ins

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "post-scout" / "install.py"
BEGIN = "<!-- post-scout rules: begin"
STUB = r'''import json, os, sys
state_path = os.environ["STUB_STATE"]
state = json.load(open(state_path))
args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(json.dumps(args) + "\n")
def save():
    json.dump(state, open(state_path, "w"))
if args[:3] == ["plugin", "marketplace", "list"]:
    print(json.dumps(state["marketplaces"]))
elif args[:3] == ["plugin", "marketplace", "add"]:
    state["marketplaces"].append({"name": "salesforce", "repo": args[3]}); save()
    print(json.dumps({"marketplace": "salesforce"}))
elif args[:2] == ["plugin", "list"]:
    print(json.dumps([{"id": i, "scope": "user"} for i in state["plugins"]]))
elif args[:2] == ["plugin", "install"]:
    state["plugins"].append(args[2]); save(); print("{}")
elif args[:2] == ["plugin", "uninstall"]:
    state["plugins"] = [p for p in state["plugins"] if p != args[2]]; save()
elif args[:2] == ["mcp", "get"]:
    sys.exit(0 if state["docs"] else 1)
elif args[:2] == ["mcp", "add"]:
    state["docs"] = True; save()
else:
    sys.exit(2)
'''


class PostScoutTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="post-scout-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        stand_ins.tool(bin_dir, "claude", STUB)
        self.state = self.tmp / "state.json"
        self.log = self.tmp / "calls.jsonl"
        self.set_state(marketplaces=[], plugins=[], docs=False)
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home), STUB_STATE=str(self.state),
                        STUB_LOG=str(self.log), PATH=os.pathsep.join([str(bin_dir), "/usr/bin", "/bin"]),
                        PYTHONDONTWRITEBYTECODE="1")
        self.config = self.tmp / "config"
        self.config.mkdir()
        self.env["CLAUDE_CONFIG_DIR"] = str(self.config)
        self.env.pop("CLAUDE_CODE_EXECPATH", None)
        self.env.pop("CODEX_HOME", None)

    def set_state(self, **values):
        self.state.write_text(json.dumps(values))

    def install(self, *args, cwd=None):
        return subprocess.run([sys.executable, "-B", str(INSTALL), *args], capture_output=True, encoding="utf-8",
                              errors="replace", env=self.env, cwd=cwd or self.tmp, timeout=120)

    def calls(self):
        return [json.loads(l) for l in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_dry_run_changes_nothing(self):
        out = self.install("--host", "claude")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertFalse((self.home / ".claude" / "CLAUDE.md").exists())
        self.assertIn("POST_SCOUT_PLAN add the rules to", out.stdout)
        self.assertIn("POST_SCOUT_PLAN install salesforce-development@salesforce", out.stdout)
        self.assertIn("POST_SCOUT_PLAN register the Salesforce Docs MCP", out.stdout)
        writes = [c for c in self.calls() if c[:2] in (["plugin", "install"], ["mcp", "add"]) or c[:3] == ["plugin", "marketplace", "add"]]
        self.assertEqual(writes, [])

    def test_claude_user_scope_applies_and_is_idempotent(self):
        claude_md = self.home / ".claude" / "CLAUDE.md"
        claude_md.parent.mkdir(parents=True)
        claude_md.write_text("# My own notes\nKeep this line.\n")
        out = self.install("--host", "claude", "--yes")
        self.assertEqual(out.returncode, 0, out.stderr)
        text = claude_md.read_text()
        self.assertIn("Keep this line.", text)
        self.assertEqual(text.count(BEGIN), 1)
        self.assertIn("Rules for Salesforce demo builds", text)
        self.assertNotIn("Your Scout workspace", text)  # no workspace in this home, so no pointer
        self.assertTrue((claude_md.parent / "CLAUDE.md.before-post-scout").exists())
        state = json.loads(self.state.read_text())
        self.assertEqual(sorted(state["plugins"]), ["salesforce-code-quality@salesforce", "salesforce-development@salesforce"])
        self.assertTrue(state["docs"])
        again = self.install("--host", "claude", "--yes")
        self.assertIn("POST_SCOUT_SKIP rules already current", again.stdout)
        self.assertIn("POST_SCOUT_SKIP salesforce-development is already installed", again.stdout)
        self.assertIn("POST_SCOUT_SKIP the Salesforce Docs MCP", again.stdout)
        self.assertEqual(claude_md.read_text().count(BEGIN), 1)

    def test_an_old_block_is_replaced_in_place(self):
        claude_md = self.home / ".claude" / "CLAUDE.md"
        claude_md.parent.mkdir(parents=True)
        claude_md.write_text("before\n<!-- post-scout rules: begin (managed by post-scout/install.py; edit outside these "
                             "markers) -->\nold rules\n<!-- post-scout rules: end -->\nafter\n")
        self.install("--host", "claude", "--plugins", "none", "--no-docs", "--yes")
        text = claude_md.read_text()
        self.assertNotIn("old rules", text)
        self.assertTrue(text.startswith("before\n") and text.rstrip().endswith("after"))

    def test_project_scope_writes_agents_md_and_the_claude_import(self):
        project = self.tmp / "proj"
        project.mkdir()
        out = self.install("--host", "claude", "--scope", "project", "--project", str(project), "--plugins", "none",
                           "--no-docs", "--yes")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn(BEGIN, (project / "AGENTS.md").read_text())
        self.assertEqual((project / "CLAUDE.md").read_text().splitlines()[0], "@AGENTS.md")
        self.assertFalse((self.home / ".claude" / "CLAUDE.md").exists())

    def test_codex_and_cursor(self):
        codex_home = self.tmp / "codex"
        self.env["CODEX_HOME"] = str(codex_home)
        out = self.install("--host", "codex", "--yes")
        self.assertIn(BEGIN, (codex_home / "AGENTS.md").read_text())
        self.assertIn("codex plugin marketplace add forcedotcom/sf-skills", out.stdout)
        self.assertIn("codex mcp add salesforce-docs --url", out.stdout)
        out = self.install("--host", "cursor", "--yes")
        self.assertIn("Cursor Settings", out.stdout)
        self.assertIn("npx skills add forcedotcom/sf-skills", out.stdout)
        self.assertEqual(self.calls(), [])  # no `claude` call for Codex or Cursor

    def test_existing_marketplace_and_plugins_are_reused(self):
        self.set_state(marketplaces=[{"name": "sf", "url": "https://github.com/forcedotcom/sf-skills.git"}],
                       plugins=["salesforce-development@sf"], docs=True)
        out = self.install("--host", "claude", "--yes")
        self.assertIn("POST_SCOUT_SKIP salesforce-development is already installed", out.stdout)
        self.assertIn("POST_SCOUT_DONE install salesforce-code-quality@sf", out.stdout)
        self.assertNotIn(["plugin", "marketplace", "add"], [c[:3] for c in self.calls()])

    def test_a_salesforce_marketplace_from_another_source_is_reused(self):
        self.set_state(marketplaces=[{"name": "salesforce", "path": "/some/local/copy"}],
                       plugins=["salesforce-development@salesforce", "salesforce-code-quality@salesforce"], docs=True)
        out = self.install("--host", "claude", "--yes")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("POST_SCOUT_SKIP using the existing Salesforce marketplace `salesforce`", out.stdout)
        self.assertNotIn("FAILED", out.stdout)
        self.assertNotIn(["plugin", "marketplace", "add"], [c[:3] for c in self.calls()])
        self.set_state(marketplaces=[{"name": "salesforce", "path": "/some/local/copy"}], plugins=[], docs=True)
        out = self.install("--host", "claude", "--yes")
        self.assertIn("POST_SCOUT_DONE install salesforce-development@salesforce", out.stdout)

    def test_auto_update_is_turned_on_unless_the_user_chose(self):
        settings = self.config / "settings.json"
        source = {"source": "github", "repo": "forcedotcom/sf-skills"}
        settings.write_text(json.dumps({"extraKnownMarketplaces": {"salesforce": {"source": source}}, "other": 1}))
        self.set_state(marketplaces=[{"name": "salesforce", "repo": "forcedotcom/sf-skills"}], plugins=[], docs=True)
        dry = self.install("--host", "claude")
        self.assertIn("POST_SCOUT_PLAN turn on auto-update for the `salesforce` marketplace", dry.stdout)
        self.assertNotIn("autoUpdate", settings.read_text())
        out = self.install("--host", "claude", "--yes")
        self.assertIn("POST_SCOUT_DONE turned on auto-update", out.stdout)
        data = json.loads(settings.read_text())
        self.assertIs(data["extraKnownMarketplaces"]["salesforce"]["autoUpdate"], True)
        self.assertEqual(data["other"], 1)
        self.assertTrue((self.config / "settings.json.before-post-scout").exists())
        self.assertIn("POST_SCOUT_SKIP auto-update is already on", self.install("--host", "claude", "--yes").stdout)
        data["extraKnownMarketplaces"]["salesforce"]["autoUpdate"] = False
        settings.write_text(json.dumps(data))
        self.assertIn("off by your own choice", self.install("--host", "claude", "--yes").stdout)
        self.assertIs(json.loads(settings.read_text())["extraKnownMarketplaces"]["salesforce"]["autoUpdate"], False)

    def test_remove_scout_runs_its_uninstaller_then_the_plugin_uninstall(self):
        config = self.home / ".config" / "sf-demo-scout"
        config.mkdir(parents=True)
        (config / "config.json").write_text("{}")
        self.set_state(marketplaces=[], plugins=["sf-demo-scout@scout"], docs=True)
        dry = self.install("--host", "claude", "--plugins", "none", "--remove-scout")
        self.assertIn("POST_SCOUT_PLAN uninstall the plugin sf-demo-scout@scout", dry.stdout)
        self.assertTrue(config.exists())
        out = self.install("--host", "claude", "--plugins", "none", "--remove-scout", "--yes")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("POST_SCOUT_DONE uninstall the plugin sf-demo-scout@scout", out.stdout)
        self.assertNotIn("sf-demo-scout@scout", json.loads(self.state.read_text())["plugins"])
        self.assertFalse(config.exists())

    def workspace(self, root=None, lessons=2):
        """A Scout workspace with one org folder and, unless `lessons` is None, that many lessons in one topic."""
        root = root or self.home / "claude-projects" / "sf-demo-scout"
        (root / "orgs" / "demo-acme").mkdir(parents=True)
        (root / "orgs" / "demo-acme" / "change-log.md").write_text("# Change log\n")
        if lessons is not None:
            (root / "orgs" / "lessons").mkdir()
            (root / "orgs" / "lessons" / "INDEX.md").write_text("# Lessons Index\n")
            (root / "orgs" / "lessons" / "flow.md").write_text(
                "".join("- 2026-08-0%d [abc123%d]: Rule %d.\n  - Symptom: x\n" % (n, n, n) for n in range(1, lessons + 1)))
        return root

    def test_the_workspace_stays_and_the_rules_point_to_it(self):
        root = self.workspace()
        config = self.home / ".config" / "sf-demo-scout"
        config.mkdir(parents=True)
        (config / "config.json").write_text("{}")
        self.set_state(marketplaces=[], plugins=["sf-demo-scout@scout"], docs=True)
        out = self.install("--host", "claude", "--plugins", "none", "--remove-scout", "--remove-scout-workspace", "--yes")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("--remove-scout-workspace is ignored", out.stdout)  # 2.6.0's flag, which removed it
        self.assertIn("with its org histories and 2 lessons", out.stdout)
        self.assertIn("review your Scout lessons", out.stdout)
        self.assertTrue((root / "orgs" / "lessons" / "flow.md").exists())
        self.assertTrue((root / "orgs" / "demo-acme" / "change-log.md").exists())
        self.assertFalse(config.exists())  # Scout's own configuration still goes
        text = (self.home / ".claude" / "CLAUDE.md").read_text()
        self.assertEqual(text.count(BEGIN), 1)
        for expected in ("## Your Scout workspace", "`%s`" % root, "orgs/lessons/INDEX.md", "review my Scout lessons"):
            self.assertIn(expected, text)
        self.assertIn("POST_SCOUT_SKIP rules already current", self.install("--host", "claude", "--plugins", "none",
                                                                          "--no-docs", "--yes").stdout)

    def test_the_workspace_scouts_configuration_names_comes_first(self):
        elsewhere = self.workspace(self.tmp / "my-scout", lessons=None)
        self.workspace()  # the default folder exists too
        config = self.home / ".config" / "sf-demo-scout"
        config.mkdir(parents=True)
        (config / "config.json").write_text(json.dumps({"workspace_path": str(elsewhere)}))
        self.install("--host", "codex", "--yes")
        text = (self.home / ".codex" / "AGENTS.md").read_text()
        self.assertIn("`%s`" % elsewhere, text)
        self.assertNotIn("orgs/lessons/INDEX.md", text)  # that one has no lessons, so no lesson lines
        self.assertNotIn("review my Scout lessons", text)

    def test_a_project_gets_no_personal_path_and_cursor_gets_lines_to_paste(self):
        self.workspace()
        project = self.tmp / "proj"
        project.mkdir()
        out = self.install("--host", "claude", "--scope", "project", "--project", str(project), "--plugins", "none",
                           "--no-docs", "--yes")
        self.assertIn("gets no personal path", out.stdout)
        self.assertNotIn("Your Scout workspace", (project / "AGENTS.md").read_text())
        self.assertIn("paste these lines under them: ## Your Scout workspace", self.install("--host", "cursor").stdout)

    def test_it_prints_utf8_under_the_ansi_code_page(self):
        # Before Python 3.15 a Windows pipe takes the ANSI code page, which can't spell → or a home such as Łukasz 東京.
        home = self.tmp / "Łukasz 東京"
        home.mkdir()
        self.env = {name: value for name, value in self.env.items() if name not in ("PYTHONUTF8", "PYTHONIOENCODING")}
        self.env.update(HOME=str(home), USERPROFILE=str(home), PYTHONIOENCODING="cp1252")
        for host, shown in (("claude", str(home)), ("codex", str(home)), ("cursor", "→")):
            with self.subTest(host=host):
                out = self.install("--host", host)
                self.assertEqual(out.returncode, 0, out.stderr)
                self.assertNotIn("Traceback", out.stderr)
                self.assertIn(shown, out.stdout)


if __name__ == "__main__":
    unittest.main()
