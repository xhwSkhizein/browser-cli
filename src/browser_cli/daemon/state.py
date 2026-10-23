"""Shared daemon state."""

from __future__ import annotations

import asyncio

from browser_cli.daemon.browser_service import BrowserService
from browser_cli.daemon.execution import BrowserExecutionCoordinator
from browser_cli.daemon.run_registry import CommandRunRegistry
from browser_cli.tabs import TabRegistry


class DaemonState:
    def __init__(
        self, *, tabs: TabRegistry | None = None, browser_service: BrowserService | None = None
    ) -> None:
        self.tabs = tabs if tabs is not None else TabRegistry()
        self.browser_service = (
            browser_service if browser_service is not None else BrowserService(self.tabs)
        )
        self.execution = BrowserExecutionCoordinator()
        self.run_registry = CommandRunRegistry(
            read_handler=self.browser_service.read_page_from_args,
            begin_handler=self.browser_service.begin_command,
            end_handler=self.browser_service.end_command,
            execution=self.execution,
        )
        self.shutdown_event = asyncio.Event()
