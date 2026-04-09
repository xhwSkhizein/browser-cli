"""Workflow manifest dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True, frozen=True)
class WorkflowIdentity:
    id: str
    name: str
    description: str = ""
    version: str = "0.1.0"


@dataclass(slots=True, frozen=True)
class WorkflowTaskConfig:
    path: Path
    meta_path: Path
    entrypoint: str = "run"


@dataclass(slots=True, frozen=True)
class WorkflowOutputs:
    artifact_dir: Path
    result_json_path: Path | None = None
    stdout: str = "json"


@dataclass(slots=True, frozen=True)
class WorkflowHooks:
    before_run: tuple[str, ...] = ()
    after_success: tuple[str, ...] = ()
    after_failure: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class WorkflowRuntime:
    timeout_seconds: float | None = None
    retry_attempts: int = 0
    log_level: str = "info"


@dataclass(slots=True, frozen=True)
class WorkflowManifest:
    manifest_path: Path
    workflow: WorkflowIdentity
    task: WorkflowTaskConfig
    inputs: dict[str, Any] = field(default_factory=dict)
    schedule: dict[str, Any] = field(default_factory=dict)
    outputs: WorkflowOutputs = field(default_factory=lambda: WorkflowOutputs(artifact_dir=Path("artifacts")))
    hooks: WorkflowHooks = field(default_factory=WorkflowHooks)
    runtime: WorkflowRuntime = field(default_factory=WorkflowRuntime)
