"""Task runtime specific errors."""

from __future__ import annotations

from browser_cli.errors import InvalidInputError


class TaskRuntimeError(InvalidInputError):
    """Raised when a task runtime contract is invalid."""


class TaskMetadataError(InvalidInputError):
    """Raised when task metadata does not satisfy the expected schema."""


class TaskEntrypointError(InvalidInputError):
    """Raised when a task module entrypoint is missing or invalid."""
