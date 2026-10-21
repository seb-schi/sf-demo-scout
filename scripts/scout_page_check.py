#!/usr/bin/env python3
"""Check that a Lightning record page edit kept every existing component and region as it was.

Compares a FlexiPage after an edit (the edited file before a deploy, or the page read back from the org after one)
with its pre-edit snapshot. Every component and field already on the page must still be there, in the same region
and in the same order relative to the others, with the same content: its properties, visibility rule and everything
else inside it. Every existing region keeps its own settings, an empty one included. New components and regions are
listed, never judged. Properties are compared as a set, because the org may write them back in another order;
everything else keeps its order.

An approval is as narrow as the builder's yes: `--allow-property ID=NAME` lets one property of one component change
and nothing else about it, `--allow-move ID` lets one component move unchanged, `--allow-remove ID` lets one go, and
`--allow-page` lets the page's own settings change.

Prints one JSON object. Exit 0: everything existing kept, apart from what was approved; 3: something else changed;
2: a file couldn't be read or parsed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional, Set, Tuple
from xml.etree import ElementTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scout_portable  # noqa: E402  (ships beside this helper)

UNORDERED = {"componentInstanceProperties", "fieldInstanceProperties"}  # the org may write these in another order
ITEM_KINDS = ("componentInstance", "fieldInstance")


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def canonical(element: ElementTree.Element, skip: Set[str] = frozenset()) -> str:
    """The element as text, namespaces and layout whitespace dropped, properties sorted, and any property named in
    `skip` left out."""
    parts = []
    for child in element:
        if local(child.tag) in UNORDERED and child_text(child, "name") in skip:
            continue
        parts.append((local(child.tag) in UNORDERED, canonical(child, skip)))
    unordered = sorted(text for is_property, text in parts if is_property)
    ordered = [text for is_property, text in parts if not is_property]
    text = (element.text or "").strip()
    return "<%s>%s%s%s</%s>" % (local(element.tag), json.dumps(text) if text else "", "".join(unordered),
                                "".join(ordered), local(element.tag))


def child_text(element: ElementTree.Element, name: str) -> Optional[str]:
    for child in element:
        if local(child.tag) == name:
            return (child.text or "").strip()
    return None


def inventory(path: str) -> Tuple[Dict[str, dict], Dict[str, List[str]], Dict[str, str], str]:
    """(items by key, each region's item keys in order, each region's own settings, the page's own settings)."""
    root = ElementTree.parse(path).getroot()
    if local(root.tag) != "FlexiPage":
        raise ValueError("not a FlexiPage: %s" % local(root.tag))
    items: Dict[str, dict] = {}
    regions: Dict[str, List[str]] = {}
    region_settings: Dict[str, str] = {}
    settings = []
    for child in root:
        if local(child.tag) != "flexiPageRegions":
            settings.append(canonical(child))
            continue
        region = child_text(child, "name") or ""
        regions.setdefault(region, [])
        region_settings[region] = "".join(canonical(part) for part in child if local(part.tag) != "itemInstances")
        seen: Dict[str, int] = {}
        for item in child:
            if local(item.tag) != "itemInstances":
                continue
            inner = next((part for part in item if local(part.tag) in ITEM_KINDS), None)
            if inner is None:
                continue
            identifier = child_text(inner, "identifier")
            if identifier:
                key = identifier
            else:  # an older page without identifiers: its region, what it shows, and which one of those it is
                name = child_text(inner, "componentName") or child_text(inner, "fieldItem") or local(inner.tag)
                seen[name] = seen.get(name, 0) + 1
                key = "%s#%s#%d" % (region, name, seen[name])
            items[key] = {"region": region, "element": item}
            regions[region].append(key)
    return items, regions, region_settings, "".join(sorted(settings))


def compare(before: str, after: str, properties: Dict[str, Set[str]], moves: Set[str], removals: Set[str],
            page: bool) -> dict:
    old, old_regions, old_region_settings, old_settings = inventory(before)
    new, new_regions, new_region_settings, new_settings = inventory(after)
    missing = [key for key in old if key not in new]
    changed = []
    for key in old:
        if key in new:
            skip = properties.get(key, set())
            if canonical(new[key]["element"], skip) != canonical(old[key]["element"], skip):
                changed.append(key)
    moved = [key for key in old if key in new and new[key]["region"] != old[key]["region"]]
    for region, keys in old_regions.items():
        # Components that weren't approved to move keep their order relative to each other; new ones and approved
        # moves may sit between them.
        steady = [key for key in keys if key in new and key not in moves and new[key]["region"] == region]
        now = [key for key in new_regions.get(region, []) if key in steady]
        if now != steady:
            moved.extend(key for key, was in zip(now, steady) if key != was and key not in moved)
    regions_missing = [region for region in old_regions if region not in new_regions]
    regions_changed = [region for region in old_regions if region in new_regions
                       and new_region_settings[region] != old_region_settings[region]]
    settings = "same" if new_settings == old_settings else "changed"
    problems = ([key for key in missing if key not in removals] + changed
                + [key for key in moved if key not in moves]
                + ["region:" + region for region in regions_missing + regions_changed])
    if settings == "changed" and not page:
        problems.append("page")
    return {"state": "changed" if problems else "kept", "existing": len(old),
            "added": [key for key in new if key not in old], "changed": changed, "moved": moved,
            "missing": missing, "regions_missing": regions_missing, "regions_changed": regions_changed,
            "page_settings": settings, "not_allowed": problems}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check that a record page edit kept every existing component.")
    parser.add_argument("--before", required=True, help="the pre-edit snapshot's .flexipage-meta.xml")
    parser.add_argument("--after", required=True, help="the edited file, or the page read back after the deploy")
    parser.add_argument("--allow-property", action="append", default=[], metavar="ID=NAME",
                        help="one property of one existing component the builder approved changing; repeat for each")
    parser.add_argument("--allow-move", action="append", default=[], metavar="ID",
                        help="an existing component the builder approved moving, unchanged")
    parser.add_argument("--allow-remove", action="append", default=[], metavar="ID",
                        help="an existing component the builder approved removing")
    parser.add_argument("--allow-page", action="store_true", help="the builder approved changing the page's own settings")
    args = parser.parse_args(argv)
    properties: Dict[str, Set[str]] = {}
    for pair in args.allow_property:
        identifier, sep, name = pair.partition("=")
        if not sep or not identifier or not name:
            parser.error("--allow-property takes ID=NAME")
        properties.setdefault(identifier, set()).add(name)
    try:
        result = compare(args.before, args.after, properties, set(args.allow_move), set(args.allow_remove),
                         args.allow_page)
    except (OSError, ValueError, ElementTree.ParseError) as error:
        print(json.dumps({"state": "unreadable", "reason": str(error)}))
        return 2
    print(json.dumps(result))
    return 0 if result["state"] == "kept" else 3


if __name__ == "__main__":
    scout_portable.utf8_output()
    raise SystemExit(main())
