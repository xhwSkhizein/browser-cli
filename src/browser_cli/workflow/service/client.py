"""Client helpers for the workflow service."""

from __future__ import annotations

import contextlib
import http.client
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from browser_cli import __version__
from browser_cli.constants import get_app_paths
from browser_cli.errors import WorkflowServiceNotAvailableError

WORKFLOW_STARTUP_TIMEOUT_SECONDS = 15.0
WORKFLOW_STARTUP_PROBE_INTERVAL_SECONDS = 0.1


def request_workflow_service(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    start_if_needed: bool = True,
) -> dict[str, Any]:
    if start_if_needed:
        ensure_workflow_service_running()
    run_info = read_workflow_service_run_info()
    if not run_info:
        raise WorkflowServiceNotAvailableError()
    host = str(run_info["host"])
    port = int(run_info["port"])
    connection = http.client.HTTPConnection(host, port, timeout=5.0)
    try:
        raw = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if raw is not None else {}
        connection.request(method, path, body=raw, headers=headers)
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    except OSError as exc:
        raise WorkflowServiceNotAvailableError(str(exc)) from exc
    finally:
        connection.close()
    if payload.get("ok"):
        return payload
    raise WorkflowServiceNotAvailableError(
        str(payload.get("error_message") or "Workflow service request failed.")
    )


def ensure_workflow_service_running() -> None:
    run_info = read_workflow_service_run_info()
    if _run_info_is_compatible(run_info) and _probe_workflow_service(run_info):
        return
    _cleanup_stale_workflow_service()
    _spawn_workflow_service()


def stop_workflow_service() -> dict[str, Any]:
    run_info = read_workflow_service_run_info()
    if not run_info or not _probe_workflow_service(run_info):
        _cleanup_stale_workflow_service()
        return {"stopped": False, "already_stopped": True}
    payload = request_workflow_service("POST", "/api/service/stop", start_if_needed=False)
    _wait_for_workflow_service_stop()
    _cleanup_stale_workflow_service()
    return dict(payload.get("data") or {})


def workflow_service_ui_url() -> str:
    ensure_workflow_service_running()
    run_info = read_workflow_service_run_info()
    if not run_info:
        raise WorkflowServiceNotAvailableError()
    return f"http://{run_info['host']}:{run_info['port']}/"


def read_workflow_service_run_info() -> dict[str, Any] | None:
    path = get_app_paths().workflow_service_run_info_path
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def _write_workflow_service_run_info(info: dict[str, Any]) -> None:
    path = get_app_paths().workflow_service_run_info_path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(info), encoding="utf-8")
    tmp.replace(path)


def remove_workflow_service_run_info() -> None:
    with contextlib.suppress(OSError):
        get_app_paths().workflow_service_run_info_path.unlink()


def _spawn_workflow_service() -> None:
    app_paths = get_app_paths()
    app_paths.run_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    existing_pythonpath = os.environ.get("PYTHONPATH", "")
    source_root = Path(__file__).resolve().parents[3]
    pythonpath_parts = [str(source_root)]
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    log_handle = app_paths.workflow_service_log_path.open("ab")
    process = None
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "browser_cli.workflow.service", "--home", str(app_paths.home)],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
    finally:
        log_handle.close()
    deadline = time.time() + WORKFLOW_STARTUP_TIMEOUT_SECONDS
    while time.time() < deadline:
        run_info = read_workflow_service_run_info()
        if _run_info_is_compatible(run_info) and _probe_workflow_service(run_info):
            return
        time.sleep(WORKFLOW_STARTUP_PROBE_INTERVAL_SECONDS)
    if process is not None:
        _terminate_process_tree(process.pid)
    raise WorkflowServiceNotAvailableError(
        f"Timed out waiting for workflow service startup (log={app_paths.workflow_service_log_path})."
    )


def _probe_workflow_service(run_info: dict[str, Any] | None) -> bool:
    if not isinstance(run_info, dict):
        return False
    host = str(run_info.get("host") or "")
    port = int(run_info.get("port") or 0)
    if not host or port <= 0:
        return False
    connection: http.client.HTTPConnection | None = None
    try:
        connection = http.client.HTTPConnection(host, port, timeout=1.0)
        connection.request("GET", "/api/service/status")
        response = connection.getresponse()
        response.read()
        return response.status == 200
    except OSError:
        return False
    finally:
        if connection is not None:
            with contextlib.suppress(Exception):
                connection.close()


def _wait_for_workflow_service_stop(timeout_seconds: float = 3.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        run_info = read_workflow_service_run_info()
        if not run_info or not _probe_workflow_service(run_info):
            return True
        time.sleep(0.1)
    return False


def _cleanup_stale_workflow_service() -> None:
    run_info = read_workflow_service_run_info()
    if isinstance(run_info, dict):
        pid = _coerce_pid(run_info.get("pid"))
        if pid is not None and _pid_exists(pid) and not _probe_workflow_service(run_info):
            _terminate_process_tree(pid)
    remove_workflow_service_run_info()


def _run_info_is_compatible(run_info: dict[str, Any] | None) -> bool:
    if not isinstance(run_info, dict):
        return False
    return (
        str(run_info.get("package_version") or "") == __version__
        and str(run_info.get("runtime_version") or "") == "2026-04-12-workflow-service-v1"
    )


def _terminate_process_tree(pid: int) -> None:
    _signal_process_tree(pid, signal.SIGTERM)
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if not _pid_exists(pid):
            return
        time.sleep(0.1)
    _signal_process_tree(pid, signal.SIGKILL)


def _signal_process_tree(pid: int, sig: signal.Signals) -> None:
    try:
        os.killpg(pid, sig)
    except OSError:
        with contextlib.suppress(OSError):
            os.kill(pid, sig)


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


__all__ = [
    "ensure_workflow_service_running",
    "read_workflow_service_run_info",
    "remove_workflow_service_run_info",
    "request_workflow_service",
    "stop_workflow_service",
    "workflow_service_ui_url",
    "_write_workflow_service_run_info",
]
