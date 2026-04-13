from __future__ import annotations

import json
from argparse import Namespace

from browser_cli.commands.paths import run_paths_command


def test_paths_text_output_lists_runtime_locations(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    text = run_paths_command(Namespace(json=False))
    assert "home:" in text
    assert "tasks_dir:" in text
    assert "automations_dir:" in text
    assert "automation_db_path:" in text


def test_paths_json_payload_uses_stable_keys(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    payload = json.loads(run_paths_command(Namespace(json=True)))
    assert payload["data"]["home"].endswith("/home")
    assert payload["data"]["tasks_dir"].endswith("/home/tasks")
    assert payload["data"]["automation_service_log_path"].endswith(
        "/home/run/automation-service.log"
    )
