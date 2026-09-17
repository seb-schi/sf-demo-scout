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
BARRIER_REF = (
    "prompts/sparring/audit-orchestration.md"
    "#phase-c-audit-ready-barrier"
)


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


def resolve_reference(reference: str) -> Heading:
    relative_path, anchor = reference.split("#", 1)
    document = read(relative_path)
    anchors = list(
        re.finditer(rf'^<a id="{re.escape(anchor)}"></a>\s*$', document, re.MULTILINE)
    )
    if len(anchors) != 1:
        raise AssertionError(
            f"{reference!r} resolves to {len(anchors)} explicit anchors in {relative_path}"
        )
    following = [item for item in headings(document) if item.start > anchors[0].end()]
    if not following or document[anchors[0].end() : following[0].start].strip():
        raise AssertionError(f"{reference!r} is not immediately followed by a heading")
    return following[0]


def assert_reference_order(
    case: unittest.TestCase,
    document: str,
    route_heading: str,
    before_text: str,
    reference: str,
    consumer_heading: str,
) -> None:
    route = heading(document, route_heading)
    before_position = document.index(before_text, route.body_start, route.end)
    reference_position = document.index(reference, route.body_start, route.end)
    case.assertLess(before_position, reference_position)
    case.assertLess(reference_position, heading(document, consumer_heading).start)


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
    def test_fresh_routes_resolve_one_barrier_before_audit_consumers(self) -> None:
        barrier = resolve_reference(BARRIER_REF)
        self.assertEqual(barrier.title, "Phase C — AUDIT-READY barrier")

        sparring = read("commands/scout-sparring.md")
        assert_reference_order(
            self,
            sparring,
            "Stage 3: Full Discovery",
            "**Stop and wait for answers.**",
            BARRIER_REF,
            "Stage 4: Platform & Data Model Research",
        )

        iteration = read("prompts/sparring/iteration.md")
        assert_reference_order(
            self,
            iteration,
            "Stage 3i: Iteration Discovery",
            "**Stop and wait for answers.**",
            BARRIER_REF,
            "Deferred reconciliation",
        )
        self.assertLess(
            heading(iteration, "Deferred reconciliation").start,
            heading(iteration, "Delta Conflict Check").start,
        )

        showtime = read("prompts/sparring/showtime.md")
        assert_reference_order(
            self,
            showtime,
            "Step S2 — Transcript Paste",
            "SE says `go`",
            BARRIER_REF,
            "Step S3 — Auto-Extract (silent)",
        )

    def test_order_check_rejects_a_removed_or_late_showtime_barrier(self) -> None:
        showtime = read("prompts/sparring/showtime.md")
        removed = showtime.replace(BARRIER_REF, "missing-barrier", 1)
        with self.assertRaises(ValueError):
            assert_reference_order(
                self,
                removed,
                "Step S2 — Transcript Paste",
                "SE says `go`",
                BARRIER_REF,
                "Step S3 — Auto-Extract (silent)",
            )

        late = showtime.replace(BARRIER_REF, "moved-barrier", 1).replace(
            "## Step S3 — Auto-Extract (silent)",
            f"## Step S3 — Auto-Extract (silent)\n\n{BARRIER_REF}",
            1,
        )
        with self.assertRaises(ValueError):
            assert_reference_order(
                self,
                late,
                "Step S2 — Transcript Paste",
                "SE says `go`",
                BARRIER_REF,
                "Step S3 — Auto-Extract (silent)",
            )

    def test_reused_iteration_reconciles_after_sync_read_and_before_questions(self) -> None:
        sparring = read("commands/scout-sparring.md")
        self.assertLess(
            sparring.index("set `AUDIT_MODE = reused`, read that selected audit"),
            sparring.index("execute Stage 3i"),
        )

        iteration = read("prompts/sparring/iteration.md")
        self.assertLess(
            heading(iteration, "Reused-audit reconciliation").start,
            heading(iteration, "Audit-independent iteration questions").start,
        )
        reused = section(iteration, "Reused-audit reconciliation")
        self.assertIn("`AUDIT_MODE = reused`", reused)
        self.assertIn("execute", reused)

    def test_audit_modes_keep_reuse_and_explicit_skip_distinct(self) -> None:
        sparring = read("commands/scout-sparring.md")
        rows = markdown_table(sparring, "Audit route states")
        actual = {
            row["Branch"]: (
                row["`AUDIT_MODE`"],
                row["Fresh work"],
                row["Current audit usable"],
            )
            for row in rows
        }
        self.assertEqual(
            actual,
            {
                "Reuse": ("`reused`", "none", "yes — selected file"),
                "Fresh": ("`background-fresh`", "Phase A, then barrier", "after ready outcome"),
                "SE skip": ("`skipped`", "none", "no"),
            },
        )

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
