"""Unix-socket transport helpers for the daemon."""

from __future__ import annotations

import json
import os
import socket
import stat
from pathlib import Path
from typing import Any

from browser_cli.constants import get_app_paths


def ensure_run_dir() -> Path:
    run_dir = get_app_paths().run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(run_dir, 0o700)
    except OSError:
        pass
    return run_dir


def write_run_info(info: dict[str, Any]) -> None:
    ensure_run_dir()
    run_info_path = get_app_paths().run_info_path
    tmp_path = run_info_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(info), encoding="utf-8")
    tmp_path.replace(run_info_path)
    try:
        os.chmod(run_info_path, 0o600)
    except OSError:
        pass


def read_run_info() -> dict[str, Any] | None:
    run_info_path = get_app_paths().run_info_path
    try:
        return json.loads(run_info_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def remove_run_info() -> None:
    try:
        get_app_paths().run_info_path.unlink()
    except OSError:
        pass


def safe_remove_socket(path: Path | None = None) -> None:
    socket_path = path or get_app_paths().socket_path
    try:
        st = socket_path.stat()
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(st.st_mode):
        raise RuntimeError(f"Refusing to remove non-socket path: {socket_path}")
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        raise PermissionError(
            f"Socket path {socket_path} is owned by uid={st.st_uid}, current uid={os.getuid()}"
        )
    try:
        socket_path.unlink()
    except FileNotFoundError:
        return


def probe_socket(path: Path | None = None) -> bool:
    socket_path = str(path or get_app_paths().socket_path)
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.settimeout(1.0)
        client.connect(socket_path)
        return True
    except OSError:
        return False
    finally:
        client.close()
