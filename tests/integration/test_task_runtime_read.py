from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path

import pytest
from tests.integration.fixture_server import run_fixture_server

from browser_cli.daemon.client import send_command
from browser_cli.profiles.discovery import ChromeEnvironment
from browser_cli.task_runtime.client import BrowserCliTaskClient


def _can_launch_playwright_browser() -> bool:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return False

    async def _probe() -> bool:
        playwright = await async_playwright().start()
        try:
            browser = await playwright.chromium.launch(headless=True)
            await browser.close()
            return True
        except Exception:
            return False
        finally:
            await playwright.stop()

    return asyncio.run(_probe())


pytestmark = pytest.mark.integration


def _unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _configure_runtime(monkeypatch, tmp_path: Path) -> None:
    real_home = Path.home()
    if not (
        real_home / "Library" / "Caches" / "ms-playwright"
    ).exists() and sys.platform.startswith("linux"):
        playwright_cache = real_home / ".cache" / "ms-playwright"
    else:
        playwright_cache = real_home / "Library" / "Caches" / "ms-playwright"
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(playwright_cache))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / ".browser-cli-runtime"))
    monkeypatch.setenv("X_AGENT_ID", "read-agent")
    monkeypatch.setenv("BROWSER_CLI_HEADLESS", "1")
    monkeypatch.setenv("BROWSER_CLI_EXTENSION_PORT", str(_unused_port()))


def _build_chrome_environment(tmp_path: Path) -> ChromeEnvironment:
    user_data_dir = tmp_path / "user-data"
    (user_data_dir / "Default").mkdir(parents=True)
    return ChromeEnvironment(
        executable_path=None,
        user_data_dir=user_data_dir,
        profile_directory="Default",
    )


def _serialize_environment(chrome_environment: ChromeEnvironment) -> dict[str, str | None]:
    return {
        "executable_path": (
            str(chrome_environment.executable_path)
            if chrome_environment.executable_path is not None
            else None
        ),
        "user_data_dir": str(chrome_environment.user_data_dir),
        "profile_directory": chrome_environment.profile_directory,
        "profile_name": chrome_environment.profile_name,
        "source": chrome_environment.source,
        "fallback_reason": chrome_environment.fallback_reason,
    }


@pytest.mark.skipif(
    not _can_launch_playwright_browser(), reason="Playwright browser runtime unavailable"
)
def test_task_runtime_read_capture_html_from_dynamic_fixture(monkeypatch, tmp_path: Path) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    client = BrowserCliTaskClient(chrome_environment=_build_chrome_environment(tmp_path))
    with run_fixture_server() as base_url:
        result = client.read(f"{base_url}/dynamic", output_mode="html")
        assert "Dynamic Fixture" in result.body
        assert "Rendered content." in result.body

        tabs = send_command("tabs", start_if_needed=False)
        assert tabs["data"]["tabs"] == []
        send_command("stop", start_if_needed=False)


@pytest.mark.skipif(
    not _can_launch_playwright_browser(), reason="Playwright browser runtime unavailable"
)
def test_task_runtime_read_capture_snapshot_from_static_fixture(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    client = BrowserCliTaskClient(chrome_environment=_build_chrome_environment(tmp_path))
    with run_fixture_server() as base_url:
        result = client.read(f"{base_url}/static", output_mode="snapshot")
        assert "heading" in result.body
        assert "Static Fixture" in result.body
        send_command("stop", start_if_needed=False)


@pytest.mark.skipif(
    not _can_launch_playwright_browser(), reason="Playwright browser runtime unavailable"
)
def test_task_runtime_read_scroll_bottom_loads_more_content_without_leaking_tabs(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    chrome_environment = _build_chrome_environment(tmp_path)
    client = BrowserCliTaskClient(chrome_environment=chrome_environment)
    with run_fixture_server() as base_url:
        existing_page = send_command(
            "open",
            {
                "url": f"{base_url}/static",
                "chrome_environment": _serialize_environment(chrome_environment),
            },
        )
        existing_page_id = existing_page["data"]["page"]["page_id"]

        result = client.read(
            f"{base_url}/lazy",
            output_mode="html",
            scroll_bottom=True,
        )
        assert "Lazy Item 4" in result.body

        tabs = send_command("tabs", start_if_needed=False)
        assert [tab["page_id"] for tab in tabs["data"]["tabs"]] == [existing_page_id]
        send_command("stop", start_if_needed=False)
