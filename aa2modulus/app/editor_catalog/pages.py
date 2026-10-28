"""Markdown pages for built-ins, one per ``editor-data catalog`` entry."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_MARKDOWN = re.compile(r"[\\`*_\[\]<>|]")
_LINE_MARKER = re.compile(r"^(\s*)([#+-])", re.MULTILINE)
_PAGE_PATH = re.compile(r"/?([^/]+)\.md")


def escape_markdown(value: str) -> str:
    """Escape Markdown syntax in prose taken from game descriptions."""

    return _LINE_MARKER.sub(r"\1\\\2", _MARKDOWN.sub(r"\\\g<0>", value))


def page(entry: Mapping[str, Any], *, website: str | None) -> str:
    title = f"# {escape_markdown(entry['name'])}"
    return "\n\n".join([title, *sections(entry, website=website)]) + "\n"


def sections(entry: Mapping[str, Any], *, website: str | None) -> list[str]:
    """The page's Markdown blocks after its title, so the website can add its own heading."""

    signatures = entry["signatures"]
    parts = [_fence("\n".join(item["label"] for item in signatures) or entry["name"])]
    if description := entry["description"].strip():
        parts.append(escape_markdown(description))

    sections = [(item, lines) for item in signatures if (lines := _parameter_lines(item))]
    if len(sections) == 1:
        parts.append("**Parameters**\n\n" + "\n".join(sections[0][1]).strip())
    elif sections:
        lines = []
        for signature, section in sections:
            lines += [_code(signature["label"]), "", *section, ""]
        parts.append("**Parameters**\n\n" + "\n".join(lines).strip())

    returns: list[str] = []
    for signature in signatures:
        if signature["returns"] is not None:
            line = _type_and_role(signature["returns"])
            if line not in returns:
                returns.append(line)
    if returns:
        parts.append("**Returns**\n\n" + "\n\n".join(returns))

    if entry["valueEvents"] is not None:
        events = ", ".join(_code(event) for event in entry["valueEvents"])
        parts.append(f"Has a value only in: {events}")
    if entry["example"]:
        parts.append("**Example**\n\n" + _fence(entry["example"]))
    parts.append(
        f"Native name: {escape_markdown(entry['nativeName'])} "
        f"({escape_markdown(entry['category'])}). ID: {_code(entry['id'])}"
    )
    if website:
        parts.append(f"[Full documentation]({website.rstrip('/')}/{entry['docPath']})")
    return parts


def page_text(entries: Mapping[str, Mapping[str, Any]], path: str, *, website: str | None) -> str:
    """The page at ``/<id>.md``, or an "Unknown built-in" page when no entry has that id."""

    match = _PAGE_PATH.fullmatch(path)
    entry = entries.get(match.group(1)) if match else None
    if entry is None:
        return f"# Unknown built-in\n\nNo built-in documentation entry matches {_code(path)}.\n"
    return page(entry, website=website)


def _code(value: str) -> str:
    return f"`` {value} ``" if "`" in value else f"`{value}`"


def _type_and_role(item: Mapping[str, Any]) -> str:
    role = item["role"]
    return f"{_code(item['type'])} ({escape_markdown(role)})" if role else _code(item["type"])


def _fence(body: str) -> str:
    return f"```aa2m\n{body}\n```"


def _parameter_lines(signature: Mapping[str, Any]) -> list[str]:
    lines = []
    if signature["receiver"] is not None:
        lines.append(f"- Receiver: {_type_and_role(signature['receiver'])}")
    for parameter in signature["parameters"]:
        default = parameter["default"]
        fallback = "" if default is None else f", default {_code(default)}"
        lines.append(f"- {_code(parameter['name'])}: {_type_and_role(parameter)}{fallback}")
    return lines
