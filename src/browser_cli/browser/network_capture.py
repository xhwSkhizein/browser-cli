"""Playwright-backed network record assembly."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import mimetypes
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from browser_cli.constants import get_app_paths
from browser_cli.network import NetworkRecordFilter, NetworkRecordStore

logger = logging.getLogger(__name__)


INLINE_TEXT_MAX_BYTES = 128 * 1024
INLINE_BINARY_MAX_BYTES = 64 * 1024
MAX_CAPTURE_BODY_BYTES = 8 * 1024 * 1024


@dataclass(slots=True)
class _PendingRequest:
    request: Any
    request_id: str
    url: str
    method: str
    resource_type: str
    started_at: float
    request_headers: dict[str, str] = field(default_factory=dict)
    request_post_data: str | None = None
    response: Any | None = None
    status: int | None = None
    ok: bool | None = None
    response_headers: dict[str, str] = field(default_factory=dict)
    mime_type: str = ""
    completed: bool = False


class PlaywrightNetworkObserver:
    def __init__(self, *, page_id: str, page: Any) -> None:
        self._page_id = page_id
        self._page = page
        self._store = NetworkRecordStore()
        self._pending_by_request_key: dict[int, _PendingRequest] = {}
        self._pending_tasks: set[asyncio.Task[None]] = set()
        self._sequence = 0
        self._closed = False
        self._handlers = {
            "request": self._on_request,
            "response": self._on_response,
            "requestfinished": self._on_request_finished,
            "requestfailed": self._on_request_failed,
        }
        for event_name, handler in self._handlers.items():
            self._page.on(event_name, handler)

    def start_capture(self) -> None:
        self._store.start_capture()

    def stop_capture(self) -> None:
        self._store.stop_capture()

    def get_records(
        self,
        *,
        record_filter: NetworkRecordFilter,
        clear: bool = True,
    ) -> list[dict[str, Any]]:
        return self._store.get_captured_records(record_filter=record_filter, clear=clear)

    async def wait_for_record(
        self,
        *,
        record_filter: NetworkRecordFilter,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        return await self._store.wait_for_record(
            record_filter=record_filter, timeout_seconds=timeout_seconds
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for event_name, handler in self._handlers.items():
            with contextlib.suppress(Exception):
                self._page.remove_listener(event_name, handler)
        for task in list(self._pending_tasks):
            task.cancel()
        if self._pending_tasks:
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)
        self._pending_tasks.clear()
        self._pending_by_request_key.clear()
        self._store.clear()

    def _on_request(self, request: Any) -> None:
        self._ensure_pending_request(request)

    def _on_response(self, response: Any) -> None:
        request = response.request
        pending = self._ensure_pending_request(request)
        pending.response = response
        pending.status = int(response.status or 0)
        pending.ok = bool(response.ok)
        response_headers = dict(response.headers) if response.headers else {}
        pending.response_headers = response_headers
        pending.mime_type = _extract_mime_type(response_headers)

    def _on_request_finished(self, request: Any) -> None:
        self._spawn(self._finalize_request(request))

    def _on_request_failed(self, request: Any) -> None:
        self._spawn(self._finalize_failed_request(request))

    def _spawn(self, coroutine: Any) -> None:
        if self._closed:
            return
        task = asyncio.create_task(coroutine)
        self._pending_tasks.add(task)
        task.add_done_callback(self._on_task_done)

    def _on_task_done(self, task: asyncio.Task[None]) -> None:
        self._pending_tasks.discard(task)
        if task.cancelled():
            return
        try:
            task.result()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Playwright network observer task failed for %s: %s", self._page_id, exc)

    def _ensure_pending_request(self, request: Any) -> _PendingRequest:
        request_key = id(request)
        pending = self._pending_by_request_key.get(request_key)
        if pending is not None:
            return pending
        self._sequence += 1
        pending = _PendingRequest(
            request=request,
            request_id=f"{self._page_id}-req-{self._sequence:04d}",
            url=str(request.url or ""),
            method=str(request.method or ""),
            resource_type=str(request.resource_type or ""),
            started_at=time.time(),
            request_headers=dict(request.headers) if request.headers else {},
            request_post_data=request.post_data,
        )
        self._pending_by_request_key[request_key] = pending
        return pending

    async def _finalize_request(self, request: Any) -> None:
        request_key = id(request)
        pending = self._ensure_pending_request(request)
        if pending.completed:
            return
        pending.completed = True
        pending.request_headers = await _read_request_headers(request, pending.request_headers)
        response = pending.response or await request.response()
        body = {
            "kind": "unavailable",
            "bytes": 0,
            "truncated": False,
            "error": "Response body was not available.",
        }
        if response is not None:
            pending.response_headers = await _read_response_headers(
                response, pending.response_headers
            )
            pending.status = int(response.status or pending.status or 0)
            pending.ok = bool(response.ok)
            pending.mime_type = _extract_mime_type(pending.response_headers) or pending.mime_type
            body = await _build_body_payload(
                page_id=self._page_id,
                request_id=pending.request_id,
                url=pending.url,
                mime_type=pending.mime_type,
                response_headers=pending.response_headers,
                response=response,
            )
        ended_at = time.time()
        record = _build_record(
            pending=pending,
            ended_at=ended_at,
            failed=False,
            failure_reason=None,
            body=body,
        )
        self._pending_by_request_key.pop(request_key, None)
        self._store.add_record(record)

    async def _finalize_failed_request(self, request: Any) -> None:
        request_key = id(request)
        pending = self._ensure_pending_request(request)
        if pending.completed:
            return
        pending.completed = True
        pending.request_headers = await _read_request_headers(request, pending.request_headers)
        failure_reason = str(request.failure or "Request failed.")
        ended_at = time.time()
        record = _build_record(
            pending=pending,
            ended_at=ended_at,
            failed=True,
            failure_reason=failure_reason,
            body={
                "kind": "unavailable",
                "bytes": 0,
                "truncated": False,
                "error": failure_reason,
            },
        )
        self._pending_by_request_key.pop(request_key, None)
        self._store.add_record(record)


async def _read_request_headers(request: Any, fallback: dict[str, str]) -> dict[str, str]:
    try:
        headers = await request.all_headers()
    except Exception:
        return fallback
    return dict(headers or fallback)


async def _read_response_headers(response: Any, fallback: dict[str, str]) -> dict[str, str]:
    try:
        headers = await response.all_headers()
    except Exception:
        return fallback
    return dict(headers or fallback)


async def _build_body_payload(
    *,
    page_id: str,
    request_id: str,
    url: str,
    mime_type: str,
    response_headers: dict[str, str],
    response: Any,
) -> dict[str, Any]:
    content_length = _parse_content_length(response_headers)
    if content_length is not None and content_length > MAX_CAPTURE_BODY_BYTES:
        return {
            "kind": "omitted",
            "bytes": content_length,
            "truncated": False,
            "error": "Response body exceeded the capture limit.",
        }
    try:
        body_bytes = await response.body()
    except Exception as exc:
        return {
            "kind": "unavailable",
            "bytes": content_length or 0,
            "truncated": False,
            "error": str(exc),
        }
    byte_length = len(body_bytes)
    if byte_length > MAX_CAPTURE_BODY_BYTES:
        return {
            "kind": "omitted",
            "bytes": byte_length,
            "truncated": False,
            "error": "Response body exceeded the capture limit.",
        }
    if _is_textual_mime(mime_type):
        if byte_length <= INLINE_TEXT_MAX_BYTES:
            return {
                "kind": "text",
                "text": body_bytes.decode("utf-8", errors="replace"),
                "bytes": byte_length,
                "truncated": False,
            }
        output_path = _write_body_artifact(
            page_id=page_id, request_id=request_id, url=url, mime_type=mime_type, content=body_bytes
        )
        return {
            "kind": "path",
            "path": str(output_path),
            "bytes": byte_length,
            "truncated": False,
        }
    if byte_length <= INLINE_BINARY_MAX_BYTES:
        return {
            "kind": "base64",
            "base64": base64.b64encode(body_bytes).decode("ascii"),
            "bytes": byte_length,
            "truncated": False,
        }
    output_path = _write_body_artifact(
        page_id=page_id, request_id=request_id, url=url, mime_type=mime_type, content=body_bytes
    )
    return {
        "kind": "path",
        "path": str(output_path),
        "bytes": byte_length,
        "truncated": False,
    }


def _build_record(
    *,
    pending: _PendingRequest,
    ended_at: float,
    failed: bool,
    failure_reason: str | None,
    body: dict[str, Any],
) -> dict[str, Any]:
    status = int(pending.status or 0)
    ok = bool(pending.ok) if pending.ok is not None else (200 <= status < 400)
    return {
        "request_id": pending.request_id,
        "url": pending.url,
        "method": pending.method,
        "resource_type": pending.resource_type,
        "status": status,
        "ok": ok and not failed,
        "request_headers": dict(pending.request_headers),
        "request_post_data": pending.request_post_data,
        "response_headers": dict(pending.response_headers),
        "mime_type": pending.mime_type,
        "started_at": pending.started_at,
        "ended_at": ended_at,
        "duration_ms": max((ended_at - pending.started_at) * 1000.0, 0.0),
        "failed": failed,
        "failure_reason": failure_reason,
        "body": body,
    }


def _extract_mime_type(headers: dict[str, str]) -> str:
    content_type = ""
    for key, value in headers.items():
        if key.lower() == "content-type":
            content_type = str(value or "")
            break
    return content_type.split(";", 1)[0].strip().lower()


def _parse_content_length(headers: dict[str, str]) -> int | None:
    for key, value in headers.items():
        if key.lower() != "content-length":
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def _is_textual_mime(mime_type: str) -> bool:
    normalized = str(mime_type or "").lower()
    if not normalized:
        return False
    if normalized.startswith("text/"):
        return True
    return any(
        token in normalized
        for token in ("json", "xml", "javascript", "ecmascript", "svg", "x-www-form-urlencoded")
    )


def _write_body_artifact(
    *,
    page_id: str,
    request_id: str,
    url: str,
    mime_type: str,
    content: bytes,
) -> Path:
    artifacts_dir = get_app_paths().artifacts_dir / "network-bodies" / page_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    suffix = _choose_body_suffix(url=url, mime_type=mime_type)
    output_path = artifacts_dir / f"{request_id}{suffix}"
    output_path.write_bytes(content)
    return output_path


def _choose_body_suffix(*, url: str, mime_type: str) -> str:
    parsed = urllib.parse.urlparse(url)
    suffix = Path(parsed.path).suffix
    if suffix:
        return suffix
    guessed = mimetypes.guess_extension(mime_type or "")
    if guessed:
        return guessed
    return ".bin"
