from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from browser_cli import error_codes
from browser_cli.daemon.app import BrowserDaemonApp
from browser_cli.daemon.models import DaemonRequest


class _FakeTabs:
    @asynccontextmanager
    async def claim_active_tab(self, **_kwargs):
        yield SimpleNamespace(page_id="page_0001")

    async def update_tab(self, *_args, **_kwargs) -> None:
        return None


class _FakeBrowserService:
    async def begin_command(self, _action: str) -> None:
        return None

    async def end_command(self) -> dict[str, str]:
        return {"driver": "playwright"}

    @property
    def active_driver_name(self) -> str:
        return "playwright"

    @property
    def chrome_environment(self):
        return None

    async def get_page_summary(self, _page_id: str) -> dict[str, str]:
        return {"url": "https://example.com", "title": "Example"}

    async def mouse_click(
        self,
        page_id: str,
        *,
        x: int,
        y: int,
        button: str,
        count: int,
    ) -> dict[str, object]:
        return {"page_id": page_id, "x": x, "y": y, "button": button, "count": count}

    async def mouse_drag(
        self,
        page_id: str,
        *,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
    ) -> dict[str, object]:
        return {"page_id": page_id, "x1": x1, "y1": y1, "x2": x2, "y2": y2}

    async def resize(self, page_id: str, *, width: int, height: int) -> dict[str, object]:
        return {"page_id": page_id, "width": width, "height": height}

    async def wait_for_network_idle(
        self, page_id: str, *, timeout_seconds: float = 30.0
    ) -> dict[str, object]:
        return {"page_id": page_id, "timeout_seconds": timeout_seconds}


class _FakeState:
    def __init__(self) -> None:
        self.tabs = _FakeTabs()
        self.browser_service = _FakeBrowserService()


def _execute(request: DaemonRequest) -> dict[str, object]:
    async def _scenario() -> dict[str, object]:
        app = BrowserDaemonApp(state=_FakeState())  # type: ignore[arg-type]
        response = await app.execute(request)
        return response.to_dict()

    return asyncio.run(_scenario())


def test_mouse_click_missing_x_returns_invalid_input() -> None:
    payload = _execute(
        DaemonRequest(
            action="mouse-click",
            args={"y": 10},
            agent_id="agent-a",
            request_id="req-1",
        )
    )

    assert payload["ok"] is False
    assert payload["error_code"] == error_codes.INVALID_INPUT
    assert payload["error_message"] == "x is required."


def test_mouse_drag_invalid_coordinate_returns_invalid_input() -> None:
    payload = _execute(
        DaemonRequest(
            action="mouse-drag",
            args={"x1": 1, "y1": 2, "x2": "bad", "y2": 4},
            agent_id="agent-a",
            request_id="req-2",
        )
    )

    assert payload["ok"] is False
    assert payload["error_code"] == error_codes.INVALID_INPUT
    assert payload["error_message"] == "x2 must be an integer."


def test_wait_network_invalid_timeout_returns_invalid_input() -> None:
    payload = _execute(
        DaemonRequest(
            action="wait-network",
            args={"timeout": "slow"},
            agent_id="agent-a",
            request_id="req-3",
        )
    )

    assert payload["ok"] is False
    assert payload["error_code"] == error_codes.INVALID_INPUT
    assert payload["error_message"] == "timeout must be a number."


def test_resize_non_positive_values_keep_handler_level_constraint() -> None:
    payload = _execute(
        DaemonRequest(
            action="resize",
            args={"width": 0, "height": 100},
            agent_id="agent-a",
            request_id="req-4",
        )
    )

    assert payload["ok"] is False
    assert payload["error_code"] == error_codes.INVALID_INPUT
    assert payload["error_message"] == "width and height must be positive integers."


def test_mouse_click_successfully_parses_integer_fields() -> None:
    payload = _execute(
        DaemonRequest(
            action="mouse-click",
            args={"x": "12", "y": "14", "count": "2"},
            agent_id="agent-a",
            request_id="req-5",
        )
    )

    assert payload["ok"] is True
    assert payload["data"] == {
        "page_id": "page_0001",
        "x": 12,
        "y": 14,
        "button": "left",
        "count": 2,
    }
