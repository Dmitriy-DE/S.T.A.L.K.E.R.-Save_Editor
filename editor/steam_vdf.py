"""Small, dependency-free reader for Steam KeyValues/VDF files."""

from __future__ import annotations

from pathlib import Path
from typing import TypeAlias

VdfValue: TypeAlias = str | dict[str, "VdfValue"]


def read_text(path: Path) -> str | None:
    """Read Steam text files using their common UTF-8/Windows fallback."""

    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="cp1251")
        except (OSError, UnicodeDecodeError):
            return None
    except OSError:
        return None


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character.isspace():
            index += 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index + 2)
            index = length if newline < 0 else newline + 1
            continue
        if character in "{}":
            tokens.append(character)
            index += 1
            continue
        if character == '"':
            index += 1
            value: list[str] = []
            while index < length:
                character = text[index]
                if character == '"':
                    index += 1
                    break
                if character == "\\" and index + 1 < length:
                    escaped = text[index + 1]
                    if escaped in ("\\", '"'):
                        value.append(escaped)
                        index += 2
                    else:
                        # Windows VDF paths commonly contain single
                        # backslashes; doubled backslashes and escaped quotes
                        # retain the normal KeyValues escape behavior.
                        value.append("\\")
                        index += 1
                    continue
                value.append(character)
                index += 1
            else:
                raise ValueError("unterminated quoted VDF string")
            tokens.append("".join(value))
            continue

        start = index
        while index < length and not text[index].isspace() and text[index] not in "{}":
            index += 1
        if start == index:
            raise ValueError("empty VDF token")
        tokens.append(text[start:index])
    return tokens


def parse_vdf(text: str) -> dict[str, VdfValue]:
    """Parse one Steam KeyValues document into nested string dictionaries."""

    tokens = _tokenize(text)
    position = 0

    def parse_object(*, closing: bool) -> dict[str, VdfValue]:
        nonlocal position
        result: dict[str, VdfValue] = {}
        while position < len(tokens):
            if tokens[position] == "}":
                if not closing:
                    raise ValueError("unexpected closing VDF brace")
                position += 1
                return result
            key = tokens[position]
            if key == "{":
                raise ValueError("VDF object is missing a key")
            position += 1
            if position >= len(tokens):
                raise ValueError("VDF key is missing a value")
            value = tokens[position]
            position += 1
            if value == "{":
                result[key] = parse_object(closing=True)
            elif value == "}":
                raise ValueError("VDF key is missing a value")
            else:
                result[key] = value
        if closing:
            raise ValueError("unterminated VDF object")
        return result

    result = parse_object(closing=False)
    if position != len(tokens):
        raise ValueError("trailing VDF tokens")
    return result


def library_paths(value: VdfValue | None) -> tuple[str, ...]:
    """Extract Steam library paths from old and current VDF shapes."""

    if not isinstance(value, dict):
        return ()
    paths: list[str] = []
    for entry in value.values():
        if isinstance(entry, str):
            paths.append(entry)
        elif isinstance(entry, dict):
            path = entry.get("path")
            if isinstance(path, str) and path.strip():
                paths.append(path)
    return tuple(paths)


__all__ = ["VdfValue", "library_paths", "parse_vdf", "read_text"]
