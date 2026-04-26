"""Agent-facing runtime recovery commands."""

from __future__ import annotations

from argparse import Namespace
from typing import Any

from browser_cli.cli.error_hints import next_hint_for_error
from browser_cli.commands.status import collect_status_report, status_report_to_json_data
from browser_cli.daemon.client import ensure_daemon_running, send_command, wait_for_daemon_stop
from browser_cli.errors import (
    BrowserCliError,
    ExtensionCapabilityIncompleteError,
    ExtensionUnavailableError,
    InvalidInputError,
)
from browser_cli.outputs.json import render_json_error, render_json_payload


def run_workspace_command(args: Namespace) -> str:
    if args.workspace_subcommand != "rebuild":
        raise InvalidInputError(f"Unsupported workspace subcommand: {args.workspace_subcommand}")
    if not getattr(args, "json", False):
        raise InvalidInputError("workspace rebuild currently requires --json")
    try:
        return _run_workspace_rebuild_json()
    except BrowserCliError as exc:
        return render_json_error(exc, next_action=next_hint_for_error(exc))


def run_recover_command(args: Namespace) -> str:
    if not getattr(args, "json", False):
        raise InvalidInputError("recover currently requires --json")
    try:
        return render_json_payload({"ok": True, "data": _recover(), "meta": {"action": "recover"}})
    except BrowserCliError as exc:
        return render_json_error(exc, next_action=next_hint_for_error(exc))


def collect_stable_status_data() -> dict[str, Any]:
    return status_report_to_json_data(collect_status_report(warmup=False))


def _run_workspace_rebuild_json() -> str:
    ensure_daemon_running()
    before = collect_stable_status_data()
    _ensure_extension_available(before)
    send_command("workspace-rebuild-binding", {}, start_if_needed=True)
    after = collect_stable_status_data()
    data = _result_payload(
        before=before,
        after=after,
        action_taken="rebuild-workspace-binding",
    )
    return render_json_payload({"ok": True, "data": data, "meta": {"action": "workspace-rebuild"}})


def _recover() -> dict[str, Any]:
    ensure_daemon_running()
    before = collect_stable_status_data()
    actions: list[str] = []
    current = before
    recommended = str(current["recovery"]["recommended_action"])
    if recommended in {"reload", "reconnect-extension"}:
        send_command("stop", {}, start_if_needed=False)
        wait_for_daemon_stop()
        ensure_daemon_running()
        actions.append("reload")
        current = collect_stable_status_data()
    if current["recovery"]["recommended_action"] == "rebuild-workspace-binding":
        _ensure_extension_available(current)
        send_command("workspace-rebuild-binding", {}, start_if_needed=True)
        actions.append("rebuild-workspace-binding")
        current = collect_stable_status_data()
    action_taken = "+".join(actions) if actions else "none"
    return _result_payload(before=before, after=current, action_taken=action_taken)


def _ensure_extension_available(status: dict[str, Any]) -> None:
    backend = dict(status.get("backend") or {})
    if not bool(backend.get("extension_connected")):
        raise ExtensionUnavailableError("Browser CLI extension is not connected.")
    if not bool(backend.get("extension_capability_complete")):
        raise ExtensionCapabilityIncompleteError(
            "Browser CLI extension is missing required capabilities."
        )


def _result_payload(
    *,
    before: dict[str, Any],
    after: dict[str, Any],
    action_taken: str,
) -> dict[str, Any]:
    return {
        "before_status": before,
        "action_taken": action_taken,
        "after_status": after,
        "recovered": after.get("recovery", {}).get("recommended_action") == "none",
    }
