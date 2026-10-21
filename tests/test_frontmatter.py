"""Strict frontmatter for the stricter hosts.

Codex's and Cursor's skill loaders read a SKILL.md's frontmatter as strict YAML and silently drop a skill whose
frontmatter isn't: a `: ` inside a plain value, or a value that starts with a backtick, is enough. These tests hold
every shipped skill, every command with frontmatter and the thin skills scripts/scout_install.py writes for Cursor to a
small, safe part of YAML, and name the file and line of anything outside it. Standard library only.

Each entry is `key: value`, where the value is one of:
- a plain scalar on its line, without `: ` or ` #`, not ending in `:` and not starting with a YAML indicator;
- a single- or double-quoted scalar, closed on its line, with only YAML's escapes;
- a block scalar (`>` or `|`, with an optional chomping and indentation indicator) and at least one indented line;
- nothing on the line and an indented block below: a mapping of entries like these, or a list of `- value` items.
A name and a description are required at the top, and no key appears twice.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True

INDICATORS = "`[]{}&*!|>%@-?:'\",#"  # YAML's indicator characters: a plain scalar can't start with one
KEY = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_-]*):(?: +(?P<value>.*))?")
ITEM = re.compile(r"- +(?P<value>.*)")
COMMENT = r"(?: +#.*)?"
BLOCK_HEADER = re.compile(r"[|>](?:[1-9][+-]?|[+-][1-9]?)?" + COMMENT)
# YAML's double-quoted escapes; a \u escape must name a character, never half of a surrogate pair.
ESCAPE = r"\\(?:[0abt\tnvfre \"/\\N_LP]|x[0-9A-Fa-f]{2}|u(?![dD][89abAB])[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8})"
DOUBLE = re.compile(r'"(?P<text>(?:[^"\\]|' + ESCAPE + r')*)"' + COMMENT)
SINGLE = re.compile(r"'(?P<text>(?:[^']|'')*)'" + COMMENT)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Frontmatter:
    """One frontmatter block's lines, checked; `first` is the file's line number of the block's first line."""

    def __init__(self, lines: list[str], first: int, where: str) -> None:
        self.lines, self.first, self.where, self.problems = lines, first, where, []

    def problem(self, index: int, message: str) -> None:
        self.problems.append("%s:%d: %s" % (self.where, self.first + index, message))

    def indent(self, index: int) -> int | None:
        """The line's indentation in spaces; None for a blank or comment line."""
        line = self.lines[index]
        content = line.lstrip(" ")
        if not content.strip() or content.startswith("#"):
            return None
        return len(line) - len(content)

    def next_content(self, index: int) -> int:
        while index < len(self.lines) and self.indent(index) is None:
            index += 1
        return index

    def deeper(self, index: int, indent: int) -> bool:
        """Whether the next content line after `index` is indented further than `indent`."""
        following = self.next_content(index + 1)
        return following < len(self.lines) and self.indent(following) > indent

    def skip_deeper(self, index: int, indent: int) -> int:
        """The index of the first line after `index` that is content at `indent` or less."""
        index += 1
        while index < len(self.lines) and (self.indent(index) is None or self.indent(index) > indent):
            index += 1
        return index

    def scalar(self, index: int, value: str) -> str | None:
        """A value on its own line: its text when it's a safe scalar, else None, with the problem noted."""
        if value.startswith('"'):
            match = DOUBLE.fullmatch(value)
            if not match:
                self.problem(index, "a double-quoted value that isn't closed on its line, or has an escape YAML lacks")
            return match and match["text"]
        if value.startswith("'"):
            match = SINGLE.fullmatch(value)
            if not match:
                self.problem(index, "a single-quoted value that isn't closed on its line (write a ' inside as '')")
            return match and match["text"]
        if value[0] in INDICATORS:
            self.problem(index, "a plain value can't start with %s; quote it or use a block scalar (>)" % value[0])
        elif ": " in value or value.endswith(":"):
            self.problem(index, "': ' in a plain value starts a mapping; quote it or use a block scalar (>)")
        elif re.search(r"\s#", value):
            self.problem(index, "' #' in a plain value starts a comment; quote it or use a block scalar (>)")
        else:
            return value
        return None

    def value(self, index: int, value: str | None, indent: int) -> tuple[int, str | None]:
        """The value after `key:` or `- ` on line `index`: where the entry ends, and its text when it's a string."""
        if not value:
            if self.deeper(index, indent):
                following = self.next_content(index + 1)
                return self.collection(following, self.indent(following))[0], None
            self.problem(index, "no value")
            return index + 1, None
        if value[0] in "|>":
            if not BLOCK_HEADER.fullmatch(value):
                self.problem(index, "a block scalar starts with | or >, then at most a chomping (+ or -) and an "
                                    "indentation indicator")
            if not self.deeper(index, indent):
                self.problem(index, "a block scalar with no indented lines")
                return index + 1, None
            # Blank lines and every deeper line belong to it, a # line too, all at least as deep as its first line.
            end, depth = index + 1, None
            explicit = re.search(r"[1-9]", value.split("#", 1)[0])
            while end < len(self.lines):
                line = self.lines[end]
                spaces = len(line) - len(line.lstrip(" "))
                if line.strip():
                    if spaces <= indent:
                        break
                    depth = depth or (indent + int(explicit.group()) if explicit else spaces)
                    if spaces < depth:
                        self.problem(end, "indented less than the block scalar's first line")
                end += 1
            return end, " ".join(line.strip() for line in self.lines[index + 1:end] if line.strip())
        text = self.scalar(index, value)
        if self.deeper(index, indent):
            self.problem(self.next_content(index + 1), "a continuation line, which YAML folds into the value above; "
                                                       "use a block scalar (>) for a long value")
            return self.skip_deeper(index, indent), None
        return index + 1, text

    def collection(self, index: int, indent: int) -> tuple[int, dict]:
        """The mapping or list whose entries start at `indent` spaces from line `index`: where it ends, and a
        mapping's keys, each with its line, its text when it's a string, and whether a problem was noted for it."""
        entries, kind = {}, None
        while index < len(self.lines):
            current = self.indent(index)
            if current is None:
                index += 1
                continue
            if current < indent:
                break
            line = self.lines[index][current:]
            if line.startswith("\t"):
                self.problem(index, "a tab in the indentation; YAML indents with spaces")
                index = self.skip_deeper(index, current)
                continue
            if current > indent:
                self.problem(index, "indented further than the entries around it")
                index = self.skip_deeper(index, current)
                continue
            item, entry = ITEM.fullmatch(line), KEY.fullmatch(line)
            shape = "list" if item else "mapping" if entry else None
            if shape is None:
                self.problem(index, "not a `key: value` line" if not line.startswith("-") else "an empty list item")
                index = self.skip_deeper(index, current)
                continue
            if kind not in (None, shape):
                self.problem(index, "list items and keys mixed in one block")
            kind = kind or shape
            if item:
                index = self.value(index, item["value"], current)[0]
                continue
            key = entry["key"]
            if key in entries:
                self.problem(index, "%s appears twice; strict loaders refuse a duplicate key" % key)
            line_index, before = index, len(self.problems)
            index, text = self.value(index, entry["value"], current)
            entries.setdefault(key, (line_index, text, len(self.problems) > before))
        return index, entries


def problems(text: str, where: str) -> list[str]:
    """Every problem in the frontmatter at the start of `text`, as `where:line: problem`."""
    if text.startswith("\ufeff"):
        return ["%s:1: a byte-order mark before the frontmatter" % where]
    lines = text.split("\n")
    if lines[0] != "---":
        return ["%s:1: no frontmatter: the file must start with a --- line" % where]
    if "---" not in lines[1:]:
        return ["%s:1: the frontmatter isn't closed with a --- line" % where]
    block = Frontmatter(lines[1:lines.index("---", 1)], 2, where)
    entries = block.collection(0, 0)[1]
    for key in ("name", "description"):
        if key not in entries:
            block.problems.append("%s: no %s" % (where, key))
        elif not entries[key][2] and not (entries[key][1] or "").strip():
            block.problem(entries[key][0], "%s needs a string value" % key)
    return block.problems


def shipped() -> list[tuple[str, str]]:
    """(where, text) for every skill, every command with frontmatter, and the thin skills the installer writes."""
    found = [(str(path.relative_to(ROOT)), path.read_text(encoding="utf-8"))
             for path in sorted((ROOT / "skills").glob("*/SKILL.md"))]
    # Every command is a slash command with frontmatter, so each is checked whatever it starts with: a BOM or a lost
    # opening line is one of the problems to catch, not a reason to skip the file.
    found += [(str(path.relative_to(ROOT)), path.read_text(encoding="utf-8"))
              for path in sorted((ROOT / "commands").glob("*.md"))]
    install = load("scout_install_frontmatter", ROOT / "scripts" / "scout_install.py")
    found += [("the Cursor skill scout_install.py writes for %s" % name, install.thin_skill(name))
              for name in install.SKILLS]
    return found


class FrontmatterTests(unittest.TestCase):
    def test_every_shipped_frontmatter_is_strict_yaml(self) -> None:
        files = shipped()
        self.assertGreaterEqual(len([where for where, _ in files if where.startswith("skills")]), 6)
        self.assertEqual(len([where for where, _ in files if where.startswith("the Cursor skill")]), 2)
        self.assertEqual(sorted(where for where, _ in files if where.startswith("commands")),
                         sorted(str(path.relative_to(ROOT)) for path in (ROOT / "commands").glob("*.md")))
        found = [problem for where, text in files for problem in problems(text, where)]
        self.assertEqual(found, [], "\n" + "\n".join(found))

    def test_a_command_saved_with_a_bom_or_without_its_opening_line_is_reported(self) -> None:
        good = (ROOT / "commands" / "scout-sparring.md").read_text(encoding="utf-8")
        for name, text in (("a BOM", "\ufeff" + good), ("no opening line", good.split("\n", 1)[1])):
            with self.subTest(case=name):
                self.assertNotEqual(problems(text, "commands/scout-sparring.md"), [])

    def test_the_check_names_the_file_and_line_of_each_trap(self) -> None:
        def check(*lines: str) -> list[str]:
            return problems("---\n%s\n---\nbody\n" % "\n".join(lines), "SKILL.md")

        valid = ("name: scout", "description: Builds demo items, with read-back.", "argument-hint: \"[request]\"",
                 "single: 'it''s fine'", "escaped: \"a \\\"b\\\" \\u2014 c\"", "folded: >-", "  one: line", "",
                 "  # kept", "metadata:", "  version: \"2.1.0\" # a comment", "tools:", "  - Read", "  - Bash",
                 "# a comment line", "disable-model-invocation: true")
        self.assertEqual(check(*valid), [])
        traps = (
            ("description: Use it when: the builder asks", "': ' in a plain value"),
            ("description: `scout` builds demos", "can't start with `"),
            ("description: [a, b]", "can't start with ["),
            ("description: builds # demos", "' #' in a plain value"),
            ("description: ends with a colon:", "': ' in a plain value"),
            ('description: "never closed', "double-quoted value"),
            ('description: "a \\q escape"', "double-quoted value"),
            ('description: "half a pair \\ud83d"', "double-quoted value"),
            ("description: 'it's'", "single-quoted value"),
            ("description: >", "no indented lines"),
            ("description: >x", "a block scalar starts with"),
            ("description: >\n    four\n  two", "indented less than the block scalar's first line"),
            ("description: >2\n one", "indented less than the block scalar's first line"),
            ("description: one line\n  folded into it", "a continuation line"),
            ("description: one\ndescription: two", "description appears twice"),
            ("description: one\n\tindented: tab", "a tab in the indentation"),
            ("description: one\nnot a key", "not a `key: value` line"),
            ("description: one\nkey:value", "not a `key: value` line"),
            ("description: one\nempty:", "no value"),
            ("description: \"\"", "description needs a string value"),
            ("description:\n  nested: map", "description needs a string value"),
        )
        for lines, message in traps:
            with self.subTest(lines=lines):
                found = check("name: scout", lines)
                self.assertTrue(found, lines)
                self.assertTrue(all(re.match(r"SKILL\.md:[0-9]+: ", line) for line in found), found)
                self.assertIn(message, "\n".join(found))
        self.assertEqual(check("name: scout", "description: `scout`"),
                         ["SKILL.md:3: a plain value can't start with `; quote it or use a block scalar (>)"])
        self.assertEqual(check("name: scout"), ["SKILL.md: no description"])
        self.assertEqual(problems("# no frontmatter\n", "x.md"), ["x.md:1: no frontmatter: the file must start with a "
                                                                 "--- line"])
        self.assertEqual(problems("---\nname: x\n", "x.md"), ["x.md:1: the frontmatter isn't closed with a --- line"])


if __name__ == "__main__":
    unittest.main()
