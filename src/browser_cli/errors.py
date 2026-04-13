"""Project-level error types."""

from __future__ import annotations

from dataclasses import dataclass

from . import error_codes, exit_codes


@dataclass(slots=True)
class BrowserCliError(Exception):
    """Base typed error surfaced to the CLI."""

    message: str
    exit_code: int = exit_codes.INTERNAL_ERROR
    error_code: str = error_codes.INTERNAL_ERROR

    def __str__(self) -> str:
        return self.message


class BrowserUnavailableError(BrowserCliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_codes.BROWSER_UNAVAILABLE, error_codes.BROWSER_UNAVAILABLE)


class ProfileUnavailableError(BrowserCliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_codes.PROFILE_UNAVAILABLE, error_codes.PROFILE_UNAVAILABLE)


class TemporaryReadError(BrowserCliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_codes.TEMPORARY_FAILURE, error_codes.TEMPORARY_FAILURE)


class EmptyContentError(BrowserCliError):
    def __init__(self, message: str = "Read completed but produced no content.") -> None:
        super().__init__(message, exit_codes.EMPTY_CONTENT, error_codes.EMPTY_CONTENT)


class InvalidInputError(BrowserCliError):
    def __init__(self, message: str, *, error_code: str = error_codes.INVALID_INPUT) -> None:
        super().__init__(message, exit_codes.USAGE_ERROR, error_code)


class DaemonNotAvailableError(BrowserCliError):
    def __init__(self, message: str = "Browser daemon is not available.") -> None:
        super().__init__(message, exit_codes.TEMPORARY_FAILURE, error_codes.DAEMON_NOT_AVAILABLE)


class NoActiveTabError(BrowserCliError):
    def __init__(self, message: str = "No active tab is available for this agent.") -> None:
        super().__init__(message, exit_codes.TEMPORARY_FAILURE, error_codes.NO_ACTIVE_TAB)


class NoVisibleTabsError(BrowserCliError):
    def __init__(self, message: str = "No visible tabs are available for this agent.") -> None:
        super().__init__(message, exit_codes.TEMPORARY_FAILURE, error_codes.NO_VISIBLE_TABS)


class BusyTabError(BrowserCliError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "The current active tab is already being operated on. Create a new tab or retry after the other command finishes.",
            exit_codes.TEMPORARY_FAILURE,
            error_codes.AGENT_ACTIVE_TAB_BUSY,
        )


class TabNotFoundError(BrowserCliError):
    def __init__(
        self, message: str = "The requested tab is not visible or does not exist."
    ) -> None:
        super().__init__(message, exit_codes.TEMPORARY_FAILURE, error_codes.TAB_NOT_FOUND)


class RefNotFoundError(BrowserCliError):
    def __init__(
        self, message: str = "The requested ref is not known in the latest snapshot."
    ) -> None:
        super().__init__(message, exit_codes.TEMPORARY_FAILURE, error_codes.REF_NOT_FOUND)


class NoSnapshotContextError(BrowserCliError):
    def __init__(
        self,
        message: str = "No snapshot context is available for the active tab. Capture a snapshot first.",
    ) -> None:
        super().__init__(message, exit_codes.TEMPORARY_FAILURE, error_codes.NO_SNAPSHOT_CONTEXT)


class StaleSnapshotError(BrowserCliError):
    def __init__(
        self, message: str = "The requested ref is stale. Capture a new snapshot and retry."
    ) -> None:
        super().__init__(message, exit_codes.TEMPORARY_FAILURE, error_codes.STALE_SNAPSHOT)


class AmbiguousRefError(BrowserCliError):
    def __init__(
        self,
        message: str = "The requested ref resolved to multiple elements. Capture a new snapshot and retry.",
    ) -> None:
        super().__init__(message, exit_codes.TEMPORARY_FAILURE, error_codes.AMBIGUOUS_REF)


class OperationFailedError(BrowserCliError):
    def __init__(self, message: str, *, error_code: str = error_codes.OPERATION_FAILED) -> None:
        super().__init__(message, exit_codes.TEMPORARY_FAILURE, error_code)


class AutomationServiceNotAvailableError(BrowserCliError):
    def __init__(self, message: str = "Automation service is not available.") -> None:
        super().__init__(
            message,
            exit_codes.TEMPORARY_FAILURE,
            error_codes.AUTOMATION_SERVICE_NOT_AVAILABLE,
        )


class AutomationServiceError(BrowserCliError):
    def __init__(self, payload: dict[str, object]) -> None:
        error_code = str(payload.get("error_code") or error_codes.INTERNAL_ERROR)
        exit_code = (
            exit_codes.USAGE_ERROR
            if error_code in {error_codes.INVALID_INPUT, error_codes.AUTOMATION_INVALID}
            else exit_codes.TEMPORARY_FAILURE
        )
        super().__init__(
            str(payload.get("error_message") or "Automation service request failed."),
            exit_code,
            error_code,
        )
        self.payload = payload


class AutomationInvalidError(BrowserCliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_codes.USAGE_ERROR, error_codes.AUTOMATION_INVALID)
