"""Automation manifest and service dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True, frozen=True)
class AutomationIdentity:
    id: str
    name: str
    description: str = ""
    version: str = "0.1.0"


@dataclass(slots=True, frozen=True)
class AutomationTaskConfig:
    path: Path
    meta_path: Path
    entrypoint: str = "run"


@dataclass(slots=True, frozen=True)
class AutomationOutputs:
    artifact_dir: Path
    result_json_path: Path | None = None
    stdout: str = "json"


@dataclass(slots=True, frozen=True)
class AutomationHooks:
    before_run: tuple[str, ...] = ()
    after_success: tuple[str, ...] = ()
    after_failure: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class AutomationRuntime:
    timeout_seconds: float | None = None
    retry_attempts: int = 0
    log_level: str = "info"


@dataclass(slots=True, frozen=True)
class AutomationManifest:
    manifest_path: Path
    automation: AutomationIdentity
    task: AutomationTaskConfig
    inputs: dict[str, Any] = field(default_factory=dict)
    schedule: dict[str, Any] = field(default_factory=dict)
    outputs: AutomationOutputs = field(
        default_factory=lambda: AutomationOutputs(artifact_dir=Path("artifacts"))
    )
    hooks: AutomationHooks = field(default_factory=AutomationHooks)
    runtime: AutomationRuntime = field(default_factory=AutomationRuntime)


@dataclass(slots=True, frozen=True)
class PersistedAutomationDefinition:
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
class AutomationRunRecord:
    run_id: str
    automation_id: str
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
class AutomationRunEvent:
    run_id: str
    event_type: str
    message: str = ""
    created_at: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


def manifest_to_persisted_definition(
    manifest: AutomationManifest,
    *,
    enabled: bool = False,
) -> PersistedAutomationDefinition:
    return PersistedAutomationDefinition(
        id=manifest.automation.id,
        name=manifest.automation.name,
        description=manifest.automation.description,
        version=manifest.automation.version,
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
