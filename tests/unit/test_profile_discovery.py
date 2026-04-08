from __future__ import annotations

from pathlib import Path

import pytest

from browser_cli.errors import BrowserUnavailableError, ProfileUnavailableError
from browser_cli.profiles.discovery import discover_chrome_executable, discover_user_data_dir, discover_chrome_environment


def test_discover_user_data_dir_for_macos() -> None:
    home = Path("/Users/example")
    result = discover_user_data_dir(platform="darwin", home=home)
    assert result == home / "Library" / "Application Support" / "Google" / "Chrome"


def test_discover_user_data_dir_for_linux() -> None:
    home = Path("/home/example")
    result = discover_user_data_dir(platform="linux", home=home)
    assert result == home / ".config" / "google-chrome"


def test_discover_chrome_executable_unsupported_platform() -> None:
    with pytest.raises(BrowserUnavailableError):
        discover_chrome_executable(platform="win32")


def test_discover_chrome_environment_missing_user_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "browser_cli.profiles.discovery.discover_chrome_executable",
        lambda platform=None: tmp_path / "Google Chrome",
    )
    monkeypatch.setattr(
        "browser_cli.profiles.discovery.discover_user_data_dir",
        lambda platform=None, home=None: tmp_path / "missing-profile-root",
    )
    with pytest.raises(ProfileUnavailableError):
        discover_chrome_environment()


def test_discover_chrome_environment_detects_lock(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "Google Chrome"
    executable.write_text("", encoding="utf-8")
    user_data = tmp_path / "user-data"
    profile = user_data / "Default"
    profile.mkdir(parents=True)
    (user_data / "SingletonLock").write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "browser_cli.profiles.discovery.discover_chrome_executable",
        lambda platform=None: executable,
    )
    monkeypatch.setattr(
        "browser_cli.profiles.discovery.discover_user_data_dir",
        lambda platform=None, home=None: user_data,
    )
    with pytest.raises(ProfileUnavailableError):
        discover_chrome_environment()

