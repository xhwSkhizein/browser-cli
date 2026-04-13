from __future__ import annotations

from pathlib import Path

import pytest
from tests.integration.fixture_server import run_fixture_server
from tests.integration.test_daemon_actions import (
    _can_launch_daemon_browser,
    _configure_runtime,
    _run_cli_json,
    _run_cli_text,
    _stop_daemon,
)

pytestmark = pytest.mark.integration


@pytest.mark.skipif(not _can_launch_daemon_browser(), reason="Stable Chrome runtime unavailable")
def test_daemon_residency_loop_keeps_runtime_status_consistent(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    with run_fixture_server() as base_url:
        _configure_runtime(monkeypatch, tmp_path)

        for round_index in range(3):
            open_payload = _run_cli_json(["open", f"{base_url}/interactive"], capsys)
            assert open_payload["meta"]["driver"] in {"playwright", "extension"}

            status_text = _run_cli_text(["status"], capsys)
            assert "Status:" in status_text
            assert "Status: broken" not in status_text

            snapshot_payload = _run_cli_json(["snapshot"], capsys)
            assert snapshot_payload["data"]["refs_summary"]

            html_payload = _run_cli_json(["html"], capsys)
            assert "<html" in html_payload["data"]["html"].lower()

            close_payload = _run_cli_json(["close"], capsys)
            assert close_payload["data"]["closed"] is True

            if round_index == 1:
                reload_text = _run_cli_text(["reload"], capsys)
                assert "Reload: complete" in reload_text

        final_status = _run_cli_text(["status"], capsys)
        assert "Status: broken" not in final_status
        _stop_daemon(capsys)
