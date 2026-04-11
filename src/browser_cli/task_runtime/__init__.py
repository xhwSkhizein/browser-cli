"""Thin Python runtime for Browser CLI-backed tasks."""

from browser_cli.task_runtime.client import BrowserCliTaskClient
from browser_cli.task_runtime.flow import Flow
from browser_cli.task_runtime.models import (
    FlowContext,
    SnapshotRef,
    SnapshotResult,
    validate_task_metadata,
)

__all__ = [
    "BrowserCliTaskClient",
    "Flow",
    "FlowContext",
    "SnapshotRef",
    "SnapshotResult",
    "validate_task_metadata",
]
