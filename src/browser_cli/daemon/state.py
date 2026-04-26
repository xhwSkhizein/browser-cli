"""Shared daemon state."""

from __future__ import annotations

import asyncio

from browser_cli.daemon.browser_service import BrowserService
from browser_cli.daemon.run_registry import CommandRunRegistry
from browser_cli.tabs import TabRegistry


class DaemonState:
    def __init__(self) -> None:
        self.tabs = TabRegistry()
        self.browser_service = BrowserService(self.tabs)
        self.run_registry = CommandRunRegistry(
            read_handler=self.browser_service.read_page_from_args,
            begin_handler=self.browser_service.begin_command,
            end_handler=self.browser_service.end_command,
        )
        self.shutdown_event = asyncio.Event()
