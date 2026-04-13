"""Install and runtime diagnostics for pip users."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from argparse import Namespace
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from browser_cli.automation.service.client import read_automation_service_run_info
from browser_cli.constants import AppPaths, get_app_paths
from browser_cli.daemon.transport import probe_socket, read_run_info
from browser_cli.outputs.json import render_json_payload

LOCK_FILES = ("SingletonLock", "SingletonCookie", "SingletonSocket")


@dataclass(slots=True, frozen=True)
class DoctorCheck:
    id: str
    status: str
    summary: str
    details: str | None = None
    next: str | None = None


def run_doctor_command(args: Namespace) -> str:
    report = collect_doctor_report()
    if getattr(args, "json", False):
        return render_json_payload({"ok": True, "data": report, "meta": {"action": "doctor"}})
    return render_doctor_report(report)


def collect_doctor_report() -> dict[str, Any]:
    app_paths = get_app_paths()
    checks = [
        _package_check(),
        _chrome_check(),
        _playwright_check(),
        _home_check(app_paths),
        _managed_profile_check(),
        _daemon_check(app_paths),
        _automation_service_check(app_paths),
    ]
    overall_status = "pass"
    if any(item.status == "fail" for item in checks):
        overall_status = "fail"
    elif any(item.status == "warn" for item in checks):
        overall_status = "warn"
    return {
        "overall_status": overall_status,
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
            next="reinstall browser-cli in this Python environment and re-run browser-cli doctor",
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
            next="install the Playwright Python package, then re-run browser-cli doctor",
        )
    return DoctorCheck(
        id="playwright",
        status="pass",
        summary="Playwright Python package import works.",
    )


def _home_check(app_paths: AppPaths) -> DoctorCheck:
    try:
        app_paths.home.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return DoctorCheck(
            id="home",
            status="fail",
            summary="Browser CLI home is not writable.",
            details=str(exc),
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
    try:
        profile_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return DoctorCheck(
            id="managed_profile",
            status="fail",
            summary="Managed profile directory is not writable.",
            details=str(exc),
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
    if probe_socket():
        return DoctorCheck(
            id="daemon",
            status="pass",
            summary="Browser daemon is reachable.",
            details=str(app_paths.socket_path),
        )
    run_info = read_run_info()
    if run_info:
        return DoctorCheck(
            id="daemon",
            status="warn",
            summary="Daemon runtime metadata exists but the daemon is not reachable.",
            details=str(app_paths.run_info_path),
            next="run browser-cli reload",
        )
    return DoctorCheck(
        id="daemon",
        status="warn",
        summary="Daemon is not running yet.",
        next="run browser-cli read https://example.com or browser-cli status when you are ready",
    )


def _automation_service_check(app_paths: AppPaths) -> DoctorCheck:
    run_info = read_automation_service_run_info()
    if run_info:
        return DoctorCheck(
            id="automation_service",
            status="pass",
            summary="Automation service metadata exists.",
            details=str(app_paths.automation_service_run_info_path),
        )
    return DoctorCheck(
        id="automation_service",
        status="warn",
        summary="Automation service is not running yet.",
        next="run browser-cli automation status or browser-cli automation ui when you need published automation management",
    )


def _discover_chrome_executable() -> Path:
    if sys.platform == "darwin":
        candidates = [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    elif sys.platform.startswith("linux"):
        candidates = []
        for binary_name in ("google-chrome", "google-chrome-stable"):
            binary_path = shutil.which(binary_name)
            if binary_path:
                candidates.append(Path(binary_path))
        candidates.extend(
            [
                Path("/opt/google/chrome/chrome"),
                Path("/usr/bin/google-chrome"),
                Path("/usr/bin/google-chrome-stable"),
            ]
        )
    else:
        raise RuntimeError(f"Unsupported platform for Chrome discovery: {sys.platform}")

    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError("Stable Google Chrome was not found on this machine.")
