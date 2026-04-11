from __future__ import annotations

from pathlib import Path

import pytest

from browser_cli.errors import BrowserUnavailableError, ProfileUnavailableError
from browser_cli.profiles.discovery import (
    discover_chrome_environment,
    discover_chrome_executable,
    discover_default_profile_dir,
    load_profile_info_cache,
    resolve_profile_directory,
    discover_user_data_dir,
)


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
    result = discover_chrome_environment(fallback_home=tmp_path)
    assert result.source == "managed"
    assert result.user_data_dir == tmp_path / ".browser-cli" / "default-profile"
    assert (result.user_data_dir / "Default").exists()


def test_discover_chrome_environment_detects_lock(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "Google Chrome"
    executable.write_text("", encoding="utf-8")
    user_data = tmp_path / ".browser-cli" / "default-profile"
    profile = user_data / "Default"
    profile.mkdir(parents=True)
    (user_data / "SingletonLock").write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "browser_cli.profiles.discovery.discover_chrome_executable",
        lambda platform=None: executable,
    )
    monkeypatch.setattr(
        "browser_cli.profiles.discovery.discover_default_profile_dir",
        lambda home=None: user_data,
    )
    with pytest.raises(ProfileUnavailableError):
        discover_chrome_environment(allow_default_fallback=False)


def test_load_profile_info_cache_reads_local_state(tmp_path: Path) -> None:
    user_data = tmp_path / "user-data"
    user_data.mkdir()
    (user_data / "Local State").write_text(
        """
        {
          "profile": {
            "info_cache": {
              "Profile 1": {"name": "Work", "active_time": 10},
              "Profile 3": {"name": "Personal", "active_time": 20}
            }
          }
        }
        """,
        encoding="utf-8",
    )

    info_cache = load_profile_info_cache(user_data)
    assert info_cache["Profile 1"]["name"] == "Work"
    assert info_cache["Profile 3"]["active_time"] == 20


def test_resolve_profile_directory_prefers_most_recent_local_state_entry(tmp_path: Path) -> None:
    user_data = tmp_path / "user-data"
    (user_data / "Profile 1").mkdir(parents=True)
    (user_data / "Profile 3").mkdir(parents=True)
    (user_data / "Local State").write_text(
        """
        {
          "profile": {
            "info_cache": {
              "Profile 1": {"name": "Work", "active_time": 10},
              "Profile 3": {"name": "Personal", "active_time": 20}
            }
          }
        }
        """,
        encoding="utf-8",
    )

    directory, name = resolve_profile_directory(user_data)
    assert directory == "Profile 3"
    assert name == "Personal"


def test_resolve_profile_directory_falls_back_to_default_when_local_state_missing(tmp_path: Path) -> None:
    user_data = tmp_path / "user-data"
    (user_data / "Default").mkdir(parents=True)

    directory, name = resolve_profile_directory(user_data)
    assert directory == "Default"
    assert name is None


def test_resolve_profile_directory_uses_preferred_when_provided(tmp_path: Path) -> None:
    user_data = tmp_path / "user-data"
    (user_data / "Profile 1").mkdir(parents=True)

    directory, name = resolve_profile_directory(user_data, preferred="Profile 1")
    assert directory == "Profile 1"
    assert name is None


def test_discover_default_profile_dir() -> None:
    home = Path("/Users/example")
    result = discover_default_profile_dir(home)
    assert result == home / ".browser-cli" / "default-profile"


def test_discover_chrome_environment_uses_managed_profile_root(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "Google Chrome"
    executable.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "browser_cli.profiles.discovery.discover_chrome_executable",
        lambda platform=None: executable,
    )

    result = discover_chrome_environment(fallback_home=tmp_path)
    assert result.source == "managed"
    assert result.user_data_dir == tmp_path / ".browser-cli" / "default-profile"
    assert (result.user_data_dir / "Default").exists()


def test_discover_chrome_environment_raises_when_managed_profile_locked(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "Google Chrome"
    executable.write_text("", encoding="utf-8")
    fallback_root = tmp_path / ".browser-cli" / "default-profile"
    fallback_root.mkdir(parents=True)
    (fallback_root / "SingletonLock").write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "browser_cli.profiles.discovery.discover_chrome_executable",
        lambda platform=None: executable,
    )
    monkeypatch.setattr(
        "browser_cli.profiles.discovery.discover_default_profile_dir",
        lambda home=None: fallback_root,
    )

    with pytest.raises(ProfileUnavailableError):
        discover_chrome_environment(fallback_home=tmp_path)
