"""Client helpers for daemon-backed commands."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from browser_cli.agent_scope import resolve_agent_id
from browser_cli.constants import get_app_paths
from browser_cli.errors import (
    AmbiguousRefError,
    BrowserCliError,
    BusyTabError,
    DaemonNotAvailableError,
    InvalidInputError,
    NoSnapshotContextError,
    NoActiveTabError,
    NoVisibleTabsError,
    OperationFailedError,
    RefNotFoundError,
    StaleSnapshotError,
    TabNotFoundError,
)

from .transport import ensure_run_dir, probe_socket, read_run_info


def send_command(
    action: str,
    args: dict[str, Any] | None = None,
    *,
    start_if_needed: bool = True,
) -> dict[str, Any]:
    if action == "stop" and not probe_socket():
        return {
            "ok": True,
            "data": {"stopped": False, "already_stopped": True},
            "meta": {"action": "stop", "agent_id": resolve_agent_id()},
        }
    if start_if_needed:
        ensure_daemon_running()
    elif not probe_socket():
        raise DaemonNotAvailableError()
    return asyncio.run(_send_command_async(action, args or {}))


async def _send_command_async(action: str, args: dict[str, Any]) -> dict[str, Any]:
    app_paths = get_app_paths()
    try:
        reader, writer = await asyncio.open_unix_connection(str(app_paths.socket_path))
    except OSError as exc:
        raise DaemonNotAvailableError(str(exc)) from exc
    request_payload = {
        "action": action,
        "args": args,
        "agent_id": resolve_agent_id(),
        "request_id": uuid.uuid4().hex,
    }
    writer.write((json.dumps(request_payload) + "\n").encode("utf-8"))
    await writer.drain()
    raw = await reader.readline()
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:
        pass
    if not raw:
        raise DaemonNotAvailableError("Browser daemon closed the connection without a response.")
    payload = json.loads(raw.decode("utf-8"))
    if payload.get("ok"):
        return payload
    raise _error_from_payload(payload)


def ensure_daemon_running() -> None:
    if probe_socket():
        return
    _spawn_daemon()


def _spawn_daemon() -> None:
    ensure_run_dir()
    app_paths = get_app_paths()
    existing_pythonpath = os.environ.get("PYTHONPATH", "")
    source_root = Path(__file__).resolve().parents[2]
    pythonpath_parts = [str(source_root)]
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    log_handle = app_paths.daemon_log_path.open("ab")
    subprocess.Popen(
        [sys.executable, "-m", "browser_cli.daemon"],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )
    deadline = time.time() + 15.0
    while time.time() < deadline:
        if probe_socket():
            return
        time.sleep(0.1)
    run_info = read_run_info()
    details = f"run_info={run_info}" if run_info else f"log={app_paths.daemon_log_path}"
    raise DaemonNotAvailableError(f"Timed out waiting for browser daemon startup ({details}).")


def _error_from_payload(payload: dict[str, Any]) -> BrowserCliError:
    error_code = str(payload.get("error_code") or "OPERATION_FAILED")
    message = str(payload.get("error_message") or "Daemon command failed.")
    if error_code == "INVALID_INPUT":
        return InvalidInputError(message)
    if error_code == "NO_ACTIVE_TAB":
        return NoActiveTabError(message)
    if error_code == "NO_VISIBLE_TABS":
        return NoVisibleTabsError(message)
    if error_code == "AGENT_ACTIVE_TAB_BUSY":
        return BusyTabError(message)
    if error_code == "TAB_NOT_FOUND":
        return TabNotFoundError(message)
    if error_code == "REF_NOT_FOUND":
        return RefNotFoundError(message)
    if error_code == "NO_SNAPSHOT_CONTEXT":
        return NoSnapshotContextError(message)
    if error_code == "AMBIGUOUS_REF":
        return AmbiguousRefError(message)
    if error_code == "STALE_SNAPSHOT":
        return StaleSnapshotError(message)
    if error_code == "DAEMON_NOT_AVAILABLE":
        return DaemonNotAvailableError(message)
    return OperationFailedError(message, error_code=error_code)
