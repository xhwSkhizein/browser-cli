"""Extension WebSocket session and hub."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any

import websockets
from websockets.datastructures import Headers
from websockets.http11 import Request, Response
from websockets.protocol import State
from websockets.server import ServerConnection

from browser_cli.constants import get_app_paths
from browser_cli.errors import OperationFailedError

from .protocol import (
    ExtensionArtifactBegin,
    ExtensionArtifactChunk,
    ExtensionArtifactEnd,
    ExtensionHello,
    ExtensionRequest,
    ExtensionResponse,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _ArtifactBuffer:
    descriptor: ExtensionArtifactBegin
    chunks: list[str] = field(default_factory=list)

    def append(self, chunk: str) -> None:
        self.chunks.append(chunk)

    def to_payload(self) -> dict[str, Any]:
        content = base64.b64decode("".join(self.chunks).encode("ascii"))
        return {
            "artifact_id": self.descriptor.artifact_id,
            "artifact_kind": self.descriptor.artifact_kind,
            "mime_type": self.descriptor.mime_type,
            "encoding": self.descriptor.encoding,
            "filename": self.descriptor.filename,
            "page_id": self.descriptor.page_id,
            "metadata": dict(self.descriptor.metadata),
            "content": content,
        }


@dataclass(slots=True)
class ExtensionSession:
    websocket: ServerConnection
    hello: ExtensionHello
    _pending: dict[str, asyncio.Future[ExtensionResponse]] = field(init=False, repr=False)
    _artifact_events: dict[str, asyncio.Event] = field(init=False, repr=False)
    _artifact_buffers: dict[tuple[str, str], _ArtifactBuffer] = field(init=False, repr=False)
    _completed_artifacts: dict[str, list[dict[str, Any]]] = field(init=False, repr=False)
    _lock: asyncio.Lock = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._pending = {}
        self._artifact_events = {}
        self._artifact_buffers = {}
        self._completed_artifacts = {}
        self._lock = asyncio.Lock()

    @property
    def available(self) -> bool:
        closed = getattr(self.websocket, "closed", None)
        if isinstance(closed, bool):
            return not closed
        state = getattr(self.websocket, "state", None)
        return state not in {State.CLOSING, State.CLOSED}

    async def send_request(
        self, action: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not self.available:
            raise OperationFailedError("Browser CLI extension session is not connected.")
        request = ExtensionRequest(
            id=uuid.uuid4().hex,
            action=action,
            payload=payload or {},
        )
        future: asyncio.Future[ExtensionResponse] = asyncio.get_running_loop().create_future()
        event = asyncio.Event()
        event.set()
        async with self._lock:
            self._pending[request.id] = future
            self._artifact_events[request.id] = event
            await self.websocket.send(json.dumps(request.to_message()))
        try:
            response = await asyncio.wait_for(future, timeout=30.0)
            await asyncio.wait_for(event.wait(), timeout=30.0)
        finally:
            self._pending.pop(request.id, None)
            self._artifact_events.pop(request.id, None)
        if not response.ok:
            raise OperationFailedError(
                response.error_message or f"Extension request failed: {action}",
                error_code=response.error_code or "EXTENSION_REQUEST_FAILED",
            )
        data = dict(response.data)
        artifacts = self._completed_artifacts.pop(request.id, [])
        if artifacts:
            data["_artifacts"] = artifacts
        return data

    def resolve_response(self, response: ExtensionResponse) -> None:
        future = self._pending.get(response.id)
        if future is None or future.done():
            return
        future.set_result(response)

    def fail_all(self, message: str) -> None:
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(
                    OperationFailedError(message, error_code="EXTENSION_DISCONNECTED")
                )
        self._pending.clear()
        self._artifact_buffers.clear()
        self._completed_artifacts.clear()
        for event in list(self._artifact_events.values()):
            event.set()
        self._artifact_events.clear()

    def begin_artifact(self, descriptor: ExtensionArtifactBegin) -> None:
        key = (descriptor.request_id, descriptor.artifact_id)
        self._artifact_buffers[key] = _ArtifactBuffer(descriptor=descriptor)
        event = self._artifact_events.get(descriptor.request_id)
        if event is not None:
            event.clear()

    def append_artifact_chunk(self, chunk: ExtensionArtifactChunk) -> None:
        key = (chunk.request_id, chunk.artifact_id)
        buffer = self._artifact_buffers.get(key)
        if buffer is None:
            return
        buffer.append(chunk.chunk)

    def complete_artifact(self, artifact_end: ExtensionArtifactEnd) -> None:
        key = (artifact_end.request_id, artifact_end.artifact_id)
        buffer = self._artifact_buffers.pop(key, None)
        if buffer is None:
            return
        self._completed_artifacts.setdefault(artifact_end.request_id, []).append(
            buffer.to_payload()
        )
        if not any(
            request_id == artifact_end.request_id
            for request_id, _artifact_id in self._artifact_buffers
        ):
            event = self._artifact_events.get(artifact_end.request_id)
            if event is not None:
                event.set()


class ExtensionHub:
    PROBE_PATH = "/ext"

    def __init__(self) -> None:
        self._server: websockets.server.Serve | None = None
        self._session: ExtensionSession | None = None
        self._session_ready = asyncio.Event()
        self._started = False
        self._lock = asyncio.Lock()
        self._session_changed = asyncio.Event()

    @property
    def session(self) -> ExtensionSession | None:
        session = self._session
        if session is None or not session.available:
            return None
        return session

    async def ensure_started(self) -> None:
        async with self._lock:
            if self._started:
                return
            app_paths = get_app_paths()
            self._server = await websockets.serve(
                self._handle_websocket,
                host=app_paths.extension_host,
                port=app_paths.extension_port,
                ping_interval=None,
                ping_timeout=None,
                process_request=self._process_request,
            )
            self._started = True
            logger.info(
                "Extension WebSocket listener started on ws://%s:%s%s",
                app_paths.extension_host,
                app_paths.extension_port,
                app_paths.extension_ws_path,
            )

    async def stop(self) -> None:
        async with self._lock:
            session = self._session
            self._session = None
            self._session_ready.clear()
            if session is not None:
                session.fail_all("Extension session closed.")
                with contextlib.suppress(Exception):
                    await session.websocket.close()
            if self._server is not None:
                self._server.close()
                await self._server.wait_closed()
                self._server = None
            self._started = False
            self._session_changed.set()
            logger.info("Extension WebSocket listener stopped")

    async def wait_for_session(self, timeout_seconds: float) -> ExtensionSession | None:
        try:
            await asyncio.wait_for(self._session_ready.wait(), timeout=timeout_seconds)
        except TimeoutError:
            return None
        return self.session

    async def wait_for_change(self) -> None:
        await self._session_changed.wait()
        self._session_changed.clear()

    async def _handle_websocket(self, websocket: ServerConnection) -> None:
        hello_payload = json.loads(await websocket.recv())
        if hello_payload.get("type") != "hello":
            await websocket.close(code=4400, reason="Expected hello")
            return
        hello = ExtensionHello.from_message(dict(hello_payload))
        session = ExtensionSession(websocket=websocket, hello=hello)
        self._session = session
        self._session_ready.set()
        self._session_changed.set()
        logger.info(
            "Extension connected: version=%s browser=%s capabilities=%d workspace=%s",
            hello.extension_version,
            hello.browser_version,
            len(hello.capabilities),
            hello.workspace_window_state,
        )
        try:
            async for raw_message in websocket:
                payload = json.loads(raw_message)
                message_type = str(payload.get("type") or "")
                if message_type == "response":
                    session.resolve_response(ExtensionResponse.from_message(dict(payload)))
                elif message_type == "artifact-begin":
                    session.begin_artifact(ExtensionArtifactBegin.from_message(dict(payload)))
                elif message_type == "artifact-chunk":
                    session.append_artifact_chunk(
                        ExtensionArtifactChunk.from_message(dict(payload))
                    )
                elif message_type == "artifact-end":
                    session.complete_artifact(ExtensionArtifactEnd.from_message(dict(payload)))
                elif message_type == "heartbeat":
                    await websocket.send(json.dumps({"type": "heartbeat-ack"}))
        finally:
            if self._session is session:
                self._session = None
                self._session_ready.clear()
                session.fail_all("Extension disconnected.")
                self._session_changed.set()
                logger.warning(
                    "Extension disconnected: code=%s reason=%s",
                    getattr(websocket, "close_code", None),
                    getattr(websocket, "close_reason", None),
                )

    @classmethod
    def _process_request(
        cls, connection_or_path: ServerConnection | str, request_or_headers: Request | Headers
    ) -> Response | None:
        # Support both websockets 12/13 (old API: process_request(path, headers))
        # and websockets 14+ (new API: process_request(connection, request))
        if hasattr(request_or_headers, "headers"):
            # websockets 14+ API: request_or_headers is a Request object
            request = request_or_headers
            path = request.path
            headers = request.headers
        else:
            # websockets 12/13 API: request_or_headers is a Headers object
            path = str(connection_or_path)
            headers = request_or_headers

        if cls._is_websocket_upgrade(headers):
            return None
        if path == cls.PROBE_PATH:
            return cls._build_response(
                HTTPStatus.UPGRADE_REQUIRED,
                b"Browser CLI extension endpoint expects a WebSocket upgrade.\n",
                upgrade="websocket",
            )
        return cls._build_response(HTTPStatus.NOT_FOUND, b"Not Found\n")

    @staticmethod
    def _is_websocket_upgrade(headers: Headers) -> bool:
        upgrade = headers.get("Upgrade", "")
        connection = headers.get("Connection", "")
        return upgrade.lower() == "websocket" and "upgrade" in connection.lower()

    @staticmethod
    def _build_response(
        status: HTTPStatus,
        body: bytes,
        *,
        upgrade: str | None = None,
    ) -> Response | tuple[int, Headers, bytes]:
        headers = Headers()
        headers["Content-Type"] = "text/plain; charset=utf-8"
        headers["Content-Length"] = str(len(body))
        if upgrade:
            headers["Upgrade"] = upgrade
        # websockets 12/13 expect tuple (status, headers, body)
        # websockets 14+ accepts Response object
        import websockets

        version_tuple = tuple(map(int, websockets.__version__.split(".")[:2]))
        if version_tuple >= (14, 0):
            return Response(int(status), status.phrase, headers, body)
        else:
            return (int(status), headers, body)
