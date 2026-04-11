from __future__ import annotations

import asyncio
import io
import zipfile
from pathlib import Path

from browser_cli.drivers.extension_driver import ExtensionDriver
from browser_cli.errors import OperationFailedError
from browser_cli.extension.protocol import ExtensionHello, REQUIRED_EXTENSION_CAPABILITIES
from browser_cli.refs.models import LocatorSpec


class _FakeSession:
    def __init__(self, hello: ExtensionHello) -> None:
        self.hello = hello
        self.requests: list[tuple[str, dict]] = []

    async def send_request(self, action: str, payload: dict) -> dict:
        self.requests.append((action, dict(payload)))
        if action == "open-tab":
            return {"tab_id": 9, "url": payload.get("url") or "about:blank", "title": "Example"}
        if action == "screenshot":
            return {
                "_artifacts": [
                    {
                        "artifact_kind": "screenshot",
                        "filename": "page_0001.png",
                        "page_id": "page_0001",
                        "metadata": {"full_page": True},
                        "content": b"png-bytes",
                    }
                ]
            }
        if action == "pdf":
            return {
                "_artifacts": [
                    {
                        "artifact_kind": "pdf",
                        "filename": "page_0001.pdf",
                        "page_id": "page_0001",
                        "metadata": {},
                        "content": b"%PDF-1.4",
                    }
                ]
            }
        if action == "options":
            return {"options": ["One", "Two"]}
        if action == "cookies-clear":
            return {"cleared": 2}
        if action == "wait-network":
            return {"network_idle": True}
        if action == "verify-visible":
            return {"passed": True}
        if action == "trace-stop":
            zip_bytes = io.BytesIO()
            with zipfile.ZipFile(zip_bytes, "w") as archive:
                archive.writestr("trace.trace", "[]")
                archive.writestr("trace.metadata.json", "{}")
            return {
                "_artifacts": [
                    {
                        "artifact_kind": "trace",
                        "filename": "trace.zip",
                        "page_id": "page_0001",
                        "metadata": {"requested_path": payload.get("path")},
                        "content": zip_bytes.getvalue(),
                    }
                ]
            }
        if action == "video-stop":
            return {"recording": False, "path": payload.get("path"), "deferred": True}
        if action == "close-tab":
            return {
                "url": "https://example.com",
                "title": "Example",
                "_artifacts": [
                    {
                        "artifact_kind": "video",
                        "filename": "page_0001.webm",
                        "page_id": "page_0001",
                        "metadata": {"requested_path": "video-demo.webm"},
                        "content": b"video-bytes",
                    }
                ],
            }
        if action == "workspace-close":
            return {
                "_artifacts": [
                    {
                        "artifact_kind": "video",
                        "filename": "page_0002.webm",
                        "page_id": "page_0002",
                        "metadata": {"requested_path": "stop-video.webm"},
                        "content": b"video-stop-bytes",
                    }
                ]
            }
        if action == "page-summary":
            return {"url": "https://example.com", "title": "Example"}
        return {"ok": True, "result": {"echo": action}}


class _FakeHub:
    def __init__(self, session: _FakeSession | None) -> None:
        self.session = session

    async def ensure_started(self) -> None:
        return None


class _FailingStopSession(_FakeSession):
    async def send_request(self, action: str, payload: dict) -> dict:
        if action == "workspace-close":
            raise OperationFailedError("No tab with id: 685338567.")
        return await super().send_request(action, payload)


def _hello(*, capabilities: set[str] | None = None) -> ExtensionHello:
    return ExtensionHello.from_message(
        {
            "protocol_version": "1",
            "extension_version": "0.1.0-test",
            "browser_name": "Chrome",
            "browser_version": "146",
            "capabilities": sorted(capabilities or set(REQUIRED_EXTENSION_CAPABILITIES)),
            "workspace_window_state": {"window_id": 77, "tab_count": 1},
            "extension_instance_id": "ext-test",
        }
    )


def test_extension_driver_health_reports_missing_required_capabilities() -> None:
    hello = _hello(capabilities=set(REQUIRED_EXTENSION_CAPABILITIES) - {"screenshot", "wait-network"})
    driver = ExtensionDriver(_FakeHub(_FakeSession(hello)))

    async def _scenario() -> None:
        health = await driver.health()
        assert health.available is False
        assert health.details["capability_complete"] is False
        assert health.details["missing_capabilities"] == ["screenshot", "wait-network"]

    asyncio.run(_scenario())


def test_extension_driver_routes_representative_actions(tmp_path: Path) -> None:
    session = _FakeSession(_hello())
    driver = ExtensionDriver(_FakeHub(session))
    locator = LocatorSpec(ref="abcd1234", role="button", name="Submit")

    async def _scenario() -> None:
        page = await driver.new_tab(page_id="page_0001", url="https://example.com")
        assert page["page_id"] == "page_0001"

        await driver.evaluate("page_0001", "(() => document.title)()")
        await driver.evaluate_on("page_0001", locator, "(el) => el.textContent")
        await driver.wait_for_network_idle("page_0001", timeout_seconds=12)
        await driver.set_cookie("page_0001", name="sid", value="123", domain="example.com")
        await driver.clear_cookies("page_0001", domain="example.com")
        await driver.verify_visible("page_0001", role="button", name="Submit", timeout_seconds=4)
        await driver.type_text("page_0001", "hello", submit=True)
        await driver.press_key("page_0001", "Enter")
        await driver.key_down("page_0001", "Shift")
        await driver.key_up("page_0001", "Shift")
        await driver.wheel("page_0001", dx=0, dy=600)
        await driver.mouse_move("page_0001", x=10, y=20)
        await driver.mouse_click("page_0001", x=10, y=20, button="left", count=2)
        await driver.mouse_drag("page_0001", x1=1, y1=2, x2=30, y2=40)
        await driver.mouse_down("page_0001", button="left")
        await driver.mouse_up("page_0001", button="left")
        await driver.double_click("page_0001", locator)
        await driver.hover("page_0001", locator)
        await driver.focus("page_0001", locator)
        options = await driver.list_options("page_0001", locator)
        assert options["options"] == ["One", "Two"]

        png_path = tmp_path / "capture"
        pdf_path = tmp_path / "capture-doc"
        screenshot = await driver.screenshot("page_0001", path=str(png_path), full_page=True)
        pdf = await driver.save_pdf("page_0001", path=str(pdf_path))
        trace = await driver.stop_tracing("page_0001", path=str(tmp_path / "trace"))
        await driver.start_video("page_0001", width=800, height=600)
        planned_video = await driver.stop_video("page_0001", path="video-demo")
        close_payload = await driver.close_tab("page_0001")
        page2 = await driver.new_tab(page_id="page_0002", url="https://example.com/two")
        stop_payload = await driver.stop()

        assert Path(screenshot["path"]).read_bytes() == b"png-bytes"
        assert Path(pdf["path"]).read_bytes() == b"%PDF-1.4"
        assert Path(trace["path"]).exists()
        assert planned_video["deferred"] is True
        assert Path(close_payload["video_path"]).read_bytes() == b"video-bytes"
        assert page2["page_id"] == "page_0002"
        assert Path(stop_payload["video_paths"][0]).read_bytes() == b"video-stop-bytes"

    asyncio.run(_scenario())

    actions = [action for action, _payload in session.requests]
    assert actions == [
        "open-tab",
        "eval",
        "eval-on",
        "wait-network",
        "cookie-set",
        "cookies-clear",
        "verify-visible",
        "type",
        "press",
        "key-down",
        "key-up",
        "scroll",
        "mouse-move",
        "mouse-click",
        "mouse-drag",
        "mouse-down",
        "mouse-up",
        "double-click",
        "hover",
        "focus",
        "options",
        "screenshot",
        "pdf",
        "trace-stop",
        "video-start",
        "video-stop",
        "close-tab",
        "open-tab",
        "workspace-close",
    ]


def test_extension_driver_stop_keeps_cleanup_errors_non_fatal() -> None:
    session = _FailingStopSession(_hello())
    driver = ExtensionDriver(_FakeHub(session))

    async def _scenario() -> None:
        await driver.new_tab(page_id="page_0001", url="https://example.com")
        payload = await driver.stop()

        assert payload["closed_pages"] == ["page_0001"]
        assert payload["cleanup_error"] == "No tab with id: 685338567."
        assert payload["video_paths"] == []

    asyncio.run(_scenario())
