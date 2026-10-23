from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from browser_cli.drivers.playwright_driver import PlaywrightDriver


def test_playwright_target_restoration_does_not_bring_page_to_front() -> None:
    driver = PlaywrightDriver()
    summary = {"page_id": "page_0001", "url": "https://example.com", "title": "Example"}
    page = SimpleNamespace(bring_to_front=AsyncMock())
    service = SimpleNamespace(
        get_page_summary=AsyncMock(return_value=summary), _require_page=Mock(return_value=page)
    )
    driver._service = service  # noqa: SLF001

    assert asyncio.run(driver.switch_tab("page_0001")) == summary
    page.bring_to_front.assert_not_awaited()
    service.get_page_summary.assert_awaited_once_with("page_0001")
