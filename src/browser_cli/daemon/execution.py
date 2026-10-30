"""Coordinate browser work across requests and daemon-memory background runs."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal


class BrowserExecutionCoordinator:
    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._active = 0
        self._exclusive_waiters = 0
        self._exclusive_mode: str | None = None

    @asynccontextmanager
    async def scope(
        self, *, mode: Literal["shared", "batch", "exclusive", "cleanup"] = "shared"
    ) -> AsyncIterator[None]:
        """Preserve independent actions and allow cleanup through ordinary batches."""
        # Shared work remains concurrent; TabRegistry owns immediate busy errors.
        # Waiting batches take priority over newly arriving browser actions.
        exclusive = mode in {"batch", "exclusive"}
        async with self._condition:
            if exclusive:
                self._exclusive_waiters += 1
                try:
                    await self._condition.wait_for(lambda: self._active == 0)
                    self._exclusive_mode = mode
                finally:
                    self._exclusive_waiters -= 1
                    self._condition.notify_all()
            elif mode == "cleanup":
                # Closing an owned page may interrupt a batch or a shared action,
                # but must not race a global stop or workspace rebuild.
                await self._condition.wait_for(lambda: self._exclusive_mode in {None, "batch"})
            else:
                await self._condition.wait_for(
                    lambda: self._exclusive_mode is None and not self._exclusive_waiters
                )
            self._active += 1
        try:
            yield
        finally:
            async with self._condition:
                self._active -= 1
                if exclusive:
                    self._exclusive_mode = None
                self._condition.notify_all()
