"""Browser-facing dataclasses."""

from __future__ import annotations

import locale as py_locale
import os
from dataclasses import dataclass, field
from pathlib import Path

HEADLESS_ENV = "BROWSER_CLI_HEADLESS"
LOCALE_ENV = "BROWSER_CLI_LOCALE"


def default_headless() -> bool:
    raw = os.environ.get(HEADLESS_ENV, "").strip().lower()
    if not raw:
        return False
    return raw in {"1", "true", "yes", "on"}


def default_locale() -> str:
    raw = os.environ.get(LOCALE_ENV, "").strip()
    if not raw:
        raw = (
            os.environ.get("LC_ALL", "").strip()
            or os.environ.get("LANG", "").strip()
        )
    if not raw:
        system_locale, _encoding = py_locale.getlocale()
        raw = system_locale or ""
    raw = raw.split(".", 1)[0].strip()
    if not raw or raw.upper() in {"C", "POSIX"}:
        return "en-US"
    return raw.replace("_", "-")


@dataclass(slots=True)
class BrowserLaunchConfig:
    executable_path: Path | None
    user_data_dir: Path
    profile_directory: str = "Default"
    headless: bool = field(default_factory=default_headless)
    locale: str = field(default_factory=default_locale)
    viewport_width: int = 1440
    viewport_height: int = 1024
    navigation_timeout_ms: int = 30_000
    settle_timeout_ms: int = 1_200
