"""Check browser dependencies once at execution time, never during collection."""

from __future__ import annotations

import pytest
from tests.browser_runtime import get_test_browser_executable

from browser_cli.browser.launch_preflight import ensure_browser_launch_allowed


@pytest.fixture(scope="session", autouse=True)
def _require_browser_runtime(request):
    ensure_browser_launch_allowed()
    executable = get_test_browser_executable()
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(f"Browser integration runtime: {executable}")
    return executable
