"""Stable Google Chrome discovery for macOS and Linux."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from browser_cli.errors import BrowserUnavailableError, ProfileUnavailableError

DEFAULT_PROFILE_DIRECTORY = "Default"
LOCK_FILES = ("SingletonLock", "SingletonCookie", "SingletonSocket")
DEFAULT_FALLBACK_ROOT = Path(".browser-cli") / "default-profile"


@dataclass(slots=True, frozen=True)
class ChromeEnvironment:
    executable_path: Path
    user_data_dir: Path
    profile_directory: str = DEFAULT_PROFILE_DIRECTORY
    source: str = "chrome"
    fallback_reason: str | None = None


def discover_chrome_environment(
    profile_directory: str = DEFAULT_PROFILE_DIRECTORY,
    *,
    allow_default_fallback: bool = True,
    fallback_home: Path | None = None,
) -> ChromeEnvironment:
    executable_path = discover_chrome_executable()
    try:
        return _discover_primary_environment(executable_path, profile_directory)
    except ProfileUnavailableError as exc:
        if not allow_default_fallback:
            raise
        return _discover_fallback_environment(
            executable_path,
            profile_directory,
            fallback_home=fallback_home,
            fallback_reason=str(exc),
        )


def _discover_primary_environment(
    executable_path: Path,
    profile_directory: str,
) -> ChromeEnvironment:
    user_data_dir = discover_user_data_dir()
    profile_path = user_data_dir / profile_directory

    if not user_data_dir.exists():
        raise ProfileUnavailableError(
            f"Chrome user data directory does not exist: {user_data_dir}"
        )
    if not profile_path.exists():
        raise ProfileUnavailableError(f"Chrome profile does not exist: {profile_path}")

    lock_files = [str(user_data_dir / name) for name in LOCK_FILES if (user_data_dir / name).exists()]
    if lock_files:
        joined = ", ".join(lock_files)
        raise ProfileUnavailableError(
            f"Chrome profile appears to be in use. Close Google Chrome first. Lock files: {joined}"
        )

    return ChromeEnvironment(
        executable_path=executable_path,
        user_data_dir=user_data_dir,
        profile_directory=profile_directory,
    )


def _discover_fallback_environment(
    executable_path: Path,
    profile_directory: str,
    *,
    fallback_home: Path | None,
    fallback_reason: str,
) -> ChromeEnvironment:
    user_data_dir = discover_default_profile_dir(home=fallback_home)
    profile_path = user_data_dir / profile_directory
    user_data_dir.mkdir(parents=True, exist_ok=True)
    profile_path.mkdir(parents=True, exist_ok=True)

    lock_files = [str(user_data_dir / name) for name in LOCK_FILES if (user_data_dir / name).exists()]
    if lock_files:
        joined = ", ".join(lock_files)
        raise ProfileUnavailableError(
            "Primary Chrome profile is unavailable "
            f"({fallback_reason}) and fallback profile is in use. "
            f"Lock files: {joined}"
        )

    return ChromeEnvironment(
        executable_path=executable_path,
        user_data_dir=user_data_dir,
        profile_directory=profile_directory,
        source="fallback",
        fallback_reason=fallback_reason,
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
    return home_dir / DEFAULT_FALLBACK_ROOT
