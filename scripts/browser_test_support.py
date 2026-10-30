"""Select a browser for test processes without changing product discovery."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from browser_cli.profiles.discovery import discover_chrome_executable


# Use the selected installation's public, read-only CLI. Its internal Node
# registry module layout differs between Playwright releases.
def _headless_shell_locations(output: str) -> list[Path]:
    locations = []
    shell_section = False
    for line in re.sub(r"\x1b\[[0-9;]*m", "", output).splitlines():
        if line and not line[0].isspace():
            title = line.lower()
            shell_section = "headless" in title and ("chrome" in title or "chromium" in title)
        elif shell_section and line.strip().lower().startswith("install location:"):
            locations.append(Path(line.split(":", 1)[1].strip()))
    return locations


def resolve_browser_test_executable(
    *,
    platform: str | None = None,
    python: Path | None = None,
    env: dict[str, str] | None = None,
) -> Path:
    if (platform or sys.platform) != "darwin":
        return discover_chrome_executable(platform=platform)

    interpreter = str(python or sys.executable)
    result = subprocess.run(
        [interpreter, "-m", "playwright", "install", "--dry-run", "--only-shell", "chromium"],
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    candidates = {
        path
        for root in _headless_shell_locations(result.stdout)
        for name in ("chrome-headless-shell", "headless_shell")
        for path in root.rglob(name)
        if path.is_file()
        and os.access(path, os.X_OK)
        and not any(part.lower().endswith(".app") for part in path.parts)
    }
    if result.returncode or len(candidates) != 1:
        raise RuntimeError(
            "macOS browser tests require Playwright's matching Chrome Headless Shell. "
            "Install it with: uv run playwright install --only-shell chromium "
            f"(for a separate test venv: {interpreter} -m playwright install --only-shell chromium). "
            "Tests will not fall back to desktop Chrome because it adds Dock recent-app entries. "
            f"Details: {result.stderr.strip() or result.stdout.strip() or 'shell path unavailable'}"
        )
    return candidates.pop()
