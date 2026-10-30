"""JSON rendering helpers for daemon-backed commands."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from browser_cli.errors import BrowserCliError


@dataclass(frozen=True, slots=True)
class CommandResult:
    stdout: str
    exit_code: int = 0


def render_json_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def render_json_error(
    exc: BrowserCliError,
    *,
    action: str | None = None,
    agent_id: str | None = None,
    next_action: str | None = None,
) -> str:
    """Render a typed error with provenance and only an available recovery hint."""
    payload: dict[str, Any] = {
        **exc.payload,
        "ok": False,
        "data": exc.payload.get("data", {}),
        "error_code": exc.error_code,
        "error_message": exc.message,
        "execution_state": exc.payload.get("execution_state", "unknown"),
    }
    meta = dict(payload.get("meta") or {})
    if action:
        meta.setdefault("action", action)
    if agent_id:
        meta.setdefault("agent_id", agent_id)
    payload["meta"] = meta
    if next_action:
        payload["next_action"] = next_action
    return render_json_payload(payload)
