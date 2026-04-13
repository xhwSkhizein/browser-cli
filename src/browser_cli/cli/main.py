"""CLI entrypoint."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from browser_cli import __version__, exit_codes
from browser_cli.actions import get_action_specs
from browser_cli.commands.action import run_action_command
from browser_cli.commands.install_skills import run_install_skills_command
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

    workflow_ui_parser = workflow_subparsers.add_parser(
        "ui",
        help="Start the local workflow service if needed and print the UI URL.",
        description="Ensure the workflow service is running and print the local Web UI URL.",
    )
    workflow_ui_parser.set_defaults(handler=run_workflow_command)

    workflow_service_status_parser = workflow_subparsers.add_parser(
        "service-status",
        help="Show local workflow-service status.",
        description="Inspect workflow-service health without forcing a browser action.",
    )
    workflow_service_status_parser.set_defaults(handler=run_workflow_command)

    workflow_service_stop_parser = workflow_subparsers.add_parser(
        "service-stop",
        help="Stop the local workflow service.",
        description="Request workflow-service shutdown and clean stale runtime metadata.",
    )
    workflow_service_stop_parser.set_defaults(handler=run_workflow_command)

    workflow_import_parser = workflow_subparsers.add_parser(
        "import",
        help="Import a workflow.toml into the persistent workflow service.",
        description="Load workflow.toml and publish it into the local workflow-service database.",
    )
    workflow_import_parser.add_argument("path", help="Path to workflow.toml.")
    workflow_import_parser.add_argument(
        "--enable",
        action="store_true",
        help="Enable the imported workflow immediately.",
    )
    workflow_import_parser.set_defaults(handler=run_workflow_command)

    workflow_export_parser = workflow_subparsers.add_parser(
        "export",
        help="Export one persisted workflow to workflow.toml.",
        description="Write a persisted workflow definition back out as workflow.toml.",
    )
    workflow_export_parser.add_argument("workflow_id", help="Persisted workflow id.")
    workflow_export_parser.add_argument(
        "--output",
        required=True,
        help="Path to write workflow.toml.",
    )
    workflow_export_parser.set_defaults(handler=run_workflow_command)

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

    skills_parser = subparsers.add_parser(
        "install-skills",
        help="Install packaged skills to ~/.agents/skills.",
        description="Copy bundled skills from the package to the user's skills directory.",
    )
    skills_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be installed without making changes.",
    )
    skills_parser.set_defaults(handler=run_install_skills_command)

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
