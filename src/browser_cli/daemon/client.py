"""Client helpers for daemon-backed commands."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from browser_cli import __version__
from browser_cli.agent_scope import resolve_agent_id
from browser_cli.constants import get_app_paths
from browser_cli.errors import (
    AmbiguousRefError,
    BrowserCliError,
    BrowserUnavailableError,
    BusyTabError,
    DaemonNotAvailableError,
    EmptyContentError,
    InvalidInputError,
    NoActiveTabError,
    NoSnapshotContextError,
    NoVisibleTabsError,
    OperationFailedError,
    ProfileUnavailableError,
    RefNotFoundError,
    StaleSnapshotError,
    TabNotFoundError,
    TemporaryReadError,
)

from .transport import (
    DAEMON_RUNTIME_VERSION,
    ensure_run_dir,
    probe_socket,
    read_run_info,
    remove_run_info,
    safe_remove_socket,
)

STARTUP_TIMEOUT_SECONDS = 15.0
STARTUP_PROBE_INTERVAL_SECONDS = 0.1
TERMINATE_GRACE_SECONDS = 3.0
_STREAM_LIMIT = 32 * 1024 * 1024


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
        reader, writer = await asyncio.open_unix_connection(
            str(app_paths.socket_path), limit=_STREAM_LIMIT
        )
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
    with contextlib.suppress(Exception):
        await writer.wait_closed()
    if not raw:
        raise DaemonNotAvailableError("Browser daemon closed the connection without a response.")
    payload = json.loads(raw.decode("utf-8"))
    if payload.get("ok"):
        return payload
    raise _error_from_payload(payload)


def ensure_daemon_running() -> None:
    run_info = read_run_info()
    if probe_socket() and _run_info_is_compatible(run_info):
        return
    if probe_socket():
        _cleanup_stale_runtime()
        if probe_socket():
            return
    _cleanup_stale_runtime()
    if probe_socket():
        return
    _spawn_daemon()


def wait_for_daemon_stop(*, timeout_seconds: float = TERMINATE_GRACE_SECONDS) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not probe_socket():
            return True
        time.sleep(0.1)
    return not probe_socket()


def cleanup_runtime(*, fast_kill: bool = False) -> bool:
    app_paths = get_app_paths()
    had_runtime_state = bool(read_run_info() is not None or app_paths.socket_path.exists())
    _cleanup_stale_runtime(fast_kill=fast_kill)
    return had_runtime_state


def run_info_is_compatible(run_info: dict[str, Any] | None) -> bool:
    return _run_info_is_compatible(run_info)


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
    process = None
    try:
        process = subprocess.Popen(
            _build_daemon_command(app_paths.home),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
    finally:
        log_handle.close()
    if _wait_for_socket(timeout_seconds=STARTUP_TIMEOUT_SECONDS):
        return
    if process is not None:
        _terminate_process_tree(process.pid)
    run_info = read_run_info()
    details = f"run_info={run_info}" if run_info else f"log={app_paths.daemon_log_path}"
    raise DaemonNotAvailableError(f"Timed out waiting for browser daemon startup ({details}).")


def _build_daemon_command(home: Path) -> list[str]:
    return [sys.executable, "-m", "browser_cli.daemon", "--home", str(home)]


def _wait_for_socket(*, timeout_seconds: float) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if probe_socket():
            return True
        time.sleep(STARTUP_PROBE_INTERVAL_SECONDS)
    return False


def _cleanup_stale_runtime(*, fast_kill: bool = False) -> None:
    run_info = read_run_info()
    socket_reachable = probe_socket()
    if run_info is not None:
        pid = _coerce_pid(run_info.get("pid"))
        if pid is not None and _pid_exists(pid):
            if fast_kill and not socket_reachable:
                _signal_process_tree(pid, signal.SIGKILL)
                _wait_for_pid_exit(pid, timeout_seconds=1.0)
            else:
                _terminate_process_tree(pid)
    remove_run_info()
    with contextlib.suppress(FileNotFoundError):
        safe_remove_socket()


def _run_info_is_compatible(run_info: dict[str, Any] | None) -> bool:
    if not isinstance(run_info, dict):
        return False
    return (
        str(run_info.get("package_version") or "") == __version__
        and str(run_info.get("runtime_version") or "") == DAEMON_RUNTIME_VERSION
    )


def _coerce_pid(value: Any) -> int | None:
    try:
        pid = int(value)
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    else:
        return True


def _terminate_process_tree(pid: int) -> None:
    _signal_process_tree(pid, signal.SIGTERM)
    if _wait_for_pid_exit(pid, timeout_seconds=TERMINATE_GRACE_SECONDS):
        return
    _signal_process_tree(pid, signal.SIGKILL)
    _wait_for_pid_exit(pid, timeout_seconds=1.0)


def _signal_process_tree(pid: int, sig: signal.Signals) -> None:
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        return
    except OSError:
        try:
            os.kill(pid, sig)
        except OSError:
            return


def _wait_for_pid_exit(pid: int, *, timeout_seconds: float) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not _pid_exists(pid):
            return True
        time.sleep(0.1)
    return not _pid_exists(pid)


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
    if error_code == "BROWSER_UNAVAILABLE":
        return BrowserUnavailableError(message)
    if error_code == "PROFILE_UNAVAILABLE":
        return ProfileUnavailableError(message)
    if error_code == "EMPTY_CONTENT":
        return EmptyContentError(message)
    if error_code == "TEMPORARY_FAILURE":
        return TemporaryReadError(message)
    return OperationFailedError(message, error_code=error_code)
