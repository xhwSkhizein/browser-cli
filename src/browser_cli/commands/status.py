"""Lifecycle status command."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from browser_cli import __version__
from browser_cli.automation.service.client import (
    read_automation_service_run_info,
    request_automation_service,
)
from browser_cli.constants import get_app_paths
from browser_cli.daemon.client import run_info_is_compatible, send_command
from browser_cli.daemon.transport import DAEMON_RUNTIME_VERSION, probe_socket, read_run_info
from browser_cli.errors import BrowserCliError


@dataclass(slots=True)
class StatusReport:
    overall_status: str
    daemon_state: str
    runtime: dict[str, Any]
    daemon: dict[str, Any]
    backend: dict[str, Any]
    browser: dict[str, Any]
    guidance: list[str]
    presentation: dict[str, Any] = field(default_factory=dict)
    stability: dict[str, Any] = field(default_factory=dict)
    automation_service: dict[str, Any] = field(default_factory=dict)
    live_error: str | None = None


def run_status_command(_args: Namespace) -> str:
    return render_status_report(collect_status_report())


def collect_status_report(*, warmup: bool = False) -> StatusReport:
    app_paths = get_app_paths()
    run_info = read_run_info()
    socket_exists = app_paths.socket_path.exists()
    socket_reachable = probe_socket()
    compatibility: bool | None = None
    if run_info is not None:
        compatibility = run_info_is_compatible(run_info)
    daemon_state = _classify_daemon_state(
        run_info=run_info,
        socket_exists=socket_exists,
        socket_reachable=socket_reachable,
        compatibility=compatibility,
    )

    live_payload: dict[str, Any] | None = None
    live_error: str | None = None
    if socket_reachable and compatibility is not False:
        try:
            response = send_command("runtime-status", {"warmup": warmup}, start_if_needed=False)
            live_payload = dict(response.get("data") or {})
        except BrowserCliError as exc:
            live_error = str(exc)

    runtime_section = {
        "home": str(app_paths.home),
        "socket": str(app_paths.socket_path),
        "run_info": str(app_paths.run_info_path),
        "daemon_log": str(app_paths.daemon_log_path),
        "package_version": __version__,
        "runtime_version": DAEMON_RUNTIME_VERSION,
    }
    daemon_section = {
        "state": daemon_state,
        "socket_exists": socket_exists,
        "socket_reachable": socket_reachable,
        "run_info_exists": run_info is not None,
        "runtime_compatibility": compatibility,
        "pid": _int_or_none((run_info or {}).get("pid")),
        "started_at": _float_or_none((run_info or {}).get("started_at")),
        "recorded_package_version": (run_info or {}).get("package_version"),
        "recorded_runtime_version": (run_info or {}).get("runtime_version"),
    }
    automation_run_info = read_automation_service_run_info()
    automation_service_section = {
        "running": False,
        "pid": _int_or_none((automation_run_info or {}).get("pid")),
        "url": (
            f"http://{automation_run_info['host']}:{automation_run_info['port']}/"
            if automation_run_info
            and automation_run_info.get("host")
            and automation_run_info.get("port")
            else None
        ),
        "automation_count": 0,
        "queued_runs": 0,
        "running_runs": 0,
    }
    if automation_run_info:
        try:
            automation_status = request_automation_service(
                "GET", "/api/service/status", start_if_needed=False
            )
            automation_data = dict(automation_status.get("data") or {})
            metrics = dict(automation_data.get("metrics") or {})
            automation_service_section.update(
                {
                    "running": True,
                    "automation_count": int(metrics.get("automation_count") or 0),
                    "queued_runs": int(metrics.get("queued_runs") or 0),
                    "running_runs": int(metrics.get("running_runs") or 0),
                }
            )
        except BrowserCliError:
            automation_service_section["running"] = False
    backend_section = _build_backend_section(live_payload, live_error=live_error)
    browser_section = _build_browser_section(live_payload)
    presentation = dict((live_payload or {}).get("presentation") or {})
    stability = dict((live_payload or {}).get("stability") or {})
    overall_status = str(presentation.get("overall_state") or "") or _classify_overall_status(
        daemon_state=daemon_state,
        compatibility=compatibility,
        live_payload=live_payload,
        live_error=live_error,
    )
    guidance = list(presentation.get("recovery_guidance") or []) or _build_guidance(
        overall_status=overall_status,
        daemon_state=daemon_state,
        live_payload=live_payload,
        live_error=live_error,
    )
    return StatusReport(
        overall_status=overall_status,
        daemon_state=daemon_state,
        runtime=runtime_section,
        daemon=daemon_section,
        automation_service=automation_service_section,
        backend=backend_section,
        browser=browser_section,
        guidance=guidance,
        presentation=presentation,
        stability=stability,
        live_error=live_error,
    )


def render_status_report(report: StatusReport) -> str:
    summary_reason = report.presentation.get("summary_reason") or "-"
    available_actions = ", ".join(report.presentation.get("available_actions") or []) or "none"
    lines = [f"Status: {report.overall_status}", "", f"Summary: {summary_reason}", ""]
    lines.extend(
        [
            "Runtime",
            f"  home: {report.runtime['home']}",
            f"  socket: {report.runtime['socket']}",
            f"  run-info: {report.runtime['run_info']}",
            f"  daemon log: {report.runtime['daemon_log']}",
            f"  package version: {report.runtime['package_version']}",
            f"  runtime version: {report.runtime['runtime_version']}",
            "",
            "Daemon",
            f"  state: {report.daemon['state']}",
            f"  pid: {_display_value(report.daemon['pid'])}",
            f"  started at: {_format_timestamp(report.daemon['started_at'])}",
            f"  socket exists: {_yes_no(report.daemon['socket_exists'])}",
            f"  socket reachable: {_yes_no(report.daemon['socket_reachable'])}",
            f"  runtime compatibility: {_compatibility_text(report.daemon['runtime_compatibility'])}",
        ]
    )
    if report.daemon["recorded_package_version"] or report.daemon["recorded_runtime_version"]:
        lines.extend(
            [
                f"  recorded package version: {_display_value(report.daemon['recorded_package_version'])}",
                f"  recorded runtime version: {_display_value(report.daemon['recorded_runtime_version'])}",
            ]
        )
    lines.extend(
        [
            "",
            "Automation Service",
            f"  running: {_yes_no(report.automation_service['running'])}",
            f"  pid: {_display_value(report.automation_service['pid'])}",
            f"  url: {_display_value(report.automation_service['url'])}",
            f"  automation count: {_display_value(report.automation_service['automation_count'])}",
            f"  queued runs: {_display_value(report.automation_service['queued_runs'])}",
            f"  running runs: {_display_value(report.automation_service['running_runs'])}",
            "",
            "Backend",
            f"  browser started: {_yes_no(report.backend['browser_started'])}",
            f"  active driver: {_display_value(report.backend['active_driver'])}",
            f"  extension connected: {_yes_no(report.backend['extension_connected'])}",
            f"  extension capability complete: {_yes_no(report.backend['extension_capability_complete'])}",
            f"  extension missing capabilities: {report.backend['extension_missing_capabilities']}",
            f"  pending rebind: {report.backend['pending_rebind']}",
        ]
    )
    if report.live_error:
        lines.append(f"  live daemon error: {report.live_error}")
    lines.extend(
        [
            "",
            "Browser",
            f"  profile source: {_display_value(report.browser['profile_source'])}",
            f"  profile dir: {_display_value(report.browser['profile_dir'])}",
            f"  profile directory: {_display_value(report.browser['profile_directory'])}",
            f"  workspace window: {report.browser['workspace_window']}",
            f"  workspace tab count: {report.browser['tab_count']}",
            f"  active tab: {report.browser['active_tab']}",
            f"  busy tab count: {report.browser['busy_tab_count']}",
            "",
            "Stability",
            f"  active command: {_display_value(report.stability.get('active_command'))}",
            f"  command depth: {_display_value(report.stability.get('command_depth'))}",
            f"  commands started: {_display_value(report.stability.get('commands_started'))}",
            f"  driver switches: {_display_value(report.stability.get('driver_switches'))}",
            f"  workspace rebuilds: {_display_value(report.stability.get('workspace_rebuilds'))}",
            f"  extension disconnects: {_display_value(report.stability.get('extension_disconnects'))}",
            f"  cleanup failures: {_display_value(report.stability.get('cleanup_failures'))}",
            f"  last cleanup error: {_display_value(report.stability.get('last_cleanup_error'))}",
            "",
            "Guidance",
        ]
    )
    for item in report.guidance:
        lines.append(f"- {item}")
    lines.extend(["", f"Available actions: {available_actions}"])
    return "\n".join(lines) + "\n"


def _classify_daemon_state(
    *,
    run_info: dict[str, Any] | None,
    socket_exists: bool,
    socket_reachable: bool,
    compatibility: bool | None,
) -> str:
    if socket_reachable:
        if compatibility is False:
            return "incompatible"
        return "running"
    if run_info is not None or socket_exists:
        return "stale"
    return "stopped"


def _classify_overall_status(
    *,
    daemon_state: str,
    compatibility: bool | None,
    live_payload: dict[str, Any] | None,
    live_error: str | None,
) -> str:
    if daemon_state == "stopped":
        return "stopped"
    if daemon_state in {"stale", "incompatible"} or compatibility is False:
        return "broken"
    if live_error:
        return "broken"
    if not live_payload:
        return "healthy"
    if not bool(live_payload.get("browser_started")):
        return "healthy"
    pending_rebind = live_payload.get("pending_rebind")
    if pending_rebind:
        return "degraded"
    active_driver = str(live_payload.get("active_driver") or "")
    extension = dict(live_payload.get("extension") or {})
    if active_driver != "extension":
        return "degraded"
    if not bool(extension.get("capability_complete")):
        return "degraded"
    return "healthy"


def _build_backend_section(
    live_payload: dict[str, Any] | None, *, live_error: str | None
) -> dict[str, Any]:
    if not live_payload:
        return {
            "browser_started": False,
            "active_driver": "not-started" if not live_error else "unknown",
            "extension_connected": False,
            "extension_capability_complete": False,
            "extension_missing_capabilities": "unknown",
            "pending_rebind": "none",
        }
    extension = dict(live_payload.get("extension") or {})
    pending = live_payload.get("pending_rebind")
    if pending:
        pending_text = (
            f"{pending.get('target') or 'unknown'} ({pending.get('reason') or 'pending'})"
        )
    else:
        pending_text = "none"
    return {
        "browser_started": bool(live_payload.get("browser_started")),
        "active_driver": live_payload.get("active_driver") or "not-started",
        "extension_connected": bool(extension.get("connected")),
        "extension_capability_complete": bool(extension.get("capability_complete")),
        "extension_missing_capabilities": (
            ", ".join(sorted(str(item) for item in (extension.get("missing_capabilities") or [])))
            or "none"
        ),
        "pending_rebind": pending_text,
    }


def _build_browser_section(live_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not live_payload:
        return {
            "profile_source": None,
            "profile_dir": None,
            "profile_directory": None,
            "workspace_window": "unknown",
            "tab_count": 0,
            "active_tab": "none",
            "busy_tab_count": 0,
        }
    workspace_state = dict(live_payload.get("workspace_window_state") or {})
    window_id = workspace_state.get("window_id")
    tabs = dict(live_payload.get("tabs") or {})
    active_tab = _select_active_tab(tabs)
    active_tab_text = "none"
    if active_tab is not None:
        active_tab_text = f"{active_tab.get('page_id')} {active_tab.get('url') or ''}".strip()
    workspace_window = "absent"
    if window_id is not None:
        workspace_window = f"present (window {window_id})"
    return {
        "profile_source": live_payload.get("profile_source"),
        "profile_dir": live_payload.get("profile_dir"),
        "profile_directory": live_payload.get("profile_directory"),
        "workspace_window": workspace_window,
        "tab_count": int(tabs.get("count") or 0),
        "active_tab": active_tab_text,
        "busy_tab_count": int(tabs.get("busy_count") or 0),
    }


def _select_active_tab(tabs: dict[str, Any]) -> dict[str, Any] | None:
    records = list(tabs.get("records") or [])
    active_by_agent = dict(tabs.get("active_by_agent") or {})
    for agent_id in ("public",):
        page_id = active_by_agent.get(agent_id)
        if not page_id:
            continue
        for record in records:
            if record.get("page_id") == page_id:
                return dict(record)
    for record in records:
        if record.get("busy"):
            return dict(record)
    if records:
        return dict(records[0])
    return None


def _build_guidance(
    *,
    overall_status: str,
    daemon_state: str,
    live_payload: dict[str, Any] | None,
    live_error: str | None,
) -> list[str]:
    if overall_status == "stopped":
        return [
            "Daemon is not running. Run `browser-cli reload` or any browser command such as `browser-cli open <url>`.",
            "If the extension should be active, open the Browser CLI extension popup and confirm it is connected after restart.",
        ]
    if daemon_state in {"stale", "incompatible"}:
        return [
            "Runtime artifacts look stale or incompatible. Run `browser-cli reload` to reset Browser CLI state.",
            "If restart still fails, inspect the daemon log path shown above.",
        ]
    if live_error:
        return [
            "The daemon is reachable but runtime diagnostics failed. Run `browser-cli reload` to force a clean restart.",
            "If the problem persists, inspect the daemon log path shown above.",
        ]
    if not live_payload or not bool(live_payload.get("browser_started")):
        return [
            "Daemon is running and idle. The browser backend will start on the next browser command.",
        ]
    active_driver = str(live_payload.get("active_driver") or "")
    pending_rebind = live_payload.get("pending_rebind")
    extension = dict(live_payload.get("extension") or {})
    if pending_rebind:
        return [
            "A driver switch is pending and will apply at the next safe idle point.",
            "Browser CLI remains usable while the rebind is pending.",
        ]
    if active_driver == "playwright":
        return [
            "Browser CLI is currently using the managed profile backend.",
            "If you expect real Chrome mode, check the extension popup or `chrome://extensions`, then run `browser-cli reload` if needed.",
        ]
    if not bool(extension.get("capability_complete")):
        missing = ", ".join(
            sorted(str(item) for item in (extension.get("missing_capabilities") or []))
        )
        return [
            "The extension is connected but its required capability set is incomplete.",
            f"Missing capabilities: {missing or 'unknown'}.",
            "Reload the extension and run `browser-cli reload` if Browser CLI should switch to extension mode.",
        ]
    return [
        "Browser CLI is healthy.",
    ]


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _compatibility_text(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return "yes" if value else "no"


def _display_value(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value)


def _format_timestamp(value: float | None) -> str:
    if value is None:
        return "-"
    return datetime.fromtimestamp(value).isoformat(timespec="seconds")


def _int_or_none(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
