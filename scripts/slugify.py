#!/usr/bin/env python3
"""Canonical folder-slug transform for SF Demo Scout.

Reference implementation that /scout runs to match customer folders
(skills/scout/SKILL.md); mirrors prompts/sparring/slug-rule.md. Input: ONE
alias or customer token as argv[1]. Output: the slug on stdout, exit 0. If no
usable slug results (empty input or a token that reduces to nothing), print
nothing and exit 1.

The alias is read as a command ARGUMENT, never interpolated into program
source, so alias characters are always data (never shell/regex/glob syntax).
"""
import os
import sys
import re
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scout_portable  # noqa: E402  (ships beside this helper)

# Explicit transliterations for characters NFKD does NOT decompose.
EXPLICIT = {
    "ß": "ss",
    "ø": "o", "Ø": "o",
    "æ": "ae", "Æ": "ae",
    "œ": "oe", "Œ": "oe",
    "đ": "d", "Đ": "d",
    "ł": "l", "Ł": "l",
}

MAX_LEN = 40


def slugify(text):
    # 1. Lowercase.
    text = text.lower()
    # 2. Strip diacritics: explicit map first (non-decomposing chars), then
    #    NFKD split + drop combining marks (é->e, ü->u, ñ->n, ...).
    text = "".join(EXPLICIT.get(ch, ch) for ch in text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    # 3. Every run of non-[a-z0-9] becomes a single hyphen.
    text = re.sub(r"[^a-z0-9]+", "-", text)
    # 4. Trim leading/trailing hyphens.
    text = text.strip("-")
    # 5. Truncate at 40 chars. Inspect the boundary in the UNSLICED string so a
    #    complete segment ending exactly at the cut is preserved:
    #      - if char[MAX_LEN] is the separator, the first MAX_LEN chars already
    #        end at a whole segment -> keep them;
    #      - otherwise the cut is inside a segment -> keep the first MAX_LEN and
    #        drop the partial trailing segment; if there is no separator in that
    #        prefix (overlong FIRST segment), keep the hard 40-char cut.
    if len(text) > MAX_LEN:
        if text[MAX_LEN] == "-":
            text = text[:MAX_LEN]
        else:
            head = text[:MAX_LEN]
            if "-" in head:
                head = head.rsplit("-", 1)[0]
            text = head
        text = text.strip("-")
    return text


def developer_name(label):
    """A Custom Metadata record's DeveloperName from its label: the official skill's sanitize-developer-name rule
    (runs of other characters become `_`, no leading or trailing `_`, an `X` before a leading digit, 40 at most)."""
    text = re.sub(r"[^A-Za-z0-9]+", "_", label).lstrip("_")
    text = re.sub(r"^([0-9])", r"X\1", text).rstrip("_")
    return text[:MAX_LEN].rstrip("_")


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--developer-name":
        name = developer_name(sys.argv[2])
        if not name:
            sys.exit(1)
        print(name)
        return
    if len(sys.argv) < 2:
        sys.exit(1)
    slug = slugify(sys.argv[1])
    if not slug:
        sys.exit(1)
    print(slug)


if __name__ == "__main__":
    scout_portable.utf8_output()
    main()
