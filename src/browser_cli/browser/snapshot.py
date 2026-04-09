"""Compatibility wrapper around semantic snapshot generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from browser_cli.refs import SemanticSnapshotGenerator


@dataclass(slots=True)
class SnapshotCapture:
    tree: str
    refs: dict[str, dict[str, Any]]
    snapshot_id: str


async def capture_snapshot(
    page: Any,
    *,
    page_id: str,
    interactive: bool = False,
    full_page: bool = True,
) -> SnapshotCapture:
    snapshot = await SemanticSnapshotGenerator().get_snapshot(
        page,
        page_id=page_id,
        interactive=interactive,
        full_page=full_page,
    )
    return SnapshotCapture(
        tree=snapshot.tree,
        refs={ref: data.to_summary() for ref, data in snapshot.refs.items()},
        snapshot_id=snapshot.metadata.snapshot_id,
    )
