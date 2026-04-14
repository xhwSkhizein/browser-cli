from __future__ import annotations

from pathlib import Path

from browser_cli.automation.loader import load_automation_manifest
from browser_cli.automation.models import PersistedAutomationDefinition
from browser_cli.automation.projections import (
    manifest_to_config_payload,
    manifest_to_persisted_definition,
    manifest_to_snapshot_manifest_toml,
    persisted_definition_to_config_payload,
    persisted_definition_to_manifest_toml,
)


def _write_task_fixture(base_dir: Path) -> Path:
    task_dir = base_dir / "task"
    task_dir.mkdir()
    (task_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'ok': True}\n",
        encoding="utf-8",
    )
    (task_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    (task_dir / "automation.toml").write_text(
        "[automation]\n"
        'id = "demo"\n'
        'name = "Demo"\n'
        'description = "Semantic round-trip"\n'
        'version = "7"\n'
        "[task]\n"
        'path = "task.py"\n'
        'meta_path = "task.meta.json"\n'
        'entrypoint = "run"\n'
        "[inputs]\n"
        'url = "https://example.com"\n'
        "[schedule]\n"
        'mode = "interval"\n'
        "interval_seconds = 900\n"
        'timezone = "Asia/Shanghai"\n'
        "[outputs]\n"
        'artifact_dir = "artifacts"\n'
        'result_json_path = "artifacts/result.json"\n'
        'stdout = "text"\n'
        "[hooks]\n"
        'before_run = ["echo before"]\n'
        'after_success = ["echo success"]\n'
        'after_failure = ["echo failure"]\n'
        "[runtime]\n"
        "retry_attempts = 2\n"
        "retry_backoff_seconds = 11\n"
        "timeout_seconds = 42.5\n"
        'log_level = "debug"\n',
        encoding="utf-8",
    )
    return task_dir


def _build_persisted_definition(base_dir: Path) -> PersistedAutomationDefinition:
    return PersistedAutomationDefinition(
        id="demo",
        name="Demo",
        description="Semantic round-trip",
        version="7",
        task_path=base_dir / "live" / "task.py",
        task_meta_path=base_dir / "live" / "task.meta.json",
        entrypoint="run",
        enabled=True,
        schedule_kind="interval",
        schedule_payload={
            "mode": "interval",
            "interval_seconds": 900,
            "timezone": "Asia/Shanghai",
        },
        timezone="Asia/Shanghai",
        output_dir=base_dir / "runs",
        result_json_path=base_dir / "runs" / "result.json",
        stdout_mode="text",
        input_overrides={"url": "https://example.com"},
        before_run_hooks=("echo before",),
        after_success_hooks=("echo success",),
        after_failure_hooks=("echo failure",),
        retry_attempts=2,
        retry_backoff_seconds=11,
        timeout_seconds=42.5,
        log_level="debug",
    )


def test_manifest_to_persisted_definition_preserves_supported_fields(tmp_path: Path) -> None:
    manifest = load_automation_manifest(_write_task_fixture(tmp_path) / "automation.toml")

    persisted = manifest_to_persisted_definition(manifest, enabled=True)

    assert persisted.description == "Semantic round-trip"
    assert persisted.schedule_kind == "interval"
    assert persisted.schedule_payload["interval_seconds"] == 900
    assert persisted.timezone == "Asia/Shanghai"
    assert persisted.result_json_path is not None
    assert persisted.stdout_mode == "text"
    assert persisted.before_run_hooks == ("echo before",)
    assert persisted.after_success_hooks == ("echo success",)
    assert persisted.after_failure_hooks == ("echo failure",)
    assert persisted.retry_attempts == 2
    assert persisted.retry_backoff_seconds == 11
    assert persisted.timeout_seconds == 42.5
    assert persisted.log_level == "debug"


def test_persisted_definition_to_manifest_toml_round_trips_supported_fields(
    tmp_path: Path,
) -> None:
    automation = _build_persisted_definition(tmp_path)
    automation.task_path.parent.mkdir(parents=True)
    automation.task_path.write_text("def run(flow, inputs):\n    return {}\n", encoding="utf-8")
    automation.task_meta_path.write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )

    manifest_path = tmp_path / "exported.toml"
    manifest_path.write_text(
        persisted_definition_to_manifest_toml(automation),
        encoding="utf-8",
    )

    manifest = load_automation_manifest(manifest_path)

    assert manifest.inputs == {"url": "https://example.com"}
    assert manifest.schedule["interval_seconds"] == 900
    assert manifest.schedule["timezone"] == "Asia/Shanghai"
    assert manifest.outputs.stdout == "text"
    assert manifest.hooks.after_failure == ("echo failure",)
    assert manifest.runtime.retry_backoff_seconds == 11
    assert manifest.runtime.timeout_seconds == 42.5
    assert manifest.runtime.log_level == "debug"


def test_manifest_to_snapshot_manifest_toml_remaps_paths_without_losing_supported_fields(
    tmp_path: Path,
) -> None:
    task_dir = _write_task_fixture(tmp_path)
    manifest = load_automation_manifest(task_dir / "automation.toml")
    snapshot_dir = tmp_path / "home" / "automations" / "demo" / "versions" / "3"
    snapshot_dir.mkdir(parents=True)
    task_path = snapshot_dir / "task.py"
    task_meta_path = snapshot_dir / "task.meta.json"
    task_path.write_text("def run(flow, inputs):\n    return {}\n", encoding="utf-8")
    task_meta_path.write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )

    manifest_path = snapshot_dir / "automation.toml"
    manifest_path.write_text(
        manifest_to_snapshot_manifest_toml(
            manifest,
            version=3,
            task_path=task_path,
            task_meta_path=task_meta_path,
            output_dir=tmp_path / "home" / "automations" / "demo",
        ),
        encoding="utf-8",
    )

    snapshot_manifest = load_automation_manifest(manifest_path)

    assert snapshot_manifest.automation.version == "3"
    assert snapshot_manifest.task.path == task_path
    assert snapshot_manifest.task.meta_path == task_meta_path
    assert snapshot_manifest.outputs.result_json_path is not None
    assert snapshot_manifest.outputs.result_json_path.name == "result.json"
    assert snapshot_manifest.hooks.after_success == ("echo success",)
    assert snapshot_manifest.runtime.log_level == "debug"


def test_manifest_and_persisted_config_payloads_share_supported_keys(tmp_path: Path) -> None:
    manifest = load_automation_manifest(_write_task_fixture(tmp_path) / "automation.toml")
    persisted = _build_persisted_definition(tmp_path)

    manifest_payload = manifest_to_config_payload(manifest)
    persisted_payload = persisted_definition_to_config_payload(persisted)

    assert set(manifest_payload) == set(persisted_payload)
    assert manifest_payload["timezone"] == "Asia/Shanghai"
    assert persisted_payload["timezone"] == "Asia/Shanghai"
    assert manifest_payload["retry_backoff_seconds"] == 11
    assert persisted_payload["retry_backoff_seconds"] == 11
    assert manifest_payload["log_level"] == "debug"
    assert persisted_payload["log_level"] == "debug"
