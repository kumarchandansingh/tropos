"""Safely extract data-bearing JavaScript literals from HTML without execution."""

from __future__ import annotations

import ast
import re
from html.parser import HTMLParser
from typing import cast

_ASSIGNMENT = re.compile(r"\\b(?:const|let|var)\\s+([A-Za-z_$][\\w$]*)\\s*=")
_IDENTIFIER_START = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_$"
)
_IDENTIFIER_CONTINUE = _IDENTIFIER_START | frozenset("0123456789")
_MAX_SCRIPT_CHARACTERS = 2_000_000
_MAX_LITERAL_CHARACTERS = 1_000_000
_MIN_TEXT_CHARACTERS = 200
_MIN_TEXT_VALUES = 3


class _InlineScriptCollector(HTMLParser):
    """Collect inline script bodies while ignoring externally loaded scripts."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.scripts: list[str] = []
        self._active = False
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        attributes = {key.lower(): value for key, value in attrs}
        self._active = "src" not in attributes
        self._buffer.clear()

    def handle_data(self, data: str) -> None:
        if self._active:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "script" or not self._active:
            return
        script = "".join(self._buffer)
        if script and len(script) <= _MAX_SCRIPT_CHARACTERS:
            self.scripts.append(script)
        self._buffer.clear()
        self._active = False


def _balanced_literal(script: str, start: int) -> str | None:
    if start >= len(script) or script[start] not in "[{":
        return None

    stack: list[str] = []
    quote: str | None = None
    escaped = False

    for index in range(start, min(len(script), start + _MAX_LITERAL_CHARACTERS)):
        character = script[index]

        if quote is not None:
            if escaped:
                escaped = False
                continue
            if character == "\\\\":
                escaped = True
                continue
            if character == quote:
                quote = None
            continue

        if character in {"'", '"'}:
            quote = character
            continue
        if character == chr(96):
            return None
        if character in "[{":
            stack.append(character)
            continue
        if character in "]}":
            if not stack:
                return None
            opener = stack.pop()
            expected = "]" if opener == "[" else "}"
            if character != expected:
                return None
            if not stack:
                return script[start : index + 1]

    return None


def _pythonize_js_literal(literal: str) -> str:
    """Convert a deliberately small JavaScript literal subset to Python literal syntax."""

    output: list[str] = []
    index = 0
    quote: str | None = None
    escaped = False

    while index < len(literal):
        character = literal[index]

        if quote is not None:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue

        if character in {"'", '"'}:
            quote = character
            output.append(character)
            index += 1
            continue

        if character in _IDENTIFIER_START:
            end = index + 1
            while end < len(literal) and literal[end] in _IDENTIFIER_CONTINUE:
                end += 1
            token = literal[index:end]

            lookahead = end
            while lookahead < len(literal) and literal[lookahead].isspace():
                lookahead += 1

            if lookahead < len(literal) and literal[lookahead] == ":":
                output.append(repr(token))
            elif token == "true":
                output.append("True")
            elif token == "false":
                output.append("False")
            elif token == "null":
                output.append("None")
            else:
                output.append(token)
            index = end
            continue

        output.append(character)
        index += 1

    return "".join(output)


def _valid_data(value: object) -> bool:
    if value is None or isinstance(value, str | int | float | bool):
        return True
    if isinstance(value, list):
        return all(_valid_data(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _valid_data(item)
            for key, item in value.items()
        )
    return False


def _text_values(value: object) -> list[str]:
    if isinstance(value, str):
        text = " ".join(value.split())
        return [text] if text else []
    if isinstance(value, list):
        return [text for item in value for text in _text_values(item)]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _text_values(item)]
    return []


def _meaningful_data(value: object) -> bool:
    values = _text_values(value)
    return (
        len(values) >= _MIN_TEXT_VALUES
        and sum(len(text) for text in values) >= _MIN_TEXT_CHARACTERS
    )


def _mostly_visible_duplicate(value: object, visible_text: str) -> bool:
    candidates = [text for text in _text_values(value) if len(text) >= 20]
    if not candidates:
        return False
    visible = " ".join(visible_text.split())
    total = sum(len(text) for text in candidates)
    duplicated = sum(len(text) for text in candidates if text in visible)
    return duplicated / total >= 0.8


def _preferred_label(item: dict[str, object], fallback: str) -> str:
    for key in ("title", "name", "label", "l"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    return fallback


def _scalar_text(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _render_mapping(mapping: dict[str, object], *, heading_level: int) -> list[str]:
    lines: list[str] = []
    for key, value in mapping.items():
        if key in {"title", "name", "label"} and isinstance(value, str):
            continue
        if value is None or isinstance(value, str | int | float | bool):
            lines.append(f"- **{key}:** {_scalar_text(value)}")
            continue

        lines.append(f"{'#' * min(heading_level, 6)} {key}")
        if isinstance(value, list):
            lines.extend(_render_list(value, heading_level=heading_level + 1))
        elif isinstance(value, dict):
            nested = cast(dict[str, object], value)
            lines.extend(_render_mapping(nested, heading_level=heading_level + 1))
    return lines


def _render_list(values: list[object], *, heading_level: int) -> list[str]:
    lines: list[str] = []
    for position, value in enumerate(values, start=1):
        if isinstance(value, dict):
            item = cast(dict[str, object], value)
            label = _preferred_label(item, f"Item {position}")
            lines.append(f"{'#' * min(heading_level, 6)} {label}")
            lines.extend(_render_mapping(item, heading_level=heading_level + 1))
        elif isinstance(value, list):
            lines.extend(_render_list(value, heading_level=heading_level))
        else:
            lines.append(f"- {_scalar_text(value)}")
    return lines


def _render_assignment(name: str, value: object) -> str:
    lines = [f"## Embedded data: {name}"]
    if isinstance(value, list):
        lines.extend(_render_list(value, heading_level=3))
    elif isinstance(value, dict):
        lines.extend(
            _render_mapping(
                cast(dict[str, object], value),
                heading_level=3,
            )
        )
    return "\\n\\n".join(lines)


def extract_embedded_data_markdown(html: str, *, visible_text: str) -> tuple[str, ...]:
    """Return deterministic Markdown for safe, data-bearing inline assignments."""

    collector = _InlineScriptCollector()
    collector.feed(html)
    collector.close()

    rendered: list[str] = []
    for script in collector.scripts:
        for match in _ASSIGNMENT.finditer(script):
            position = match.end()
            while position < len(script) and script[position].isspace():
                position += 1
            literal = _balanced_literal(script, position)
            if literal is None:
                continue

            try:
                parsed = ast.literal_eval(_pythonize_js_literal(literal))
            except (SyntaxError, ValueError):
                continue

            value = cast(object, parsed)
            if not _valid_data(value):
                continue
            if not _meaningful_data(value):
                continue
            if _mostly_visible_duplicate(value, visible_text):
                continue

            rendered.append(_render_assignment(match.group(1), value))

    return tuple(rendered)
