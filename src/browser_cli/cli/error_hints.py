"""Short recovery hints for common CLI failures."""

from __future__ import annotations

from browser_cli import error_codes
from browser_cli.errors import BrowserCliError


def next_hint_for_error(exc: BrowserCliError) -> str | None:
    if exc.error_code == error_codes.BROWSER_UNAVAILABLE:
        return "install stable Google Chrome and re-run browser-cli doctor"
    if exc.error_code == error_codes.PROFILE_UNAVAILABLE:
        return "close Browser CLI-owned Chrome windows or inspect browser-cli status"
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
