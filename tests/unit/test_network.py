from __future__ import annotations

import asyncio

from browser_cli.network import NetworkRecordFilter, NetworkRecordStore


def _record(
    url: str,
    *,
    resource_type: str = "fetch",
    status: int = 200,
    mime_type: str = "application/json",
) -> dict[str, object]:
    return {
        "request_id": url,
        "url": url,
        "method": "GET",
        "resource_type": resource_type,
        "status": status,
        "ok": True,
        "request_headers": {},
        "request_post_data": None,
        "response_headers": {"content-type": mime_type},
        "mime_type": mime_type,
        "started_at": 1.0,
        "ended_at": 1.1,
        "duration_ms": 100.0,
        "failed": False,
        "failure_reason": None,
        "body": {"kind": "text", "text": "{}", "bytes": 2, "truncated": False},
    }


def test_network_record_store_wait_reads_recent_buffer() -> None:
    store = NetworkRecordStore()
    store.add_record(_record("https://example.com/api/older"))
    store.add_record(_record("https://example.com/api/latest"))

    async def _scenario() -> None:
        record = await store.wait_for_record(
            record_filter=NetworkRecordFilter(url_contains="/api/"),
            timeout_seconds=0.1,
        )
        assert record["url"] == "https://example.com/api/latest"

    asyncio.run(_scenario())


def test_network_record_store_clear_only_removes_matched_records() -> None:
    store = NetworkRecordStore()
    store.start_capture()
    store.add_record(_record("https://example.com/api/ping"))
    store.add_record(
        _record("https://example.com/styles.css", resource_type="stylesheet", mime_type="text/css")
    )

    matched = store.get_captured_records(
        record_filter=NetworkRecordFilter(url_contains="/api/"),
        clear=True,
    )
    assert [item["url"] for item in matched] == ["https://example.com/api/ping"]

    remaining = store.get_captured_records(
        record_filter=NetworkRecordFilter(include_static=True),
        clear=False,
    )
    assert [item["url"] for item in remaining] == ["https://example.com/styles.css"]
