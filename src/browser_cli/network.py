"""Shared network record models, filtering, and buffering."""

from __future__ import annotations

import asyncio
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any


STATIC_RESOURCE_TYPES = frozenset({"image", "stylesheet", "script", "font", "media"})
DEFAULT_NETWORK_RECENT_LIMIT = 200
DEFAULT_NETWORK_CAPTURE_LIMIT = 200


@dataclass(slots=True, frozen=True)
class NetworkRecordFilter:
    url_contains: str | None = None
    url_regex: str | None = None
    method: str | None = None
    status: int | None = None
    resource_type: str | None = None
    mime_contains: str | None = None
    include_static: bool = False
    _compiled_url_regex: re.Pattern[str] | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        compiled = re.compile(self.url_regex) if self.url_regex else None
        object.__setattr__(self, "_compiled_url_regex", compiled)

    def matches(self, record: dict[str, Any]) -> bool:
        resource_type = str(record.get("resource_type") or "")
        if not self.include_static and is_static_resource_type(resource_type):
            return False
        url = str(record.get("url") or "")
        if self.url_contains and self.url_contains not in url:
            return False
        if self._compiled_url_regex and self._compiled_url_regex.search(url) is None:
            return False
        if self.method and str(record.get("method") or "").upper() != self.method.upper():
            return False
        if self.status is not None and int(record.get("status") or 0) != self.status:
            return False
        if self.resource_type and resource_type != self.resource_type:
            return False
        if self.mime_contains and self.mime_contains.lower() not in str(record.get("mime_type") or "").lower():
            return False
        return True


def is_static_resource_type(resource_type: str | None) -> bool:
    return str(resource_type or "").lower() in STATIC_RESOURCE_TYPES


@dataclass(slots=True)
class _NetworkWaiter:
    record_filter: NetworkRecordFilter
    future: asyncio.Future[dict[str, Any]]


class NetworkRecordStore:
    """Keep a bounded recent buffer plus an explicit capture-session buffer."""

    def __init__(
        self,
        *,
        recent_limit: int = DEFAULT_NETWORK_RECENT_LIMIT,
        capture_limit: int = DEFAULT_NETWORK_CAPTURE_LIMIT,
    ) -> None:
        self._recent_records: deque[dict[str, Any]] = deque(maxlen=recent_limit)
        self._captured_records: deque[dict[str, Any]] = deque(maxlen=capture_limit)
        self._waiters: list[_NetworkWaiter] = []
        self._capturing = False

    @property
    def capturing(self) -> bool:
        return self._capturing

    def start_capture(self) -> None:
        self._captured_records.clear()
        self._capturing = True

    def stop_capture(self) -> None:
        self._capturing = False

    def clear(self) -> None:
        self._recent_records.clear()
        self._captured_records.clear()
        for waiter in self._waiters:
            if waiter.future.done():
                continue
            waiter.future.cancel()
        self._waiters.clear()

    def add_record(self, record: dict[str, Any]) -> None:
        self._recent_records.append(record)
        if self._capturing:
            self._captured_records.append(record)
        remaining_waiters: list[_NetworkWaiter] = []
        for waiter in self._waiters:
            if waiter.future.done():
                continue
            if waiter.record_filter.matches(record):
                waiter.future.set_result(record)
                continue
            remaining_waiters.append(waiter)
        self._waiters = remaining_waiters

    def get_captured_records(
        self,
        *,
        record_filter: NetworkRecordFilter,
        clear: bool = True,
    ) -> list[dict[str, Any]]:
        matched: list[dict[str, Any]] = []
        if not clear:
            for record in self._captured_records:
                if record_filter.matches(record):
                    matched.append(record)
            return matched
        retained: deque[dict[str, Any]] = deque(maxlen=self._captured_records.maxlen)
        for record in self._captured_records:
            if record_filter.matches(record):
                matched.append(record)
                continue
            retained.append(record)
        self._captured_records = retained
        return matched

    async def wait_for_record(
        self,
        *,
        record_filter: NetworkRecordFilter,
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        for record in reversed(self._recent_records):
            if record_filter.matches(record):
                return record
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        waiter = _NetworkWaiter(record_filter=record_filter, future=future)
        self._waiters.append(waiter)
        try:
            return await asyncio.wait_for(future, timeout=timeout_seconds)
        finally:
            self._waiters = [item for item in self._waiters if item.future is not future]
