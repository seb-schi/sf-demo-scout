#!/usr/bin/env python3
"""Safely perform Scout's narrowly scoped settings operations: marketplace auto-update and refs, and the workspace env."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
from typing import Callable, NoReturn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scout_portable  # noqa: E402  (ships beside this helper)


class SettingsError(Exception):
    pass


class DuplicateKey(SettingsError):
    pass


class JsoncError(SettingsError):
    pass


def path_present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def explicit_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise SettingsError("settings path must be absolute")
    if ".." in path.parts:
        raise SettingsError("settings path must not contain '..'")
    return path


def has_symlink_component(path: Path) -> bool:
    current = path
    while True:
        if current.is_symlink():
            return True
        if current == current.parent:
            return False
        current = current.parent


def read_regular(path: Path) -> tuple[bytes, int]:
    if has_symlink_component(path):
        raise SettingsError("settings path or ancestor is a symlink")
    if not path.exists():
        raise FileNotFoundError(path)
    try:
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode):
            raise SettingsError("settings path is not a regular file")
        return path.read_bytes(), stat.S_IMODE(metadata.st_mode)
    except OSError as error:
        raise SettingsError(str(error)) from error


def strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateKey(f"duplicate key: {key}")
        value[key] = item
    return value


def load_strict_json(content: bytes) -> dict[str, object]:
    def reject_constant(value: str) -> NoReturn:
        raise SettingsError(f"non-finite JSON constant is unsupported: {value}")

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise SettingsError(f"non-finite JSON number is unsupported: {value}")
        return parsed

    try:
        value = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=strict_object,
            parse_constant=reject_constant,
            parse_float=finite_float,
        )
    except (UnicodeError, json.JSONDecodeError, DuplicateKey) as error:
        raise SettingsError(str(error)) from error
    if not isinstance(value, dict):
        raise SettingsError("top-level value must be an object")
    return value


@dataclass(frozen=True)
class Token:
    kind: str
    value: object
    start: int
    end: int


@dataclass
class Element:
    node: "Node"
    comma_after: Token | None = None


@dataclass
class Member:
    key: str
    value: "Node"


@dataclass
class Node:
    kind: str
    value: object
    start: int
    end: int
    members: list[Member] = field(default_factory=list)
    elements: list[Element] = field(default_factory=list)


NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")


def tokenize_jsonc(source: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0
    length = len(source)
    while index < length:
        character = source[index]
        if character.isspace():
            index += 1
            continue
        if source.startswith("//", index):
            newline = source.find("\n", index + 2)
            index = length if newline < 0 else newline + 1
            continue
        if source.startswith("/*", index):
            close = source.find("*/", index + 2)
            if close < 0:
                raise JsoncError("unterminated block comment")
            index = close + 2
            continue
        if character in "{}[]: ,":
            if character != " ":
                tokens.append(Token(character, character, index, index + 1))
            index += 1
            continue
        if character == '"':
            start = index
            index += 1
            while index < length:
                if source[index] == "\\":
                    index += 2
                    continue
                if source[index] == '"':
                    index += 1
                    break
                index += 1
            else:
                raise JsoncError("unterminated string")
            raw = source[start:index]
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as error:
                raise JsoncError(str(error)) from error
            tokens.append(Token("string", value, start, index))
            continue
        match = NUMBER.match(source, index)
        if match:
            raw = match.group(0)
            tokens.append(Token("number", json.loads(raw), index, match.end()))
            index = match.end()
            continue
        literal = next(
            (item for item in ("true", "false", "null") if source.startswith(item, index)),
            None,
        )
        if literal is not None:
            values = {"true": True, "false": False, "null": None}
            tokens.append(Token("literal", values[literal], index, index + len(literal)))
            index += len(literal)
            continue
        raise JsoncError(f"unsupported token at character {index}")
    return tokens


class JsoncParser:
    def __init__(self, source: str) -> None:
        self.tokens = tokenize_jsonc(source)
        self.position = 0

    def peek(self) -> Token | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def take(self, kind: str | None = None) -> Token:
        token = self.peek()
        if token is None or (kind is not None and token.kind != kind):
            actual = "end of input" if token is None else token.kind
            raise JsoncError(f"expected {kind or 'token'}, got {actual}")
        self.position += 1
        return token

    def parse(self) -> Node:
        node = self.parse_value()
        if self.peek() is not None:
            raise JsoncError("unexpected token after top-level value")
        return node

    def parse_value(self) -> Node:
        token = self.peek()
        if token is None:
            raise JsoncError("expected value, got end of input")
        if token.kind == "{":
            return self.parse_object()
        if token.kind == "[":
            return self.parse_array()
        if token.kind in {"string", "number", "literal"}:
            token = self.take()
            return Node(token.kind, token.value, token.start, token.end)
        raise JsoncError(f"unexpected token {token.kind}")

    def parse_object(self) -> Node:
        opening = self.take("{")
        value: dict[str, object] = {}
        members: list[Member] = []
        if self.peek() is not None and self.peek().kind == "}":
            closing = self.take("}")
            return Node("object", value, opening.start, closing.end, members=members)
        while True:
            key_token = self.take("string")
            key = str(key_token.value)
            if key in value:
                raise JsoncError(f"duplicate key: {key}")
            self.take(":")
            child = self.parse_value()
            value[key] = child.value
            members.append(Member(key, child))
            token = self.peek()
            if token is not None and token.kind == ",":
                self.take(",")
                if self.peek() is not None and self.peek().kind == "}":
                    closing = self.take("}")
                    return Node("object", value, opening.start, closing.end, members=members)
                continue
            closing = self.take("}")
            return Node("object", value, opening.start, closing.end, members=members)

    def parse_array(self) -> Node:
        opening = self.take("[")
        elements: list[Element] = []
        values: list[object] = []
        if self.peek() is not None and self.peek().kind == "]":
            closing = self.take("]")
            return Node("array", values, opening.start, closing.end, elements=elements)
        while True:
            child = self.parse_value()
            element = Element(child)
            elements.append(element)
            values.append(child.value)
            token = self.peek()
            if token is not None and token.kind == ",":
                element.comma_after = self.take(",")
                if self.peek() is not None and self.peek().kind == "]":
                    closing = self.take("]")
                    return Node("array", values, opening.start, closing.end, elements=elements)
                continue
            closing = self.take("]")
            return Node("array", values, opening.start, closing.end, elements=elements)


def parse_jsonc(content: bytes) -> tuple[str, Node]:
    try:
        source = content.decode("utf-8")
    except UnicodeError as error:
        raise JsoncError(str(error)) from error
    root = JsoncParser(source).parse()
    if root.kind != "object":
        raise JsoncError("top-level value must be an object")
    return source, root


def json_bytes(value: dict[str, object]) -> bytes:
    return (json.dumps(value, indent=2) + "\n").encode("utf-8")


WORKSPACE_ENV_KEYS = {"SF_DISABLE_PLUGIN_MATCH": "1"}  # the official plugin's recommender off in Scout's workspace


def guarded_json_update(path: Path, prefix: str, suffix: str, change: Callable[[dict[str, object]], str | None]) -> str:
    """Apply one narrow change to a strict JSON settings file, never over a newer save: back up under a unique name,
    re-read just before replacing (abort when the file changed meanwhile), validate, and restore only while the
    file still holds Scout's bytes."""
    label = path.name
    try:
        original, mode = read_regular(path)
    except FileNotFoundError:
        return f"{prefix}_ABSENT[{label}]"
    except SettingsError as error:
        return f"{prefix}_UNSAFE_FILE[{label}]: {error}"
    try:
        data = load_strict_json(original)
    except SettingsError as error:
        return f"{prefix}_PARSE_ERROR[{label}]: {error}"
    outcome = change(data)
    if outcome is not None:
        return f"{prefix}_{outcome}[{label}]"
    replacement = json_bytes(data)
    stamp = f"{path.name}{suffix}-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    temporary = None
    try:
        for attempt in range(100):  # exclusive and unique: an earlier backup, even from this same second, is kept
            backup = path.with_name(stamp if attempt == 0 else f"{stamp}-{attempt}")
            try:
                with open(backup, "xb") as stream:
                    stream.write(original)
                break
            except FileExistsError:
                continue
        else:
            return f"{prefix}_WRITE_FAILED[{label}]: no free backup name"
        os.chmod(backup, mode)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(replacement)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        if path.read_bytes() != original:
            return f"{prefix}_CHANGED_MEANWHILE[{label}]: rerun setup"
        scout_portable.replace(temporary, path)  # closed first; on Windows a brief scanner hold is ridden out
        temporary = None
    except OSError as error:
        return f"{prefix}_WRITE_FAILED[{label}]: {error}"
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    try:
        load_strict_json(path.read_bytes())
    except (OSError, SettingsError):
        try:
            if path.read_bytes() == replacement:  # still Scout's write: put the original back
                path.write_bytes(original)
                return f"{prefix}_POST_WRITE_FAILED[{label}]: original restored; backup {backup.name}"
        except OSError:
            pass
        return f"{prefix}_POST_WRITE_FAILED[{label}]: left as found; backup {backup.name}"
    return f"{prefix}_SET[{label}]"


def run_marketplace_autoupdate(path: Path, name: str) -> str:
    """Turn auto-update on for one declared marketplace when the user hasn't set it; the entry must already exist."""
    def change(data: dict[str, object]) -> str | None:
        entry = data.get("extraKnownMarketplaces", {}).get(name) if isinstance(data.get("extraKnownMarketplaces"), dict) else None
        if not isinstance(entry, dict):
            return "NO_ENTRY"
        if entry.get("autoUpdate") is True:
            return "ALREADY"
        if "autoUpdate" in entry:
            return "LEFT_AS_CHOSEN"  # an explicit choice, false included, is the user's
        entry["autoUpdate"] = True
        return None
    return guarded_json_update(path, "AUTOUPDATE", ".scout-bak-autoupdate", change)


def run_marketplace_ref(path: Path, name: str, ref: str | None, expect_ref: str | None = None,
                        expect_source: dict | None = None) -> str:
    """Remove (ref None) or restore one declared marketplace's pinned ref, compare-and-set: removal only while the
    ref is still `expect_ref`, restoration only while the source is still exactly `expect_source` (Scout's own
    post-unpin form). Anything else is the builder's newer choice, kept as found (CHANGED). Claude Code accepts a re-add
    only from the source this entry lists, so setup changes the entry first."""
    def change(data: dict[str, object]) -> str | None:
        entry = data.get("extraKnownMarketplaces", {}).get(name) if isinstance(data.get("extraKnownMarketplaces"), dict) else None
        source = entry.get("source") if isinstance(entry, dict) else None
        if not isinstance(source, dict):
            return "NO_ENTRY"
        if ref is None:
            if "ref" not in source:
                return "ALREADY"
            if expect_ref is not None and source.get("ref") != expect_ref:
                return "CHANGED"
            del source["ref"]
        else:
            if source.get("ref") == ref:
                return "ALREADY"
            if expect_source is not None and source != expect_source:
                return "CHANGED"
            source["ref"] = ref
        return None
    return guarded_json_update(path, "UNPIN" if ref is None else "REPIN", ".scout-bak-unpin", change)


def run_workspace_env(path: Path, key: str) -> str:
    """Set one allowlisted env value in Scout's own workspace settings."""
    if key not in WORKSPACE_ENV_KEYS:
        return f"ENV_KEY_NOT_ALLOWED[{key}]"
    def change(data: dict[str, object]) -> str | None:
        environment = data.setdefault("env", {})
        if not isinstance(environment, dict):
            return "UNSAFE_ENV"
        if environment.get(key) == WORKSPACE_ENV_KEYS[key]:
            return "ALREADY"
        environment[key] = WORKSPACE_ENV_KEYS[key]
        return None
    return guarded_json_update(path, "ENV", ".scout-bak-env", change)


def die(message: str) -> NoReturn:
    print(message)
    raise SystemExit(2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("marketplace-autoupdate", "marketplace-unpin", "marketplace-repin",
                                            "workspace-env"))
    parser.add_argument("--settings", required=True)
    parser.add_argument("--name", default="salesforce", help="marketplace-autoupdate: the declared marketplace")
    parser.add_argument("--key", default="SF_DISABLE_PLUGIN_MATCH", help="workspace-env: an allowlisted env key")
    parser.add_argument("--ref", help="marketplace-repin: the ref to restore after a failed unpin")
    parser.add_argument("--expect-ref", help="marketplace-unpin: remove the ref only while it's still this one")
    parser.add_argument("--expect-source", help="marketplace-repin: restore only while the source is still this JSON")
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    try:
        path = explicit_path(arguments.settings)
    except SettingsError as error:
        die(f"SETTINGS_INVALID_ARGUMENT: {error}")
    if arguments.command == "marketplace-autoupdate":
        outcome = run_marketplace_autoupdate(path, arguments.name)
    elif arguments.command == "marketplace-unpin":
        outcome = run_marketplace_ref(path, arguments.name, None, expect_ref=arguments.expect_ref)
    elif arguments.command == "marketplace-repin":
        if not arguments.ref:
            die("SETTINGS_INVALID_ARGUMENT: marketplace-repin needs --ref")
        try:
            expected = json.loads(arguments.expect_source) if arguments.expect_source else None
        except ValueError:
            die("SETTINGS_INVALID_ARGUMENT: --expect-source must be JSON")
        outcome = run_marketplace_ref(path, arguments.name, arguments.ref, expect_source=expected)
    else:
        outcome = run_workspace_env(path, arguments.key)
    print(outcome)
    return 0


if __name__ == "__main__":
    scout_portable.utf8_output()
    sys.exit(main())
