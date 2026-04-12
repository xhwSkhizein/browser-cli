"""Workflow manifest and service dataclasses."""

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
    outputs: WorkflowOutputs = field(
        default_factory=lambda: WorkflowOutputs(artifact_dir=Path("artifacts"))
    )
    hooks: WorkflowHooks = field(default_factory=WorkflowHooks)
    runtime: WorkflowRuntime = field(default_factory=WorkflowRuntime)


@dataclass(slots=True, frozen=True)
class PersistedWorkflowDefinition:
    id: str
    name: str
    description: str = ""
    version: str = "0.1.0"
    task_path: Path = Path()
    task_meta_path: Path = Path()
    entrypoint: str = "run"
    enabled: bool = False
    definition_status: str = "valid"
    definition_error: str | None = None
    schedule_kind: str = "manual"
    schedule_payload: dict[str, Any] = field(default_factory=dict)
    timezone: str = "UTC"
    output_dir: Path = Path()
    result_json_path: Path | None = None
    stdout_mode: str = "json"
    input_overrides: dict[str, Any] = field(default_factory=dict)
    before_run_hooks: tuple[str, ...] = ()
    after_success_hooks: tuple[str, ...] = ()
    after_failure_hooks: tuple[str, ...] = ()
    retry_attempts: int = 0
    retry_backoff_seconds: int = 0
    timeout_seconds: float | None = None
    created_at: str | None = None
    updated_at: str | None = None
    last_run_at: str | None = None
    next_run_at: str | None = None


@dataclass(slots=True, frozen=True)
class WorkflowRunRecord:
    run_id: str
    workflow_id: str
    trigger_type: str
    status: str
    effective_inputs: dict[str, Any] = field(default_factory=dict)
    attempt_number: int = 0
    queued_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    result_json_path: Path | None = None
    artifacts_dir: Path | None = None
    log_path: Path | None = None


@dataclass(slots=True, frozen=True)
class WorkflowRunEvent:
    run_id: str
    event_type: str
    message: str = ""
    created_at: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


def manifest_to_persisted_definition(
    manifest: WorkflowManifest,
    *,
    enabled: bool = False,
) -> PersistedWorkflowDefinition:
    return PersistedWorkflowDefinition(
        id=manifest.workflow.id,
        name=manifest.workflow.name,
        description=manifest.workflow.description,
        version=manifest.workflow.version,
        task_path=manifest.task.path,
        task_meta_path=manifest.task.meta_path,
        entrypoint=manifest.task.entrypoint,
        enabled=enabled,
        schedule_kind=str(manifest.schedule.get("mode") or "manual"),
        schedule_payload=dict(manifest.schedule),
        timezone=str(manifest.schedule.get("timezone") or "UTC"),
        output_dir=manifest.outputs.artifact_dir,
        result_json_path=manifest.outputs.result_json_path,
        stdout_mode=manifest.outputs.stdout,
        input_overrides=dict(manifest.inputs),
        before_run_hooks=manifest.hooks.before_run,
        after_success_hooks=manifest.hooks.after_success,
        after_failure_hooks=manifest.hooks.after_failure,
        retry_attempts=manifest.runtime.retry_attempts,
        timeout_seconds=manifest.runtime.timeout_seconds,
    )
