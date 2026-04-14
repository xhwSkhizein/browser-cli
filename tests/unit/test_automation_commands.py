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


def test_automation_inspect_combines_service_and_snapshot_data(monkeypatch, tmp_path: Path) -> None:
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
    assert payload["data"]["automation"]["id"] == "demo"
    assert payload["data"]["automation"]["name"] == "Demo Snapshot"
    assert payload["data"]["versions"][0]["version"] == 2
    assert payload["data"]["latest_run"] is None
    assert payload["data"]["summary"]["automation_id"] == "demo"
    assert payload["data"]["summary"]["selected_version"] == 2
    assert payload["data"]["summary"]["latest_run_status"] is None
