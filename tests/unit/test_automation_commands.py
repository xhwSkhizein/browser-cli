from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from browser_cli.commands.automation import run_automation_command


def test_automation_publish_returns_snapshot_metadata(monkeypatch, tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8"
    )
    (task_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "browser_cli.commands.automation.ensure_automation_service_running",
        lambda: None,
    )
    monkeypatch.setattr(
        "browser_cli.commands.automation.request_automation_service",
        lambda method, path, body=None, start_if_needed=True: {"ok": True, "data": {"id": "demo"}},
    )
    payload = run_automation_command(Namespace(automation_subcommand="publish", path=str(task_dir)))
    assert '"automation_id": "demo"' in payload
    assert '"version": 1' in payload


def test_automation_publish_reports_next_commands(monkeypatch, tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8"
    )
    (task_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "browser_cli.commands.automation.ensure_automation_service_running",
        lambda: None,
    )
    monkeypatch.setattr(
        "browser_cli.commands.automation.request_automation_service",
        lambda method, path, body=None, start_if_needed=True: {"ok": True, "data": {"id": "demo"}},
    )
    payload = json.loads(
        run_automation_command(Namespace(automation_subcommand="publish", path=str(task_dir)))
    )
    assert payload["data"]["published"]["source_task_dir"] == str(task_dir.resolve())
    assert payload["data"]["next_commands"]["inspect"] == "browser-cli automation inspect demo"


def test_automation_publish_returns_manifest_source(monkeypatch, tmp_path: Path) -> None:
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
        'meta_path = "task.meta.json"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "browser_cli.commands.automation.ensure_automation_service_running",
        lambda: None,
    )
    monkeypatch.setattr(
        "browser_cli.commands.automation.request_automation_service",
        lambda method, path, body=None, start_if_needed=True: {"ok": True, "data": {"id": "demo"}},
    )
    payload = json.loads(
        run_automation_command(Namespace(automation_subcommand="publish", path=str(task_dir)))
    )
    assert payload["data"]["published"]["manifest_source"] == "task_dir"


def test_automation_list_returns_service_items(monkeypatch) -> None:
    monkeypatch.setattr(
        "browser_cli.commands.automation.request_automation_service",
        lambda method, path, body=None, start_if_needed=True: {
            "ok": True,
            "data": [{"id": "demo", "version": "2", "enabled": True, "latest_run": None}],
        },
    )
    payload = json.loads(run_automation_command(Namespace(automation_subcommand="list")))
    assert payload["data"]["automations"][0]["id"] == "demo"


def test_automation_versions_reads_snapshot_versions(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    version_dir = tmp_path / "home" / "automations" / "demo" / "versions" / "3"
    version_dir.mkdir(parents=True)
    (version_dir / "publish.json").write_text(
        f'{{"automation_id":"demo","version":3,"source_task_path":"/tmp/task","snapshot_dir":"{version_dir}"}}',
        encoding="utf-8",
    )
    payload = json.loads(
        run_automation_command(Namespace(automation_subcommand="versions", automation_id="demo"))
    )
    assert payload["data"]["versions"][0]["version"] == 3


def test_automation_inspect_without_version_returns_live_config(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    version_dir = tmp_path / "home" / "automations" / "demo" / "versions" / "2"
    version_dir.mkdir(parents=True)
    (version_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8"
    )
    (version_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    (version_dir / "automation.toml").write_text(
        "[automation]\n"
        'id = "demo"\n'
        'name = "Demo Snapshot"\n'
        'version = "2"\n'
        "[task]\n"
        'path = "task.py"\n'
        'meta_path = "task.meta.json"\n'
        'entrypoint = "run"\n'
        "[schedule]\n"
        'mode = "manual"\n',
        encoding="utf-8",
    )
    (version_dir / "publish.json").write_text(
        f'{{"automation_id":"demo","version":2,"source_task_path":"/tmp/task","snapshot_dir":"{version_dir}"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "browser_cli.commands.automation.request_automation_service",
        lambda method, path, body=None, start_if_needed=True: {
            "ok": True,
            "data": {
                "id": "demo",
                "version": "2",
                "task_path": str(version_dir / "task.py"),
                "task_meta_path": str(version_dir / "task.meta.json"),
                "schedule_kind": "manual",
                "schedule_payload": {"mode": "manual"},
                "latest_run": {"status": "success"},
            },
        },
    )
    payload = json.loads(
        run_automation_command(
            Namespace(automation_subcommand="inspect", automation_id="demo", version=None)
        )
    )
    assert payload["data"]["snapshot_config"] is None
    assert payload["data"]["live_config"]["id"] == "demo"
    assert payload["data"]["versions"][0]["version"] == 2
    assert payload["data"]["latest_run"] == {"status": "success"}
    assert payload["data"]["summary"]["automation_id"] == "demo"
    assert payload["data"]["summary"]["selected_version"] is None
    assert payload["data"]["summary"]["latest_run_status"] == "success"


def test_automation_inspect_version_returns_snapshot_and_live_config(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    version_dir = tmp_path / "home" / "automations" / "demo" / "versions" / "1"
    version_dir.mkdir(parents=True)
    (version_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8"
    )
    (version_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    (version_dir / "automation.toml").write_text(
        "[automation]\n"
        'id = "demo"\n'
        'name = "Demo Snapshot"\n'
        'version = "1"\n'
        "[task]\n"
        'path = "task.py"\n'
        'meta_path = "task.meta.json"\n'
        "[outputs]\n"
        'stdout = "text"\n',
        encoding="utf-8",
    )
    (version_dir / "publish.json").write_text(
        f'{{"automation_id":"demo","version":1,"source_task_path":"/tmp/task","snapshot_dir":"{version_dir}"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "browser_cli.commands.automation.request_automation_service",
        lambda method, path, body=None, start_if_needed=True: {
            "ok": True,
            "data": {
                "id": "demo",
                "name": "Demo Live",
                "version": "2",
                "task_path": str(version_dir / "task.py"),
                "task_meta_path": str(version_dir / "task.meta.json"),
                "schedule_kind": "manual",
                "schedule_payload": {"mode": "manual"},
                "stdout_mode": "json",
                "latest_run": {"status": "success"},
            },
        },
    )

    payload = json.loads(
        run_automation_command(
            Namespace(automation_subcommand="inspect", automation_id="demo", version=1)
        )
    )

    assert payload["data"]["snapshot_config"]["name"] == "Demo Snapshot"
    assert payload["data"]["snapshot_config"]["stdout_mode"] == "text"
    assert payload["data"]["live_config"]["name"] == "Demo Live"
    assert payload["data"]["latest_run"] == {"status": "success"}
    assert payload["data"]["summary"]["selected_version"] == 1


def test_automation_inspect_version_reports_snapshot_config_error(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    version_dir = tmp_path / "home" / "automations" / "demo" / "versions" / "1"
    version_dir.mkdir(parents=True)
    (version_dir / "automation.toml").write_text("[automation]\n", encoding="utf-8")
    (version_dir / "publish.json").write_text(
        f'{{"automation_id":"demo","version":1,"source_task_path":"/tmp/task","snapshot_dir":"{version_dir}"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "browser_cli.commands.automation.request_automation_service",
        lambda method, path, body=None, start_if_needed=True: {
            "ok": True,
            "data": {"id": "demo", "name": "Demo Live", "latest_run": None},
        },
    )

    payload = json.loads(
        run_automation_command(
            Namespace(automation_subcommand="inspect", automation_id="demo", version=1)
        )
    )

    assert payload["data"]["snapshot_config"] is None
    assert "snapshot_config_error" in payload["data"]
    assert payload["data"]["live_config"]["name"] == "Demo Live"


def test_automation_inspect_version_aligns_snapshot_and_live_config_shapes(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    version_dir = tmp_path / "home" / "automations" / "demo" / "versions" / "1"
    version_dir.mkdir(parents=True)
    (version_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8"
    )
    (version_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    (version_dir / "automation.toml").write_text(
        "[automation]\n"
        'id = "demo"\n'
        'name = "Demo Snapshot"\n'
        'description = "Snapshot"\n'
        'version = "1"\n'
        "[task]\n"
        'path = "task.py"\n'
        'meta_path = "task.meta.json"\n'
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
    (version_dir / "publish.json").write_text(
        f'{{"automation_id":"demo","version":1,"source_task_path":"/tmp/task","snapshot_dir":"{version_dir}"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "browser_cli.commands.automation.request_automation_service",
        lambda method, path, body=None, start_if_needed=True: {
            "ok": True,
            "data": {
                "id": "demo",
                "name": "Demo Live",
                "description": "Live",
                "version": "2",
                "task_path": str(version_dir / "task.py"),
                "task_meta_path": str(version_dir / "task.meta.json"),
                "entrypoint": "run",
                "schedule_kind": "interval",
                "schedule_payload": {
                    "mode": "interval",
                    "interval_seconds": 900,
                    "timezone": "Asia/Shanghai",
                },
                "timezone": "Asia/Shanghai",
                "output_dir": str(tmp_path / "home" / "automations" / "demo"),
                "result_json_path": str(tmp_path / "home" / "automations" / "demo" / "result.json"),
                "stdout_mode": "text",
                "input_overrides": {"url": "https://example.com"},
                "before_run_hooks": ["echo before"],
                "after_success_hooks": ["echo success"],
                "after_failure_hooks": ["echo failure"],
                "retry_attempts": 2,
                "retry_backoff_seconds": 11,
                "timeout_seconds": 42.5,
                "log_level": "debug",
                "enabled": True,
                "definition_status": "valid",
                "latest_run": {"status": "success"},
            },
        },
    )

    payload = json.loads(
        run_automation_command(
            Namespace(automation_subcommand="inspect", automation_id="demo", version=1)
        )
    )

    snapshot_keys = set(payload["data"]["snapshot_config"])
    live_keys = set(payload["data"]["live_config"])

    assert snapshot_keys == live_keys
    assert payload["data"]["snapshot_config"]["log_level"] == "debug"
    assert payload["data"]["live_config"]["retry_backoff_seconds"] == 11
    assert payload["data"]["live_config"]["log_level"] == "debug"
