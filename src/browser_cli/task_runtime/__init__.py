"""Thin Python runtime for Browser CLI-backed tasks."""

from browser_cli.task_runtime.client import BrowserCliTaskClient
from browser_cli.task_runtime.entrypoint import (
    load_task_entrypoint,
    parse_input_overrides,
    run_task_entrypoint,
    validate_task_dir,
)
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
    "load_task_entrypoint",
    "parse_input_overrides",
    "run_task_entrypoint",
    "validate_task_dir",
    "validate_task_metadata",
]
