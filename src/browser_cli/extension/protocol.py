"""JSON protocol between daemon and Browser CLI extension."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

REQUIRED_EXTENSION_CAPABILITIES = frozenset(
    {
        "open",
        "tabs",
        "info",
        "html",
        "snapshot",
        "reload",
        "back",
        "forward",
        "resize",
        "click",
        "double-click",
        "hover",
        "focus",
        "fill",
        "fill-form",
        "select",
        "options",
        "check",
        "uncheck",
        "scroll-to",
        "drag",
        "upload",
        "type",
        "press",
        "key-down",
        "key-up",
        "scroll",
        "mouse-click",
        "mouse-move",
        "mouse-drag",
        "mouse-down",
        "mouse-up",
        "eval",
        "eval-on",
        "wait",
        "wait-network",
        "screenshot",
        "pdf",
        "trace-start",
        "trace-chunk",
        "trace-stop",
        "video-start",
        "video-stop",
        "console-start",
        "console",
        "console-stop",
        "network-wait",
        "network-start",
        "network",
        "network-stop",
        "dialog-setup",
        "dialog",
        "dialog-remove",
        "cookies",
        "cookie-set",
        "cookies-clear",
        "storage-save",
        "storage-load",
        "verify-text",
        "verify-visible",
        "verify-url",
        "verify-title",
        "verify-state",
        "verify-value",
    }
)
OPTIONAL_EXTENSION_CAPABILITIES = frozenset()
ALL_EXTENSION_CAPABILITIES = REQUIRED_EXTENSION_CAPABILITIES
CORE_EXTENSION_CAPABILITIES = REQUIRED_EXTENSION_CAPABILITIES
PROTOCOL_VERSION = "1"
ARTIFACT_CHUNK_SIZE = 256 * 1024


@dataclass(slots=True, frozen=True)
class ExtensionHello:
    protocol_version: str
    extension_version: str
    browser_name: str
    browser_version: str
    capabilities: frozenset[str]
    workspace_window_state: dict[str, Any] = field(default_factory=dict)
    extension_instance_id: str = ""

    @classmethod
    def from_message(cls, payload: dict[str, Any]) -> "ExtensionHello":
        return cls(
            protocol_version=str(payload.get("protocol_version") or ""),
            extension_version=str(payload.get("extension_version") or ""),
            browser_name=str(payload.get("browser_name") or ""),
            browser_version=str(payload.get("browser_version") or ""),
            capabilities=frozenset(str(item) for item in (payload.get("capabilities") or [])),
            workspace_window_state=dict(payload.get("workspace_window_state") or {}),
            extension_instance_id=str(payload.get("extension_instance_id") or ""),
        )

    def is_compatible(self) -> bool:
        return self.protocol_version == PROTOCOL_VERSION

    def has_required_capabilities(self) -> bool:
        return REQUIRED_EXTENSION_CAPABILITIES.issubset(self.capabilities)

    def missing_required_capabilities(self) -> list[str]:
        return sorted(REQUIRED_EXTENSION_CAPABILITIES - self.capabilities)

    def has_core_capabilities(self) -> bool:
        return self.has_required_capabilities()


@dataclass(slots=True, frozen=True)
class ExtensionRequest:
    id: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_message(self) -> dict[str, Any]:
        return {
            "type": "request",
            "id": self.id,
            "action": self.action,
            "payload": self.payload,
        }


@dataclass(slots=True, frozen=True)
class ExtensionResponse:
    id: str
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None

    @classmethod
    def from_message(cls, payload: dict[str, Any]) -> "ExtensionResponse":
        return cls(
            id=str(payload.get("id") or ""),
            ok=bool(payload.get("ok")),
            data=dict(payload.get("data") or {}),
            error_code=(str(payload["error_code"]) if payload.get("error_code") is not None else None),
            error_message=(
                str(payload["error_message"]) if payload.get("error_message") is not None else None
            ),
        )


@dataclass(slots=True, frozen=True)
class ExtensionArtifactBegin:
    request_id: str
    artifact_id: str
    artifact_kind: str
    mime_type: str
    encoding: str
    filename: str | None = None
    page_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_message(cls, payload: dict[str, Any]) -> "ExtensionArtifactBegin":
        return cls(
            request_id=str(payload.get("request_id") or ""),
            artifact_id=str(payload.get("artifact_id") or ""),
            artifact_kind=str(payload.get("artifact_kind") or ""),
            mime_type=str(payload.get("mime_type") or "application/octet-stream"),
            encoding=str(payload.get("encoding") or "base64"),
            filename=(str(payload["filename"]) if payload.get("filename") is not None else None),
            page_id=(str(payload["page_id"]) if payload.get("page_id") is not None else None),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(slots=True, frozen=True)
class ExtensionArtifactChunk:
    request_id: str
    artifact_id: str
    artifact_kind: str
    mime_type: str
    encoding: str
    index: int
    chunk: str
    final: bool = False

    @classmethod
    def from_message(cls, payload: dict[str, Any]) -> "ExtensionArtifactChunk":
        return cls(
            request_id=str(payload.get("request_id") or ""),
            artifact_id=str(payload.get("artifact_id") or ""),
            artifact_kind=str(payload.get("artifact_kind") or ""),
            mime_type=str(payload.get("mime_type") or "application/octet-stream"),
            encoding=str(payload.get("encoding") or "base64"),
            index=int(payload.get("index") or 0),
            chunk=str(payload.get("chunk") or ""),
            final=bool(payload.get("final")),
        )


@dataclass(slots=True, frozen=True)
class ExtensionArtifactEnd:
    request_id: str
    artifact_id: str
    size_bytes: int | None = None

    @classmethod
    def from_message(cls, payload: dict[str, Any]) -> "ExtensionArtifactEnd":
        return cls(
            request_id=str(payload.get("request_id") or ""),
            artifact_id=str(payload.get("artifact_id") or ""),
            size_bytes=(int(payload["size_bytes"]) if payload.get("size_bytes") is not None else None),
        )
