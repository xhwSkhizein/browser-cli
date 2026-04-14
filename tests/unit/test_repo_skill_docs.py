from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (_repo_root() / path).read_text(encoding="utf-8")


def test_browser_cli_skill_topology_exists() -> None:
    skills_dir = _repo_root() / "skills"
    actual = {
        path.name
        for path in skills_dir.iterdir()
        if path.is_dir() and path.name.startswith("browser-cli-")
    }

    assert actual == {
        "browser-cli-delivery",
        "browser-cli-explore",
        "browser-cli-converge",
    }


def test_agents_points_to_browser_cli_delivery_skill() -> None:
    agents_text = _read("AGENTS.md")

    assert "skills/browser-cli-delivery/SKILL.md" in agents_text


def test_browser_cli_explore_skill_records_feedback_into_task_metadata() -> None:
    skill_text = _read("skills/browser-cli-explore/SKILL.md")

    assert "task.meta.json" in skill_text
    assert "browser-cli is the primary browser execution path" in skill_text
    assert "environment" in skill_text
    assert "success_path" in skill_text
    assert "recovery_hints" in skill_text
    assert "failures" in skill_text
    assert "knowledge" in skill_text
    assert "Do not record raw logs" in skill_text


def test_browser_cli_converge_skill_centers_task_py_and_flow_validation() -> None:
    skill_text = _read("skills/browser-cli-converge/SKILL.md")

    assert "task.py is the single source of execution logic" in skill_text
    assert "browser_cli.task_runtime.Flow" in skill_text
    assert "browser-cli task validate" in skill_text
    assert "browser-cli task run" in skill_text
    assert "must stay aligned with task.meta.json" in skill_text


def test_browser_cli_delivery_skill_orchestrates_explore_converge_and_optional_automation() -> None:
    skill_text = _read("skills/browser-cli-delivery/SKILL.md")

    assert "browser-cli-explore" in skill_text
    assert "browser-cli-converge" in skill_text
    assert "task.py + task.meta.json" in skill_text
    assert "automation.toml" in skill_text
    assert "publish" in skill_text
    assert "If validation fails because evidence is missing, go back to explore" in skill_text
