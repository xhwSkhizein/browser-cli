"""Managed Chrome profile discovery for Browser CLI."""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from browser_cli.errors import BrowserUnavailableError, ProfileUnavailableError

DEFAULT_PROFILE_DIRECTORY = "Default"
LOCK_FILES = ("SingletonLock", "SingletonCookie", "SingletonSocket")
DEFAULT_MANAGED_ROOT = Path(".browser-cli") / "default-profile"
LOCAL_STATE_FILENAME = "Local State"


@dataclass(slots=True, frozen=True)
class ChromeEnvironment:
    executable_path: Path | None
    user_data_dir: Path
    profile_directory: str = DEFAULT_PROFILE_DIRECTORY
    profile_name: str | None = None
    source: str = "chrome"
    fallback_reason: str | None = None


def discover_chrome_environment(
    profile_directory: str | None = None,
    *,
    allow_default_fallback: bool = True,
    fallback_home: Path | None = None,
) -> ChromeEnvironment:
    executable_path = discover_chrome_executable()
    _ = allow_default_fallback
    return _discover_managed_environment(
        executable_path,
        profile_directory,
        home=fallback_home,
    )


def _discover_managed_environment(
    executable_path: Path,
    profile_directory: str | None,
    *,
    home: Path | None,
) -> ChromeEnvironment:
    user_data_dir = discover_default_profile_dir(home=home)
    user_data_dir.mkdir(parents=True, exist_ok=True)
    selected_profile_directory = profile_directory or DEFAULT_PROFILE_DIRECTORY
    selected_profile_name = None
    profile_path = user_data_dir / selected_profile_directory
    profile_path.mkdir(parents=True, exist_ok=True)

    lock_files = [str(user_data_dir / name) for name in LOCK_FILES if (user_data_dir / name).exists()]
    if lock_files:
        joined = ", ".join(lock_files)
        raise ProfileUnavailableError(
            "Browser CLI managed Chrome profile appears to be in use. "
            f"Close Browser CLI Chrome first. Lock files: {joined}"
        )

    return ChromeEnvironment(
        executable_path=executable_path,
        user_data_dir=user_data_dir,
        profile_directory=selected_profile_directory,
        profile_name=selected_profile_name,
        source="managed",
    )


def discover_chrome_executable(platform: str | None = None) -> Path:
    resolved_platform = platform or sys.platform
    candidates: list[Path]

    if resolved_platform == "darwin":
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
    elif resolved_platform.startswith("linux"):
        candidates = []
        for binary_name in ("google-chrome", "google-chrome-stable"):
            binary_path = shutil.which(binary_name)
            if binary_path:
                candidates.append(Path(binary_path))
        candidates.extend(
            [
                Path("/opt/google/chrome/chrome"),
                Path("/usr/bin/google-chrome"),
                Path("/usr/bin/google-chrome-stable"),
            ]
        )
    else:
        raise BrowserUnavailableError(f"Unsupported platform for Chrome discovery: {resolved_platform}")

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise BrowserUnavailableError("Stable Google Chrome was not found on this machine.")


def discover_user_data_dir(platform: str | None = None, home: Path | None = None) -> Path:
    resolved_platform = platform or sys.platform
    home_dir = home or Path.home()

    if resolved_platform == "darwin":
        return home_dir / "Library" / "Application Support" / "Google" / "Chrome"
    if resolved_platform.startswith("linux"):
        return home_dir / ".config" / "google-chrome"
    raise ProfileUnavailableError(f"Unsupported platform for profile discovery: {resolved_platform}")


def discover_default_profile_dir(home: Path | None = None) -> Path:
    home_dir = home or Path.home()
    return home_dir / DEFAULT_MANAGED_ROOT


def discover_local_state_path(user_data_dir: Path) -> Path:
    return user_data_dir / LOCAL_STATE_FILENAME


def load_profile_info_cache(user_data_dir: Path) -> dict[str, dict]:
    local_state_path = discover_local_state_path(user_data_dir)
    try:
        payload = json.loads(local_state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    info_cache = payload.get("profile", {}).get("info_cache", {})
    if not isinstance(info_cache, dict):
        return {}
    return {
        str(key): value
        for key, value in info_cache.items()
        if isinstance(value, dict)
    }


def resolve_profile_directory(user_data_dir: Path, *, preferred: str | None = None) -> tuple[str, str | None]:
    if preferred:
        return preferred, load_profile_info_cache(user_data_dir).get(preferred, {}).get("name")

    info_cache = load_profile_info_cache(user_data_dir)
    ranked_profiles: list[tuple[float, str, str | None]] = []
    for directory, metadata in info_cache.items():
        profile_path = user_data_dir / directory
        if not profile_path.exists():
            continue
        active_time = metadata.get("active_time")
        try:
            rank = float(active_time) if active_time is not None else 0.0
        except (TypeError, ValueError):
            rank = 0.0
        ranked_profiles.append((rank, directory, metadata.get("name")))
    if ranked_profiles:
        ranked_profiles.sort(key=lambda item: (item[0], item[1]), reverse=True)
        _rank, directory, name = ranked_profiles[0]
        return directory, name if isinstance(name, str) else None

    default_path = user_data_dir / DEFAULT_PROFILE_DIRECTORY
    if default_path.exists():
        return DEFAULT_PROFILE_DIRECTORY, None

    fallback_directories: list[Path] = sorted(
        (
            entry
            for entry in user_data_dir.iterdir()
            if entry.is_dir() and (entry.name.startswith("Profile ") or entry.name == DEFAULT_PROFILE_DIRECTORY)
        ),
        key=lambda entry: entry.stat().st_mtime,
        reverse=True,
    )
    if fallback_directories:
        return fallback_directories[0].name, None

    raise ProfileUnavailableError(
        f"Chrome profile does not exist: expected a recent profile under {user_data_dir}"
    )
