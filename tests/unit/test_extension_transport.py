from __future__ import annotations

import asyncio
import base64
import json
import socket
from pathlib import Path

import pytest
import websockets

from browser_cli.constants import APP_HOME_ENV, EXTENSION_PORT_ENV, get_app_paths
from browser_cli.errors import OperationFailedError
from browser_cli.extension.protocol import PROTOCOL_VERSION, REQUIRED_EXTENSION_CAPABILITIES
from browser_cli.extension.session import ExtensionHub


def _unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_extension_hub_accepts_handshake_and_round_trips_requests(
    monkeypatch, tmp_path: Path
) -> None:
    async def _scenario() -> None:
        monkeypatch.setenv(APP_HOME_ENV, str(tmp_path / ".browser-cli-runtime"))
        monkeypatch.setenv(EXTENSION_PORT_ENV, str(_unused_port()))

        hub = ExtensionHub()
        await hub.ensure_started()
        app_paths = get_app_paths()

        async with websockets.connect(app_paths.extension_ws_url) as websocket:
            await websocket.send(
                json.dumps(
                    {
                        "type": "hello",
                        "protocol_version": PROTOCOL_VERSION,
                        "extension_version": "0.1.0-test",
                        "browser_name": "Chrome",
                        "browser_version": "146",
                        "capabilities": sorted(REQUIRED_EXTENSION_CAPABILITIES),
                        "workspace_window_state": {"connected": True},
                        "extension_instance_id": "ext-test",
                    }
                )
            )

            session = await hub.wait_for_session(timeout_seconds=1.0)
            assert session is not None
            assert session.hello.is_compatible() is True
            assert session.hello.has_required_capabilities() is True
            assert session.hello.missing_required_capabilities() == []

            request_task = asyncio.create_task(session.send_request("ping", {"value": 7}))
            raw_request = json.loads(await websocket.recv())
            assert raw_request["type"] == "request"
            assert raw_request["action"] == "ping"
            assert raw_request["payload"] == {"value": 7}

            await websocket.send(
                json.dumps(
                    {
                        "type": "response",
                        "id": raw_request["id"],
                        "ok": True,
                        "data": {"pong": 7},
                    }
                )
            )
            assert await request_task == {"pong": 7}

        await hub.wait_for_change()
        assert hub.session is None
        await hub.stop()

    asyncio.run(_scenario())


def test_extension_hub_answers_http_probe_without_websocket_upgrade(
    monkeypatch, tmp_path: Path
) -> None:
    async def _scenario() -> None:
        monkeypatch.setenv(APP_HOME_ENV, str(tmp_path / ".browser-cli-runtime"))
        monkeypatch.setenv(EXTENSION_PORT_ENV, str(_unused_port()))

        hub = ExtensionHub()
        await hub.ensure_started()
        app_paths = get_app_paths()

        reader, writer = await asyncio.open_connection(
            app_paths.extension_host, app_paths.extension_port
        )
        writer.write(
            (
                f"GET /ext HTTP/1.1\r\n"
                f"Host: {app_paths.extension_host}:{app_paths.extension_port}\r\n"
                "Connection: keep-alive\r\n"
                "Accept: */*\r\n"
                "\r\n"
            ).encode("ascii")
        )
        await writer.drain()
        response = await reader.read(-1)
        writer.close()
        await writer.wait_closed()

        lowered = response.lower()
        assert b"426 upgrade required" in lowered
        assert b"upgrade: websocket" in lowered
        assert b"expects a websocket upgrade" in lowered

        await hub.stop()

    asyncio.run(_scenario())


def test_extension_hub_serves_runtime_status_snapshot(monkeypatch, tmp_path: Path) -> None:
    async def _scenario() -> None:
        monkeypatch.setenv(APP_HOME_ENV, str(tmp_path / ".browser-cli-runtime"))
        monkeypatch.setenv(EXTENSION_PORT_ENV, str(_unused_port()))

        hub = ExtensionHub()
        hub.set_status_provider(
            lambda: {"presentation": {"overall_state": "healthy", "summary_reason": "ok"}}
        )
        await hub.ensure_started()
        app_paths = get_app_paths()

        reader, writer = await asyncio.open_connection(
            app_paths.extension_host, app_paths.extension_port
        )
        writer.write(
            (
                f"GET /ext/runtime-status HTTP/1.1\r\n"
                f"Host: {app_paths.extension_host}:{app_paths.extension_port}\r\n"
                "Connection: close\r\n"
                "Accept: application/json\r\n"
                "\r\n"
            ).encode("ascii")
        )
        await writer.drain()
        response = await reader.read(-1)
        writer.close()
        await writer.wait_closed()

        lowered = response.lower()
        assert b"200 ok" in lowered
        assert b"application/json" in lowered
        assert b'"overall_state": "healthy"' in response

        await hub.stop()

    asyncio.run(_scenario())


def test_extension_hub_fetches_workspace_rebuild(monkeypatch, tmp_path: Path) -> None:
    async def _scenario() -> None:
        monkeypatch.setenv(APP_HOME_ENV, str(tmp_path / ".browser-cli-runtime"))
        monkeypatch.setenv(EXTENSION_PORT_ENV, str(_unused_port()))

        hub = ExtensionHub()
        hub.set_status_provider(lambda: {"presentation": {"overall_state": "degraded"}})
        hub.set_workspace_rebuild_handler(
            lambda: {
                "rebuilt": True,
                "presentation": {"overall_state": "healthy"},
            }
        )
        await hub.ensure_started()
        app_paths = get_app_paths()

        reader, writer = await asyncio.open_connection(
            app_paths.extension_host, app_paths.extension_port
        )
        writer.write(
            (
                f"GET /ext/workspace-rebuild HTTP/1.1\r\n"
                f"Host: {app_paths.extension_host}:{app_paths.extension_port}\r\n"
                "Connection: close\r\n"
                "Accept: application/json\r\n"
                "\r\n"
            ).encode("ascii")
        )
        await writer.drain()
        response = await reader.read(-1)
        writer.close()
        await writer.wait_closed()

        lowered = response.lower()
        assert b"200 ok" in lowered
        assert b"application/json" in lowered
        assert b'"rebuilt": true' in lowered
        assert b'"overall_state": "healthy"' in response

        await hub.stop()

    asyncio.run(_scenario())


def test_extension_session_collects_chunked_artifacts(monkeypatch, tmp_path: Path) -> None:
    async def _scenario() -> None:
        monkeypatch.setenv(APP_HOME_ENV, str(tmp_path / ".browser-cli-runtime"))
        monkeypatch.setenv(EXTENSION_PORT_ENV, str(_unused_port()))

        hub = ExtensionHub()
        await hub.ensure_started()
        app_paths = get_app_paths()

        async with websockets.connect(app_paths.extension_ws_url) as websocket:
            await websocket.send(
                json.dumps(
                    {
                        "type": "hello",
                        "protocol_version": PROTOCOL_VERSION,
                        "extension_version": "0.1.0-test",
                        "browser_name": "Chrome",
                        "browser_version": "146",
                        "capabilities": sorted(REQUIRED_EXTENSION_CAPABILITIES),
                        "workspace_window_state": {"connected": True},
                        "extension_instance_id": "ext-test",
                    }
                )
            )
            session = await hub.wait_for_session(timeout_seconds=1.0)
            assert session is not None

            request_task = asyncio.create_task(
                session.send_request("screenshot", {"full_page": True})
            )
            raw_request = json.loads(await websocket.recv())
            request_id = raw_request["id"]

            await websocket.send(
                json.dumps(
                    {
                        "type": "response",
                        "id": request_id,
                        "ok": True,
                        "data": {"ack": True},
                    }
                )
            )
            content = b"chunked-image"
            encoded = base64.b64encode(content).decode("ascii")
            await websocket.send(
                json.dumps(
                    {
                        "type": "artifact-begin",
                        "request_id": request_id,
                        "artifact_id": "artifact-1",
                        "artifact_kind": "screenshot",
                        "mime_type": "image/png",
                        "encoding": "base64",
                        "filename": "page.png",
                        "page_id": "page_0001",
                        "metadata": {"full_page": True},
                    }
                )
            )
            await websocket.send(
                json.dumps(
                    {
                        "type": "artifact-chunk",
                        "request_id": request_id,
                        "artifact_id": "artifact-1",
                        "artifact_kind": "screenshot",
                        "mime_type": "image/png",
                        "encoding": "base64",
                        "index": 0,
                        "chunk": encoded[:4],
                        "final": False,
                    }
                )
            )
            await websocket.send(
                json.dumps(
                    {
                        "type": "artifact-chunk",
                        "request_id": request_id,
                        "artifact_id": "artifact-1",
                        "artifact_kind": "screenshot",
                        "mime_type": "image/png",
                        "encoding": "base64",
                        "index": 1,
                        "chunk": encoded[4:],
                        "final": True,
                    }
                )
            )
            await websocket.send(
                json.dumps(
                    {
                        "type": "artifact-end",
                        "request_id": request_id,
                        "artifact_id": "artifact-1",
                        "size_bytes": len(content),
                    }
                )
            )
            response = await request_task
            assert response["ack"] is True
            assert response["_artifacts"][0]["artifact_kind"] == "screenshot"
            assert response["_artifacts"][0]["content"] == content

        await hub.stop()

    asyncio.run(_scenario())


def test_extension_session_disconnect_fails_pending_artifacts(monkeypatch, tmp_path: Path) -> None:
    async def _scenario() -> None:
        monkeypatch.setenv(APP_HOME_ENV, str(tmp_path / ".browser-cli-runtime"))
        monkeypatch.setenv(EXTENSION_PORT_ENV, str(_unused_port()))

        hub = ExtensionHub()
        await hub.ensure_started()
        app_paths = get_app_paths()

        async with websockets.connect(app_paths.extension_ws_url) as websocket:
            await websocket.send(
                json.dumps(
                    {
                        "type": "hello",
                        "protocol_version": PROTOCOL_VERSION,
                        "extension_version": "0.1.0-test",
                        "browser_name": "Chrome",
                        "browser_version": "146",
                        "capabilities": sorted(REQUIRED_EXTENSION_CAPABILITIES),
                        "workspace_window_state": {"connected": True},
                        "extension_instance_id": "ext-test",
                    }
                )
            )
            session = await hub.wait_for_session(timeout_seconds=1.0)
            assert session is not None

            request_task = asyncio.create_task(session.send_request("trace-stop", {}))
            raw_request = json.loads(await websocket.recv())
            request_id = raw_request["id"]
            await websocket.send(
                json.dumps(
                    {
                        "type": "artifact-begin",
                        "request_id": request_id,
                        "artifact_id": "artifact-2",
                        "artifact_kind": "trace",
                        "mime_type": "application/zip",
                        "encoding": "base64",
                        "filename": "trace.zip",
                    }
                )
            )
            await websocket.close()
            with pytest.raises(OperationFailedError):
                await request_task

        await hub.stop()

    asyncio.run(_scenario())
