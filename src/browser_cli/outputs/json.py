"""JSON rendering helpers for daemon-backed commands."""

from __future__ import annotations

import json
from typing import Any

from browser_cli.errors import BrowserCliError


def render_json_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def render_json_error(
    exc: BrowserCliError,
    *,
    action: str | None = None,
    next_action: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "ok": False,
        "error_code": exc.error_code,
        "message": exc.message,
    }
    if action:
        payload["meta"] = {"action": action}
    if next_action:
        payload["next_action"] = next_action
    return render_json_payload(payload)
