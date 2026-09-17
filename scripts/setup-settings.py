#!/usr/bin/env python3
"""Safely perform Scout's narrowly scoped settings cleanup operations."""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import sys
import tempfile
from typing import Callable, NoReturn


MODEL_KEYS = (
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
)
JSON_PIN_KEYS = MODEL_KEYS + (
    "MAX_THINKING_TOKENS",
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
)
INTERPRETERS = {"bash", "sh", "zsh", "python", "python3", "node"}
SHELL_PUNCTUATION = set(";&|<>")


class SettingsError(Exception):
    pass


class DuplicateKey(SettingsError):
    pass


class BackupFailure(SettingsError):
    pass


class WriteFailure(SettingsError):
    pass


class PostWriteFailure(WriteFailure):
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


def validate_backup_path(path: Path, original: bytes, mode: int) -> bool:
    if has_symlink_component(path):
        raise BackupFailure("backup path or ancestor is a symlink")
    if not path.exists():
        return False
    try:
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode):
            raise BackupFailure("backup path is not a regular file")
        if path.read_bytes() != original or stat.S_IMODE(metadata.st_mode) != mode:
            raise BackupFailure("existing backup does not exactly match the source")
    except OSError as error:
        raise BackupFailure(str(error)) from error
    return True


def guarded_replace(
    path: Path,
    original: bytes,
    replacement: bytes,
    mode: int,
    backup_suffix: str,
    validate: Callable[[bytes], None],
) -> None:
    backup = Path(str(path) + backup_suffix)
    try:
        backup_exists = validate_backup_path(backup, original, mode)
        if not backup_exists:
            shutil.copy2(path, backup)
        backup_bytes, backup_mode = read_regular(backup)
        if backup_bytes != original or backup_mode != mode:
            raise BackupFailure("backup verification failed")
    except BackupFailure:
        raise
    except (OSError, SettingsError) as error:
        raise BackupFailure(str(error)) from error

    temporary: Path | None = None
    replaced = False
    try:
        descriptor, name = tempfile.mkstemp(
            dir=path.parent, prefix=".settings.", suffix=".tmp"
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(replacement)
            stream.flush()
            os.fsync(stream.fileno())
        staged = temporary.read_bytes()
        if staged != replacement:
            raise WriteFailure("staged bytes differ from the proposed content")
        validate(staged)
        os.replace(temporary, path)
        temporary = None
        replaced = True
        written, written_mode = read_regular(path)
        if written != replacement or written_mode != mode:
            raise PostWriteFailure("post-replace verification failed")
    except PostWriteFailure:
        raise
    except WriteFailure:
        raise
    except (OSError, SettingsError) as error:
        failure = PostWriteFailure if replaced else WriteFailure
        raise failure(str(error)) from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


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


def delete_spans(source: str, spans: list[tuple[int, int]]) -> str:
    unique = sorted(set(spans), reverse=True)
    output = source
    for start, end in unique:
        output = output[:start] + output[end:]
    return output


def vscode_replacement(content: bytes) -> bytes | None:
    source, root = parse_jsonc(content)
    member = next(
        (item for item in root.members if item.key == "claudeCode.environmentVariables"),
        None,
    )
    if member is None:
        return None
    array = member.value
    if array.kind != "array":
        raise SettingsError("VSCODE_UNSUPPORTED_TARGET: environmentVariables is not an array")
    selected: list[int] = []
    for index, element in enumerate(array.elements):
        value = element.node.value
        if isinstance(value, dict) and value.get("name") in MODEL_KEYS:
            if set(value) != {"name", "value"} or not isinstance(value.get("value"), str):
                raise SettingsError("VSCODE_UNSUPPORTED_TARGET: unexpected target entry shape")
            selected.append(index)
    if not selected:
        return None
    spans: list[tuple[int, int]] = []
    for index in selected:
        element = array.elements[index]
        spans.append((element.node.start, element.node.end))
        if element.comma_after is not None:
            spans.append((element.comma_after.start, element.comma_after.end))
        elif index > 0 and array.elements[index - 1].comma_after is not None:
            comma = array.elements[index - 1].comma_after
            spans.append((comma.start, comma.end))
    output = delete_spans(source, spans)
    _, after = parse_jsonc(output.encode("utf-8"))
    expected = copy.deepcopy(root.value)
    expected["claudeCode.environmentVariables"] = [
        value for index, value in enumerate(array.value) if index not in selected
    ]
    if after.value != expected:
        raise SettingsError("VSCODE_SEMANTIC_MISMATCH: proposed edit changed unexpected values")
    return output.encode("utf-8")


def run_vscode(path: Path) -> str:
    try:
        original, mode = read_regular(path)
    except FileNotFoundError:
        return "VSCODE_ABSENT"
    except SettingsError as error:
        return f"VSCODE_UNSAFE_FILE: {error}"
    try:
        replacement = vscode_replacement(original)
    except JsoncError as error:
        return f"VSCODE_UNPARSEABLE: {error}"
    except SettingsError as error:
        return str(error)
    if replacement is None:
        return "VSCODE_PINS_NONE"
    try:
        guarded_replace(
            path,
            original,
            replacement,
            mode,
            ".scout-bak",
            lambda content: parse_jsonc(content),
        )
    except BackupFailure as error:
        return f"VSCODE_BACKUP_FAILED: {error}"
    except PostWriteFailure as error:
        return f"VSCODE_POST_WRITE_FAILED: {error}"
    except WriteFailure as error:
        return f"VSCODE_WRITE_FAILED: {error}"
    return "VSCODE_PINS_REMOVED"


def json_bytes(value: dict[str, object]) -> bytes:
    return (json.dumps(value, indent=2) + "\n").encode("utf-8")


def run_json_pins(path: Path) -> str:
    label = path.name
    try:
        original, mode = read_regular(path)
    except FileNotFoundError:
        return f"PINS_ABSENT[{label}]"
    except SettingsError as error:
        return f"PINS_UNSAFE_FILE[{label}]: {error}"
    try:
        data = load_strict_json(original)
    except SettingsError as error:
        return f"PINS_PARSE_ERROR[{label}]: {error}"
    removed: list[str] = []
    environment = data.get("env")
    if isinstance(environment, dict):
        for key in JSON_PIN_KEYS:
            if key in environment:
                del environment[key]
                removed.append(key)
    flags = ["modelOverrides"] if "modelOverrides" in data else []
    tail = f" FLAGS[{','.join(flags)}]" if flags else ""
    if not removed:
        return f"PINS_NONE[{label}]{tail}"
    replacement = json_bytes(data)
    try:
        guarded_replace(
            path,
            original,
            replacement,
            mode,
            ".scout-bak-modelpins",
            lambda content: load_strict_json(content),
        )
    except BackupFailure as error:
        return f"PINS_BACKUP_FAILED[{label}]: {error}"
    except PostWriteFailure as error:
        return f"PINS_POST_WRITE_FAILED[{label}]: {error}"
    except WriteFailure as error:
        return f"PINS_WRITE_FAILED[{label}]: {error}"
    return f"PINS_REMOVED[{label}]: {','.join(removed)}{tail}"


def aisuite_path(token: str) -> Path | None:
    if any(character in token for character in "*?[]"):
        return None
    try:
        expanded = Path(token).expanduser()
    except (OSError, RuntimeError):
        return None
    if not expanded.is_absolute() or ".aisuite" not in expanded.parts:
        return None
    return expanded


def command_target(command: str) -> tuple[str, Path | None]:
    if "$" in command or "`" in command or any(
        character in command for character in ("\n", "\r", "\x00")
    ):
        return "unsupported", None
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return "unsupported", None
    if not tokens:
        return "irrelevant", None
    if any(token and all(character in SHELL_PUNCTUATION for character in token) for token in tokens):
        return "unsupported", None
    candidates = [
        (index, candidate)
        for index, token in enumerate(tokens)
        if (candidate := aisuite_path(token)) is not None
    ]
    if len(candidates) > 1:
        return "unsupported", None
    if candidates and candidates[0][0] == 0:
        return "target", candidates[0][1]
    executable = Path(tokens[0]).name
    if (
        executable in INTERPRETERS
        and len(tokens) >= 2
        and not tokens[1].startswith("-")
        and candidates
        and candidates[0][0] == 1
    ):
        return "target", candidates[0][1]
    if ".aisuite" in command:
        return "unsupported", None
    return "irrelevant", None


def target_state(path: Path) -> str:
    try:
        metadata = path.stat()
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "uncertain"
    return "live" if stat.S_ISREG(metadata.st_mode) else "uncertain"


def aisuite_flags(data: dict[str, object]) -> list[str]:
    flags: list[str] = []
    environment = data.get("env")
    if isinstance(environment, dict):
        certificate = environment.get("NODE_EXTRA_CA_CERTS")
        if isinstance(certificate, str) and "/.aisuite/" in certificate:
            flags.append("cert:NODE_EXTRA_CA_CERTS")
    marketplaces = data.get("extraKnownMarketplaces")
    if isinstance(marketplaces, dict) and any(
        "aisuite" in str(key).lower() for key in marketplaces
    ):
        flags.append("marketplace:aisuite")
    plugins = data.get("enabledPlugins")
    if isinstance(plugins, dict) and any(
        str(key).lower().endswith("@aisuite") for key in plugins
    ):
        flags.append("plugins:@aisuite")
    return flags


def run_aisuite(path: Path) -> str:
    label = path.name
    try:
        original, mode = read_regular(path)
    except FileNotFoundError:
        return f"AISUITE_ABSENT[{label}]"
    except SettingsError as error:
        return f"AISUITE_UNSAFE_FILE[{label}]: {error}"
    try:
        data = load_strict_json(original)
    except SettingsError as error:
        return f"AISUITE_PARSE_ERROR[{label}]: {error}"
    removed: list[str] = []
    unsupported = 0
    hooks = data.get("hooks")
    if isinstance(hooks, dict):
        for event, groups in hooks.items():
            if not isinstance(groups, list):
                continue
            for group in groups:
                if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                    continue
                kept: list[object] = []
                for hook in group["hooks"]:
                    command = hook.get("command") if isinstance(hook, dict) else None
                    if not isinstance(command, str):
                        kept.append(hook)
                        continue
                    if hook.get("type") != "command":
                        if ".aisuite" in command:
                            unsupported += 1
                        kept.append(hook)
                        continue
                    command_kind, target = command_target(command)
                    if command_kind == "unsupported":
                        unsupported += 1
                        kept.append(hook)
                    elif command_kind == "target" and target is not None:
                        state = target_state(target)
                        if state == "missing":
                            removed.append(f"{event}:{target.name}")
                        else:
                            if state == "uncertain":
                                unsupported += 1
                            kept.append(hook)
                    else:
                        kept.append(hook)
                group["hooks"] = kept
    flags = aisuite_flags(data)
    flag_tail = f" FLAGS[{','.join(flags)}]" if flags else ""
    unsupported_tail = f" UNSUPPORTED[{unsupported}]" if unsupported else ""
    if not removed:
        return f"AISUITE_HOOKS_NONE[{label}]{flag_tail}{unsupported_tail}"
    replacement = json_bytes(data)
    try:
        guarded_replace(
            path,
            original,
            replacement,
            mode,
            ".scout-bak-aisuite",
            lambda content: load_strict_json(content),
        )
    except BackupFailure as error:
        return f"AISUITE_BACKUP_FAILED[{label}]: {error}"
    except PostWriteFailure as error:
        return f"AISUITE_POST_WRITE_FAILED[{label}]: {error}"
    except WriteFailure as error:
        return f"AISUITE_WRITE_FAILED[{label}]: {error}"
    return (
        f"AISUITE_HOOKS_REMOVED[{label}]: {','.join(removed)}"
        f"{flag_tail}{unsupported_tail}"
    )


def die(message: str) -> NoReturn:
    print(message)
    raise SystemExit(2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("json-pins", "vscode-pins", "aisuite-hooks"))
    parser.add_argument("--settings", required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    try:
        path = explicit_path(arguments.settings)
    except SettingsError as error:
        die(f"SETTINGS_INVALID_ARGUMENT: {error}")
    if arguments.command == "json-pins":
        outcome = run_json_pins(path)
    elif arguments.command == "vscode-pins":
        outcome = run_vscode(path)
    else:
        outcome = run_aisuite(path)
    print(outcome)
    return 0


if __name__ == "__main__":
    sys.exit(main())
