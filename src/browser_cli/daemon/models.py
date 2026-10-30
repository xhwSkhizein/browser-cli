"""Daemon request and response models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DaemonRequest:
    action: str
    args: dict[str, Any]
    agent_id: str
    request_id: str
    runtime_version: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DaemonRequest:
        return cls(
            action=str(payload.get("action") or "").strip(),
            args=dict(payload.get("args") or {}),
            agent_id=str(payload.get("agent_id") or "").strip(),
            request_id=str(payload.get("request_id") or "").strip(),
            runtime_version=payload.get("runtime_version"),
        )


@dataclass(slots=True)
class DaemonResponse:
    ok: bool
    data: dict[str, Any] | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    execution_state: str | None = None
    blocked_by: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "data": self.data or {},
            "meta": self.meta,
        }
        if not self.ok:
            payload["error_code"] = self.error_code
            payload["error_message"] = self.error_message
            if self.execution_state is not None:
                payload["execution_state"] = self.execution_state
            if self.blocked_by is not None:
                payload["blocked_by"] = self.blocked_by
        return payload

    @classmethod
    def success(cls, data: dict[str, Any], *, meta: dict[str, Any] | None = None) -> DaemonResponse:
        return cls(ok=True, data=data, meta=meta or {})

    @classmethod
    def failure(
        cls,
        *,
        error_code: str,
        error_message: str,
        meta: dict[str, Any] | None = None,
        execution_state: str | None = None,
        blocked_by: dict[str, Any] | None = None,
    ) -> DaemonResponse:
        return cls(
            ok=False,
            data={},
            meta=meta or {},
            error_code=error_code,
            error_message=error_message,
            execution_state=execution_state,
            blocked_by=blocked_by,
        )
