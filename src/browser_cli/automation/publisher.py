"""Publish local task directories as versioned automation snapshots."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

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


def publish_task_dir(task_dir: Path, *, app_paths: AppPaths) -> PublishedAutomation:
    metadata = validate_task_dir(task_dir)
    automation_id = str(metadata["task"]["id"])
    automation_name = str(metadata["task"]["name"])
    automation_root = app_paths.automations_dir / automation_id
    versions_dir = automation_root / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    version = _next_version(versions_dir)
    snapshot_dir = versions_dir / str(version)
    snapshot_dir.mkdir(parents=True, exist_ok=False)

    task_path = snapshot_dir / "task.py"
    task_meta_path = snapshot_dir / "task.meta.json"
    shutil.copy2(task_dir / "task.py", task_path)
    shutil.copy2(task_dir / "task.meta.json", task_meta_path)

    manifest_path = snapshot_dir / "automation.toml"
    manifest_path.write_text(
        render_automation_manifest(
            automation_id=automation_id,
            name=automation_name,
            version=version,
            task_path=task_path,
            task_meta_path=task_meta_path,
            output_dir=automation_root,
        ),
        encoding="utf-8",
    )
    (snapshot_dir / "publish.json").write_text(
        json.dumps(
            {
                "automation_id": automation_id,
                "name": automation_name,
                "version": version,
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
    return (
        "[automation]\n"
        f'id = "{automation_id}"\n'
        f'name = "{_escape(name)}"\n'
        f'version = "{version}"\n'
        "\n"
        "[task]\n"
        f'path = "{_escape(str(task_path))}"\n'
        f'meta_path = "{_escape(str(task_meta_path))}"\n'
        'entrypoint = "run"\n'
        "\n"
        "[inputs]\n"
        "\n"
        "[schedule]\n"
        'mode = "manual"\n'
        'timezone = "UTC"\n'
        "\n"
        "[outputs]\n"
        f'artifact_dir = "{_escape(str(output_dir))}"\n'
        'stdout = "json"\n'
        "\n"
        "[hooks]\n"
        "before_run = []\n"
        "after_success = []\n"
        "after_failure = []\n"
        "\n"
        "[runtime]\n"
        "retry_attempts = 0\n"
        'log_level = "info"\n'
    )


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _next_version(versions_dir: Path) -> int:
    versions = [
        int(path.name) for path in versions_dir.iterdir() if path.is_dir() and path.name.isdigit()
    ]
    return max(versions, default=0) + 1
