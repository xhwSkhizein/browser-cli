from __future__ import annotations

import asyncio
import io
import zipfile
from pathlib import Path

from browser_cli.drivers.extension_driver import ExtensionDriver
from browser_cli.errors import OperationFailedError
from browser_cli.extension.protocol import REQUIRED_EXTENSION_CAPABILITIES, ExtensionHello
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
        if action == "network-wait":
            return {
                "record": {
                    "request_id": "page_0001-req-0001",
                    "url": "https://example.com/api/ping",
                    "method": "GET",
                    "resource_type": "fetch",
                    "status": 200,
                    "ok": True,
                    "request_headers": {"accept": "application/json"},
                    "request_post_data": None,
                    "response_headers": {"content-type": "application/json"},
                    "mime_type": "application/json",
                    "started_at": 1.0,
                    "ended_at": 1.1,
                    "duration_ms": 100.0,
                    "failed": False,
                    "failure_reason": None,
                    "body": {
                        "kind": "text",
                        "text": '{"ok":true}',
                        "bytes": 11,
                        "truncated": False,
                    },
                }
            }
        if action == "network":
            return {
                "records": [
                    {
                        "request_id": "page_0001-req-0002",
                        "url": "https://example.com/api/ping",
                        "method": "GET",
                        "resource_type": "fetch",
                        "status": 200,
                        "ok": True,
                        "request_headers": {"accept": "application/json"},
                        "request_post_data": None,
                        "response_headers": {"content-type": "application/json"},
                        "mime_type": "application/json",
                        "started_at": 2.0,
                        "ended_at": 2.1,
                        "duration_ms": 100.0,
                        "failed": False,
                        "failure_reason": None,
                        "body": {
                            "kind": "text",
                            "text": '{"ok":true}',
                            "bytes": 11,
                            "truncated": False,
                        },
                    }
                ]
            }
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
        if action == "workspace-rebuild-binding":
            return {
                "rebuilt": True,
                "window_id": 77,
                "tab_count": 1,
                "managed_tab_count": 1,
                "binding_state": "tracked",
                "_artifacts": [
                    {
                        "artifact_kind": "video",
                        "filename": "page_0003.webm",
                        "page_id": "page_0003",
                        "metadata": {"requested_path": "rebuild-video.webm"},
                        "content": b"video-rebuild-bytes",
                    }
                ],
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
    hello = _hello(
        capabilities=set(REQUIRED_EXTENSION_CAPABILITIES) - {"screenshot", "wait-network"}
    )
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
        waited_record = await driver.wait_for_network_record(
            "page_0001",
            url_contains="/api/ping",
            mime_contains="json",
            timeout_seconds=8,
        )
        records = await driver.get_network_records(
            "page_0001", url_contains="/api/ping", include_static=True, clear=False
        )
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
        assert waited_record["record"]["body"]["text"] == '{"ok":true}'
        assert records["records"][0]["mime_type"] == "application/json"
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
        "network-wait",
        "network",
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


def test_extension_driver_rebuild_workspace_binding_flushes_pending_video_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / ".browser-cli-runtime"))
    session = _FakeSession(_hello())
    driver = ExtensionDriver(_FakeHub(session))

    async def _scenario() -> None:
        payload = await driver.rebuild_workspace_binding()
        assert payload["rebuilt"] is True
        assert payload["workspace_window_state"]["binding_state"] == "tracked"
        assert Path(payload["video_paths"][0]).read_bytes() == b"video-rebuild-bytes"

    asyncio.run(_scenario())

    actions = [action for action, _payload in session.requests]
    assert actions == ["workspace-rebuild-binding"]


def test_extension_protocol_js_lists_workspace_runtime_capabilities() -> None:
    protocol_js = (
        Path(__file__).resolve().parents[2] / "browser-cli-extension" / "src" / "protocol.js"
    ).read_text(encoding="utf-8")
    assert "'workspace-status'" in protocol_js
    assert "'workspace-rebuild-binding'" in protocol_js
