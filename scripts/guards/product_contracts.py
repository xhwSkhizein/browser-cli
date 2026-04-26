"""Guards for frozen CLI and product contracts."""

from __future__ import annotations

import argparse
from pathlib import Path

from browser_cli.actions import get_action_specs
from browser_cli.cli.main import build_parser
from browser_cli.extension.protocol import REQUIRED_EXTENSION_CAPABILITIES
from scripts.guards.common import Finding

REQUIRED_ACTIONS = {"html", "stop"}
DISALLOWED_COMMANDS = {"explore", "session"}
REQUIRED_EXTENSION_TRACE_VIDEO = {
    "trace-start",
    "trace-chunk",
    "trace-stop",
    "video-start",
    "video-stop",
}


def run(_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    parser = build_parser()
    top_level_commands = _subcommand_parsers(parser)

    for command in sorted(DISALLOWED_COMMANDS):
        if command in top_level_commands:
            findings.append(
                Finding(
                    "error",
                    "CONTRACT001",
                    f"Top-level command '{command}' is not allowed. Exploration must remain an agent activity outside the public CLI.",
                )
            )

    if "read" not in top_level_commands:
        findings.append(Finding("error", "CONTRACT002", "Top-level 'read' command is required."))
    if "doctor" not in top_level_commands:
        findings.append(Finding("error", "CONTRACT018", "Top-level 'doctor' command is required."))
    if "paths" not in top_level_commands:
        findings.append(Finding("error", "CONTRACT019", "Top-level 'paths' command is required."))
    if "task" not in top_level_commands:
        findings.append(Finding("error", "CONTRACT003", "Top-level 'task' command is required."))
    if "automation" not in top_level_commands:
        findings.append(
            Finding("error", "CONTRACT016", "Top-level 'automation' command is required.")
        )
    if "status" not in top_level_commands:
        findings.append(Finding("error", "CONTRACT010", "Top-level 'status' command is required."))
    if "reload" not in top_level_commands:
        findings.append(
            Finding("error", "CONTRACT011", "Top-level lifecycle 'reload' command is required.")
        )
    if "page-reload" not in top_level_commands:
        findings.append(
            Finding(
                "error",
                "CONTRACT012",
                "Top-level 'page-reload' command is required to preserve page reload behavior.",
            )
        )

    if "read" in top_level_commands:
        findings.extend(_check_read_contract(top_level_commands["read"]))
    if "task" in top_level_commands:
        findings.extend(_check_task_contract(top_level_commands["task"]))
    if "automation" in top_level_commands:
        findings.extend(_check_automation_contract(top_level_commands["automation"]))
    if "reload" in top_level_commands:
        findings.extend(_check_lifecycle_reload_contract(top_level_commands["reload"]))
    if "page-reload" in top_level_commands:
        findings.extend(_check_page_reload_contract(top_level_commands["page-reload"]))

    findings.extend(_check_action_specs())
    findings.extend(_check_extension_required_capabilities())
    return findings


def _check_read_contract(parser: argparse.ArgumentParser) -> list[Finding]:
    findings: list[Finding] = []
    option_strings = _custom_option_strings(parser)
    expected = {"--async", "--json", "--snapshot", "--scroll-bottom"}
    if option_strings != expected:
        findings.append(
            Finding(
                "error",
                "CONTRACT004",
                f"'read' optional flags changed unexpectedly. Expected {sorted(expected)}, found {sorted(option_strings)}.",
            )
        )
    positional = [
        action.dest
        for action in parser._actions
        if not action.option_strings and action.dest != "help"
    ]
    if positional != ["url"]:
        findings.append(
            Finding(
                "error",
                "CONTRACT005",
                f"'read' should expose exactly one positional argument 'url'. Found {positional}.",
            )
        )
    return findings


def _check_task_contract(parser: argparse.ArgumentParser) -> list[Finding]:
    findings: list[Finding] = []
    subcommands = _subcommand_parsers(parser)
    expected = {"examples", "run", "template", "validate"}
    actual = set(subcommands)
    if actual != expected:
        findings.append(
            Finding(
                "error",
                "CONTRACT006",
                f"'task' subcommands changed unexpectedly. Expected {sorted(expected)}, found {sorted(actual)}.",
            )
        )
    return findings


def _check_automation_contract(parser: argparse.ArgumentParser) -> list[Finding]:
    findings: list[Finding] = []
    subcommands = _subcommand_parsers(parser)
    expected = {
        "export",
        "import",
        "inspect",
        "list",
        "publish",
        "status",
        "stop",
        "ui",
        "versions",
    }
    actual = set(subcommands)
    if actual != expected:
        findings.append(
            Finding(
                "error",
                "CONTRACT017",
                f"'automation' subcommands changed unexpectedly. Expected {sorted(expected)}, found {sorted(actual)}.",
            )
        )
    return findings


def _check_action_specs() -> list[Finding]:
    findings: list[Finding] = []
    action_specs = get_action_specs()
    action_names = {spec.name for spec in action_specs}
    missing = REQUIRED_ACTIONS - action_names
    if missing:
        findings.append(
            Finding(
                "error",
                "CONTRACT007",
                f"Required daemon-backed actions are missing: {', '.join(sorted(missing))}.",
            )
        )
    for forbidden in DISALLOWED_COMMANDS:
        if forbidden in action_names:
            findings.append(
                Finding(
                    "error",
                    "CONTRACT008",
                    f"Action '{forbidden}' is not allowed in the public action catalog.",
                )
            )
    for spec in action_specs:
        parser = argparse.ArgumentParser(prog=spec.name, add_help=False)
        spec.add_arguments(parser)
        for action in parser._actions:
            if "--page" in action.option_strings or "--page-id" in action.option_strings:
                findings.append(
                    Finding(
                        "error",
                        "CONTRACT009",
                        f"Action '{spec.name}' exposes a page targeting flag. Public --page style targeting is forbidden.",
                    )
                )
    return findings


def _check_lifecycle_reload_contract(parser: argparse.ArgumentParser) -> list[Finding]:
    findings: list[Finding] = []
    if "action_name" in parser._defaults:
        findings.append(
            Finding(
                "error",
                "CONTRACT013",
                "Top-level 'reload' must remain a lifecycle command, not a daemon action-catalog command.",
            )
        )
    return findings


def _check_page_reload_contract(parser: argparse.ArgumentParser) -> list[Finding]:
    findings: list[Finding] = []
    action_name = parser._defaults.get("action_name")
    if action_name != "reload":
        findings.append(
            Finding(
                "error",
                "CONTRACT014",
                "Top-level 'page-reload' must dispatch the page action named 'reload'.",
            )
        )
    return findings


def _check_extension_required_capabilities() -> list[Finding]:
    findings: list[Finding] = []
    missing = REQUIRED_EXTENSION_TRACE_VIDEO - set(REQUIRED_EXTENSION_CAPABILITIES)
    if missing:
        findings.append(
            Finding(
                "error",
                "CONTRACT015",
                "Extension required capabilities must include trace/video parity actions: "
                + ", ".join(sorted(missing)),
            )
        )
    return findings


def _subcommand_parsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _custom_option_strings(parser: argparse.ArgumentParser) -> set[str]:
    option_strings: set[str] = set()
    for action in parser._actions:
        for option in action.option_strings:
            if option in {"-h", "--help"}:
                continue
            option_strings.add(option)
    return option_strings
