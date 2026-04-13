from __future__ import annotations

from pathlib import Path

import pytest

from browser_cli.task_runtime.entrypoint import (
    load_task_entrypoint,
    parse_input_overrides,
    validate_task_dir,
)
from browser_cli.task_runtime.errors import TaskEntrypointError, TaskMetadataError


def test_validate_task_dir_rejects_missing_task_meta(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text("def run(flow, inputs):\n    return {}\n", encoding="utf-8")
    with pytest.raises(TaskMetadataError, match="task.meta.json"):
        validate_task_dir(tmp_path)


def test_load_task_entrypoint_returns_callable(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text(
        "def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8"
    )
    (tmp_path / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    entrypoint = load_task_entrypoint(tmp_path / "task.py", "run")
    assert callable(entrypoint)


def test_parse_input_overrides_merges_json_and_set_values() -> None:
    payload = parse_input_overrides(["url=https://example.com"], '{"timeout": 5}')
    assert payload == {"timeout": 5, "url": "https://example.com"}


def test_load_task_entrypoint_rejects_extra_required_positionals(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text(
        "def run(flow, inputs, required):\n    return {'ok': True}\n",
        encoding="utf-8",
    )
    (tmp_path / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    with pytest.raises(TaskEntrypointError, match="required positional parameters"):
        load_task_entrypoint(tmp_path / "task.py", "run")
