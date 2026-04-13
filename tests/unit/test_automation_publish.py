from __future__ import annotations

from pathlib import Path

from browser_cli.automation.loader import load_automation_manifest
from browser_cli.automation.publisher import publish_task_dir
from browser_cli.constants import get_app_paths


def test_load_automation_manifest_resolves_snapshot_files(tmp_path: Path) -> None:
    manifest_path = tmp_path / "automation.toml"
    manifest_path.write_text(
        "[automation]\n"
        'id = "demo"\n'
        'name = "Demo"\n'
        "[task]\n"
        'path = "task.py"\n'
        'meta_path = "task.meta.json"\n',
        encoding="utf-8",
    )
    (tmp_path / "task.py").write_text(
        "def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8"
    )
    (tmp_path / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    manifest = load_automation_manifest(manifest_path)
    assert manifest.automation.id == "demo"
    assert manifest.task.path == tmp_path / "task.py"


def test_publish_task_dir_creates_versioned_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8"
    )
    (task_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    published = publish_task_dir(task_dir, app_paths=get_app_paths())
    assert published.automation_id == "demo"
    assert published.version == 1
    assert (published.snapshot_dir / "automation.toml").exists()
