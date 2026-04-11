"""Shared pytest helpers."""

from __future__ import annotations

import contextlib
import os

import pytest

from browser_cli.constants import APP_HOME_ENV
from browser_cli.daemon.client import _coerce_pid, _pid_exists, _terminate_process_tree
from browser_cli.daemon.transport import read_run_info, remove_run_info, safe_remove_socket


@pytest.fixture(autouse=True)
def _cleanup_browser_cli_runtime(monkeypatch):
    yield
    home = os.environ.get(APP_HOME_ENV, "").strip()
    if not home:
        return
    run_info = read_run_info()
    pid = _coerce_pid((run_info or {}).get("pid"))
    if pid is not None and _pid_exists(pid):
        _terminate_process_tree(pid)
    remove_run_info()
    with contextlib.suppress(FileNotFoundError):
        safe_remove_socket()
