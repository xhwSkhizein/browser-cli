"""Coordinate browser work across requests and daemon-memory background runs."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class BrowserExecutionCoordinator:
    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._active = 0
        self._exclusive_waiters = 0
        self._exclusive_running = False

    @asynccontextmanager
    async def scope(self, *, exclusive: bool = False) -> AsyncIterator[None]:
        # Shared work remains concurrent; TabRegistry owns immediate busy errors.
        # Waiting batches take priority over newly arriving browser actions.
        async with self._condition:
            if exclusive:
                self._exclusive_waiters += 1
                try:
                    await self._condition.wait_for(lambda: self._active == 0)
                    self._exclusive_running = True
                finally:
                    self._exclusive_waiters -= 1
                    self._condition.notify_all()
            else:
                await self._condition.wait_for(
                    lambda: not self._exclusive_running and not self._exclusive_waiters
                )
            self._active += 1
        try:
            yield
        finally:
            async with self._condition:
                self._active -= 1
                if exclusive:
                    self._exclusive_running = False
                self._condition.notify_all()
