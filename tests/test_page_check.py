"""scout_page_check.py: a record page edit keeps every existing component as it was (2.4.1).

A structural read-back (identifiers, parents, order) missed an existing component whose properties or visibility rule
changed. The checker compares each existing component's whole content with the pre-edit snapshot.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("scout_page_check", ROOT / "scripts" / "scout_page_check.py")
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)

NS = 'xmlns="http://soap.sforce.com/2006/04/metadata"'


def component(identifier, name, properties=(), rule=""):
    props = "".join("<componentInstanceProperties><name>%s</name><value>%s</value></componentInstanceProperties>"
                    % pair for pair in properties)
    ident = "<identifier>%s</identifier>" % identifier if identifier else ""
    return ("<itemInstances><componentInstance>%s<componentName>%s</componentName>%s%s</componentInstance>"
            "</itemInstances>" % (props, name, ident, rule))


def region(name, items, kind="Region"):
    return "<flexiPageRegions>%s<name>%s</name><type>%s</type></flexiPageRegions>" % ("".join(items), name, kind)


def page(regions, template="flexipage:recordHomeTemplateDesktop"):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<FlexiPage %s>%s<masterLabel>Quote</masterLabel>'
            "<template><name>%s</name></template><type>RecordPage</type></FlexiPage>" % (NS, "".join(regions), template))


RULE = ("<visibilityRule><criteria><leftValue>{!Record.Status}</leftValue><operator>EQUAL</operator>"
        "<rightValue>Draft</rightValue></criteria></visibilityRule>")
TABS = region("tabs", [component("detailTab", "flexipage:tab", [("body", "detailFacet"), ("title", "Details")])],
              kind="Facet")
MAIN = region("main", [component("tabset", "flexipage:tabset", [("tabs", "tabs")]),
                       component("note", "flexipage:richText", [("richTextValue", "Hello")], RULE)])
BEFORE = page([TABS, MAIN])


class PageCheckTests(unittest.TestCase):
    def check(self, after, before=BEFORE, extra=()):
        with tempfile.TemporaryDirectory(prefix="scout-page-check-") as folder:
            old, new = Path(folder) / "before.xml", Path(folder) / "after.xml"
            old.write_text(before, encoding="utf-8")
            new.write_text(after, encoding="utf-8")
            args = ["--before", str(old), "--after", str(new), *extra]
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = CHECK.main(args)
            return code, json.loads(output.getvalue())

    def test_an_additive_edit_keeps_every_existing_component(self):
        tabs = region("tabs", [component("detailTab", "flexipage:tab", [("body", "detailFacet"), ("title", "Details")]),
                               component("approvalsTab", "flexipage:tab", [("body", "approvalsFacet"),
                                                                           ("title", "Approvals")])], kind="Facet")
        facet = region("approvalsFacet", [component("workGuide", "runtime_approval:workGuide")], kind="Facet")
        code, result = self.check(page([tabs, MAIN, facet]))
        self.assertEqual((code, result["state"]), (0, "kept"))
        self.assertEqual(sorted(result["added"]), ["approvalsTab", "workGuide"])

    def test_a_changed_property_of_an_existing_component_is_caught(self):
        main = region("main", [component("tabset", "flexipage:tabset", [("tabs", "tabs")]),
                               component("note", "flexipage:richText", [("richTextValue", "Changed")], RULE)])
        code, result = self.check(page([TABS, main]))
        self.assertEqual((code, result["state"], result["changed"]), (3, "changed", ["note"]))

    def test_a_changed_or_lost_visibility_rule_is_caught(self):
        main = region("main", [component("tabset", "flexipage:tabset", [("tabs", "tabs")]),
                               component("note", "flexipage:richText", [("richTextValue", "Hello")])])
        code, result = self.check(page([TABS, main]))
        self.assertEqual((code, result["changed"]), (3, ["note"]))

    def test_a_missing_or_moved_component_is_caught(self):
        code, result = self.check(page([TABS, region("main", [component("tabset", "flexipage:tabset",
                                                                        [("tabs", "tabs")])])]))
        self.assertEqual((code, result["missing"]), (3, ["note"]))
        swapped = region("main", [component("note", "flexipage:richText", [("richTextValue", "Hello")], RULE),
                                  component("tabset", "flexipage:tabset", [("tabs", "tabs")])])
        code, result = self.check(page([TABS, swapped]))
        self.assertEqual(code, 3)
        self.assertTrue(result["moved"])
        elsewhere = region("side", [component("note", "flexipage:richText", [("richTextValue", "Hello")], RULE)])
        code, result = self.check(page([TABS, region("main", [component("tabset", "flexipage:tabset",
                                                                        [("tabs", "tabs")])]), elsewhere]))
        self.assertEqual((code, result["moved"]), (3, ["note"]))

    def test_properties_written_back_in_another_order_are_the_same(self):
        before = page([region("main", [component("c", "x:y", [("a", "1"), ("b", "2")])])])
        code, result = self.check(page([region("main", [component("c", "x:y", [("b", "2"), ("a", "1")])])]), before)
        self.assertEqual((code, result["state"]), (0, "kept"))

    def test_an_approved_property_change_allows_that_property_and_nothing_else(self):
        changed_text = region("main", [component("tabset", "flexipage:tabset", [("tabs", "tabs")]),
                                       component("note", "flexipage:richText", [("richTextValue", "Changed")], RULE)])
        approval = ["--allow-property", "note=richTextValue"]
        self.assertEqual(self.check(page([TABS, changed_text]), extra=approval)[0], 0)
        # The approved text change doesn't cover a lost visibility rule, a deletion, or another component.
        lost_rule = region("main", [component("tabset", "flexipage:tabset", [("tabs", "tabs")]),
                                    component("note", "flexipage:richText", [("richTextValue", "Changed")])])
        code, result = self.check(page([TABS, lost_rule]), extra=approval)
        self.assertEqual((code, result["not_allowed"]), (3, ["note"]))
        gone = region("main", [component("tabset", "flexipage:tabset", [("tabs", "tabs")])])
        code, result = self.check(page([TABS, gone]), extra=approval)
        self.assertEqual((code, result["not_allowed"]), (3, ["note"]))
        self.assertEqual(self.check(page([TABS, changed_text]), extra=["--allow-property", "tabset=tabs"])[0], 3)

    def test_an_approved_move_keeps_the_neighbours_order_and_the_content(self):
        before = page([region("main", [component("a", "x:a"), component("b", "x:b"), component("c", "x:c")])])
        a_last = page([region("main", [component("b", "x:b"), component("c", "x:c"), component("a", "x:a")])])
        code, result = self.check(a_last, before, extra=["--allow-move", "a"])
        self.assertEqual((code, result["not_allowed"]), (0, []))
        self.assertEqual(self.check(a_last, before)[0], 3)
        neighbours_swapped = page([region("main", [component("c", "x:c"), component("b", "x:b"), component("a", "x:a")])])
        self.assertEqual(self.check(neighbours_swapped, before, extra=["--allow-move", "a"])[0], 3)
        moved_and_changed = page([region("main", [component("b", "x:b"), component("c", "x:c"),
                                                  component("a", "x:a", [("p", "1")])])])
        self.assertEqual(self.check(moved_and_changed, before, extra=["--allow-move", "a"])[0], 3)

    def test_an_approved_removal_allows_only_that_removal(self):
        gone = region("main", [component("tabset", "flexipage:tabset", [("tabs", "tabs")])])
        self.assertEqual(self.check(page([TABS, gone]), extra=["--allow-remove", "note"])[0], 0)
        self.assertEqual(self.check(page([TABS, gone]), extra=["--allow-remove", "tabset"])[0], 3)

    def test_a_regions_own_settings_and_empty_regions_count(self):
        retyped = region("tabs", [component("detailTab", "flexipage:tab", [("body", "detailFacet"),
                                                                          ("title", "Details")])], kind="Region")
        code, result = self.check(page([retyped, MAIN]))
        self.assertEqual((code, result["regions_changed"]), (3, ["tabs"]))
        with_empty = page([TABS, MAIN, region("sidebar", [])])
        code, result = self.check(page([TABS, MAIN]), with_empty)
        self.assertEqual((code, result["regions_missing"]), (3, ["sidebar"]))

    def test_components_without_identifiers_are_matched_by_region_and_name(self):
        before = page([region("main", [component(None, "force:highlightsPanel"), component(None, "force:detailPanel")])])
        added = page([region("main", [component(None, "force:highlightsPanel"), component(None, "force:detailPanel"),
                                      component(None, "force:relatedListContainer")])])
        self.assertEqual(self.check(added, before)[0], 0)
        lost = page([region("main", [component(None, "force:highlightsPanel")])])
        code, result = self.check(lost, before)
        self.assertEqual((code, result["missing"]), (3, ["main#force:detailPanel#1"]))

    def test_the_pages_own_settings_count_too(self):
        code, result = self.check(page([TABS, MAIN], template="flexipage:recordHomeSimpleViewTemplate"))
        self.assertEqual((code, result["page_settings"], result["not_allowed"]), (3, "changed", ["page"]))
        self.assertEqual(self.check(page([TABS, MAIN], template="flexipage:recordHomeSimpleViewTemplate"),
                                    extra=["--allow-page"])[0], 0)

    def test_an_unreadable_file_is_said_plainly(self):
        code, result = self.check("<FlexiPage", BEFORE)
        self.assertEqual((code, result["state"]), (2, "unreadable"))
        code, result = self.check('<Layout %s/>' % NS)
        self.assertEqual((code, result["state"]), (2, "unreadable"))


if __name__ == "__main__":
    unittest.main()
