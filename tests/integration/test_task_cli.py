from __future__ import annotations

import json
from pathlib import Path

from browser_cli.cli.main import main


def _run_cli_json(args: list[str], capsys) -> dict:
    exit_code = main(args)
    captured = capsys.readouterr()
    assert exit_code == 0, captured.err
    return json.loads(captured.out)


def test_task_validate_and_run_against_local_fixture(capsys, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    task_dir = tmp_path / "fixture_task"
    task_dir.mkdir()
    (task_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'url': inputs['url'], 'ok': True}\n",
        encoding="utf-8",
    )
    (task_dir / "task.meta.json").write_text(
        '{"task":{"id":"fixture","name":"Fixture","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )

    validate_payload = _run_cli_json(["task", "validate", str(task_dir)], capsys)
    assert validate_payload["data"]["valid"] is True

    run_payload = _run_cli_json(
        ["task", "run", str(task_dir), "--set", "url=https://example.com"],
        capsys,
    )
    assert run_payload["data"]["url"] == "https://example.com"
    assert run_payload["data"]["ok"] is True
