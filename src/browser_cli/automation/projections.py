"""Shared semantic projections for automation manifests and live definitions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from browser_cli.automation.models import (
    AutomationManifest,
    PersistedAutomationDefinition,
)
from browser_cli.automation.toml import dumps_toml_sections


def manifest_to_persisted_definition(
    manifest: AutomationManifest,
    *,
    enabled: bool = False,
) -> PersistedAutomationDefinition:
    return PersistedAutomationDefinition(
        id=manifest.automation.id,
        name=manifest.automation.name,
        task_path=manifest.task.path,
        task_meta_path=manifest.task.meta_path,
        output_dir=manifest.outputs.artifact_dir,
        description=manifest.automation.description,
        version=str(manifest.automation.version),
        entrypoint=manifest.task.entrypoint,
        enabled=enabled,
        schedule_kind=str(manifest.schedule.get("mode") or "manual"),
        schedule_payload=dict(manifest.schedule),
        timezone=str(manifest.schedule.get("timezone") or "UTC"),
        result_json_path=manifest.outputs.result_json_path,
        stdout_mode=manifest.outputs.stdout,
        input_overrides=dict(manifest.inputs),
        before_run_hooks=manifest.hooks.before_run,
        after_success_hooks=manifest.hooks.after_success,
        after_failure_hooks=manifest.hooks.after_failure,
        retry_attempts=manifest.runtime.retry_attempts,
        retry_backoff_seconds=manifest.runtime.retry_backoff_seconds,
        timeout_seconds=manifest.runtime.timeout_seconds,
        log_level=manifest.runtime.log_level,
    )


def payload_to_persisted_definition(payload: dict[str, Any]) -> PersistedAutomationDefinition:
    automation_id = str(payload.get("id") or "").strip()
    if not automation_id:
        raise ValueError("Automation id is required.")
    output_dir_raw = str(payload.get("output_dir") or "").strip()
    result_json_raw = str(payload.get("result_json_path") or "").strip()
    return PersistedAutomationDefinition(
        id=automation_id,
        name=str(payload.get("name") or automation_id),
        description=str(payload.get("description") or ""),
        version=str(payload.get("version") or "0.1.0"),
        task_path=Path(str(payload.get("task_path") or "")),
        task_meta_path=Path(str(payload.get("task_meta_path") or "")),
        entrypoint=str(payload.get("entrypoint") or "run"),
        enabled=bool(payload.get("enabled")),
        definition_status=str(payload.get("definition_status") or "valid"),
        definition_error=str(payload.get("definition_error"))
        if payload.get("definition_error")
        else None,
        schedule_kind=str(payload.get("schedule_kind") or "manual"),
        schedule_payload=dict(payload.get("schedule_payload") or {}),
        timezone=str(payload.get("timezone") or "UTC"),
        output_dir=Path(output_dir_raw) if output_dir_raw else Path(),
        result_json_path=Path(result_json_raw) if result_json_raw else None,
        stdout_mode=str(payload.get("stdout_mode") or "json"),
        input_overrides=dict(payload.get("input_overrides") or {}),
        before_run_hooks=tuple(payload.get("before_run_hooks") or []),
        after_success_hooks=tuple(payload.get("after_success_hooks") or []),
        after_failure_hooks=tuple(payload.get("after_failure_hooks") or []),
        retry_attempts=int(payload.get("retry_attempts") or 0),
        retry_backoff_seconds=int(payload.get("retry_backoff_seconds") or 0),
        timeout_seconds=float(payload["timeout_seconds"])
        if payload.get("timeout_seconds") is not None
        else None,
        log_level=str(payload.get("log_level") or "info"),
    )


def persisted_definition_to_manifest_toml(
    automation: PersistedAutomationDefinition,
) -> str:
    return dumps_toml_sections(
        [
            (
                "automation",
                {
                    "id": automation.id,
                    "name": automation.name,
                    "description": automation.description,
                    "version": automation.version,
                },
            ),
            (
                "task",
                {
                    "path": str(automation.task_path),
                    "meta_path": str(automation.task_meta_path),
                    "entrypoint": automation.entrypoint,
                },
            ),
            ("inputs", dict(automation.input_overrides)),
            ("schedule", _schedule_values(automation)),
            (
                "outputs",
                {
                    "artifact_dir": str(automation.output_dir),
                    "result_json_path": str(automation.result_json_path)
                    if automation.result_json_path
                    else None,
                    "stdout": automation.stdout_mode,
                },
            ),
            (
                "hooks",
                {
                    "before_run": list(automation.before_run_hooks),
                    "after_success": list(automation.after_success_hooks),
                    "after_failure": list(automation.after_failure_hooks),
                },
            ),
            (
                "runtime",
                {
                    "retry_attempts": automation.retry_attempts,
                    "retry_backoff_seconds": automation.retry_backoff_seconds,
                    "timeout_seconds": automation.timeout_seconds,
                    "log_level": automation.log_level,
                },
            ),
        ]
    )


def manifest_to_snapshot_manifest_toml(
    manifest: AutomationManifest,
    *,
    version: int,
    task_path: Path,
    task_meta_path: Path,
    output_dir: Path,
) -> str:
    result_json_path = _remap_result_json_path(
        manifest.outputs.artifact_dir,
        manifest.outputs.result_json_path,
        output_dir,
    )
    return dumps_toml_sections(
        [
            (
                "automation",
                {
                    "id": manifest.automation.id,
                    "name": manifest.automation.name,
                    "description": manifest.automation.description,
                    "version": str(version),
                },
            ),
            (
                "task",
                {
                    "path": str(task_path),
                    "meta_path": str(task_meta_path),
                    "entrypoint": manifest.task.entrypoint,
                },
            ),
            ("inputs", dict(manifest.inputs)),
            ("schedule", dict(manifest.schedule)),
            (
                "outputs",
                {
                    "artifact_dir": str(output_dir),
                    "result_json_path": str(result_json_path) if result_json_path else None,
                    "stdout": manifest.outputs.stdout,
                },
            ),
            (
                "hooks",
                {
                    "before_run": list(manifest.hooks.before_run),
                    "after_success": list(manifest.hooks.after_success),
                    "after_failure": list(manifest.hooks.after_failure),
                },
            ),
            (
                "runtime",
                {
                    "retry_attempts": manifest.runtime.retry_attempts,
                    "retry_backoff_seconds": manifest.runtime.retry_backoff_seconds,
                    "timeout_seconds": manifest.runtime.timeout_seconds,
                    "log_level": manifest.runtime.log_level,
                },
            ),
        ]
    )


def manifest_to_config_payload(manifest: AutomationManifest) -> dict[str, object]:
    return {
        "id": manifest.automation.id,
        "name": manifest.automation.name,
        "description": manifest.automation.description,
        "version": str(manifest.automation.version),
        "task_path": str(manifest.task.path),
        "task_meta_path": str(manifest.task.meta_path),
        "entrypoint": manifest.task.entrypoint,
        "schedule_kind": str(manifest.schedule.get("mode") or "manual"),
        "schedule_payload": dict(manifest.schedule),
        "timezone": str(manifest.schedule.get("timezone") or "UTC"),
        "output_dir": str(manifest.outputs.artifact_dir),
        "result_json_path": str(manifest.outputs.result_json_path)
        if manifest.outputs.result_json_path
        else None,
        "stdout_mode": manifest.outputs.stdout,
        "input_overrides": dict(manifest.inputs),
        "before_run_hooks": list(manifest.hooks.before_run),
        "after_success_hooks": list(manifest.hooks.after_success),
        "after_failure_hooks": list(manifest.hooks.after_failure),
        "retry_attempts": manifest.runtime.retry_attempts,
        "retry_backoff_seconds": manifest.runtime.retry_backoff_seconds,
        "timeout_seconds": manifest.runtime.timeout_seconds,
        "log_level": manifest.runtime.log_level,
    }


def persisted_definition_to_config_payload(
    automation: PersistedAutomationDefinition,
) -> dict[str, object]:
    return {
        "id": automation.id,
        "name": automation.name,
        "description": automation.description,
        "version": automation.version,
        "task_path": str(automation.task_path),
        "task_meta_path": str(automation.task_meta_path),
        "entrypoint": automation.entrypoint,
        "schedule_kind": automation.schedule_kind,
        "schedule_payload": dict(automation.schedule_payload),
        "timezone": automation.timezone,
        "output_dir": str(automation.output_dir),
        "result_json_path": str(automation.result_json_path)
        if automation.result_json_path
        else None,
        "stdout_mode": automation.stdout_mode,
        "input_overrides": dict(automation.input_overrides),
        "before_run_hooks": list(automation.before_run_hooks),
        "after_success_hooks": list(automation.after_success_hooks),
        "after_failure_hooks": list(automation.after_failure_hooks),
        "retry_attempts": automation.retry_attempts,
        "retry_backoff_seconds": automation.retry_backoff_seconds,
        "timeout_seconds": automation.timeout_seconds,
        "log_level": automation.log_level,
    }


def _schedule_values(automation: PersistedAutomationDefinition) -> dict[str, Any]:
    values = {"mode": automation.schedule_kind, "timezone": automation.timezone}
    for key, value in automation.schedule_payload.items():
        if key not in {"mode", "timezone"}:
            values[key] = value
    return values


def _remap_result_json_path(
    source_artifact_dir: Path,
    source_result_json_path: Path | None,
    target_artifact_dir: Path,
) -> Path | None:
    if source_result_json_path is None:
        return None
    try:
        relative = source_result_json_path.relative_to(source_artifact_dir)
    except ValueError:
        return target_artifact_dir / source_result_json_path.name
    return target_artifact_dir / relative
