"""Agent visibility-domain helpers."""

from __future__ import annotations

import os

from browser_cli.constants import DEFAULT_PUBLIC_AGENT_ID

AGENT_ID_ENV = "X_AGENT_ID"


def resolve_agent_id() -> str:
    raw_value = os.environ.get(AGENT_ID_ENV, "").strip()
    return raw_value or DEFAULT_PUBLIC_AGENT_ID
