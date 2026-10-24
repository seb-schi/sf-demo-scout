#!/usr/bin/env python3
"""Set up post-Scout: Salesforce's official plugins, the Salesforce Docs MCP, and the post-Scout rules. Optionally,
remove Scout.

Usage:
  python3 install.py --host claude|codex|cursor [--scope user|project] [--project DIR] [--plugins core|all|none]
                     [--no-docs] [--remove-scout] [--remove-scout-workspace] [--dry-run | --yes]

Without --yes it only prints the plan (a dry run). With --yes it carries the plan out, printing each step as it goes.

What it does:
- **The rules.** It writes post-scout/RULES.md between two marker lines, so a rerun replaces the block instead of
  adding a second one, and it keeps a backup of the file the first time.
  - user scope (default): ~/.claude/CLAUDE.md on Claude Code, ~/.codex/AGENTS.md on Codex
  - project scope: AGENTS.md in the project folder, plus CLAUDE.md with `@AGENTS.md` on Claude Code
  - On Cursor, user rules live in Cursor's settings, so the user scope prints the rules for you to paste there.
- **The official plugins.** On Claude Code it adds Salesforce's marketplace (github.com/forcedotcom/sf-skills) and
  installs its core plugins (salesforce-development, salesforce-code-quality), or more with --plugins all, and turns
  that marketplace's auto-update on unless you chose otherwise. On Codex
  and Cursor it prints Salesforce's own commands to run (the same marketplace on Codex; `npx skills add` on Cursor).
- **The Salesforce Docs MCP.** On Claude Code it registers it at user scope; on Codex and Cursor it prints the command
  or setting.
- **--remove-scout.** It first runs Scout's own uninstaller (configuration and cache; the workspace with its org
  histories only with --remove-scout-workspace), then removes the plugin with the host's own command.

It never touches Salesforce orgs, logins, aliases or default orgs. Every printed line starts with a token:
POST_SCOUT_PLAN, POST_SCOUT_DONE, POST_SCOUT_SKIP, POST_SCOUT_NOTE or POST_SCOUT_FAILED.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
RULES = HERE / "RULES.md"
BEGIN = "<!-- post-scout rules: begin (managed by post-scout/install.py; edit outside these markers) -->"
END = "<!-- post-scout rules: end -->"
SCOPE_LINE = "Apply these rules whenever you work with a Salesforce org."
OFFICIAL_SOURCE = "forcedotcom/sf-skills"
CORE = ("salesforce-development", "salesforce-code-quality")
MORE = ("agentforce-adlc", "experience-lwc", "service-engagement")
DOCS_NAME = "salesforce-docs"
DOCS_URL = "https://salesforce-docs-76258744c9d7.herokuapp.com/api/mcp"


def say(token, text):
    print("POST_SCOUT_%s %s" % (token, text))
    sys.stdout.flush()


def utf8_output():
    """Write stdout and stderr in UTF-8 with LF line ends, as Scout's helpers do. Before Python 3.15, Windows encodes a
    pipe with the ANSI code page (cp1252 and the like), where printing → or a path such as C:\\Users\\Łukasz raises
    UnicodeEncodeError."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors=stream.errors, newline="\n")
        except (AttributeError, ValueError):
            pass


def run(argv, timeout=600):
    try:
        out = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError) as error:
        return 127, "", str(error)
    return out.returncode, out.stdout, out.stderr


def run_json(argv):
    code, out, err = run(argv)
    try:
        return code, json.loads(out)
    except ValueError:
        return code, {"message": (out + err).strip()[-300:]}


def find_claude():
    found = shutil.which("claude")
    if found:
        return found
    desktop = os.environ.get("CLAUDE_CODE_EXECPATH", "")
    return desktop if desktop and Path(desktop).exists() else None


# ---------------------------------------------------------------- the rules

def block():
    return "%s\n%s\n\n%s\n%s\n" % (BEGIN, SCOPE_LINE, RULES.read_text(encoding="utf-8").strip(), END)


def with_block(text):
    """The file's text with the rules block added, or replaced in place when it's already there."""
    if BEGIN in text and END in text:
        head, rest = text.split(BEGIN, 1)
        tail = rest.split(END, 1)[1]
        return head + block().rstrip("\n") + tail
    joiner = "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    return text + joiner + block()


def write_rules(path, apply):
    path = Path(path)
    before = path.read_text(encoding="utf-8") if path.exists() else ""
    after = with_block(before)
    if after == before:
        return say("SKIP", "rules already current in %s" % path)
    verb = "update the rules in" if BEGIN in before else "add the rules to"
    if not apply:
        return say("PLAN", "%s %s" % (verb, path))
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name(path.name + ".before-post-scout")
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(after, encoding="utf-8")
    say("DONE", "%s %s%s" % (verb.replace("add", "added").replace("update", "updated"), path,
                             " (backup: %s)" % backup if backup.exists() else ""))


def import_line(path, apply):
    """Claude Code reads CLAUDE.md, not AGENTS.md: a project CLAUDE.md imports AGENTS.md with one line."""
    path = Path(path)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if any(line.strip() == "@AGENTS.md" for line in text.splitlines()):
        return say("SKIP", "%s already imports AGENTS.md" % path)
    if not apply:
        return say("PLAN", "add `@AGENTS.md` to %s" % path)
    path.write_text(("@AGENTS.md\n" + ("\n" + text if text else "")), encoding="utf-8")
    say("DONE", "added `@AGENTS.md` to %s" % path)


def rules(args, apply):
    home = Path.home()
    if args.scope == "project":
        project = Path(args.project or os.getcwd()).resolve()
        write_rules(project / "AGENTS.md", apply)
        if args.host == "claude":
            import_line(project / "CLAUDE.md", apply)
        return
    if args.host == "claude":
        write_rules(home / ".claude" / "CLAUDE.md", apply)
    elif args.host == "codex":
        write_rules(Path(os.environ.get("CODEX_HOME") or home / ".codex") / "AGENTS.md", apply)
    else:
        say("NOTE", "Cursor keeps user rules in its settings: open Cursor Settings → Rules → User Rules and paste "
                    "%s, or rerun with --scope project to write AGENTS.md into a project" % RULES)


# ---------------------------------------------------------------- Claude Code: official plugins and the Docs MCP

def official_plugins(claude, wanted, apply):
    """Reuse what's there: the marketplace an installed official plugin comes from, then one with Salesforce's source,
    then one named `salesforce` (for example a local copy); add Salesforce's GitHub marketplace only when none exists."""
    code, rows = run_json([claude, "plugin", "list", "--json"])
    ids = [str(row.get("id", "")) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    have = {i.split("@")[0] for i in ids}
    name = next((i.split("@", 1)[1] for i in ids if "@" in i and i.split("@")[0] in CORE + MORE), None)
    if not name:
        code, markets = run_json([claude, "plugin", "marketplace", "list", "--json"])
        markets = [m for m in markets if isinstance(m, dict)] if isinstance(markets, list) else []
        by_source = [m.get("name") for m in markets
                     if OFFICIAL_SOURCE in str(m.get("url") or m.get("repo") or m.get("path") or "").replace(".git", "")]
        by_name = [m.get("name") for m in markets if m.get("name") == "salesforce"]
        name = (by_source or by_name or [None])[0]
    if not name:
        if not apply:
            say("PLAN", "add Salesforce's marketplace (%s)" % OFFICIAL_SOURCE)
            name = "salesforce"
        else:
            code, data = run_json([claude, "plugin", "marketplace", "add", OFFICIAL_SOURCE, "--scope", "user", "--json"])
            if code != 0:
                return say("FAILED", "couldn't add Salesforce's marketplace: %s" % (data.get("message") if isinstance(data, dict) else data))
            name = (data.get("marketplace") if isinstance(data, dict) else None) or "salesforce"
            say("DONE", "added Salesforce's marketplace as `%s`" % name)
    else:
        say("SKIP", "using the existing Salesforce marketplace `%s`" % name)
    auto_update(name, apply)
    for plugin in wanted:
        if plugin in have:
            say("SKIP", "%s is already installed" % plugin)
        elif not apply:
            say("PLAN", "install %s@%s" % (plugin, name))
        else:
            code, data = run_json([claude, "plugin", "install", "%s@%s" % (plugin, name), "--scope", "user", "--json"])
            say("DONE" if code == 0 else "FAILED", "install %s@%s%s" % (plugin, name, "" if code == 0 else ": %s" % (
                data.get("message") if isinstance(data, dict) else data)))


def auto_update(name, apply):
    """Keep Salesforce's plugins current: turn auto-update on for their marketplace, unless you already chose (an explicit
    false is yours to keep). Claude Code has no flag for this, so it's a careful edit of settings.json, with a backup."""
    path = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:
        return say("FAILED", "%s isn't valid JSON, so auto-update wasn't turned on; turn it on in /plugin → Marketplaces" % path)
    entry = (data.get("extraKnownMarketplaces") or {}).get(name) if isinstance(data, dict) else None
    if not isinstance(entry, dict):
        if not apply:
            return say("PLAN", "turn on auto-update for the `%s` marketplace once it's declared" % name)
        return say("NOTE", "the `%s` marketplace isn't declared in %s; turn on auto-update in /plugin → Marketplaces" % (name, path))
    if entry.get("autoUpdate") is True:
        return say("SKIP", "auto-update is already on for `%s`" % name)
    if "autoUpdate" in entry:
        return say("SKIP", "auto-update for `%s` is off by your own choice; left as it is" % name)
    if not apply:
        return say("PLAN", "turn on auto-update for the `%s` marketplace in %s" % (name, path))
    backup = path.with_name(path.name + ".before-post-scout")
    if not backup.exists():
        shutil.copy2(path, backup)
    entry["autoUpdate"] = True
    temp = path.with_name(path.name + ".post-scout-tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)
    say("DONE", "turned on auto-update for the `%s` marketplace (backup: %s)" % (name, backup))


def docs_mcp(claude, apply):
    code, _, _ = run([claude, "mcp", "get", DOCS_NAME])
    if code == 0:
        return say("SKIP", "the Salesforce Docs MCP (%s) is already registered" % DOCS_NAME)
    if not apply:
        return say("PLAN", "register the Salesforce Docs MCP at user scope (%s)" % DOCS_URL)
    code, out, err = run([claude, "mcp", "add", "-s", "user", "--transport", "http", DOCS_NAME, DOCS_URL])
    say("DONE" if code == 0 else "FAILED", "register the Salesforce Docs MCP%s" % ("" if code == 0 else ": " + (out + err).strip()[-200:]))


# ---------------------------------------------------------------- removing Scout

def remove_scout(args, claude, apply):
    uninstaller = HERE.parent / "scripts" / "scout_uninstall.py"
    if uninstaller.exists():
        extra = ["--workspace"] if args.remove_scout_workspace else []
        if not apply:
            code, out, err = run([sys.executable, str(uninstaller), "--dry-run", *extra])
            for line in out.splitlines():
                if line.strip():
                    say("PLAN", "Scout's uninstaller would: %s" % line.strip())
        else:
            code, out, err = run([sys.executable, str(uninstaller), "--yes", *extra])
            for line in out.splitlines():
                if line.strip():
                    say("DONE" if code == 0 else "FAILED", "Scout's uninstaller: %s" % line.strip())
    else:
        say("NOTE", "Scout's uninstaller isn't beside this script; its files in ~/.config/sf-demo-scout and "
                    "~/.cache/sf-demo-scout can be removed by hand")
    if args.host == "claude":
        if not claude:
            return say("NOTE", "remove the plugin with `claude plugin uninstall sf-demo-scout@scout`")
        code, rows = run_json([claude, "plugin", "list", "--json"])
        ids = [row["id"] for row in rows if isinstance(row, dict) and str(row.get("id", "")).startswith("sf-demo-scout@")] \
            if isinstance(rows, list) else []
        if not ids:
            return say("SKIP", "the Scout plugin isn't installed")
        for ident in ids:
            if not apply:
                say("PLAN", "uninstall the plugin %s" % ident)
            else:
                code, out, err = run([claude, "plugin", "uninstall", ident])
                say("DONE" if code == 0 else "FAILED", "uninstall the plugin %s%s" % (ident, "" if code == 0 else ": " + (out + err).strip()[-200:]))
        say("NOTE", "Scout's marketplace stays registered; remove it with `claude plugin marketplace remove %s` if "
                    "nothing else comes from it" % ids[0].split("@", 1)[1])
    elif args.host == "codex":
        if not apply:
            return say("PLAN", "remove the plugin with `codex plugin remove sf-demo-scout@scout`")
        code, out, err = run([shutil.which("codex") or "codex", "plugin", "remove", "sf-demo-scout@scout"])  # Windows starts npm's codex.cmd only by its full path
        say("DONE" if code == 0 else "FAILED", "codex plugin remove sf-demo-scout@scout%s" % ("" if code == 0 else ": " + (out + err).strip()[-200:]))
    else:
        installer = HERE.parent / "scripts" / "scout_install.py"
        if not apply:
            return say("PLAN", "remove Scout from Cursor with `%s uninstall --host cursor --yes`, then delete the folder" % installer)
        code, out, err = run([sys.executable, str(installer), "uninstall", "--host", "cursor", "--yes"])
        say("DONE" if code == 0 else "FAILED", "Cursor uninstall%s; delete the Scout folder by hand" % ("" if code == 0 else ": " + (out + err).strip()[-200:]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--host", required=True, choices=("claude", "codex", "cursor"))
    parser.add_argument("--scope", default="user", choices=("user", "project"))
    parser.add_argument("--project", help="the project folder for --scope project (default: the current folder)")
    parser.add_argument("--plugins", default="core", choices=("core", "all", "none"))
    parser.add_argument("--no-docs", action="store_true", help="don't register the Salesforce Docs MCP")
    parser.add_argument("--remove-scout", action="store_true")
    parser.add_argument("--remove-scout-workspace", action="store_true",
                        help="with --remove-scout, also remove Scout's workspace and its org histories")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    if args.remove_scout_workspace and not args.remove_scout:
        parser.error("--remove-scout-workspace needs --remove-scout")
    apply = bool(args.yes)
    say("NOTE", "%s for %s (%s scope)" % ("applying" if apply else "dry run: nothing changes", args.host, args.scope))
    rules(args, apply)
    claude = find_claude() if args.host == "claude" else None
    if args.host == "claude" and not claude:
        say("FAILED", "Claude Code's `claude` command isn't on PATH; install it, or run the plugin and MCP steps by hand")
    if args.host == "claude" and claude:
        if args.plugins != "none":
            official_plugins(claude, CORE + (MORE if args.plugins == "all" else ()), apply)
        if not args.no_docs:
            docs_mcp(claude, apply)
    if args.host == "codex":
        if args.plugins != "none":
            plugins = CORE + (MORE if args.plugins == "all" else ())
            say("NOTE", "add Salesforce's official plugins to Codex: `codex plugin marketplace add %s`, then %s"
                % (OFFICIAL_SOURCE, ", ".join("`codex plugin add %s@salesforce`" % p for p in plugins)))
        if not args.no_docs:
            say("NOTE", "add the Salesforce Docs MCP to Codex: `codex mcp add %s --url %s`" % (DOCS_NAME, DOCS_URL))
    if args.host == "cursor":
        if args.plugins != "none":
            say("NOTE", "add Salesforce's official skills to Cursor: `npx skills add %s` (Salesforce's own route)" % OFFICIAL_SOURCE)
        if not args.no_docs:
            say("NOTE", "add the Salesforce Docs MCP to Cursor: in ~/.cursor/mcp.json, an entry \"%s\" with \"url\": \"%s\""
                % (DOCS_NAME, DOCS_URL))
    if args.host != "claude":
        say("NOTE", "the benchmark behind post-Scout ran on Claude Code; on %s these steps follow Salesforce's and "
                    "Scout's own setup, untested by that benchmark" % args.host.title())
    if args.remove_scout:
        remove_scout(args, claude, apply)
    if not apply:
        say("NOTE", "rerun with --yes to apply")
    return 0


if __name__ == "__main__":
    utf8_output()
    sys.exit(main())
