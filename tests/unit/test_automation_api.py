from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path

from browser_cli.automation.api import AutomationHttpServer, AutomationRequestHandler
from browser_cli.automation.api.server import _payload_to_automation
from browser_cli.automation.persistence import AutomationStore
from browser_cli.automation.service.runtime import AutomationServiceRuntime

REPO_ROOT = Path(__file__).resolve().parents[2]


def _request(
    base_host: str, base_port: int, method: str, path: str, body: dict | None = None
) -> dict:
    connection = http.client.HTTPConnection(base_host, base_port, timeout=5.0)
    try:
        raw = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if raw is not None else {}
        connection.request(method, path, body=raw, headers=headers)
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status < 400, payload
        return payload
    finally:
        connection.close()


def test_automation_api_crud_and_export(tmp_path: Path) -> None:
    runtime = AutomationServiceRuntime(store=AutomationStore(tmp_path / "automations.db"))
    server = AutomationHttpServer(("127.0.0.1", 0), AutomationRequestHandler, runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        create_payload = _request(
            host,
            int(port),
            "POST",
            "/api/automations",
            {
                "id": "interactive_reveal_capture",
                "name": "Interactive Reveal Capture",
                "task_path": str(REPO_ROOT / "tasks" / "interactive_reveal_capture" / "task.py"),
                "task_meta_path": str(
                    REPO_ROOT / "tasks" / "interactive_reveal_capture" / "task.meta.json"
                ),
                "schedule_kind": "manual",
                "schedule_payload": {},
                "timezone": "UTC",
                "output_dir": str(tmp_path / "runs"),
                "input_overrides": {"url": "https://example.com"},
                "retry_backoff_seconds": 7,
            },
        )
        assert create_payload["data"]["id"] == "interactive_reveal_capture"

        list_payload = _request(host, int(port), "GET", "/api/automations")
        assert len(list_payload["data"]) == 1

        run_payload = _request(
            host,
            int(port),
            "POST",
            "/api/automations/interactive_reveal_capture/run",
        )
        assert run_payload["data"]["status"] == "queued"

        export_payload = _request(
            host,
            int(port),
            "GET",
            "/api/automations/interactive_reveal_capture/export",
        )
        assert "[automation]" in export_payload["data"]["toml"]
        assert 'id = "interactive_reveal_capture"' in export_payload["data"]["toml"]
        assert 'result_json_path = ""' in export_payload["data"]["toml"]
        assert "retry_backoff_seconds = 7" in export_payload["data"]["toml"]
        assert "timeout_seconds = 0" not in export_payload["data"]["toml"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_automation_api_returns_not_found_for_missing_run(tmp_path: Path) -> None:
    runtime = AutomationServiceRuntime(store=AutomationStore(tmp_path / "automations.db"))
    server = AutomationHttpServer(("127.0.0.1", 0), AutomationRequestHandler, runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        connection = http.client.HTTPConnection(host, int(port), timeout=5.0)
        try:
            connection.request("GET", "/api/runs/missing")
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()
        assert response.status == 404
        assert payload["error_code"] == "NOT_FOUND"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_payload_to_automation_preserves_stdout_and_retry_backoff() -> None:
    persisted = _payload_to_automation(
        {
            "id": "demo",
            "name": "Demo",
            "task_path": "/tmp/task.py",
            "task_meta_path": "/tmp/task.meta.json",
            "output_dir": "/tmp/out",
            "stdout_mode": "text",
            "retry_attempts": 1,
            "retry_backoff_seconds": 9,
            "timeout_seconds": 4.0,
        }
    )

    assert persisted.stdout_mode == "text"
    assert persisted.retry_backoff_seconds == 9
    assert persisted.timeout_seconds == 4.0
