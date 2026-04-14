"""Automation hook execution helpers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


def run_hook_commands(
    commands: tuple[str, ...],
    *,
    cwd: Path,
    extra_env: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    env = os.environ.copy()
    if extra_env:
        env.update({key: str(value) for key, value in extra_env.items() if value is not None})
    for command in commands:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        results.append(
            {
                "command": command,
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Hook failed: {command}")
    return results
