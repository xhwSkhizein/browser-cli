"""Runtime paths and shared constants."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

APP_HOME_ENV = "BROWSER_CLI_HOME"
DEFAULT_HOME_DIRNAME = ".browser-cli"
DEFAULT_PUBLIC_AGENT_ID = "public"


@dataclass(slots=True, frozen=True)
class AppPaths:
    home: Path
    run_dir: Path
    socket_path: Path
    run_info_path: Path
    daemon_log_path: Path
    artifacts_dir: Path


def get_app_paths() -> AppPaths:
    configured_home = os.environ.get(APP_HOME_ENV)
    home = Path(configured_home).expanduser() if configured_home else Path.home() / DEFAULT_HOME_DIRNAME
    run_dir = home / "run"
    socket_path = run_dir / "browser-cli.sock"
    if len(str(socket_path)) > 90:
        digest = hashlib.sha1(str(home).encode("utf-8")).hexdigest()[:12]
        socket_path = Path(tempfile.gettempdir()) / f"browser-cli-{digest}.sock"
    return AppPaths(
        home=home,
        run_dir=run_dir,
        socket_path=socket_path,
        run_info_path=run_dir / "daemon.json",
        daemon_log_path=run_dir / "daemon.log",
        artifacts_dir=home / "artifacts",
    )
