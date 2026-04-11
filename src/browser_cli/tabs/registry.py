"""Agent-scoped tab ownership and conflict tracking."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from browser_cli.errors import BusyTabError, NoActiveTabError, TabNotFoundError


@dataclass(slots=True)
class BusyState:
    request_id: str
    command: str
    agent_id: str
    started_at: float


@dataclass(slots=True)
class TabRecord:
    page_id: str
    owner_agent_id: str
    created_at: float
    last_used_at: float
    url: str = ""
    title: str = ""
    busy: BusyState | None = None
    last_snapshot_refs: set[str] = field(default_factory=set)
    last_snapshot_id: str | None = None
    last_snapshot_ref_count: int = 0
    last_snapshot_url: str = ""
    last_snapshot_at: float | None = None


class TabRegistry:
    def __init__(self) -> None:
        self._tabs: dict[str, TabRecord] = {}
        self._active_tab_by_agent: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def add_tab(
        self,
        *,
        page_id: str,
        owner_agent_id: str,
        url: str = "",
        title: str = "",
    ) -> TabRecord:
        now = time.time()
        async with self._lock:
            record = TabRecord(
                page_id=page_id,
                owner_agent_id=owner_agent_id,
                created_at=now,
                last_used_at=now,
                url=url,
                title=title,
            )
            self._tabs[page_id] = record
            self._active_tab_by_agent[owner_agent_id] = page_id
            return record

    async def update_tab(
        self,
        page_id: str,
        *,
        url: str | None = None,
        title: str | None = None,
        last_snapshot_refs: set[str] | None = None,
        last_snapshot_id: str | None = None,
        last_snapshot_ref_count: int | None = None,
        last_snapshot_url: str | None = None,
        last_snapshot_at: float | None = None,
    ) -> TabRecord:
        async with self._lock:
            record = self._tabs.get(page_id)
            if record is None:
                raise TabNotFoundError()
            record.last_used_at = time.time()
            if url is not None:
                record.url = url
            if title is not None:
                record.title = title
            if last_snapshot_refs is not None:
                record.last_snapshot_refs = set(last_snapshot_refs)
            if last_snapshot_id is not None:
                record.last_snapshot_id = last_snapshot_id
            if last_snapshot_ref_count is not None:
                record.last_snapshot_ref_count = last_snapshot_ref_count
            if last_snapshot_url is not None:
                record.last_snapshot_url = last_snapshot_url
            if last_snapshot_at is not None:
                record.last_snapshot_at = last_snapshot_at
            return record

    async def list_tabs(self, agent_id: str) -> list[TabRecord]:
        async with self._lock:
            active_page_id = self._active_tab_by_agent.get(agent_id)
            visible = [
                self._copy_record(record)
                for record in self._tabs.values()
                if record.owner_agent_id == agent_id
            ]
            visible.sort(key=lambda item: item.created_at)
            if active_page_id:
                visible.sort(key=lambda item: item.page_id != active_page_id)
            return visible

    async def has_tabs(self, agent_id: str) -> bool:
        async with self._lock:
            return any(record.owner_agent_id == agent_id for record in self._tabs.values())

    async def get_active_tab(self, agent_id: str) -> TabRecord:
        async with self._lock:
            page_id = self._active_tab_by_agent.get(agent_id)
            if page_id is None:
                raise NoActiveTabError()
            record = self._tabs.get(page_id)
            if record is None or record.owner_agent_id != agent_id:
                raise NoActiveTabError()
            return self._copy_record(record)

    async def set_active_tab(self, agent_id: str, page_id: str) -> TabRecord:
        async with self._lock:
            record = self._tabs.get(page_id)
            if record is None or record.owner_agent_id != agent_id:
                raise TabNotFoundError()
            self._active_tab_by_agent[agent_id] = page_id
            record.last_used_at = time.time()
            return self._copy_record(record)

    async def get_tab(self, agent_id: str, page_id: str) -> TabRecord:
        async with self._lock:
            record = self._tabs.get(page_id)
            if record is None or record.owner_agent_id != agent_id:
                raise TabNotFoundError()
            return self._copy_record(record)

    async def remove_tab(self, agent_id: str, page_id: str) -> TabRecord:
        async with self._lock:
            record = self._tabs.get(page_id)
            if record is None or record.owner_agent_id != agent_id:
                raise TabNotFoundError()
            removed = self._tabs.pop(page_id)
            active_page_id = self._active_tab_by_agent.get(agent_id)
            if active_page_id == page_id:
                replacement = self._find_latest_page_id_locked(agent_id)
                if replacement is None:
                    self._active_tab_by_agent.pop(agent_id, None)
                else:
                    self._active_tab_by_agent[agent_id] = replacement
            return self._copy_record(removed)

    async def current_active_page_id(self, agent_id: str) -> str:
        return (await self.get_active_tab(agent_id)).page_id

    async def snapshot_state(self) -> tuple[list[TabRecord], dict[str, str]]:
        async with self._lock:
            records = [self._copy_record(record) for record in self._tabs.values()]
            records.sort(key=lambda item: item.created_at)
            return records, dict(self._active_tab_by_agent)

    async def replace_tab_ids(self, replacements: dict[str, str]) -> None:
        if not replacements:
            return
        async with self._lock:
            new_tabs: dict[str, TabRecord] = {}
            for old_page_id, record in list(self._tabs.items()):
                new_page_id = replacements.get(old_page_id, old_page_id)
                new_record = self._copy_record(record)
                new_record.page_id = new_page_id
                new_tabs[new_page_id] = new_record
            self._tabs = new_tabs
            for agent_id, page_id in list(self._active_tab_by_agent.items()):
                self._active_tab_by_agent[agent_id] = replacements.get(page_id, page_id)

    async def clear_snapshot_state(self) -> None:
        async with self._lock:
            for record in self._tabs.values():
                record.last_snapshot_refs = set()
                record.last_snapshot_id = None
                record.last_snapshot_ref_count = 0
                record.last_snapshot_url = ""
                record.last_snapshot_at = None

    async def is_visible(self, agent_id: str, page_id: str) -> bool:
        async with self._lock:
            record = self._tabs.get(page_id)
            return bool(record and record.owner_agent_id == agent_id)

    @asynccontextmanager
    async def claim_active_tab(
        self,
        *,
        agent_id: str,
        request_id: str,
        command: str,
    ) -> AsyncIterator[TabRecord]:
        page_id: str
        async with self._lock:
            page_id = self._active_tab_by_agent.get(agent_id, "")
            if not page_id:
                raise NoActiveTabError()
            record = self._tabs.get(page_id)
            if record is None or record.owner_agent_id != agent_id:
                raise NoActiveTabError()
            if record.busy and record.busy.request_id != request_id:
                raise BusyTabError()
            record.busy = BusyState(
                request_id=request_id,
                command=command,
                agent_id=agent_id,
                started_at=time.time(),
            )
            record.last_used_at = time.time()
            claimed = self._copy_record(record)
        try:
            yield claimed
        finally:
            await self.release_tab(page_id=page_id, request_id=request_id)

    async def claim_page(
        self,
        *,
        agent_id: str,
        page_id: str,
        request_id: str,
        command: str,
    ) -> TabRecord:
        async with self._lock:
            record = self._tabs.get(page_id)
            if record is None or record.owner_agent_id != agent_id:
                raise TabNotFoundError()
            if record.busy and record.busy.request_id != request_id:
                raise BusyTabError()
            record.busy = BusyState(
                request_id=request_id,
                command=command,
                agent_id=agent_id,
                started_at=time.time(),
            )
            record.last_used_at = time.time()
            return self._copy_record(record)

    async def release_tab(self, *, page_id: str, request_id: str) -> None:
        async with self._lock:
            record = self._tabs.get(page_id)
            if record is None:
                return
            if record.busy and record.busy.request_id == request_id:
                record.busy = None

    def _find_latest_page_id_locked(self, agent_id: str) -> str | None:
        candidates = [record for record in self._tabs.values() if record.owner_agent_id == agent_id]
        if not candidates:
            return None
        candidates.sort(key=lambda item: item.last_used_at, reverse=True)
        return candidates[0].page_id

    @staticmethod
    def _copy_record(record: TabRecord) -> TabRecord:
        return TabRecord(
            page_id=record.page_id,
            owner_agent_id=record.owner_agent_id,
            created_at=record.created_at,
            last_used_at=record.last_used_at,
            url=record.url,
            title=record.title,
            busy=record.busy,
            last_snapshot_refs=set(record.last_snapshot_refs),
            last_snapshot_id=record.last_snapshot_id,
            last_snapshot_ref_count=record.last_snapshot_ref_count,
            last_snapshot_url=record.last_snapshot_url,
            last_snapshot_at=record.last_snapshot_at,
        )
