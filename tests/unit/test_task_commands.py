from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from browser_cli.cli.main import build_parser
from browser_cli.commands.task import run_task_command
from browser_cli.constants import get_app_paths


def test_build_parser_exposes_task_and_automation_commands(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path))
    parser = build_parser()
    subparsers = next(action for action in parser._actions if action.dest == "command")
    assert "task" in subparsers.choices
    assert "automation" in subparsers.choices
    assert "workflow" not in subparsers.choices


def test_get_app_paths_exposes_task_and_automation_roots(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path))
    paths = get_app_paths()
    assert paths.tasks_dir == tmp_path / "tasks"
    assert paths.automations_dir == tmp_path / "automations"
    assert paths.automation_db_path == tmp_path / "automations.db"


def test_task_validate_returns_json_payload(tmp_path: Path) -> None:
    task_dir = tmp_path / "demo"
    task_dir.mkdir()
    (task_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8"
    )
    (task_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    payload = json.loads(
        run_task_command(Namespace(task_subcommand="validate", path=str(task_dir)))
    )
    assert payload["ok"] is True
    assert payload["data"]["valid"] is True
    assert payload["data"]["task"]["id"] == "demo"


def test_task_run_executes_task_dir(tmp_path: Path) -> None:
    task_dir = tmp_path / "demo"
    task_dir.mkdir()
    (task_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'url': inputs['url'], 'ok': True}\n",
        encoding="utf-8",
    )
    (task_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    payload = json.loads(
        run_task_command(
            Namespace(
                task_subcommand="run",
                path=str(task_dir),
                set_values=["url=https://example.com"],
                inputs_json=None,
            )
        )
    )
    assert payload["ok"] is True
    assert payload["data"]["ok"] is True
    assert payload["data"]["url"] == "https://example.com"


def test_task_examples_lists_curated_examples() -> None:
    payload = run_task_command(Namespace(task_subcommand="examples"))
    assert "interactive_reveal_capture" in payload
    assert "lazy_scroll_capture" in payload


def test_task_template_prints_three_contract_files() -> None:
    payload = run_task_command(Namespace(task_subcommand="template", output=None))
    assert "task.py" in payload
    assert "task.meta.json" in payload
    assert "automation.toml" in payload


def test_task_template_output_writes_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "demo"
    run_task_command(Namespace(task_subcommand="template", output=str(output_dir)))
    assert (output_dir / "task.py").exists()
    assert (output_dir / "task.meta.json").exists()
    assert (output_dir / "automation.toml").exists()
