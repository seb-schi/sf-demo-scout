"""Text rules shared by the string telephone and the build cards: what a reader can see, and the metadata types
Scout names when text leaves the builder's machine.

A character is unseen when a reader can't tell it's there and it isn't part of ordinary writing:
- controls other than tab and line break
- bidirectional embeddings, overrides and isolates
- zero-width spaces, word joiners, byte-order marks and other format characters
- a zero-width joiner or non-joiner that doesn't sit between two visible characters
- tag characters outside a flag emoji's tag sequence
- a variation selector that doesn't directly follow a visible character
- a lone surrogate

Persian and other scripts' joining marks, emoji sequences, flags, ideographic variants, soft hyphens and the marks
right-to-left text uses all stay as they are.
"""
from __future__ import annotations

import re
import unicodedata

BIDI_CONTROLS = frozenset(range(0x202A, 0x202F)) | frozenset(range(0x2066, 0x206A))
JOINERS = frozenset((0x200C, 0x200D))
# Format characters ordinary text uses: the soft hyphen, the right-to-left marks, and the prepended number signs.
ORDINARY_FORMAT = frozenset((0x00AD, 0x061C, 0x200E, 0x200F, 0x06DD, 0x070F, 0x08E2, *range(0x0600, 0x0606)))
TAGS = range(0xE0020, 0xE0080)
BLACK_FLAG = 0x1F3F4
CANCEL_TAG = 0xE007F

CATEGORIES = {
    "Data model": ("customobject", "customfield", "recordtype", "globalvalueset", "standardvalueset", "validationrule",
                   "businessprocess", "custommetadatatype", "custommetadata", "customsetting"),
    "Automation": ("flow", "flowdefinition", "apextrigger", "workflow", "workflowrule", "approvalprocess"),
    "Code": ("apexclass", "lightningcomponentbundle", "lwc", "auradefinitionbundle", "aura", "apexpage",
             "apexcomponent", "staticresource"),
    "Experience and UI": ("flexipage", "layout", "compactlayout", "customapplication", "customtab", "listview",
                          "quickaction", "pathassistant", "weblink", "experiencebundle", "digitalexperiencebundle",
                          "network", "customsite", "site"),
    "AI and agents": ("genaiplannerbundle", "genaiplanner", "genaiplugin", "genaifunction", "genaiprompttemplate",
                      "bot", "botversion", "aiagent", "agent", "agentscript", "prompttemplate"),
    "Security and access": ("permissionset", "permissionsetgroup", "permissionsetassignment", "profile",
                            "sharingrules", "sharingrule", "queue", "role", "group"),
    "Analytics": ("report", "reportfolder", "reporttype", "customreporttype", "dashboard", "dashboardfolder"),
    "Data": ("data", "dataseeding", "record"),
}
CATEGORY_OF = {kind: category for category, kinds in CATEGORIES.items() for kind in kinds}
ALIASES = {"pagelayout": "layout", "lightningapp": "customapplication", "path": "pathassistant",
           "paths": "pathassistant", "businessprocesses": "businessprocess", "records": "record",
           "picklistvalues": "standardvalueset", "lightningwebcomponent": "lightningcomponentbundle",
           "lightningpage": "flexipage", "recordpage": "flexipage"}
ORDER = (*CATEGORIES, "Other")


def _selector(code: int) -> bool:
    return 0xFE00 <= code <= 0xFE0F or 0xE0100 <= code <= 0xE01EF


def _base(character: str) -> bool:
    """A character a joiner or selector may attach to: anything a reader sees, marks included."""
    return (unicodedata.category(character) not in ("Cc", "Cf", "Cs", "Zs", "Zl", "Zp")
            and not _selector(ord(character)))


def _in_flag(characters, index: int) -> bool:
    start = index
    while start > 0 and ord(characters[start - 1]) in TAGS:
        start -= 1
    end = index
    while end + 1 < len(characters) and ord(characters[end + 1]) in TAGS:
        end += 1
    return start > 0 and ord(characters[start - 1]) == BLACK_FLAG and ord(characters[end]) == CANCEL_TAG


def flags(value: str):
    """Yield (character, unseen) for each character of `value`."""
    characters = list(value)
    for index, character in enumerate(characters):
        code, category = ord(character), unicodedata.category(character)
        before = characters[index - 1] if index else ""
        after = characters[index + 1] if index + 1 < len(characters) else ""
        if character in "\t\n":
            hidden = False
        elif code in JOINERS:
            hidden = not (before and after and (_base(before) or _selector(ord(before))) and _base(after))
        elif _selector(code):
            hidden = not (before and _base(before))
        elif code in TAGS:
            hidden = not _in_flag(characters, index)
        elif code in BIDI_CONTROLS:
            hidden = True
        elif category == "Cf":
            hidden = code not in ORDINARY_FORMAT
        else:
            hidden = category in ("Cc", "Cs")
        yield character, hidden


def unseen(value: str) -> list:
    return [character for character, hidden in flags(value) if hidden]


def visible(value):
    """Text from another builder's tool as a reader sees it: each unseen character spelled out as ⟦U+XXXX⟧."""
    if not isinstance(value, str):
        return value
    return "".join("⟦U+%04X⟧" % ord(character) if hidden else character
                   for character, hidden in flags(value.replace("\r\n", "\n")))


def type_key(kind: str) -> str:
    key = re.sub(r"[\s_-]", "", kind).lower()
    return ALIASES.get(key, key)


def category(kind: str) -> str:
    key = type_key(kind)
    if key in CATEGORY_OF:
        return CATEGORY_OF[key]
    return "AI and agents" if key.startswith(("genai", "bot")) else "Other"


KNOWN_ELSEWHERE = frozenset(("emailtemplate", "translation", "customlabel", "remotesitesetting", "namedcredential",
                             "connectedapp"))


def known_type(kind: str):
    """The builder's spelling of a metadata type Scout knows by name, such as "CustomField" or "Custom Field"; None
    for anything else, so a phrase in a type field never leaves the machine. Only an exact entry counts: the
    "bot" and "genai" prefixes that sort a type into a category prove nothing here."""
    kind = kind.strip() if isinstance(kind, str) else ""
    key = type_key(kind)
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9 ]{0,39}", kind) and (key in CATEGORY_OF or key in KNOWN_ELSEWHERE):
        return kind
    return None
