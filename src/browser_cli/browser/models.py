"""Browser-facing dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class BrowserLaunchConfig:
    executable_path: Path | None
    user_data_dir: Path
    profile_directory: str = "Default"
    headless: bool = True
    viewport_width: int = 1440
    viewport_height: int = 1024
    navigation_timeout_ms: int = 30_000
    settle_timeout_ms: int = 1_200

