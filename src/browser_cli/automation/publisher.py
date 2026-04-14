"""Publish local task directories as versioned automation snapshots."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from browser_cli.automation.loader import load_automation_manifest
from browser_cli.automation.models import AutomationManifest
from browser_cli.automation.toml import dumps_toml_sections
from browser_cli.constants import AppPaths
from browser_cli.task_runtime import validate_task_dir


@dataclass(slots=True, frozen=True)
class PublishedAutomation:
    automation_id: str
    automation_name: str
    version: int
    snapshot_dir: Path
    manifest_path: Path
    output_dir: Path
    manifest_source: str


def publish_task_dir(task_dir: Path, *, app_paths: AppPaths) -> PublishedAutomation:
    metadata = validate_task_dir(task_dir)
    automation_id = str(metadata["task"]["id"])
    automation_name = str(metadata["task"]["name"])
    automation_root = app_paths.automations_dir / automation_id
    versions_dir = automation_root / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    while True:
        version = _next_version(versions_dir)
        snapshot_dir = versions_dir / str(version)
        try:
            snapshot_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        break

    task_path = snapshot_dir / "task.py"
    task_meta_path = snapshot_dir / "task.meta.json"
    shutil.copy2(task_dir / "task.py", task_path)
    shutil.copy2(task_dir / "task.meta.json", task_meta_path)

    source_manifest_path = task_dir / "automation.toml"
    if source_manifest_path.exists():
        manifest_source = "task_dir"
        source_manifest = load_automation_manifest(source_manifest_path)
        rendered_manifest = render_automation_manifest_from_manifest(
            source_manifest,
            version=version,
            task_path=task_path,
            task_meta_path=task_meta_path,
            output_dir=automation_root,
        )
    else:
        manifest_source = "generated_defaults"
        rendered_manifest = render_automation_manifest(
            automation_id=automation_id,
            name=automation_name,
            version=version,
            task_path=task_path,
            task_meta_path=task_meta_path,
            output_dir=automation_root,
        )

    manifest_path = snapshot_dir / "automation.toml"
    manifest_path.write_text(rendered_manifest, encoding="utf-8")
    (snapshot_dir / "publish.json").write_text(
        json.dumps(
            {
                "automation_id": automation_id,
                "name": automation_name,
                "version": version,
                "manifest_source": manifest_source,
                "source_task_path": str(task_dir),
                "snapshot_dir": str(snapshot_dir),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return PublishedAutomation(
        automation_id=automation_id,
        automation_name=automation_name,
        version=version,
        snapshot_dir=snapshot_dir,
        manifest_path=manifest_path,
        output_dir=automation_root,
        manifest_source=manifest_source,
    )


def render_automation_manifest(
    *,
    automation_id: str,
    name: str,
    version: int,
    task_path: Path,
    task_meta_path: Path,
    output_dir: Path,
) -> str:
    sections: list[tuple[str, dict[str, Any]]] = [
        (
            "automation",
            {
                "id": str(automation_id),
                "name": str(name),
                "version": str(version),
            },
        ),
        (
            "task",
            {
                "path": str(task_path),
                "meta_path": str(task_meta_path),
                "entrypoint": "run",
            },
        ),
        ("inputs", {}),
        ("schedule", {"mode": "manual", "timezone": "UTC"}),
        ("outputs", {"artifact_dir": str(output_dir), "stdout": "json"}),
        (
            "hooks",
            {
                "before_run": [],
                "after_success": [],
                "after_failure": [],
            },
        ),
        (
            "runtime",
            {
                "retry_attempts": 0,
                "retry_backoff_seconds": 0,
                "log_level": "info",
            },
        ),
    ]
    return dumps_toml_sections(sections)


def render_automation_manifest_from_manifest(
    manifest: AutomationManifest,
    *,
    version: int,
    task_path: Path,
    task_meta_path: Path,
    output_dir: Path,
) -> str:
    schedule = dict(manifest.schedule)
    artifact_dir = output_dir
    result_json_path = _remap_result_json_path(
        manifest.outputs.artifact_dir,
        manifest.outputs.result_json_path,
        artifact_dir,
    )
    sections: list[tuple[str, dict[str, Any]]] = [
        (
            "automation",
            {
                "id": str(manifest.automation.id),
                "name": str(manifest.automation.name),
                "description": str(manifest.automation.description),
                "version": str(version),
            },
        ),
        (
            "task",
            {
                "path": str(task_path),
                "meta_path": str(task_meta_path),
                "entrypoint": str(manifest.task.entrypoint),
            },
        ),
        ("inputs", dict(manifest.inputs)),
        ("schedule", schedule),
        (
            "outputs",
            {
                "artifact_dir": str(artifact_dir),
                "result_json_path": str(result_json_path) if result_json_path else None,
                "stdout": str(manifest.outputs.stdout),
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
                "retry_attempts": int(manifest.runtime.retry_attempts),
                "retry_backoff_seconds": int(manifest.runtime.retry_backoff_seconds),
                "timeout_seconds": manifest.runtime.timeout_seconds,
                "log_level": str(manifest.runtime.log_level),
            },
        ),
    ]
    return dumps_toml_sections(sections)


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


def _next_version(versions_dir: Path) -> int:
    versions = [
        int(path.name) for path in versions_dir.iterdir() if path.is_dir() and path.name.isdigit()
    ]
    return max(versions, default=0) + 1
