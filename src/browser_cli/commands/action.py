"""Generic daemon-backed action command runner."""

from __future__ import annotations

from argparse import Namespace

from browser_cli.daemon.client import send_command
from browser_cli.errors import InvalidInputError
from browser_cli.outputs.json import render_json_payload


def run_action_command(args: Namespace) -> str:
    builder = getattr(args, "action_request_builder", None)
    if builder is None:
        raise InvalidInputError("Internal CLI configuration error: missing action request builder.")
    try:
        request_payload = builder(args)
    except ValueError as exc:
        raise InvalidInputError(str(exc)) from exc
    response = send_command(
        args.action_name,
        request_payload,
        start_if_needed=bool(getattr(args, "action_start_if_needed", True)),
    )
    return render_json_payload(response)
