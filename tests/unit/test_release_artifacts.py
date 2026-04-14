from __future__ import annotations

import email
import zipfile
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_built_wheel_contains_packaged_browser_cli_skills() -> None:
    wheels = list((_repo_root() / "dist").glob("*.whl"))
    if not wheels:
        pytest.skip("Build a wheel before running this test: uv build --wheel")
    wheel_path = max(wheels, key=lambda path: path.stat().st_mtime)
    with zipfile.ZipFile(wheel_path) as archive:
        names = set(archive.namelist())
    assert "browser_cli/packaged_skills/browser-cli-delivery/SKILL.md" in names
    assert "browser_cli/packaged_skills/browser-cli-explore/SKILL.md" in names
    assert "browser_cli/packaged_skills/browser-cli-converge/SKILL.md" in names


def test_built_wheel_uses_a_pypi_uploadable_version() -> None:
    wheels = list((_repo_root() / "dist").glob("*.whl"))
    if not wheels:
        pytest.skip("Build a wheel before running this test: uv build --wheel")
    wheel_path = max(wheels, key=lambda path: path.stat().st_mtime)
    with zipfile.ZipFile(wheel_path) as archive:
        metadata_name = next(name for name in archive.namelist() if name.endswith("/METADATA"))
        metadata = email.message_from_bytes(archive.read(metadata_name))
    version = metadata["Version"]
    assert version is not None
    assert "+" not in version
