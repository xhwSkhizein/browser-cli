from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

from browser_cli.commands.reload import run_reload_command
from browser_cli.commands.status import StatusReport, collect_status_report, run_status_command
from browser_cli.errors import DaemonNotAvailableError, OperationFailedError


def _fake_paths(tmp_path: Path):
    class _Paths:
        home = tmp_path / ".browser-cli"
        run_dir = home / "run"
        socket_path = run_dir / "browser-cli.sock"
        run_info_path = run_dir / "daemon.json"
        daemon_log_path = run_dir / "daemon.log"
        artifacts_dir = home / "artifacts"
        extension_host = "127.0.0.1"
        extension_port = 19825
        extension_ws_path = "/ext"

    return _Paths()


def test_collect_status_report_when_stopped(tmp_path: Path) -> None:
    with (
        patch("browser_cli.commands.status.get_app_paths", return_value=_fake_paths(tmp_path)),
        patch("browser_cli.commands.status.read_run_info", return_value=None),
        patch("browser_cli.commands.status.probe_socket", return_value=False),
    ):
        report = collect_status_report()

    assert report.overall_status == "stopped"
    assert report.daemon_state == "stopped"
    assert any("browser-cli reload" in line for line in report.guidance)


def test_collect_status_report_when_stale_runtime(tmp_path: Path) -> None:
    run_info = {"pid": 123, "package_version": "0.0.0", "runtime_version": "old"}
    with (
        patch("browser_cli.commands.status.get_app_paths", return_value=_fake_paths(tmp_path)),
        patch("browser_cli.commands.status.read_run_info", return_value=run_info),
        patch("browser_cli.commands.status.probe_socket", return_value=False),
        patch("pathlib.Path.exists", return_value=True),
    ):
        report = collect_status_report()

    assert report.overall_status == "broken"
    assert report.daemon_state == "stale"


def test_collect_status_report_when_managed_backend_is_degraded(tmp_path: Path) -> None:
    run_info = {
        "pid": 123,
        "package_version": "0.1.0",
        "runtime_version": "2026-04-10-dual-driver-extension-v1",
    }
    runtime_status = {
        "browser_started": True,
        "active_driver": "playwright",
        "profile_source": "managed",
        "profile_dir": str(tmp_path / ".browser-cli/default-profile"),
        "profile_directory": "Default",
        "extension": {
            "connected": False,
            "capability_complete": False,
            "missing_capabilities": ["screenshot", "wait-network"],
        },
        "pending_rebind": None,
        "workspace_window_state": {},
        "tabs": {
            "count": 1,
            "busy_count": 0,
            "records": [{"page_id": "page_0001", "url": "https://example.com", "busy": False}],
            "active_by_agent": {"public": "page_0001"},
        },
        "presentation": {
            "overall_state": "degraded",
            "summary_reason": "Browser CLI is running on Playwright instead of extension mode.",
            "execution_path": {
                "active_driver": "playwright",
                "pending_rebind": None,
                "safe_point_wait": False,
                "last_transition": None,
            },
            "workspace_state": {
                "window_id": None,
                "tab_count": 0,
                "managed_tab_count": 0,
                "binding_state": "absent",
                "busy_tab_count": 0,
            },
            "recovery_guidance": [
                "Agent can continue on the managed profile backend.",
                "Reconnect the extension if real Chrome mode should be restored.",
            ],
            "available_actions": ["refresh-status", "reconnect-extension"],
        },
    }
    with (
        patch("browser_cli.commands.status.get_app_paths", return_value=_fake_paths(tmp_path)),
        patch("browser_cli.commands.status.read_run_info", return_value=run_info),
        patch("browser_cli.commands.status.probe_socket", return_value=True),
        patch(
            "browser_cli.commands.status.send_command",
            return_value={"ok": True, "data": runtime_status},
        ),
    ):
        report = collect_status_report()
        text = run_status_command(Namespace())

    assert report.overall_status == "degraded"
    assert report.backend["active_driver"] == "playwright"
    assert report.backend["extension_missing_capabilities"] == "screenshot, wait-network"
    assert "Status:" in text


def test_collect_status_report_uses_daemon_presentation_snapshot(tmp_path: Path) -> None:
    run_info = {
        "pid": 123,
        "package_version": "0.1.0",
        "runtime_version": "2026-04-10-dual-driver-extension-v1",
    }
    runtime_status = {
        "browser_started": True,
        "active_driver": "playwright",
        "profile_source": "managed",
        "profile_dir": str(tmp_path / ".browser-cli/default-profile"),
        "profile_directory": "Default",
        "extension": {
            "connected": False,
            "capability_complete": False,
            "missing_capabilities": [],
        },
        "pending_rebind": {
            "target": "playwright",
            "reason": "extension-disconnected-waiting-command",
        },
        "workspace_window_state": {
            "window_id": None,
            "tab_count": 0,
            "managed_tab_count": 0,
            "binding_state": "absent",
        },
        "tabs": {"count": 0, "busy_count": 0, "records": [], "active_by_agent": {}},
        "presentation": {
            "overall_state": "recovering",
            "summary_reason": "Extension disconnected; Browser CLI will switch to Playwright at the next safe point.",
            "execution_path": {
                "active_driver": "playwright",
                "pending_rebind": {
                    "target": "playwright",
                    "reason": "extension-disconnected-waiting-command",
                },
                "safe_point_wait": True,
                "last_transition": None,
            },
            "workspace_state": {
                "window_id": None,
                "tab_count": 0,
                "managed_tab_count": 0,
                "binding_state": "absent",
                "busy_tab_count": 0,
            },
            "recovery_guidance": [
                "Agent can continue while Browser CLI waits for the safe-point fallback.",
            ],
            "available_actions": ["refresh-status", "reconnect-extension"],
        },
    }
    with (
        patch("browser_cli.commands.status.get_app_paths", return_value=_fake_paths(tmp_path)),
        patch("browser_cli.commands.status.read_run_info", return_value=run_info),
        patch("browser_cli.commands.status.probe_socket", return_value=True),
        patch(
            "browser_cli.commands.status.send_command",
            return_value={"ok": True, "data": runtime_status},
        ),
    ):
        report = collect_status_report()
        text = run_status_command(Namespace())

    assert report.overall_status == "recovering"
    assert report.presentation["summary_reason"].startswith("Extension disconnected")
    assert "Summary:" in text
    assert "Available actions: refresh-status, reconnect-extension" in text


def test_reload_command_reports_forced_cleanup() -> None:
    status_report = StatusReport(
        overall_status="degraded",
        daemon_state="running",
        runtime={},
        daemon={},
        backend={},
        browser={},
        guidance=[],
        presentation={},
    )
    with (
        patch(
            "browser_cli.commands.reload.send_command",
            return_value={"ok": True, "data": {"already_stopped": False}},
        ),
        patch("browser_cli.commands.reload.wait_for_daemon_stop", return_value=False),
        patch("browser_cli.commands.reload.cleanup_runtime", return_value=True),
        patch("browser_cli.commands.reload.ensure_daemon_running"),
        patch("browser_cli.commands.reload.collect_status_report", return_value=status_report),
        patch(
            "browser_cli.commands.reload.render_status_report", return_value="Status: degraded\n"
        ),
    ):
        text = run_reload_command(Namespace())

    assert "Reload: complete" in text
    assert "forced cleanup: yes" in text
    assert "result: degraded" in text


def test_reload_command_checks_status_without_browser_warmup() -> None:
    status_report = StatusReport(
        overall_status="healthy",
        daemon_state="running",
        runtime={},
        daemon={},
        backend={},
        browser={},
        guidance=[],
        presentation={},
    )
    with (
        patch(
            "browser_cli.commands.reload.send_command",
            return_value={"ok": True, "data": {"already_stopped": True}},
        ),
        patch("browser_cli.commands.reload.wait_for_daemon_stop", return_value=True),
        patch("browser_cli.commands.reload.cleanup_runtime", return_value=False),
        patch("browser_cli.commands.reload.ensure_daemon_running"),
        patch(
            "browser_cli.commands.reload.collect_status_report", return_value=status_report
        ) as collect_status,
        patch("browser_cli.commands.reload.render_status_report", return_value="Status: healthy\n"),
    ):
        run_reload_command(Namespace())

    collect_status.assert_called_once_with(warmup=False)


def test_reload_command_wraps_restart_failure() -> None:
    with (
        patch(
            "browser_cli.commands.reload.send_command",
            return_value={"ok": True, "data": {"already_stopped": True}},
        ),
        patch("browser_cli.commands.reload.wait_for_daemon_stop", return_value=True),
        patch("browser_cli.commands.reload.cleanup_runtime", return_value=False),
        patch(
            "browser_cli.commands.reload.ensure_daemon_running",
            side_effect=DaemonNotAvailableError("boom"),
        ),
        pytest.raises(OperationFailedError) as exc_info,
    ):
        run_reload_command(Namespace())

    assert "restart failed" in str(exc_info.value)
