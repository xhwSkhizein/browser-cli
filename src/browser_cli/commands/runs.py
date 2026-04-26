"""CLI handlers for daemon async command runs."""

from __future__ import annotations

from argparse import Namespace

from browser_cli.daemon.client import send_command
from browser_cli.outputs.json import render_json_payload


def run_run_status_command(args: Namespace) -> str:
    response = send_command("run-status", {"run_id": args.run_id}, start_if_needed=True)
    return render_json_payload(response)


def run_run_logs_command(args: Namespace) -> str:
    response = send_command(
        "run-logs",
        {"run_id": args.run_id, "tail": int(args.tail)},
        start_if_needed=True,
    )
    return render_json_payload(response)


def run_run_cancel_command(args: Namespace) -> str:
    response = send_command("run-cancel", {"run_id": args.run_id}, start_if_needed=True)
    return render_json_payload(response)
