"""Semantic ref dataclasses."""

from __future__ import annotations

import time
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


@dataclass(slots=True, frozen=True)
class SnapshotInput:
    raw_snapshot: str
    captured_url: str
    captured_at: float = field(default_factory=time.time)


@dataclass(slots=True, frozen=True)
class LocatorSpec:
    ref: str
    role: str
    name: str | None = None
    text_content: str | None = None
    match_text: str | None = None
    child_text: str | None = None
    nth: int | None = None
    tag: str | None = None
    interactive: bool = False
    frame_path: tuple[int, ...] = ()
    selector_recipe: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "role": self.role,
            "name": self.name,
            "text_content": self.text_content,
            "match_text": self.match_text,
            "child_text": self.child_text,
            "nth": self.nth,
            "tag": self.tag,
            "interactive": self.interactive,
            "frame_path": list(self.frame_path),
            "selector_recipe": self.selector_recipe,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> LocatorSpec:
        return cls(
            ref=str(payload.get("ref") or "").strip(),
            role=str(payload.get("role") or "").strip(),
            name=(str(payload["name"]) if payload.get("name") is not None else None),
            text_content=(
                str(payload["text_content"]) if payload.get("text_content") is not None else None
            ),
            match_text=(
                str(payload["match_text"]) if payload.get("match_text") is not None else None
            ),
            child_text=(
                str(payload["child_text"]) if payload.get("child_text") is not None else None
            ),
            nth=(int(payload["nth"]) if payload.get("nth") is not None else None),
            tag=(str(payload["tag"]) if payload.get("tag") is not None else None),
            interactive=bool(payload.get("interactive")),
            frame_path=tuple(int(item) for item in (payload.get("frame_path") or [])),
            selector_recipe=(
                str(payload["selector_recipe"])
                if payload.get("selector_recipe") is not None
                else None
            ),
        )
