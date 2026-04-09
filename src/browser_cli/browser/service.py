"""Long-lived browser service owned by the daemon."""

from __future__ import annotations

import asyncio
import json
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any

from browser_cli.browser.models import BrowserLaunchConfig
from browser_cli.browser.snapshot import SnapshotCapture, capture_snapshot
from browser_cli.browser.stealth import STEALTH_INIT_SCRIPT, build_launch_args
from browser_cli.constants import get_app_paths
from browser_cli.errors import (
    BrowserUnavailableError,
    InvalidInputError,
    OperationFailedError,
    ProfileUnavailableError,
    RefNotFoundError,
    StaleSnapshotError,
    TemporaryReadError,
)
from browser_cli.profiles.discovery import ChromeEnvironment, discover_chrome_environment


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
        self._snapshot_refs_by_page: dict[str, set[str]] = {}
        self._console_messages: dict[str, list[dict[str, Any]]] = {}
        self._console_handlers: dict[str, Any] = {}
        self._network_requests: dict[str, list[dict[str, Any]]] = {}
        self._network_handlers: dict[str, Any] = {}
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
            self._context = await chromium.launch_persistent_context(
                user_data_dir=str(launch_config.user_data_dir),
                executable_path=str(launch_config.executable_path) if launch_config.executable_path else None,
                headless=launch_config.headless,
                viewport={
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

    async def stop(self) -> None:
        pages = list(self._pages.values())
        for page in pages:
            try:
                await page.close()
            except Exception:
                pass
        self._pages.clear()
        self._snapshot_refs_by_page.clear()
        self._console_messages.clear()
        self._console_handlers.clear()
        self._network_requests.clear()
        self._network_handlers.clear()
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

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
            self._snapshot_refs_by_page[page_id] = set()
            if url:
                await page.goto(
                    self._normalize_url(url),
                    wait_until=wait_until,
                    timeout=(timeout_seconds or 30.0) * 1000.0,
                )
            return await self.get_page_summary(page_id)

    async def close_tab(self, page_id: str) -> dict[str, Any]:
        page = self._require_page(page_id)
        await page.close()
        self._pages.pop(page_id, None)
        self._snapshot_refs_by_page.pop(page_id, None)
        self._remove_page_handlers(page_id)
        return {"page_id": page_id, "closed": True}

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
                const clone = document.documentElement.cloneNode(true);
                for (const node of clone.querySelectorAll('[data-browser-cli-ref]')) {
                    node.removeAttribute('data-browser-cli-ref');
                }
                const doctype = document.doctype
                    ? `<!DOCTYPE ${document.doctype.name}>`
                    : '';
                return `${doctype}${clone.outerHTML}`;
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
        snapshot = await capture_snapshot(page, interactive=interactive, full_page=full_page)
        refs = set(snapshot.refs.keys())
        self._snapshot_refs_by_page[page_id] = refs
        return {
            "page_id": page_id,
            "tree": snapshot.tree,
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
        normalized = ref.strip().removeprefix("@").removeprefix("ref=")
        locator = page.locator(f'[data-browser-cli-ref="{normalized}"]')
        count = await locator.count()
        if count == 0:
            known_refs = self._snapshot_refs_by_page.get(page_id, set())
            if normalized in known_refs:
                raise StaleSnapshotError()
            raise RefNotFoundError()
        return locator.first

    def _remove_page_handlers(self, page_id: str) -> None:
        self._console_messages.pop(page_id, None)
        self._console_handlers.pop(page_id, None)
        self._network_requests.pop(page_id, None)
        self._network_handlers.pop(page_id, None)

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

    @staticmethod
    def _raise_launch_error(exc: Exception) -> None:
        message = str(exc)
        lowered = message.lower()
        if "singleton" in lowered or "profile" in lowered or "user data directory is already in use" in lowered:
            raise ProfileUnavailableError(message) from exc
        if "executable" in lowered or "browser" in lowered or "failed to launch" in lowered:
            raise BrowserUnavailableError(message) from exc
        raise TemporaryReadError(message) from exc
