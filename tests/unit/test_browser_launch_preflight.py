from __future__ import annotations

import asyncio
import ctypes
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import playwright.async_api as playwright_async_api
import pytest

from browser_cli.browser.launch_preflight import ensure_browser_launch_allowed
from browser_cli.browser.models import BrowserLaunchConfig
from browser_cli.browser.service import BrowserService
from browser_cli.browser.session import BrowserSession
from browser_cli.errors import BrowserUnavailableError
from browser_cli.profiles.discovery import ChromeEnvironment


@pytest.mark.parametrize("headless", [False, True])
@pytest.mark.parametrize("runtime", ["service", "session"])
def test_macos_sandbox_denial_prevents_chrome_process_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, runtime: str, headless: bool
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    sandbox_check = Mock(return_value=1)
    monkeypatch.setattr(
        ctypes, "CDLL", Mock(return_value=SimpleNamespace(sandbox_check=sandbox_check))
    )
    monkeypatch.setattr(ctypes.c_int, "in_dll", Mock(return_value=ctypes.c_int(0x40000000)))
    start_playwright = Mock(side_effect=AssertionError("Chrome must not be launched"))
    monkeypatch.setattr(playwright_async_api, "async_playwright", start_playwright)

    if runtime == "service":
        browser = BrowserService(
            ChromeEnvironment(executable_path=None, user_data_dir=tmp_path), headless=headless
        )
        start = browser.ensure_started
    else:
        browser = BrowserSession(
            BrowserLaunchConfig(executable_path=None, user_data_dir=tmp_path, headless=headless)
        )
        start = browser.start

    with pytest.raises(BrowserUnavailableError, match="macOS sandbox") as error:
        asyncio.run(start())

    assert error.value.error_code == "BROWSER_UNAVAILABLE"
    assert "outside" in str(error.value)
    start_playwright.assert_not_called()


@pytest.mark.parametrize("result", [0, -1])
def test_sandbox_environment_marker_alone_does_not_block_launch(
    monkeypatch: pytest.MonkeyPatch, result: int
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("CODEX_SANDBOX", "seatbelt")
    sandbox_check = Mock(return_value=result)
    monkeypatch.setattr(
        ctypes, "CDLL", Mock(return_value=SimpleNamespace(sandbox_check=sandbox_check))
    )
    monkeypatch.setattr(ctypes.c_int, "in_dll", Mock(return_value=ctypes.c_int(0x40000000)))

    ensure_browser_launch_allowed()

    sandbox_check.assert_called_once()
    args = sandbox_check.call_args.args
    assert args[1:3] == (b"mach-lookup", 2 | 0x40000000)
    assert args[3].value == b"com.apple.coreservices.launchservicesd"


def test_other_platforms_do_not_load_macos_sandbox_library(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    load_library = Mock(side_effect=AssertionError("macOS library must not be loaded"))
    monkeypatch.setattr(ctypes, "CDLL", load_library)

    ensure_browser_launch_allowed()

    load_library.assert_not_called()


@pytest.mark.parametrize(
    "error", [OSError("library unavailable"), AttributeError("SPI unavailable")]
)
def test_missing_sandbox_api_preserves_normal_launch(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(ctypes, "CDLL", Mock(side_effect=error))

    ensure_browser_launch_allowed()
