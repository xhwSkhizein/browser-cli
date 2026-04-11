"""Workflow manifest loading and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from browser_cli.errors import InvalidInputError
from browser_cli.task_runtime.models import validate_task_metadata
from browser_cli.workflow.models import (
    WorkflowHooks,
    WorkflowIdentity,
    WorkflowManifest,
    WorkflowOutputs,
    WorkflowRuntime,
    WorkflowTaskConfig,
)


def load_workflow_manifest(path: str | Path) -> WorkflowManifest:
    manifest_path = Path(path).expanduser().resolve()
    if not manifest_path.exists():
        raise InvalidInputError(f"Workflow manifest does not exist: {manifest_path}")
    data = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise InvalidInputError(f"Workflow manifest must be a TOML object: {manifest_path}")

    workflow_section = _require_section(data, "workflow", manifest_path)
    task_section = _require_section(data, "task", manifest_path)
    outputs_section = dict(data.get("outputs") or {})
    hooks_section = dict(data.get("hooks") or {})
    runtime_section = dict(data.get("runtime") or {})
    inputs_section = dict(data.get("inputs") or {})
    schedule_section = dict(data.get("schedule") or {})

    base_dir = manifest_path.parent
    task_path = _resolve_relative(base_dir, _require_string(task_section, "path", manifest_path))
    meta_path = _resolve_relative(
        base_dir, _require_string(task_section, "meta_path", manifest_path)
    )
    if not task_path.exists():
        raise InvalidInputError(f"Task file does not exist: {task_path}")
    if not meta_path.exists():
        raise InvalidInputError(f"Task metadata file does not exist: {meta_path}")
    validate_task_metadata(json.loads(meta_path.read_text(encoding="utf-8")), source=str(meta_path))

    artifact_dir = _resolve_relative(
        base_dir, str(outputs_section.get("artifact_dir") or "artifacts")
    )
    result_json_raw = outputs_section.get("result_json_path")
    result_json_path = (
        _resolve_relative(base_dir, str(result_json_raw)) if result_json_raw else None
    )

    return WorkflowManifest(
        manifest_path=manifest_path,
        workflow=WorkflowIdentity(
            id=_require_string(workflow_section, "id", manifest_path),
            name=_require_string(workflow_section, "name", manifest_path),
            description=str(workflow_section.get("description") or ""),
            version=str(workflow_section.get("version") or "0.1.0"),
        ),
        task=WorkflowTaskConfig(
            path=task_path,
            meta_path=meta_path,
            entrypoint=str(task_section.get("entrypoint") or "run"),
        ),
        inputs=inputs_section,
        schedule=schedule_section,
        outputs=WorkflowOutputs(
            artifact_dir=artifact_dir,
            result_json_path=result_json_path,
            stdout=str(outputs_section.get("stdout") or "json"),
        ),
        hooks=WorkflowHooks(
            before_run=tuple(_as_string_list(hooks_section.get("before_run"))),
            after_success=tuple(_as_string_list(hooks_section.get("after_success"))),
            after_failure=tuple(_as_string_list(hooks_section.get("after_failure"))),
        ),
        runtime=WorkflowRuntime(
            timeout_seconds=float(runtime_section["timeout_seconds"])
            if runtime_section.get("timeout_seconds") is not None
            else None,
            retry_attempts=int(runtime_section.get("retry_attempts") or 0),
            log_level=str(runtime_section.get("log_level") or "info"),
        ),
    )


def _require_section(data: dict[str, Any], key: str, source: Path) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise InvalidInputError(f"Workflow manifest requires a [{key}] section: {source}")
    return value


def _require_string(section: dict[str, Any], key: str, source: Path) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError(f"Workflow manifest requires non-empty {key!r}: {source}")
    return value.strip()


def _resolve_relative(base_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]
