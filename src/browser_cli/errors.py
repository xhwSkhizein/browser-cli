"""Project-level error types."""

from __future__ import annotations

from dataclasses import dataclass

from . import exit_codes


@dataclass(slots=True)
class BrowserCliError(Exception):
    """Base typed error surfaced to the CLI."""

    message: str
    exit_code: int = exit_codes.INTERNAL_ERROR

    def __str__(self) -> str:
        return self.message


class BrowserUnavailableError(BrowserCliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_codes.BROWSER_UNAVAILABLE)


class ProfileUnavailableError(BrowserCliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_codes.PROFILE_UNAVAILABLE)


class TemporaryReadError(BrowserCliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_codes.TEMPORARY_FAILURE)


class EmptyContentError(BrowserCliError):
    def __init__(self, message: str = "Read completed but produced no content.") -> None:
        super().__init__(message, exit_codes.EMPTY_CONTENT)

