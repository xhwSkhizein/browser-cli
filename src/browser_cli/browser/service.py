"""Long-lived browser service owned by the daemon."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any

from browser_cli.browser.models import BrowserLaunchConfig, default_headless
from browser_cli.browser.network_capture import PlaywrightNetworkObserver
from browser_cli.browser.snapshot import SnapshotCapture, capture_snapshot
from browser_cli.browser.stealth import (
    build_context_options,
    build_ignore_default_args,
    build_init_script,
    build_launch_args,
)
from browser_cli.constants import get_app_paths
from browser_cli.errors import (
    AmbiguousRefError,
    BrowserUnavailableError,
    EmptyContentError,
    InvalidInputError,
    NoSnapshotContextError,
    OperationFailedError,
    ProfileUnavailableError,
    RefNotFoundError,
    StaleSnapshotError,
    TemporaryReadError,
)
from browser_cli.network import NetworkRecordFilter
from browser_cli.profiles.discovery import ChromeEnvironment, discover_chrome_environment
from browser_cli.refs import SemanticRefResolver, SnapshotRegistry
from browser_cli.refs.generator import SemanticSnapshotGenerator
from browser_cli.refs.models import (
    LocatorSpec,
    RefData,
    SemanticSnapshot,
    SnapshotInput,
    SnapshotMetadata,
)


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
        self._snapshot_registry = SnapshotRegistry()
        self._ref_resolver = SemanticRefResolver()
        self._console_messages: dict[str, list[dict[str, Any]]] = {}
        self._console_handlers: dict[str, Any] = {}
        self._network_observers: dict[str, PlaywrightNetworkObserver] = {}
        self._dialog_handlers: dict[str, Any] = {}
        self._tracing_active = False
        self._video_started: set[str] = set()
        self._pending_video_save_paths: dict[str, str | None] = {}
        self._start_lock = asyncio.Lock()
        # Serialize page acquisition with last-page replacement/close so
        # concurrent closers cannot strand the persistent context with zero pages.
        self._page_create_lock = asyncio.Lock()

    @property
    def chrome_environment(self) -> ChromeEnvironment | None:
        return self._chrome_environment

    def configure_environment(self, chrome_environment: ChromeEnvironment) -> None:
        if self._context is not None and self._chrome_environment not in (None, chrome_environment):
            raise OperationFailedError(
                "Browser daemon is already running with a different Chrome profile."
            )
        self._chrome_environment = chrome_environment

    async def ensure_started(self) -> None:
        async with self._start_lock:
            if self._context is not None:
                return
            await self._start()

    async def _start(self) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover
            raise BrowserUnavailableError(
                "Playwright is not installed. Run: python3 -m pip install -e ."
            ) from exc

        chrome_environment = self._chrome_environment or discover_chrome_environment()
        launch_config = BrowserLaunchConfig(
            executable_path=chrome_environment.executable_path,
            user_data_dir=chrome_environment.user_data_dir,
            profile_directory=chrome_environment.profile_directory,
            headless=self._headless,
        )
        self._chrome_environment = chrome_environment

        try:
            self._playwright = await async_playwright().start()
            chromium = self._playwright.chromium
            video_dir = get_app_paths().artifacts_dir / "playwright-video"
            video_dir.mkdir(parents=True, exist_ok=True)
            context_options = build_context_options(
                viewport_width=launch_config.viewport_width,
                viewport_height=launch_config.viewport_height,
                locale=launch_config.locale,
            )
            self._context = await chromium.launch_persistent_context(
                user_data_dir=str(launch_config.user_data_dir),
                executable_path=str(launch_config.executable_path)
                if launch_config.executable_path
                else None,
                headless=launch_config.headless,
                viewport={
                    "width": launch_config.viewport_width,
                    "height": launch_config.viewport_height,
                },
                record_video_dir=str(video_dir),
                record_video_size={
                    "width": launch_config.viewport_width,
                    "height": launch_config.viewport_height,
                },
                ignore_default_args=build_ignore_default_args(),
                args=[
                    *build_launch_args(
                        headless=launch_config.headless,
                        viewport_width=launch_config.viewport_width,
                        viewport_height=launch_config.viewport_height,
                        locale=launch_config.locale,
                    ),
                    f"--profile-directory={launch_config.profile_directory}",
                ],
                **context_options,
            )
            init_script = build_init_script(
                headless=launch_config.headless, locale=launch_config.locale
            )
            if init_script:
                await self._context.add_init_script(init_script)
            self._reusable_startup_pages = list(self._context.pages)
        except Exception as exc:
            await self.stop()
            self._raise_launch_error(exc)

    async def stop(self) -> dict[str, Any]:
        trace_path: str | None = None
        if self._tracing_active and self._context is not None:
            try:
                trace_path = await self._stop_tracing_impl(path=None)
            except Exception:
                trace_path = None
        closed_pages: list[str] = []
        video_paths: list[str] = []
        for page_id in list(self._pages.keys()):
            try:
                result = await self._close_page(page_id)
                closed_pages.append(page_id)
                if result.get("video_path"):
                    video_paths.append(str(result["video_path"]))
            except Exception:
                pass
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
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        return {
            "closed_pages": closed_pages,
            "video_paths": video_paths,
            "trace_path": trace_path,
        }

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

    async def capture_snapshot_input(
        self,
        page_id: str,
        *,
        interactive: bool = False,
        full_page: bool = True,
    ) -> SnapshotInput:
        _ = interactive
        _ = full_page
        page = self._require_page(page_id)
        raw_snapshot = await SemanticSnapshotGenerator().page_snapshot_for_ai(page)
        return SnapshotInput(
            raw_snapshot=raw_snapshot,
            captured_url=str(page.url),
            captured_at=time.time(),
        )

    async def capture_semantic_snapshot(
        self,
        page_id: str,
        *,
        interactive: bool = False,
        full_page: bool = True,
    ) -> SemanticSnapshot:
        page = self._require_page(page_id)
        raw_snapshot = await SemanticSnapshotGenerator().page_snapshot_for_ai(page)
        return SemanticSnapshotGenerator().snapshot_from_raw_text(
            raw_snapshot,
            page_id=page_id,
            captured_url=str(page.url),
            interactive=interactive,
            full_page=full_page,
            captured_at=time.time(),
        )

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
            await page.goto(
                self._normalize_url(url),
                wait_until="load",
                timeout=self.READ_NAVIGATION_TIMEOUT_SECONDS * 1000.0,
            )
            await self._settle_page(page)
            if scroll_bottom:
                await self._scroll_page_to_bottom(page)
                await self._settle_page(page)
            if output_mode == "snapshot":
                snapshot = await capture_snapshot(
                    page, page_id=page_id, interactive=False, full_page=True
                )
                body = snapshot.tree
            else:
                body = await self._capture_html_from_page(page)
            if not body.strip():
                raise EmptyContentError()
            payload = {
                "page_id": page_id,
                "body": body,
                "output_mode": output_mode,
                "url": page.url,
            }
            chrome_environment = self._chrome_environment
            if chrome_environment is not None:
                payload["used_fallback_profile"] = chrome_environment.source == "fallback"
                if chrome_environment.source == "fallback":
                    payload["fallback_profile_dir"] = str(chrome_environment.user_data_dir)
                    payload["fallback_reason"] = chrome_environment.fallback_reason
                if chrome_environment.profile_name:
                    payload["profile_name"] = chrome_environment.profile_name
                payload["profile_directory"] = chrome_environment.profile_directory
            return payload
        finally:
            if page_id is not None and page_id in self._pages:
                with contextlib.suppress(Exception):
                    await self._close_page(page_id)

    async def close_tab(self, page_id: str) -> dict[str, Any]:
        return await self._close_page(page_id)

    async def get_page_summary(self, page_id: str) -> dict[str, Any]:
        page = self._require_page(page_id)
        title = await page.title()
        return {
            "page_id": page_id,
            "url": page.url,
            "title": title,
        }

    async def get_page_info(self, page_id: str) -> dict[str, Any]:
        page = self._require_page(page_id)
        title = await page.title()
        page_metrics = await page.evaluate(
            """() => ({
                viewport_width: window.innerWidth,
                viewport_height: window.innerHeight,
                page_width: Math.max(document.body.scrollWidth, document.documentElement.scrollWidth),
                page_height: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight),
                scroll_x: window.scrollX,
                scroll_y: window.scrollY,
            })"""
        )
        return {
            "page_id": page_id,
            "url": page.url,
            "title": title,
            **page_metrics,
        }

    async def capture_html(self, page_id: str) -> dict[str, Any]:
        page = self._require_page(page_id)
        html = await self._capture_html_from_page(page)
        return {
            "page_id": page_id,
            "html": html,
        }

    async def capture_snapshot(
        self,
        page_id: str,
        *,
        interactive: bool = False,
        full_page: bool = True,
    ) -> dict[str, Any]:
        page = self._require_page(page_id)
        snapshot = await capture_snapshot(
            page, page_id=page_id, interactive=interactive, full_page=full_page
        )
        semantic_snapshot = self._semantic_snapshot_from_capture(
            page_id, snapshot, interactive=interactive, full_page=full_page
        )
        state = self._snapshot_registry.store(semantic_snapshot)
        return {
            "page_id": page_id,
            "tree": snapshot.tree,
            "snapshot_id": snapshot.snapshot_id,
            "captured_url": state.captured_url,
            "captured_at": state.captured_at,
            "refs_summary": [
                {
                    "ref": ref,
                    **metadata,
                }
                for ref, metadata in snapshot.refs.items()
            ],
        }

    async def navigate(
        self, page_id: str, url: str, *, wait_until: str = "load", timeout_seconds: float = 30.0
    ) -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.goto(
            self._normalize_url(url), wait_until=wait_until, timeout=timeout_seconds * 1000.0
        )
        return await self.get_page_summary(page_id)

    async def reload(
        self, page_id: str, *, wait_until: str = "load", timeout_seconds: float = 30.0
    ) -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.reload(wait_until=wait_until, timeout=timeout_seconds * 1000.0)
        return await self.get_page_summary(page_id)

    async def go_back(self, page_id: str) -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.go_back()
        return await self.get_page_summary(page_id)

    async def go_forward(self, page_id: str) -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.go_forward()
        return await self.get_page_summary(page_id)

    async def resize(self, page_id: str, *, width: int, height: int) -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.set_viewport_size({"width": width, "height": height})
        return {"page_id": page_id, "width": width, "height": height}

    async def click_locator(self, page_id: str, locator_spec: LocatorSpec) -> dict[str, Any]:
        locator = await self._get_locator_by_spec(page_id, locator_spec)
        await locator.click()
        return {"page_id": page_id, "ref": locator_spec.ref, "action": "click"}

    async def double_click_locator(self, page_id: str, locator_spec: LocatorSpec) -> dict[str, Any]:
        locator = await self._get_locator_by_spec(page_id, locator_spec)
        await locator.dblclick()
        return {"page_id": page_id, "ref": locator_spec.ref, "action": "double-click"}

    async def hover_locator(self, page_id: str, locator_spec: LocatorSpec) -> dict[str, Any]:
        locator = await self._get_locator_by_spec(page_id, locator_spec)
        await locator.hover()
        return {"page_id": page_id, "ref": locator_spec.ref, "action": "hover"}

    async def focus_locator(self, page_id: str, locator_spec: LocatorSpec) -> dict[str, Any]:
        locator = await self._get_locator_by_spec(page_id, locator_spec)
        await locator.focus()
        return {"page_id": page_id, "ref": locator_spec.ref, "action": "focus"}

    async def fill_locator(
        self,
        page_id: str,
        locator_spec: LocatorSpec,
        text: str,
        *,
        submit: bool = False,
    ) -> dict[str, Any]:
        locator = await self._get_locator_by_spec(page_id, locator_spec)
        await locator.fill(text)
        if submit:
            await locator.press("Enter")
        return {"page_id": page_id, "ref": locator_spec.ref, "filled": True, "submitted": submit}

    async def select_locator(
        self, page_id: str, locator_spec: LocatorSpec, text: str
    ) -> dict[str, Any]:
        locator = await self._get_locator_by_spec(page_id, locator_spec)
        await locator.select_option(label=text)
        return {"page_id": page_id, "ref": locator_spec.ref, "selected": text}

    async def list_locator_options(self, page_id: str, locator_spec: LocatorSpec) -> dict[str, Any]:
        locator = await self._get_locator_by_spec(page_id, locator_spec)
        options = await locator.locator("option").all_inner_texts()
        normalized = [item.strip() for item in options if item.strip()]
        return {"page_id": page_id, "ref": locator_spec.ref, "options": normalized}

    async def set_checked_locator(
        self,
        page_id: str,
        locator_spec: LocatorSpec,
        *,
        checked: bool,
    ) -> dict[str, Any]:
        locator = await self._get_locator_by_spec(page_id, locator_spec)
        if checked:
            await locator.check()
        else:
            await locator.uncheck()
        return {"page_id": page_id, "ref": locator_spec.ref, "checked": checked}

    async def scroll_to_locator(self, page_id: str, locator_spec: LocatorSpec) -> dict[str, Any]:
        locator = await self._get_locator_by_spec(page_id, locator_spec)
        await locator.scroll_into_view_if_needed()
        return {"page_id": page_id, "ref": locator_spec.ref, "scrolled": True}

    async def drag_between_locators(
        self,
        page_id: str,
        start_locator_spec: LocatorSpec,
        end_locator_spec: LocatorSpec,
    ) -> dict[str, Any]:
        source = await self._get_locator_by_spec(page_id, start_locator_spec)
        target = await self._get_locator_by_spec(page_id, end_locator_spec)
        await source.drag_to(target)
        return {
            "page_id": page_id,
            "start_ref": start_locator_spec.ref,
            "end_ref": end_locator_spec.ref,
            "dragged": True,
        }

    async def upload_to_locator(
        self,
        page_id: str,
        locator_spec: LocatorSpec,
        file_path: str,
    ) -> dict[str, Any]:
        locator = await self._get_locator_by_spec(page_id, locator_spec)
        await locator.set_input_files(file_path)
        return {
            "page_id": page_id,
            "ref": locator_spec.ref,
            "file_path": str(Path(file_path).resolve()),
        }

    async def evaluate_on_locator(
        self, page_id: str, locator_spec: LocatorSpec, code: str
    ) -> dict[str, Any]:
        locator = await self._get_locator_by_spec(page_id, locator_spec)
        result = await locator.evaluate(code)
        return {
            "page_id": page_id,
            "ref": locator_spec.ref,
            "result": self._normalize_json_value(result),
        }

    async def verify_state_locator(
        self, page_id: str, locator_spec: LocatorSpec, *, state: str
    ) -> dict[str, Any]:
        locator = await self._get_locator_by_spec(page_id, locator_spec)
        normalized = state.strip().lower()
        if normalized in {"checked", "unchecked"}:
            actual = await locator.is_checked()
            expected = normalized == "checked"
        elif normalized == "disabled":
            actual = await locator.is_disabled()
            expected = True
        elif normalized == "enabled":
            actual = await locator.is_enabled()
            expected = True
        elif normalized == "editable":
            actual = await locator.is_editable()
            expected = True
        elif normalized == "visible":
            actual = await locator.is_visible()
            expected = True
        elif normalized == "hidden":
            actual = not await locator.is_visible()
            expected = True
        else:
            raise InvalidInputError(f"Unsupported verify-state value: {state}")
        return {
            "page_id": page_id,
            "ref": locator_spec.ref,
            "state": normalized,
            "passed": actual == expected,
        }

    async def verify_value_locator(
        self,
        page_id: str,
        locator_spec: LocatorSpec,
        *,
        expected: str,
    ) -> dict[str, Any]:
        locator = await self._get_locator_by_spec(page_id, locator_spec)
        actual = await locator.input_value()
        return {
            "page_id": page_id,
            "ref": locator_spec.ref,
            "expected": expected,
            "actual": actual,
            "passed": actual == expected,
        }

    async def click_ref(self, page_id: str, ref: str) -> dict[str, Any]:
        locator = await self._get_locator_by_ref(page_id, ref)
        await locator.click()
        return {"page_id": page_id, "ref": ref, "action": "click"}

    async def double_click_ref(self, page_id: str, ref: str) -> dict[str, Any]:
        locator = await self._get_locator_by_ref(page_id, ref)
        await locator.dblclick()
        return {"page_id": page_id, "ref": ref, "action": "double-click"}

    async def hover_ref(self, page_id: str, ref: str) -> dict[str, Any]:
        locator = await self._get_locator_by_ref(page_id, ref)
        await locator.hover()
        return {"page_id": page_id, "ref": ref, "action": "hover"}

    async def focus_ref(self, page_id: str, ref: str) -> dict[str, Any]:
        locator = await self._get_locator_by_ref(page_id, ref)
        await locator.focus()
        return {"page_id": page_id, "ref": ref, "action": "focus"}

    async def fill_ref(
        self, page_id: str, ref: str, text: str, *, submit: bool = False
    ) -> dict[str, Any]:
        locator = await self._get_locator_by_ref(page_id, ref)
        await locator.fill(text)
        if submit:
            await locator.press("Enter")
        return {"page_id": page_id, "ref": ref, "filled": True, "submitted": submit}

    async def fill_form(
        self, page_id: str, fields: list[dict[str, Any]], *, submit: bool = False
    ) -> dict[str, Any]:
        for field in fields:
            ref = str(field.get("ref") or "").strip()
            text = str(field.get("text") or "")
            if not ref:
                raise InvalidInputError("Each fill-form field must include a ref.")
            await self.fill_ref(page_id, ref, text, submit=False)
        if submit and fields:
            await self.press_key(page_id, "Enter")
        return {"page_id": page_id, "filled_fields": len(fields), "submitted": submit}

    async def select_option(self, page_id: str, ref: str, text: str) -> dict[str, Any]:
        locator = await self._get_locator_by_ref(page_id, ref)
        await locator.select_option(label=text)
        return {"page_id": page_id, "ref": ref, "selected": text}

    async def list_options(self, page_id: str, ref: str) -> dict[str, Any]:
        locator = await self._get_locator_by_ref(page_id, ref)
        options = await locator.locator("option").all_inner_texts()
        normalized = [item.strip() for item in options if item.strip()]
        return {"page_id": page_id, "ref": ref, "options": normalized}

    async def check_ref(self, page_id: str, ref: str) -> dict[str, Any]:
        locator = await self._get_locator_by_ref(page_id, ref)
        await locator.check()
        return {"page_id": page_id, "ref": ref, "checked": True}

    async def uncheck_ref(self, page_id: str, ref: str) -> dict[str, Any]:
        locator = await self._get_locator_by_ref(page_id, ref)
        await locator.uncheck()
        return {"page_id": page_id, "ref": ref, "checked": False}

    async def scroll_to_ref(self, page_id: str, ref: str) -> dict[str, Any]:
        locator = await self._get_locator_by_ref(page_id, ref)
        await locator.scroll_into_view_if_needed()
        return {"page_id": page_id, "ref": ref, "scrolled": True}

    async def drag_ref(self, page_id: str, start_ref: str, end_ref: str) -> dict[str, Any]:
        source = await self._get_locator_by_ref(page_id, start_ref)
        target = await self._get_locator_by_ref(page_id, end_ref)
        await source.drag_to(target)
        return {"page_id": page_id, "start_ref": start_ref, "end_ref": end_ref, "dragged": True}

    async def upload_file(self, page_id: str, ref: str, file_path: str) -> dict[str, Any]:
        locator = await self._get_locator_by_ref(page_id, ref)
        await locator.set_input_files(file_path)
        return {"page_id": page_id, "ref": ref, "file_path": str(Path(file_path).resolve())}

    async def type_text(self, page_id: str, text: str, *, submit: bool = False) -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.keyboard.type(text)
        if submit:
            await page.keyboard.press("Enter")
        return {"page_id": page_id, "typed": True, "submitted": submit}

    async def press_key(self, page_id: str, key: str) -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.keyboard.press(key)
        return {"page_id": page_id, "key": key}

    async def key_down(self, page_id: str, key: str) -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.keyboard.down(key)
        return {"page_id": page_id, "key": key}

    async def key_up(self, page_id: str, key: str) -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.keyboard.up(key)
        return {"page_id": page_id, "key": key}

    async def wheel(self, page_id: str, *, dx: int = 0, dy: int = 700) -> dict[str, Any]:
        page = self._require_page(page_id)
        before = await page.evaluate(
            """() => ({
                scrollX: window.scrollX,
                scrollY: window.scrollY
            })"""
        )
        await page.mouse.wheel(dx, dy)
        await page.wait_for_timeout(50)
        after = await page.evaluate(
            """() => ({
                scrollX: window.scrollX,
                scrollY: window.scrollY
            })"""
        )
        if (after["scrollX"], after["scrollY"]) == (before["scrollX"], before["scrollY"]) and (
            dx or dy
        ):
            after = await page.evaluate(
                """({ dx, dy }) => {
                    window.scrollBy(dx, dy);
                    return {
                        scrollX: window.scrollX,
                        scrollY: window.scrollY
                    };
                }""",
                {"dx": dx, "dy": dy},
            )
        return {
            "page_id": page_id,
            "dx": dx,
            "dy": dy,
            "scroll_x": after["scrollX"],
            "scroll_y": after["scrollY"],
        }

    async def mouse_move(self, page_id: str, *, x: int, y: int) -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.mouse.move(x, y)
        return {"page_id": page_id, "x": x, "y": y}

    async def mouse_click(
        self, page_id: str, *, x: int, y: int, button: str = "left", count: int = 1
    ) -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.mouse.click(x, y, button=button, click_count=count)
        return {"page_id": page_id, "x": x, "y": y, "button": button, "count": count}

    async def mouse_drag(
        self, page_id: str, *, x1: int, y1: int, x2: int, y2: int
    ) -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.mouse.move(x1, y1)
        await page.mouse.down()
        await page.mouse.move(x2, y2)
        await page.mouse.up()
        return {"page_id": page_id, "from": {"x": x1, "y": y1}, "to": {"x": x2, "y": y2}}

    async def mouse_down(self, page_id: str, *, button: str = "left") -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.mouse.down(button=button)
        return {"page_id": page_id, "button": button}

    async def mouse_up(self, page_id: str, *, button: str = "left") -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.mouse.up(button=button)
        return {"page_id": page_id, "button": button}

    async def evaluate(self, page_id: str, code: str) -> dict[str, Any]:
        page = self._require_page(page_id)
        result = await page.evaluate(code)
        return {"page_id": page_id, "result": self._normalize_json_value(result)}

    async def evaluate_on_ref(self, page_id: str, ref: str, code: str) -> dict[str, Any]:
        locator = await self._get_locator_by_ref(page_id, ref)
        result = await locator.evaluate(code)
        return {"page_id": page_id, "ref": ref, "result": self._normalize_json_value(result)}

    async def wait(
        self,
        page_id: str,
        *,
        seconds: float | None = None,
        text: str | None = None,
        gone: bool = False,
        exact: bool = False,
    ) -> dict[str, Any]:
        page = self._require_page(page_id)
        if text:
            locator = page.get_by_text(text, exact=exact).first
            state = "hidden" if gone else "visible"
            await locator.wait_for(state=state, timeout=((seconds or 30.0) * 1000.0))
            return {"page_id": page_id, "text": text, "state": state}
        await page.wait_for_timeout((seconds or 1.0) * 1000.0)
        return {"page_id": page_id, "seconds": seconds or 1.0}

    async def wait_for_network_idle(
        self, page_id: str, *, timeout_seconds: float = 30.0
    ) -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.wait_for_load_state("networkidle", timeout=timeout_seconds * 1000.0)
        return {"page_id": page_id, "network_idle": True}

    async def screenshot(
        self, page_id: str, *, path: str, full_page: bool = False
    ) -> dict[str, Any]:
        page = self._require_page(page_id)
        output_path = self._resolve_output_path(path)
        await page.screenshot(path=str(output_path), full_page=full_page)
        return {"page_id": page_id, "path": str(output_path), "full_page": full_page}

    async def save_pdf(self, page_id: str, *, path: str) -> dict[str, Any]:
        page = self._require_page(page_id)
        output_path = self._resolve_output_path(path)
        await page.pdf(path=str(output_path))
        return {"page_id": page_id, "path": str(output_path)}

    async def start_console_capture(self, page_id: str) -> dict[str, Any]:
        page = self._require_page(page_id)
        if page_id in self._console_handlers:
            with contextlib.suppress(Exception):
                page.remove_listener("console", self._console_handlers[page_id])
        self._console_messages[page_id] = []

        def _handle_console(message: Any) -> None:
            location = message.location or {}
            location_text = None
            if location:
                location_text = f"{location.get('url', '')}:{location.get('lineNumber', 0)}:{location.get('columnNumber', 0)}"
            self._console_messages.setdefault(page_id, []).append(
                {
                    "type": message.type,
                    "text": message.text,
                    "location": location_text,
                }
            )

        page.on("console", _handle_console)
        self._console_handlers[page_id] = _handle_console
        return {"page_id": page_id, "capturing": True}

    async def get_console_messages(
        self, page_id: str, *, message_type: str | None = None, clear: bool = True
    ) -> dict[str, Any]:
        messages = list(self._console_messages.get(page_id, []))
        if message_type:
            messages = [item for item in messages if item.get("type") == message_type]
        if clear:
            self._console_messages[page_id] = []
        return {"page_id": page_id, "messages": messages}

    async def stop_console_capture(self, page_id: str) -> dict[str, Any]:
        page = self._require_page(page_id)
        handler = self._console_handlers.pop(page_id, None)
        if handler is not None:
            with contextlib.suppress(Exception):
                page.remove_listener("console", handler)
        return {"page_id": page_id, "capturing": False}

    async def start_network_capture(self, page_id: str) -> dict[str, Any]:
        _ = self._require_page(page_id)
        observer = self._require_network_observer(page_id)
        observer.start_capture()
        return {"page_id": page_id, "capturing": True}

    async def wait_for_network_record(
        self,
        page_id: str,
        *,
        url_contains: str | None = None,
        url_regex: str | None = None,
        method: str | None = None,
        status: int | None = None,
        resource_type: str | None = None,
        mime_contains: str | None = None,
        include_static: bool = False,
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        _ = self._require_page(page_id)
        observer = self._require_network_observer(page_id)
        try:
            record = await observer.wait_for_record(
                record_filter=NetworkRecordFilter(
                    url_contains=url_contains,
                    url_regex=url_regex,
                    method=method,
                    status=status,
                    resource_type=resource_type,
                    mime_contains=mime_contains,
                    include_static=include_static,
                ),
                timeout_seconds=timeout_seconds,
            )
        except TimeoutError as exc:
            raise OperationFailedError(
                f"Timed out waiting for a matching network record after {timeout_seconds:.1f}s."
            ) from exc
        return {"page_id": page_id, "record": record}

    async def get_network_records(
        self,
        page_id: str,
        *,
        url_contains: str | None = None,
        url_regex: str | None = None,
        method: str | None = None,
        status: int | None = None,
        resource_type: str | None = None,
        mime_contains: str | None = None,
        include_static: bool = False,
        clear: bool = True,
    ) -> dict[str, Any]:
        _ = self._require_page(page_id)
        observer = self._require_network_observer(page_id)
        records = observer.get_records(
            record_filter=NetworkRecordFilter(
                url_contains=url_contains,
                url_regex=url_regex,
                method=method,
                status=status,
                resource_type=resource_type,
                mime_contains=mime_contains,
                include_static=include_static,
            ),
            clear=clear,
        )
        return {"page_id": page_id, "records": records}

    async def stop_network_capture(self, page_id: str) -> dict[str, Any]:
        _ = self._require_page(page_id)
        observer = self._require_network_observer(page_id)
        observer.stop_capture()
        return {"page_id": page_id, "capturing": False}

    async def setup_dialog_handler(
        self,
        page_id: str,
        *,
        default_action: str = "accept",
        default_prompt_text: str | None = None,
    ) -> dict[str, Any]:
        page = self._require_page(page_id)
        existing = self._dialog_handlers.pop(page_id, None)
        if existing is not None:
            with contextlib.suppress(Exception):
                page.remove_listener("dialog", existing)

        async def _handle_dialog(dialog: Any) -> None:
            if default_action == "accept":
                if dialog.type == "prompt" and default_prompt_text is not None:
                    await dialog.accept(default_prompt_text)
                else:
                    await dialog.accept()
            else:
                await dialog.dismiss()

        page.on("dialog", _handle_dialog)
        self._dialog_handlers[page_id] = _handle_dialog
        return {
            "page_id": page_id,
            "action": default_action,
            "text": default_prompt_text,
            "configured": True,
        }

    async def handle_dialog(
        self,
        page_id: str,
        *,
        accept: bool,
        prompt_text: str | None = None,
    ) -> dict[str, Any]:
        page = self._require_page(page_id)
        existing = self._dialog_handlers.pop(page_id, None)
        if existing is not None:
            with contextlib.suppress(Exception):
                page.remove_listener("dialog", existing)

        async def _handle_next_dialog(dialog: Any) -> None:
            if accept:
                if dialog.type == "prompt" and prompt_text is not None:
                    await dialog.accept(prompt_text)
                else:
                    await dialog.accept()
            else:
                await dialog.dismiss()

        page.once("dialog", _handle_next_dialog)
        return {
            "page_id": page_id,
            "accept": accept,
            "text": prompt_text,
            "armed": True,
        }

    async def remove_dialog_handler(self, page_id: str) -> dict[str, Any]:
        page = self._require_page(page_id)
        existing = self._dialog_handlers.pop(page_id, None)
        removed = existing is not None
        if existing is not None:
            with contextlib.suppress(Exception):
                page.remove_listener("dialog", existing)
        return {"page_id": page_id, "removed": removed}

    async def start_tracing(
        self,
        page_id: str,
        *,
        screenshots: bool = True,
        snapshots: bool = True,
        sources: bool = False,
    ) -> dict[str, Any]:
        _ = self._require_page(page_id)
        if self._context is None:
            raise OperationFailedError("Browser context is not available.")
        if self._tracing_active:
            raise OperationFailedError("Tracing is already active. Stop the current trace first.")
        await self._context.tracing.start(
            screenshots=screenshots,
            snapshots=snapshots,
            sources=sources,
        )
        self._tracing_active = True
        return {
            "page_id": page_id,
            "tracing": True,
            "screenshots": screenshots,
            "snapshots": snapshots,
            "sources": sources,
        }

    async def add_trace_chunk(self, page_id: str, *, title: str | None = None) -> dict[str, Any]:
        _ = self._require_page(page_id)
        if self._context is None or not self._tracing_active:
            raise OperationFailedError("No active tracing session. Start tracing first.")
        await self._context.tracing.start_chunk(title=title)
        return {"page_id": page_id, "chunk_started": True, "title": title}

    async def stop_tracing(self, page_id: str, *, path: str | None = None) -> dict[str, Any]:
        _ = self._require_page(page_id)
        saved_path = await self._stop_tracing_impl(path=path)
        return {"page_id": page_id, "path": saved_path}

    async def start_video(
        self, page_id: str, *, width: int | None = None, height: int | None = None
    ) -> dict[str, Any]:
        page = self._require_page(page_id)
        if getattr(page, "video", None) is None:
            raise OperationFailedError("No video recording is available for the active tab.")
        self._video_started.add(page_id)
        self._pending_video_save_paths.pop(page_id, None)
        return {
            "page_id": page_id,
            "recording": True,
            "width": width,
            "height": height,
        }

    async def stop_video(self, page_id: str, *, path: str | None = None) -> dict[str, Any]:
        page = self._require_page(page_id)
        if getattr(page, "video", None) is None:
            raise OperationFailedError("No video recording is available for the active tab.")
        if page_id not in self._video_started:
            raise OperationFailedError("No active video recording. Use video-start first.")
        resolved_path = self._resolve_video_output_path(path, page_id=page_id)
        self._video_started.discard(page_id)
        self._pending_video_save_paths[page_id] = str(resolved_path) if resolved_path else None
        return {
            "page_id": page_id,
            "recording": False,
            "path": str(resolved_path) if resolved_path else None,
            "deferred": True,
        }

    async def get_cookies(
        self,
        page_id: str,
        *,
        name: str | None = None,
        domain: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        _ = self._require_page(page_id)
        cookies = await self._context.cookies()
        if name:
            cookies = [cookie for cookie in cookies if cookie.get("name") == name]
        if domain:
            cookies = [cookie for cookie in cookies if domain in (cookie.get("domain") or "")]
        if path:
            cookies = [cookie for cookie in cookies if (cookie.get("path") or "").startswith(path)]
        return {"page_id": page_id, "cookies": cookies}

    async def set_cookie(
        self,
        page_id: str,
        *,
        name: str,
        value: str,
        domain: str | None = None,
        path: str = "/",
        expires: float | None = None,
        http_only: bool = False,
        secure: bool = False,
        same_site: str | None = None,
    ) -> dict[str, Any]:
        page = self._require_page(page_id)
        cookie_domain = domain or urllib.parse.urlparse(page.url).hostname
        if not cookie_domain:
            raise InvalidInputError(
                "Cookie domain is required when the current page has no hostname."
            )
        payload: dict[str, Any] = {
            "name": name,
            "value": value,
            "domain": cookie_domain,
            "path": path,
            "httpOnly": http_only,
            "secure": secure,
        }
        if expires is not None:
            payload["expires"] = expires
        if same_site:
            payload["sameSite"] = same_site
        await self._context.add_cookies([payload])
        return {"page_id": page_id, "cookie": payload}

    async def clear_cookies(
        self,
        page_id: str,
        *,
        name: str | None = None,
        domain: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        _ = self._require_page(page_id)
        await self._context.clear_cookies(name=name, domain=domain, path=path)
        return {
            "page_id": page_id,
            "cleared": True,
            "filters": {"name": name, "domain": domain, "path": path},
        }

    async def save_storage_state(self, page_id: str, *, path: str | None = None) -> dict[str, Any]:
        _ = self._require_page(page_id)
        if path:
            output_path = self._resolve_output_path(path)
        else:
            output_path = Path(tempfile.mkstemp(suffix=".json", prefix="browser-cli-state-")[1])
        await self._context.storage_state(path=str(output_path))
        return {"page_id": page_id, "path": str(output_path)}

    async def load_storage_state(self, page_id: str, *, path: str) -> dict[str, Any]:
        page = self._require_page(page_id)
        input_path = Path(path).expanduser().resolve()
        if not input_path.exists():
            raise InvalidInputError(f"Storage state file does not exist: {input_path}")
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        cookies = payload.get("cookies", [])
        if cookies:
            await self._context.add_cookies(cookies)
        for origin_payload in payload.get("origins", []):
            for entry in origin_payload.get("localStorage", []):
                name = entry.get("name")
                value = entry.get("value")
                if name is None:
                    continue
                await page.evaluate(
                    "(args) => localStorage.setItem(args.name, args.value)",
                    {"name": name, "value": value},
                )
        return {"page_id": page_id, "path": str(input_path), "cookies_loaded": len(cookies)}

    async def verify_text(
        self, page_id: str, *, text: str, exact: bool = False, timeout_seconds: float = 5.0
    ) -> dict[str, Any]:
        page = self._require_page(page_id)
        locator = page.get_by_text(text, exact=exact).first
        try:
            await locator.wait_for(state="visible", timeout=timeout_seconds * 1000.0)
            return {"page_id": page_id, "passed": True, "text": text}
        except Exception:
            return {"page_id": page_id, "passed": False, "text": text}

    async def verify_visible(
        self, page_id: str, *, role: str, name: str, timeout_seconds: float = 5.0
    ) -> dict[str, Any]:
        page = self._require_page(page_id)
        locator = page.get_by_role(role, name=name).first
        try:
            await locator.wait_for(state="visible", timeout=timeout_seconds * 1000.0)
            return {"page_id": page_id, "passed": True, "role": role, "name": name}
        except Exception:
            return {"page_id": page_id, "passed": False, "role": role, "name": name}

    async def verify_url(
        self, page_id: str, *, expected: str, exact: bool = False
    ) -> dict[str, Any]:
        page = self._require_page(page_id)
        actual = page.url
        passed = actual == expected if exact else expected in actual
        return {"page_id": page_id, "passed": passed, "expected": expected, "actual": actual}

    async def verify_title(
        self, page_id: str, *, expected: str, exact: bool = False
    ) -> dict[str, Any]:
        page = self._require_page(page_id)
        actual = await page.title()
        passed = actual == expected if exact else expected in actual
        return {"page_id": page_id, "passed": passed, "expected": expected, "actual": actual}

    async def verify_state(self, page_id: str, *, ref: str, state: str) -> dict[str, Any]:
        locator = await self._get_locator_by_ref(page_id, ref)
        state = state.lower()
        passed: bool
        if state == "visible":
            passed = await locator.is_visible()
        elif state == "hidden":
            passed = not await locator.is_visible()
        elif state == "enabled":
            passed = await locator.is_enabled()
        elif state == "disabled":
            passed = not await locator.is_enabled()
        elif state == "checked":
            passed = await locator.is_checked()
        elif state == "unchecked":
            passed = not await locator.is_checked()
        elif state == "editable":
            passed = await locator.is_editable()
        else:
            raise InvalidInputError(f"Unsupported state: {state}")
        return {"page_id": page_id, "ref": ref, "state": state, "passed": passed}

    async def verify_value(self, page_id: str, *, ref: str, expected: str) -> dict[str, Any]:
        locator = await self._get_locator_by_ref(page_id, ref)
        actual = await locator.input_value()
        return {
            "page_id": page_id,
            "ref": ref,
            "expected": expected,
            "actual": actual,
            "passed": actual == expected,
        }

    async def search(self, *, query: str, engine: str = "duckduckgo") -> dict[str, Any]:
        search_url = self._build_search_url(query, engine)
        return await self.new_tab(url=search_url, wait_until="load")

    async def _get_locator_by_ref(self, page_id: str, ref: str) -> Any:
        page = self._require_page(page_id)
        state = self._snapshot_registry.get(page_id)
        if state is None:
            raise NoSnapshotContextError()
        normalized = self._ref_resolver.parse_ref(ref)
        if normalized is None:
            raise InvalidInputError(f"Invalid ref: {ref}")
        if normalized not in state.refs:
            raise RefNotFoundError()
        locator = self._ref_resolver.get_locator(page, normalized, state.refs)
        if locator is None:
            raise RefNotFoundError()
        count = await locator.count()
        if count == 0:
            raise StaleSnapshotError()
        if count > 1:
            raise AmbiguousRefError()
        return locator.first

    async def _get_locator_by_spec(self, page_id: str, locator_spec: LocatorSpec) -> Any:
        page = self._require_page(page_id)
        locator = self._ref_resolver.get_locator_from_spec(page, locator_spec)
        if locator is None:
            raise RefNotFoundError()
        count = await locator.count()
        if count == 0:
            raise StaleSnapshotError()
        if count > 1:
            raise AmbiguousRefError()
        return locator.first

    async def _remove_page_handlers(self, page_id: str) -> None:
        page = self._pages.get(page_id)
        self._console_messages.pop(page_id, None)
        console_handler = self._console_handlers.pop(page_id, None)
        if page is not None and console_handler is not None:
            with contextlib.suppress(Exception):
                page.remove_listener("console", console_handler)
        network_observer = self._network_observers.pop(page_id, None)
        if network_observer is not None:
            await network_observer.close()
        dialog_handler = self._dialog_handlers.pop(page_id, None)
        if page is not None and dialog_handler is not None:
            with contextlib.suppress(Exception):
                page.remove_listener("dialog", dialog_handler)
        self._video_started.discard(page_id)
        self._pending_video_save_paths.pop(page_id, None)

    def _require_page(self, page_id: str) -> Any:
        page = self._pages.get(page_id)
        if page is None:
            raise OperationFailedError(f"Page {page_id} is not available anymore.")
        return page

    def _require_network_observer(self, page_id: str) -> PlaywrightNetworkObserver:
        observer = self._network_observers.get(page_id)
        if observer is None:
            raise OperationFailedError(f"Network capture is not available for page {page_id}.")
        return observer

    def _next_page_id(self) -> str:
        self._page_counter += 1
        return f"page_{self._page_counter:04d}"

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

    def _count_open_context_pages(self) -> int:
        if self._context is None:
            return 0
        return sum(1 for page in self._context.pages if not page.is_closed())

    async def _ensure_reusable_page_before_last_close(self, page: Any) -> None:
        if self._context is None or page.is_closed() or self._count_open_context_pages() > 1:
            return
        replacement = await self._context.new_page()
        if self._is_reusable_startup_page(replacement):
            self._reusable_startup_pages.append(replacement)

    @staticmethod
    async def _capture_html_from_page(page: Any) -> str:
        return await page.evaluate(
            """() => {
                const doctype = document.doctype
                    ? `<!DOCTYPE ${document.doctype.name}>`
                    : '';
                return `${doctype}${document.documentElement.outerHTML}`;
            }"""
        )

    async def _settle_page(self, page: Any) -> None:
        await page.wait_for_timeout(self.READ_SETTLE_TIMEOUT_MS)

    async def _scroll_page_to_bottom(self, page: Any) -> None:
        stable_rounds = 0
        previous_height = -1
        for _ in range(self.READ_SCROLL_MAX_ROUNDS):
            current_height = await page.evaluate(
                "() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
            )
            await page.evaluate(
                "() => window.scrollTo({ top: document.body.scrollHeight, behavior: 'instant' })"
            )
            await page.wait_for_timeout(self.READ_SCROLL_PAUSE_MS)
            next_height = await page.evaluate(
                "() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
            )
            if next_height == current_height == previous_height:
                stable_rounds += 1
            else:
                stable_rounds = 0
            previous_height = next_height
            if stable_rounds >= self.READ_SCROLL_STABLE_ROUNDS - 1:
                break

    @staticmethod
    def _normalize_json_value(value: Any) -> Any:
        if value is None or isinstance(value, bool | int | float | str):
            return value
        if isinstance(value, list):
            return [BrowserService._normalize_json_value(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): BrowserService._normalize_json_value(item) for key, item in value.items()
            }
        return str(value)

    @staticmethod
    def _normalize_url(url: str) -> str:
        lowered = url.lower()
        if "://" in url or lowered.startswith(("data:", "about:")):
            return url
        return f"https://{url}"

    @staticmethod
    def _build_search_url(query: str, engine: str) -> str:
        encoded = urllib.parse.quote_plus(query)
        template = os.environ.get("BROWSER_CLI_SEARCH_URL_TEMPLATE")
        if template:
            return template.format(query=encoded, raw_query=query, engine=engine)
        if engine == "google":
            return f"https://www.google.com/search?q={encoded}&udm=14"
        if engine == "bing":
            return f"https://www.bing.com/search?q={encoded}"
        return f"https://duckduckgo.com/?q={encoded}"

    @staticmethod
    def _resolve_output_path(path: str) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = (get_app_paths().artifacts_dir / candidate).resolve()
        candidate.parent.mkdir(parents=True, exist_ok=True)
        return candidate

    async def _close_page(self, page_id: str) -> dict[str, Any]:
        page = self._require_page(page_id)
        video = getattr(page, "video", None)
        sentinel = object()
        pending = self._pending_video_save_paths.pop(page_id, sentinel)
        has_pending = pending is not sentinel
        video_requested = page_id in self._video_started or has_pending
        self._video_started.discard(page_id)
        async with self._page_create_lock:
            await self._ensure_reusable_page_before_last_close(page)
            await self._remove_page_handlers(page_id)
            await page.close()
        self._pages.pop(page_id, None)
        self._snapshot_registry.clear_page(page_id)
        result: dict[str, Any] = {"page_id": page_id, "closed": True}
        if video is not None and video_requested:
            result["video_path"] = await self._save_video_artifact(
                video,
                None if pending is sentinel else pending,
            )
        return result

    async def _stop_tracing_impl(self, *, path: str | None) -> str:
        if self._context is None or not self._tracing_active:
            raise OperationFailedError("No active tracing session. Start tracing first.")
        if path:
            output_path = self._resolve_output_path(path)
            if output_path.suffix.lower() != ".zip":
                output_path = output_path.with_suffix(".zip")
        else:
            artifacts_dir = get_app_paths().artifacts_dir
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            fd, raw_path = tempfile.mkstemp(
                suffix=".zip",
                prefix="browser-cli-trace-",
                dir=str(artifacts_dir),
            )
            os.close(fd)
            output_path = Path(raw_path)
        await self._context.tracing.stop(path=str(output_path))
        self._tracing_active = False
        return str(output_path)

    async def _save_video_artifact(self, video: Any, requested_path: str | None) -> str:
        if requested_path:
            output_path = Path(requested_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            await video.save_as(str(output_path))
            return str(output_path)
        raw_path = await video.path()
        return str(Path(str(raw_path)).resolve())

    @staticmethod
    def _resolve_video_output_path(path: str | None, *, page_id: str) -> Path | None:
        if not path:
            return None
        raw = Path(path).expanduser()
        if path.endswith(os.sep) or path.endswith("/") or raw.is_dir():
            base_dir = raw if raw.is_absolute() else (get_app_paths().artifacts_dir / raw)
            base_dir.mkdir(parents=True, exist_ok=True)
            return (base_dir / f"{page_id}.webm").resolve()
        if not raw.is_absolute():
            raw = (get_app_paths().artifacts_dir / raw).resolve()
        if raw.suffix.lower() != ".webm":
            raw = raw.with_suffix(".webm")
        raw.parent.mkdir(parents=True, exist_ok=True)
        return raw

    @staticmethod
    def _raise_launch_error(exc: Exception) -> None:
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

    def _semantic_snapshot_from_capture(
        self,
        page_id: str,
        snapshot: SnapshotCapture,
        *,
        interactive: bool,
        full_page: bool,
    ) -> SemanticSnapshot:
        page = self._require_page(page_id)
        captured_at = time.time()
        metadata = SnapshotMetadata(
            snapshot_id=snapshot.snapshot_id,
            page_id=page_id,
            captured_url=str(page.url),
            captured_at=captured_at,
            interactive=interactive,
            full_page=full_page,
        )
        refs = {
            ref: RefData(
                ref=str(ref),
                role=str(data.get("role") or ""),
                name=str(data["name"]) if data.get("name") is not None else None,
                nth=int(data["nth"]) if data.get("nth") is not None else None,
                text_content=str(data["text_content"])
                if data.get("text_content") is not None
                else None,
                tag=str(data["tag"]) if data.get("tag") is not None else None,
                interactive=bool(data.get("interactive")),
                parent_ref=str(data["parent_ref"]) if data.get("parent_ref") is not None else None,
                frame_path=tuple(int(item) for item in (data.get("frame_path") or [])),
                playwright_ref=str(data["playwright_ref"])
                if data.get("playwright_ref") is not None
                else None,
                selector_recipe=str(data["selector_recipe"])
                if data.get("selector_recipe") is not None
                else None,
                snapshot_id=snapshot.snapshot_id,
                page_id=page_id,
                captured_url=str(page.url),
                captured_at=captured_at,
            )
            for ref, data in snapshot.refs.items()
        }
        return SemanticSnapshot(tree=snapshot.tree, refs=refs, metadata=metadata)
