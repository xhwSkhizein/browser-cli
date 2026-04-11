"""Playwright-backed driver adapter."""

from __future__ import annotations

from browser_cli.browser.service import BrowserService as PlaywrightBrowserService
from browser_cli.profiles.discovery import ChromeEnvironment
from browser_cli.refs.models import LocatorSpec, SnapshotInput

from .base import BrowserDriver
from .models import DriverHealth, TabState


class PlaywrightDriver(BrowserDriver):
    name = "playwright"

    def __init__(
        self,
        chrome_environment: ChromeEnvironment | None = None,
        *,
        headless: bool | None = None,
    ) -> None:
        self._service = PlaywrightBrowserService(chrome_environment=chrome_environment, headless=headless)

    @property
    def chrome_environment(self) -> ChromeEnvironment | None:
        return self._service.chrome_environment

    def configure_environment(self, chrome_environment: ChromeEnvironment) -> None:
        self._service.configure_environment(chrome_environment)

    @staticmethod
    def build_search_url(query: str, engine: str = "duckduckgo") -> str:
        return PlaywrightBrowserService._build_search_url(query, engine)

    async def ensure_started(self) -> None:
        await self._service.ensure_started()

    async def stop(self) -> dict[str, Any]:
        return await self._service.stop()

    async def health(self) -> DriverHealth:
        environment = self.chrome_environment
        return DriverHealth(
            name=self.name,
            available=True,
            details={
                "chrome_environment": (
                    environment.source if environment is not None else None
                ),
                "user_data_dir": str(environment.user_data_dir) if environment is not None else None,
                "profile_directory": environment.profile_directory if environment is not None else None,
            },
        )

    async def new_tab(
        self,
        *,
        page_id: str,
        url: str | None = None,
        wait_until: str = "load",
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        return await self._service.new_tab(
            page_id=page_id,
            url=url,
            wait_until=wait_until,
            timeout_seconds=timeout_seconds,
        )

    async def close_tab(self, page_id: str) -> dict[str, Any]:
        return await self._service.close_tab(page_id)

    async def list_tabs(self) -> list[TabState]:
        results: list[TabState] = []
        for page_id in sorted(self._service._pages.keys()):  # noqa: SLF001
            summary = await self._service.get_page_summary(page_id)
            results.append(
                TabState(
                    page_id=page_id,
                    url=str(summary["url"]),
                    title=str(summary["title"]),
                    active=False,
                )
            )
        return results

    async def switch_tab(self, page_id: str) -> dict[str, Any]:
        page = self._service._require_page(page_id)  # noqa: SLF001
        await page.bring_to_front()
        return await self._service.get_page_summary(page_id)

    async def get_page_summary(self, page_id: str) -> dict[str, Any]:
        return await self._service.get_page_summary(page_id)

    async def get_page_info(self, page_id: str) -> dict[str, Any]:
        return await self._service.get_page_info(page_id)

    async def capture_html(self, page_id: str) -> dict[str, Any]:
        return await self._service.capture_html(page_id)

    async def capture_snapshot_input(
        self,
        page_id: str,
        *,
        interactive: bool = False,
        full_page: bool = True,
    ) -> SnapshotInput:
        return await self._service.capture_snapshot_input(
            page_id,
            interactive=interactive,
            full_page=full_page,
        )

    async def navigate(
        self,
        page_id: str,
        url: str,
        *,
        wait_until: str = "load",
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        return await self._service.navigate(
            page_id,
            url,
            wait_until=wait_until,
            timeout_seconds=timeout_seconds,
        )

    async def reload(
        self,
        page_id: str,
        *,
        wait_until: str = "load",
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        return await self._service.reload(page_id, wait_until=wait_until, timeout_seconds=timeout_seconds)

    async def go_back(self, page_id: str) -> dict[str, Any]:
        return await self._service.go_back(page_id)

    async def go_forward(self, page_id: str) -> dict[str, Any]:
        return await self._service.go_forward(page_id)

    async def resize(self, page_id: str, *, width: int, height: int) -> dict[str, Any]:
        return await self._service.resize(page_id, width=width, height=height)

    async def click(self, page_id: str, locator: LocatorSpec) -> dict[str, Any]:
        return await self._service.click_locator(page_id, locator)

    async def double_click(self, page_id: str, locator: LocatorSpec) -> dict[str, Any]:
        return await self._service.double_click_locator(page_id, locator)

    async def hover(self, page_id: str, locator: LocatorSpec) -> dict[str, Any]:
        return await self._service.hover_locator(page_id, locator)

    async def focus(self, page_id: str, locator: LocatorSpec) -> dict[str, Any]:
        return await self._service.focus_locator(page_id, locator)

    async def fill(
        self,
        page_id: str,
        locator: LocatorSpec,
        text: str,
        *,
        submit: bool = False,
    ) -> dict[str, Any]:
        return await self._service.fill_locator(page_id, locator, text, submit=submit)

    async def select_option(self, page_id: str, locator: LocatorSpec, text: str) -> dict[str, Any]:
        return await self._service.select_locator(page_id, locator, text)

    async def list_options(self, page_id: str, locator: LocatorSpec) -> dict[str, Any]:
        return await self._service.list_locator_options(page_id, locator)

    async def check(self, page_id: str, locator: LocatorSpec, *, checked: bool) -> dict[str, Any]:
        return await self._service.set_checked_locator(page_id, locator, checked=checked)

    async def scroll_to(self, page_id: str, locator: LocatorSpec) -> dict[str, Any]:
        return await self._service.scroll_to_locator(page_id, locator)

    async def drag(self, page_id: str, start_locator: LocatorSpec, end_locator: LocatorSpec) -> dict[str, Any]:
        return await self._service.drag_between_locators(page_id, start_locator, end_locator)

    async def upload(self, page_id: str, locator: LocatorSpec, file_path: str) -> dict[str, Any]:
        return await self._service.upload_to_locator(page_id, locator, file_path)

    async def evaluate(self, page_id: str, code: str) -> dict[str, Any]:
        return await self._service.evaluate(page_id, code)

    async def evaluate_on(self, page_id: str, locator: LocatorSpec, code: str) -> dict[str, Any]:
        return await self._service.evaluate_on_locator(page_id, locator, code)

    async def wait(
        self,
        page_id: str,
        *,
        seconds: float | None = None,
        text: str | None = None,
        gone: bool = False,
        exact: bool = False,
        ) -> dict[str, Any]:
        return await self._service.wait(
            page_id,
            seconds=seconds,
            text=text,
            gone=gone,
            exact=exact,
        )

    async def wait_for_network_idle(self, page_id: str, *, timeout_seconds: float = 30.0) -> dict[str, Any]:
        return await self._service.wait_for_network_idle(page_id, timeout_seconds=timeout_seconds)

    async def start_console_capture(self, page_id: str) -> dict[str, Any]:
        return await self._service.start_console_capture(page_id)

    async def get_console_messages(
        self,
        page_id: str,
        *,
        message_type: str | None = None,
        clear: bool = True,
    ) -> dict[str, Any]:
        return await self._service.get_console_messages(page_id, message_type=message_type, clear=clear)

    async def stop_console_capture(self, page_id: str) -> dict[str, Any]:
        return await self._service.stop_console_capture(page_id)

    async def start_network_capture(self, page_id: str) -> dict[str, Any]:
        return await self._service.start_network_capture(page_id)

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
        return await self._service.wait_for_network_record(
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
        return await self._service.get_network_records(
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
        return await self._service.stop_network_capture(page_id)

    async def get_cookies(
        self,
        page_id: str,
        *,
        name: str | None = None,
        domain: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        return await self._service.get_cookies(page_id, name=name, domain=domain, path=path)

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
        return await self._service.set_cookie(
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
        return await self._service.clear_cookies(page_id, name=name, domain=domain, path=path)

    async def save_storage_state(self, page_id: str, *, path: str | None = None) -> dict[str, Any]:
        return await self._service.save_storage_state(page_id, path=path)

    async def load_storage_state(self, page_id: str, *, path: str) -> dict[str, Any]:
        return await self._service.load_storage_state(page_id, path=path)

    async def verify_text(
        self,
        page_id: str,
        *,
        text: str,
        exact: bool = False,
        timeout_seconds: float = 5.0,
    ) -> dict[str, Any]:
        return await self._service.verify_text(
            page_id,
            text=text,
            exact=exact,
            timeout_seconds=timeout_seconds,
        )

    async def verify_url(self, page_id: str, *, expected: str, exact: bool = False) -> dict[str, Any]:
        return await self._service.verify_url(page_id, expected=expected, exact=exact)

    async def verify_title(self, page_id: str, *, expected: str, exact: bool = False) -> dict[str, Any]:
        return await self._service.verify_title(page_id, expected=expected, exact=exact)

    async def verify_visible(
        self,
        page_id: str,
        *,
        role: str,
        name: str,
        timeout_seconds: float = 5.0,
    ) -> dict[str, Any]:
        return await self._service.verify_visible(
            page_id,
            role=role,
            name=name,
            timeout_seconds=timeout_seconds,
        )

    async def verify_state(self, page_id: str, *, locator: LocatorSpec, state: str) -> dict[str, Any]:
        return await self._service.verify_state_locator(page_id, locator, state=state)

    async def verify_value(self, page_id: str, *, locator: LocatorSpec, expected: str) -> dict[str, Any]:
        return await self._service.verify_value_locator(page_id, locator, expected=expected)

    async def type_text(self, page_id: str, text: str, *, submit: bool = False) -> dict[str, Any]:
        return await self._service.type_text(page_id, text, submit=submit)

    async def press_key(self, page_id: str, key: str) -> dict[str, Any]:
        return await self._service.press_key(page_id, key)

    async def key_down(self, page_id: str, key: str) -> dict[str, Any]:
        return await self._service.key_down(page_id, key)

    async def key_up(self, page_id: str, key: str) -> dict[str, Any]:
        return await self._service.key_up(page_id, key)

    async def wheel(self, page_id: str, *, dx: int = 0, dy: int = 700) -> dict[str, Any]:
        return await self._service.wheel(page_id, dx=dx, dy=dy)

    async def mouse_move(self, page_id: str, *, x: int, y: int) -> dict[str, Any]:
        return await self._service.mouse_move(page_id, x=x, y=y)

    async def mouse_click(
        self,
        page_id: str,
        *,
        x: int,
        y: int,
        button: str = "left",
        count: int = 1,
    ) -> dict[str, Any]:
        return await self._service.mouse_click(page_id, x=x, y=y, button=button, count=count)

    async def mouse_drag(self, page_id: str, *, x1: int, y1: int, x2: int, y2: int) -> dict[str, Any]:
        return await self._service.mouse_drag(page_id, x1=x1, y1=y1, x2=x2, y2=y2)

    async def mouse_down(self, page_id: str, *, button: str = "left") -> dict[str, Any]:
        return await self._service.mouse_down(page_id, button=button)

    async def mouse_up(self, page_id: str, *, button: str = "left") -> dict[str, Any]:
        return await self._service.mouse_up(page_id, button=button)

    async def screenshot(self, page_id: str, *, path: str, full_page: bool = False) -> dict[str, Any]:
        return await self._service.screenshot(page_id, path=path, full_page=full_page)

    async def save_pdf(self, page_id: str, *, path: str) -> dict[str, Any]:
        return await self._service.save_pdf(page_id, path=path)

    async def setup_dialog_handler(
        self,
        page_id: str,
        *,
        default_action: str = "accept",
        default_prompt_text: str | None = None,
    ) -> dict[str, Any]:
        return await self._service.setup_dialog_handler(
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
        return await self._service.handle_dialog(page_id, accept=accept, prompt_text=prompt_text)

    async def remove_dialog_handler(self, page_id: str) -> dict[str, Any]:
        return await self._service.remove_dialog_handler(page_id)

    async def start_tracing(
        self,
        page_id: str,
        *,
        screenshots: bool = True,
        snapshots: bool = True,
        sources: bool = False,
    ) -> dict[str, Any]:
        return await self._service.start_tracing(
            page_id,
            screenshots=screenshots,
            snapshots=snapshots,
            sources=sources,
        )

    async def add_trace_chunk(self, page_id: str, *, title: str | None = None) -> dict[str, Any]:
        return await self._service.add_trace_chunk(page_id, title=title)

    async def stop_tracing(self, page_id: str, *, path: str | None = None) -> dict[str, Any]:
        return await self._service.stop_tracing(page_id, path=path)

    async def start_video(self, page_id: str, *, width: int | None = None, height: int | None = None) -> dict[str, Any]:
        return await self._service.start_video(page_id, width=width, height=height)

    async def stop_video(self, page_id: str, *, path: str | None = None) -> dict[str, Any]:
        return await self._service.stop_video(page_id, path=path)
