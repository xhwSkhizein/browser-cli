from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from browser_cli.browser.models import BrowserLaunchConfig
from browser_cli.browser.session import BrowserSession
from browser_cli.runtime.read_runner import ReadRequest, ReadRunner
from tests.integration.fixture_server import run_fixture_server


def _can_launch_playwright_browser() -> bool:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return False

    async def _probe() -> bool:
        playwright = await async_playwright().start()
        try:
            browser = await playwright.chromium.launch(headless=True)
            await browser.close()
            return True
        except Exception:
            return False
        finally:
            await playwright.stop()

    return asyncio.run(_probe())


pytestmark = pytest.mark.integration


@pytest.mark.skipif(not _can_launch_playwright_browser(), reason="Playwright browser runtime unavailable")
def test_capture_html_from_dynamic_fixture(tmp_path: Path) -> None:
    async def _run() -> str:
        config = BrowserLaunchConfig(
            executable_path=None,
            user_data_dir=tmp_path / "user-data",
            headless=True,
        )
        config.user_data_dir.mkdir(parents=True)
        async with BrowserSession(config) as browser:
            with run_fixture_server() as base_url:
                await browser.navigate(f"{base_url}/dynamic")
                await browser.settle()
                return await browser.capture_html()

    html = asyncio.run(_run())
    assert "Dynamic Fixture" in html
    assert "Rendered content." in html


@pytest.mark.skipif(not _can_launch_playwright_browser(), reason="Playwright browser runtime unavailable")
def test_capture_snapshot_from_static_fixture(tmp_path: Path) -> None:
    async def _run() -> str:
        config = BrowserLaunchConfig(
            executable_path=None,
            user_data_dir=tmp_path / "user-data",
            headless=True,
        )
        config.user_data_dir.mkdir(parents=True)
        async with BrowserSession(config) as browser:
            with run_fixture_server() as base_url:
                await browser.navigate(f"{base_url}/static")
                await browser.settle()
                return await browser.capture_snapshot()

    snapshot = asyncio.run(_run())
    assert "heading" in snapshot
    assert "Static Fixture" in snapshot


@pytest.mark.skipif(not _can_launch_playwright_browser(), reason="Playwright browser runtime unavailable")
def test_read_runner_scroll_bottom_loads_more_content(tmp_path: Path) -> None:
    async def _run() -> str:
        with run_fixture_server() as base_url:
            runner = ReadRunner()
            runner._chrome_environment = type(  # noqa: SLF001
                "Env",
                (),
                {
                    "executable_path": None,
                    "user_data_dir": tmp_path / "user-data",
                    "profile_directory": "Default",
                },
            )()
            (tmp_path / "user-data" / "Default").mkdir(parents=True)
            result = await runner.run(
                ReadRequest(
                    url=f"{base_url}/lazy",
                    output_mode="html",
                    scroll_bottom=True,
                )
            )
            return result.body

    html = asyncio.run(_run())
    assert "Lazy Item 4" in html

