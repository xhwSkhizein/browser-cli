"""Long-lived browser service owned by the daemon."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any

from browser_cli.browser.models import BrowserLaunchConfig
from browser_cli.browser.snapshot import SnapshotCapture, capture_snapshot
from browser_cli.browser.stealth import STEALTH_INIT_SCRIPT, build_launch_args
from browser_cli.constants import get_app_paths
from browser_cli.errors import (
    AmbiguousRefError,
    BrowserUnavailableError,
    InvalidInputError,
    NoSnapshotContextError,
    OperationFailedError,
    ProfileUnavailableError,
    RefNotFoundError,
    StaleSnapshotError,
    TemporaryReadError,
)
from browser_cli.profiles.discovery import ChromeEnvironment, discover_chrome_environment
from browser_cli.refs import SemanticRefResolver, SnapshotRegistry
from browser_cli.refs.models import RefData, SemanticSnapshot, SnapshotMetadata


class BrowserService:
    def __init__(
        self,
        chrome_environment: ChromeEnvironment | None = None,
        *,
        headless: bool = True,
    ) -> None:
        self._chrome_environment = chrome_environment
        self._headless = headless
        self._playwright: Any | None = None
        self._context: Any | None = None
        self._pages: dict[str, Any] = {}
        self._page_counter = 0
        self._snapshot_registry = SnapshotRegistry()
        self._ref_resolver = SemanticRefResolver()
        self._console_messages: dict[str, list[dict[str, Any]]] = {}
        self._console_handlers: dict[str, Any] = {}
        self._network_requests: dict[str, list[dict[str, Any]]] = {}
        self._network_handlers: dict[str, Any] = {}
        self._dialog_handlers: dict[str, Any] = {}
        self._tracing_active = False
        self._video_started: set[str] = set()
        self._pending_video_save_paths: dict[str, str | None] = {}
        self._start_lock = asyncio.Lock()
        self._page_create_lock = asyncio.Lock()

    @property
    def chrome_environment(self) -> ChromeEnvironment | None:
        return self._chrome_environment

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
            self._context = await chromium.launch_persistent_context(
                user_data_dir=str(launch_config.user_data_dir),
                executable_path=str(launch_config.executable_path) if launch_config.executable_path else None,
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
                ignore_default_args=["--enable-automation"],
                args=[*build_launch_args(), f"--profile-directory={launch_config.profile_directory}"],
            )
            await self._context.add_init_script(STEALTH_INIT_SCRIPT)
            for page in list(self._context.pages):
                await page.close()
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
        self._network_requests.clear()
        self._network_handlers.clear()
        self._dialog_handlers.clear()
        self._video_started.clear()
        self._pending_video_save_paths.clear()
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
        url: str | None = None,
        wait_until: str = "load",
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        await self.ensure_started()
        async with self._page_create_lock:
            page = await self._context.new_page()
            page_id = self._next_page_id()
            self._pages[page_id] = page
            if url:
                await page.goto(
                    self._normalize_url(url),
                    wait_until=wait_until,
                    timeout=(timeout_seconds or 30.0) * 1000.0,
                )
            return await self.get_page_summary(page_id)

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
        html = await page.evaluate(
            """() => {
                const doctype = document.doctype
                    ? `<!DOCTYPE ${document.doctype.name}>`
                    : '';
                return `${doctype}${document.documentElement.outerHTML}`;
            }"""
        )
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
        snapshot = await capture_snapshot(page, page_id=page_id, interactive=interactive, full_page=full_page)
        semantic_snapshot = self._semantic_snapshot_from_capture(page_id, snapshot, interactive=interactive, full_page=full_page)
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

    async def navigate(self, page_id: str, url: str, *, wait_until: str = "load", timeout_seconds: float = 30.0) -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.goto(self._normalize_url(url), wait_until=wait_until, timeout=timeout_seconds * 1000.0)
        return await self.get_page_summary(page_id)

    async def reload(self, page_id: str, *, wait_until: str = "load", timeout_seconds: float = 30.0) -> dict[str, Any]:
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

    async def fill_ref(self, page_id: str, ref: str, text: str, *, submit: bool = False) -> dict[str, Any]:
        locator = await self._get_locator_by_ref(page_id, ref)
        await locator.fill(text)
        if submit:
            await locator.press("Enter")
        return {"page_id": page_id, "ref": ref, "filled": True, "submitted": submit}

    async def fill_form(self, page_id: str, fields: list[dict[str, Any]], *, submit: bool = False) -> dict[str, Any]:
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
        await page.mouse.wheel(dx, dy)
        return {"page_id": page_id, "dx": dx, "dy": dy}

    async def mouse_move(self, page_id: str, *, x: int, y: int) -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.mouse.move(x, y)
        return {"page_id": page_id, "x": x, "y": y}

    async def mouse_click(self, page_id: str, *, x: int, y: int, button: str = "left", count: int = 1) -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.mouse.click(x, y, button=button, click_count=count)
        return {"page_id": page_id, "x": x, "y": y, "button": button, "count": count}

    async def mouse_drag(self, page_id: str, *, x1: int, y1: int, x2: int, y2: int) -> dict[str, Any]:
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

    async def wait_for_network_idle(self, page_id: str, *, timeout_seconds: float = 30.0) -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.wait_for_load_state("networkidle", timeout=timeout_seconds * 1000.0)
        return {"page_id": page_id, "network_idle": True}

    async def screenshot(self, page_id: str, *, path: str, full_page: bool = False) -> dict[str, Any]:
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
            try:
                page.remove_listener("console", self._console_handlers[page_id])
            except Exception:
                pass
        self._console_messages[page_id] = []

        def _handle_console(message: Any) -> None:
            location = message.location or {}
            location_text = None
            if location:
                location_text = (
                    f"{location.get('url', '')}:{location.get('lineNumber', 0)}:{location.get('columnNumber', 0)}"
                )
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

    async def get_console_messages(self, page_id: str, *, message_type: str | None = None, clear: bool = True) -> dict[str, Any]:
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
            try:
                page.remove_listener("console", handler)
            except Exception:
                pass
        return {"page_id": page_id, "capturing": False}

    async def start_network_capture(self, page_id: str) -> dict[str, Any]:
        page = self._require_page(page_id)
        if page_id in self._network_handlers:
            try:
                page.remove_listener("request", self._network_handlers[page_id])
            except Exception:
                pass
        self._network_requests[page_id] = []

        def _handle_request(request: Any) -> None:
            self._network_requests.setdefault(page_id, []).append(
                {
                    "url": request.url,
                    "method": request.method,
                    "resource_type": request.resource_type,
                    "headers": dict(request.headers) if request.headers else {},
                    "post_data": request.post_data,
                }
            )

        page.on("request", _handle_request)
        self._network_handlers[page_id] = _handle_request
        return {"page_id": page_id, "capturing": True}

    async def get_network_requests(self, page_id: str, *, include_static: bool = False, clear: bool = True) -> dict[str, Any]:
        requests = list(self._network_requests.get(page_id, []))
        if not include_static:
            static_types = {"image", "stylesheet", "script", "font", "media"}
            requests = [item for item in requests if item.get("resource_type") not in static_types]
        if clear:
            self._network_requests[page_id] = []
        return {"page_id": page_id, "requests": requests}

    async def stop_network_capture(self, page_id: str) -> dict[str, Any]:
        page = self._require_page(page_id)
        handler = self._network_handlers.pop(page_id, None)
        if handler is not None:
            try:
                page.remove_listener("request", handler)
            except Exception:
                pass
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
            try:
                page.remove_listener("dialog", existing)
            except Exception:
                pass

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
            try:
                page.remove_listener("dialog", existing)
            except Exception:
                pass

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
            try:
                page.remove_listener("dialog", existing)
            except Exception:
                pass
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

    async def start_video(self, page_id: str, *, width: int | None = None, height: int | None = None) -> dict[str, Any]:
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
            raise InvalidInputError("Cookie domain is required when the current page has no hostname.")
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
        return {"page_id": page_id, "cleared": True, "filters": {"name": name, "domain": domain, "path": path}}

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

    async def verify_text(self, page_id: str, *, text: str, exact: bool = False, timeout_seconds: float = 5.0) -> dict[str, Any]:
        page = self._require_page(page_id)
        locator = page.get_by_text(text, exact=exact).first
        try:
            await locator.wait_for(state="visible", timeout=timeout_seconds * 1000.0)
            return {"page_id": page_id, "passed": True, "text": text}
        except Exception:
            return {"page_id": page_id, "passed": False, "text": text}

    async def verify_visible(self, page_id: str, *, role: str, name: str, timeout_seconds: float = 5.0) -> dict[str, Any]:
        page = self._require_page(page_id)
        locator = page.get_by_role(role, name=name).first
        try:
            await locator.wait_for(state="visible", timeout=timeout_seconds * 1000.0)
            return {"page_id": page_id, "passed": True, "role": role, "name": name}
        except Exception:
            return {"page_id": page_id, "passed": False, "role": role, "name": name}

    async def verify_url(self, page_id: str, *, expected: str, exact: bool = False) -> dict[str, Any]:
        page = self._require_page(page_id)
        actual = page.url
        passed = actual == expected if exact else expected in actual
        return {"page_id": page_id, "passed": passed, "expected": expected, "actual": actual}

    async def verify_title(self, page_id: str, *, expected: str, exact: bool = False) -> dict[str, Any]:
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
        return {"page_id": page_id, "ref": ref, "expected": expected, "actual": actual, "passed": actual == expected}

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

    def _remove_page_handlers(self, page_id: str) -> None:
        page = self._pages.get(page_id)
        self._console_messages.pop(page_id, None)
        console_handler = self._console_handlers.pop(page_id, None)
        if page is not None and console_handler is not None:
            try:
                page.remove_listener("console", console_handler)
            except Exception:
                pass
        self._network_requests.pop(page_id, None)
        network_handler = self._network_handlers.pop(page_id, None)
        if page is not None and network_handler is not None:
            try:
                page.remove_listener("request", network_handler)
            except Exception:
                pass
        dialog_handler = self._dialog_handlers.pop(page_id, None)
        if page is not None and dialog_handler is not None:
            try:
                page.remove_listener("dialog", dialog_handler)
            except Exception:
                pass
        self._video_started.discard(page_id)
        self._pending_video_save_paths.pop(page_id, None)

    def _require_page(self, page_id: str) -> Any:
        page = self._pages.get(page_id)
        if page is None:
            raise OperationFailedError(f"Page {page_id} is not available anymore.")
        return page

    def _next_page_id(self) -> str:
        self._page_counter += 1
        return f"page_{self._page_counter:04d}"

    @staticmethod
    def _normalize_json_value(value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, list):
            return [BrowserService._normalize_json_value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): BrowserService._normalize_json_value(item) for key, item in value.items()}
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
        self._remove_page_handlers(page_id)
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
        if "singleton" in lowered or "profile" in lowered or "user data directory is already in use" in lowered:
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
                text_content=str(data["text_content"]) if data.get("text_content") is not None else None,
                tag=str(data["tag"]) if data.get("tag") is not None else None,
                interactive=bool(data.get("interactive")),
                parent_ref=str(data["parent_ref"]) if data.get("parent_ref") is not None else None,
                frame_path=tuple(int(item) for item in (data.get("frame_path") or [])),
                playwright_ref=str(data["playwright_ref"]) if data.get("playwright_ref") is not None else None,
                selector_recipe=str(data["selector_recipe"]) if data.get("selector_recipe") is not None else None,
                snapshot_id=snapshot.snapshot_id,
                page_id=page_id,
                captured_url=str(page.url),
                captured_at=captured_at,
            )
            for ref, data in snapshot.refs.items()
        }
        return SemanticSnapshot(tree=snapshot.tree, refs=refs, metadata=metadata)
