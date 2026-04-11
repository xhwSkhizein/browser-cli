"""Playwright-backed browser session wrapper."""

from __future__ import annotations

from types import TracebackType
from typing import Any

from browser_cli.browser.models import BrowserLaunchConfig
from browser_cli.browser.snapshot import capture_snapshot
from browser_cli.browser.stealth import (
    build_context_options,
    build_ignore_default_args,
    build_init_script,
    build_launch_args,
)
from browser_cli.errors import BrowserUnavailableError, ProfileUnavailableError, TemporaryReadError


class BrowserSession:
    def __init__(self, config: BrowserLaunchConfig) -> None:
        self._config = config
        self._playwright: Any | None = None
        self._context: Any | None = None
        self._page: Any | None = None

    async def __aenter__(self) -> BrowserSession:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def start(self) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - dependency problem
            raise BrowserUnavailableError(
                "Playwright is not installed. Run: python3 -m pip install -e ."
            ) from exc

        try:
            self._playwright = await async_playwright().start()
            chromium = self._playwright.chromium
            context_options = build_context_options(
                viewport_width=self._config.viewport_width,
                viewport_height=self._config.viewport_height,
                locale=self._config.locale,
            )
            self._context = await chromium.launch_persistent_context(
                user_data_dir=str(self._config.user_data_dir),
                executable_path=str(self._config.executable_path)
                if self._config.executable_path
                else None,
                headless=self._config.headless,
                viewport={
                    "width": self._config.viewport_width,
                    "height": self._config.viewport_height,
                },
                ignore_default_args=build_ignore_default_args(),
                args=[
                    *build_launch_args(
                        headless=self._config.headless,
                        viewport_width=self._config.viewport_width,
                        viewport_height=self._config.viewport_height,
                        locale=self._config.locale,
                    ),
                    f"--profile-directory={self._config.profile_directory}",
                ],
                **context_options,
            )
            init_script = build_init_script(
                headless=self._config.headless, locale=self._config.locale
            )
            if init_script:
                await self._context.add_init_script(init_script)
            self._page = (
                self._context.pages[0] if self._context.pages else await self._context.new_page()
            )
            self._page.set_default_navigation_timeout(self._config.navigation_timeout_ms)
        except Exception as exc:
            await self.close()
            self._raise_launch_error(exc)

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        self._page = None

    async def navigate(self, url: str) -> None:
        self._ensure_started()
        try:
            await self._page.goto(
                url, wait_until="load", timeout=self._config.navigation_timeout_ms
            )
        except Exception as exc:
            raise TemporaryReadError(f"Failed to navigate to {url}: {exc}") from exc

    async def settle(self) -> None:
        self._ensure_started()
        await self._page.wait_for_timeout(self._config.settle_timeout_ms)

    async def scroll_to_bottom(self) -> None:
        self._ensure_started()
        stable_rounds = 0
        previous_height = -1
        for _ in range(8):
            current_height = await self._page.evaluate(
                "() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
            )
            await self._page.evaluate(
                "() => window.scrollTo({ top: document.body.scrollHeight, behavior: 'instant' })"
            )
            await self._page.wait_for_timeout(450)
            next_height = await self._page.evaluate(
                "() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
            )
            if next_height == current_height == previous_height:
                stable_rounds += 1
            else:
                stable_rounds = 0
            previous_height = next_height
            if stable_rounds >= 1:
                break

    async def capture_html(self) -> str:
        self._ensure_started()
        return await self._page.content()

    async def capture_snapshot(self) -> str:
        self._ensure_started()
        snapshot = await capture_snapshot(self._page, page_id="read_page")
        return snapshot.tree

    def _ensure_started(self) -> None:
        if self._page is None:
            raise TemporaryReadError("Browser session was not started.")

    def _raise_launch_error(self, exc: Exception) -> None:
        message = str(exc)
        lowered = message.lower()
        if (
            "singleton" in lowered
            or "profile" in lowered
            or "user data directory is already in use" in lowered
        ):
            raise ProfileUnavailableError(message) from exc
        if "executable" in lowered or "browser" in lowered or "failed to launch" in lowered:
            raise BrowserUnavailableError(message) from exc
        raise TemporaryReadError(message) from exc
