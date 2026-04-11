"""Extension transport primitives."""

from .protocol import (
    ALL_EXTENSION_CAPABILITIES,
    ARTIFACT_CHUNK_SIZE,
    CORE_EXTENSION_CAPABILITIES,
    ExtensionArtifactBegin,
    ExtensionArtifactChunk,
    ExtensionArtifactEnd,
    ExtensionHello,
    ExtensionRequest,
    ExtensionResponse,
    OPTIONAL_EXTENSION_CAPABILITIES,
    REQUIRED_EXTENSION_CAPABILITIES,
)
from .session import ExtensionHub, ExtensionSession

__all__ = [
    "CORE_EXTENSION_CAPABILITIES",
    "REQUIRED_EXTENSION_CAPABILITIES",
    "OPTIONAL_EXTENSION_CAPABILITIES",
    "ALL_EXTENSION_CAPABILITIES",
    "ARTIFACT_CHUNK_SIZE",
    "ExtensionHello",
    "ExtensionRequest",
    "ExtensionResponse",
    "ExtensionArtifactBegin",
    "ExtensionArtifactChunk",
    "ExtensionArtifactEnd",
    "ExtensionHub",
    "ExtensionSession",
]
