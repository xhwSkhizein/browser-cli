"""Daemon-owned runtime presentation model derived from raw runtime facts."""

from __future__ import annotations

from typing import Any


def build_runtime_presentation(raw_status: dict[str, Any]) -> dict[str, Any]:
    browser_started = bool(raw_status.get("browser_started"))
    active_driver = str(raw_status.get("active_driver") or "not-started")
    pending_rebind = _as_dict_or_none(raw_status.get("pending_rebind"))
    extension = dict(raw_status.get("extension") or {})
    workspace_window_state = dict(raw_status.get("workspace_window_state") or {})
    tabs = dict(raw_status.get("tabs") or {})
    busy_tab_count = int(tabs.get("busy_count") or 0)
    binding_state = str(workspace_window_state.get("binding_state") or "absent")
    extension_connected = bool(extension.get("connected"))
    capability_complete = bool(extension.get("capability_complete"))
    stability = dict(raw_status.get("stability") or {})
    cleanup_failures = int(stability.get("cleanup_failures") or 0)
    last_cleanup_error = str(stability.get("last_cleanup_error") or "").strip() or None

    execution_path = {
        "active_driver": active_driver,
        "pending_rebind": pending_rebind,
        "safe_point_wait": pending_rebind is not None,
        "last_transition": _as_dict_or_none(raw_status.get("last_transition")),
    }
    workspace_state = {
        "window_id": workspace_window_state.get("window_id"),
        "tab_count": int(workspace_window_state.get("tab_count") or 0),
        "managed_tab_count": int(workspace_window_state.get("managed_tab_count") or 0),
        "binding_state": binding_state,
        "busy_tab_count": busy_tab_count,
    }

    overall_state = "healthy"
    summary_reason = "Browser CLI runtime is healthy."
    recovery_guidance = ["Browser CLI can continue normally."]

    if not browser_started:
        summary_reason = "Browser runtime is idle and will start on the next browser command."
        recovery_guidance = ["Run a browser command to initialize runtime state."]
    elif active_driver == "not-started":
        overall_state = "broken"
        summary_reason = "Browser runtime reports started but no active driver is selected."
        recovery_guidance = [
            "Refresh runtime status to confirm the state.",
            "Reload Browser CLI if the runtime remains driverless.",
        ]
    elif pending_rebind is not None:
        overall_state = "recovering"
        summary_reason = _pending_rebind_summary(pending_rebind)
        recovery_guidance = _pending_rebind_guidance(pending_rebind)
    elif active_driver != "extension":
        overall_state = "degraded"
        summary_reason = "Browser CLI is running on Playwright instead of extension mode."
        recovery_guidance = [
            "Agent can continue on the managed profile backend.",
            "Reconnect the extension if real Chrome mode should be restored.",
        ]
    elif not extension_connected or not capability_complete:
        overall_state = "degraded"
        if extension_connected:
            summary_reason = "Extension is connected but its required capabilities are incomplete."
        else:
            summary_reason = "Extension mode is selected but the extension is disconnected."
        recovery_guidance = [
            "Reconnect or reload the extension.",
            "Refresh runtime status after extension health changes.",
        ]
    elif binding_state in {"stale", "absent"}:
        overall_state = "degraded"
        if binding_state == "stale":
            summary_reason = "Workspace binding is stale while extension mode is active."
        else:
            summary_reason = "Browser CLI no longer has a trusted extension workspace binding."
        recovery_guidance = [
            "Rebuild workspace binding to restore Browser CLI-owned tab tracking.",
            "Reconnect the extension if workspace state does not recover.",
        ]
    elif cleanup_failures:
        overall_state = "degraded"
        summary_reason = "Browser CLI recorded recent cleanup failures during runtime transitions."
        recovery_guidance = [
            "Run `browser-cli reload` if cleanup failures continue to appear.",
            "Refresh runtime status after the reload finishes.",
        ]

    return {
        "overall_state": overall_state,
        "summary_reason": summary_reason,
        "execution_path": execution_path,
        "workspace_state": workspace_state,
        "stability": {
            **stability,
            "last_cleanup_error": last_cleanup_error,
        },
        "recovery_guidance": recovery_guidance,
        "available_actions": _available_actions(
            active_driver=active_driver,
            pending_rebind=pending_rebind,
            extension_connected=extension_connected,
            capability_complete=capability_complete,
            binding_state=binding_state,
        ),
    }


def _available_actions(
    *,
    active_driver: str,
    pending_rebind: dict[str, Any] | None,
    extension_connected: bool,
    capability_complete: bool,
    binding_state: str,
) -> list[str]:
    actions = ["refresh-status"]
    if (
        pending_rebind is not None
        or active_driver != "extension"
        or not extension_connected
        or not capability_complete
    ):
        actions.append("reconnect-extension")
    if active_driver == "extension" and binding_state in {"stale", "absent"}:
        if "reconnect-extension" not in actions:
            actions.append("reconnect-extension")
        actions.append("rebuild-workspace-binding")
    return actions


def _pending_rebind_summary(pending_rebind: dict[str, Any]) -> str:
    target = str(pending_rebind.get("target") or "unknown")
    reason = str(pending_rebind.get("reason") or "pending-rebind")
    if reason == "extension-disconnected-waiting-command" and target == "playwright":
        return (
            "Extension disconnected; Browser CLI will switch to Playwright at the next safe point."
        )
    if reason == "extension-connected" and target == "extension":
        return (
            "Extension reconnected; Browser CLI will restore extension mode at the next safe point."
        )
    return f"Browser CLI is waiting to rebind the active driver to {target} at the next safe point."


def _pending_rebind_guidance(pending_rebind: dict[str, Any]) -> list[str]:
    target = str(pending_rebind.get("target") or "unknown")
    if target == "playwright":
        return [
            "Agent can continue while Browser CLI waits for the safe-point fallback.",
            "Reconnect the extension if real Chrome mode should be restored later.",
        ]
    if target == "extension":
        return [
            "Wait for the current command boundary, then refresh runtime status.",
            "Browser CLI will resume extension mode at the next safe point.",
        ]
    return [
        "Wait for the current command boundary, then refresh runtime status.",
    ]


def _as_dict_or_none(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return dict(value)
    return None
