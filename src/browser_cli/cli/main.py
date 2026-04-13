"""CLI entrypoint."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from browser_cli import __version__, exit_codes
from browser_cli.actions import get_action_specs
from browser_cli.commands.action import run_action_command
from browser_cli.commands.automation import run_automation_command
from browser_cli.commands.install_skills import run_install_skills_command
from browser_cli.commands.read import run_read_command
from browser_cli.commands.reload import run_reload_command
from browser_cli.commands.status import run_status_command
from browser_cli.commands.task import run_task_command
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

    task_parser = subparsers.add_parser(
        "task",
        help="Run or validate a local task directory.",
        description="Run task.py + task.meta.json from a local task directory.",
    )
    task_subparsers = task_parser.add_subparsers(dest="task_subcommand", metavar="TASK_COMMAND")

    task_run_parser = task_subparsers.add_parser(
        "run",
        help="Run a task directory.",
        description="Load task.py from a local task directory and execute its run() entrypoint.",
    )
    task_run_parser.add_argument("path", help="Path to the task directory.")
    task_run_parser.add_argument(
        "--set",
        dest="set_values",
        action="append",
        default=[],
        help="Override one input as KEY=VALUE. Repeat as needed.",
    )
    task_run_parser.add_argument(
        "--inputs-json",
        help="JSON object with input overrides.",
    )
    task_run_parser.set_defaults(handler=run_task_command)

    task_validate_parser = task_subparsers.add_parser(
        "validate",
        help="Validate a task directory.",
        description="Validate task.py and task.meta.json in a local task directory.",
    )
    task_validate_parser.add_argument("path", help="Path to the task directory.")
    task_validate_parser.set_defaults(handler=run_task_command)

    automation_parser = subparsers.add_parser(
        "automation",
        help="Publish and operate versioned automations.",
        description="Publish a task snapshot and manage automation service state.",
    )
    automation_subparsers = automation_parser.add_subparsers(
        dest="automation_subcommand", metavar="AUTOMATION_COMMAND"
    )

    automation_publish_parser = automation_subparsers.add_parser(
        "publish",
        help="Publish one task directory into the automation service.",
        description="Create a published automation from a task directory.",
    )
    automation_publish_parser.add_argument("path", help="Path to the task directory.")
    automation_publish_parser.set_defaults(handler=run_automation_command)

    automation_ui_parser = automation_subparsers.add_parser(
        "ui",
        help="Start the local automation service if needed and print the UI URL.",
        description="Ensure the automation service is running and print the local Web UI URL.",
    )
    automation_ui_parser.set_defaults(handler=run_automation_command)

    automation_status_parser = automation_subparsers.add_parser(
        "status",
        help="Show local automation-service status.",
        description="Inspect automation-service health without forcing a browser action.",
    )
    automation_status_parser.set_defaults(handler=run_automation_command)

    automation_stop_parser = automation_subparsers.add_parser(
        "stop",
        help="Stop the local automation service.",
        description="Request automation-service shutdown and clean stale runtime metadata.",
    )
    automation_stop_parser.set_defaults(handler=run_automation_command)

    automation_import_parser = automation_subparsers.add_parser(
        "import",
        help="Import an automation manifest into the persistent automation service.",
        description="Load automation.toml and publish it into the local automation-service database.",
    )
    automation_import_parser.add_argument("path", help="Path to automation.toml.")
    automation_import_parser.add_argument(
        "--enable",
        action="store_true",
        help="Enable the imported automation immediately.",
    )
    automation_import_parser.set_defaults(handler=run_automation_command)

    automation_export_parser = automation_subparsers.add_parser(
        "export",
        help="Export one persisted automation to automation.toml.",
        description="Write a persisted automation definition back out as automation.toml.",
    )
    automation_export_parser.add_argument("automation_id", help="Persisted automation id.")
    automation_export_parser.add_argument(
        "--output",
        required=True,
        help="Path to write automation.toml.",
    )
    automation_export_parser.set_defaults(handler=run_automation_command)

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
