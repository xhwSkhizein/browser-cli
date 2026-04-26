from __future__ import annotations

import json
from argparse import Namespace
from unittest.mock import patch

from browser_cli.commands.recovery import (
    _next_action_for_error,
    run_recover_command,
    run_workspace_command,
)
from browser_cli.errors import ExtensionPortInUseError, WorkspaceBindingLostError


def _status_data(binding: str, recommended: str = "none") -> dict[str, object]:
    return {
        "status": "degraded" if recommended != "none" else "healthy",
        "daemon": {"state": "running", "pid": 100, "socket_reachable": True},
        "backend": {
            "active_driver": "extension",
            "extension_connected": recommended != "reconnect-extension",
            "extension_capability_complete": True,
            "extension_listener": {
                "host": "127.0.0.1",
                "port": 19825,
                "ws_url": "ws://127.0.0.1:19825/ext",
            },
        },
        "browser": {"started": True, "workspace_binding": binding},
        "recovery": {
            "recommended_action": recommended,
            "available_actions": ["refresh-status", "rebuild-workspace-binding"],
        },
    }


def test_workspace_rebuild_json_reports_before_after() -> None:
    statuses = [_status_data("stale", "rebuild-workspace-binding"), _status_data("tracked")]
    with (
        patch("browser_cli.commands.recovery.ensure_daemon_running") as ensure_daemon,
        patch("browser_cli.commands.recovery.collect_stable_status_data", side_effect=statuses),
        patch(
            "browser_cli.commands.recovery.send_command",
            return_value={"ok": True, "data": {"tab_state_reset": True}},
        ) as send_command,
    ):
        payload = json.loads(
            run_workspace_command(Namespace(workspace_subcommand="rebuild", json=True))
        )

    ensure_daemon.assert_called_once_with()
    send_command.assert_called_once_with("workspace-rebuild-binding", {}, start_if_needed=True)
    assert payload["data"]["action_taken"] == "rebuild-workspace-binding"
    assert payload["data"]["before_status"]["browser"]["workspace_binding"] == "stale"
    assert payload["data"]["after_status"]["browser"]["workspace_binding"] == "tracked"
    assert payload["data"]["recovered"] is True


def test_recover_json_can_reload_then_rebuild() -> None:
    statuses = [
        _status_data("absent", "reload"),
        _status_data("stale", "rebuild-workspace-binding"),
        _status_data("tracked"),
    ]
    calls: list[str] = []

    def _send(action: str, args=None, start_if_needed: bool = True):
        _ = args
        _ = start_if_needed
        calls.append(action)
        return {"ok": True, "data": {}}

    with (
        patch("browser_cli.commands.recovery.ensure_daemon_running"),
        patch("browser_cli.commands.recovery.wait_for_daemon_stop", return_value=True),
        patch("browser_cli.commands.recovery.collect_stable_status_data", side_effect=statuses),
        patch("browser_cli.commands.recovery.send_command", side_effect=_send),
    ):
        payload = json.loads(run_recover_command(Namespace(json=True)))

    assert calls == ["stop", "workspace-rebuild-binding"]
    assert payload["data"]["action_taken"] == "reload+rebuild-workspace-binding"
    assert payload["data"]["recovered"] is True


def test_workspace_rebuild_json_failure_returns_structured_error() -> None:
    with (
        patch("browser_cli.commands.recovery.ensure_daemon_running"),
        patch(
            "browser_cli.commands.recovery.collect_stable_status_data",
            return_value=_status_data("absent", "reconnect-extension"),
        ),
    ):
        payload = json.loads(
            run_workspace_command(Namespace(workspace_subcommand="rebuild", json=True))
        )

    assert payload == {
        "ok": False,
        "error_code": "EXTENSION_UNAVAILABLE",
        "message": "Browser CLI extension is not connected.",
        "next_action": "connect or reload the Browser CLI extension",
    }


def test_recovery_next_action_covers_binding_and_port_errors() -> None:
    assert (
        _next_action_for_error(WorkspaceBindingLostError("lost"))
        == "run browser-cli workspace rebuild --json"
    )
    assert (
        _next_action_for_error(ExtensionPortInUseError("busy"))
        == "set BROWSER_CLI_EXTENSION_PORT to a free port or stop the process using it"
    )
