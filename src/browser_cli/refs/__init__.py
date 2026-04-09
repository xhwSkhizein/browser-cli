"""Semantic ref models, snapshot generation, and locator resolution."""

from browser_cli.refs.generator import SemanticSnapshotGenerator, SnapshotOptions
from browser_cli.refs.models import RefData, SemanticSnapshot, SnapshotMetadata
from browser_cli.refs.registry import PageSnapshotState, SnapshotRegistry
from browser_cli.refs.resolver import SemanticRefResolver

__all__ = [
    "PageSnapshotState",
    "RefData",
    "SemanticRefResolver",
    "SemanticSnapshot",
    "SemanticSnapshotGenerator",
    "SnapshotMetadata",
    "SnapshotOptions",
    "SnapshotRegistry",
]
