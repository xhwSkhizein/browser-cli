from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import time
from pathlib import Path

import pytest

from browser_cli.cli.main import main
from browser_cli.daemon.client import send_command
from browser_cli.errors import BusyTabError
from browser_cli.profiles.discovery import discover_chrome_executable
from tests.integration.fixture_server import run_fixture_server


def _can_launch_daemon_browser() -> bool:
    try:
        executable_path = discover_chrome_executable()
    except Exception:
        return False

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return False

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


pytestmark = pytest.mark.integration


def _configure_runtime(monkeypatch, tmp_path: Path, *, agent_id: str = "agent-a") -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / ".browser-cli-runtime"))
    monkeypatch.setenv("X_AGENT_ID", agent_id)


def _run_cli_json(args: list[str], capsys) -> dict:
    exit_code = main(args)
    captured = capsys.readouterr()
    assert exit_code == 0, captured.err
    return json.loads(captured.out)


def _stop_daemon(capsys) -> None:
    main(["stop"])
    capsys.readouterr()


@pytest.mark.skipif(not _can_launch_daemon_browser(), reason="Stable Chrome runtime unavailable")
def test_open_tabs_snapshot_html_and_stop(monkeypatch, tmp_path: Path, capsys) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    with run_fixture_server() as base_url:
        open_payload = _run_cli_json(["open", f"{base_url}/static"], capsys)
        assert open_payload["data"]["page"]["page_id"] == "page_0001"

        tabs_payload = _run_cli_json(["tabs"], capsys)
        assert len(tabs_payload["data"]["tabs"]) == 1
        assert tabs_payload["data"]["tabs"][0]["active"] is True

        snapshot_payload = _run_cli_json(["snapshot"], capsys)
        assert "Static Fixture" in snapshot_payload["data"]["tree"]

        html_payload = _run_cli_json(["html"], capsys)
        assert "Static Fixture" in html_payload["data"]["html"]
        assert "data-browser-cli-ref" not in html_payload["data"]["html"]

        stop_payload = _run_cli_json(["stop"], capsys)
        assert stop_payload["data"]["stopped"] is True


@pytest.mark.skipif(not _can_launch_daemon_browser(), reason="Stable Chrome runtime unavailable")
def test_interactive_action_chain(monkeypatch, tmp_path: Path, capsys) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    with run_fixture_server() as base_url:
        _run_cli_json(["open", f"{base_url}/interactive"], capsys)
        snapshot_payload = _run_cli_json(["snapshot"], capsys)
        refs_summary = snapshot_payload["data"]["refs_summary"]

        def _find_ref(name: str, role: str) -> str:
            for item in refs_summary:
                if item.get("name") == name and item.get("role") == role:
                    return str(item["ref"])
            raise AssertionError(f"Missing ref for {role} {name}")

        button_ref = _find_ref("Reveal Message", "button")
        input_ref = _find_ref("Name Input", "textbox")
        select_ref = _find_ref("Color Select", "combobox")

        _run_cli_json(["console-start"], capsys)
        _run_cli_json(["network-start"], capsys)
        _run_cli_json(["fill", input_ref, "Alice"], capsys)
        _run_cli_json(["select", select_ref, "Blue"], capsys)
        _run_cli_json(["click", button_ref], capsys)
        _run_cli_json(["wait", "5", "--text", "Revealed"], capsys)

        eval_payload = _run_cli_json(["eval-on", input_ref, "(el) => el.value"], capsys)
        assert eval_payload["data"]["result"] == "Alice"

        console_payload = _run_cli_json(["console"], capsys)
        assert any(message["text"] == "reveal-clicked" for message in console_payload["data"]["messages"])

        network_payload = _run_cli_json(["network"], capsys)
        assert any("/api/ping" in request["url"] for request in network_payload["data"]["requests"])

        verify_payload = _run_cli_json(["verify-text", "Revealed"], capsys)
        assert verify_payload["data"]["passed"] is True

        _stop_daemon(capsys)


@pytest.mark.skipif(not _can_launch_daemon_browser(), reason="Stable Chrome runtime unavailable")
def test_agent_visibility_isolation(monkeypatch, tmp_path: Path, capsys) -> None:
    with run_fixture_server() as base_url:
        _configure_runtime(monkeypatch, tmp_path, agent_id="agent-a")
        _run_cli_json(["open", f"{base_url}/static"], capsys)

        monkeypatch.setenv("X_AGENT_ID", "agent-b")
        _run_cli_json(["open", f"{base_url}/dynamic"], capsys)

        tabs_b = _run_cli_json(["tabs"], capsys)
        assert len(tabs_b["data"]["tabs"]) == 1
        assert "/dynamic" in tabs_b["data"]["tabs"][0]["url"]

        monkeypatch.setenv("X_AGENT_ID", "agent-a")
        tabs_a = _run_cli_json(["tabs"], capsys)
        assert len(tabs_a["data"]["tabs"]) == 1
        assert "/static" in tabs_a["data"]["tabs"][0]["url"]

        _stop_daemon(capsys)


@pytest.mark.skipif(not _can_launch_daemon_browser(), reason="Stable Chrome runtime unavailable")
def test_busy_active_tab_returns_explicit_error(monkeypatch, tmp_path: Path, capsys) -> None:
    _configure_runtime(monkeypatch, tmp_path, agent_id="agent-a")
    with run_fixture_server() as base_url:
        _run_cli_json(["open", f"{base_url}/interactive"], capsys)

        result_box: dict[str, object] = {}

        def _run_long_eval() -> None:
            result_box["payload"] = send_command(
                "eval",
                {
                    "code": "async () => { await new Promise((resolve) => setTimeout(resolve, 700)); return 'done'; }",
                },
            )

        thread = threading.Thread(target=_run_long_eval)
        thread.start()
        time.sleep(0.15)
        with pytest.raises(BusyTabError):
            send_command("html")
        thread.join(timeout=5)
        assert result_box["payload"]["ok"] is True

        _stop_daemon(capsys)
