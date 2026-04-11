"""Capability-oriented browser driver base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from browser_cli.refs.models import LocatorSpec, SnapshotInput

from .models import DriverHealth, TabState


class BrowserDriver(ABC):
    name: str

    @abstractmethod
    async def ensure_started(self) -> None: ...

    @abstractmethod
    async def stop(self) -> dict[str, Any]: ...

    @abstractmethod
    async def health(self) -> DriverHealth: ...

    @abstractmethod
    async def new_tab(
        self,
        *,
        page_id: str,
        url: str | None = None,
        wait_until: str = "load",
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def close_tab(self, page_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def list_tabs(self) -> list[TabState]: ...

    @abstractmethod
    async def switch_tab(self, page_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def get_page_summary(self, page_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def get_page_info(self, page_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def capture_html(self, page_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def capture_snapshot_input(
        self,
        page_id: str,
        *,
        interactive: bool = False,
        full_page: bool = True,
    ) -> SnapshotInput: ...

    @abstractmethod
    async def navigate(
        self,
        page_id: str,
        url: str,
        *,
        wait_until: str = "load",
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def reload(
        self,
        page_id: str,
        *,
        wait_until: str = "load",
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def go_back(self, page_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def go_forward(self, page_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def resize(self, page_id: str, *, width: int, height: int) -> dict[str, Any]: ...

    @abstractmethod
    async def click(self, page_id: str, locator: LocatorSpec) -> dict[str, Any]: ...

    @abstractmethod
    async def double_click(self, page_id: str, locator: LocatorSpec) -> dict[str, Any]: ...

    @abstractmethod
    async def hover(self, page_id: str, locator: LocatorSpec) -> dict[str, Any]: ...

    @abstractmethod
    async def focus(self, page_id: str, locator: LocatorSpec) -> dict[str, Any]: ...

    @abstractmethod
    async def fill(
        self,
        page_id: str,
        locator: LocatorSpec,
        text: str,
        *,
        submit: bool = False,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def select_option(self, page_id: str, locator: LocatorSpec, text: str) -> dict[str, Any]: ...

    @abstractmethod
    async def list_options(self, page_id: str, locator: LocatorSpec) -> dict[str, Any]: ...

    @abstractmethod
    async def check(self, page_id: str, locator: LocatorSpec, *, checked: bool) -> dict[str, Any]: ...

    @abstractmethod
    async def scroll_to(self, page_id: str, locator: LocatorSpec) -> dict[str, Any]: ...

    @abstractmethod
    async def drag(self, page_id: str, start_locator: LocatorSpec, end_locator: LocatorSpec) -> dict[str, Any]: ...

    @abstractmethod
    async def upload(self, page_id: str, locator: LocatorSpec, file_path: str) -> dict[str, Any]: ...

    @abstractmethod
    async def evaluate(self, page_id: str, code: str) -> dict[str, Any]: ...

    @abstractmethod
    async def evaluate_on(self, page_id: str, locator: LocatorSpec, code: str) -> dict[str, Any]: ...

    @abstractmethod
    async def wait(
        self,
        page_id: str,
        *,
        seconds: float | None = None,
        text: str | None = None,
        gone: bool = False,
        exact: bool = False,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def wait_for_network_idle(self, page_id: str, *, timeout_seconds: float = 30.0) -> dict[str, Any]: ...

    @abstractmethod
    async def start_console_capture(self, page_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def get_console_messages(
        self,
        page_id: str,
        *,
        message_type: str | None = None,
        clear: bool = True,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def stop_console_capture(self, page_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def start_network_capture(self, page_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def get_network_requests(
        self,
        page_id: str,
        *,
        include_static: bool = False,
        clear: bool = True,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def stop_network_capture(self, page_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def get_cookies(
        self,
        page_id: str,
        *,
        name: str | None = None,
        domain: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]: ...

    @abstractmethod
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
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def clear_cookies(
        self,
        page_id: str,
        *,
        name: str | None = None,
        domain: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def save_storage_state(self, page_id: str, *, path: str | None = None) -> dict[str, Any]: ...

    @abstractmethod
    async def load_storage_state(self, page_id: str, *, path: str) -> dict[str, Any]: ...

    @abstractmethod
    async def verify_text(
        self,
        page_id: str,
        *,
        text: str,
        exact: bool = False,
        timeout_seconds: float = 5.0,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def verify_url(self, page_id: str, *, expected: str, exact: bool = False) -> dict[str, Any]: ...

    @abstractmethod
    async def verify_title(self, page_id: str, *, expected: str, exact: bool = False) -> dict[str, Any]: ...

    @abstractmethod
    async def verify_visible(
        self,
        page_id: str,
        *,
        role: str,
        name: str,
        timeout_seconds: float = 5.0,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def verify_state(self, page_id: str, *, locator: LocatorSpec, state: str) -> dict[str, Any]: ...

    @abstractmethod
    async def verify_value(self, page_id: str, *, locator: LocatorSpec, expected: str) -> dict[str, Any]: ...

    @abstractmethod
    async def type_text(self, page_id: str, text: str, *, submit: bool = False) -> dict[str, Any]: ...

    @abstractmethod
    async def press_key(self, page_id: str, key: str) -> dict[str, Any]: ...

    @abstractmethod
    async def key_down(self, page_id: str, key: str) -> dict[str, Any]: ...

    @abstractmethod
    async def key_up(self, page_id: str, key: str) -> dict[str, Any]: ...

    @abstractmethod
    async def wheel(self, page_id: str, *, dx: int = 0, dy: int = 700) -> dict[str, Any]: ...

    @abstractmethod
    async def mouse_move(self, page_id: str, *, x: int, y: int) -> dict[str, Any]: ...

    @abstractmethod
    async def mouse_click(
        self,
        page_id: str,
        *,
        x: int,
        y: int,
        button: str = "left",
        count: int = 1,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def mouse_drag(self, page_id: str, *, x1: int, y1: int, x2: int, y2: int) -> dict[str, Any]: ...

    @abstractmethod
    async def mouse_down(self, page_id: str, *, button: str = "left") -> dict[str, Any]: ...

    @abstractmethod
    async def mouse_up(self, page_id: str, *, button: str = "left") -> dict[str, Any]: ...

    @abstractmethod
    async def screenshot(self, page_id: str, *, path: str, full_page: bool = False) -> dict[str, Any]: ...

    @abstractmethod
    async def save_pdf(self, page_id: str, *, path: str) -> dict[str, Any]: ...

    @abstractmethod
    async def setup_dialog_handler(
        self,
        page_id: str,
        *,
        default_action: str = "accept",
        default_prompt_text: str | None = None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def handle_dialog(
        self,
        page_id: str,
        *,
        accept: bool,
        prompt_text: str | None = None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def remove_dialog_handler(self, page_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def start_tracing(
        self,
        page_id: str,
        *,
        screenshots: bool = True,
        snapshots: bool = True,
        sources: bool = False,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def add_trace_chunk(self, page_id: str, *, title: str | None = None) -> dict[str, Any]: ...

    @abstractmethod
    async def stop_tracing(self, page_id: str, *, path: str | None = None) -> dict[str, Any]: ...

    @abstractmethod
    async def start_video(self, page_id: str, *, width: int | None = None, height: int | None = None) -> dict[str, Any]: ...

    @abstractmethod
    async def stop_video(self, page_id: str, *, path: str | None = None) -> dict[str, Any]: ...
