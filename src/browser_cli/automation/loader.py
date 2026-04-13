"""Automation manifest loading helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

from browser_cli.automation.models import (
    AutomationHooks,
    AutomationIdentity,
    AutomationManifest,
    AutomationOutputs,
    AutomationRuntime,
    AutomationTaskConfig,
)
from browser_cli.errors import InvalidInputError
from browser_cli.task_runtime import validate_task_metadata


def load_automation_manifest(path: str | Path) -> AutomationManifest:
    manifest_path = Path(path).expanduser().resolve()
    if not manifest_path.exists():
        raise InvalidInputError(f"Automation manifest does not exist: {manifest_path}")
    data = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise InvalidInputError(f"Automation manifest must be a TOML object: {manifest_path}")

    automation_section = _require_section(data, "automation", manifest_path)
    task_section = _require_section(data, "task", manifest_path)
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
    return AutomationManifest(
        manifest_path=manifest_path,
        automation=AutomationIdentity(
            id=_require_string(automation_section, "id", manifest_path),
            name=_require_string(automation_section, "name", manifest_path),
            description=str(automation_section.get("description") or ""),
            version=str(automation_section.get("version") or "1"),
        ),
        task=AutomationTaskConfig(
            path=task_path,
            meta_path=meta_path,
            entrypoint=str(task_section.get("entrypoint") or "run"),
        ),
        inputs=dict(data.get("inputs") or {}),
        schedule=dict(data.get("schedule") or {}),
        outputs=AutomationOutputs(
            artifact_dir=_resolve_relative(
                base_dir,
                str((data.get("outputs") or {}).get("artifact_dir") or "artifacts"),
            ),
            result_json_path=(
                _resolve_relative(
                    base_dir, str((data.get("outputs") or {}).get("result_json_path"))
                )
                if (data.get("outputs") or {}).get("result_json_path")
                else None
            ),
            stdout=str((data.get("outputs") or {}).get("stdout") or "json"),
        ),
        hooks=AutomationHooks(
            before_run=tuple(_as_string_list((data.get("hooks") or {}).get("before_run"))),
            after_success=tuple(_as_string_list((data.get("hooks") or {}).get("after_success"))),
            after_failure=tuple(_as_string_list((data.get("hooks") or {}).get("after_failure"))),
        ),
        runtime=AutomationRuntime(
            timeout_seconds=float((data.get("runtime") or {})["timeout_seconds"])
            if (data.get("runtime") or {}).get("timeout_seconds") is not None
            else None,
            retry_attempts=int((data.get("runtime") or {}).get("retry_attempts") or 0),
            log_level=str((data.get("runtime") or {}).get("log_level") or "info"),
        ),
    )


def _require_section(data: dict[str, Any], key: str, source: Path) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise InvalidInputError(f"Automation manifest requires a [{key}] section: {source}")
    return value


def _require_string(section: dict[str, Any], key: str, source: Path) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError(f"Automation manifest requires non-empty {key!r}: {source}")
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
