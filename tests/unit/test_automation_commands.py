from __future__ import annotations

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
