"""Static cross-file audit route contracts.

These checks resolve Markdown route targets and section order. They do not prove
model compliance, notification timing, background scheduling, or live org behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


@dataclass(frozen=True)
class Heading:
    level: int
    title: str
    start: int
    body_start: int
    end: int


def headings(document: str) -> list[Heading]:
    matches = list(re.finditer(r"^(#{1,6})\s+(.+?)\s*$", document, re.MULTILINE))
    result: list[Heading] = []
    for index, match in enumerate(matches):
        level = len(match.group(1))
        end = len(document)
        for following in matches[index + 1 :]:
            if len(following.group(1)) <= level:
                end = following.start()
                break
        result.append(
            Heading(
                level=level,
                title=match.group(2),
                start=match.start(),
                body_start=match.end(),
                end=end,
            )
        )
    return result


def heading(document: str, title: str) -> Heading:
    matches = [candidate for candidate in headings(document) if candidate.title == title]
    if len(matches) != 1:
        raise AssertionError(f"expected one heading {title!r}, found {len(matches)}")
    return matches[0]


def section(document: str, title: str) -> str:
    match = heading(document, title)
    return document[match.body_start : match.end]


def markdown_table(document: str, heading_title: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in section(document, heading_title).splitlines()]
    table_lines: list[str] = []
    for line in lines:
        if line.startswith("|"):
            table_lines.append(line)
        elif table_lines:
            break
    if len(table_lines) < 3:
        raise AssertionError(f"missing table below {heading_title!r}")
    headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    rows = []
    for line in table_lines[2:]:
        values = [cell.strip() for cell in line.strip("|").split("|")]
        if len(values) != len(headers):
            raise AssertionError(f"malformed table row below {heading_title!r}: {line}")
        rows.append(dict(zip(headers, values)))
    return rows


class AuditRouteContractTests(unittest.TestCase):
    def test_unknown_agent_source_evidence_cannot_trigger_ui_built_fork(self) -> None:
        iteration = read("prompts/sparring/iteration.md")
        rows = markdown_table(iteration, "Agent source evidence gate")
        actual = {
            row["Classification"]: (row["UI-built fork allowed"], row["Next step"])
            for row in rows
        }
        self.assertEqual(actual["source-confirmed"][0], "no")
        self.assertEqual(actual["source-absence-confirmed"][0], "yes")
        self.assertEqual(
            actual["unknown"],
            ("no", "targeted source/metadata follow-up; remain unknown if unavailable"),
        )


if __name__ == "__main__":
    unittest.main()
