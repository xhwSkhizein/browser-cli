"""SQLite-backed automation persistence."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from browser_cli.automation.models import (
    AutomationRunEvent,
    AutomationRunRecord,
    PersistedAutomationDefinition,
)
from browser_cli.automation.scheduler import compute_next_run_at, normalize_schedule
from browser_cli.constants import get_app_paths
from browser_cli.task_runtime.models import validate_task_metadata

SCHEMA_VERSION = 1


class AutomationStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or get_app_paths().automation_db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS automations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    version TEXT NOT NULL DEFAULT '0.1.0',
                    task_path TEXT NOT NULL,
                    task_meta_path TEXT NOT NULL,
                    entrypoint TEXT NOT NULL DEFAULT 'run',
                    enabled INTEGER NOT NULL DEFAULT 0,
                    definition_status TEXT NOT NULL DEFAULT 'valid',
                    definition_error TEXT,
                    schedule_kind TEXT NOT NULL DEFAULT 'manual',
                    schedule_payload_json TEXT NOT NULL DEFAULT '{}',
                    timezone TEXT NOT NULL DEFAULT 'UTC',
                    output_dir TEXT NOT NULL,
                    result_json_path TEXT,
                    stdout_mode TEXT NOT NULL DEFAULT 'json',
                    input_overrides_json TEXT NOT NULL DEFAULT '{}',
                    before_run_hooks_json TEXT NOT NULL DEFAULT '[]',
                    after_success_hooks_json TEXT NOT NULL DEFAULT '[]',
                    after_failure_hooks_json TEXT NOT NULL DEFAULT '[]',
                    retry_attempts INTEGER NOT NULL DEFAULT 0,
                    retry_backoff_seconds INTEGER NOT NULL DEFAULT 0,
                    timeout_seconds REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_run_at TEXT,
                    next_run_at TEXT
                );
                CREATE TABLE IF NOT EXISTS automation_runs (
                    run_id TEXT PRIMARY KEY,
                    automation_id TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    effective_inputs_json TEXT NOT NULL DEFAULT '{}',
                    attempt_number INTEGER NOT NULL DEFAULT 0,
                    queued_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    result_json_path TEXT,
                    artifacts_dir TEXT,
                    log_path TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_automation_runs_automation_id
                    ON automation_runs(automation_id, queued_at DESC);
                CREATE INDEX IF NOT EXISTS idx_automation_runs_status
                    ON automation_runs(status, queued_at ASC);
                CREATE TABLE IF NOT EXISTS automation_run_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_automation_run_events_run_id
                    ON automation_run_events(run_id, created_at ASC);
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path, timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def upsert_automation(
        self, automation: PersistedAutomationDefinition
    ) -> PersistedAutomationDefinition:
        normalized = self._normalize_automation(automation)
        now = _utcnow()
        created_at = normalized.created_at or self._existing_created_at(normalized.id) or now
        updated = replace(normalized, created_at=created_at, updated_at=now)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO automations (
                    id, name, description, version, task_path, task_meta_path, entrypoint,
                    enabled, definition_status, definition_error, schedule_kind,
                    schedule_payload_json, timezone, output_dir, result_json_path, stdout_mode,
                    input_overrides_json, before_run_hooks_json, after_success_hooks_json,
                    after_failure_hooks_json, retry_attempts, retry_backoff_seconds,
                    timeout_seconds, created_at, updated_at, last_run_at, next_run_at
                ) VALUES (
                    :id, :name, :description, :version, :task_path, :task_meta_path, :entrypoint,
                    :enabled, :definition_status, :definition_error, :schedule_kind,
                    :schedule_payload_json, :timezone, :output_dir, :result_json_path, :stdout_mode,
                    :input_overrides_json, :before_run_hooks_json, :after_success_hooks_json,
                    :after_failure_hooks_json, :retry_attempts, :retry_backoff_seconds,
                    :timeout_seconds, :created_at, :updated_at, :last_run_at, :next_run_at
                )
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    version = excluded.version,
                    task_path = excluded.task_path,
                    task_meta_path = excluded.task_meta_path,
                    entrypoint = excluded.entrypoint,
                    enabled = excluded.enabled,
                    definition_status = excluded.definition_status,
                    definition_error = excluded.definition_error,
                    schedule_kind = excluded.schedule_kind,
                    schedule_payload_json = excluded.schedule_payload_json,
                    timezone = excluded.timezone,
                    output_dir = excluded.output_dir,
                    result_json_path = excluded.result_json_path,
                    stdout_mode = excluded.stdout_mode,
                    input_overrides_json = excluded.input_overrides_json,
                    before_run_hooks_json = excluded.before_run_hooks_json,
                    after_success_hooks_json = excluded.after_success_hooks_json,
                    after_failure_hooks_json = excluded.after_failure_hooks_json,
                    retry_attempts = excluded.retry_attempts,
                    retry_backoff_seconds = excluded.retry_backoff_seconds,
                    timeout_seconds = excluded.timeout_seconds,
                    updated_at = excluded.updated_at,
                    next_run_at = excluded.next_run_at
                """,
                _automation_to_row(updated),
            )
        return self.get_automation(updated.id)

    def _existing_created_at(self, automation_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT created_at FROM automations WHERE id = ?",
                (automation_id,),
            ).fetchone()
        return str(row["created_at"]) if row and row["created_at"] else None

    def get_automation(self, automation_id: str) -> PersistedAutomationDefinition:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM automations WHERE id = ?", (automation_id,)
            ).fetchone()
        if row is None:
            raise KeyError(automation_id)
        return _row_to_automation(row)

    def list_automations(self) -> list[PersistedAutomationDefinition]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM automations ORDER BY name, id").fetchall()
        return [_row_to_automation(row) for row in rows]

    def set_enabled(self, automation_id: str, enabled: bool) -> PersistedAutomationDefinition:
        automation = self.get_automation(automation_id)
        updated = replace(automation, enabled=enabled)
        return self.upsert_automation(updated)

    def create_run(
        self,
        automation_id: str,
        *,
        trigger_type: str,
        effective_inputs: dict[str, Any] | None = None,
        attempt_number: int = 0,
        queued_at: str | None = None,
    ) -> AutomationRunRecord:
        automation = self.get_automation(automation_id)
        if automation.definition_status != "valid":
            raise ValueError(
                f"Automation {automation_id} is invalid: {automation.definition_error or 'invalid'}"
            )
        now = _utcnow()
        run = AutomationRunRecord(
            run_id=uuid.uuid4().hex,
            automation_id=automation.id,
            trigger_type=trigger_type,
            status="queued",
            effective_inputs=dict(
                effective_inputs if effective_inputs is not None else automation.input_overrides
            ),
            attempt_number=attempt_number,
            queued_at=queued_at or now,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO automation_runs (
                    run_id, automation_id, trigger_type, status, effective_inputs_json,
                    attempt_number, queued_at, started_at, finished_at, error_code,
                    error_message, result_json_path, artifacts_dir, log_path
                ) VALUES (
                    :run_id, :automation_id, :trigger_type, :status, :effective_inputs_json,
                    :attempt_number, :queued_at, :started_at, :finished_at, :error_code,
                    :error_message, :result_json_path, :artifacts_dir, :log_path
                )
                """,
                _run_to_row(run),
            )
        self.add_run_event(
            run.run_id,
            AutomationRunEvent(
                run_id=run.run_id,
                event_type="queued",
                message=f"Run queued by {trigger_type}.",
                created_at=now,
            ),
        )
        return self.get_run(run.run_id)

    def enqueue_due_runs(self) -> list[str]:
        now = _utcnow()
        queued: list[str] = []
        for automation in self.list_automations():
            if (
                not automation.enabled
                or automation.definition_status != "valid"
                or not automation.next_run_at
            ):
                continue
            if automation.schedule_kind == "manual":
                continue
            if automation.next_run_at > now:
                continue
            if self._has_pending_run(automation.id):
                continue
            run = self.create_run(automation.id, trigger_type="scheduled")
            queued.append(run.run_id)
            self._update_next_run(automation.id)
        return queued

    def _has_pending_run(self, automation_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM automation_runs
                WHERE automation_id = ? AND status IN ('queued', 'running')
                """,
                (automation_id,),
            ).fetchone()
        return int(row["count"]) > 0

    def _update_next_run(self, automation_id: str) -> None:
        automation = self.get_automation(automation_id)
        normalized = self._normalize_automation(automation)
        with self._connect() as conn:
            conn.execute(
                "UPDATE automations SET next_run_at = ?, updated_at = ? WHERE id = ?",
                (normalized.next_run_at, _utcnow(), automation_id),
            )

    def claim_next_run(self) -> AutomationRunRecord | None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT *
                FROM automation_runs
                WHERE status = 'queued' AND queued_at <= ?
                ORDER BY queued_at ASC
                LIMIT 1
                """,
                (_utcnow(),),
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            run_id = str(row["run_id"])
            started_at = _utcnow()
            conn.execute(
                """
                UPDATE automation_runs
                SET status = 'running', started_at = ?
                WHERE run_id = ?
                """,
                (started_at, run_id),
            )
            conn.execute("COMMIT")
        self.add_run_event(
            run_id,
            AutomationRunEvent(
                run_id=run_id,
                event_type="claimed",
                message="Executor claimed run.",
                created_at=started_at,
            ),
        )
        return self.get_run(run_id)

    def complete_run(
        self,
        run_id: str,
        *,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
        result_json_path: Path | None = None,
        artifacts_dir: Path | None = None,
        log_path: Path | None = None,
    ) -> AutomationRunRecord:
        finished_at = _utcnow()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE automation_runs
                SET status = ?, finished_at = ?, error_code = ?, error_message = ?,
                    result_json_path = ?, artifacts_dir = ?, log_path = ?
                WHERE run_id = ?
                """,
                (
                    status,
                    finished_at,
                    error_code,
                    error_message,
                    str(result_json_path) if result_json_path else None,
                    str(artifacts_dir) if artifacts_dir else None,
                    str(log_path) if log_path else None,
                    run_id,
                ),
            )
            row = conn.execute(
                "SELECT automation_id FROM automation_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is not None and status == "success":
                conn.execute(
                    """
                    UPDATE automations
                    SET last_run_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (finished_at, finished_at, str(row["automation_id"])),
                )
        event_type = "task_succeeded" if status == "success" else "task_failed"
        message = (
            "Task completed successfully."
            if status == "success"
            else (error_message or "Task failed.")
        )
        self.add_run_event(
            run_id,
            AutomationRunEvent(
                run_id=run_id,
                event_type=event_type,
                message=message,
                created_at=finished_at,
                payload={"error_code": error_code} if error_code else {},
            ),
        )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> AutomationRunRecord:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM automation_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return _row_to_run(row)

    def list_runs(self, automation_id: str, *, limit: int = 50) -> list[AutomationRunRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM automation_runs
                WHERE automation_id = ?
                ORDER BY queued_at DESC
                LIMIT ?
                """,
                (automation_id, limit),
            ).fetchall()
        return [_row_to_run(row) for row in rows]

    def list_run_events(self, run_id: str) -> list[AutomationRunEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM automation_run_events
                WHERE run_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (run_id,),
            ).fetchall()
        return [_row_to_event(row) for row in rows]

    def add_run_event(self, run_id: str, event: AutomationRunEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO automation_run_events (run_id, event_type, message, created_at, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    event.event_type,
                    event.message,
                    event.created_at or _utcnow(),
                    json.dumps(event.payload, ensure_ascii=False, sort_keys=True),
                ),
            )

    def retry_run(self, run_id: str) -> AutomationRunRecord:
        source = self.get_run(run_id)
        automation = self.get_automation(source.automation_id)
        queued_at = _utcnow()
        if automation.retry_backoff_seconds > 0:
            queued_at = (
                datetime.now(timezone.utc) + timedelta(seconds=automation.retry_backoff_seconds)
            ).isoformat()
        return self.create_run(
            source.automation_id,
            trigger_type="retry",
            effective_inputs=source.effective_inputs,
            attempt_number=source.attempt_number + 1,
            queued_at=queued_at,
        )

    def service_metrics(self) -> dict[str, Any]:
        with self._connect() as conn:
            queued = conn.execute(
                "SELECT COUNT(*) AS count FROM automation_runs WHERE status = 'queued'"
            ).fetchone()
            running = conn.execute(
                "SELECT COUNT(*) AS count FROM automation_runs WHERE status = 'running'"
            ).fetchone()
            automations = conn.execute("SELECT COUNT(*) AS count FROM automations").fetchone()
        return {
            "automation_count": int(automations["count"]),
            "queued_runs": int(queued["count"]),
            "running_runs": int(running["count"]),
        }

    def _normalize_automation(
        self,
        automation: PersistedAutomationDefinition,
    ) -> PersistedAutomationDefinition:
        task_path = automation.task_path.expanduser().resolve()
        task_meta_path = automation.task_meta_path.expanduser().resolve()
        raw_output_dir = str(automation.output_dir).strip()
        output_dir = (
            (get_app_paths().automation_runs_dir / automation.id).resolve()
            if raw_output_dir in {"", "."}
            else automation.output_dir.expanduser().resolve()
        )
        result_json_path = None
        if automation.result_json_path is not None:
            result_json_path = automation.result_json_path.expanduser()
            if not result_json_path.is_absolute():
                result_json_path = (output_dir / result_json_path).resolve()
        normalized_kind, normalized_payload, normalized_timezone = normalize_schedule(
            automation.schedule_kind,
            automation.schedule_payload,
            timezone_name=automation.timezone,
        )
        definition_status = "valid"
        definition_error: str | None = None
        next_run_at: str | None = None
        try:
            if not task_path.exists():
                raise FileNotFoundError(f"Task file does not exist: {task_path}")
            payload = _load_task_metadata(task_meta_path)
            validate_task_metadata(payload, source=str(task_meta_path))
            if automation.enabled:
                next_run_at = compute_next_run_at(
                    normalized_kind,
                    normalized_payload,
                    timezone_name=normalized_timezone,
                )
        except Exception as exc:
            definition_status = "invalid"
            definition_error = str(exc)
        return replace(
            automation,
            task_path=task_path,
            task_meta_path=task_meta_path,
            output_dir=output_dir,
            result_json_path=result_json_path,
            schedule_kind=normalized_kind,
            schedule_payload=normalized_payload,
            timezone=normalized_timezone,
            definition_status=definition_status,
            definition_error=definition_error,
            next_run_at=next_run_at if automation.enabled else None,
        )


def _automation_to_row(automation: PersistedAutomationDefinition) -> dict[str, Any]:
    return {
        "id": automation.id,
        "name": automation.name,
        "description": automation.description,
        "version": automation.version,
        "task_path": str(automation.task_path),
        "task_meta_path": str(automation.task_meta_path),
        "entrypoint": automation.entrypoint,
        "enabled": 1 if automation.enabled else 0,
        "definition_status": automation.definition_status,
        "definition_error": automation.definition_error,
        "schedule_kind": automation.schedule_kind,
        "schedule_payload_json": json.dumps(
            automation.schedule_payload, ensure_ascii=False, sort_keys=True
        ),
        "timezone": automation.timezone,
        "output_dir": str(automation.output_dir),
        "result_json_path": str(automation.result_json_path)
        if automation.result_json_path
        else None,
        "stdout_mode": automation.stdout_mode,
        "input_overrides_json": json.dumps(
            automation.input_overrides, ensure_ascii=False, sort_keys=True
        ),
        "before_run_hooks_json": json.dumps(list(automation.before_run_hooks), ensure_ascii=False),
        "after_success_hooks_json": json.dumps(
            list(automation.after_success_hooks), ensure_ascii=False
        ),
        "after_failure_hooks_json": json.dumps(
            list(automation.after_failure_hooks), ensure_ascii=False
        ),
        "retry_attempts": automation.retry_attempts,
        "retry_backoff_seconds": automation.retry_backoff_seconds,
        "timeout_seconds": automation.timeout_seconds,
        "created_at": automation.created_at,
        "updated_at": automation.updated_at,
        "last_run_at": automation.last_run_at,
        "next_run_at": automation.next_run_at,
    }


def _row_to_automation(row: sqlite3.Row) -> PersistedAutomationDefinition:
    return PersistedAutomationDefinition(
        id=str(row["id"]),
        name=str(row["name"]),
        task_path=Path(str(row["task_path"])),
        task_meta_path=Path(str(row["task_meta_path"])),
        output_dir=Path(str(row["output_dir"])),
        description=str(row["description"] or ""),
        version=str(row["version"] or "0.1.0"),
        entrypoint=str(row["entrypoint"] or "run"),
        enabled=bool(row["enabled"]),
        definition_status=str(row["definition_status"] or "valid"),
        definition_error=str(row["definition_error"]) if row["definition_error"] else None,
        schedule_kind=str(row["schedule_kind"] or "manual"),
        schedule_payload=json.loads(row["schedule_payload_json"] or "{}"),
        timezone=str(row["timezone"] or "UTC"),
        result_json_path=Path(str(row["result_json_path"])) if row["result_json_path"] else None,
        stdout_mode=str(row["stdout_mode"] or "json"),
        input_overrides=json.loads(row["input_overrides_json"] or "{}"),
        before_run_hooks=tuple(json.loads(row["before_run_hooks_json"] or "[]")),
        after_success_hooks=tuple(json.loads(row["after_success_hooks_json"] or "[]")),
        after_failure_hooks=tuple(json.loads(row["after_failure_hooks_json"] or "[]")),
        retry_attempts=int(row["retry_attempts"] or 0),
        retry_backoff_seconds=int(row["retry_backoff_seconds"] or 0),
        timeout_seconds=float(row["timeout_seconds"])
        if row["timeout_seconds"] is not None
        else None,
        created_at=str(row["created_at"]) if row["created_at"] else None,
        updated_at=str(row["updated_at"]) if row["updated_at"] else None,
        last_run_at=str(row["last_run_at"]) if row["last_run_at"] else None,
        next_run_at=str(row["next_run_at"]) if row["next_run_at"] else None,
    )


def _run_to_row(run: AutomationRunRecord) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "automation_id": run.automation_id,
        "trigger_type": run.trigger_type,
        "status": run.status,
        "effective_inputs_json": json.dumps(
            run.effective_inputs, ensure_ascii=False, sort_keys=True
        ),
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


def _row_to_run(row: sqlite3.Row) -> AutomationRunRecord:
    return AutomationRunRecord(
        run_id=str(row["run_id"]),
        automation_id=str(row["automation_id"]),
        trigger_type=str(row["trigger_type"]),
        status=str(row["status"]),
        effective_inputs=json.loads(row["effective_inputs_json"] or "{}"),
        attempt_number=int(row["attempt_number"] or 0),
        queued_at=str(row["queued_at"]) if row["queued_at"] else None,
        started_at=str(row["started_at"]) if row["started_at"] else None,
        finished_at=str(row["finished_at"]) if row["finished_at"] else None,
        error_code=str(row["error_code"]) if row["error_code"] else None,
        error_message=str(row["error_message"]) if row["error_message"] else None,
        result_json_path=Path(str(row["result_json_path"])) if row["result_json_path"] else None,
        artifacts_dir=Path(str(row["artifacts_dir"])) if row["artifacts_dir"] else None,
        log_path=Path(str(row["log_path"])) if row["log_path"] else None,
    )


def _row_to_event(row: sqlite3.Row) -> AutomationRunEvent:
    return AutomationRunEvent(
        run_id=str(row["run_id"]),
        event_type=str(row["event_type"]),
        message=str(row["message"] or ""),
        created_at=str(row["created_at"]),
        payload=json.loads(row["payload_json"] or "{}"),
    )


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_task_metadata(task_meta_path: Path) -> dict[str, Any]:
    try:
        return json.loads(task_meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Task metadata is invalid JSON: {task_meta_path}: {exc}") from exc
