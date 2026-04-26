"""Install and runtime diagnostics for Browser CLI environments."""

from __future__ import annotations

import contextlib
import importlib.util
import os
import shutil
import socket
import sys
from argparse import Namespace
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from browser_cli import error_codes
from browser_cli.automation.service.client import (
    _probe_automation_service,
    read_automation_service_run_info,
)
from browser_cli.constants import AppPaths, get_app_paths
from browser_cli.daemon.client import run_info_is_compatible, send_command
from browser_cli.daemon.transport import probe_socket, read_run_info
from browser_cli.outputs.json import render_json_payload

LOCK_FILES = ("SingletonLock", "SingletonCookie", "SingletonSocket")
HEADLESS_ENV = "BROWSER_CLI_HEADLESS"


@dataclass(slots=True, frozen=True)
class DoctorCheck:
    id: str
    status: str
    summary: str
    details: str | None = None
    next: str | None = None
    error_code: str | None = None


def run_doctor_command(args: Namespace) -> str:
    report = collect_doctor_report()
    if getattr(args, "json", False):
        return render_json_payload({"ok": True, "data": report, "meta": {"action": "doctor"}})
    return render_doctor_report(report)


def collect_doctor_report() -> dict[str, Any]:
    app_paths = get_app_paths()
    daemon_payload = _daemon_runtime_payload()
    environment = _environment_payload(app_paths)
    checks = [
        _package_check(),
        _chrome_check(),
        _chrome_candidates_check(),
        _playwright_check(),
        _home_check(app_paths),
        _managed_profile_check(),
        _daemon_check(app_paths),
        _automation_service_check(app_paths),
        _extension_check(daemon_payload),
        _headless_check(environment),
        _container_check(environment),
        _extension_port_check(app_paths),
    ]
    overall_status = "pass"
    if any(item.status == "fail" for item in checks):
        overall_status = "fail"
    elif any(item.status == "warn" for item in checks):
        overall_status = "warn"
    return {
        "overall_status": overall_status,
        "environment": environment,
        "checks": [asdict(item) for item in checks],
    }


def render_doctor_report(report: dict[str, Any]) -> str:
    lines = [f"Doctor: {report['overall_status']}", ""]
    for check in report["checks"]:
        details = f" ({check['details']})" if check.get("details") else ""
        lines.append(f"{check['id']}: {check['status']} - {check['summary']}{details}")
        if check.get("next"):
            lines.append(f"Next: {check['next']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _package_check() -> DoctorCheck:
    entrypoint = importlib.util.find_spec("browser_cli")
    if entrypoint is None:
        return DoctorCheck(
            id="package",
            status="fail",
            summary="Python package import failed.",
            next=(
                "reinstall browser-control-and-automation-cli in this Python environment "
                "and re-run browser-cli doctor"
            ),
        )
    return DoctorCheck(
        id="package",
        status="pass",
        summary="Python package import works.",
    )


def _chrome_check() -> DoctorCheck:
    try:
        executable = _discover_chrome_executable()
    except Exception as exc:
        return DoctorCheck(
            id="chrome",
            status="fail",
            summary="Stable Google Chrome was not found.",
            details=str(exc),
            next="install stable Google Chrome and re-run browser-cli doctor",
            error_code=error_codes.CHROME_EXECUTABLE_NOT_FOUND,
        )
    return DoctorCheck(
        id="chrome",
        status="pass",
        summary="Stable Google Chrome was found.",
        details=str(executable),
    )


def _playwright_check() -> DoctorCheck:
    if importlib.util.find_spec("playwright") is None:
        return DoctorCheck(
            id="playwright",
            status="fail",
            summary="Playwright Python package is not installed.",
            next=(
                "reinstall browser-control-and-automation-cli with uv tool install "
                "--reinstall browser-control-and-automation-cli, or run uv sync --dev "
                "in a repository checkout, then re-run browser-cli doctor"
            ),
        )
    return DoctorCheck(
        id="playwright",
        status="pass",
        summary="Playwright Python package import works.",
    )


def _home_check(app_paths: AppPaths) -> DoctorCheck:
    if not app_paths.home.exists():
        return DoctorCheck(
            id="home",
            status="fail",
            summary="Browser CLI home does not exist yet.",
            details=str(app_paths.home),
            next="create the Browser CLI home directory or run a Browser CLI command that initializes it, then re-run browser-cli doctor",
        )
    if not _is_writable_directory(app_paths.home):
        return DoctorCheck(
            id="home",
            status="fail",
            summary="Browser CLI home is not writable.",
            details=str(app_paths.home),
            next="set BROWSER_CLI_HOME to a writable directory and re-run browser-cli doctor",
        )
    return DoctorCheck(
        id="home",
        status="pass",
        summary="Browser CLI home is ready.",
        details=str(app_paths.home),
    )


def _managed_profile_check() -> DoctorCheck:
    profile_root = get_app_paths().home / "default-profile"
    if not profile_root.exists():
        return DoctorCheck(
            id="managed_profile",
            status="fail",
            summary="Managed profile directory does not exist yet.",
            details=str(profile_root),
            next="run browser-cli read https://example.com once to initialize the managed profile, then re-run browser-cli doctor",
        )
    if not _is_writable_directory(profile_root):
        return DoctorCheck(
            id="managed_profile",
            status="fail",
            summary="Managed profile directory is not writable.",
            details=str(profile_root),
            next="fix permissions for the Browser CLI home directory and re-run browser-cli doctor",
        )

    lock_paths = [
        profile_root / lock_name for lock_name in LOCK_FILES if (profile_root / lock_name).exists()
    ]
    if lock_paths:
        return DoctorCheck(
            id="managed_profile",
            status="warn",
            summary="Managed profile directory exists but appears to be in use.",
            details=", ".join(str(path) for path in lock_paths),
            next="close Browser CLI-owned Chrome windows or inspect browser-cli status",
        )
    return DoctorCheck(
        id="managed_profile",
        status="pass",
        summary="Managed profile directory is writable.",
        details=str(profile_root),
    )


def _daemon_check(app_paths: AppPaths) -> DoctorCheck:
    run_info = read_run_info()
    return _runtime_reachability_check(
        id="daemon",
        metadata_exists=run_info is not None,
        reachable=probe_socket(),
        metadata_path=app_paths.run_info_path,
        reachable_summary="Browser daemon is reachable.",
        unreachable_summary="Daemon runtime metadata exists but the daemon is not reachable.",
        missing_summary="Daemon is not running yet.",
        reachable_details=app_paths.socket_path,
        unreachable_next="run browser-cli reload",
        missing_next="run browser-cli read https://example.com or browser-cli status when you are ready",
    )


def _automation_service_check(app_paths: AppPaths) -> DoctorCheck:
    run_info = read_automation_service_run_info()
    return _runtime_reachability_check(
        id="automation_service",
        metadata_exists=run_info is not None,
        reachable=_probe_automation_service(run_info),
        metadata_path=app_paths.automation_service_run_info_path,
        reachable_summary="Automation service is reachable.",
        unreachable_summary="Automation service metadata exists but service is not reachable.",
        missing_summary="Automation service is not running yet.",
        reachable_details=app_paths.automation_service_run_info_path,
        unreachable_next="run browser-cli automation status or browser-cli automation ui after restarting the service",
        missing_next="run browser-cli automation status or browser-cli automation ui when you need published automation management",
    )


def _extension_check(daemon_payload: dict[str, Any] | None) -> DoctorCheck:
    if daemon_payload is None:
        return DoctorCheck(
            id="extension",
            status="warn",
            summary="Extension reachability is unavailable until the daemon is running.",
            next="run browser-cli status after the daemon starts if you need extension mode",
        )
    extension = dict(daemon_payload.get("extension") or {})
    if bool(extension.get("connected")) and bool(extension.get("capability_complete")):
        return DoctorCheck(
            id="extension",
            status="pass",
            summary="Browser CLI extension is connected and capability-complete.",
        )
    if bool(extension.get("connected")):
        missing = ", ".join(str(item) for item in (extension.get("missing_capabilities") or []))
        details = missing or "required capability set is incomplete"
        return DoctorCheck(
            id="extension",
            status="warn",
            summary="Browser CLI extension is connected but incomplete.",
            details=details,
            next="reload the extension or run browser-cli reload after reconnecting it",
        )
    return DoctorCheck(
        id="extension",
        status="warn",
        summary="Browser CLI extension is not connected.",
        next="start with managed profile mode, or connect the extension if you need real Chrome behavior",
    )


def _discover_chrome_executable() -> Path:
    if not (sys.platform == "darwin" or sys.platform.startswith("linux")):
        raise RuntimeError(f"Unsupported platform for Chrome discovery: {sys.platform}")
    for candidate in _chrome_candidates():
        path = Path(str(candidate["path"]))
        if bool(candidate["exists"]) and path.exists():
            return path
    raise RuntimeError("Stable Google Chrome was not found on this machine.")


def _chrome_candidates() -> list[dict[str, Any]]:
    if sys.platform == "darwin":
        candidates = [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    elif sys.platform.startswith("linux"):
        candidates = []
        for binary_name in (
            "google-chrome",
            "google-chrome-stable",
            "chromium",
            "chromium-browser",
        ):
            binary_path = shutil.which(binary_name)
            if binary_path:
                candidates.append(Path(binary_path))
        candidates.extend(
            [
                Path("/opt/google/chrome/chrome"),
                Path("/usr/bin/google-chrome"),
                Path("/usr/bin/google-chrome-stable"),
                Path("/usr/bin/chromium"),
                Path("/usr/bin/chromium-browser"),
            ]
        )
    else:
        return []
    seen: set[str] = set()
    payload: list[dict[str, Any]] = []
    for candidate in candidates:
        text = str(candidate)
        if text in seen:
            continue
        seen.add(text)
        payload.append({"path": text, "exists": candidate.exists()})
    return payload


def _chrome_candidates_check() -> DoctorCheck:
    candidates = _chrome_candidates()
    details = ", ".join(
        f"{item['path']}={'yes' if item['exists'] else 'no'}" for item in candidates
    )
    return DoctorCheck(
        id="chrome_candidates",
        status="pass" if candidates else "warn",
        summary="Chrome candidate paths were inspected.",
        details=details or "no candidates for this platform",
    )


def _environment_payload(app_paths: AppPaths) -> dict[str, Any]:
    in_container, markers = _is_container()
    return {
        "in_container": in_container,
        "container_markers": markers,
        "headless_env": os.environ.get(HEADLESS_ENV),
        "headless_effective": _default_headless(),
        "extension_host": app_paths.extension_host,
        "extension_port": app_paths.extension_port,
    }


def _is_container() -> tuple[bool, list[str]]:
    markers: list[str] = []
    for marker in ("/.dockerenv", "/run/.containerenv"):
        if Path(marker).exists():
            markers.append(marker)
    cgroup = Path("/proc/1/cgroup")
    if cgroup.exists():
        with contextlib.suppress(OSError):
            content = cgroup.read_text(encoding="utf-8", errors="ignore")
            if any(token in content for token in ("docker", "kubepods", "containerd", "podman")):
                markers.append("/proc/1/cgroup")
    return bool(markers), markers


def _headless_check(environment: dict[str, Any]) -> DoctorCheck:
    if environment["in_container"] and not environment["headless_effective"]:
        return DoctorCheck(
            id="headless",
            status="warn",
            summary="Container environment detected but headless mode is not enabled.",
            details=f"{HEADLESS_ENV}={environment['headless_env']}",
            next="set BROWSER_CLI_HEADLESS=1 and re-run browser-cli doctor --json",
            error_code=error_codes.HEADLESS_RUNTIME_UNAVAILABLE,
        )
    return DoctorCheck(
        id="headless",
        status="pass",
        summary="Headless configuration is explicit or not required.",
        details=f"effective={environment['headless_effective']}",
    )


def _default_headless() -> bool:
    raw = os.environ.get(HEADLESS_ENV, "").strip().lower()
    if not raw:
        return False
    return raw in {"1", "true", "yes", "on"}


def _container_check(environment: dict[str, Any]) -> DoctorCheck:
    if environment["in_container"]:
        return DoctorCheck(
            id="container",
            status="pass",
            summary="Container environment detected.",
            details=", ".join(environment["container_markers"]),
        )
    return DoctorCheck(id="container", status="pass", summary="No container markers detected.")


def _can_bind_extension_port(host: str, port: int) -> tuple[bool, str | None]:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
    except OSError as exc:
        return False, str(exc)
    finally:
        probe.close()
    return True, None


def _extension_port_check(app_paths: AppPaths) -> DoctorCheck:
    ok, reason = _can_bind_extension_port(app_paths.extension_host, app_paths.extension_port)
    endpoint = f"{app_paths.extension_host}:{app_paths.extension_port}"
    if ok:
        return DoctorCheck(
            id="extension_port",
            status="pass",
            summary="Extension listener port can be bound.",
            details=endpoint,
        )
    return DoctorCheck(
        id="extension_port",
        status="warn",
        summary="Extension listener port cannot be bound.",
        details=f"{endpoint}: {reason}",
        next="set BROWSER_CLI_EXTENSION_PORT to a free port or stop the process using it",
        error_code=error_codes.EXTENSION_PORT_IN_USE,
    )


def _daemon_runtime_payload() -> dict[str, Any] | None:
    run_info = read_run_info()
    if not probe_socket() or not run_info_is_compatible(run_info):
        return None
    try:
        response = send_command("runtime-status", {"warmup": False}, start_if_needed=False)
    except Exception:
        return None
    data = response.get("data")
    return dict(data) if isinstance(data, dict) else None


def _is_writable_directory(path: Path) -> bool:
    return path.is_dir() and os.access(path, os.W_OK)


def _runtime_reachability_check(
    *,
    id: str,
    metadata_exists: bool,
    reachable: bool,
    metadata_path: Path,
    reachable_summary: str,
    unreachable_summary: str,
    missing_summary: str,
    reachable_details: Path,
    unreachable_next: str,
    missing_next: str,
) -> DoctorCheck:
    if reachable:
        return DoctorCheck(
            id=id,
            status="pass",
            summary=reachable_summary,
            details=str(reachable_details),
        )
    if metadata_exists:
        return DoctorCheck(
            id=id,
            status="warn",
            summary=unreachable_summary,
            details=str(metadata_path),
            next=unreachable_next,
        )
    return DoctorCheck(
        id=id,
        status="warn",
        summary=missing_summary,
        next=missing_next,
    )
