"""Driver-managing browser service used by the daemon."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from browser_cli.drivers.base import BrowserDriver
from browser_cli.drivers.extension_driver import ExtensionDriver
from browser_cli.drivers.playwright_driver import PlaywrightDriver
from browser_cli.errors import (
    EmptyContentError,
    InvalidInputError,
    NoSnapshotContextError,
    OperationFailedError,
    RefNotFoundError,
)
from browser_cli.extension import ExtensionHub
from browser_cli.profiles.discovery import ChromeEnvironment
from browser_cli.refs import SemanticRefResolver, SemanticSnapshotGenerator, SnapshotRegistry
from browser_cli.tabs import TabRegistry
from browser_cli.tabs.registry import TabRecord

logger = logging.getLogger(__name__)


class BrowserService:
    INITIAL_EXTENSION_WAIT_SECONDS = 3.0
    READ_NAVIGATION_TIMEOUT_SECONDS = 30.0
    READ_SETTLE_TIMEOUT_MS = 1_200
    READ_SCROLL_PAUSE_MS = 450
    READ_SCROLL_MAX_ROUNDS = 8
    READ_SCROLL_STABLE_ROUNDS = 2

    def __init__(
        self,
        tabs: TabRegistry | None = None,
        chrome_environment: ChromeEnvironment | None = None,
        *,
        headless: bool | None = None,
    ) -> None:
        self._tabs = tabs or TabRegistry()
        self._playwright = PlaywrightDriver(
            chrome_environment=chrome_environment, headless=headless
        )
        self._extension_hub = ExtensionHub()
        self._extension = ExtensionDriver(self._extension_hub)
        self._snapshot_registry = SnapshotRegistry()
        self._ref_resolver = SemanticRefResolver()
        self._snapshot_generator = SemanticSnapshotGenerator()
        self._driver_name: str | None = None
        self._driver: BrowserDriver | None = None
        self._watch_task: asyncio.Task[None] | None = None
        self._command_depth = 0
        self._pending_driver: str | None = None
        self._pending_reason: str | None = None
        self._last_runtime_meta: dict[str, Any] = {}
        self._page_counter = 0
        self._rebind_lock = asyncio.Lock()

    @property
    def chrome_environment(self) -> ChromeEnvironment | None:
        if self._driver_name == "playwright":
            return self._playwright.chrome_environment
        return None

    def configure_environment(self, chrome_environment: ChromeEnvironment) -> None:
        self._playwright.configure_environment(chrome_environment)

    async def ensure_extension_listener_started(self) -> None:
        await self._extension_hub.ensure_started()

    async def begin_command(self, action: str) -> None:
        await self.ensure_started()
        if self._driver_name == "extension":
            session = self._extension_hub.session
            if session is None or not session.hello.has_required_capabilities():
                logger.warning(
                    "Extension unavailable at command start; rebinding to playwright for action=%s",
                    action,
                )
                await self._activate_driver("playwright", reason="extension-disconnected-command")
        await self._maybe_apply_pending_rebind()
        self._command_depth += 1
        self._last_runtime_meta = {"driver": self.active_driver_name, "command": action}

    async def end_command(self) -> dict[str, Any]:
        self._command_depth = max(0, self._command_depth - 1)
        if self._command_depth == 0:
            await self._maybe_apply_pending_rebind()
        meta = dict(self._last_runtime_meta)
        self._last_runtime_meta = {}
        return meta

    @property
    def active_driver_name(self) -> str:
        return self._driver_name or "playwright"

    async def ensure_started(self) -> None:
        await self._extension_hub.ensure_started()
        if self._watch_task is None:
            self._watch_task = asyncio.create_task(self._watch_extension_changes())
        if self._driver is not None:
            return
        session = None
        try:
            session = await self._extension_hub.wait_for_session(
                self.INITIAL_EXTENSION_WAIT_SECONDS
            )
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            logger.info(
                "Extension did not connect within %.1fs; falling back to playwright",
                self.INITIAL_EXTENSION_WAIT_SECONDS,
            )
        except Exception:
            logger.warning(
                "Extension startup wait failed; falling back to playwright",
                exc_info=True,
            )
        target = (
            "extension" if session and session.hello.has_required_capabilities() else "playwright"
        )
        logger.info("Selecting startup driver=%s", target)
        await self._activate_driver(target, reason="startup")

    async def stop(self) -> dict[str, Any]:
        if self._watch_task is not None:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            self._watch_task = None
        shutdown: dict[str, Any] = {}
        cleanup_error: str | None = None
        try:
            if self._driver_name == "extension":
                shutdown = await self._extension.stop()
            elif self._driver_name == "playwright":
                shutdown = await self._playwright.stop()
            else:
                shutdown = {}
        except Exception as exc:
            cleanup_error = str(exc)
            logger.warning(
                "Driver stop failed for %s: %s", self._driver_name or "none", cleanup_error
            )
            shutdown = {}
        await self._extension_hub.stop()
        with contextlib.suppress(Exception):
            await self._playwright.stop()
        self._driver = None
        self._driver_name = None
        self._snapshot_registry.clear()
        if cleanup_error:
            shutdown["cleanup_error"] = cleanup_error
        return shutdown

    async def runtime_status(self, *, warmup: bool = False) -> dict[str, Any]:
        if warmup:
            await self.ensure_started()
        extension_health = await self._extension.health()
        playwright_health = await self._playwright.health()
        extension_details = dict(extension_health.details)
        playwright_details = dict(playwright_health.details)
        workspace_window_state = dict(extension_details.get("workspace_window_state") or {})
        profile_source: str | None = None
        profile_dir: str | None = None
        profile_directory: str | None = None
        if self._driver_name == "extension":
            profile_source = "extension"
        else:
            environment = self._playwright.chrome_environment
            if environment is not None:
                profile_source = environment.source
                profile_dir = str(environment.user_data_dir)
                profile_directory = environment.profile_directory
        return {
            "browser_started": self._driver is not None,
            "active_driver": self._driver_name,
            "profile_source": profile_source,
            "profile_dir": profile_dir,
            "profile_directory": profile_directory,
            "playwright": {
                "available": playwright_health.available,
                "details": playwright_details,
            },
            "extension": {
                "available": extension_health.available,
                "connected": bool(extension_details.get("connected")),
                "capability_complete": bool(extension_details.get("capability_complete")),
                "missing_capabilities": list(extension_details.get("missing_capabilities") or []),
                "details": extension_details,
            },
            "workspace_window_state": workspace_window_state,
            "pending_rebind": (
                {
                    "target": self._pending_driver,
                    "reason": self._pending_reason,
                }
                if self._pending_driver
                else (
                    {
                        "target": "playwright",
                        "reason": "extension-disconnected-waiting-command",
                    }
                    if self._driver_name == "extension"
                    and not bool(extension_details.get("connected"))
                    else None
                )
            ),
        }

    async def new_tab(
        self,
        *,
        url: str | None = None,
        wait_until: str = "load",
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        page_id = self._next_page_id()
        return await self._active_driver().new_tab(
            page_id=page_id,
            url=url,
            wait_until=wait_until,
            timeout_seconds=timeout_seconds,
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
        page = await self.new_tab(
            url=url, wait_until="load", timeout_seconds=self.READ_NAVIGATION_TIMEOUT_SECONDS
        )
        page_id = str(page["page_id"])
        try:
            await self.wait(page_id, seconds=self.READ_SETTLE_TIMEOUT_MS / 1000.0)
            if scroll_bottom:
                await self._scroll_page_to_bottom(page_id)
                await self.wait(page_id, seconds=self.READ_SETTLE_TIMEOUT_MS / 1000.0)
            if output_mode == "snapshot":
                body = str(
                    (await self.capture_snapshot(page_id, interactive=False, full_page=True))[
                        "tree"
                    ]
                )
            else:
                body = str((await self.capture_html(page_id))["html"])
            if not body.strip():
                raise EmptyContentError()
            return {
                "page_id": page_id,
                "body": body,
                "output_mode": output_mode,
                "url": str(page["url"]),
            }
        finally:
            with contextlib.suppress(Exception):
                await self.close_tab(page_id)

    async def close_tab(self, page_id: str) -> dict[str, Any]:
        self._snapshot_registry.clear_page(page_id)
        return await self._active_driver().close_tab(page_id)

    async def get_page_summary(self, page_id: str) -> dict[str, Any]:
        return await self._active_driver().get_page_summary(page_id)

    async def get_page_info(self, page_id: str) -> dict[str, Any]:
        return await self._active_driver().get_page_info(page_id)

    async def capture_html(self, page_id: str) -> dict[str, Any]:
        return await self._active_driver().capture_html(page_id)

    async def capture_snapshot(
        self,
        page_id: str,
        *,
        interactive: bool = False,
        full_page: bool = True,
    ) -> dict[str, Any]:
        snapshot_input = await self._active_driver().capture_snapshot_input(
            page_id,
            interactive=interactive,
            full_page=full_page,
        )
        semantic_snapshot = self._snapshot_generator.snapshot_from_raw_text(
            snapshot_input.raw_snapshot,
            page_id=page_id,
            captured_url=snapshot_input.captured_url,
            interactive=interactive,
            full_page=full_page,
            captured_at=snapshot_input.captured_at,
        )
        state = self._snapshot_registry.store(semantic_snapshot)
        return {
            "page_id": page_id,
            "tree": semantic_snapshot.tree,
            "snapshot_id": semantic_snapshot.metadata.snapshot_id,
            "captured_url": state.captured_url,
            "captured_at": state.captured_at,
            "refs_summary": [
                {
                    "ref": ref,
                    **data.to_summary(),
                }
                for ref, data in semantic_snapshot.refs.items()
            ],
        }

    async def navigate(
        self, page_id: str, url: str, *, wait_until: str = "load", timeout_seconds: float = 30.0
    ) -> dict[str, Any]:
        self._snapshot_registry.clear_page(page_id)
        return await self._active_driver().navigate(
            page_id, url, wait_until=wait_until, timeout_seconds=timeout_seconds
        )

    async def reload(
        self, page_id: str, *, wait_until: str = "load", timeout_seconds: float = 30.0
    ) -> dict[str, Any]:
        self._snapshot_registry.clear_page(page_id)
        return await self._active_driver().reload(
            page_id, wait_until=wait_until, timeout_seconds=timeout_seconds
        )

    async def go_back(self, page_id: str) -> dict[str, Any]:
        self._snapshot_registry.clear_page(page_id)
        return await self._active_driver().go_back(page_id)

    async def go_forward(self, page_id: str) -> dict[str, Any]:
        self._snapshot_registry.clear_page(page_id)
        return await self._active_driver().go_forward(page_id)

    async def resize(self, page_id: str, *, width: int, height: int) -> dict[str, Any]:
        return await self._active_driver().resize(page_id, width=width, height=height)

    async def click_ref(self, page_id: str, ref: str) -> dict[str, Any]:
        return await self._active_driver().click(page_id, await self._require_locator(page_id, ref))

    async def double_click_ref(self, page_id: str, ref: str) -> dict[str, Any]:
        return await self._active_driver().double_click(
            page_id, await self._require_locator(page_id, ref)
        )

    async def hover_ref(self, page_id: str, ref: str) -> dict[str, Any]:
        return await self._active_driver().hover(page_id, await self._require_locator(page_id, ref))

    async def focus_ref(self, page_id: str, ref: str) -> dict[str, Any]:
        return await self._active_driver().focus(page_id, await self._require_locator(page_id, ref))

    async def fill_ref(
        self, page_id: str, ref: str, text: str, *, submit: bool = False
    ) -> dict[str, Any]:
        return await self._active_driver().fill(
            page_id, await self._require_locator(page_id, ref), text, submit=submit
        )

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
            await self._active_driver().press_key(page_id, "Enter")
        return {"page_id": page_id, "filled_fields": len(fields), "submitted": submit}

    async def select_option(self, page_id: str, ref: str, text: str) -> dict[str, Any]:
        return await self._active_driver().select_option(
            page_id, await self._require_locator(page_id, ref), text
        )

    async def list_options(self, page_id: str, ref: str) -> dict[str, Any]:
        return await self._active_driver().list_options(
            page_id, await self._require_locator(page_id, ref)
        )

    async def check_ref(self, page_id: str, ref: str) -> dict[str, Any]:
        return await self._active_driver().check(
            page_id, await self._require_locator(page_id, ref), checked=True
        )

    async def uncheck_ref(self, page_id: str, ref: str) -> dict[str, Any]:
        return await self._active_driver().check(
            page_id, await self._require_locator(page_id, ref), checked=False
        )

    async def scroll_to_ref(self, page_id: str, ref: str) -> dict[str, Any]:
        return await self._active_driver().scroll_to(
            page_id, await self._require_locator(page_id, ref)
        )

    async def drag_ref(self, page_id: str, start_ref: str, end_ref: str) -> dict[str, Any]:
        return await self._active_driver().drag(
            page_id,
            await self._require_locator(page_id, start_ref),
            await self._require_locator(page_id, end_ref),
        )

    async def upload_file(self, page_id: str, ref: str, file_path: str) -> dict[str, Any]:
        return await self._active_driver().upload(
            page_id, await self._require_locator(page_id, ref), file_path
        )

    async def evaluate(self, page_id: str, code: str) -> dict[str, Any]:
        return await self._active_driver().evaluate(page_id, code)

    async def evaluate_on_ref(self, page_id: str, ref: str, code: str) -> dict[str, Any]:
        return await self._active_driver().evaluate_on(
            page_id, await self._require_locator(page_id, ref), code
        )

    async def wait(
        self,
        page_id: str,
        *,
        seconds: float | None = None,
        text: str | None = None,
        gone: bool = False,
        exact: bool = False,
    ) -> dict[str, Any]:
        return await self._active_driver().wait(
            page_id, seconds=seconds, text=text, gone=gone, exact=exact
        )

    async def wait_for_network_idle(
        self, page_id: str, *, timeout_seconds: float = 30.0
    ) -> dict[str, Any]:
        return await self._active_driver().wait_for_network_idle(
            page_id, timeout_seconds=timeout_seconds
        )

    async def start_console_capture(self, page_id: str) -> dict[str, Any]:
        return await self._active_driver().start_console_capture(page_id)

    async def get_console_messages(
        self, page_id: str, *, message_type: str | None = None, clear: bool = True
    ) -> dict[str, Any]:
        return await self._active_driver().get_console_messages(
            page_id, message_type=message_type, clear=clear
        )

    async def stop_console_capture(self, page_id: str) -> dict[str, Any]:
        return await self._active_driver().stop_console_capture(page_id)

    async def start_network_capture(self, page_id: str) -> dict[str, Any]:
        return await self._active_driver().start_network_capture(page_id)

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
        return await self._active_driver().wait_for_network_record(
            page_id,
            url_contains=url_contains,
            url_regex=url_regex,
            method=method,
            status=status,
            resource_type=resource_type,
            mime_contains=mime_contains,
            include_static=include_static,
            timeout_seconds=timeout_seconds,
        )

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
        return await self._active_driver().get_network_records(
            page_id,
            url_contains=url_contains,
            url_regex=url_regex,
            method=method,
            status=status,
            resource_type=resource_type,
            mime_contains=mime_contains,
            include_static=include_static,
            clear=clear,
        )

    async def stop_network_capture(self, page_id: str) -> dict[str, Any]:
        return await self._active_driver().stop_network_capture(page_id)

    async def get_cookies(
        self,
        page_id: str,
        *,
        name: str | None = None,
        domain: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        return await self._active_driver().get_cookies(page_id, name=name, domain=domain, path=path)

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
        return await self._active_driver().set_cookie(
            page_id,
            name=name,
            value=value,
            domain=domain,
            path=path,
            expires=expires,
            http_only=http_only,
            secure=secure,
            same_site=same_site,
        )

    async def clear_cookies(
        self,
        page_id: str,
        *,
        name: str | None = None,
        domain: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        return await self._active_driver().clear_cookies(
            page_id, name=name, domain=domain, path=path
        )

    async def save_storage_state(self, page_id: str, *, path: str | None = None) -> dict[str, Any]:
        return await self._active_driver().save_storage_state(page_id, path=path)

    async def load_storage_state(self, page_id: str, *, path: str) -> dict[str, Any]:
        return await self._active_driver().load_storage_state(page_id, path=path)

    async def verify_text(
        self, page_id: str, *, text: str, exact: bool = False, timeout_seconds: float = 5.0
    ) -> dict[str, Any]:
        return await self._active_driver().verify_text(
            page_id, text=text, exact=exact, timeout_seconds=timeout_seconds
        )

    async def verify_url(
        self, page_id: str, *, expected: str, exact: bool = False
    ) -> dict[str, Any]:
        return await self._active_driver().verify_url(page_id, expected=expected, exact=exact)

    async def verify_title(
        self, page_id: str, *, expected: str, exact: bool = False
    ) -> dict[str, Any]:
        return await self._active_driver().verify_title(page_id, expected=expected, exact=exact)

    async def verify_visible(
        self, page_id: str, *, role: str, name: str, timeout_seconds: float = 5.0
    ) -> dict[str, Any]:
        return await self._active_driver().verify_visible(
            page_id,
            role=role,
            name=name,
            timeout_seconds=timeout_seconds,
        )

    async def verify_state(self, page_id: str, *, ref: str, state: str) -> dict[str, Any]:
        return await self._active_driver().verify_state(
            page_id, locator=await self._require_locator(page_id, ref), state=state
        )

    async def verify_value(self, page_id: str, *, ref: str, expected: str) -> dict[str, Any]:
        return await self._active_driver().verify_value(
            page_id, locator=await self._require_locator(page_id, ref), expected=expected
        )

    async def type_text(self, page_id: str, text: str, *, submit: bool = False) -> dict[str, Any]:
        return await self._active_driver().type_text(page_id, text, submit=submit)

    async def press_key(self, page_id: str, key: str) -> dict[str, Any]:
        return await self._active_driver().press_key(page_id, key)

    async def key_down(self, page_id: str, key: str) -> dict[str, Any]:
        return await self._active_driver().key_down(page_id, key)

    async def key_up(self, page_id: str, key: str) -> dict[str, Any]:
        return await self._active_driver().key_up(page_id, key)

    async def wheel(self, page_id: str, *, dx: int = 0, dy: int = 700) -> dict[str, Any]:
        return await self._active_driver().wheel(page_id, dx=dx, dy=dy)

    async def mouse_move(self, page_id: str, *, x: int, y: int) -> dict[str, Any]:
        return await self._active_driver().mouse_move(page_id, x=x, y=y)

    async def mouse_click(
        self,
        page_id: str,
        *,
        x: int,
        y: int,
        button: str = "left",
        count: int = 1,
    ) -> dict[str, Any]:
        return await self._active_driver().mouse_click(
            page_id, x=x, y=y, button=button, count=count
        )

    async def mouse_drag(
        self, page_id: str, *, x1: int, y1: int, x2: int, y2: int
    ) -> dict[str, Any]:
        return await self._active_driver().mouse_drag(page_id, x1=x1, y1=y1, x2=x2, y2=y2)

    async def mouse_down(self, page_id: str, *, button: str = "left") -> dict[str, Any]:
        return await self._active_driver().mouse_down(page_id, button=button)

    async def mouse_up(self, page_id: str, *, button: str = "left") -> dict[str, Any]:
        return await self._active_driver().mouse_up(page_id, button=button)

    async def screenshot(
        self, page_id: str, *, path: str, full_page: bool = False
    ) -> dict[str, Any]:
        return await self._active_driver().screenshot(page_id, path=path, full_page=full_page)

    async def save_pdf(self, page_id: str, *, path: str) -> dict[str, Any]:
        return await self._active_driver().save_pdf(page_id, path=path)

    async def setup_dialog_handler(
        self,
        page_id: str,
        *,
        default_action: str = "accept",
        default_prompt_text: str | None = None,
    ) -> dict[str, Any]:
        return await self._active_driver().setup_dialog_handler(
            page_id,
            default_action=default_action,
            default_prompt_text=default_prompt_text,
        )

    async def handle_dialog(
        self,
        page_id: str,
        *,
        accept: bool,
        prompt_text: str | None = None,
    ) -> dict[str, Any]:
        return await self._active_driver().handle_dialog(
            page_id, accept=accept, prompt_text=prompt_text
        )

    async def remove_dialog_handler(self, page_id: str) -> dict[str, Any]:
        return await self._active_driver().remove_dialog_handler(page_id)

    async def start_tracing(
        self,
        page_id: str,
        *,
        screenshots: bool = True,
        snapshots: bool = True,
        sources: bool = False,
    ) -> dict[str, Any]:
        return await self._active_driver().start_tracing(
            page_id,
            screenshots=screenshots,
            snapshots=snapshots,
            sources=sources,
        )

    async def add_trace_chunk(self, page_id: str, *, title: str | None = None) -> dict[str, Any]:
        return await self._active_driver().add_trace_chunk(page_id, title=title)

    async def stop_tracing(self, page_id: str, *, path: str | None = None) -> dict[str, Any]:
        return await self._active_driver().stop_tracing(page_id, path=path)

    async def start_video(
        self, page_id: str, *, width: int | None = None, height: int | None = None
    ) -> dict[str, Any]:
        return await self._active_driver().start_video(page_id, width=width, height=height)

    async def stop_video(self, page_id: str, *, path: str | None = None) -> dict[str, Any]:
        return await self._active_driver().stop_video(page_id, path=path)

    async def search(self, *, query: str, engine: str = "duckduckgo") -> dict[str, Any]:
        return await self.new_tab(
            url=PlaywrightDriver.build_search_url(query, engine), wait_until="load"
        )

    async def _require_locator(self, page_id: str, ref: str):
        state = self._snapshot_registry.get(page_id)
        if state is None:
            raise NoSnapshotContextError()
        locator = self._ref_resolver.build_locator_spec(ref, state.refs)
        if locator is None:
            normalized = self._ref_resolver.parse_ref(ref)
            if normalized is None:
                raise InvalidInputError(f"Invalid ref: {ref}")
            raise RefNotFoundError()
        return locator

    async def _scroll_page_to_bottom(self, page_id: str) -> None:
        previous_height: int | None = None
        stable_rounds = 0
        for _ in range(self.READ_SCROLL_MAX_ROUNDS):
            before_payload = await self.evaluate(
                page_id,
                """() => ({
                    height: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)
                })""",
            )
            current_height = int((before_payload.get("result") or {}).get("height") or 0)
            await self.evaluate(
                page_id,
                """() => {
                    const height = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
                    window.scrollTo(0, height);
                    return height;
                }""",
            )
            await self.wait(page_id, seconds=self.READ_SCROLL_PAUSE_MS / 1000.0)
            after_payload = await self.evaluate(
                page_id,
                """() => ({
                    height: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)
                })""",
            )
            new_height = int((after_payload.get("result") or {}).get("height") or 0)
            if previous_height is None:
                previous_height = current_height
            if new_height <= previous_height:
                stable_rounds += 1
                if stable_rounds >= self.READ_SCROLL_STABLE_ROUNDS:
                    return
            else:
                stable_rounds = 0
                previous_height = new_height

    async def _activate_driver(self, driver_name: str, *, reason: str) -> None:
        async with self._rebind_lock:
            if self._driver_name == driver_name and self._driver is not None:
                return
            old_driver_name = self._driver_name
            logger.info(
                "Rebinding driver from=%s to=%s reason=%s",
                old_driver_name or "none",
                driver_name,
                reason,
            )
            records, active_by_agent = await self._tabs.snapshot_state()
            if old_driver_name == "extension":
                with contextlib.suppress(Exception):
                    await self._extension.stop()
            elif old_driver_name == "playwright":
                with contextlib.suppress(Exception):
                    await self._playwright.stop()
            self._driver = None
            self._driver_name = None
            if driver_name == "extension":
                await self._extension.ensure_started()
                self._driver = self._extension
            else:
                await self._playwright.ensure_started()
                self._driver = self._playwright
            self._driver_name = driver_name
            self._snapshot_registry.clear()
            await self._tabs.clear_snapshot_state()
            state_reset = False
            if records:
                state_reset = True
                reopened: list[tuple[TabRecord, dict[str, Any]]] = []
                for record in records:
                    reopened_page = await self._driver.new_tab(
                        page_id=record.page_id,
                        url=record.url,
                        wait_until="load",
                        timeout_seconds=self.READ_NAVIGATION_TIMEOUT_SECONDS,
                    )
                    reopened.append((record, reopened_page))
                for record, reopened_page in reopened:
                    await self._tabs.update_tab(
                        record.page_id,
                        url=str(reopened_page.get("url") or record.url),
                        title=str(reopened_page.get("title") or record.title),
                    )
                for agent_id, page_id in active_by_agent.items():
                    try:
                        await self._tabs.set_active_tab(agent_id, page_id)
                        await self._driver.switch_tab(page_id)
                    except Exception:
                        pass
            self._last_runtime_meta = {
                "driver": self._driver_name,
                "driver_reason": reason,
            }
            if old_driver_name and old_driver_name != driver_name:
                self._last_runtime_meta.update(
                    {
                        "state_reset": state_reset,
                        "driver_changed_from": old_driver_name,
                        "driver_changed_to": driver_name,
                    }
                )
            logger.info(
                "Driver rebound active=%s restored_tabs=%d state_reset=%s",
                self._driver_name,
                len(records),
                state_reset,
            )

    async def _watch_extension_changes(self) -> None:
        try:
            while True:
                await self._extension_hub.wait_for_change()
                session = self._extension_hub.session
                target: str | None = None
                reason: str | None = None
                if session is not None and session.hello.has_required_capabilities():
                    if self._driver_name != "extension":
                        target = "extension"
                        reason = "extension-connected"
                elif self._driver_name == "extension":
                    logger.warning(
                        "Extension disconnected while extension driver is active; holding driver until next command"
                    )
                if not target:
                    continue
                try:
                    if self._command_depth == 0:
                        await self._activate_driver(target, reason=reason or "rebind")
                    else:
                        self._pending_driver = target
                        self._pending_reason = reason
                except Exception:
                    self._pending_driver = None
                    self._pending_reason = None
        except asyncio.CancelledError:
            return

    async def _maybe_apply_pending_rebind(self) -> None:
        if self._command_depth != 0:
            return
        if not self._pending_driver:
            return
        target = self._pending_driver
        reason = self._pending_reason or "pending-rebind"
        self._pending_driver = None
        self._pending_reason = None
        await self._activate_driver(target, reason=reason)

    def _active_driver(self) -> BrowserDriver:
        if self._driver is None:
            raise OperationFailedError("Browser backend is not started.")
        return self._driver

    def _next_page_id(self) -> str:
        self._page_counter += 1
        return f"page_{self._page_counter:04d}"
