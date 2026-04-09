"""Daemon application and action handlers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from browser_cli import error_codes
from browser_cli.constants import DEFAULT_PUBLIC_AGENT_ID
from browser_cli.errors import (
    BrowserCliError,
    BusyTabError,
    InvalidInputError,
    NoActiveTabError,
    OperationFailedError,
    TabNotFoundError,
)

from .models import DaemonRequest, DaemonResponse
from .state import DaemonState

Handler = Callable[[DaemonRequest], Awaitable[dict[str, Any]]]


class BrowserDaemonApp:
    def __init__(self, state: DaemonState | None = None) -> None:
        self._state = state or DaemonState()
        self._handlers: dict[str, Handler] = {
            "open": self._handle_open,
            "search": self._handle_search,
            "tabs": self._handle_tabs,
            "switch-tab": self._handle_switch_tab,
            "new-tab": self._handle_new_tab,
            "close-tab": self._handle_close_tab,
            "close": self._handle_close,
            "stop": self._handle_stop,
            "info": self._handle_info,
            "html": self._handle_html,
            "snapshot": self._handle_snapshot,
            "reload": self._handle_reload,
            "back": self._handle_back,
            "forward": self._handle_forward,
            "click": self._handle_click,
            "double-click": self._handle_double_click,
            "hover": self._handle_hover,
            "focus": self._handle_focus,
            "fill": self._handle_fill,
            "fill-form": self._handle_fill_form,
            "select": self._handle_select,
            "options": self._handle_options,
            "check": self._handle_check,
            "uncheck": self._handle_uncheck,
            "scroll-to": self._handle_scroll_to,
            "drag": self._handle_drag,
            "upload": self._handle_upload,
            "type": self._handle_type,
            "press": self._handle_press,
            "key-down": self._handle_key_down,
            "key-up": self._handle_key_up,
            "scroll": self._handle_scroll,
            "mouse-click": self._handle_mouse_click,
            "mouse-move": self._handle_mouse_move,
            "mouse-drag": self._handle_mouse_drag,
            "mouse-down": self._handle_mouse_down,
            "mouse-up": self._handle_mouse_up,
            "eval": self._handle_eval,
            "eval-on": self._handle_eval_on,
            "wait": self._handle_wait,
            "wait-network": self._handle_wait_network,
            "screenshot": self._handle_screenshot,
            "pdf": self._handle_pdf,
            "console-start": self._handle_console_start,
            "console": self._handle_console,
            "console-stop": self._handle_console_stop,
            "network-start": self._handle_network_start,
            "network": self._handle_network,
            "network-stop": self._handle_network_stop,
            "dialog-setup": self._handle_dialog_setup,
            "dialog": self._handle_dialog,
            "dialog-remove": self._handle_dialog_remove,
            "cookies": self._handle_cookies,
            "cookie-set": self._handle_cookie_set,
            "cookies-clear": self._handle_cookies_clear,
            "storage-save": self._handle_storage_save,
            "storage-load": self._handle_storage_load,
            "verify-text": self._handle_verify_text,
            "verify-visible": self._handle_verify_visible,
            "verify-url": self._handle_verify_url,
            "verify-title": self._handle_verify_title,
            "verify-state": self._handle_verify_state,
            "verify-value": self._handle_verify_value,
            "trace-start": self._handle_trace_start,
            "trace-chunk": self._handle_trace_chunk,
            "trace-stop": self._handle_trace_stop,
            "video-start": self._handle_video_start,
            "video-stop": self._handle_video_stop,
            "resize": self._handle_resize,
        }

    @property
    def state(self) -> DaemonState:
        return self._state

    async def execute(self, request: DaemonRequest) -> DaemonResponse:
        agent_id = request.agent_id or DEFAULT_PUBLIC_AGENT_ID
        request.agent_id = agent_id
        handler = self._handlers.get(request.action)
        if handler is None:
            return self._error_response(
                InvalidInputError(f"Unknown command: {request.action}"),
                request=request,
            )
        try:
            data = await handler(request)
            meta = {
                "action": request.action,
                "agent_id": agent_id,
            }
            chrome_environment = self._state.browser_service.chrome_environment
            if chrome_environment is not None:
                meta["profile_source"] = chrome_environment.source
            return DaemonResponse.success(data, meta=meta)
        except BrowserCliError as exc:
            return self._error_response(exc, request=request)
        except Exception as exc:  # pragma: no cover - last-resort daemon guard
            return self._error_response(
                OperationFailedError(f"Unexpected daemon failure: {exc}", error_code=error_codes.INTERNAL_ERROR),
                request=request,
            )

    def _error_response(self, exc: BrowserCliError, *, request: DaemonRequest) -> DaemonResponse:
        return DaemonResponse.failure(
            error_code=exc.error_code,
            error_message=exc.message,
            meta={
                "action": request.action,
                "agent_id": request.agent_id,
            },
        )

    async def _handle_stop(self, request: DaemonRequest) -> dict[str, Any]:
        shutdown = await self._state.browser_service.stop()
        self._state.shutdown_event.set()
        return {"stopped": True, **shutdown}

    async def _handle_open(self, request: DaemonRequest) -> dict[str, Any]:
        url = self._require_str(request.args, "url")
        page = await self._state.browser_service.new_tab(url=url)
        await self._state.tabs.add_tab(
            page_id=str(page["page_id"]),
            owner_agent_id=request.agent_id,
            url=str(page["url"]),
            title=str(page["title"]),
        )
        return {"page": page}

    async def _handle_search(self, request: DaemonRequest) -> dict[str, Any]:
        query = self._require_str(request.args, "query")
        engine = str(request.args.get("engine") or "duckduckgo")
        page = await self._state.browser_service.search(query=query, engine=engine)
        await self._state.tabs.add_tab(
            page_id=str(page["page_id"]),
            owner_agent_id=request.agent_id,
            url=str(page["url"]),
            title=str(page["title"]),
        )
        return {"page": page}

    async def _handle_new_tab(self, request: DaemonRequest) -> dict[str, Any]:
        url = str(request.args.get("url") or "").strip() or None
        page = await self._state.browser_service.new_tab(url=url)
        await self._state.tabs.add_tab(
            page_id=str(page["page_id"]),
            owner_agent_id=request.agent_id,
            url=str(page["url"]),
            title=str(page["title"]),
        )
        return {"page": page}

    async def _handle_tabs(self, request: DaemonRequest) -> dict[str, Any]:
        tabs = await self._state.tabs.list_tabs(request.agent_id)
        current_active: str | None = None
        try:
            current_active = (await self._state.tabs.get_active_tab(request.agent_id)).page_id
        except NoActiveTabError:
            current_active = None
        results: list[dict[str, Any]] = []
        for record in tabs:
            try:
                latest = await self._state.browser_service.get_page_summary(record.page_id)
                await self._state.tabs.update_tab(
                    record.page_id,
                    url=str(latest["url"]),
                    title=str(latest["title"]),
                )
                record.url = str(latest["url"])
                record.title = str(latest["title"])
            except BrowserCliError:
                pass
            results.append(
                {
                    "page_id": record.page_id,
                    "url": record.url,
                    "title": record.title,
                    "active": record.page_id == current_active,
                    "busy": record.busy is not None,
                }
            )
        return {"tabs": results}

    async def _handle_switch_tab(self, request: DaemonRequest) -> dict[str, Any]:
        page_id = self._require_str(request.args, "page_id")
        claimed = await self._state.tabs.claim_page(
            agent_id=request.agent_id,
            page_id=page_id,
            request_id=request.request_id,
            command=request.action,
        )
        try:
            await self._state.tabs.set_active_tab(request.agent_id, page_id)
        finally:
            await self._state.tabs.release_tab(page_id=claimed.page_id, request_id=request.request_id)
        return {"page": await self._state.browser_service.get_page_summary(page_id)}

    async def _handle_close_tab(self, request: DaemonRequest) -> dict[str, Any]:
        page_id = str(request.args.get("page_id") or "").strip()
        if not page_id:
            page_id = await self._state.tabs.current_active_page_id(request.agent_id)
        claimed = await self._state.tabs.claim_page(
            agent_id=request.agent_id,
            page_id=page_id,
            request_id=request.request_id,
            command=request.action,
        )
        try:
            result = await self._state.browser_service.close_tab(page_id)
            await self._state.tabs.remove_tab(request.agent_id, page_id)
            return result
        finally:
            await self._state.tabs.release_tab(page_id=claimed.page_id, request_id=request.request_id)

    async def _handle_close(self, request: DaemonRequest) -> dict[str, Any]:
        return await self._handle_close_tab(request)

    async def _handle_info(self, request: DaemonRequest) -> dict[str, Any]:
        page = await self._run_active_page_action(request, self._state.browser_service.get_page_info)
        return {"page": page}

    async def _handle_html(self, request: DaemonRequest) -> dict[str, Any]:
        payload = await self._run_active_page_action(request, self._state.browser_service.capture_html)
        return payload

    async def _handle_snapshot(self, request: DaemonRequest) -> dict[str, Any]:
        interactive = bool(request.args.get("interactive"))
        full_page = bool(request.args.get("full_page", True))

        async def _snapshot(page_id: str) -> dict[str, Any]:
            payload = await self._state.browser_service.capture_snapshot(
                page_id,
                interactive=interactive,
                full_page=full_page,
            )
            refs_summary = payload.get("refs_summary", [])
            ref_ids = {str(item.get("ref")) for item in refs_summary if item.get("ref")}
            await self._state.tabs.update_tab(page_id, last_snapshot_refs=ref_ids)
            return payload

        return await self._run_active_page_action(request, _snapshot)

    async def _handle_reload(self, request: DaemonRequest) -> dict[str, Any]:
        payload = await self._run_active_page_action(request, self._state.browser_service.reload)
        return {"page": payload}

    async def _handle_back(self, request: DaemonRequest) -> dict[str, Any]:
        payload = await self._run_active_page_action(request, self._state.browser_service.go_back)
        return {"page": payload}

    async def _handle_forward(self, request: DaemonRequest) -> dict[str, Any]:
        payload = await self._run_active_page_action(request, self._state.browser_service.go_forward)
        return {"page": payload}

    async def _handle_resize(self, request: DaemonRequest) -> dict[str, Any]:
        width = int(request.args.get("width") or 0)
        height = int(request.args.get("height") or 0)
        if width <= 0 or height <= 0:
            raise InvalidInputError("width and height must be positive integers.")
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.resize(page_id, width=width, height=height),
        )

    async def _handle_click(self, request: DaemonRequest) -> dict[str, Any]:
        ref = self._require_str(request.args, "ref")
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.click_ref(page_id, ref))

    async def _handle_double_click(self, request: DaemonRequest) -> dict[str, Any]:
        ref = self._require_str(request.args, "ref")
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.double_click_ref(page_id, ref))

    async def _handle_hover(self, request: DaemonRequest) -> dict[str, Any]:
        ref = self._require_str(request.args, "ref")
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.hover_ref(page_id, ref))

    async def _handle_focus(self, request: DaemonRequest) -> dict[str, Any]:
        ref = self._require_str(request.args, "ref")
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.focus_ref(page_id, ref))

    async def _handle_fill(self, request: DaemonRequest) -> dict[str, Any]:
        ref = self._require_str(request.args, "ref")
        text = self._require_str(request.args, "text")
        submit = bool(request.args.get("submit"))
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.fill_ref(page_id, ref, text, submit=submit),
        )

    async def _handle_fill_form(self, request: DaemonRequest) -> dict[str, Any]:
        fields = request.args.get("fields") or []
        if not isinstance(fields, list):
            raise InvalidInputError("fill-form expects a JSON array in --fields.")
        submit = bool(request.args.get("submit"))
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.fill_form(page_id, fields, submit=submit),
        )

    async def _handle_select(self, request: DaemonRequest) -> dict[str, Any]:
        ref = self._require_str(request.args, "ref")
        text = self._require_str(request.args, "text")
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.select_option(page_id, ref, text))

    async def _handle_options(self, request: DaemonRequest) -> dict[str, Any]:
        ref = self._require_str(request.args, "ref")
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.list_options(page_id, ref))

    async def _handle_check(self, request: DaemonRequest) -> dict[str, Any]:
        ref = self._require_str(request.args, "ref")
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.check_ref(page_id, ref))

    async def _handle_uncheck(self, request: DaemonRequest) -> dict[str, Any]:
        ref = self._require_str(request.args, "ref")
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.uncheck_ref(page_id, ref))

    async def _handle_scroll_to(self, request: DaemonRequest) -> dict[str, Any]:
        ref = self._require_str(request.args, "ref")
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.scroll_to_ref(page_id, ref))

    async def _handle_drag(self, request: DaemonRequest) -> dict[str, Any]:
        start_ref = self._require_str(request.args, "start_ref")
        end_ref = self._require_str(request.args, "end_ref")
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.drag_ref(page_id, start_ref, end_ref))

    async def _handle_upload(self, request: DaemonRequest) -> dict[str, Any]:
        ref = self._require_str(request.args, "ref")
        path = self._require_str(request.args, "path")
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.upload_file(page_id, ref, path))

    async def _handle_type(self, request: DaemonRequest) -> dict[str, Any]:
        text = self._require_str(request.args, "text")
        submit = bool(request.args.get("submit"))
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.type_text(page_id, text, submit=submit))

    async def _handle_press(self, request: DaemonRequest) -> dict[str, Any]:
        key = self._require_str(request.args, "key")
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.press_key(page_id, key))

    async def _handle_key_down(self, request: DaemonRequest) -> dict[str, Any]:
        key = self._require_str(request.args, "key")
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.key_down(page_id, key))

    async def _handle_key_up(self, request: DaemonRequest) -> dict[str, Any]:
        key = self._require_str(request.args, "key")
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.key_up(page_id, key))

    async def _handle_scroll(self, request: DaemonRequest) -> dict[str, Any]:
        dx = int(request.args.get("dx") or 0)
        dy = int(request.args.get("dy") or 700)
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.wheel(page_id, dx=dx, dy=dy))

    async def _handle_mouse_click(self, request: DaemonRequest) -> dict[str, Any]:
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.mouse_click(
                page_id,
                x=int(request.args.get("x")),
                y=int(request.args.get("y")),
                button=str(request.args.get("button") or "left"),
                count=int(request.args.get("count") or 1),
            ),
        )

    async def _handle_mouse_move(self, request: DaemonRequest) -> dict[str, Any]:
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.mouse_move(
                page_id,
                x=int(request.args.get("x")),
                y=int(request.args.get("y")),
            ),
        )

    async def _handle_mouse_drag(self, request: DaemonRequest) -> dict[str, Any]:
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.mouse_drag(
                page_id,
                x1=int(request.args.get("x1")),
                y1=int(request.args.get("y1")),
                x2=int(request.args.get("x2")),
                y2=int(request.args.get("y2")),
            ),
        )

    async def _handle_mouse_down(self, request: DaemonRequest) -> dict[str, Any]:
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.mouse_down(
                page_id,
                button=str(request.args.get("button") or "left"),
            ),
        )

    async def _handle_mouse_up(self, request: DaemonRequest) -> dict[str, Any]:
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.mouse_up(
                page_id,
                button=str(request.args.get("button") or "left"),
            ),
        )

    async def _handle_eval(self, request: DaemonRequest) -> dict[str, Any]:
        code = self._require_str(request.args, "code")
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.evaluate(page_id, code))

    async def _handle_eval_on(self, request: DaemonRequest) -> dict[str, Any]:
        ref = self._require_str(request.args, "ref")
        code = self._require_str(request.args, "code")
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.evaluate_on_ref(page_id, ref, code))

    async def _handle_wait(self, request: DaemonRequest) -> dict[str, Any]:
        seconds = request.args.get("seconds")
        text = request.args.get("text")
        gone = bool(request.args.get("gone"))
        exact = bool(request.args.get("exact"))
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.wait(
                page_id,
                seconds=float(seconds) if seconds is not None else None,
                text=str(text) if text else None,
                gone=gone,
                exact=exact,
            ),
        )

    async def _handle_wait_network(self, request: DaemonRequest) -> dict[str, Any]:
        timeout_seconds = float(request.args.get("timeout") or 30.0)
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.wait_for_network_idle(page_id, timeout_seconds=timeout_seconds),
        )

    async def _handle_screenshot(self, request: DaemonRequest) -> dict[str, Any]:
        path = self._require_str(request.args, "path")
        full_page = bool(request.args.get("full_page"))
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.screenshot(page_id, path=path, full_page=full_page),
        )

    async def _handle_pdf(self, request: DaemonRequest) -> dict[str, Any]:
        path = self._require_str(request.args, "path")
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.save_pdf(page_id, path=path))

    async def _handle_console_start(self, request: DaemonRequest) -> dict[str, Any]:
        return await self._run_active_page_action(request, self._state.browser_service.start_console_capture)

    async def _handle_console(self, request: DaemonRequest) -> dict[str, Any]:
        message_type = str(request.args.get("message_type") or "").strip() or None
        clear = not bool(request.args.get("no_clear"))
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.get_console_messages(page_id, message_type=message_type, clear=clear),
        )

    async def _handle_console_stop(self, request: DaemonRequest) -> dict[str, Any]:
        return await self._run_active_page_action(request, self._state.browser_service.stop_console_capture)

    async def _handle_network_start(self, request: DaemonRequest) -> dict[str, Any]:
        return await self._run_active_page_action(request, self._state.browser_service.start_network_capture)

    async def _handle_network(self, request: DaemonRequest) -> dict[str, Any]:
        include_static = bool(request.args.get("include_static"))
        clear = not bool(request.args.get("no_clear"))
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.get_network_requests(page_id, include_static=include_static, clear=clear),
        )

    async def _handle_network_stop(self, request: DaemonRequest) -> dict[str, Any]:
        return await self._run_active_page_action(request, self._state.browser_service.stop_network_capture)

    async def _handle_dialog_setup(self, request: DaemonRequest) -> dict[str, Any]:
        action = str(request.args.get("action") or "accept")
        if action not in {"accept", "dismiss"}:
            raise InvalidInputError("action must be accept or dismiss.")
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.setup_dialog_handler(
                page_id,
                default_action=action,
                default_prompt_text=self._optional_str(request.args, "text"),
            ),
        )

    async def _handle_dialog(self, request: DaemonRequest) -> dict[str, Any]:
        accept = not bool(request.args.get("dismiss"))
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.handle_dialog(
                page_id,
                accept=accept,
                prompt_text=self._optional_str(request.args, "text"),
            ),
        )

    async def _handle_dialog_remove(self, request: DaemonRequest) -> dict[str, Any]:
        return await self._run_active_page_action(request, self._state.browser_service.remove_dialog_handler)

    async def _handle_cookies(self, request: DaemonRequest) -> dict[str, Any]:
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.get_cookies(
                page_id,
                name=self._optional_str(request.args, "name"),
                domain=self._optional_str(request.args, "domain"),
                path=self._optional_str(request.args, "path"),
            ),
        )

    async def _handle_cookie_set(self, request: DaemonRequest) -> dict[str, Any]:
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.set_cookie(
                page_id,
                name=self._require_str(request.args, "name"),
                value=self._require_str(request.args, "value"),
                domain=self._optional_str(request.args, "domain"),
                path=str(request.args.get("path") or "/"),
                expires=float(request.args["expires"]) if request.args.get("expires") is not None else None,
                http_only=bool(request.args.get("http_only")),
                secure=bool(request.args.get("secure")),
                same_site=self._optional_str(request.args, "same_site"),
            ),
        )

    async def _handle_cookies_clear(self, request: DaemonRequest) -> dict[str, Any]:
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.clear_cookies(
                page_id,
                name=self._optional_str(request.args, "name"),
                domain=self._optional_str(request.args, "domain"),
                path=self._optional_str(request.args, "path"),
            ),
        )

    async def _handle_storage_save(self, request: DaemonRequest) -> dict[str, Any]:
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.save_storage_state(
                page_id,
                path=self._optional_str(request.args, "path"),
            ),
        )

    async def _handle_storage_load(self, request: DaemonRequest) -> dict[str, Any]:
        path = self._require_str(request.args, "path")
        return await self._run_active_page_action(request, lambda page_id: self._state.browser_service.load_storage_state(page_id, path=path))

    async def _handle_verify_text(self, request: DaemonRequest) -> dict[str, Any]:
        text = self._require_str(request.args, "text")
        exact = bool(request.args.get("exact"))
        timeout = float(request.args.get("timeout") or 5.0)
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.verify_text(page_id, text=text, exact=exact, timeout_seconds=timeout),
        )

    async def _handle_verify_visible(self, request: DaemonRequest) -> dict[str, Any]:
        role = self._require_str(request.args, "role")
        name = self._require_str(request.args, "name")
        timeout = float(request.args.get("timeout") or 5.0)
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.verify_visible(page_id, role=role, name=name, timeout_seconds=timeout),
        )

    async def _handle_verify_url(self, request: DaemonRequest) -> dict[str, Any]:
        expected = self._require_str(request.args, "expected")
        exact = bool(request.args.get("exact"))
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.verify_url(page_id, expected=expected, exact=exact),
        )

    async def _handle_verify_title(self, request: DaemonRequest) -> dict[str, Any]:
        expected = self._require_str(request.args, "expected")
        exact = bool(request.args.get("exact"))
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.verify_title(page_id, expected=expected, exact=exact),
        )

    async def _handle_verify_state(self, request: DaemonRequest) -> dict[str, Any]:
        ref = self._require_str(request.args, "ref")
        state = self._require_str(request.args, "state")
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.verify_state(page_id, ref=ref, state=state),
        )

    async def _handle_verify_value(self, request: DaemonRequest) -> dict[str, Any]:
        ref = self._require_str(request.args, "ref")
        expected = self._require_str(request.args, "expected")
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.verify_value(page_id, ref=ref, expected=expected),
        )

    async def _handle_trace_start(self, request: DaemonRequest) -> dict[str, Any]:
        screenshots = not bool(request.args.get("no_screenshots"))
        snapshots = not bool(request.args.get("no_snapshots"))
        sources = bool(request.args.get("sources"))
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.start_tracing(
                page_id,
                screenshots=screenshots,
                snapshots=snapshots,
                sources=sources,
            ),
        )

    async def _handle_trace_chunk(self, request: DaemonRequest) -> dict[str, Any]:
        title = self._optional_str(request.args, "title")
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.add_trace_chunk(page_id, title=title),
        )

    async def _handle_trace_stop(self, request: DaemonRequest) -> dict[str, Any]:
        path = self._optional_str(request.args, "path")
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.stop_tracing(page_id, path=path),
        )

    async def _handle_video_start(self, request: DaemonRequest) -> dict[str, Any]:
        width = request.args.get("width")
        height = request.args.get("height")
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.start_video(
                page_id,
                width=int(width) if width is not None else None,
                height=int(height) if height is not None else None,
            ),
        )

    async def _handle_video_stop(self, request: DaemonRequest) -> dict[str, Any]:
        path = self._optional_str(request.args, "path")
        return await self._run_active_page_action(
            request,
            lambda page_id: self._state.browser_service.stop_video(page_id, path=path),
        )

    async def _run_active_page_action(
        self,
        request: DaemonRequest,
        operation: Callable[[str], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        async with self._state.tabs.claim_active_tab(
            agent_id=request.agent_id,
            request_id=request.request_id,
            command=request.action,
        ) as tab:
            payload = await operation(tab.page_id)
            try:
                latest = await self._state.browser_service.get_page_summary(tab.page_id)
                await self._state.tabs.update_tab(
                    tab.page_id,
                    url=str(latest["url"]),
                    title=str(latest["title"]),
                )
            except BrowserCliError:
                pass
            return payload

    @staticmethod
    def _require_str(args: dict[str, Any], key: str) -> str:
        value = str(args.get(key) or "").strip()
        if not value:
            raise InvalidInputError(f"{key} is required.")
        return value

    @staticmethod
    def _optional_str(args: dict[str, Any], key: str) -> str | None:
        value = str(args.get(key) or "").strip()
        return value or None
