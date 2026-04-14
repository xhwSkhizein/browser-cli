from __future__ import annotations

import zipfile
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_built_wheel_contains_packaged_browser_cli_skills() -> None:
    wheels = sorted((_repo_root() / "dist").glob("*.whl"))
    if not wheels:
        pytest.skip("Build a wheel before running this test: uv build --wheel")
    wheel_path = wheels[-1]
    with zipfile.ZipFile(wheel_path) as archive:
        names = set(archive.namelist())
    assert "browser_cli/packaged_skills/browser-cli-delivery/SKILL.md" in names
    assert "browser_cli/packaged_skills/browser-cli-explore/SKILL.md" in names
    assert "browser_cli/packaged_skills/browser-cli-converge/SKILL.md" in names
