"""Shared driver-side dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class TabState:
    page_id: str
    url: str
    title: str = ""
    active: bool = False


@dataclass(slots=True, frozen=True)
class DriverHealth:
    name: str
    available: bool
    details: dict[str, Any] = field(default_factory=dict)
