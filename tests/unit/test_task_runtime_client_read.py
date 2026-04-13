from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from browser_cli.errors import EmptyContentError
from browser_cli.profiles.discovery import ChromeEnvironment
from browser_cli.task_runtime.client import BrowserCliTaskClient
from browser_cli.task_runtime.flow import Flow
from browser_cli.task_runtime.models import FlowContext


def _chrome_environment(tmp_path: Path) -> ChromeEnvironment:
    user_data_dir = tmp_path / "user-data"
    (user_data_dir / "Default").mkdir(parents=True)
    return ChromeEnvironment(
        executable_path=None,
        user_data_dir=user_data_dir,
        profile_directory="Default",
        source="fallback",
        fallback_reason="Chrome profile appears to be in use.",
    )


def test_client_read_injects_chrome_environment_when_daemon_is_cold(tmp_path: Path) -> None:
    from browser_cli.task_runtime.read import ReadResult

    chrome_environment = _chrome_environment(tmp_path)
    captured: dict[str, object] = {}

    def _fake_send_command(action: str, args=None, start_if_needed: bool = True):
        captured["action"] = action
        captured["args"] = args
        captured["start_if_needed"] = start_if_needed
        return {
            "ok": True,
            "data": {
                "body": "<html>ready</html>",
                "used_fallback_profile": True,
                "fallback_profile_dir": str(chrome_environment.user_data_dir),
                "fallback_reason": chrome_environment.fallback_reason,
            },
        }

    with (
        patch("browser_cli.task_runtime.read.probe_socket", return_value=False),
        patch(
            "browser_cli.task_runtime.read.discover_chrome_environment",
            return_value=chrome_environment,
        ),
        patch("browser_cli.task_runtime.read.send_command", side_effect=_fake_send_command),
    ):
        result = BrowserCliTaskClient().read("https://example.com", scroll_bottom=True)

    assert captured["action"] == "read-page"
    assert captured["start_if_needed"] is True
    assert captured["args"] == {
        "url": "https://example.com",
        "output_mode": "html",
        "scroll_bottom": True,
        "chrome_environment": {
            "executable_path": None,
            "user_data_dir": str(chrome_environment.user_data_dir),
            "profile_directory": "Default",
            "profile_name": None,
            "source": "fallback",
            "fallback_reason": "Chrome profile appears to be in use.",
        },
    }
    assert result == ReadResult(
        body="<html>ready</html>",
        used_fallback_profile=True,
        fallback_profile_dir=str(chrome_environment.user_data_dir),
        fallback_reason="Chrome profile appears to be in use.",
    )


def test_client_read_raises_empty_content_error() -> None:
    with (
        patch("browser_cli.task_runtime.read.probe_socket", return_value=True),
        patch(
            "browser_cli.task_runtime.read.send_command",
            return_value={"ok": True, "data": {"body": "   "}},
        ),
        pytest.raises(EmptyContentError),
    ):
        BrowserCliTaskClient().read("https://example.com")


def test_flow_read_delegates_to_client(tmp_path: Path) -> None:
    from browser_cli.task_runtime.read import ReadResult

    class _FakeClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, bool]] = []

        def read(
            self,
            url: str,
            *,
            output_mode: str = "html",
            scroll_bottom: bool = False,
        ) -> ReadResult:
            self.calls.append((url, output_mode, scroll_bottom))
            return ReadResult(body="snapshot tree")

    client = _FakeClient()
    flow = Flow(
        client=client,
        context=FlowContext(
            task_path=tmp_path / "task.py",
            task_dir=tmp_path,
            artifacts_dir=tmp_path / "artifacts",
        ),
    )

    result = flow.read("https://example.com", output_mode="snapshot", scroll_bottom=True)

    assert client.calls == [("https://example.com", "snapshot", True)]
    assert result.body == "snapshot tree"
