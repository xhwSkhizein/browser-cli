"""Minimal TOML rendering helpers for automation manifests."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any


def dumps_toml_sections(sections: Iterable[tuple[str, dict[str, Any]]]) -> str:
    lines: list[str] = []
    first_section = True
    for section_name, values in sections:
        if not first_section:
            lines.append("")
        first_section = False
        lines.append(f"[{section_name}]")
        for key, value in values.items():
            if value is None:
                continue
            lines.append(f"{key} = {_toml_value(value)}")
    lines.append("")
    return "\n".join(lines)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list | tuple):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise TypeError(f"Unsupported TOML value type: {type(value)!r}")
