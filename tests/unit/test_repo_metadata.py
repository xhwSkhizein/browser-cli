from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_pyproject() -> dict[str, object]:
    with (_repo_root() / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_repo_uses_uv_dependency_groups_for_dev_tools() -> None:
    data = _load_pyproject()

    assert data["dependency-groups"]["dev"] == [
        "pytest>=8.0",
        "ruff>=0.4.0",
        "mypy>=1.10.0",
    ]
    assert data["tool"]["uv"]["default-groups"] == ["dev"]
    assert "dev" not in data["project"].get("optional-dependencies", {})


def test_repo_pins_python_version_for_uv() -> None:
    assert (_repo_root() / ".python-version").read_text(encoding="utf-8").strip() == "3.10"


def test_repo_tracks_uv_lockfile() -> None:
    assert (_repo_root() / "uv.lock").exists()
