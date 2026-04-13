from __future__ import annotations

import asyncio
from dataclasses import dataclass

from browser_cli.daemon.app import BrowserDaemonApp
from browser_cli.daemon.models import DaemonRequest
from browser_cli.daemon.runtime_presentation import build_runtime_presentation


def test_build_runtime_presentation_marks_safe_point_fallback_as_recovering() -> None:
    raw_status = {
        "browser_started": True,
        "active_driver": "extension",
        "pending_rebind": {"target": "playwright", "reason": "extension-disconnected-waiting-command"},
        "extension": {
            "connected": False,
            "capability_complete": False,
            "missing_capabilities": [],
        },
        "workspace_window_state": {
            "window_id": 91,
            "tab_count": 1,
            "managed_tab_count": 1,
            "binding_state": "tracked",
        },
        "tabs": {"count": 1, "busy_count": 0, "records": [], "active_by_agent": {}},
        "last_transition": {},
    }

    presentation = build_runtime_presentation(raw_status)

    assert presentation["overall_state"] == "recovering"
    assert presentation["summary_reason"] == (
        "Extension disconnected; Browser CLI will switch to Playwright at the next safe point."
    )
    assert presentation["available_actions"] == ["refresh-status", "reconnect-extension"]


def test_build_runtime_presentation_marks_workspace_binding_loss_as_degraded() -> None:
    raw_status = {
        "browser_started": True,
        "active_driver": "extension",
        "pending_rebind": None,
        "extension": {
            "connected": True,
            "capability_complete": True,
            "missing_capabilities": [],
        },
        "workspace_window_state": {
            "window_id": 91,
            "tab_count": 0,
            "managed_tab_count": 0,
            "binding_state": "stale",
        },
        "tabs": {"count": 0, "busy_count": 0, "records": [], "active_by_agent": {}},
        "last_transition": {},
    }

    presentation = build_runtime_presentation(raw_status)

    assert presentation["overall_state"] == "degraded"
    assert presentation["available_actions"] == [
        "refresh-status",
        "reconnect-extension",
        "rebuild-workspace-binding",
    ]
    assert presentation["workspace_state"]["binding_state"] == "stale"


def test_build_runtime_presentation_marks_playwright_fallback_as_degraded() -> None:
    raw_status = {
        "browser_started": True,
        "active_driver": "playwright",
        "pending_rebind": None,
        "extension": {
            "connected": False,
            "capability_complete": False,
            "missing_capabilities": [],
        },
        "workspace_window_state": {
            "window_id": None,
            "tab_count": 0,
            "managed_tab_count": 0,
            "binding_state": "absent",
        },
        "tabs": {"count": 0, "busy_count": 0, "records": [], "active_by_agent": {}},
        "last_transition": {},
    }

    presentation = build_runtime_presentation(raw_status)

    assert presentation["overall_state"] == "degraded"
    assert presentation["available_actions"] == ["refresh-status", "reconnect-extension"]
    assert presentation["summary_reason"] == (
        "Browser CLI is running on Playwright instead of extension mode."
    )


def test_build_runtime_presentation_marks_extension_rebind_as_recovering() -> None:
    raw_status = {
        "browser_started": True,
        "active_driver": "playwright",
        "pending_rebind": {"target": "extension", "reason": "extension-connected"},
        "extension": {
            "connected": True,
            "capability_complete": True,
            "missing_capabilities": [],
        },
        "workspace_window_state": {
            "window_id": 91,
            "tab_count": 1,
            "managed_tab_count": 1,
            "binding_state": "tracked",
        },
        "tabs": {"count": 1, "busy_count": 0, "records": [], "active_by_agent": {}},
        "last_transition": {},
    }

    presentation = build_runtime_presentation(raw_status)

    assert presentation["overall_state"] == "recovering"
    assert presentation["summary_reason"] == (
        "Extension reconnected; Browser CLI will restore extension mode at the next safe point."
    )
    assert presentation["available_actions"] == ["refresh-status", "reconnect-extension"]


def test_build_runtime_presentation_marks_absent_workspace_binding_as_degraded() -> None:
    raw_status = {
        "browser_started": True,
        "active_driver": "extension",
        "pending_rebind": None,
        "extension": {
            "connected": True,
            "capability_complete": True,
            "missing_capabilities": [],
        },
        "workspace_window_state": {
            "window_id": None,
            "tab_count": 0,
            "managed_tab_count": 0,
            "binding_state": "absent",
        },
        "tabs": {"count": 0, "busy_count": 0, "records": [], "active_by_agent": {}},
        "last_transition": {},
    }

    presentation = build_runtime_presentation(raw_status)

    assert presentation["overall_state"] == "degraded"
    assert presentation["available_actions"] == [
        "refresh-status",
        "reconnect-extension",
        "rebuild-workspace-binding",
    ]
    assert presentation["summary_reason"] == (
        "Browser CLI no longer has a trusted extension workspace binding."
    )


@dataclass
class _FakeTabRecord:
    page_id: str
    owner_agent_id: str
    url: str
    title: str
    busy: object | None
    last_snapshot_id: str | None


class _FakeBrowserService:
    active_driver_name = "extension"

    async def runtime_status(self, *, warmup: bool = False) -> dict[str, object]:
        assert warmup is True
        return {
            "browser_started": True,
            "active_driver": "extension",
            "pending_rebind": None,
            "extension": {
                "connected": True,
                "capability_complete": True,
                "missing_capabilities": [],
            },
            "workspace_window_state": {
                "window_id": 91,
                "tab_count": 1,
                "managed_tab_count": 1,
                "binding_state": "tracked",
            },
            "last_transition": {},
        }


class _FakeTabs:
    async def snapshot_state(self) -> tuple[list[_FakeTabRecord], dict[str, str]]:
        return (
            [
                _FakeTabRecord(
                    page_id="page-1",
                    owner_agent_id="agent-a",
                    url="https://example.com",
                    title="Example",
                    busy=None,
                    last_snapshot_id=None,
                )
            ],
            {"agent-a": "page-1"},
        )


class _FakeState:
    def __init__(self) -> None:
        self.browser_service = _FakeBrowserService()
        self.tabs = _FakeTabs()


def test_handle_runtime_status_returns_raw_tabs_and_presentation() -> None:
    async def _scenario() -> None:
        app = BrowserDaemonApp(state=_FakeState())  # type: ignore[arg-type]
        response = await app._handle_runtime_status(  # noqa: SLF001
            DaemonRequest(
                action="runtime-status",
                args={"warmup": True},
                agent_id="agent-a",
                request_id="req-1",
            )
        )
        assert response["tabs"] == {
            "count": 1,
            "busy_count": 0,
            "active_by_agent": {"agent-a": "page-1"},
            "records": [
                {
                    "page_id": "page-1",
                    "owner_agent_id": "agent-a",
                    "url": "https://example.com",
                    "title": "Example",
                    "busy": False,
                    "last_snapshot_id": None,
                }
            ],
        }
        assert response["presentation"]["overall_state"] == "healthy"
        assert response["presentation"]["workspace_state"]["busy_tab_count"] == 0

    asyncio.run(_scenario())
