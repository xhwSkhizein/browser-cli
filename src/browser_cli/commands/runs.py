"""CLI handlers for daemon async command runs."""

from __future__ import annotations

from argparse import Namespace

from browser_cli.daemon.client import send_command
from browser_cli.outputs.json import render_json_payload


def run_run_status_command(args: Namespace) -> str:
    response = send_command("run-status", {"run_id": args.run_id}, start_if_needed=True)
    if not getattr(args, "json", False):
        data = dict(response.get("data") or {})
        return (
            f"Run: {data.get('run_id') or args.run_id}\nStatus: {data.get('status') or 'unknown'}\n"
        )
    return render_json_payload(response)


def run_run_logs_command(args: Namespace) -> str:
    response = send_command(
        "run-logs",
        {"run_id": args.run_id, "tail": int(args.tail)},
        start_if_needed=True,
    )
    if not getattr(args, "json", False):
        data = dict(response.get("data") or {})
        lines = [
            f"Run: {data.get('run_id') or args.run_id}",
            f"Status: {data.get('status') or 'unknown'}",
        ]
        for event in data.get("events") or []:
            item = dict(event)
            lines.append(f"- {item.get('event')}: {item.get('message')}")
        return "\n".join(lines) + "\n"
    return render_json_payload(response)


def run_run_cancel_command(args: Namespace) -> str:
    response = send_command("run-cancel", {"run_id": args.run_id}, start_if_needed=True)
    if not getattr(args, "json", False):
        data = dict(response.get("data") or {})
        return (
            f"Run: {data.get('run_id') or args.run_id}\n"
            f"Status: {data.get('status') or 'unknown'}\n"
            f"Cancel requested: {'yes' if data.get('cancel_requested') else 'no'}\n"
        )
    return render_json_payload(response)
