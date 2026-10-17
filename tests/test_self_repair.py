"""Scout repairs its own setup: every break its checks report goes to setup, which fixes it or says why not."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_HELPER = ROOT / "scripts" / "setup-workspace.py"
SF_STUB = """#!/bin/bash
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--output-dir" ]; then shift; out="$1"; fi
  shift
done
mkdir -p "$out/sf-demo-scout/force-app/main/default"
printf '{"packageDirectories":[{"path":"force-app","default":true}],"sourceApiVersion":"65.0"}\\n' > "$out/sf-demo-scout/sfdx-project.json"
printf '{"status": 0, "result": {}}\\n'
"""


def gate_tokens() -> set[str]:
    """The workspace verifier's failures that /scout's gate hands to setup."""
    gate = (ROOT / "prompts/workspace-bootstrap.md").read_text()
    rule = gate.split("When that output names", 1)[1].split("Scout repairs", 1)[0]
    return set(re.findall(r"`([A-Z_]+)`", rule))


def verifier_tokens() -> set[str]:
    """Every failure token the verifier's checks can raise, read from the helper's source."""
    tree = ast.parse(WORKSPACE_HELPER.read_text())
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    tokens = set()
    for name in ("verify", "validate_project", "validate_settings", "validate_config", "load_json_object"):
        for call in ast.walk(functions[name]):
            if isinstance(call, ast.Call) and getattr(call.func, "id", "") in ("fail", "load_json_object"):
                for argument in call.args:
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str) \
                            and re.fullmatch(r"[A-Z_]+", argument.value):
                        tokens.add(argument.value)
    return tokens


def held_steps() -> dict[str, set[str]]:
    """The steps a self-repair run holds for the SE's yes, by procedure, from `commands/scout-setup.md`."""
    section = (ROOT / "commands/scout-setup.md").read_text().split("## Self-repair runs", 1)[1].split("\n## ", 1)[0]
    held: dict[str, set[str]] = {"fresh install": set(), "refresh": set()}
    for line in section.splitlines():
        if line.startswith("- "):
            for procedure, ids in re.findall(r"(fresh install|refresh) ((?:`[^`]+`(?:,? and |, )?)+)", line):
                held[procedure] |= set(re.findall(r"`([a-z](?:\.\d+)?)`", ids))
    return held


# Every bash fence in setup, classified by the command that identifies it. A fence that changes the SE's machine is
# "machine"; one that only reads is "read"; Scout's own files and Salesforce's official plugins repair on their own.
FENCE_KINDS = {
    "setup-bootstrap.sh": "machine", "setup-cli-refresh.sh": "machine", "sf plugins update": "machine",
    "setup-zshrc.sh": "machine", "json-pins --settings": "machine", "retired-allow --settings": "machine",
    "aisuite-hooks --settings": "machine", 'USER_SETTINGS="$HOME/.claude/settings.json"': "machine",
    "vscode-pins": "read", "launchctl getenv": "read", "setup-model-report.py": "read", "client-version.py": "read",
    "setup-mcp-status.py": "read", "command -v npm": "read", "command -v brew": "read",
    "setup-workspace.py": "scout", "setup-official-plugins.py": "plugins",
}


def fence_kind(fence: str) -> str:
    """The one kind a setup fence's commands identify; a fence no entry names fails, so it gets classified first."""
    kinds = {kind for command, kind in FENCE_KINDS.items() if command in fence}
    if len(kinds) != 1:
        raise AssertionError(f"classify this setup fence in FENCE_KINDS ({sorted(kinds) or 'no known command'}):\n{fence}")
    return kinds.pop()


def fences(text: str) -> list[str]:
    return re.findall(r"^[ \t]*```bash\n(.*?)^[ \t]*```", text, re.S | re.M)


def machine_wide_steps(procedure: str) -> set[str]:
    """Steps with a "machine" fence of their own or in a setup fragment they read."""
    steps = set()
    for step in re.split(r"(?m)^## ", (ROOT / f"prompts/setup/{procedure}.md").read_text())[1:]:
        heading, body = step.split("\n", 1)
        fragments = set(re.findall(r"prompts/setup/([a-z0-9-]+\.md)", body))
        text = body + "".join((ROOT / "prompts/setup" / name).read_text() for name in fragments)
        if any(fence_kind(fence) == "machine" for fence in fences(text)):
            steps.add(heading.split(":", 1)[0].strip())
    return steps


class SelfRepairTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="scout-self-repair-")
        self.addCleanup(temp.cleanup)
        base = Path(temp.name).resolve()
        self.workspace, self.config = base / "sf-demo-scout", base / "config" / "config.json"
        bin_dir = base / "bin"
        bin_dir.mkdir()
        (bin_dir / "sf").write_text(SF_STUB)
        (bin_dir / "sf").chmod(0o700)
        self.env = {**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
        self.env.pop("PYTHONPATH", None)

    def helper(self, command: str, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-B", str(WORKSPACE_HELPER), command, "--workspace", str(self.workspace),
                               "--config", str(self.config), "--host", "claude", *extra],
                              env=self.env, text=True, capture_output=True, timeout=60, check=False)

    def setup_workspace(self) -> subprocess.CompletedProcess[str]:
        """What /scout-setup runs for the workspace (fresh-install.md, steps d–f)."""
        return self.helper("setup", "--template", str(ROOT / "assets/workspace-settings.template.json"),
                           "--plugin-version", "fixture")

    def test_the_gate_hands_every_verifier_failure_to_setup(self) -> None:
        # A new verifier check can't slip past the repair: its token must be one the gate sends to setup.
        self.assertEqual(verifier_tokens(), gate_tokens())

    def test_every_break_the_gate_reports_is_repaired_by_setup(self) -> None:
        self.assertEqual(self.setup_workspace().returncode, 0)
        breaks = {
            "WORKSPACE_INVALID": lambda: shutil.rmtree(self.workspace),
            "SFDX_PROJECT_INVALID": lambda: (self.workspace / "sfdx-project.json").unlink(),
            "FORCE_APP_INVALID": lambda: shutil.rmtree(self.workspace / "force-app"),
            "LESSONS_INVALID": lambda: (self.workspace / "orgs/lessons/INDEX.md").unlink(),
            "SETTINGS_INVALID": lambda: (self.workspace / ".claude/settings.json").unlink(),
            "CONFIG_INVALID": lambda: self.config.unlink(),
        }
        self.assertEqual(set(breaks), gate_tokens())
        for token, damage in breaks.items():
            with self.subTest(token=token):
                damage()
                broken = self.helper("verify")
                self.assertNotEqual(broken.returncode, 0)
                self.assertTrue(broken.stdout.startswith(token + ":"), broken.stdout)
                repaired = self.setup_workspace()
                self.assertEqual(repaired.returncode, 0, repaired.stdout + repaired.stderr)
                self.assertIn("WORKSPACE_READY", repaired.stdout)
                self.assertEqual(self.helper("verify").returncode, 0)

    def test_setup_never_replaces_a_file_the_se_wrote_so_the_gate_stops_after_one_try(self) -> None:
        self.assertEqual(self.setup_workspace().returncode, 0)
        self.config.write_text("{not json\n")
        repaired = self.setup_workspace()
        self.assertNotEqual(repaired.returncode, 0)
        self.assertIn("CONFIG_INVALID:", repaired.stdout)
        self.assertEqual(self.config.read_text(), "{not json\n")
        gate = " ".join((ROOT / "prompts/workspace-bootstrap.md").read_text().split())
        self.assertIn("Scout repairs itself: say so in one line, run `/scout-setup self-repair` once (the "
                      "`sf-demo-scout:scout-setup` skill, or `[PLUGIN_ROOT]/commands/scout-setup.md`), then rerun this "
                      "gate. Otherwise, or if it still fails, stop.", gate)

    def test_every_setup_fence_is_classified(self) -> None:
        # The guarantee below is only as good as this classification: a new fence must name a known command.
        for path in sorted((ROOT / "prompts/setup").glob("*.md")) + [ROOT / "commands/scout-setup.md"]:
            for fence in fences(path.read_text()):
                with self.subTest(path=path.name, fence=fence.splitlines()[0]):
                    fence_kind(fence)
        with self.assertRaises(AssertionError):  # a write outside the known commands isn't silently "read"
            fence_kind('python3 -c "open(\'/tmp/x\', \'w\')"\n')

    def test_a_self_repair_run_holds_exactly_the_steps_that_change_the_machine(self) -> None:
        # Workspace files and the official plugins repair on their own; the CLI, `~/.zshrc` and Claude settings wait for
        # one yes. Every step with a classified "machine" fence is held, and the list names no other step.
        held = held_steps()
        self.assertEqual(machine_wide_steps("fresh-install"), held["fresh install"])
        self.assertEqual(machine_wide_steps("refresh"), held["refresh"])
        self.assertEqual(held["fresh install"], {"b", "g", "g.5", "g.6", "g.7", "g.8", "j"})
        self.assertEqual(held["refresh"], {"a", "b.5", "d", "d.7", "d.8"})
        for name in ("slack-mcp.md", "google-mcp.md", "salesforce-docs-mcp.md"):  # registrations stay the SE's explicit choice
            fragment = (ROOT / "prompts/setup" / name).read_text()
            self.assertIn("claude mcp add", fragment)
            self.assertTrue("never run it automatically" in fragment or "offer this command without running it" in fragment)

    def test_every_entry_point_starts_a_self_repair_run_and_a_no_is_reported(self) -> None:
        for path in ("hooks/session-startup.sh", "prompts/workspace-bootstrap.md", "AGENTS.md"):
            self.assertIn("/scout-setup self-repair", (ROOT / path).read_text().replace("\\`", "`"), path)
        command = (ROOT / "commands/scout.md").read_text()
        self.assertIn("On `CHECK_FAILED`, absent success evidence or nonzero exit, follow the gate's rules.", command)
        setup = (ROOT / "commands/scout-setup.md").read_text()
        for phrase in ("this run's arguments are `$ARGUMENTS`", "fixes Scout's workspace files and installs Salesforce's "
                       "official plugins without asking", "Before its first step, it asks the SE one question",
                       "On a yes, run the procedure as usual.", "On a no, skip those steps, and fresh install `a` too, "
                       "since the Homebrew check only serves `b`'s installs", "add `--keep-se-choices`",
                       "Read-only reports run either way, such as the running-client report and `model-pin-strip.md`'s "
                       "model checks", "Name each skipped step and left plugin in the closing message",
                       "A `/scout-setup` the SE runs themselves asks nothing extra.", "--keep-se-choices"):
            self.assertIn(phrase, setup)
        self.assertIn("If the SE said no to the held steps, name each as skipped", (ROOT / "prompts/setup/done.md").read_text())
        for name in ("refresh.md", "fresh-install.md"):
            text = " ".join((ROOT / "prompts/setup" / name).read_text().split())
            self.assertIn("self-repair run, ask its one question first (`commands/scout-setup.md`)", text, name)
        overrides = (ROOT / "prompts/building/official-skill-overrides.md").read_text()
        self.assertIn("the one exception is the missing-plugin repair below, which says when it asks first", overrides)
        self.assertIn("official-plugins.md` with `--keep-se-choices`, with this session's launch folder", overrides)

    def test_the_rule_names_a_setup_skill_the_session_can_run(self) -> None:
        rule = (ROOT / "AGENTS.md").read_text().split("## Org\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("When startup or a Scout check reports setup incomplete or broken, run `/scout-setup self-repair` yourself "
                      "(the `sf-demo-scout:scout-setup` skill) once per session, saying so in one line, not asking the SE; "
                      "its own questions still need their answers, and if it can't fix the problem, say why.", rule)
        # `sf-demo-scout:scout-setup` is this plugin's command, and the model may invoke it.
        self.assertIn('"name": "sf-demo-scout"', (ROOT / ".claude-plugin/plugin.json").read_text())
        command = (ROOT / "commands/scout-setup.md").read_text()
        frontmatter = command.split("---", 2)[1]
        self.assertRegex(frontmatter, r"(?m)^name: scout-setup$")
        self.assertNotIn("disable-model-invocation", frontmatter)


if __name__ == "__main__":
    unittest.main()
