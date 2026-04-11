"""Lifecycle reload command."""

from __future__ import annotations

from argparse import Namespace

from browser_cli.daemon.client import (
    cleanup_runtime,
    ensure_daemon_running,
    send_command,
    wait_for_daemon_stop,
)
from browser_cli.errors import BrowserCliError, OperationFailedError

from .status import collect_status_report, render_status_report


def run_reload_command(_args: Namespace) -> str:
    graceful_stop = False
    forced_cleanup = False

    try:
        stop_response = send_command("stop", start_if_needed=False)
        graceful_stop = not bool((stop_response.get("data") or {}).get("already_stopped"))
    except BrowserCliError:
        graceful_stop = False

    if not wait_for_daemon_stop():
        forced_cleanup = True

    if cleanup_runtime():
        forced_cleanup = True

    try:
        ensure_daemon_running()
        after = collect_status_report(warmup=False)
    except BrowserCliError as exc:
        raise OperationFailedError(
            "Reload cleared Browser CLI runtime state, but restart failed. "
            f"Reason: {exc}. Run `browser-cli status` and inspect the daemon log for details."
        ) from exc

    lines = [
        "Reload: complete",
        f"- graceful stop: {'yes' if graceful_stop else 'no'}",
        f"- forced cleanup: {'yes' if forced_cleanup else 'no'}",
        f"- result: {after.overall_status}",
        "",
        render_status_report(after).rstrip(),
    ]
    return "\n".join(lines) + "\n"
