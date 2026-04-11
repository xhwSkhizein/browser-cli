"""Tab-scoped semantic snapshot registry."""

from __future__ import annotations

from dataclasses import dataclass

from browser_cli.refs.models import RefData, SemanticSnapshot


@dataclass(slots=True)
class PageSnapshotState:
    snapshot_id: str
    tree: str
    refs: dict[str, RefData]
    captured_url: str
    captured_at: float

    @classmethod
    def from_snapshot(cls, snapshot: SemanticSnapshot) -> PageSnapshotState:
        return cls(
            snapshot_id=snapshot.metadata.snapshot_id,
            tree=snapshot.tree,
            refs=dict(snapshot.refs),
            captured_url=snapshot.metadata.captured_url,
            captured_at=snapshot.metadata.captured_at,
        )


class SnapshotRegistry:
    def __init__(self) -> None:
        self._latest_by_page: dict[str, PageSnapshotState] = {}

    def store(self, snapshot: SemanticSnapshot) -> PageSnapshotState:
        state = PageSnapshotState.from_snapshot(snapshot)
        self._latest_by_page[snapshot.metadata.page_id] = state
        return state

    def get(self, page_id: str) -> PageSnapshotState | None:
        return self._latest_by_page.get(page_id)

    def get_ref(self, page_id: str, ref: str) -> RefData | None:
        state = self.get(page_id)
        if state is None:
            return None
        return state.refs.get(ref)

    def clear_page(self, page_id: str) -> None:
        self._latest_by_page.pop(page_id, None)

    def clear(self) -> None:
        self._latest_by_page.clear()
