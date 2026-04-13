"""Local HTTP API for workflow service."""

from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from browser_cli.workflow.loader import load_workflow_manifest
from browser_cli.workflow.models import (
    PersistedWorkflowDefinition,
    manifest_to_persisted_definition,
)
from browser_cli.workflow.web import render_index_html


class WorkflowHttpServer(ThreadingHTTPServer):
    def __init__(self, server_address, request_handler_class, runtime) -> None:
        super().__init__(server_address, request_handler_class)
        self.runtime = runtime


class WorkflowRequestHandler(BaseHTTPRequestHandler):
    server: WorkflowHttpServer

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
                    {"ok": True, "data": self.server.runtime.status_payload(), "meta": {}}
                )
                return
            if path == "/api/service/stop" and method == "POST":
                self.server.runtime.stop()
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                self._send_json({"ok": True, "data": {"stopped": True}, "meta": {}})
                return
            if path == "/api/workflows" and method == "GET":
                workflows = [
                    self._serialize_workflow(item, include_latest_run=True)
                    for item in self.server.runtime.store.list_workflows()
                ]
                self._send_json({"ok": True, "data": workflows, "meta": {}})
                return
            if path == "/api/workflows" and method == "POST":
                body = self._read_json_body()
                created = self.server.runtime.store.upsert_workflow(_payload_to_workflow(body))
                self._send_json(
                    {"ok": True, "data": self._serialize_workflow(created), "meta": {}},
                    status=HTTPStatus.CREATED,
                )
                return
            if path == "/api/workflows/import" and method == "POST":
                body = self._read_json_body()
                manifest = load_workflow_manifest(str(body["path"]))
                enabled = bool(body.get("enabled"))
                workflow = manifest_to_persisted_definition(manifest, enabled=enabled)
                created = self.server.runtime.store.upsert_workflow(workflow)
                self._send_json({"ok": True, "data": self._serialize_workflow(created), "meta": {}})
                return
            if path.startswith("/api/workflows/") and path.endswith("/runs") and method == "GET":
                workflow_id = path.split("/")[3]
                runs = [
                    self._serialize_run(item)
                    for item in self.server.runtime.store.list_runs(workflow_id)
                ]
                self._send_json({"ok": True, "data": runs, "meta": {}})
                return
            if path.startswith("/api/workflows/") and path.endswith("/enable") and method == "POST":
                workflow_id = path.split("/")[3]
                updated = self.server.runtime.store.set_enabled(workflow_id, True)
                self._send_json({"ok": True, "data": self._serialize_workflow(updated), "meta": {}})
                return
            if (
                path.startswith("/api/workflows/")
                and path.endswith("/disable")
                and method == "POST"
            ):
                workflow_id = path.split("/")[3]
                updated = self.server.runtime.store.set_enabled(workflow_id, False)
                self._send_json({"ok": True, "data": self._serialize_workflow(updated), "meta": {}})
                return
            if path.startswith("/api/workflows/") and path.endswith("/run") and method == "POST":
                workflow_id = path.split("/")[3]
                run = self.server.runtime.store.create_run(workflow_id, trigger_type="manual")
                self._send_json({"ok": True, "data": self._serialize_run(run), "meta": {}})
                return
            if path.startswith("/api/workflows/") and path.endswith("/export") and method == "GET":
                workflow_id = path.split("/")[3]
                workflow = self.server.runtime.store.get_workflow(workflow_id)
                self._send_json(
                    {"ok": True, "data": {"toml": _workflow_to_toml(workflow)}, "meta": {}}
                )
                return
            if path.startswith("/api/workflows/") and method == "GET":
                workflow_id = path.split("/")[3]
                workflow = self.server.runtime.store.get_workflow(workflow_id)
                self._send_json(
                    {"ok": True, "data": self._serialize_workflow(workflow), "meta": {}}
                )
                return
            if path.startswith("/api/workflows/") and method == "PUT":
                workflow_id = path.split("/")[3]
                payload = self._read_json_body()
                payload["id"] = workflow_id
                updated = self.server.runtime.store.upsert_workflow(_payload_to_workflow(payload))
                self._send_json({"ok": True, "data": self._serialize_workflow(updated), "meta": {}})
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
                {"ok": False, "error_message": f"Not found: {path}", "error_code": "NOT_FOUND"},
                status=HTTPStatus.NOT_FOUND,
            )
        except Exception as exc:
            self._send_json(
                {
                    "ok": False,
                    "error_message": str(exc),
                    "error_code": getattr(exc, "error_code", "INTERNAL_ERROR"),
                },
                status=HTTPStatus.BAD_REQUEST,
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

    def _serialize_workflow(
        self, workflow: PersistedWorkflowDefinition, *, include_latest_run: bool = False
    ) -> dict:
        payload = {
            "id": workflow.id,
            "name": workflow.name,
            "description": workflow.description,
            "version": workflow.version,
            "task_path": str(workflow.task_path),
            "task_meta_path": str(workflow.task_meta_path),
            "entrypoint": workflow.entrypoint,
            "enabled": workflow.enabled,
            "definition_status": workflow.definition_status,
            "definition_error": workflow.definition_error,
            "schedule_kind": workflow.schedule_kind,
            "schedule_payload": workflow.schedule_payload,
            "timezone": workflow.timezone,
            "output_dir": str(workflow.output_dir),
            "result_json_path": str(workflow.result_json_path)
            if workflow.result_json_path
            else None,
            "stdout_mode": workflow.stdout_mode,
            "input_overrides": workflow.input_overrides,
            "before_run_hooks": list(workflow.before_run_hooks),
            "after_success_hooks": list(workflow.after_success_hooks),
            "after_failure_hooks": list(workflow.after_failure_hooks),
            "retry_attempts": workflow.retry_attempts,
            "retry_backoff_seconds": workflow.retry_backoff_seconds,
            "timeout_seconds": workflow.timeout_seconds,
            "created_at": workflow.created_at,
            "updated_at": workflow.updated_at,
            "last_run_at": workflow.last_run_at,
            "next_run_at": workflow.next_run_at,
        }
        if include_latest_run:
            runs = self.server.runtime.store.list_runs(workflow.id, limit=1)
            payload["latest_run"] = self._serialize_run(runs[0]) if runs else None
        return payload

    def _serialize_run(self, run) -> dict:
        return {
            "run_id": run.run_id,
            "workflow_id": run.workflow_id,
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


def _payload_to_workflow(payload: dict) -> PersistedWorkflowDefinition:
    workflow_id = str(payload.get("id") or "").strip()
    if not workflow_id:
        raise ValueError("Workflow id is required.")
    output_dir_raw = str(payload.get("output_dir") or "").strip()
    output_dir = Path(output_dir_raw) if output_dir_raw else Path()
    result_json_raw = str(payload.get("result_json_path") or "").strip()
    return PersistedWorkflowDefinition(
        id=workflow_id,
        name=str(payload.get("name") or workflow_id),
        description=str(payload.get("description") or ""),
        version=str(payload.get("version") or "0.1.0"),
        task_path=Path(str(payload.get("task_path") or "")),
        task_meta_path=Path(str(payload.get("task_meta_path") or "")),
        entrypoint=str(payload.get("entrypoint") or "run"),
        enabled=bool(payload.get("enabled")),
        schedule_kind=str(payload.get("schedule_kind") or "manual"),
        schedule_payload=dict(payload.get("schedule_payload") or {}),
        timezone=str(payload.get("timezone") or "UTC"),
        output_dir=output_dir,
        result_json_path=Path(result_json_raw) if result_json_raw else None,
        input_overrides=dict(payload.get("input_overrides") or {}),
        before_run_hooks=tuple(payload.get("before_run_hooks") or []),
        after_success_hooks=tuple(payload.get("after_success_hooks") or []),
        after_failure_hooks=tuple(payload.get("after_failure_hooks") or []),
        retry_attempts=int(payload.get("retry_attempts") or 0),
        retry_backoff_seconds=int(payload.get("retry_backoff_seconds") or 0),
        timeout_seconds=float(payload["timeout_seconds"])
        if payload.get("timeout_seconds") is not None
        else None,
    )


def _workflow_to_toml(workflow: PersistedWorkflowDefinition) -> str:
    def fmt(value):
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int | float):
            return str(value)
        return json.dumps(value, ensure_ascii=False)

    result_json_value = fmt(str(workflow.result_json_path)) if workflow.result_json_path else '""'
    lines = [
        "[workflow]",
        f"id = {fmt(workflow.id)}",
        f"name = {fmt(workflow.name)}",
        f"description = {fmt(workflow.description)}",
        f"version = {fmt(workflow.version)}",
        "",
        "[task]",
        f"path = {fmt(str(workflow.task_path))}",
        f"meta_path = {fmt(str(workflow.task_meta_path))}",
        f"entrypoint = {fmt(workflow.entrypoint)}",
        "",
        "[inputs]",
    ]
    if workflow.input_overrides:
        for key, value in workflow.input_overrides.items():
            lines.append(f"{key} = {fmt(value)}")
    lines.extend(
        [
            "",
            "[schedule]",
            f"mode = {fmt(workflow.schedule_kind)}",
            f"timezone = {fmt(workflow.timezone)}",
        ]
    )
    for key, value in workflow.schedule_payload.items():
        if key in {"mode", "timezone"}:
            continue
        lines.append(f"{key} = {fmt(value)}")
    lines.extend(
        [
            "",
            "[outputs]",
            f"artifact_dir = {fmt(str(workflow.output_dir))}",
            f"result_json_path = {result_json_value}",
            f"stdout = {fmt(workflow.stdout_mode)}",
            "",
            "[hooks]",
            f"before_run = {json.dumps(list(workflow.before_run_hooks), ensure_ascii=False)}",
            f"after_success = {json.dumps(list(workflow.after_success_hooks), ensure_ascii=False)}",
            f"after_failure = {json.dumps(list(workflow.after_failure_hooks), ensure_ascii=False)}",
            "",
            "[runtime]",
            f"retry_attempts = {fmt(workflow.retry_attempts)}",
            f"timeout_seconds = {fmt(workflow.timeout_seconds) if workflow.timeout_seconds is not None else '0'}",
            f"log_level = {fmt('info')}",
        ]
    )
    return "\n".join(lines) + "\n"


def _read_text(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8")
