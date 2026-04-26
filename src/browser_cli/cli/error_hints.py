"""Short recovery hints for common CLI failures."""

from __future__ import annotations

from browser_cli import error_codes
from browser_cli.errors import BrowserCliError


def next_hint_for_error(exc: BrowserCliError) -> str | None:
    if exc.error_code == error_codes.BROWSER_UNAVAILABLE:
        return "install stable Google Chrome and re-run browser-cli doctor"
    if exc.error_code == error_codes.PROFILE_UNAVAILABLE:
        return "close Browser CLI-owned Chrome windows or inspect browser-cli status"
    if exc.error_code == error_codes.WORKSPACE_BINDING_LOST:
        return "run browser-cli workspace rebuild --json"
    if exc.error_code == error_codes.EXTENSION_UNAVAILABLE:
        return "connect or reload the Browser CLI extension"
    if exc.error_code == error_codes.EXTENSION_CAPABILITY_INCOMPLETE:
        return "reload the Browser CLI extension and run browser-cli recover --json"
    if exc.error_code == error_codes.EXTENSION_PORT_IN_USE:
        return "set BROWSER_CLI_EXTENSION_PORT to a free port or stop the process using it"
    if exc.error_code == error_codes.CHROME_EXECUTABLE_NOT_FOUND:
        return "install stable Google Chrome and re-run browser-cli doctor --json"
    if exc.error_code == error_codes.HEADLESS_RUNTIME_UNAVAILABLE:
        return (
            "set BROWSER_CLI_HEADLESS=1 in container environments and re-run "
            "browser-cli doctor --json"
        )
    if exc.error_code in {
        error_codes.DAEMON_NOT_AVAILABLE,
        error_codes.AUTOMATION_SERVICE_NOT_AVAILABLE,
    }:
        return "run browser-cli reload"
    message = str(exc).lower()
    if exc.error_code == error_codes.INVALID_INPUT and "task" in message:
        return "run browser-cli task validate <task-dir>"
    if "version" in message and "not found" in message:
        return "run browser-cli automation versions <automation-id>"
    if "automation" in message and "not found" in message:
        return "run browser-cli automation list"
    return None
