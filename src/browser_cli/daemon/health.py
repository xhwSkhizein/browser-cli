"""Filesystem health as observed by the calling process, independently of runtime health."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from browser_cli.constants import AppPaths


def directory_writable(path: Path) -> bool:
    """Check real write access, including sandbox restrictions that os.access misses."""
    if not path.is_dir() or not os.access(path, os.W_OK | os.X_OK):
        return False
    try:
        with tempfile.TemporaryFile(dir=path):
            return True
    except OSError:
        return False


def inspect_directory(path: Path) -> dict[str, Any]:
    """Probe existing directories without creating missing runtime directories."""
    exists = path.exists()
    writable = directory_writable(path) if exists else False
    ancestor = path.parent
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    can_create = not exists and directory_writable(ancestor)
    state = (
        "writable"
        if writable
        else "ready_to_create"
        if can_create
        else "not_a_directory"
        if exists and not path.is_dir()
        else "unwritable"
        if exists
        else "unavailable"
    )
    return {
        "path": str(path),
        "exists": exists,
        "writable": writable,
        "can_create": can_create,
        "state": state,
        "status": "pass" if writable else "warn" if can_create else "fail",
        "checked_by": "caller",
    }


def directory_health(paths: AppPaths) -> dict[str, dict[str, Any]]:
    return {
        "config_dir": inspect_directory(paths.home),
        "managed_profile": inspect_directory(paths.home / "default-profile"),
        "output_dir": inspect_directory(paths.artifacts_dir),
    }
