# Browser CLI Persistent Startup Page Reuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the managed Playwright backend able to open and read pages after startup by reusing persistent-context startup blank pages instead of closing the last page and breaking `new_page()`.

**Architecture:** Add startup-page tracking inside `src/browser_cli/browser/service.py`, route both `new_tab()` and `read_page()` through one internal page-acquisition helper, and cover the failure mode with browser-service unit tests that reproduce the persistent-context last-page bug without depending on the daemon layer.

**Tech Stack:** Python 3.10+, Playwright async API, pytest, Browser CLI browser service

---

## Task 1: Add browser-service regression tests for startup page reuse

**Files:**
- Create: `tests/unit/test_browser_service.py`
- Modify: `src/browser_cli/browser/service.py`
- Reference: `src/browser_cli/browser/session.py`

- [ ] **Step 1: Write the failing test scaffolding for reusable startup pages**

Create `tests/unit/test_browser_service.py` with fake page/context/playwright objects that model the reproduced failure: once the last startup page is closed, later `new_page()` raises `Target.createTarget`.

```python
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import playwright.async_api as playwright_async_api

from browser_cli.browser.service import BrowserService
from browser_cli.profiles.discovery import ChromeEnvironment


class _FakePage:
    def __init__(self, url: str = "about:blank", *, title: str = "blank") -> None:
        self.url = url
        self._title = title
        self.closed = False
        self.goto_calls: list[str] = []

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

    async def content(self) -> str:
        return f"<html>{self.url}</html>"

    async def evaluate(self, script: str):
        if "outerHTML" in script:
            return f"<html>{self.url}</html>"
        if "scrollHeight" in script:
            return 100
        return None


class _FakeContext:
    def __init__(self, startup_pages: list[_FakePage]) -> None:
        self.pages = list(startup_pages)
        self.new_page_calls = 0
        self.closed = False

    async def add_init_script(self, script: str) -> None:
        _ = script

    async def new_page(self) -> _FakePage:
        self.new_page_calls += 1
        if not self.pages or all(page.is_closed() for page in self.pages):
            raise RuntimeError("Target.createTarget: Failed to open a new tab")
        page = _FakePage()
        self.pages.append(page)
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
```

- [ ] **Step 2: Add targeted failing tests for startup-page reuse**

Add tests that assert Browser CLI no longer closes the startup page during `_start()`, reuses a tracked blank page in `new_tab()`, reuses a tracked blank page in `read_page()`, skips non-blank startup pages, and clears startup-page state on `stop()`.

```python
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


def test_startup_keeps_blank_page_for_reuse(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def _scenario() -> None:
        startup_page = _FakePage()
        context = _FakeContext([startup_page])
        monkeypatch.setattr(playwright_async_api, "async_playwright", lambda: _FakeAsyncPlaywright(context))
        service = BrowserService(chrome_environment=_chrome_environment(tmp_path))

        await service.ensure_started()

        assert startup_page.closed is False
        assert service._reusable_startup_pages == [startup_page]  # noqa: SLF001

    asyncio.run(_scenario())


def test_new_tab_reuses_startup_blank_page(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def _scenario() -> None:
        startup_page = _FakePage()
        context = _FakeContext([startup_page])
        monkeypatch.setattr(playwright_async_api, "async_playwright", lambda: _FakeAsyncPlaywright(context))
        service = BrowserService(chrome_environment=_chrome_environment(tmp_path))

        page = await service.new_tab(url="https://example.com/start")

        assert page["url"] == "https://example.com/start"
        assert context.new_page_calls == 0
        assert startup_page.goto_calls == ["https://example.com/start"]

    asyncio.run(_scenario())


def test_read_page_reuses_startup_blank_page(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def _scenario() -> None:
        startup_page = _FakePage()
        context = _FakeContext([startup_page])
        monkeypatch.setattr(playwright_async_api, "async_playwright", lambda: _FakeAsyncPlaywright(context))
        service = BrowserService(chrome_environment=_chrome_environment(tmp_path))

        payload = await service.read_page(url="https://example.com/read")

        assert payload["url"] == "https://example.com/read"
        assert context.new_page_calls == 0
        assert startup_page.goto_calls == ["https://example.com/read"]

    asyncio.run(_scenario())


def test_non_blank_startup_page_falls_back_to_new_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _scenario() -> None:
        startup_page = _FakePage(url="chrome://newtab/")
        context = _FakeContext([startup_page])
        monkeypatch.setattr(playwright_async_api, "async_playwright", lambda: _FakeAsyncPlaywright(context))
        service = BrowserService(chrome_environment=_chrome_environment(tmp_path))

        await service.new_tab(url="https://example.com/fallback")

        assert context.new_page_calls == 1

    asyncio.run(_scenario())


def test_stop_clears_reusable_startup_page_pool(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _scenario() -> None:
        startup_page = _FakePage()
        context = _FakeContext([startup_page])
        monkeypatch.setattr(playwright_async_api, "async_playwright", lambda: _FakeAsyncPlaywright(context))
        service = BrowserService(chrome_environment=_chrome_environment(tmp_path))

        await service.ensure_started()
        await service.stop()

        assert service._reusable_startup_pages == []  # noqa: SLF001

    asyncio.run(_scenario())
```

- [ ] **Step 3: Run the targeted test file and confirm it fails on the current implementation**

Run: `pytest tests/unit/test_browser_service.py -q`

Expected: FAIL because the current implementation closes the startup page during `_start()` and still calls `self._context.new_page()` directly from both `new_tab()` and `read_page()`.

- [ ] **Step 4: Commit the failing-test checkpoint**

```bash
git add tests/unit/test_browser_service.py
git commit -m "test: add startup page reuse regression coverage"
```

## Task 2: Implement reusable startup-page acquisition in the browser service

**Files:**
- Modify: `src/browser_cli/browser/service.py`
- Reference: `src/browser_cli/browser/session.py`
- Test: `tests/unit/test_browser_service.py`

- [ ] **Step 1: Add startup-page tracking state to `BrowserService`**

Extend `BrowserService.__init__()` so the service can remember startup pages created by the persistent context before Browser CLI assigns them to page ids.

```python
class BrowserService:
    READ_NAVIGATION_TIMEOUT_SECONDS = 30.0
    READ_SETTLE_TIMEOUT_MS = 1_200
    READ_SCROLL_PAUSE_MS = 450
    READ_SCROLL_MAX_ROUNDS = 8
    READ_SCROLL_STABLE_ROUNDS = 2

    def __init__(
        self,
        chrome_environment: ChromeEnvironment | None = None,
        *,
        headless: bool | None = None,
    ) -> None:
        self._chrome_environment = chrome_environment
        self._headless = default_headless() if headless is None else headless
        self._playwright: Any | None = None
        self._context: Any | None = None
        self._pages: dict[str, Any] = {}
        self._page_counter = 0
        self._reusable_startup_pages: list[Any] = []
```

- [ ] **Step 2: Preserve startup pages during `_start()` instead of closing them**

Replace the eager close loop after `launch_persistent_context(...)` with startup-page capture.

```python
            init_script = build_init_script(
                headless=launch_config.headless, locale=launch_config.locale
            )
            if init_script:
                await self._context.add_init_script(init_script)
            self._reusable_startup_pages = list(self._context.pages)
```

- [ ] **Step 3: Add one internal helper that claims a safe startup blank page before calling `new_page()`**

Add focused helpers in `BrowserService` to keep the reuse rules explicit and shared by `new_tab()` and `read_page()`.

```python
    def _is_reusable_startup_page(self, page: Any) -> bool:
        if page.is_closed():
            return False
        return str(getattr(page, "url", "")) in {"", "about:blank"}

    async def _acquire_page(self) -> Any:
        while self._reusable_startup_pages:
            page = self._reusable_startup_pages.pop(0)
            if self._is_reusable_startup_page(page):
                return page
        return await self._context.new_page()

    def _register_page(self, page: Any, *, page_id: str | None = None) -> str:
        resolved_page_id = page_id or self._next_page_id()
        self._pages[resolved_page_id] = page
        self._network_observers[resolved_page_id] = PlaywrightNetworkObserver(
            page_id=resolved_page_id,
            page=page,
        )
        return resolved_page_id
```

- [ ] **Step 4: Route both `new_tab()` and `read_page()` through the new helper**

Update both call sites so the browser service reuses a startup page when safe and only falls back to `new_page()` when no reusable page remains.

```python
    async def new_tab(
        self,
        *,
        page_id: str | None = None,
        url: str | None = None,
        wait_until: str = "load",
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        await self.ensure_started()
        async with self._page_create_lock:
            page = await self._acquire_page()
            page_id = self._register_page(page, page_id=page_id)
            if url:
                await page.goto(
                    self._normalize_url(url),
                    wait_until=wait_until,
                    timeout=(timeout_seconds or 30.0) * 1000.0,
                )
            return await self.get_page_summary(page_id)

    async def read_page(
        self,
        *,
        url: str,
        output_mode: str = "html",
        scroll_bottom: bool = False,
    ) -> dict[str, Any]:
        if output_mode not in {"html", "snapshot"}:
            raise InvalidInputError(f"Unsupported read output mode: {output_mode}")
        await self.ensure_started()
        page_id: str | None = None
        page: Any | None = None
        try:
            async with self._page_create_lock:
                page = await self._acquire_page()
                page_id = self._register_page(page)
```

- [ ] **Step 5: Clear startup-page state during shutdown**

Keep `stop()` bounded by clearing the new reuse pool with the rest of Browser CLI's transient browser-service state.

```python
        self._pages.clear()
        self._snapshot_registry.clear()
        self._console_messages.clear()
        self._console_handlers.clear()
        self._network_observers.clear()
        self._dialog_handlers.clear()
        self._video_started.clear()
        self._pending_video_save_paths.clear()
        self._reusable_startup_pages.clear()
        self._tracing_active = False
```

- [ ] **Step 6: Run the targeted tests and make them pass**

Run: `pytest tests/unit/test_browser_service.py -q`

Expected: PASS

- [ ] **Step 7: Commit the implementation checkpoint**

```bash
git add src/browser_cli/browser/service.py tests/unit/test_browser_service.py
git commit -m "fix: reuse startup pages in persistent browser contexts"
```

## Task 3: Verify the real-world reproduction and run repository validation

**Files:**
- Modify: `src/browser_cli/browser/service.py`
- Test: `tests/unit/test_browser_service.py`
- Validate: `scripts/lint.sh`
- Validate: `scripts/test.sh`
- Validate: `scripts/guard.sh`

- [ ] **Step 1: Re-run the local reproduction that previously failed**

Use the same minimal reproduction approach that proved the bug: launch a persistent context, keep the startup page alive, and confirm Browser CLI can now create or reuse a page without raising `Target.createTarget`.

```bash
python3 - <<'PY'
import asyncio
import tempfile
from pathlib import Path
from playwright.async_api import async_playwright
from browser_cli.browser.stealth import build_context_options, build_ignore_default_args, build_launch_args
from browser_cli.profiles.discovery import discover_chrome_executable

async def main():
    user_data_dir = Path(tempfile.mkdtemp(prefix="bcli-repro-"))
    executable = discover_chrome_executable()
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            executable_path=str(executable),
            headless=False,
            viewport={"width": 1440, "height": 1024},
            ignore_default_args=build_ignore_default_args(),
            args=[
                *build_launch_args(headless=False, viewport_width=1440, viewport_height=1024, locale="en-US"),
                "--profile-directory=Default",
            ],
            **build_context_options(viewport_width=1440, viewport_height=1024, locale="en-US"),
        )
        startup_page = context.pages[0]
        assert startup_page.url == "about:blank"
        page = startup_page
        await page.goto("https://example.com", wait_until="load", timeout=30_000)
        print("PASS", page.url)
        await context.close()

asyncio.run(main())
PY
```

Expected: `PASS https://example.com/`

- [ ] **Step 2: Verify the Browser CLI command path that originally failed**

Run:

```bash
BROWSER_CLI_EXTENSION_PORT=19827 browser-cli reload
BROWSER_CLI_EXTENSION_PORT=19827 browser-cli read https://example.com
```

Expected:

- `browser-cli reload` reports a healthy daemon
- `browser-cli read https://example.com` returns page HTML instead of `Target.createTarget`

- [ ] **Step 3: Run repository lint**

Run: `scripts/lint.sh`

Expected: PASS

- [ ] **Step 4: Run repository tests**

Run: `scripts/test.sh`

Expected: PASS

- [ ] **Step 5: Run repository guards**

Run: `scripts/guard.sh`

Expected: PASS

- [ ] **Step 6: Commit the validated fix**

```bash
git add src/browser_cli/browser/service.py tests/unit/test_browser_service.py
git commit -m "fix: keep persistent startup pages reusable"
```
