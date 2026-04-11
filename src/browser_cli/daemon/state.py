"""Shared daemon state."""

from __future__ import annotations

import asyncio

from browser_cli.daemon.browser_service import BrowserService
from browser_cli.tabs import TabRegistry


class DaemonState:
    def __init__(self) -> None:
        self.tabs = TabRegistry()
        self.browser_service = BrowserService(self.tabs)
        self.shutdown_event = asyncio.Event()
