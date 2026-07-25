from __future__ import annotations

from browser_cli.daemon.client import _error_from_payload
from browser_cli.errors import EmptyContentError


def test_empty_body_treats_whitespace_and_snapshot_sentinel_as_empty() -> None:
    assert EmptyContentError.is_empty_body("")
    assert EmptyContentError.is_empty_body("   \n")
    assert EmptyContentError.is_empty_body("(empty)")
    assert EmptyContentError.is_empty_body("  (empty)  ")
    assert not EmptyContentError.is_empty_body("<html></html>")
    assert not EmptyContentError.is_empty_body("RootWebArea")


def test_daemon_empty_content_error_preserves_details_and_driver() -> None:
    exc = _error_from_payload(
        {
            "ok": False,
            "error_code": "EMPTY_CONTENT",
            "error_message": "Read completed but produced no content.",
            "meta": {
                "action": "read-page",
                "driver": "extension",
                "details": {
                    "url": "https://example.com",
                    "final_url": "https://example.com/",
                    "title": "Example",
                    "body_len": 0,
                    "output_mode": "html",
                },
            },
        }
    )
    assert isinstance(exc, EmptyContentError)
    assert exc.details["driver"] == "extension"
    assert exc.details["final_url"] == "https://example.com/"
    assert exc.details["body_len"] == 0
