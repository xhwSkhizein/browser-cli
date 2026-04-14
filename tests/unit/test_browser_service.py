from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import playwright.async_api as playwright_async_api
import pytest

from browser_cli.browser.service import BrowserService
from browser_cli.profiles.discovery import ChromeEnvironment


class _FakePage:
    def __init__(self, url: str = "about:blank", *, title: str = "blank") -> None:
        self.url = url
        self._title = title
        self.closed = False
        self.goto_calls: list[str] = []
        self.event_handlers: dict[str, list[Any]] = {}

    def is_closed(self) -> bool:
        return self.closed

    async def close(self) -> None:
        self.closed = True

    async def title(self) -> str:
        return self._title

    async def goto(self, url: str, *, wait_until: str, timeout: float) -> None:
        _ = wait_until
        _ = timeout
        self.url = url
        self._title = f"title:{url}"
        self.goto_calls.append(url)

    async def wait_for_timeout(self, timeout_ms: int) -> None:
        _ = timeout_ms

    async def evaluate(self, script: str) -> Any:
        if "outerHTML" in script:
            return f"<html>{self.url}</html>"
        if "scrollHeight" in script:
            return 100
        return None

    def on(self, event_name: str, handler: Any) -> None:
        self.event_handlers.setdefault(event_name, []).append(handler)

    def remove_listener(self, event_name: str, handler: Any) -> None:
        handlers = self.event_handlers.get(event_name, [])
        if handler in handlers:
            handlers.remove(handler)


class _FakeContext:
    def __init__(self, startup_pages: list[_FakePage]) -> None:
        self._pages = list(startup_pages)
        self.new_page_calls = 0
        self.closed = False

    @property
    def pages(self) -> list[_FakePage]:
        return [page for page in self._pages if not page.is_closed()]

    async def add_init_script(self, script: str) -> None:
        _ = script

    async def new_page(self) -> _FakePage:
        self.new_page_calls += 1
        if not self.pages:
            raise RuntimeError("Target.createTarget: Failed to open a new tab")
        page = _FakePage()
        self._pages.append(page)
        return page

    async def close(self) -> None:
        self.closed = True


class _FakeChromium:
    def __init__(self, context: _FakeContext) -> None:
        self._context = context

    async def launch_persistent_context(self, **kwargs):
        _ = kwargs
        return self._context


class _FakePlaywrightManager:
    def __init__(self, context: _FakeContext) -> None:
        self.chromium = _FakeChromium(context)

    async def stop(self) -> None:
        return None


class _FakeAsyncPlaywright:
    def __init__(self, context: _FakeContext) -> None:
        self._manager = _FakePlaywrightManager(context)

    async def start(self) -> _FakePlaywrightManager:
        return self._manager


def _chrome_environment(tmp_path: Path) -> ChromeEnvironment:
    profile_root = tmp_path / "profile"
    profile_root.mkdir()
    (profile_root / "Default").mkdir()
    return ChromeEnvironment(
        executable_path=Path("/usr/bin/google-chrome"),
        user_data_dir=profile_root,
        profile_directory="Default",
        source="managed",
    )


def test_startup_keeps_blank_page_for_reuse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _scenario() -> None:
        startup_page = _FakePage()
        context = _FakeContext([startup_page])
        monkeypatch.setattr(
            playwright_async_api, "async_playwright", lambda: _FakeAsyncPlaywright(context)
        )
        service = BrowserService(chrome_environment=_chrome_environment(tmp_path))

        await service.ensure_started()

        assert startup_page.closed is False
        assert service._reusable_startup_pages == [startup_page]  # noqa: SLF001
        await service.stop()

    asyncio.run(_scenario())


def test_new_tab_reuses_startup_blank_page(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def _scenario() -> None:
        startup_page = _FakePage()
        context = _FakeContext([startup_page])
        monkeypatch.setattr(
            playwright_async_api, "async_playwright", lambda: _FakeAsyncPlaywright(context)
        )
        service = BrowserService(chrome_environment=_chrome_environment(tmp_path))

        page = await service.new_tab(url="https://example.com/start")

        assert page["url"] == "https://example.com/start"
        assert context.new_page_calls == 0
        assert startup_page.goto_calls == ["https://example.com/start"]
        await service.stop()

    asyncio.run(_scenario())


def test_read_page_reuses_startup_blank_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _scenario() -> None:
        startup_page = _FakePage()
        context = _FakeContext([startup_page])
        monkeypatch.setattr(
            playwright_async_api, "async_playwright", lambda: _FakeAsyncPlaywright(context)
        )
        service = BrowserService(chrome_environment=_chrome_environment(tmp_path))

        payload = await service.read_page(url="https://example.com/read")

        assert payload["url"] == "https://example.com/read"
        assert startup_page.goto_calls == ["https://example.com/read"]
        assert context.new_page_calls == 1
        assert len(service._reusable_startup_pages) == 1  # noqa: SLF001
        assert service._reusable_startup_pages[0].url == "about:blank"  # noqa: SLF001
        await service.stop()

    asyncio.run(_scenario())


def test_repeated_read_page_calls_keep_context_usable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _scenario() -> None:
        startup_page = _FakePage()
        context = _FakeContext([startup_page])
        monkeypatch.setattr(
            playwright_async_api, "async_playwright", lambda: _FakeAsyncPlaywright(context)
        )
        service = BrowserService(chrome_environment=_chrome_environment(tmp_path))

        first = await service.read_page(url="https://example.com/one")
        second = await service.read_page(url="https://example.com/two")

        assert first["url"] == "https://example.com/one"
        assert second["url"] == "https://example.com/two"
        assert context.new_page_calls == 2
        await service.stop()

    asyncio.run(_scenario())


def test_non_blank_startup_page_falls_back_to_new_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _scenario() -> None:
        startup_page = _FakePage(url="chrome://newtab/")
        context = _FakeContext([startup_page])
        monkeypatch.setattr(
            playwright_async_api, "async_playwright", lambda: _FakeAsyncPlaywright(context)
        )
        service = BrowserService(chrome_environment=_chrome_environment(tmp_path))

        page = await service.new_tab(url="https://example.com/fallback")

        assert page["url"] == "https://example.com/fallback"
        assert context.new_page_calls == 1
        await service.stop()

    asyncio.run(_scenario())


def test_stop_clears_reusable_startup_page_pool(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _scenario() -> None:
        startup_page = _FakePage()
        context = _FakeContext([startup_page])
        monkeypatch.setattr(
            playwright_async_api, "async_playwright", lambda: _FakeAsyncPlaywright(context)
        )
        service = BrowserService(chrome_environment=_chrome_environment(tmp_path))

        await service.ensure_started()
        await service.stop()

        assert service._reusable_startup_pages == []  # noqa: SLF001

    asyncio.run(_scenario())
