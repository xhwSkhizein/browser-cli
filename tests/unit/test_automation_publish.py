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
    assert manifest.task.meta_path == tmp_path / "task.meta.json"


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


def test_publish_task_dir_preserves_source_manifest_fields(tmp_path: Path, monkeypatch) -> None:
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
    (task_dir / "automation.toml").write_text(
        "[automation]\n"
        'id = "demo"\n'
        'name = "Demo"\n'
        "[task]\n"
        'path = "task.py"\n'
        'meta_path = "task.meta.json"\n'
        "[inputs]\n"
        'url = "https://example.com"\n'
        "[schedule]\n"
        'mode = "manual"\n'
        'timezone = "Asia/Shanghai"\n'
        "[outputs]\n"
        'artifact_dir = "artifacts"\n'
        'result_json_path = "artifacts/result.json"\n'
        'stdout = "text"\n'
        "[runtime]\n"
        "retry_attempts = 1\n"
        "retry_backoff_seconds = 7\n",
        encoding="utf-8",
    )

    published = publish_task_dir(task_dir, app_paths=get_app_paths())
    manifest = load_automation_manifest(published.manifest_path)

    assert published.manifest_source == "task_dir"
    assert manifest.inputs == {"url": "https://example.com"}
    assert manifest.schedule["timezone"] == "Asia/Shanghai"
    assert manifest.outputs.result_json_path is not None
    assert manifest.outputs.stdout == "text"
    assert manifest.runtime.retry_backoff_seconds == 7


def test_publish_task_dir_preserves_hooks_timeout_and_log_level(
    tmp_path: Path, monkeypatch
) -> None:
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
    (task_dir / "automation.toml").write_text(
        "[automation]\n"
        'id = "demo"\n'
        'name = "Demo"\n'
        "[task]\n"
        'path = "task.py"\n'
        'meta_path = "task.meta.json"\n'
        "[hooks]\n"
        'before_run = ["echo before"]\n'
        'after_success = ["echo success"]\n'
        'after_failure = ["echo failure"]\n'
        "[runtime]\n"
        "timeout_seconds = 6.5\n"
        'log_level = "debug"\n',
        encoding="utf-8",
    )

    published = publish_task_dir(task_dir, app_paths=get_app_paths())
    manifest = load_automation_manifest(published.manifest_path)

    assert manifest.hooks.before_run == ("echo before",)
    assert manifest.hooks.after_success == ("echo success",)
    assert manifest.hooks.after_failure == ("echo failure",)
    assert manifest.runtime.timeout_seconds == 6.5
    assert manifest.runtime.log_level == "debug"


def test_publish_task_dir_generates_defaults_when_manifest_is_absent(
    tmp_path: Path, monkeypatch
) -> None:
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
    manifest = load_automation_manifest(published.manifest_path)

    assert published.manifest_source == "generated_defaults"
    assert manifest.schedule["timezone"] == "UTC"
    assert manifest.inputs == {}


def test_publish_task_dir_accepts_douyin_example(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    published = publish_task_dir(
        Path(__file__).resolve().parents[2] / "tasks" / "douyin_video_download",
        app_paths=get_app_paths(),
    )
    assert published.automation_id == "douyin_video_download"
    assert published.manifest_path.exists()
    assert (published.snapshot_dir / "automation.toml").exists()
