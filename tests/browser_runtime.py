"""Explicit browser configuration shared by the integration test fixtures."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from scripts.browser_test_support import resolve_browser_test_executable

from browser_cli.constants import APP_HOME_ENV, get_app_paths
from browser_cli.daemon.client import send_command


@lru_cache(maxsize=1)
def get_test_browser_executable() -> Path:
    return resolve_browser_test_executable()


def prepare_daemon_browser() -> None:
    if not os.environ.get(APP_HOME_ENV):
        raise RuntimeError("Browser tests must configure an isolated BROWSER_CLI_HOME first.")
    # Use the existing daemon configuration seam after each cold start/reload.
    send_command(
        "runtime-status",
        {
            "chrome_environment": {
                "executable_path": str(get_test_browser_executable()),
                "user_data_dir": str(get_app_paths().home / "default-profile"),
                "profile_directory": "Default",
                "source": "managed",
            }
        },
    )
