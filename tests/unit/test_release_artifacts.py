from __future__ import annotations

import email
import tarfile
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


def test_built_wheel_contains_importable_node_client() -> None:
    wheels = list((_repo_root() / "dist").glob("*.whl"))
    if not wheels:
        pytest.skip("Build a wheel before running this test: uv build --wheel")
    wheel_path = max(wheels, key=lambda path: path.stat().st_mtime)
    with zipfile.ZipFile(wheel_path) as archive:
        assert "browser_cli/task_runtime/node/client.mjs" in archive.namelist()
        assert "browser_cli/task_runtime/node/package.json" in archive.namelist()
        assert b"export class BrowserCliClient" in archive.read(
            "browser_cli/task_runtime/node/client.mjs"
        )


def test_source_distribution_contains_new_extension_modules_and_acceptance_tests() -> None:
    root = _repo_root()
    distributions = list((root / "dist").glob("*.tar.gz"))
    if not distributions:
        pytest.skip("Build a source distribution before running this test: uv build")
    distribution = max(distributions, key=lambda path: path.stat().st_mtime)
    with tarfile.open(distribution) as archive:
        prefix = archive.getnames()[0].split("/", 1)[0]
        for relative in (
            "browser-cli-extension/src/offscreen_client.js",
            "browser-cli-extension/src/offscreen_image.js",
            "tests/integration/test_capture_context_batch.py",
            "tests/unit/test_batch.py",
        ):
            content = archive.extractfile(f"{prefix}/{relative}")
            assert content is not None
            assert content.read() == (root / relative).read_bytes()
