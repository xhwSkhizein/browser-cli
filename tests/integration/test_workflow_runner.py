from __future__ import annotations

import json
import shutil
import socket
import sys
import tempfile
from pathlib import Path

import pytest
from tests.integration.fixture_server import run_fixture_server

from browser_cli.cli.main import main
from browser_cli.profiles.discovery import discover_chrome_executable

REPO_ROOT = Path(__file__).resolve().parents[2]


def _can_launch_daemon_browser() -> bool:
    try:
        executable_path = discover_chrome_executable()
    except Exception:
        return False

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return False

    import asyncio

    async def _probe() -> bool:
        playwright = await async_playwright().start()
        with tempfile.TemporaryDirectory() as tmp:
            user_data_dir = Path(tmp) / "user-data"
            user_data_dir.mkdir(parents=True)
            try:
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=str(user_data_dir),
                    executable_path=str(executable_path),
                    headless=True,
                )
                await context.close()
                return True
            except Exception:
                return False
            finally:
                await playwright.stop()

    return asyncio.run(_probe())


def _configure_runtime(monkeypatch, tmp_path: Path) -> None:
    def _unused_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

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
    monkeypatch.setenv("X_AGENT_ID", "workflow-agent")
    monkeypatch.setenv("BROWSER_CLI_HEADLESS", "1")
    monkeypatch.setenv("BROWSER_CLI_EXTENSION_PORT", str(_unused_port()))


def _run_cli_json(args: list[str], capsys) -> dict:
    exit_code = main(args)
    captured = capsys.readouterr()
    assert exit_code == 0, captured.err
    return json.loads(captured.out)


@pytest.mark.skipif(not _can_launch_daemon_browser(), reason="Stable Chrome runtime unavailable")
def test_workflow_validate_and_run_against_local_fixture(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    source_dir = REPO_ROOT / "tasks" / "interactive_reveal_capture"
    copied_dir = tmp_path / "interactive_reveal_capture"
    shutil.copytree(source_dir, copied_dir)
    workflow_path = copied_dir / "workflow.toml"

    validate_payload = _run_cli_json(["workflow", "validate", str(workflow_path)], capsys)
    assert validate_payload["data"]["valid"] is True

    with run_fixture_server() as base_url:
        run_payload = _run_cli_json(
            [
                "workflow",
                "run",
                str(workflow_path),
                "--set",
                f"url={base_url}/interactive",
            ],
            capsys,
        )

    result = run_payload["data"]["result"]
    assert result["url"].endswith("/interactive")
    assert Path(result["html_path"]).exists()
    assert "Interactive Fixture" in Path(result["html_path"]).read_text(encoding="utf-8")
    assert Path(run_payload["data"]["result_json_path"]).exists()
