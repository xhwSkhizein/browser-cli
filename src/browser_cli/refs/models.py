"""Semantic ref dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class SnapshotMetadata:
    snapshot_id: str
    page_id: str
    captured_url: str
    captured_at: float
    interactive: bool
    full_page: bool


@dataclass(slots=True, frozen=True)
class RefData:
    ref: str
    role: str
    name: str | None = None
    nth: int | None = None
    text_content: str | None = None
    tag: str | None = None
    interactive: bool = False
    parent_ref: str | None = None
    frame_path: tuple[int, ...] = ()
    playwright_ref: str | None = None
    selector_recipe: str | None = None
    snapshot_id: str = ""
    page_id: str = ""
    captured_url: str = ""
    captured_at: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_summary(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "role": self.role,
            "name": self.name,
            "nth": self.nth,
            "text_content": self.text_content,
            "tag": self.tag,
            "interactive": self.interactive,
            "parent_ref": self.parent_ref,
            "frame_path": list(self.frame_path),
            "playwright_ref": self.playwright_ref,
            "selector_recipe": self.selector_recipe,
            "snapshot_id": self.snapshot_id,
            "page_id": self.page_id,
            "captured_url": self.captured_url,
            "captured_at": self.captured_at,
            **self.extra,
        }


@dataclass(slots=True, frozen=True)
class SemanticSnapshot:
    tree: str
    refs: dict[str, RefData]
    metadata: SnapshotMetadata
