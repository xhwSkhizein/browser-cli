"""CLI entrypoint."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from browser_cli import __version__, exit_codes
from browser_cli.actions import get_action_specs
from browser_cli.commands.action import run_action_command
from browser_cli.commands.read import run_read_command
from browser_cli.commands.reload import run_reload_command
from browser_cli.commands.status import run_status_command
from browser_cli.commands.workflow import run_workflow_command
from browser_cli.errors import BrowserCliError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="browser-cli")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    read_parser = subparsers.add_parser(
        "read",
        help="Read a rendered page as HTML or snapshot text.",
        description="Open a page, wait for render completion, and capture rendered output.",
    )
    read_parser.add_argument("url", help="Target page URL.")
    read_parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Return snapshot tree output instead of rendered HTML.",
    )
    read_parser.add_argument(
        "--scroll-bottom",
        action="store_true",
        help="Scroll to the bottom before capture to trigger lazy-loaded content.",
    )
    read_parser.set_defaults(handler=run_read_command)

    workflow_parser = subparsers.add_parser(
        "workflow",
        help="Validate or run a published workflow wrapper.",
        description="Run workflow.toml packaging around a task.py artifact.",
    )
    workflow_subparsers = workflow_parser.add_subparsers(
        dest="workflow_subcommand", metavar="WORKFLOW_COMMAND"
    )

    workflow_run_parser = workflow_subparsers.add_parser(
        "run",
        help="Run a workflow manifest.",
        description="Load workflow.toml, merge inputs, and execute its task.",
    )
    workflow_run_parser.add_argument("path", help="Path to workflow.toml.")
    workflow_run_parser.add_argument(
        "--set",
        dest="set_values",
        action="append",
        default=[],
        help="Override one input as KEY=VALUE. Repeat as needed.",
    )
    workflow_run_parser.add_argument(
        "--inputs-json",
        help="JSON object with input overrides.",
    )
    workflow_run_parser.set_defaults(handler=run_workflow_command)

    workflow_validate_parser = workflow_subparsers.add_parser(
        "validate",
        help="Validate a workflow manifest.",
        description="Validate workflow.toml and the referenced task metadata.",
    )
    workflow_validate_parser.add_argument("path", help="Path to workflow.toml.")
    workflow_validate_parser.set_defaults(handler=run_workflow_command)

    status_parser = subparsers.add_parser(
        "status",
        help="Show daemon, backend, and workspace runtime status.",
        description="Inspect Browser CLI runtime state and print operational guidance.",
    )
    status_parser.set_defaults(handler=run_status_command)

    reload_parser = subparsers.add_parser(
        "reload",
        help="Reset Browser CLI runtime and restart the daemon/browser backend.",
        description="Clear Browser CLI runtime state, restart the daemon, and print the refreshed status.",
    )
    reload_parser.set_defaults(handler=run_reload_command)

    for spec in get_action_specs():
        parser_name = spec.cli_name or spec.name
        action_parser = subparsers.add_parser(
            parser_name,
            help=spec.help,
            description=spec.description,
        )
        spec.add_arguments(action_parser)
        action_parser.set_defaults(
            handler=run_action_command,
            action_name=spec.name,
            action_request_builder=spec.build_request,
            action_start_if_needed=spec.start_if_needed,
        )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else exit_codes.USAGE_ERROR
        return code

    if not hasattr(args, "handler"):
        parser.print_help()
        return exit_codes.USAGE_ERROR

    try:
        result = args.handler(args)
    except BrowserCliError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return exc.exit_code
    except KeyboardInterrupt:
        sys.stderr.write("Error: interrupted.\n")
        return exit_codes.TEMPORARY_FAILURE
    except Exception as exc:  # pragma: no cover - last-resort guard
        sys.stderr.write(f"Error: unexpected failure: {exc}\n")
        return exit_codes.INTERNAL_ERROR

    if result:
        sys.stdout.write(result)
    return exit_codes.SUCCESS


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
