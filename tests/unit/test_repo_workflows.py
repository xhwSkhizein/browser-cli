from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _workflow_text(name: str) -> str:
    return (_repo_root() / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_ci_workflow_is_uv_only() -> None:
    workflow = _workflow_text("ci.yml")

    assert "astral-sh/setup-uv@" in workflow
    assert "uv sync --locked --dev" in workflow
    assert "uv run pytest tests/unit -v --tb=short" in workflow
    assert 'uv run pytest tests/integration -v --tb=short -m "not smoke"' in workflow
    assert "python -m pip" not in workflow
    assert "pip install -e ." not in workflow
    assert "cache: 'pip'" not in workflow


def test_release_workflow_builds_and_publishes_with_uv() -> None:
    workflow = _workflow_text("release.yml")

    assert "astral-sh/setup-uv@" in workflow
    assert "uv build --no-sources" in workflow
    assert "uv publish" in workflow
    assert "pip install build twine" not in workflow
    assert "twine check" not in workflow
