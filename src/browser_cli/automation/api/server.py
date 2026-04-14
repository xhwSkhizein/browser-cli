"""Local HTTP API for automation service."""

from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from browser_cli.automation.loader import load_automation_manifest
from browser_cli.automation.models import PersistedAutomationDefinition
from browser_cli.automation.projections import (
    manifest_to_persisted_definition,
    payload_to_persisted_definition,
    persisted_definition_to_config_payload,
    persisted_definition_to_manifest_toml,
)
from browser_cli.automation.web import render_index_html
from browser_cli.errors import BrowserCliError, InvalidInputError


class AutomationHttpServer(ThreadingHTTPServer):
    def __init__(self, server_address, request_handler_class, runtime) -> None:
        super().__init__(server_address, request_handler_class)
        self.runtime = runtime


class AutomationRequestHandler(BaseHTTPRequestHandler):
    server: AutomationHttpServer

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._handle("PUT")

    def log_message(self, _format: str, *_args) -> None:
        return

    def _handle(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/":
                self._send_html(render_index_html())
                return
            if path == "/api/service/status":
                self._send_json(
                    {
                        "ok": True,
                        "data": self.server.runtime.status_payload(),
                        "meta": {},
                    }
                )
                return
            if path == "/api/service/stop" and method == "POST":
                self.server.runtime.stop()
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                self._send_json({"ok": True, "data": {"stopped": True}, "meta": {}})
                return
            if path == "/api/automations" and method == "GET":
                automations = [
                    self._serialize_automation(item, include_latest_run=True)
                    for item in self.server.runtime.store.list_automations()
                ]
                self._send_json({"ok": True, "data": automations, "meta": {}})
                return
            if path == "/api/automations" and method == "POST":
                body = self._read_json_body()
                created = self.server.runtime.store.upsert_automation(
                    payload_to_persisted_definition(body)
                )
                self._send_json(
                    {
                        "ok": True,
                        "data": self._serialize_automation(created),
                        "meta": {},
                    },
                    status=HTTPStatus.CREATED,
                )
                return
            if path == "/api/automations/import" and method == "POST":
                body = self._read_json_body()
                manifest_path = str(body.get("path") or "").strip()
                if not manifest_path:
                    raise InvalidInputError("Automation import requires non-empty path.")
                manifest = load_automation_manifest(manifest_path)
                enabled = bool(body.get("enabled"))
                automation = manifest_to_persisted_definition(manifest, enabled=enabled)
                created = self.server.runtime.store.upsert_automation(automation)
                self._send_json(
                    {
                        "ok": True,
                        "data": self._serialize_automation(created),
                        "meta": {},
                    }
                )
                return
            if path.startswith("/api/automations/") and path.endswith("/runs") and method == "GET":
                automation_id = path.split("/")[3]
                runs = [
                    self._serialize_run(item)
                    for item in self.server.runtime.store.list_runs(automation_id)
                ]
                self._send_json({"ok": True, "data": runs, "meta": {}})
                return
            if (
                path.startswith("/api/automations/")
                and path.endswith("/enable")
                and method == "POST"
            ):
                automation_id = path.split("/")[3]
                updated = self.server.runtime.store.set_enabled(automation_id, True)
                self._send_json(
                    {
                        "ok": True,
                        "data": self._serialize_automation(updated),
                        "meta": {},
                    }
                )
                return
            if (
                path.startswith("/api/automations/")
                and path.endswith("/disable")
                and method == "POST"
            ):
                automation_id = path.split("/")[3]
                updated = self.server.runtime.store.set_enabled(automation_id, False)
                self._send_json(
                    {
                        "ok": True,
                        "data": self._serialize_automation(updated),
                        "meta": {},
                    }
                )
                return
            if path.startswith("/api/automations/") and path.endswith("/run") and method == "POST":
                automation_id = path.split("/")[3]
                run = self.server.runtime.store.create_run(automation_id, trigger_type="manual")
                self._send_json({"ok": True, "data": self._serialize_run(run), "meta": {}})
                return
            if (
                path.startswith("/api/automations/")
                and path.endswith("/export")
                and method == "GET"
            ):
                automation_id = path.split("/")[3]
                automation = self.server.runtime.store.get_automation(automation_id)
                self._send_json(
                    {
                        "ok": True,
                        "data": {"toml": persisted_definition_to_manifest_toml(automation)},
                        "meta": {},
                    }
                )
                return
            if path.startswith("/api/automations/") and method == "GET":
                automation_id = path.split("/")[3]
                automation = self.server.runtime.store.get_automation(automation_id)
                self._send_json(
                    {
                        "ok": True,
                        "data": self._serialize_automation(automation, include_latest_run=True),
                        "meta": {},
                    }
                )
                return
            if path.startswith("/api/automations/") and method == "PUT":
                automation_id = path.split("/")[3]
                payload = self._read_json_body()
                payload["id"] = automation_id
                updated = self.server.runtime.store.upsert_automation(
                    payload_to_persisted_definition(payload)
                )
                self._send_json(
                    {
                        "ok": True,
                        "data": self._serialize_automation(updated),
                        "meta": {},
                    }
                )
                return
            if path.startswith("/api/runs/") and path.endswith("/retry") and method == "POST":
                run_id = path.split("/")[3]
                run = self.server.runtime.store.retry_run(run_id)
                self._send_json({"ok": True, "data": self._serialize_run(run), "meta": {}})
                return
            if path.startswith("/api/runs/") and method == "GET":
                run_id = path.split("/")[3]
                run = self.server.runtime.store.get_run(run_id)
                events = self.server.runtime.store.list_run_events(run_id)
                self._send_json(
                    {
                        "ok": True,
                        "data": {
                            **self._serialize_run(run),
                            "events": [self._serialize_event(item) for item in events],
                            "log_text": _read_text(run.log_path),
                        },
                        "meta": {},
                    }
                )
                return
            self._send_json(
                {
                    "ok": False,
                    "error_message": f"Not found: {path}",
                    "error_code": "NOT_FOUND",
                },
                status=HTTPStatus.NOT_FOUND,
            )
        except KeyError as exc:
            self._send_json(
                {
                    "ok": False,
                    "error_message": f"Not found: {exc}",
                    "error_code": "NOT_FOUND",
                },
                status=HTTPStatus.NOT_FOUND,
            )
        except Exception as exc:
            status = (
                HTTPStatus.BAD_REQUEST
                if isinstance(exc, BrowserCliError | ValueError | json.JSONDecodeError)
                else HTTPStatus.INTERNAL_SERVER_ERROR
            )
            self._send_json(
                {
                    "ok": False,
                    "error_message": str(exc),
                    "error_code": getattr(
                        exc,
                        "error_code",
                        "INVALID_INPUT" if status == HTTPStatus.BAD_REQUEST else "INTERNAL_ERROR",
                    ),
                },
                status=status,
            )

    def _send_html(self, html: str, *, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = html.encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict, *, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _serialize_automation(
        self,
        automation: PersistedAutomationDefinition,
        *,
        include_latest_run: bool = False,
    ) -> dict:
        payload = persisted_definition_to_config_payload(automation)
        payload.update(
            {
                "enabled": automation.enabled,
                "definition_status": automation.definition_status,
                "definition_error": automation.definition_error,
                "created_at": automation.created_at,
                "updated_at": automation.updated_at,
                "last_run_at": automation.last_run_at,
                "next_run_at": automation.next_run_at,
            }
        )
        if include_latest_run:
            runs = self.server.runtime.store.list_runs(automation.id, limit=1)
            payload["latest_run"] = self._serialize_run(runs[0]) if runs else None
        return payload

    def _serialize_run(self, run) -> dict:
        return {
            "run_id": run.run_id,
            "automation_id": run.automation_id,
            "trigger_type": run.trigger_type,
            "status": run.status,
            "effective_inputs": run.effective_inputs,
            "attempt_number": run.attempt_number,
            "queued_at": run.queued_at,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "error_code": run.error_code,
            "error_message": run.error_message,
            "result_json_path": str(run.result_json_path) if run.result_json_path else None,
            "artifacts_dir": str(run.artifacts_dir) if run.artifacts_dir else None,
            "log_path": str(run.log_path) if run.log_path else None,
        }

    def _serialize_event(self, event) -> dict:
        return {
            "event_type": event.event_type,
            "message": event.message,
            "created_at": event.created_at,
            "payload": event.payload,
        }


def _read_text(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8")
