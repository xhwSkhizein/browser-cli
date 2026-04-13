from __future__ import annotations

from pathlib import Path

import pytest

from browser_cli.automation.hooks import run_hook_commands
from browser_cli.automation.loader import load_automation_manifest
from browser_cli.task_runtime import parse_input_overrides
from browser_cli.task_runtime.models import TaskMetadataError, validate_task_metadata

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_validate_task_metadata_requires_sections() -> None:
    with pytest.raises(TaskMetadataError):
        validate_task_metadata({"task": {}}, source="memory")


def test_parse_input_overrides_merges_json_and_set() -> None:
    payload = parse_input_overrides(["mode=snapshot", "limit=5"], '{"url":"https://example.com"}')
    assert payload == {
        "url": "https://example.com",
        "mode": "snapshot",
        "limit": "5",
    }


def test_load_automation_manifest_resolves_repo_examples() -> None:
    manifest = load_automation_manifest(
        REPO_ROOT / "tasks" / "interactive_reveal_capture" / "automation.toml"
    )
    assert manifest.automation.id == "interactive_reveal_capture"
    assert manifest.task.path.name == "task.py"
    assert manifest.task.meta_path.name == "task.meta.json"


def test_load_automation_manifest_resolves_douyin_example() -> None:
    manifest = load_automation_manifest(
        REPO_ROOT / "tasks" / "douyin_video_download" / "automation.toml"
    )
    assert manifest.automation.id == "douyin_video_download"
    assert manifest.task.path.name == "task.py"
    assert manifest.task.meta_path.name == "task.meta.json"


def test_run_hook_commands_executes_shell_commands(tmp_path: Path) -> None:
    marker = tmp_path / "hook.txt"
    results = run_hook_commands((f'printf done > "{marker}"',), cwd=tmp_path)
    assert marker.read_text(encoding="utf-8") == "done"
    assert results[0]["returncode"] == 0
