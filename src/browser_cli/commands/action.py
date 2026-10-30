"""Generic daemon-backed action command runner."""

from __future__ import annotations

from argparse import Namespace

from browser_cli import exit_codes
from browser_cli.daemon.client import send_command
from browser_cli.errors import BrowserCliError, InvalidInputError
from browser_cli.outputs.files import write_json_artifact
from browser_cli.outputs.json import CommandResult, render_json_payload


def run_action_command(args: Namespace) -> CommandResult:
    """Run an action, optionally export its full data, and retain failure exit codes."""
    builder = getattr(args, "action_request_builder", None)
    if builder is None:
        raise InvalidInputError("Internal CLI configuration error: missing action request builder.")
    try:
        request_payload = builder(args)
    except ValueError as exc:
        error = InvalidInputError(str(exc))
        error.payload = {"execution_state": "not_started"}
        raise error from exc
    response = send_command(
        args.action_name,
        request_payload,
        start_if_needed=bool(getattr(args, "action_start_if_needed", True)),
    )
    failed_batch = args.action_name == "batch" and response["data"].get("success") is not True
    output = getattr(args, "output", None)
    if output:
        source = "data.result" if args.action_name in {"eval", "eval-on"} else "data"
        value = response["data"]["result"] if source == "data.result" else response["data"]
        try:
            artifact = write_json_artifact(output, value)
        except BrowserCliError as exc:
            # A local save failure must not imply that the browser action was rejected.
            exc.payload.update({"meta": response.get("meta", {}), "execution_state": "completed"})
            raise
        data = {"artifact": {**artifact, "source": source}}
        if args.action_name == "batch":
            data.update(
                {
                    key: response["data"][key]
                    for key in (
                        "success",
                        "completed",
                        "completed_count",
                        "total_count",
                        "failed_indices",
                    )
                }
            )
        response = {**response, "data": data}
    return CommandResult(
        render_json_payload(response),
        exit_codes.TEMPORARY_FAILURE if failed_batch else exit_codes.SUCCESS,
    )
