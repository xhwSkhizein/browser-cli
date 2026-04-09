"""JSON rendering helpers for daemon-backed commands."""

from __future__ import annotations

import json
from typing import Any


def render_json_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
